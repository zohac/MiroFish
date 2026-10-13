"""Régressions 007-2 : parcours livré, persistance, concurrence et sauvegarde."""

import asyncio
from copy import deepcopy
import threading
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from graphiti_core.driver.neo4j_driver import Neo4jDriver

from app import create_app
from app.api import graph as graph_api, project as project_api
from app.models.project import ProjectManager, ProjectStatus
from app.models.task import TaskManager, TaskStatus
from app.services.ontology_policy import OntologyPolicyService
from app.utils.graph_store import GraphValidationError
from app.utils.graph_store.errors import GraphNotFoundError
from app.utils.graph_store.factory import override_graph_store
from app.utils.graph_store.graphiti_store import GraphitiGraphStore
from app.utils.graph_store.zep_store import ZepGraphStore
from app.utils.project_locks import project_lock
from scripts.verifier_ontology_validation import DeterministicLLM, DeterministicEmbedder, ONTOLOGY, inject_final_candidate


@pytest.fixture
def pipeline_factory(monkeypatch):
    """Seuls les accès Neo4j sont doublés ; le pipeline et les clients sont réels."""
    stores = []

    def create(type_ids=(1,)):
        driver = Neo4jDriver(uri="bolt://localhost:7687", user="test", password="test")
        monkeypatch.setattr(driver, "execute_query", AsyncMock(return_value=([], None, None)))
        monkeypatch.setattr(driver, "health_check", AsyncMock(return_value=True))
        session = MagicMock()
        session.close = AsyncMock()
        writes = []
        tx = SimpleNamespace(run=AsyncMock(side_effect=lambda query, **kw: writes.append((query, deepcopy(kw))) or []))

        async def execute_write(callback, *args, **kwargs):
            return await callback(tx, *args, **kwargs)
        session.execute_write = execute_write
        monkeypatch.setattr(driver, "session", lambda *args, **kwargs: session)
        llm = DeterministicLLM(type_ids)
        store = GraphitiGraphStore(driver=driver, llm_client=llm, embedder=DeterministicEmbedder())
        stores.append((store, driver))
        return store, writes

    yield create
    for store, driver in stores:
        if not store._closed:
            store._run_async(driver.close())
            store.close()
        else:
            asyncio.run(driver.close())


def _saved_nodes(writes):
    return [node for _, parameters in writes for node in parameters.get("nodes", [])]


@pytest.mark.parametrize("type_id", [0, 999])
def test_pipeline_strict_rejects_before_transaction(pipeline_factory, type_id):
    store, writes = pipeline_factory([type_id])
    store.set_ontology("strict", ONTOLOGY, strict=True)
    with pytest.raises(GraphValidationError, match="hors ontologie.*strict"):
        store.add_episode("strict", "Un acteur.")
    assert writes == []


def test_pipeline_permissive_saves_generic_node(pipeline_factory):
    store, writes = pipeline_factory([999])
    store.set_ontology("permissive", ONTOLOGY)
    store.add_episode("permissive", "Un acteur.")
    assert _saved_nodes(writes)[0]["labels"] == ["Entity"]
    assert store.get_ontology_warnings("permissive")[0].attempted_type == "id=999"


def test_pipeline_declared_type_has_no_warning(pipeline_factory):
    store, writes = pipeline_factory()
    store.set_ontology("declared", ONTOLOGY, strict=True)
    store.add_episode("declared", "Un acteur.")
    assert set(_saved_nodes(writes)[0]["labels"]) == {"Entity", "Person"}
    assert store.get_ontology_warnings("declared") == []


@pytest.mark.parametrize("strict,expected", [(True, 1), (False, 2)])
def test_mixed_batch_uses_episode_policy(pipeline_factory, strict, expected):
    store, writes = pipeline_factory([1, 999])
    store.set_ontology("batch", ONTOLOGY, strict=strict)
    if strict:
        with pytest.raises(GraphValidationError):
            store.add_text_batch("batch", ["Un fait.", "Autre fait."])
    else:
        result = store.add_text_batch("batch", ["Un fait.", "Autre fait."])
        assert len(result.episode_uuids) == 2
    assert len(_saved_nodes(writes)) == expected


@pytest.mark.parametrize("labels", [["Entity", "Unknown"], ["Entity", "Person", "Company"]])
def test_final_invalid_labels_refuse_transaction(pipeline_factory, labels):
    store, writes = pipeline_factory()
    store.set_ontology("final", ONTOLOGY, strict=True)
    inject_final_candidate(store._graphiti, labels=labels)
    with pytest.raises(GraphValidationError, match="hors ontologie.*final"):
        store.add_episode("final", "Un fait.")
    assert writes == []


@pytest.mark.parametrize("labels", [["Entity", "Person", "Unknown"], ["Entity", "Person", "Company"]])
def test_final_downgrade_is_fully_generic(pipeline_factory, labels):
    store, writes = pipeline_factory()
    store.set_ontology("final", ONTOLOGY)
    inject_final_candidate(store._graphiti, labels=labels, attributes={"entity_type": "Unknown", "type": "Unknown", "category": "Unknown"})
    store.add_episode("final", "Un fait.")
    node = _saved_nodes(writes)[0]
    assert node["labels"] == ["Entity"]
    assert not any(key in node for key in ("entity_type", "type", "category"))
    assert len(store.get_ontology_warnings("final")) == 1


def test_existing_labels_removed_in_save_transaction(pipeline_factory):
    store, writes = pipeline_factory()
    store.set_ontology("final", ONTOLOGY)
    inject_final_candidate(store._graphiti, labels=["Entity", "Unknown"], node_uuid="existing")
    store.add_episode("final", "Un fait.")
    query, parameters = writes[0]
    assert "REMOVE n:$(labels(n))" in query
    assert parameters == {"graph_id": "final", "node_ids": ["existing"]}
    assert _saved_nodes(writes)[0]["uuid"] == "existing"


def test_generic_attributes_do_not_reaffirm_rejected_type(pipeline_factory):
    from app.services.zep_entity_reader import EntityNode as ReaderNode

    store, writes = pipeline_factory([999])
    store.set_ontology("generic", ONTOLOGY)
    inject_final_candidate(store._graphiti, labels=["Entity"], attributes={"entity_type": "Unknown"})
    store.add_episode("generic", "Un fait.")
    node = _saved_nodes(writes)[0]
    attributes = {k: v for k, v in node.items() if k not in store._NODE_SYSTEM_KEYS}
    reader = ReaderNode(uuid=node["uuid"], name=node["name"], labels=node["labels"], summary="", attributes=attributes)
    assert reader.get_entity_type() == "Entity"


def test_new_writer_restores_strict_policy(pipeline_factory):
    original, _ = pipeline_factory()
    original.set_ontology("restart", ONTOLOGY, strict=True)
    fresh, writes = pipeline_factory([999])
    with pytest.raises(GraphValidationError):
        fresh.add_episode("restart", "Un fait.")
    assert writes == []
    assert fresh.get_applied_ontology("restart").strict is True


def test_live_writer_reads_changed_policy(pipeline_factory):
    writer, writes = pipeline_factory([999])
    writer.set_ontology("live", ONTOLOGY)
    updater, _ = pipeline_factory()
    updater.update_ontology_policy("live", True)
    with pytest.raises(GraphValidationError):
        writer.add_episode("live", "Un fait.")
    assert writes == []


def test_explicit_ontology_inherits_durable_policy(pipeline_factory):
    original, _ = pipeline_factory()
    original.set_ontology("explicit", ONTOLOGY, strict=True)
    fresh, writes = pipeline_factory([999])
    with pytest.raises(GraphValidationError):
        fresh.add_episode("explicit", "Un fait.", ontology=ONTOLOGY)
    assert writes == []


def test_graph_policies_are_isolated(pipeline_factory):
    store, writes = pipeline_factory([999])
    store.set_ontology("strict", ONTOLOGY, strict=True)
    store.set_ontology("permissive", ONTOLOGY)
    store.add_episode("permissive", "Un fait.")
    assert _saved_nodes(writes)[0]["group_id"] == "permissive"
    assert store.get_ontology_warnings("strict") == []


def test_policy_change_has_no_graph_mutation(pipeline_factory):
    store, writes = pipeline_factory()
    store.set_ontology("policy", ONTOLOGY)
    store.update_ontology_policy("policy", True)
    assert writes == []
    store._driver.execute_query.assert_not_called()


@pytest.mark.parametrize("batch", [False, True])
def test_zep_strict_refuses_before_remote_write(batch):
    client = MagicMock()
    store = ZepGraphStore(client=client)
    store.set_ontology("zep", ONTOLOGY, strict=True)
    client.reset_mock()
    with pytest.raises(GraphValidationError, match="avant persistance"):
        if batch:
            store.add_text_batch("zep", ["Un fait."])
        else:
            store.add_episode("zep", "Un fait.")
    assert client.mock_calls == []


def test_zep_fresh_writer_retains_refusal():
    ZepGraphStore(client=MagicMock()).set_ontology("zep", ONTOLOGY, strict=True)
    client = MagicMock()
    with pytest.raises(GraphValidationError):
        ZepGraphStore(client=client).add_episode("zep", "Un fait.")
    client.graph.add.assert_not_called()


def test_warnings_require_applied_ontology(tmp_path, monkeypatch, pipeline_factory):
    monkeypatch.setattr(ProjectManager, "PROJECTS_DIR", str(tmp_path / "projects"))
    project = ProjectManager.create_project("test")
    project.graph_id = "not-applied"
    project.ontology = ONTOLOGY
    ProjectManager.save_project(project)
    store, _ = pipeline_factory()
    with pytest.raises(GraphNotFoundError):
        OntologyPolicyService.warnings(project.project_id, store)


def test_patch_changes_live_writer_policy(tmp_path, monkeypatch, pipeline_factory):
    monkeypatch.setattr(ProjectManager, "PROJECTS_DIR", str(tmp_path / "projects"))
    project = ProjectManager.create_project("test")
    project.graph_id = "patch"
    project.ontology = ONTOLOGY
    ProjectManager.save_project(project)
    writer, writes = pipeline_factory([999])
    writer.set_ontology("patch", ONTOLOGY)
    updater, _ = pipeline_factory()
    monkeypatch.setattr(project_api, "get_graph_store", lambda: updater)
    response = create_app().test_client().patch(f"/api/project/{project.project_id}/ontology/policy", json={"strict_ontology": True})
    assert response.status_code == 200
    with pytest.raises(GraphValidationError):
        writer.add_episode("patch", "Un fait.")
    assert writes == []


def test_patch_waits_for_build_lock(tmp_path, monkeypatch):
    monkeypatch.setattr(ProjectManager, "PROJECTS_DIR", str(tmp_path / "projects"))
    project = ProjectManager.create_project("test")
    started = threading.Event()
    finished = threading.Event()
    errors = []
    def update():
        started.set()
        try:
            OntologyPolicyService.update(project.project_id, True)
        except GraphValidationError as exc:
            errors.append(str(exc))
        finally:
            finished.set()
    with graph_api._project_build_lock(project.project_id):
        assert graph_api._project_build_lock(project.project_id) is project_lock(project.project_id)
        thread = threading.Thread(target=update)
        thread.start()
        assert started.wait(1)
        assert not finished.wait(0.05)
        project.status = ProjectStatus.GRAPH_BUILDING
        ProjectManager.save_project(project)
    thread.join(2)
    assert finished.is_set()
    assert errors
    assert ProjectManager.get_project(project.project_id).strict_ontology is False


def test_warnings_route_closes_owned_store(tmp_path, monkeypatch, pipeline_factory):
    monkeypatch.setattr(ProjectManager, "PROJECTS_DIR", str(tmp_path / "projects"))
    project = ProjectManager.create_project("journal sans ontologie")
    project.graph_id = "not-applied"
    ProjectManager.save_project(project)
    store, _ = pipeline_factory()
    monkeypatch.setattr(project_api, "get_graph_store", lambda: store)
    response = create_app().test_client().get(f"/api/project/{project.project_id}/ontology/warnings")
    assert response.status_code == 404
    assert not store._async_runner._thread.is_alive()


def test_warnings_route_preserves_override_owner(tmp_path, monkeypatch, pipeline_factory):
    monkeypatch.setattr(ProjectManager, "PROJECTS_DIR", str(tmp_path / "projects"))
    project = ProjectManager.create_project("journal emprunté")
    project.graph_id = "applied"
    ProjectManager.save_project(project)
    store, _ = pipeline_factory()
    store.set_ontology("applied", ONTOLOGY)
    with override_graph_store(store):
        response = create_app().test_client().get(f"/api/project/{project.project_id}/ontology/warnings")
    assert response.status_code == 200
    assert store._async_runner._thread.is_alive()


def test_build_restores_strict_project_preference(tmp_path, monkeypatch, pipeline_factory):
    monkeypatch.setattr(ProjectManager, "PROJECTS_DIR", str(tmp_path / "projects"))
    monkeypatch.setattr(TaskManager, "_instance", None)
    project = ProjectManager.create_project("construction stricte")
    project.status = ProjectStatus.ONTOLOGY_GENERATED
    project.ontology = ONTOLOGY
    project.strict_ontology = True
    ProjectManager.save_project(project)
    monkeypatch.setattr(ProjectManager, "get_extracted_text", lambda project_id: "Un acteur inconnu.")
    store, writes = pipeline_factory([999])
    finished = threading.Event()
    save = ProjectManager.save_project
    def observe(project):
        save(project)
        if project.status == ProjectStatus.FAILED:
            finished.set()
    monkeypatch.setattr(ProjectManager, "save_project", observe)
    with override_graph_store(store):
        response = create_app().test_client().post("/api/graph/build", json={"project_id": project.project_id})
        assert response.status_code == 200
        assert finished.wait(3)
    reloaded = ProjectManager.get_project(project.project_id)
    assert reloaded.status == ProjectStatus.FAILED
    assert store.get_applied_ontology(reloaded.graph_id).strict is True
    assert "hors ontologie" in reloaded.error
    assert writes == []
    assert TaskManager().get_task(response.json["data"]["task_id"]).status == TaskStatus.FAILED


def test_project_without_graph_does_not_construct_store(tmp_path, monkeypatch):
    monkeypatch.setattr(ProjectManager, "PROJECTS_DIR", str(tmp_path / "projects"))
    project = ProjectManager.create_project("préférence future")
    factory = MagicMock(side_effect=AssertionError("Aucun store nécessaire"))
    monkeypatch.setattr(project_api, "get_graph_store", factory)
    response = create_app().test_client().patch(f"/api/project/{project.project_id}/ontology/policy", json={"strict_ontology": True})
    assert response.status_code == 200
    factory.assert_not_called()


def test_concurrent_requests_keep_their_ontology_snapshot(pipeline_factory):
    store, writes = pipeline_factory([999, 999])
    store.set_ontology("strict", ONTOLOGY, strict=True)
    store.set_ontology("permissive", ONTOLOGY)
    engine = store._graphiti
    from datetime import datetime, timezone
    from graphiti_core.nodes import EpisodeType
    async def write_both():
        async def write(group):
            return await engine.add_episode(
                name="concurrence", episode_body="Un acteur.", source_description="test",
                reference_time=datetime.now(timezone.utc), source=EpisodeType.text,
                group_id=group, entity_types=store._resolve_applied_ontology(group, None).entity_types,
                _mirofish_ontology_validation=store._resolve_applied_ontology(group, None),
            )
        return await asyncio.gather(write("strict"), write("permissive"), return_exceptions=True)
    results = store._run_async(write_both())
    assert isinstance(results[0], GraphValidationError)
    assert not isinstance(results[1], Exception)
    assert [n["group_id"] for n in _saved_nodes(writes)] == ["permissive"]
    assert store.get_ontology_warnings("strict") == []


@pytest.mark.parametrize("exists", [False, True])
def test_warnings_missing_graph_does_not_construct_store(tmp_path, monkeypatch, exists):
    monkeypatch.setattr(ProjectManager, "PROJECTS_DIR", str(tmp_path / "projects"))
    project_id = ProjectManager.create_project("sans graphe").project_id if exists else "missing"
    factory = MagicMock(side_effect=GraphValidationError("Configuration incomplète"))
    monkeypatch.setattr(project_api, "get_graph_store", factory)
    response = create_app().test_client().get(f"/api/project/{project_id}/ontology/warnings")
    assert response.status_code == 404
    factory.assert_not_called()


def test_zep_live_reader_discards_deleted_ontology():
    store = ZepGraphStore(client=MagicMock())
    store.set_ontology("zep", ONTOLOGY, strict=True)
    ZepGraphStore(client=MagicMock()).delete_graph("zep")
    assert store.get_applied_ontology("zep") is None


def test_zep_failed_creation_preserves_strict_ontology():
    client = MagicMock()
    store = ZepGraphStore(client=client)
    store.set_ontology("existing", ONTOLOGY, strict=True)
    client.graph.create.side_effect = RuntimeError("Création refusée")
    with pytest.raises(Exception, match="Création refusée"):
        store.create_graph("nouveau", graph_id="existing")
    reader = ZepGraphStore(client=MagicMock())
    assert reader.get_applied_ontology("existing").strict is True
    with pytest.raises(GraphValidationError):
        reader.add_episode("existing", "Un acteur.")
    reader._client.graph.add.assert_not_called()


def test_graphiti_failed_creation_preserves_strict_ontology(pipeline_factory):
    store, _ = pipeline_factory()
    store.set_ontology("existing", ONTOLOGY, strict=True)
    store._driver.health_check.side_effect = RuntimeError("Connexion indisponible")
    with pytest.raises(Exception, match="Connexion indisponible"):
        store.create_graph("nouveau", graph_id="existing")
    reader, _ = pipeline_factory()
    assert reader.get_applied_ontology("existing").strict is True
