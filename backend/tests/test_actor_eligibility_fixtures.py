"""Contrat des jeux annotés préparant la story 009-1, sans classifieur réel."""

import json
from dataclasses import fields
from pathlib import Path
from uuid import UUID

import pytest

from app.services.zep_entity_reader import EntityNode


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "actor_eligibility"
DATASET_NAMES = ("logiciel_gestion", "evenement_culturel")
ROLES = {
    "person", "organization", "collective", "product", "service",
    "domain", "place", "event", "concept", "unknown",
}
REQUIRED_TAGS = {
    "generic_actor", "typed_actor", "composite_actor", "brand_organization",
    "brand_product", "product", "tariff", "url", "domain", "place",
    "event", "concept", "collective", "ambiguous", "date", "duration",
    "fiction", "untrusted_eligibility", "misleading_label", "empty_identity",
    "duration_in_name", "amount_in_name", "date_in_name", "exact_homonym",
}


def load_dataset(name):
    return json.loads((FIXTURE_DIR / f"{name}.json").read_text(encoding="utf-8"))


@pytest.fixture(params=DATASET_NAMES)
def dataset(request):
    return load_dataset(request.param)


def test_dataset_declares_annotation_context(dataset):
    """La consigne et la politique rendent les attentes interprétables."""
    assert dataset["schema_version"] == 1
    assert dataset["dataset_id"] in DATASET_NAMES
    assert dataset["domain"].strip()
    assert dataset["policy_version"] == "009-1-v1"
    assert dataset["synthetic"] is True
    assert dataset["simulation_requirement"].strip()


def test_entity_payload_matches_reader_contract(dataset):
    """Les annotations restent hors des arguments du lecteur existant."""
    field_names = {field.name for field in fields(EntityNode)}
    for case in dataset["cases"]:
        assert set(case) == {"case_id", "entity", "expected", "tags"}
        raw = case["entity"]
        assert set(raw) == field_names, case["case_id"]
        entity = EntityNode(**raw)
        assert str(UUID(entity.uuid)) == entity.uuid
        assert isinstance(entity.name, str)
        assert isinstance(entity.summary, str)
        assert all(isinstance(label, str) for label in entity.labels)
        assert isinstance(entity.attributes, dict)
        assert entity.to_dict() == raw


def test_case_identifiers_are_unique(dataset):
    identifiers = [case["case_id"] for case in dataset["cases"]]
    assert all(identifier.strip() for identifier in identifiers)
    assert len(set(identifiers)) == len(identifiers)


def test_entity_identifiers_are_globally_unique():
    identifiers = [
        case["entity"]["uuid"]
        for name in DATASET_NAMES
        for case in load_dataset(name)["cases"]
    ]
    assert len(set(identifiers)) == len(identifiers)


def test_annotations_follow_minimal_role_policy(dataset):
    """Un statut attendu ne peut contredire la politique du lot."""
    for case in dataset["cases"]:
        expected = case["expected"]
        assert set(expected) == {"role", "status", "rationale"}
        assert expected["role"] in ROLES
        assert expected["rationale"].strip()
        role = expected["role"]
        if role in {"person", "organization"}:
            assert expected["status"] == "eligible", case["case_id"]
        elif role in {"collective", "unknown"}:
            assert expected["status"] == "review", case["case_id"]
        else:
            assert expected["status"] == "ineligible", case["case_id"]


def test_dataset_meets_multidomain_coverage(dataset):
    assert len(dataset["cases"]) >= 10
    actors = [case for case in dataset["cases"] if case["expected"]["status"] == "eligible"]
    assert len(actors) >= 2
    assert {case["expected"]["role"] for case in actors} == {"person", "organization"}
    assert {case["expected"]["role"] for case in dataset["cases"]} == ROLES
    assert any(case["entity"]["labels"] == ["Entity"] for case in actors)
    assert any(case["entity"]["labels"] != ["Entity"] for case in actors)


def test_dataset_covers_required_boundary_cases(dataset):
    tags = {tag for case in dataset["cases"] for tag in case["tags"]}
    assert REQUIRED_TAGS <= tags
    syntactic_cases = [
        case for case in dataset["cases"] if "deterministic_exclusion" in case["tags"]
    ]
    assert {case["expected"]["role"] for case in syntactic_cases} == {
        "domain", "product", "event", "concept",
    }
    assert all(case["expected"]["status"] == "ineligible" for case in syntactic_cases)
    composite_cases = [case for case in dataset["cases"] if "composite_actor" in case["tags"]]
    assert all(case["expected"]["status"] == "eligible" for case in composite_cases)
    assert all("deterministic_exclusion" not in case["tags"] for case in composite_cases)


def test_dataset_contains_exact_product_organization_homonym(dataset):
    by_name = {}
    for case in dataset["cases"]:
        by_name.setdefault(case["entity"]["name"], []).append(case)
    assert any(
        {case["expected"]["role"] for case in cases} >= {"organization", "product"}
        for cases in by_name.values()
    )


@pytest.mark.parametrize(
    ("actor_tag", "value_tag"),
    [("amount_in_name", "tariff"), ("date_in_name", "date"), ("duration_in_name", "duration")],
)
def test_composite_actor_contains_whole_passive_value(dataset, actor_tag, value_tag):
    """La collision promise existe dans les noms, pas seulement dans leurs tags."""
    actors = [case for case in dataset["cases"] if actor_tag in case["tags"]]
    values = [case for case in dataset["cases"] if value_tag in case["tags"]]
    assert actors
    assert values
    for actor in actors:
        assert actor["expected"]["status"] == "eligible"
        assert any(
            value["entity"]["name"] in actor["entity"]["name"]
            and value["entity"]["name"] != actor["entity"]["name"]
            and value["expected"]["status"] == "ineligible"
            for value in values
        )


def test_relationship_context_resolves_within_dataset(dataset):
    """Chaque voisin est le nœud réel décrit dans ce même jeu."""
    nodes = {case["entity"]["uuid"]: case["entity"] for case in dataset["cases"]}
    assert any(node["related_edges"] for node in nodes.values())
    for node in nodes.values():
        neighbor_ids = {neighbor["uuid"] for neighbor in node["related_nodes"]}
        edge_neighbor_ids = set()
        for edge in node["related_edges"]:
            assert edge["direction"] in {"incoming", "outgoing"}
            key = "target_node_uuid" if edge["direction"] == "outgoing" else "source_node_uuid"
            other_id = edge[key]
            assert other_id in nodes
            assert other_id != node["uuid"]
            assert edge["fact"].strip()
            edge_neighbor_ids.add(other_id)
            opposite = "incoming" if edge["direction"] == "outgoing" else "outgoing"
            opposite_key = "source_node_uuid" if opposite == "incoming" else "target_node_uuid"
            assert any(
                candidate["direction"] == opposite
                and candidate[opposite_key] == node["uuid"]
                and candidate["fact"] == edge["fact"]
                for candidate in nodes[other_id]["related_edges"]
            )
        assert neighbor_ids == edge_neighbor_ids
        for neighbor in node["related_nodes"]:
            target = nodes[neighbor["uuid"]]
            assert neighbor == {key: target[key] for key in ("uuid", "name", "labels", "summary")}


def test_untrusted_actor_override_stays_in_passive_case(dataset):
    """Le contre-exemple hostile conserve un oracle indépendant des attributs."""
    hostile = [case for case in dataset["cases"] if "untrusted_eligibility" in case["tags"]]
    assert hostile
    for case in hostile:
        assert case["entity"]["attributes"]["status"] == "eligible"
        assert case["entity"]["attributes"]["role"] == "person"
        assert "Person" in case["entity"]["labels"]
        assert case["expected"]["role"] == "product"
        assert case["expected"]["status"] == "ineligible"
