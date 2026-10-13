"""Couverture de la validation Graphiti et de la politique ontologique 007-2."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app import create_app
from app.api import project as project_api
from app.models.project import ProjectManager, ProjectStatus
from app.utils.graph_store import GraphStore, GraphValidationWarning
from app.utils.graph_store.errors import GraphNotFoundError, GraphValidationError
from app.utils.graph_store.graphiti_store import _OntologyValidatingGraphiti
from app.utils.graph_store.ontology_warnings import append_ontology_warning, read_ontology_warnings


def _warning(graph_id, timestamp, attempted_type="id=999"):
    return GraphValidationWarning(
        graph_id=graph_id,
        attempted_type=attempted_type,
        node_uuid=None,
        source_call="test",
        message=f"Type refusé : {attempted_type}",
        timestamp=timestamp,
    )


def _validator(strict=False, count=2, warnings=None):
    warnings = warnings if warnings is not None else []
    engine = _OntologyValidatingGraphiti.__new__(_OntologyValidatingGraphiti)
    applied = SimpleNamespace(
        entity_types={f"Type{i}": object() for i in range(1, count + 1)},
        neutre=SimpleNamespace(strict=strict),
    )
    engine._ontology_resolver = lambda graph_id: applied
    engine._warning_callback = lambda *args: warnings.append(args)
    return engine, warnings


@pytest.mark.parametrize("type_id", [1, 2])
def test_type_declare_est_conserve(type_id):
    engine, warnings = _validator()
    response = {"extracted_entities": [{"name": "x", "entity_type_id": type_id}]}
    result = engine._validate_response(response, type("ExtractedEntities", (), {}), "g")
    assert result["extracted_entities"][0]["entity_type_id"] == type_id
    assert warnings == []


@pytest.mark.parametrize("type_id,expected", [(0, "Entity"), (999, "id=999")])
def test_type_hors_ontologie_est_retrograde_et_journalise(type_id, expected):
    engine, warnings = _validator()
    response = {"extracted_entities": [{"name": "x", "entity_type_id": type_id}]}
    result = engine._validate_response(response, type("ExtractedEntities", (), {}), "g")
    assert result["extracted_entities"][0]["entity_type_id"] == 0
    assert warnings[0][0:3] == ("g", expected, None)


@pytest.mark.parametrize("type_id", [0, 999])
def test_type_hors_ontologie_strict_est_refuse(type_id):
    engine, warnings = _validator(strict=True)
    with pytest.raises(GraphValidationError, match="g"):
        engine._validate_response(
            {"extracted_entities": [{"name": "x", "entity_type_id": type_id}]},
            type("ExtractedEntities", (), {}),
            "g",
        )
    assert warnings == []


def test_reponse_structuree_invalide_est_refusee():
    engine, _ = _validator()
    with pytest.raises(GraphValidationError, match="ExtractedEntities"):
        engine._validate_response({}, type("ExtractedEntities", (), {}), "g")


def test_type_non_entier_est_refuse():
    engine, _ = _validator()
    with pytest.raises(GraphValidationError, match="invalide"):
        engine._validate_response(
            {"extracted_entities": [{"name": "x", "entity_type_id": "1"}]},
            type("ExtractedEntities", (), {}),
            "g",
        )


def test_reponse_sans_ontologie_reste_inchangee():
    engine = _OntologyValidatingGraphiti.__new__(_OntologyValidatingGraphiti)
    engine._ontology_resolver = lambda graph_id: None
    response = {"extracted_entities": [{"name": "x", "entity_type_id": 999}]}
    assert engine._validate_response(response, type("ExtractedEntities", (), {}), "g") == response


def test_journal_est_durable_et_isole(tmp_path, monkeypatch):
    from app.config import Config

    monkeypatch.setattr(Config, "UPLOAD_FOLDER", str(tmp_path))
    timestamp = "2026-10-12T10:00:00+00:00"
    append_ontology_warning(_warning("g1", timestamp))
    append_ontology_warning(_warning("g2", timestamp, "Entity"))
    assert [item.graph_id for item in read_ontology_warnings("g1")] == ["g1"]
    assert read_ontology_warnings("g2")[0].attempted_type == "Entity"
    assert read_ontology_warnings("unknown") == []


def test_journal_est_ordonne(tmp_path, monkeypatch):
    from app.config import Config

    monkeypatch.setattr(Config, "UPLOAD_FOLDER", str(tmp_path))
    append_ontology_warning(_warning("g", "2026-10-12T10:02:00+00:00", "late"))
    append_ontology_warning(_warning("g", "2026-10-12T10:01:00+00:00", "early"))
    assert [item.attempted_type for item in read_ontology_warnings("g")] == ["early", "late"]


def test_journal_since_est_inclusif_et_normalise(tmp_path, monkeypatch):
    from app.config import Config

    monkeypatch.setattr(Config, "UPLOAD_FOLDER", str(tmp_path))
    append_ontology_warning(_warning("g", "2026-10-12T10:00:00+00:00", "exact"))
    append_ontology_warning(_warning("g", "2026-10-12T10:01:00+00:00", "later"))
    result = read_ontology_warnings("g", since="2026-10-12T12:00:00+02:00")
    assert [item.attempted_type for item in result] == ["exact", "later"]


@pytest.mark.parametrize("since", ["2026-10-12T10:00:00", "invalid", ""])
def test_journal_refuse_date_invalide(since, tmp_path, monkeypatch):
    from app.config import Config

    monkeypatch.setattr(Config, "UPLOAD_FOLDER", str(tmp_path))
    with pytest.raises(GraphValidationError):
        read_ontology_warnings("g", since=since)


def test_project_strict_ontology_est_retrocompatible(tmp_path, monkeypatch):
    monkeypatch.setattr(ProjectManager, "PROJECTS_DIR", str(tmp_path / "projects"))
    project = ProjectManager.create_project("policy")
    assert project.strict_ontology is False
    project.strict_ontology = True
    ProjectManager.save_project(project)
    assert ProjectManager.get_project(project.project_id).strict_ontology is True


@pytest.fixture
def policy_client(tmp_path, monkeypatch):
    monkeypatch.setattr(ProjectManager, "PROJECTS_DIR", str(tmp_path / "projects"))
    monkeypatch.setattr(project_api, "get_graph_store", lambda: MagicMock(spec=GraphStore))
    app = create_app()
    app.config.update(TESTING=True)
    return app.test_client()


def test_policy_patch_persiste(policy_client):
    project = ProjectManager.create_project("policy")
    response = policy_client.patch(
        f"/api/project/{project.project_id}/ontology/policy",
        json={"strict_ontology": True},
    )
    assert response.status_code == 200
    assert response.json["data"]["strict_ontology"] is True
    assert ProjectManager.get_project(project.project_id).strict_ontology is True


def test_policy_patch_identique_est_idempotent(policy_client, monkeypatch):
    project = ProjectManager.create_project("policy")
    project.strict_ontology = True
    ProjectManager.save_project(project)
    save_calls = []
    original_save = ProjectManager.save_project
    monkeypatch.setattr(ProjectManager, "save_project", lambda value: save_calls.append(value))
    response = policy_client.patch(
        f"/api/project/{project.project_id}/ontology/policy",
        json={"strict_ontology": True},
    )
    monkeypatch.setattr(ProjectManager, "save_project", original_save)
    assert response.status_code == 200
    assert save_calls == []


@pytest.mark.parametrize("payload", [{}, {"strict_ontology": "false"}, {"strict_ontology": 0}, {"strict_ontology": None}, {"strict_ontology": False, "extra": 1}, []])
def test_policy_patch_rejette_payload_non_conforme(policy_client, payload):
    project = ProjectManager.create_project("policy")
    response = policy_client.patch(
        f"/api/project/{project.project_id}/ontology/policy", json=payload
    )
    assert response.status_code == 400


def test_policy_patch_projet_absent(policy_client):
    response = policy_client.patch(
        "/api/project/absent/ontology/policy", json={"strict_ontology": True}
    )
    assert response.status_code == 404


def test_policy_patch_refuse_pendant_ingestion(policy_client):
    project = ProjectManager.create_project("policy")
    project.status = ProjectStatus.GRAPH_BUILDING
    ProjectManager.save_project(project)
    response = policy_client.patch(
        f"/api/project/{project.project_id}/ontology/policy",
        json={"strict_ontology": True},
    )
    assert response.status_code == 409


def test_warnings_route_expose_journal(policy_client, tmp_path, monkeypatch):
    from app.config import Config

    monkeypatch.setattr(Config, "UPLOAD_FOLDER", str(tmp_path / "uploads"))
    project = ProjectManager.create_project("policy")
    project.graph_id = "graph-policy"
    project.ontology = {"entity_types": [{"name": "Person"}], "edge_types": []}
    ProjectManager.save_project(project)
    append_ontology_warning(_warning(project.graph_id, "2026-10-12T10:00:00+00:00"))
    store = MagicMock(spec=GraphStore)
    store.get_ontology_warnings.side_effect = lambda graph_id, since=None: read_ontology_warnings(graph_id, since)
    monkeypatch.setattr(project_api, "get_graph_store", lambda: store)
    response = policy_client.get(f"/api/project/{project.project_id}/ontology/warnings")
    assert response.status_code == 200
    assert response.json["data"][0]["attempted_type"] == "id=999"


def test_warnings_route_refuse_date_invalide(policy_client, monkeypatch):
    project = ProjectManager.create_project("policy")
    project.graph_id = "graph-policy"
    project.ontology = {"entity_types": [{"name": "Person"}], "edge_types": []}
    ProjectManager.save_project(project)
    store = MagicMock(spec=GraphStore)
    store.get_ontology_warnings.side_effect = GraphValidationError("date invalide")
    monkeypatch.setattr(project_api, "get_graph_store", lambda: store)
    response = policy_client.get(f"/api/project/{project.project_id}/ontology/warnings?since=invalid")
    assert response.status_code == 400


def test_warnings_route_refuse_projet_sans_ontologie(policy_client):
    project = ProjectManager.create_project("policy")
    response = policy_client.get(f"/api/project/{project.project_id}/ontology/warnings")
    assert response.status_code == 404


def test_warnings_route_refuse_projet_absent(policy_client):
    response = policy_client.get("/api/project/absent/ontology/warnings")
    assert response.status_code == 404
