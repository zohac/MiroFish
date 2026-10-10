"""Tests unitaires hermétiques pour le script de vérification d'intégration Graphiti (Story 003-5).

Ces tests vérifient le fonctionnement autonome de `verifier_integration_graphiti.py`,
le comportement du client LLM déterministe, la gestion des erreurs de connexion,
le respect des signatures et la robustesse du protocole sans dépendance externe obligatoire.
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from scripts.verifier_integration_graphiti import (
    DeterministicMockLLMClient,
    main,
    run_integration_validation,
)


@pytest.mark.asyncio
async def test_deterministic_mock_llm_client_extracted_entities():
    """Vérifie que le client LLM mocké extrait les entités attendues selon le domaine."""
    client = DeterministicMockLLMClient()

    class ExtractedEntities:
        pass

    # Domaine Défense (Thalès)
    msg_thales = MagicMock(content="L'entreprise Thalès conçoit des radars côtiers.")
    res_thales = await client._generate_response([msg_thales], response_model=ExtractedEntities)
    assert "extracted_entities" in res_thales
    entities_thales = [e["name"] for e in res_thales["extracted_entities"]]
    assert "Thalès" in entities_thales
    assert "Marine Nationale" in entities_thales

    # Domaine Santé (BioMed)
    msg_biomed = MagicMock(content="BioMed produit un vaccin innovant contre la grippe aviaire.")
    res_biomed = await client._generate_response([msg_biomed], response_model=ExtractedEntities)
    assert "extracted_entities" in res_biomed
    entities_biomed = [e["name"] for e in res_biomed["extracted_entities"]]
    assert "BioMed" in entities_biomed
    assert "Grippe Aviaire" in entities_biomed

    # Domaine Inconnu
    msg_inconnu = MagicMock(content="Texte sans entité connue.")
    res_inconnu = await client._generate_response([msg_inconnu], response_model=ExtractedEntities)
    assert res_inconnu == {"extracted_entities": []}


@pytest.mark.asyncio
async def test_deterministic_mock_llm_client_summaries_and_edges():
    """Vérifie que les résumés, arêtes et résolutions sont correctement simulés."""
    client = DeterministicMockLLMClient()

    class SummarizedEntities:
        pass

    class ExtractedEdges:
        pass

    class EdgeDuplicate:
        pass

    class NodeResolutions:
        pass

    msg_thales = MagicMock(content="Thalès radar Marine Nationale.")
    res_sum = await client._generate_response([msg_thales], response_model=SummarizedEntities)
    assert "summaries" in res_sum
    assert len(res_sum["summaries"]) > 0

    res_edges = await client._generate_response([msg_thales], response_model=ExtractedEdges)
    assert "edges" in res_edges
    assert len(res_edges["edges"]) > 0
    assert res_edges["edges"][0]["source_entity_name"] == "Thalès"

    res_dup = await client._generate_response([msg_thales], response_model=EdgeDuplicate)
    assert res_dup == {"duplicate_facts": [], "contradicted_facts": []}

    res_resol = await client._generate_response([msg_thales], response_model=NodeResolutions)
    assert res_resol == {"resolutions": []}


def test_run_integration_validation_handles_connection_failure(monkeypatch):
    """Vérifie que le script retourne un rapport d'échec propre si Neo4j est inaccessible."""
    monkeypatch.setenv("NEO4J_URI", "bolt://invalid-host-unreachable:9999")
    monkeypatch.setenv("NEO4J_PASSWORD", "test-pass")
    monkeypatch.setenv("LLM_API_KEY", "test-pass-llm")

    def _mock_fail(coro):
        if hasattr(coro, "close"):
            coro.close()
        raise ConnectionError("Échec de connexion réseau")

    with patch("scripts.verifier_integration_graphiti.GraphitiGraphStore._run_async", side_effect=_mock_fail):
        rapport = run_integration_validation(use_mock_llm=True, keep_graph=False)

        assert rapport["statut"] == "ECHEC"
        assert "erreur_connexion" in rapport["details"]
        assert rapport["criteres"]["C1_14_methodes_implementees"] is False


def test_main_cli_dispatch(monkeypatch):
    """Vérifie le code de retour de main() selon le succès ou l'échec du rapport."""
    with patch("scripts.verifier_integration_graphiti.run_integration_validation") as mock_run:
        mock_run.return_value = {"statut": "SUCCES", "criteres": {}}
        monkeypatch.setattr("sys.argv", ["verifier_integration_graphiti.py", "--mock-llm"])
        assert main() == 0

        mock_run.return_value = {"statut": "ECHEC", "details": {"erreur": "test"}}
        assert main() == 1
