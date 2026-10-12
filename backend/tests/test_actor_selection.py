"""Tests unitaires hermétiques pour `ActorSelection` (story 009-3, AC1/AC3)."""

import json
import os
import tempfile
import pytest

from app.models.actor_eligibility import ActorRole, EligibilityStatus
from app.models.actor_selection import (
    ActorItem,
    ActorSelection,
    OptimisticLockError,
    SelectionValidationError,
)


def _sample_actor_items():
    return [
        ActorItem(
            entity_uuid="uuid-1",
            entity_name="Alice Martin",
            original_type="Person",
            qualified_role=ActorRole.PERSON,
            eligibility_status=EligibilityStatus.ELIGIBLE,
            confidence=0.95,
            reasoning="Utilisatrice active",
        ),
        ActorItem(
            entity_uuid="uuid-2",
            entity_name="Acme Corp",
            original_type="Organization",
            qualified_role=ActorRole.ORGANIZATION,
            eligibility_status=EligibilityStatus.ELIGIBLE,
            confidence=0.90,
            reasoning="Entreprise de logiciels",
        ),
        ActorItem(
            entity_uuid="uuid-3",
            entity_name="Collectif Citoyen",
            original_type="Group",
            qualified_role=ActorRole.COLLECTIVE,
            eligibility_status=EligibilityStatus.REVIEW,
            confidence=0.60,
            reasoning="Groupe informel à confirmer",
        ),
        ActorItem(
            entity_uuid="uuid-4",
            entity_name="Forfait Pro 49€",
            original_type="Product",
            qualified_role=ActorRole.PRODUCT,
            eligibility_status=EligibilityStatus.INELIGIBLE,
            confidence=1.0,
            reasoning="Offre tarifaire",
        ),
    ]


def test_actor_selection_counts_and_serialization():
    actors = _sample_actor_items()
    selection = ActorSelection(
        simulation_id="sim-123",
        project_id="proj-456",
        graph_id="graph-789",
        input_fingerprint="sha256-abc",
        actors=actors,
    )

    assert selection.counts == {
        "total": 4,
        "eligible": 2,
        "review": 1,
        "ineligible": 1,
    }
    assert len(selection.eligible_actors) == 2
    assert len(selection.review_actors) == 1
    assert len(selection.ineligible_actors) == 1

    data = selection.to_dict()
    assert data["simulation_id"] == "sim-123"
    assert data["revision"] == 1
    assert len(data["actors"]) == 4

    # Désérialisation
    loaded = ActorSelection.from_dict(data)
    assert loaded.simulation_id == selection.simulation_id
    assert loaded.revision == 1
    assert loaded.counts == selection.counts
    assert loaded.actors[0].entity_name == "Alice Martin"


def test_actor_selection_atomic_save_and_load():
    actors = _sample_actor_items()
    selection = ActorSelection(
        simulation_id="sim-123",
        project_id="proj-456",
        graph_id="graph-789",
        input_fingerprint="sha256-abc",
        actors=actors,
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        filepath = os.path.join(tmpdir, "actors.json")
        selection.save_atomic(filepath)

        assert os.path.exists(filepath)
        # Pas de résidu temporaire
        assert not os.path.exists(f"{filepath}.tmp")

        loaded = ActorSelection.load(filepath)
        assert loaded is not None
        assert loaded.simulation_id == "sim-123"
        assert loaded.counts["total"] == 4


def test_apply_review_success():
    actors = _sample_actor_items()
    selection = ActorSelection(
        simulation_id="sim-123",
        project_id="proj-456",
        graph_id="graph-789",
        input_fingerprint="sha256-abc",
        actors=actors,
    )

    # Requalification du collectif en Organisation éligible avec motif
    selection.apply_review(
        expected_revision=1,
        modifications=[
            {
                "entity_uuid": "uuid-3",
                "role": "organization",
                "status": "eligible",
                "justification": "Structure associative formelle dotée de statuts déclarés.",
            }
        ],
    )

    assert selection.revision == 2
    assert selection.counts["eligible"] == 3
    assert selection.counts["review"] == 0
    uuid_3 = selection.by_uuid()["uuid-3"]
    assert uuid_3.qualified_role == ActorRole.ORGANIZATION
    assert uuid_3.eligibility_status == EligibilityStatus.ELIGIBLE
    assert uuid_3.is_human_modified is True
    assert uuid_3.justification == "Structure associative formelle dotée de statuts déclarés."
    assert len(selection.modifications_history) == 1
    assert selection.modifications_history[0].revision == 2


def test_apply_review_optimistic_lock_conflict():
    actors = _sample_actor_items()
    selection = ActorSelection(
        simulation_id="sim-123",
        project_id="proj-456",
        graph_id="graph-789",
        input_fingerprint="sha256-abc",
        revision=2,  # Déjà en révision 2
        actors=actors,
    )

    with pytest.raises(OptimisticLockError) as exc_info:
        selection.apply_review(
            expected_revision=1,  # Obsolète !
            modifications=[
                {
                    "entity_uuid": "uuid-3",
                    "role": "organization",
                    "status": "eligible",
                    "justification": "Arbitrage",
                }
            ],
        )
    assert "Conflit de révision" in str(exc_info.value)


def test_apply_review_rejects_passive_role_as_eligible():
    actors = _sample_actor_items()
    selection = ActorSelection(
        simulation_id="sim-123",
        project_id="proj-456",
        graph_id="graph-789",
        input_fingerprint="sha256-abc",
        actors=actors,
    )

    # Tentative d'arbitrage illicite : transformer un produit en éligible
    with pytest.raises(SelectionValidationError) as exc_info:
        selection.apply_review(
            expected_revision=1,
            modifications=[
                {
                    "entity_uuid": "uuid-4",
                    "role": "product",
                    "status": "eligible",
                    "justification": "Je veux que le produit poste sur Twitter",
                }
            ],
        )
    assert "Interdiction stricte" in str(exc_info.value)
    assert "product" in str(exc_info.value)


def test_apply_review_rejects_empty_justification():
    actors = _sample_actor_items()
    selection = ActorSelection(
        simulation_id="sim-123",
        project_id="proj-456",
        graph_id="graph-789",
        input_fingerprint="sha256-abc",
        actors=actors,
    )

    with pytest.raises(SelectionValidationError) as exc_info:
        selection.apply_review(
            expected_revision=1,
            modifications=[
                {
                    "entity_uuid": "uuid-3",
                    "role": "organization",
                    "status": "eligible",
                    "justification": "   ",  # Justification vide
                }
            ],
        )
    assert "Justification obligatoire" in str(exc_info.value)


def test_apply_review_rejects_unknown_entity():
    actors = _sample_actor_items()
    selection = ActorSelection(
        simulation_id="sim-123",
        project_id="proj-456",
        graph_id="graph-789",
        input_fingerprint="sha256-abc",
        actors=actors,
    )

    with pytest.raises(SelectionValidationError) as exc_info:
        selection.apply_review(
            expected_revision=1,
            modifications=[
                {
                    "entity_uuid": "uuid-inconnu",
                    "role": "person",
                    "status": "eligible",
                    "justification": "Entité inexistante",
                }
            ],
        )
    assert "Entité inconnue" in str(exc_info.value)


def test_actor_item_from_dict_with_none_values():
    """Vérifie la robustesse face aux champs explicitement None dans le dictionnaire JSON."""
    data = {
        "entity_uuid": "uuid-none",
        "entity_name": "Test Entity",
        "original_type": None,
        "qualified_role": None,
        "eligibility_status": None,
        "confidence": None,
        "reasoning": None,
    }
    item = ActorItem.from_dict(data)
    assert item.entity_uuid == "uuid-none"
    assert item.original_type == "Entity"
    assert item.qualified_role == ActorRole.UNKNOWN
    assert item.eligibility_status == EligibilityStatus.REVIEW
    assert item.confidence == 0.0
    assert item.reasoning == ""
