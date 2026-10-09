import pytest
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

_backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_backend_dir))

from scripts import verifier_personas_simulation_graphiti as verifier_module


import asyncio

def test_deterministic_personas_llm_client_responses():
    client = verifier_module.DeterministicPersonasLLMClient()

    class FakeModel:
        pass

    FakeModel.__name__ = "ExtractedEntities"
    res1 = asyncio.run(client._generate_response(messages=["test"], response_model=FakeModel))
    assert "extracted_entities" in res1
    assert len(res1["extracted_entities"]) == 4

    FakeModel.__name__ = "ExtractedEdges"
    res2 = asyncio.run(client._generate_response(messages=["test"], response_model=FakeModel))
    assert "edges" in res2
    assert len(res2["edges"]) == 3

    FakeModel.__name__ = "SummarizedEntities"
    res3 = asyncio.run(client._generate_response(messages=["test"], response_model=FakeModel))
    assert "summaries" in res3


def test_verifier_personas_simulation_main_help():
    with patch.object(sys, "argv", ["verifier_personas_simulation_graphiti.py", "--help"]):
        with pytest.raises(SystemExit) as exc_info:
            verifier_module.main()
        assert exc_info.value.code == 0


def test_run_personas_simulation_validation_error_handling(monkeypatch):
    mock_store = MagicMock()
    mock_store._run_async.return_value = None
    mock_store.create_graph.side_effect = RuntimeError("Erreur simulée Neo4j")

    monkeypatch.setattr(verifier_module, "GraphitiGraphStore", lambda **kwargs: mock_store)
    monkeypatch.setattr(verifier_module, "SentenceTransformerEmbedder", lambda: MagicMock())
    monkeypatch.setattr(verifier_module, "LocalPassthroughCrossEncoder", lambda: MagicMock())

    from app.config import Config
    original_backend = Config.ZEP_BACKEND
    original_key = Config.ZEP_API_KEY

    rapport = verifier_module.run_personas_simulation_validation(use_mock_llm=True)

    assert rapport["statut"] == "ECHEC"
    assert "Erreur simulée Neo4j" in rapport["details"]["erreur"]
    assert rapport["criteres"]["C4_extraction_entites_reussie"] is False
    assert rapport["criteres"]["C4_zero_cle_zep_exigee"] is True
    assert Config.ZEP_BACKEND == original_backend
    assert Config.ZEP_API_KEY == original_key
    mock_store.close.assert_called_once()

