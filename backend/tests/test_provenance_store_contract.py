"""Contrat de provenance `GraphStore` dans les deux implémentations (AC3, AC4, AC5).

Ces tests sont hermétiques : doubles en mémoire, aucun réseau, aucun Neo4j. La
preuve contre un vrai Neo4j est portée par la sonde `verifier_provenance_documents.py`,
hors pytest.
"""

from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock

import pytest

from app.utils.graph_store import (
    BatchSubmissionRecord,
    EpisodeRecord,
    GraphEdge,
    GraphInfo,
    GraphNode,
    GraphNotFoundError,
    GraphSearchResult,
    GraphStore,
    GraphStoreError,
    ProvenanceOrigin,
    ProvenanceRecord,
    ZepGraphStore,
    GraphitiGraphStore,
    validate_chunk_metadata,
)
from app.utils.graph_store.errors import GraphValidationError


def make_metadata(**overrides) -> Dict[str, Any]:
    entry = {
        "source_document_id": "doc_1",
        "source_filename": "alpha.txt",
        "chunk_index": 0,
        "char_start": 0,
        "char_end": 12,
        "source_role": "facts",
    }
    entry.update(overrides)
    return entry


class RecordingStore(GraphStore):
    """Store en mémoire qui enregistre ce qu'il reçoit, pour éprouver le contrat sans I/O."""

    def __init__(self) -> None:
        self.batches: List[Dict[str, Any]] = []
        self.episodes: List[Dict[str, Any]] = []
        self.provenance_by_edge: Dict[str, List[ProvenanceRecord]] = {}

    # --- contrat minimal ---
    def create_graph(self, name, graph_id=None): return graph_id or "g1"
    def delete_graph(self, graph_id): return None
    def get_graph_data(self, graph_id): return {"nodes": [], "edges": []}
    def get_graph_info(self, graph_id): return GraphInfo(graph_id=graph_id, node_count=0, edge_count=0)
    def set_ontology(self, graph_id, ontology): return None
    def add_episode(self, graph_id, text, source_description="", metadata=None, created_at=None):
        self.episodes.append(
            {"graph_id": graph_id, "text": text, "metadata": metadata, "source_description": source_description}
        )
        return EpisodeRecord(uuid=f"ep-{len(self.episodes)}", graph_id=graph_id, processed=True)

    def add_text_batch(self, graph_id, chunks, batch_size=350, progress_callback=None, chunk_metadata=None):
        validated = validate_chunk_metadata(chunks, chunk_metadata)
        self.batches.append(
            {"graph_id": graph_id, "chunks": list(chunks), "chunk_metadata": validated}
        )
        for chunk, entry in zip(chunks, validated) if validated else [(c, None) for c in chunks]:
            self.add_episode(
                graph_id, chunk, metadata=entry,
                source_description=(f"{entry['source_filename']}#{entry['chunk_index']}" if entry else f"chunk_1"),
            )
        return BatchSubmissionRecord(
            batch_id="b1", operation_id="op1",
            episode_uuids=[e["text"] for e in []], item_count=len(chunks),
        )

    def wait_for_batch(self, batch, progress_callback=None, timeout=600.0): return True
    def wait_for_episodes(self, graph_id, episode_uuids, timeout=600.0): return True
    def get_all_nodes(self, graph_id): return []
    def get_all_edges(self, graph_id, include_temporal=True): return []
    def get_node(self, graph_id, node_uuid): return None
    def get_node_edges(self, graph_id, node_uuid): return []
    def search(self, graph_id, query, limit=10, scope="edges", reranker=None):
        return GraphSearchResult(facts=[], nodes=[], edges=[], query=query, total_count=0)

    def get_edge_provenance(self, graph_id: str, edge_uuid: str):
        return list(self.provenance_by_edge.get(edge_uuid, []))


# --- AC3 : extension rétrocompatible du contrat d'écriture ---


class TestBackwardCompatibility:
    def test_un_appel_sans_metadonnees_reste_valide(self):
        store = RecordingStore()
        store.add_text_batch("g1", ["un", "deux"])
        assert store.batches[0]["chunk_metadata"] == []

    def test_la_position_du_parametre_optionnel_est_apres_progress_callback(self):
        import inspect

        params = list(inspect.signature(GraphStore.add_text_batch).parameters)
        assert params == [
            "self", "graph_id", "chunks", "batch_size", "progress_callback", "chunk_metadata",
        ]

    @pytest.mark.parametrize("store_class", [GraphitiGraphStore, ZepGraphStore])
    def test_les_deux_stores_exposent_la_meme_signature(self, store_class):
        import inspect

        base = list(inspect.signature(GraphStore.add_text_batch).parameters)
        for name in base:
            assert name in inspect.signature(store_class.add_text_batch).parameters

    def test_le_demarrage_avec_cinq_arguments_positionnels_reste_valide(self):
        store = RecordingStore()
        store.add_text_batch("g1", ["un"], 350, None)
        assert store.batches[0]["chunk_metadata"] == []


class TestMetadataValidation:
    def test_metadonnees_alignees_acceptees(self):
        entries = [make_metadata(chunk_index=0), make_metadata(chunk_index=1)]
        validated = validate_chunk_metadata(["aaa", "bbb"], entries)
        assert len(validated) == 2

    def test_desalignement_refuse(self):
        with pytest.raises(GraphValidationError):
            validate_chunk_metadata(["a", "b"], [make_metadata()])

    @pytest.mark.parametrize("champ", [
        "source_document_id", "source_filename", "chunk_index", "char_start", "char_end", "source_role",
    ])
    def test_champ_requis_manquant_refuse(self, champ):
        entry = make_metadata()
        del entry[champ]
        with pytest.raises(GraphValidationError):
            validate_chunk_metadata(["a"], [entry])

    def test_entree_non_dictionnaire_refusee(self):
        with pytest.raises(GraphValidationError):
            validate_chunk_metadata(["a"], ["pas un dict"])

    def test_type_invalide_refuse(self):
        with pytest.raises(GraphValidationError):
            validate_chunk_metadata(["a"], [make_metadata(chunk_index="0")])

    def test_positions_incoherentes_refusees(self):
        with pytest.raises(GraphValidationError):
            validate_chunk_metadata(["a"], [make_metadata(char_start=10, char_end=10)])

    def test_role_inconnu_refuse(self):
        with pytest.raises(GraphValidationError):
            validate_chunk_metadata(["a"], [make_metadata(source_role="officiel")])

    def test_une_cle_inconnue_est_refusee(self):
        """Une clé libre deviendrait un nom de propriété Cypher non maîtrisé."""
        with pytest.raises(GraphValidationError):
            validate_chunk_metadata(["a"], [{**make_metadata(), "saved_filename": "x"}])

    def test_une_cle_group_id_est_refusee(self):
        with pytest.raises(GraphValidationError):
            validate_chunk_metadata(["a"], [{**make_metadata(), "group_id": "ailleurs"}])

    def test_un_desalignement_ne_declenche_aucune_ecriture(self):
        store = RecordingStore()
        with pytest.raises(GraphValidationError):
            store.add_text_batch("g1", ["a", "b"], chunk_metadata=[make_metadata()])
        assert store.episodes == []

    def test_page_fournie_acceptee_et_page_absente_acceptee(self):
        assert validate_chunk_metadata(["a"], [make_metadata(page=3)])[0]["page"] == 3
        assert "page" not in validate_chunk_metadata(["a"], [make_metadata()])[0] or \
               validate_chunk_metadata(["a"], [make_metadata()])[0].get("page") is None


class TestOperationIdentity:
    def test_sans_metadonnees_le_hachage_reste_celui_d_avant(self):
        from app.services.graph_builder import GraphBuilderService

        # Digest figé : l'ADR 0012 promet la réconciliation d'un lot Zep déjà
        # persisté. Si l'algorithme sans provenance changeait, ce test échouerait.
        attendu = "668c25273a97a925807eeff414799bc0c607888f8664b7a1808244fcab1bfd8c"
        assert GraphBuilderService.build_operation_id("g1", ["a", "b"]) == attendu
        assert GraphBuilderService.build_operation_id("g1", ["a", "b"], None) == attendu

    def test_avec_metadonnees_deux_documents_differents_donnent_deux_operations(self):
        from app.services.graph_builder import GraphBuilderService

        un = GraphBuilderService.build_operation_id("g1", ["meme"], [make_metadata(source_document_id="doc_1")])
        deux = GraphBuilderService.build_operation_id("g1", ["meme"], [make_metadata(source_document_id="doc_2")])
        assert un != deux


# --- AC4 : persistance réelle et UUID réellement persisté ---


class TestGraphitiAnnotation:
    def _store(self):
        driver, llm, embedder, cross, graphiti = (MagicMock() for _ in range(5))
        return GraphitiGraphStore(
            driver=driver, llm_client=llm, embedder=embedder,
            cross_encoder=cross, graphiti=graphiti,
        ), graphiti

    def test_un_uuid_fabrique_sur_place_est_refuse(self):
        store, graphiti = self._store()
        graphiti.add_episode = MagicMock(return_value=MagicMock(episode=None, uuid=None))
        with pytest.raises(GraphStoreError):
            store.add_episode("g1", "texte")

    def test_l_uuid_reellement_persisté_est_retourné(self):
        store, graphiti = self._store()
        graphiti.add_episode = MagicMock(return_value=MagicMock(episode=MagicMock(uuid="ep-vrai")))
        record = store.add_episode("g1", "texte")
        assert record.uuid == "ep-vrai"

    def test_annotation_refusee_si_aucune_ligne_touchee(self):
        """Une annotation qui ne trouve rien ne doit pas devenir un succès."""
        store, graphiti = self._store()
        graphiti.add_episode = MagicMock(return_value=MagicMock(episode=MagicMock(uuid="ep-1")))
        store._execute_cypher = MagicMock(return_value=[])
        with pytest.raises(GraphStoreError):
            store.add_episode("g1", "texte", metadata={"source_document_id": "doc_1"})

    def test_annotation_appliquee_et_verifiee(self):
        store, graphiti = self._store()
        graphiti.add_episode = MagicMock(return_value=MagicMock(episode=MagicMock(uuid="ep-1")))
        captured = {}

        def fake_cypher(query, params=None):
            captured["query"] = query
            captured["params"] = params
            return [{"uuid": "ep-1"}]

        store._execute_cypher = fake_cypher
        record = store.add_episode(
            "mon_graphe", "texte",
            metadata={"source_document_id": "doc_1", "chunk_index": 2},
        )
        assert record.uuid == "ep-1"
        # La requête doit cibler le bon label, borner par graphe et poser les
        # champs réellement demandés (AC4).
        assert ":Episodic" in captured["query"]
        assert "group_id" in captured["query"]
        assert "e.source_document_id" in captured["query"]
        assert "e.chunk_index" in captured["query"]
        assert captured["params"]["group_id"] == "mon_graphe"
        assert captured["params"]["episode_uuid"] == "ep-1"
        assert captured["params"]["source_document_id"] == "doc_1"

    def test_metadata_reserve_refuse(self):
        store, graphiti = self._store()
        graphiti.add_episode = MagicMock(return_value=MagicMock(episode=MagicMock(uuid="ep-1")))
        with pytest.raises(GraphValidationError):
            store.add_episode("g1", "texte", metadata={"group_id": "ailleurs"})

    def test_la_cle_source_est_refusee(self):
        """`source` est un EpisodeType Graphiti : l'annoter corromprait l'épisode."""
        store, graphiti = self._store()
        graphiti.add_episode = MagicMock(return_value=MagicMock(episode=MagicMock(uuid="ep-1")))
        with pytest.raises(GraphValidationError):
            store.add_episode("g1", "texte", metadata={"source": "mirofish_simulation"})


# --- AC5 : lecture neutre et origines distinctes ---


class TestProvenanceClassification:
    def test_origine_documentaire(self):
        record = GraphitiGraphStore._to_provenance_record(
            "ep-1",
            {"source_document_id": "doc_1", "source_filename": "a.txt",
             "source_role": "facts", "chunk_index": 0,
             "char_start": 0, "char_end": 5, "content": "abcde"},
        )
        assert record.resolved
        assert record.origin == ProvenanceOrigin.DOCUMENT
        assert record.is_documentary
        assert record.missing_reason is None

    def test_origine_simulee_n_est_pas_un_fait_documentaire(self):
        record = GraphitiGraphStore._to_provenance_record(
            "ep-sim", {"simulation_id": "sim_1", "platform": "reddit"}
        )
        assert record.origin == ProvenanceOrigin.SIMULATION
        assert not record.is_documentary

    def test_origine_heritee(self):
        record = GraphitiGraphStore._to_provenance_record("ep-legacy", {"content": "x"})
        assert record.origin == ProvenanceOrigin.LEGACY
        assert not record.is_documentary

    def test_origine_non_resolue(self):
        record = GraphitiGraphStore._to_provenance_record("ep-absent", None)
        assert not record.resolved
        assert record.origin == ProvenanceOrigin.UNRESOLVED
        assert record.missing_reason

    def test_provenance_documentaire_incomplete_est_signalee(self):
        record = GraphitiGraphStore._to_provenance_record(
            "ep-1", {"source_document_id": "doc_1"}
        )
        assert record.origin == ProvenanceOrigin.DOCUMENT
        assert record.missing_reason  # incomplet mais non inventé
        assert not record.is_documentary  # une provenance incomplète ne compte pas

    def test_source_role_manquant_rend_la_provenance_incomplete(self):
        record = GraphitiGraphStore._to_provenance_record(
            "ep-1",
            {"source_document_id": "doc_1", "source_filename": "a.txt",
             "chunk_index": 0, "char_start": 0, "char_end": 5, "content": "abcde"},
        )
        assert record.resolved
        assert "source_role" in record.missing_reason
        assert not record.is_documentary

    def test_provenance_complete_est_documentaire(self):
        record = GraphitiGraphStore._to_provenance_record(
            "ep-1",
            {"source_document_id": "doc_1", "source_filename": "a.txt",
             "source_role": "facts", "chunk_index": 0, "char_start": 0,
             "char_end": 5, "content": "abcde"},
        )
        assert record.is_documentary

    def test_positions_incoherentes_signalees(self):
        record = GraphitiGraphStore._to_provenance_record(
            "ep-1",
            {"source_document_id": "doc_1", "source_filename": "a.txt",
             "source_role": "facts", "chunk_index": 0,
             "char_start": 10, "char_end": 10},
        )
        assert "positions incohérentes" in record.missing_reason


class TestProvenanceIsolation:
    def test_la_lecture_est_bornee_par_le_graphe(self):
        store = GraphitiGraphStore(
            driver=MagicMock(), llm_client=MagicMock(), embedder=MagicMock(),
            cross_encoder=MagicMock(), graphiti=MagicMock(),
        )
        params_seen = {}

        def fake_cypher(query, params=None):
            params_seen.update(params or {})
            return []

        store._execute_cypher = fake_cypher
        store._run_async = lambda coro: coro
        store.get_edge_provenance("graphe_A", "edge-1")
        assert params_seen["group_id"] == "graphe_A"
        assert params_seen["edge_uuid"] == "edge-1"

    def test_une_arete_absente_retourne_une_liste_vide(self):
        store = GraphitiGraphStore(
            driver=MagicMock(), llm_client=MagicMock(), embedder=MagicMock(),
            cross_encoder=MagicMock(), graphiti=MagicMock(),
        )
        store._execute_cypher = lambda query, params=None: []
        store._run_async = lambda coro: coro
        assert store.get_edge_provenance("g1", "inconnue") == []

    def test_les_quatre_origines_sont_distinctes(self):
        origines = {
            ProvenanceOrigin.DOCUMENT,
            ProvenanceOrigin.SIMULATION,
            ProvenanceOrigin.LEGACY,
            ProvenanceOrigin.UNRESOLVED,
        }
        assert len(origines) == 4
        # Aucun couple d'origines n'est fusionné : chacune est signalée à part.
        assert ProvenanceOrigin.DOCUMENT != ProvenanceOrigin.LEGACY


class TestZepProvenance:
    def _store(self):
        client = MagicMock()
        return ZepGraphStore(client=client), client

    def test_un_doublure_episode_documente_est_classe_documentaire(self):
        from zep_cloud.types.episode import Episode

        record = ZepGraphStore._classify_episode(
            "ep-1",
            Episode(content="abcde", created_at="2026-01-01T00:00:00Z", uuid_="ep-1",
                    metadata={"source_document_id": "doc_1", "source_filename": "a.txt",
                              "source_chunk_index": 2, "char_start": 4, "char_end": 9,
                              "source_role": "facts"}),
            {"source_document_id": "doc_1", "source_filename": "a.txt",
             "source_chunk_index": 2, "char_start": 4, "char_end": 9, "source_role": "facts"},
        )
        assert record.origin == ProvenanceOrigin.DOCUMENT
        assert record.chunk_index == 2
        assert record.content == "abcde"

    def test_origine_simulee_zep(self):
        record = ZepGraphStore._classify_episode(
            "ep-sim", MagicMock(content="x"), {"simulation_id": "sim_1", "platform": "twitter"}
        )
        assert record.origin == ProvenanceOrigin.SIMULATION
        assert record.platform == "twitter"

    def test_origine_non_resolue_zep(self):
        from zep_cloud import NotFoundError

        store, client = self._store()
        client.graph.episode.get.side_effect = NotFoundError(body="absent")
        record = store._load_episode_record("ep-absent")
        assert not record.resolved
        assert record.origin == ProvenanceOrigin.UNRESOLVED

    def test_une_panne_de_lecture_zep_remonte(self):
        """Une panne n'est pas une provenance absente : elle remonte."""
        from app.utils.graph_store import GraphStoreError

        store, client = self._store()
        client.graph.episode.get.side_effect = RuntimeError("connexion perdue")
        with pytest.raises((GraphStoreError, RuntimeError)):
            store._load_episode_record("ep-1")