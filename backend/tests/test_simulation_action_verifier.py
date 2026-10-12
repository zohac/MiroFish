"""Tests unitaires pour SimulationActionVerifier (Story 009-4, AC3, AC4, AC5, AC6)."""

import json
import os
import pytest

from app.models.source_document import (
    ConflictResolutionRule,
    ConflictStatus,
    DocumentRole,
    DocumentValidationStatus,
    SourceConflict,
    SourceReference,
)
from app.services.simulation_action_verifier import (
    ActionEventRecord,
    CitationVerificationResult,
    IntentionAnalysisResult,
    SimulationActionVerifier,
)


def test_action_event_id_computation_deterministic():
    """Vérifie que l'event_id est déterministe et stable (AC3)."""
    id1 = SimulationActionVerifier.compute_event_id(
        "sim_100", "twitter", 2, 42, "CREATE_POST", "2026-10-12T10:00:00"
    )
    id2 = SimulationActionVerifier.compute_event_id(
        "sim_100", "twitter", 2, 42, "CREATE_POST", "2026-10-12T10:00:00"
    )
    assert id1 == id2
    assert id1.startswith("evt_twitter_2_42_")


def test_load_simulation_actions_and_verify_observed_action(tmp_path):
    """Vérifie le chargement des actions et l'authentification d'une action observée (AC3)."""
    sim_dir = tmp_path / "sim_test"
    sim_dir.mkdir()
    twitter_dir = sim_dir / "twitter"
    twitter_dir.mkdir()

    # Créer un fichier actions.jsonl Twitter avec un événement de publication et un événement round_start
    actions_path = twitter_dir / "actions.jsonl"
    entries = [
        {"round": 1, "timestamp": "2026-10-12T10:01:00", "event_type": "round_start"},
        {
            "round": 1,
            "timestamp": "2026-10-12T10:02:00",
            "agent_id": 7,
            "agent_name": "Alice",
            "action_type": "unsubscribe",
            "action_args": {"reason": "prix élevé"},
            "result": "Résiliation confirmée",
            "success": True,
        },
        {
            "round": 1,
            "timestamp": "2026-10-12T10:03:00",
            "agent_id": 8,
            "agent_name": "Bob",
            "action_type": "like",
            "action_args": {"post_id": 12},
            "result": "Like",
            "success": False,  # échec
        },
    ]
    with open(actions_path, "w", encoding="utf-8") as f:
        for entry in entries:
            f.write(json.dumps(entry) + "\n")

    verifier = SimulationActionVerifier(simulation_id="sim_test")
    actions = verifier.load_simulation_actions(simulation_id="sim_test", sim_dir=str(sim_dir))

    # Seules les actions sans event_type sont chargées
    assert len(actions) == 2
    act_alice = actions[0]
    assert act_alice.agent_name == "Alice"
    assert act_alice.action_type == "unsubscribe"
    assert act_alice.success is True
    assert act_alice.event_id.startswith("evt_twitter_1_7_")

    # Vérification d'action observée pour Alice
    event = verifier.verify_observed_action("sim_test", 7, "unsubscribe")
    assert event is not None
    assert event.event_id == act_alice.event_id

    # Pour Bob, action échouée -> non vérifiée comme action observée
    assert verifier.verify_observed_action("sim_test", 8, "like") is None

    # Pour Charlie (inexistant) -> None
    assert verifier.verify_observed_action("sim_test", 99, "unsubscribe") is None


def test_anti_affabulation_guard_c7(tmp_path):
    """RÈGLE D'OR C7 : Un post d'intention sans action effective ne devient pas une action observée (AC4)."""
    sim_dir = tmp_path / "sim_c7"
    sim_dir.mkdir()
    twitter_dir = sim_dir / "twitter"
    twitter_dir.mkdir()

    # Agent 10 (Claire) exprime son intention de résilier, mais n'effectue AUCUNE action de résiliation
    # Agent 11 (David) exprime son intention et effectue ensuite une action réelle
    actions_path = twitter_dir / "actions.jsonl"
    entries = [
        {
            "round": 1,
            "timestamp": "2026-10-12T10:00:00",
            "agent_id": 10,
            "agent_name": "Claire",
            "action_type": "CREATE_POST",
            "action_args": {"content": "Ce service est insupportable, je vais résilier mon abonnement dès demain !"},
            "result": "Post créé",
            "success": True,
        },
        {
            "round": 1,
            "timestamp": "2026-10-12T10:05:00",
            "agent_id": 11,
            "agent_name": "David",
            "action_type": "CREATE_POST",
            "action_args": {"content": "Je vais résilier mon abonnement tout de suite."},
            "result": "Post créé",
            "success": True,
        },
        {
            "round": 2,
            "timestamp": "2026-10-12T10:10:00",
            "agent_id": 11,
            "agent_name": "David",
            "action_type": "unsubscribe",
            "action_args": {},
            "result": "Désabonnement exécuté",
            "success": True,
        },
    ]
    with open(actions_path, "w", encoding="utf-8") as f:
        for entry in entries:
            f.write(json.dumps(entry) + "\n")

    verifier = SimulationActionVerifier(simulation_id="sim_c7")
    verifier.load_simulation_actions(simulation_id="sim_c7", sim_dir=str(sim_dir))

    intentions = verifier.analyze_intentions("sim_c7")
    assert len(intentions) == 2

    # Claire : simple intention, aucune action observée
    intent_claire = next(it for it in intentions if it.agent_id == 10)
    assert intent_claire.has_executed_action is False
    assert intent_claire.status == "intention_simulee_exprimee"
    assert "Intention simulée exprimée" in intent_claire.qualification
    assert intent_claire.matching_event_id is None

    # David : intention confirmée par une action réelle
    intent_david = next(it for it in intentions if it.agent_id == 11)
    assert intent_david.has_executed_action is True
    assert intent_david.status == "action_observee"
    assert intent_david.matching_event_id is not None

    # Contrôle d'affirmation du rapport (validate_report_claim) :
    # Si le rapport prétend que Claire a résilié -> INTERDIT / REQUALIFIÉ
    claim_claire = verifier.validate_report_claim("sim_c7", "Claire a résilié son contrat", 10, "unsubscribe")
    assert claim_claire["allowed_as_observed_action"] is False
    assert claim_claire["qualification"] == "intention_simulee_exprimee"
    assert "Interdiction anti-affabulation (C7)" in claim_claire["warning"]

    # Si le rapport prétend que David a résilié -> AUTORISÉ
    claim_david = verifier.validate_report_claim("sim_c7", "David a résilié son contrat", 11, "unsubscribe")
    assert claim_david["allowed_as_observed_action"] is True
    assert claim_david["qualification"] == "action_observee"
    assert claim_david["event_id"] == intent_david.matching_event_id


def test_citation_verifier_exact_match_and_alteration_detection():
    """Garantie zéro citation fabriquée (AC6) : vérification exacte contre le texte source."""
    doc_text = "Le Conseil d'État a statué que la redevance sur les réseaux est conforme à la directive européenne."

    # 1. Citation exacte avec positions
    res_exact = SimulationActionVerifier.verify_citation(
        document_text=doc_text,
        claimed_citation="la redevance sur les réseaux est conforme",
        char_start=31,
        char_end=72,
        source_filename="decision_ce.txt",
    )
    assert res_exact.valid is True
    assert res_exact.exact_match is True
    assert res_exact.error is None

    # 2. Citation altérée à la même position -> interception
    res_altered = SimulationActionVerifier.verify_citation(
        document_text=doc_text,
        claimed_citation="la taxe sur les réseaux est ILLÉGALE",
        char_start=31,
        char_end=72,
        source_filename="decision_ce.txt",
    )
    assert res_altered.valid is False
    assert res_altered.exact_match is False
    assert "Altération textuelle" in res_altered.error

    # 3. Citation hors limites
    res_oob = SimulationActionVerifier.verify_citation(
        document_text=doc_text,
        claimed_citation="test",
        char_start=200,
        char_end=250,
        source_filename="decision_ce.txt",
    )
    assert res_oob.valid is False
    assert "hors limites" in res_oob.error

    # 4. Citation fabriquée / non trouvée dans le texte
    res_fake = SimulationActionVerifier.verify_citation(
        document_text=doc_text,
        claimed_citation="Le ministre a démissionné en raison du scandale financier.",
        source_filename="decision_ce.txt",
    )
    assert res_fake.valid is False
    assert "non retrouvée" in res_fake.error


def test_format_conflicts_for_report():
    """Traitement transparent des contradictions documentaires (AC5)."""
    ref1 = SourceReference(
        document_id="doc_a",
        filename="bilan_2025.pdf",
        role=DocumentRole.FACTS,
        priority=1,
        date="2025-12-31",
        validation_status=DocumentValidationStatus.VALIDATED,
        chunk_index=2,
        char_start=100,
        char_end=180,
    )
    ref2 = SourceReference(
        document_id="doc_b",
        filename="audit_externe.pdf",
        role=DocumentRole.FACTS,
        priority=2,
        date="2026-02-15",
        validation_status=DocumentValidationStatus.CONFLICTED,
        chunk_index=0,
        char_start=50,
        char_end=120,
    )

    # Conflit ouvert
    conflict_open = SourceConflict(
        conflict_id="conf_1",
        claim="Chiffre d'affaires annuel de l'entité",
        source_references=[ref1, ref2],
        status=ConflictStatus.OPEN,
    )

    formatted_open = SimulationActionVerifier.format_conflicts_for_report([conflict_open])
    assert "Chiffre d'affaires annuel" in formatted_open
    assert "`bilan_2025.pdf`" in formatted_open
    assert "`audit_externe.pdf`" in formatted_open
    assert "**À confirmer**" in formatted_open

    # Conflit résolu par règle
    conflict_resolved = SourceConflict(
        conflict_id="conf_2",
        claim="Nombre d'adhérents actifs",
        source_references=[ref1, ref2],
        resolution_rule=ConflictResolutionRule.VALIDATION_STATUS,
        resolution="doc_a",
        status=ConflictStatus.RESOLVED,
    )
    formatted_resolved = SimulationActionVerifier.format_conflicts_for_report([conflict_resolved])
    assert "Résolu selon la règle `validation_status`" in formatted_resolved
    assert "source retenue : `doc_a`" in formatted_resolved


def test_compute_event_id_rejects_missing_timestamp():
    """Vérifie que `compute_event_id` lève une `ValueError` sur timestamp vide (AC3)."""
    with pytest.raises(ValueError, match="timestamp"):
        SimulationActionVerifier.compute_event_id(
            "sim_x", "twitter", 1, 1, "post", ""
        )
    with pytest.raises(ValueError, match="timestamp"):
        SimulationActionVerifier.compute_event_id(
            "sim_x", "twitter", 1, 1, "post", "   "
        )


def test_load_simulation_actions_invalidates_cache_on_file_change(tmp_path):
    """Vérifie que le cache `_action_cache` est invalidé quand un fichier change."""
    sim_dir = tmp_path / "sim_cache"
    sim_dir.mkdir()
    twitter_dir = sim_dir / "twitter"
    twitter_dir.mkdir()
    actions_path = twitter_dir / "actions.jsonl"
    actions_path.write_text(
        json.dumps(
            {
                "round": 1,
                "timestamp": "2026-10-12T10:00:00",
                "agent_id": 1,
                "action_type": "CREATE_POST",
                "action_args": {"content": "Hello"},
                "success": True,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    verifier = SimulationActionVerifier(simulation_id="sim_cache")
    first = verifier.load_simulation_actions(simulation_id="sim_cache", sim_dir=str(sim_dir))
    assert len(first) == 1
    assert first[0].event_id  # l'event_id est non vide

    # Le second appel sans modification du fichier doit réutiliser le cache
    second = verifier.load_simulation_actions(simulation_id="sim_cache", sim_dir=str(sim_dir))
    assert len(second) == 1
    assert second[0].event_id == first[0].event_id

    # On ajoute une nouvelle action et on force un mtime ultérieur
    import time
    time.sleep(0.01)
    with open(actions_path, "a", encoding="utf-8") as f:
        f.write(
            json.dumps(
                {
                    "round": 2,
                    "timestamp": "2026-10-12T10:01:00",
                    "agent_id": 2,
                    "action_type": "vote",
                    "action_args": {},
                    "success": True,
                }
            )
            + "\n"
        )

    third = verifier.load_simulation_actions(simulation_id="sim_cache", sim_dir=str(sim_dir))
    assert len(third) == 2  # le cache a été invalidé, le nouvel événement est lu


def test_refresh_simulation_actions_forces_reload(tmp_path):
    """Vérifie que `refresh_simulation_actions` force le rechargement."""
    sim_dir = tmp_path / "sim_refresh"
    sim_dir.mkdir()
    twitter_dir = sim_dir / "twitter"
    twitter_dir.mkdir()
    actions_path = twitter_dir / "actions.jsonl"
    actions_path.write_text(
        json.dumps(
            {
                "round": 1,
                "timestamp": "2026-10-12T10:00:00",
                "agent_id": 1,
                "action_type": "CREATE_POST",
                "action_args": {"content": "Hello"},
                "success": True,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    verifier = SimulationActionVerifier(simulation_id="sim_refresh")
    verifier.load_simulation_actions(simulation_id="sim_refresh", sim_dir=str(sim_dir))

    # On force un mtime ultérieur (les filesystems coarse-grained peuvent
    # produire le même mtime sur deux écritures rapprochées) puis on
    # réécrit le fichier avec un contenu différent.
    import os
    import time
    future = time.time() + 1
    os.utime(actions_path, (future, future))
    actions_path.write_text(
        json.dumps(
            {
                "round": 1,
                "timestamp": "2026-10-12T10:05:00",
                "agent_id": 1,
                "action_type": "CREATE_POST",
                "action_args": {"content": "Bonjour"},
                "success": True,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    refreshed = verifier.refresh_simulation_actions(simulation_id="sim_refresh", sim_dir=str(sim_dir))
    assert refreshed[0].action_args["content"] == "Bonjour"


def test_verify_citation_strict_no_whitespace_normalization():
    """Vérifie que `verify_citation` rejette les citations qui ne matchent pas exactement (AC6)."""
    doc_text = "Le Conseil d'État a statué sur la conformité de la redevance."

    # Espaces surnuméraires : la citation est altérée, le vérificateur doit refuser
    res_altered = SimulationActionVerifier.verify_citation(
        document_text=doc_text,
        claimed_citation="la  conformité  de la redevance",  # doubles espaces
        char_start=doc_text.index("conformité"),
        char_end=doc_text.index("redevance.") + len("redevance."),
        source_filename="ce.txt",
    )
    assert res_altered.valid is False
    assert res_altered.exact_match is False
    assert "diffère" in (res_altered.error or "")


def test_analyze_intentions_covers_extended_action_types():
    """Vérifie que les motifs étendus couvrent pétitions, dons, partages, commentaires et plaintes (C7)."""
    extended_posts = [
        ("Je vais signer la pétition dès demain.", "sign_petition"),
        ("I will sign the petition now.", "sign_petition"),
        ("Je compte faire un don de 50€.", "donate"),
        ("I will donate 100$ to the cause.", "donate"),
        ("Je vais partager ce post avec mes amis.", "share"),
        ("I will retweet this message.", "share"),
        ("Je vais déposer une plainte.", "file_complaint"),
        ("I will file a complaint tomorrow.", "file_complaint"),
        ("Je vais commenter cet article.", "comment"),
        ("I will reply to this thread.", "comment"),
    ]
    for content, expected in extended_posts:
        matched = [
            (pat, act) for pat, act in SimulationActionVerifier.INTENTION_PATTERNS
            if pat.search(content)
        ]
        assert matched, f"Aucun motif trouvé pour : {content!r}"
        assert any(act == expected for _, act in matched), (
            f"Motif trouvé pour {content!r} mais pas le type attendu {expected!r} : {matched}"
        )
