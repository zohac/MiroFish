"""Tests unitaires hermétiques du script de qualification globale local-first (Story 004-5)."""

import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import pytest

from scripts.verifier_qualification_local_first import (
    DeterministicQualificationLLMClient,
    main,
    run_qualification_protocol,
)


def test_deterministic_qualification_llm_client_responses():
    """Vérifie que le client LLM déterministe retourne les entités, relations et résumés attendus."""
    client = DeterministicQualificationLLMClient()

    # 1. ExtractedEntities
    mock_model_entities = type("ExtractedEntities", (), {})
    res_entities = asyncio.run(client._generate_response(
        messages=["Thalès Marine Nationale Alice Martin"],
        response_model=mock_model_entities,
    ))
    assert "extracted_entities" in res_entities
    assert len(res_entities["extracted_entities"]) >= 5
    names = {e["name"] for e in res_entities["extracted_entities"]}
    assert "Thalès Défense" in names
    assert "Alice Martin" in names

    # 2. ExtractedEdges
    mock_model_edges = type("ExtractedEdges", (), {})
    res_edges = asyncio.run(client._generate_response(
        messages=["Fourniture de matériel radar"],
        response_model=mock_model_edges,
    ))
    assert "edges" in res_edges
    assert len(res_edges["edges"]) >= 3
    rel_types = {e["relation_type"] for e in res_edges["edges"]}
    assert "FOURNIT_EQUIPEMENT" in rel_types
    assert "DIRIGE_PROJET" in rel_types

    # 3. SummarizedEntities
    mock_model_summaries = type("SummarizedEntities", (), {})
    res_summaries = asyncio.run(client._generate_response(
        messages=["Résumés des entités"],
        response_model=mock_model_summaries,
    ))
    assert "summaries" in res_summaries
    assert len(res_summaries["summaries"]) >= 4

    # 4. Déduplication
    mock_model_dedup = type("EdgeDuplicate", (), {})
    res_dedup = asyncio.run(client._generate_response(
        messages=["Déduplication"],
        response_model=mock_model_dedup,
    ))
    assert res_dedup == {"duplicate_facts": [], "contradicted_facts": []}


def test_verifier_qualification_main_help():
    """Vérifie que l'option --help s'exécute proprement."""
    with patch("sys.argv", ["verifier_qualification_local_first.py", "--help"]):
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 0


def test_run_qualification_protocol_success_with_mocked_neo4j(monkeypatch):
    """Vérifie le déroulement nominal du protocole complet avec GraphStore simulé."""
    from app.utils.graph_store.base import BatchSubmissionRecord, GraphEdge, GraphInfo, GraphNode, GraphStore

    class MockQualificationStore(GraphStore):
        def __init__(self, **kwargs):
            self._nodes = [
                GraphNode(
                    uuid=f"n-{i}",
                    name=f"Entite-{i}",
                    labels=["Entity", "Organization" if i % 2 == 0 else "Person"],
                    attributes={"summary": f"Résumé de l'entité {i}", "role": "Expert"},
                )
                for i in range(6)
            ]
            self._edges = [
                GraphEdge(
                    uuid=f"e-{i}",
                    name=f"REL_{i}",
                    fact=f"Fact {i}",
                    source_node_uuid="n-0",
                    target_node_uuid=f"n-{i + 1}",
                )
                for i in range(4)
            ]

        def create_graph(self, name: str, graph_id: str | None = None) -> str:
            return graph_id or "graph-test"

        def delete_graph(self, graph_id: str) -> None:
            self._nodes.clear()
            self._edges.clear()

        def get_graph_info(self, graph_id: str) -> GraphInfo:
            return GraphInfo(
                graph_id=graph_id,
                name="Mock Graph",
                node_count=len(self._nodes),
                edge_count=len(self._edges),
                entity_types=["Person", "Organization"],
            )

        def get_all_nodes(self, graph_id: str) -> list[GraphNode]:
            return list(self._nodes)

        def get_all_edges(self, graph_id: str, include_temporal: bool = True) -> list[GraphEdge]:
            return list(self._edges)

        def get_node(self, graph_id: str, node_uuid: str) -> GraphNode | None:
            for n in self._nodes:
                if n.uuid == node_uuid:
                    return n
            return None

        def get_node_edges(self, graph_id: str, node_uuid: str) -> list[GraphEdge]:
            return [
                e for e in self._edges
                if e.source_node_uuid == node_uuid or e.target_node_uuid == node_uuid
            ]

        def set_ontology(self, graph_id: str, ontology: dict) -> None:
            pass

        def get_graph_data(self, graph_id: str) -> dict:
            return {
                "nodes": [n.to_dict() if hasattr(n, "to_dict") else n for n in self._nodes],
                "edges": [e.to_dict() if hasattr(e, "to_dict") else e for e in self._edges],
                "statistics": {"node_count": len(self._nodes), "edge_count": len(self._edges)},
            }

        def add_episode(self, graph_id: str, text: str, source_description: str = "", metadata=None, created_at=None):
            return SimpleNamespace(uuid="ep-1", graph_id=graph_id, processed=True)

        def add_text_batch(self, graph_id: str, chunks: list[str], batch_size: int = 350, progress_callback=None):
            return BatchSubmissionRecord(
                batch_id="batch-1",
                operation_id="op-1",
                episode_uuids=["ep-1"],
                item_count=len(chunks),
            )

        def wait_for_batch(self, batch, progress_callback=None, timeout=600.0):
            return True

        def wait_for_episodes(self, episode_uuids: list[str], timeout: float = 600.0) -> bool:
            return True

        def search(self, graph_id: str, query: str, limit: int = 10, **kwargs):
            return []

        def close(self):
            pass

    monkeypatch.setattr("scripts.verifier_qualification_local_first.GraphitiGraphStore", MockQualificationStore)
    monkeypatch.setattr("scripts.verifier_qualification_local_first.SentenceTransformerEmbedder", lambda: MagicMock())
    monkeypatch.setattr("scripts.verifier_qualification_local_first.LocalPassthroughCrossEncoder", lambda: MagicMock())

    rapport = run_qualification_protocol(
        use_mock_llm=True,
        keep_graph=False,
        keep_artifacts=False,
    )

    assert rapport["statut"] == "SUCCES"
    assert rapport["criteres"]["C1_zero_blocage_api_sans_zep"] is True
    assert rapport["criteres"]["C2_parametrage_llm_universel"] is True
    assert rapport["criteres"]["C3_graphe_neo4j_construit"] is True
    assert rapport["criteres"]["C4_personas_simulation_validees"] is True
    assert rapport["criteres"]["C5_filet_tests_vert"] is True
    assert rapport["details"]["nodes_count"] == 6
    assert rapport["details"]["edges_count"] == 4
    assert rapport["details"]["personas_count"] >= 3


def test_run_qualification_protocol_error_handling(monkeypatch):
    """Vérifie la gestion d'erreur lors d'une défaillance dans le protocole."""
    from app.utils.graph_store.graphiti_store import GraphitiGraphStore

    mock_store = MagicMock(spec=GraphitiGraphStore)
    mock_store._run_async.return_value = None
    mock_store.get_graph_data.return_value = {
        "nodes": [], "edges": [], "statistics": {"node_count": 0, "edge_count": 0}
    }
    mock_store.create_graph.side_effect = RuntimeError("Erreur simulée de connexion Neo4j")

    monkeypatch.setattr("scripts.verifier_qualification_local_first.GraphitiGraphStore", lambda **kwargs: mock_store)
    monkeypatch.setattr("scripts.verifier_qualification_local_first.SentenceTransformerEmbedder", lambda: MagicMock())
    monkeypatch.setattr("scripts.verifier_qualification_local_first.LocalPassthroughCrossEncoder", lambda: MagicMock())

    from app.config import Config
    orig_backend = Config.ZEP_BACKEND
    orig_key = Config.ZEP_API_KEY

    rapport = run_qualification_protocol(
        use_mock_llm=True,
        keep_graph=False,
        keep_artifacts=False,
    )

    assert rapport["statut"] == "ECHEC"
    assert "Erreur simulée de connexion Neo4j" in rapport["details"]["erreur"]
    assert rapport["criteres"]["C3_graphe_neo4j_construit"] is False
    assert Config.ZEP_BACKEND == orig_backend
    assert Config.ZEP_API_KEY == orig_key
    mock_store.close.assert_called_once()


def test_main_cli_exit_codes(monkeypatch):
    """Vérifie les codes de retour de la fonction main CLI."""
    monkeypatch.setattr(
        "scripts.verifier_qualification_local_first.run_qualification_protocol",
        lambda **kwargs: {"statut": "SUCCES", "criteres": {}, "details": {}},
    )
    monkeypatch.setattr("sys.argv", ["verifier_qualification_local_first.py", "--mock-llm"])
    assert main() == 0

    monkeypatch.setattr(
        "scripts.verifier_qualification_local_first.run_qualification_protocol",
        lambda **kwargs: {"statut": "ECHEC", "criteres": {}, "details": {"erreur": "Échec simulé"}},
    )
    monkeypatch.setattr("sys.argv", ["verifier_qualification_local_first.py", "--mock-llm"])
    assert main() == 1


def test_main_cli_json_output(monkeypatch, capsys):
    """Vérifie que l'option --json produit un document JSON valide sur stdout."""
    monkeypatch.setattr(
        "scripts.verifier_qualification_local_first.run_qualification_protocol",
        lambda **kwargs: {"statut": "SUCCES", "criteres": {"C1": True}, "details": {}},
    )
    monkeypatch.setattr("sys.argv", ["verifier_qualification_local_first.py", "--mock-llm", "--json"])
    assert main() == 0
    captured = capsys.readouterr()
    assert '"statut": "SUCCES"' in captured.out


def test_run_qualification_protocol_insufficient_nodes_fails(monkeypatch):
    """Vérifie que le protocole échoue si le graphe Neo4j ne contient pas le nombre minimal de nœuds (Critère C3)."""
    from app.utils.graph_store.base import BatchSubmissionRecord, GraphInfo, GraphNode, GraphStore

    class MockSmallGraphStore(GraphStore):
        def __init__(self, **kwargs):
            self._nodes = [
                GraphNode(uuid="n-1", name="Entite-1", labels=["Entity"], attributes={})
            ]
            self._edges = []

        def create_graph(self, name: str, graph_id: str | None = None) -> str:
            return graph_id or "graph-test"

        def delete_graph(self, graph_id: str) -> None:
            self._nodes.clear()

        def get_graph_info(self, graph_id: str) -> GraphInfo:
            return GraphInfo(graph_id=graph_id, name="Small", node_count=len(self._nodes), edge_count=0)

        def get_all_nodes(self, graph_id: str) -> list[GraphNode]:
            return list(self._nodes)

        def get_all_edges(self, graph_id: str, include_temporal: bool = True):
            return []

        def get_node(self, graph_id: str, node_uuid: str) -> GraphNode | None:
            return self._nodes[0] if self._nodes and self._nodes[0].uuid == node_uuid else None

        def get_node_edges(self, graph_id: str, node_uuid: str):
            return []

        def set_ontology(self, graph_id: str, ontology: dict) -> None:
            pass

        def get_graph_data(self, graph_id: str) -> dict:
            return {
                "nodes": [n.to_dict() if hasattr(n, "to_dict") else n for n in self._nodes],
                "edges": [],
                "statistics": {"node_count": len(self._nodes), "edge_count": 0},
            }

        def add_episode(self, graph_id: str, text: str, source_description: str = "", metadata=None, created_at=None):
            return SimpleNamespace(uuid="ep-1", graph_id=graph_id, processed=True)

        def add_text_batch(self, graph_id: str, chunks: list[str], batch_size: int = 350, progress_callback=None):
            return BatchSubmissionRecord(batch_id="batch-1", operation_id="op-1", episode_uuids=["ep-1"], item_count=len(chunks))

        def wait_for_batch(self, batch, progress_callback=None, timeout=600.0):
            return True

        def wait_for_episodes(self, episode_uuids: list[str], timeout: float = 600.0) -> bool:
            return True

        def search(self, graph_id: str, query: str, limit: int = 10, **kwargs):
            return []

        def close(self):
            pass

    monkeypatch.setattr("scripts.verifier_qualification_local_first.GraphitiGraphStore", MockSmallGraphStore)
    monkeypatch.setattr("scripts.verifier_qualification_local_first.SentenceTransformerEmbedder", lambda: MagicMock())
    monkeypatch.setattr("scripts.verifier_qualification_local_first.LocalPassthroughCrossEncoder", lambda: MagicMock())

    rapport = run_qualification_protocol(use_mock_llm=True, keep_graph=False, keep_artifacts=False)
    assert rapport["statut"] == "ECHEC"
    assert rapport["criteres"]["C3_graphe_neo4j_construit"] is False
    assert "Seuil de nœuds non atteint" in rapport["details"]["erreur"]

