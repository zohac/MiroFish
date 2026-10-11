"""Découpage par document et métadonnées alignées (story 009-2, AC2, AC7).

Propriété centrale vérifiée ici : pour 100 % des fragments,
``document_text[char_start:char_end] == chunk_text``.
"""

from pathlib import Path

import pytest

from app.services.graph_builder import (
    DocumentChunkPlan,
    plan_document_chunks,
)

FIXTURES = Path(__file__).parent / "fixtures" / "source_documents"

ALPHA = (FIXTURES / "document_alpha.txt").read_text(encoding="utf-8")
BETA = (FIXTURES / "document_beta.txt").read_text(encoding="utf-8")

DOCUMENTS = [
    {"document_id": "doc_alpha", "filename": "document_alpha.txt", "role": "facts",
     "saved_filename": "a1b2c3.txt"},
    {"document_id": "doc_beta", "filename": "document_beta.txt", "role": "scenario",
     "saved_filename": "d4e5f6.txt"},
]
TEXTS = {"doc_alpha": ALPHA, "doc_beta": BETA}


@pytest.fixture(scope="module")
def plan() -> DocumentChunkPlan:
    return plan_document_chunks(DOCUMENTS, TEXTS, chunk_size=180, chunk_overlap=30)


class TestPerDocumentChunking:
    def test_chaque_document_produit_plusieurs_fragments(self, plan):
        counts = plan.per_document_counts()
        assert counts["doc_alpha"] >= 2
        assert counts["doc_beta"] >= 2

    def test_les_index_sont_locaux_et_base_zero(self, plan):
        for document_id in ("doc_alpha", "doc_beta"):
            indexes = [
                entry["chunk_index"]
                for entry in plan.chunk_metadata
                if entry["source_document_id"] == document_id
            ]
            assert indexes == list(range(len(indexes)))

    def test_un_fragment_ne_couvre_jamais_deux_documents(self, plan):
        for entry in plan.chunk_metadata:
            assert entry["source_document_id"] in TEXTS
            texte = TEXTS[entry["source_document_id"]]
            assert texte[entry["char_start"]:entry["char_end"]] == plan.chunks[
                plan.chunk_metadata.index(entry)
            ]

    def test_les_positions_restituent_exactement_le_fragment(self, plan):
        for chunk, entry in zip(plan.chunks, plan.chunk_metadata):
            texte = TEXTS[entry["source_document_id"]]
            assert texte[entry["char_start"]:entry["char_end"]] == chunk

    def test_les_positions_sont_dans_le_texte_normalise(self, plan):
        for entry in plan.chunk_metadata:
            texte = TEXTS[entry["source_document_id"]]
            assert 0 <= entry["char_start"] < entry["char_end"] <= len(texte)

    def test_le_dernier_fragment_est_inclus(self, plan):
        for document_id, texte in TEXTS.items():
            dernier = [
                entry for entry in plan.chunk_metadata
                if entry["source_document_id"] == document_id
            ][-1]
            chunk = plan.chunks[plan.chunk_metadata.index(dernier)]
            assert chunk in texte

    def test_le_role_du_document_est_reporte(self, plan):
        roles = {entry["source_document_id"]: entry["source_role"] for entry in plan.chunk_metadata}
        assert roles["doc_alpha"] == "facts"
        assert roles["doc_beta"] == "scenario"

    def test_le_nom_sauvegarde_reste_sur_le_document_pas_sur_le_fragment(self, plan):
        """Le contrat d'ingestion n'accepte pas `saved_filename` : il vit sur le
        `SourceDocument`, pas dans les métadonnées de fragment (ADR 0012 §1)."""
        for entry in plan.chunk_metadata:
            assert "saved_filename" not in entry

    def test_aucune_page_inventee_quand_l_extracteur_n_en_fournit_pas(self, plan):
        for entry in plan.chunk_metadata:
            assert entry.get("page") is None
            assert entry.get("section") is None


class TestOverlap:
    def test_le_chevauchement_est_reproduit_entre_fragments(self):
        texte = ALPHA
        plan = plan_document_chunks([DOCUMENTS[0]], {"doc_alpha": texte},
                                   chunk_size=120, chunk_overlap=40)
        entrees = plan.chunk_metadata
        if len(entrees) >= 2:
            fin = entrees[0]["char_end"]
            debut = entrees[1]["char_start"]
            assert debut < fin


class TestContextText:
    def test_la_concatenation_reste_disponible_comme_contexte(self, plan):
        assert "document_alpha.txt" in plan.context_text
        assert "document_beta.txt" in plan.context_text
        assert ALPHA in plan.context_text
        assert BETA in plan.context_text

    def test_le_contexte_ne_sert_pas_de_source_de_positions(self, plan):
        """Le contexte est un texte de prompt, pas l'origine des fragments."""
        assert plan.chunks != [plan.context_text]


class TestDiagnostics:
    def test_un_document_sans_texte_est_signale(self):
        plan = plan_document_chunks(
            DOCUMENTS, {"doc_alpha": ALPHA}, chunk_size=180, chunk_overlap=30
        )
        omis = plan.diagnostics["documents_omitted"]
        assert [entry["document_id"] for entry in omis] == ["doc_beta"]
        assert "absent" in omis[0]["reason"]

    def test_un_document_vide_est_signale(self):
        plan = plan_document_chunks(
            DOCUMENTS, {"doc_alpha": ALPHA, "doc_beta": "   "},
            chunk_size=180, chunk_overlap=30,
        )
        omis = plan.diagnostics["documents_omitted"]
        assert [entry["document_id"] for entry in omis] == ["doc_beta"]

    def test_les_diagnostics_comptent_documents_et_fragments(self, plan):
        assert plan.diagnostics["documents_total"] == 2
        assert plan.diagnostics["documents_ingested"] == 2
        assert plan.diagnostics["chunks_total"] == len(plan.chunks)

    def test_les_metadonnees_alignees_sont_completes(self, plan):
        for entry in plan.chunk_metadata:
            for champ in (
                "source_document_id", "source_filename", "chunk_index",
                "char_start", "char_end", "source_role",
            ):
                assert champ in entry


class TestRepetitiveTextPositions:
    """Le cas que `str.find` ratait : un texte répétitif avec chevauchement.

    Chaque fragment doit porter la position de l'occurrence réellement découpée,
    pas la première occurrence du texte. Sinon deux fragments distincts
    partagent la même plage et la traçabilité est fausse.
    """

    def test_les_positions_sont_distinctes_et_monotones(self):
        texte = "ab cd ef gh " * 60
        plan = plan_document_chunks(
            [{"document_id": "d", "filename": "r.txt", "role": "facts"}],
            {"d": texte},
            chunk_size=40,
            chunk_overlap=20,
        )
        spans = [(e["char_start"], e["char_end"]) for e in plan.chunk_metadata]
        assert len(set(spans)) == len(spans), "deux fragments partagent la même plage"
        starts = [s for s, _ in spans]
        assert starts == sorted(starts), "les positions reculent"

    def test_le_chevauchement_eleve_ne_repete_pas_le_meme_span(self):
        texte = "phrase identique repetee plusieurs fois. " * 40
        plan = plan_document_chunks(
            [{"document_id": "d", "filename": "r.txt", "role": "facts"}],
            {"d": texte},
            chunk_size=500,
            chunk_overlap=400,
        )
        spans = [(e["char_start"], e["char_end"]) for e in plan.chunk_metadata]
        assert len(set(spans)) == len(spans)

    def test_l_invariant_de_position_tient_sur_texte_repetitif(self):
        texte = "ab cd ef gh " * 60
        plan = plan_document_chunks(
            [{"document_id": "d", "filename": "r.txt", "role": "facts"}],
            {"d": texte},
            chunk_size=40,
            chunk_overlap=20,
        )
        for chunk, entry in zip(plan.chunks, plan.chunk_metadata):
            assert texte[entry["char_start"]:entry["char_end"]] == chunk

    def test_un_chevauchement_maximal_ne_boucle_pas(self):
        texte = "un texte assez long pour etre decoupe en plusieurs morceaux." * 5
        plan = plan_document_chunks(
            [{"document_id": "d", "filename": "r.txt", "role": "facts"}],
            {"d": texte},
            chunk_size=40,
            chunk_overlap=39,
        )
        assert plan.total_chunks > 0
        spans = [(e["char_start"], e["char_end"]) for e in plan.chunk_metadata]
        assert len(set(spans)) == len(spans), "spans dupliqués avec un overlap maximal"

    def test_un_chevauchement_eleve_proche_de_la_taille_ne_duplique_rien(self):
        texte = "ab cd ef gh ij kl mn op " * 20
        for chunk_size, overlap in ((10, 9), (12, 8), (30, 29)):
            plan = plan_document_chunks(
                [{"document_id": "d", "filename": "r.txt", "role": "facts"}],
                {"d": texte},
                chunk_size=chunk_size,
                chunk_overlap=overlap,
            )
            spans = [(e["char_start"], e["char_end"]) for e in plan.chunk_metadata]
            assert len(set(spans)) == len(spans), f"doublon pour {chunk_size}/{overlap}"


class TestLegacyFallback:
    def test_aucun_document_ne_produit_aucun_fragment(self):
        plan = plan_document_chunks([], {}, chunk_size=100, chunk_overlap=10)
        assert plan.chunks == []
        assert plan.chunk_metadata == []