"""Tests unitaires du script de vérification d'ingestion réelle (Story 004-3)."""

import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import pytest

from scripts.verifier_ingestion_graphiti import (
    DeterministicIngestionLLMClient,
    main,
    run_ingestion_validation,
)


def test_deterministic_ingestion_llm_client_extracts_entities_and_edges():
    """Vérifie que le client LLM déterministe retourne les entités et relations attendues."""
    client = DeterministicIngestionLLMClient()

    # 1. ExtractedEntities
    mock_model_entities = type("ExtractedEntities", (), {})
    res_entities = asyncio.run(client._generate_response(
        messages=["Thalès Marine Nationale Alice Martin"],
        response_model=mock_model_entities,
    ))
    assert "extracted_entities" in res_entities
    assert len(res_entities["extracted_entities"]) >= 5
    names = {e["name"] for e in res_entities["extracted_entities"]}
    assert "Thalès" in names
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
    assert "SUPERVISE" in rel_types


def test_run_ingestion_validation_returns_success_with_mocked_neo4j(monkeypatch):
    """Vérifie le déroulement nominal de run_ingestion_validation avec un driver Neo4j simulé."""
    from app.utils.graph_store.graphiti_store import GraphitiGraphStore

    # Simuler le driver Neo4j et Graphiti
    mock_driver = MagicMock()
    mock_driver.build_indices_and_constraints = MagicMock(return_value=None)
    mock_driver.execute_query = MagicMock(return_value=[{"uuid": "ep-1"}])

    mock_graphiti = MagicMock()
    mock_ep = SimpleNamespace(uuid="ep-1")
    mock_res = SimpleNamespace(episode=mock_ep)
    mock_graphiti.add_episode = MagicMock(return_value=mock_res)

    # Patch GraphitiGraphStore
    original_init = GraphitiGraphStore.__init__

    def patched_init(self, *args, **kwargs):
        kwargs["driver"] = mock_driver
        kwargs["graphiti"] = mock_graphiti
        original_init(self, *args, **kwargs)

    monkeypatch.setattr(GraphitiGraphStore, "__init__", patched_init)

    # Mock get_all_nodes et get_all_edges pour satisfaire C3
    from app.utils.graph_store.base import GraphEdge, GraphNode

    mock_nodes = [
        GraphNode(uuid=f"n-{i}", name=f"Node {i}", labels=["Entity", "Org"])
        for i in range(6)
    ]
    mock_edges = [
        GraphEdge(
            uuid=f"e-{i}",
            name=f"REL_{i}",
            fact=f"Fact {i}",
            source_node_uuid="n-1",
            target_node_uuid="n-2",
        )
        for i in range(4)
    ]

    monkeypatch.setattr(GraphitiGraphStore, "get_all_nodes", lambda self, gid: list(mock_nodes))
    monkeypatch.setattr(GraphitiGraphStore, "get_all_edges", lambda self, gid, **kw: list(mock_edges))
    monkeypatch.setattr(GraphitiGraphStore, "wait_for_batch", lambda self, batch, **kw: True)
    monkeypatch.setattr(
        GraphitiGraphStore,
        "delete_graph",
        lambda self, gid: (mock_nodes.clear(), mock_edges.clear()),
    )

    rapport = run_ingestion_validation(use_mock_llm=True, keep_graph=False)

    assert rapport["statut"] == "SUCCES"
    assert rapport["criteres"]["C3_statut_tache_completed"] is True
    assert rapport["criteres"]["C3_statut_projet_graph_completed"] is True
    assert rapport["criteres"]["C3_seuil_noeuds_atteint"] is True
    assert rapport["criteres"]["C3_seuil_aretes_atteint"] is True
    assert rapport["details"]["nodes_count"] == 6
    assert rapport["details"]["edges_count"] == 4


def test_run_ingestion_validation_returns_failure_on_exception(monkeypatch):
    """Vérifie que run_ingestion_validation gère proprement une exception et renvoie un rapport d'échec."""
    from app.utils.graph_store.graphiti_store import GraphitiGraphStore

    mock_driver = MagicMock()
    mock_driver.build_indices_and_constraints = MagicMock(
        side_effect=RuntimeError("Erreur simulée de connexion Neo4j")
    )

    original_init = GraphitiGraphStore.__init__

    def patched_init(self, *args, **kwargs):
        kwargs["driver"] = mock_driver
        kwargs["graphiti"] = MagicMock()
        original_init(self, *args, **kwargs)

    monkeypatch.setattr(GraphitiGraphStore, "__init__", patched_init)

    rapport = run_ingestion_validation(use_mock_llm=True, keep_graph=False)

    assert rapport["statut"] == "ECHEC"
    assert "Erreur simulée de connexion Neo4j" in rapport["details"]["erreur"]
    assert rapport["criteres"]["C3_statut_tache_completed"] is False
    assert rapport["criteres"]["C3_seuil_noeuds_atteint"] is False


def test_main_cli_returns_zero_on_success(monkeypatch):
    """Vérifie que la fonction main CLI retourne le code de sortie 0 en cas de succès."""
    monkeypatch.setattr(
        "scripts.verifier_ingestion_graphiti.run_ingestion_validation",
        lambda **kwargs: {"statut": "SUCCES", "criteres": {}, "details": {}},
    )
    monkeypatch.setattr("sys.argv", ["verifier_ingestion_graphiti.py", "--mock-llm"])

    exit_code = main()
    assert exit_code == 0


def test_main_cli_returns_one_on_failure(monkeypatch):
    """Vérifie que la fonction main CLI retourne le code de sortie 1 en cas d'échec."""
    monkeypatch.setattr(
        "scripts.verifier_ingestion_graphiti.run_ingestion_validation",
        lambda **kwargs: {"statut": "ECHEC", "criteres": {}, "details": {"erreur": "Test failure"}},
    )
    monkeypatch.setattr("sys.argv", ["verifier_ingestion_graphiti.py", "--mock-llm"])

    exit_code = main()
    assert exit_code == 1
