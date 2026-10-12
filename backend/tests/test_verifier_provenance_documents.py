"""Protocole de la sonde réelle de provenance (story 009-2, AC10).

Ces tests vérifient la sonde elle-même : seuils, modes, gestion d'erreur et
absence de secret dans la sortie. Ils ne remplacent pas l'exécution réelle
contre Neo4j, qui est consignée séparément dans `mesure-009-2.md`.
"""

import asyncio
import sys
from pathlib import Path
from typing import Any, List, Tuple
from unittest.mock import MagicMock

import pytest

_backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_backend_dir))

from scripts import verifier_provenance_documents as sonde  # noqa: E402


class TestDeterministicClient:
    def test_reponses_deterministes(self):
        client = sonde.DeterministicProvenanceLLMClient()

        class FakeModel:
            pass

        FakeModel.__name__ = "ExtractedEntities"
        res1 = asyncio.run(client._generate_response(messages=["x"], response_model=FakeModel))
        assert len(res1["extracted_entities"]) == 3

        FakeModel.__name__ = "ExtractedEdges"
        res2 = asyncio.run(client._generate_response(messages=["x"], response_model=FakeModel))
        assert len(res2["edges"]) == 2

        FakeModel.__name__ = "SummarizedEntities"
        res3 = asyncio.run(client._generate_response(messages=["x"], response_model=FakeModel))
        assert "summaries" in res3


class TestCli:
    def test_help_sort_sans_erreur(self):
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(sys, "argv", ["verifier_provenance_documents.py", "--help"])
            with pytest.raises(SystemExit) as exc:
                sonde.main()
            assert exc.value.code == 0

    def test_les_deux_documents_de_la_sonde_sont_distincts(self):
        assert len(sonde.DOCUMENTS) >= 2
        assert len({doc.document_id for doc in sonde.DOCUMENTS}) == len(sonde.DOCUMENTS)


class FakeProvenanceStore:
    """Store double qui produit deux documents, deux fragments chacun."""

    def __init__(self, documents, document_texts, **_kwargs):
        self._documents = documents
        self._texts = document_texts
        self._edges = []
        self.set_ontology_calls: List[Tuple[str, Any]] = []

    def _run_async(self, coro):
        return None

    class _Driver:
        def build_indices_and_constraints(self):
            return None

    _driver = _Driver()

    def create_graph(self, name, graph_id=None):
        return graph_id

    def set_ontology(self, graph_id, ontology, **kwargs):
        self.set_ontology_calls.append((graph_id, ontology))
        return None

    def add_text_batch(self, graph_id, chunks, batch_size=350, progress_callback=None, chunk_metadata=None):
        from app.utils.graph_store import BatchSubmissionRecord
        from app.utils.graph_store.base import validate_chunk_metadata

        validated = validate_chunk_metadata(chunks, chunk_metadata)
        episodes = []
        for index, (chunk, entry) in enumerate(zip(chunks, validated)):
            episodes.append((f"ep-{index}", entry, chunk))
        self._episodes = episodes
        return BatchSubmissionRecord(
            batch_id="b1", operation_id="op1",
            episode_uuids=[e[0] for e in episodes], item_count=len(chunks),
        )

    def wait_for_batch(self, batch, progress_callback=None, timeout=600.0):
        return True

    def get_all_edges(self, graph_id, include_temporal=True):
        from app.utils.graph_store import GraphEdge

        return [
            GraphEdge(
                uuid="edge-1", name="RELATES_TO", fact="un fait",
                source_node_uuid="n1", target_node_uuid="n2",
                episodes=[self._episodes[0][0], self._episodes[1][0]],
            )
        ]

    def get_edge_provenance(self, graph_id, edge_uuid):
        from app.utils.graph_store import ProvenanceOrigin, ProvenanceRecord

        if graph_id != self._graph_id:
            return []
        records = []
        for episode_uuid, entry, chunk in self._episodes:
            records.append(
                ProvenanceRecord(
                    episode_uuid=episode_uuid,
                    resolved=True,
                    origin=ProvenanceOrigin.DOCUMENT,
                    source_document_id=entry["source_document_id"],
                    source_filename=entry["source_filename"],
                    source_role=entry["source_role"],
                    chunk_index=entry["chunk_index"],
                    char_start=entry["char_start"],
                    char_end=entry["char_end"],
                    content=chunk,
                )
            )
        return records

    _graph_id = None

    def delete_graph(self, graph_id):
        return None

    def close(self):
        return None


def test_sonde_reussit_avec_un_store_double(monkeypatch, tmp_path):
    """Avec deux documents de deux fragments et des positions exactes, C3 passe."""
    import app.models.project as project_module

    monkeypatch.setattr(project_module.ProjectManager, "PROJECTS_DIR", str(tmp_path / "projects"))

    created: dict = {}

    def fake_store_factory(**kwargs):
        # Les textes sont persistés par le vrai ProjectManager ; on les relit.
        store = FakeProvenanceStore(sonde.DOCUMENTS, {}, **kwargs)
        created["store"] = store
        return store

    monkeypatch.setattr(sonde, "GraphitiGraphStore", fake_store_factory)
    monkeypatch.setattr(sonde, "SentenceTransformerEmbedder", lambda: MagicMock())
    monkeypatch.setattr(sonde, "LocalPassthroughCrossEncoder", lambda: MagicMock())

    # Le store double doit connaître le graph_id qu'on lui demandera de vérifier.
    original_create = FakeProvenanceStore.create_graph

    def create_and_remember(self, name, graph_id=None):
        FakeProvenanceStore._graph_id = graph_id
        return original_create(self, name, graph_id=graph_id)

    monkeypatch.setattr(FakeProvenanceStore, "create_graph", create_and_remember)

    rapport = sonde.run_provenance_validation(use_mock_llm=True)
    assert rapport["statut"] == "SUCCES"
    assert all(rapport["criteres"].values())
    assert rapport["details"]["positions_exactes"] == rapport["details"]["resolved_documentary"]

    # AC5 symétrie relecture BMAD groupe C : la sonde passe un payload non-vide
    # à `set_ontology` (ADR 0014 refuse l'ontologie vide). Une régression qui
    # reviendrait au payload `{"entity_types": [], "edge_types": []}` lèverait
    # `OntologyValidationError` en vrai sur Neo4j ; on l'attrape ici.
    assert created["store"].set_ontology_calls, "set_ontology jamais appelé"
    payload = created["store"].set_ontology_calls[0][1]
    assert payload["entity_types"], (
        f"L'ontologie passée à set_ontology doit comporter au moins un type "
        f"d'entité (ADR 0014 refuse les ontologies vides), reçu : {payload}"
    )


def test_sonde_gere_une_erreur_et_restaure_la_config(monkeypatch):
    mock_store = MagicMock()
    mock_store._run_async.return_value = None
    mock_store._driver = MagicMock()
    mock_store.create_graph.side_effect = RuntimeError("Erreur simulée Neo4j")

    monkeypatch.setattr(sonde, "GraphitiGraphStore", lambda **kwargs: mock_store)
    monkeypatch.setattr(sonde, "SentenceTransformerEmbedder", lambda: MagicMock())
    monkeypatch.setattr(sonde, "LocalPassthroughCrossEncoder", lambda: MagicMock())

    from app.config import Config

    original_backend, original_key = Config.ZEP_BACKEND, Config.ZEP_API_KEY

    rapport = sonde.run_provenance_validation(use_mock_llm=True)
    assert rapport["statut"] == "ECHEC"
    assert "Erreur simulée Neo4j" in rapport["details"]["erreur"]
    assert Config.ZEP_BACKEND == original_backend
    assert Config.ZEP_API_KEY == original_key
    mock_store.close.assert_called_once()


class TestReportRendering:
    def test_le_rapport_ne_contient_aucun_secret(self):
        rapport = {
            "timestamp": "2026-10-11T00:00:00Z",
            "statut": "SUCCES",
            "criteres": {"C3_positions_exactes": True},
            "details": {
                "documents": [
                    {"filename": "a.txt", "role": "facts", "priority": 1,
                     "validation_status": "unvalidated"}
                ],
                "chunks_per_document": {"doc_1": 2},
                "total_references": 2,
                "resolved_documentary": 2,
                "positions_exactes": 2,
                "origins": {"document": 2},
                "unresolved": [],
                "document_sha256": {"alpha": "abc"},
                # Une valeur sensible qui ne doit jamais être rendue : le
                # rapport ne construit ses lignes que depuis des clés connues.
                "neo4j_password": "MOT_DE_PASSE_A_NE_JAMAIS_RENDRE",
                "api_key": "CLE_A_NE_JAMAIS_RENDRE",
            },
        }
        markdown = sonde.render_markdown_report(rapport)
        assert "MOT_DE_PASSE_A_NE_JAMAIS_RENDRE" not in markdown
        assert "CLE_A_NE_JAMAIS_RENDRE" not in markdown
        assert "C3_positions_exactes" in markdown
        assert "unvalidated" in markdown

    def test_le_rapport_nomme_les_criteres_et_le_statut(self):
        markdown = sonde.render_markdown_report(
            {"timestamp": "t", "statut": "ECHEC", "criteres": {"x": False}, "details": {}}
        )
        assert "ECHEC" in markdown
        assert "| `x` | ❌ ÉCHEC |" in markdown