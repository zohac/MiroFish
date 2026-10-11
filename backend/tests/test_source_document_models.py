"""Contrat des modèles de sources typées (story 009-2, AC1, AC2).

Ces tests sont hermétiques : aucun réseau, aucun `.env`, aucun Neo4j. Le cas
long de plus de 50 000 caractères est **généré** par un motif déterministe,
jamais committé en clair.
"""

import hashlib
from pathlib import Path

import pytest

from app.models.source_document import (
    ConflictResolutionRule,
    ConflictStatus,
    DocumentChunk,
    DocumentRole,
    DocumentValidationStatus,
    SourceConflict,
    SourceConflictError,
    SourceDocument,
    SourceDocumentError,
    SourceReference,
    create_source_document,
    can_transition,
    detect_conflicts,
    resolve_conflict,
)

FIXTURES = Path(__file__).parent / "fixtures" / "source_documents"


def load_document(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


# --- AC1 : création, défauts du mode simple, autorité du nom de fichier ---


class TestSourceDocumentCreation:
    def test_mode_simple_applique_les_defauts_de_l_adrs(self):
        document = create_source_document(
            filename="notes.txt", saved_filename="ab12cd34.txt"
        )
        assert document.role is DocumentRole.FACTS
        assert document.priority == 1
        assert document.date is None
        assert document.author is None
        assert document.source is None
        assert document.validation_status is DocumentValidationStatus.UNVALIDATED
        assert document.total_chunks == 0

    def test_identifiant_stable_est_un_uuid_unique(self):
        premier = create_source_document(filename="a.txt", saved_filename="a")
        second = create_source_document(filename="a.txt", saved_filename="a")
        assert premier.document_id != second.document_id
        assert premier.document_id.startswith("doc_")

    def test_un_nom_de_fichier_flatteur_ne_confere_aucune_autorite(self):
        """`official`, `canonical`, `source_of_truth` : aucun traitement particulier."""
        flatteurs = [
            "official.pdf",
            "canonical_v3.pdf",
            "source_of_truth.docx",
            "FINAL_final_v2.pdf",
            "validated.pdf",
        ]
        documents = [
            create_source_document(filename=name, saved_filename="s.txt")
            for name in flatteurs
        ]
        assert {d.role for d in documents} == {DocumentRole.FACTS}
        assert {d.priority for d in documents} == {1}
        assert {d.validation_status for d in documents} == {
            DocumentValidationStatus.UNVALIDATED
        }

    def test_le_constructeur_ne_prend_jamais_le_nom_comme_autorite(self):
        """`filename` n'est stocké, jamais interprété : seul `role` l'est."""
        document = SourceDocument(
            document_id="doc_x",
            filename="official.pdf",
            role="facts",
            saved_filename="s.pdf",
        )
        assert document.filename == "official.pdf"
        assert document.validation_status is DocumentValidationStatus.UNVALIDATED

    @pytest.mark.parametrize("priority", [0, 6, -1, "1", 1.5, True])
    def test_priorite_hors_borne_refusee(self, priority):
        with pytest.raises(SourceDocumentError):
            create_source_document(
                filename="a.txt", saved_filename="a", priority=priority
            )

    def test_role_inconnu_refuse(self):
        with pytest.raises(SourceDocumentError):
            create_source_document(
                filename="a.txt", saved_filename="a", role="autoritaire"
            )

    def test_statut_de_validation_inconnu_refuse(self):
        with pytest.raises(SourceDocumentError):
            create_source_document(
                filename="a.txt", saved_filename="a", validation_status="vrai"
            )


class TestSourceDocumentSerialisation:
    def test_round_trip_ne_perd_aucun_champ(self):
        document = create_source_document(
            filename="rapport.pdf",
            saved_filename="deadbeef.pdf",
            role=DocumentRole.REFERENCE,
            priority=3,
            date="2026-03-14",
            author="Alice Martin",
            source="Rapport annuel",
        )
        relu = SourceDocument.from_dict(document.to_dict())
        assert relu.to_dict() == document.to_dict()

    def test_le_champ_supprime_ou_absent_reprend_son_defaut(self):
        relu = SourceDocument.from_dict(
            {"document_id": "doc_1", "filename": "a.txt", "saved_filename": "a"}
        )
        assert relu.role is DocumentRole.FACTS
        assert relu.priority == 1
        assert relu.validation_status is DocumentValidationStatus.UNVALIDATED


class TestValidationStatusTransitions:
    def test_transitions_declarees_autorisees(self):
        assert can_transition(
            DocumentValidationStatus.UNVALIDATED, DocumentValidationStatus.VALIDATED
        )
        assert can_transition(
            DocumentValidationStatus.UNVALIDATED, DocumentValidationStatus.CONFLICTED
        )
        assert can_transition(
            DocumentValidationStatus.CONFLICTED, DocumentValidationStatus.VALIDATED
        )

    def test_transition_non_declaree_refusee(self):
        assert not can_transition(
            DocumentValidationStatus.UNVALIDATED, DocumentValidationStatus.UNVALIDATED
        )
        with pytest.raises(SourceDocumentError):
            create_source_document(
                filename="a.txt", saved_filename="a"
            ).with_validation_status(DocumentValidationStatus.UNVALIDATED)

    def test_statut_n_influence_jamais_le_contenu(self):
        """Aucun statut ne modifie rôle, priorité ni texte : il est déclaratif."""
        base = create_source_document(filename="a.txt", saved_filename="a")
        validé = base.with_validation_status(DocumentValidationStatus.VALIDATED)
        assert validé.role is base.role
        assert validé.priority == base.priority
        assert validé.filename == base.filename


# --- AC2 : fragments et positions exactes ---


class TestDocumentChunk:
    def test_positions_contraintes(self):
        chunk = DocumentChunk(
            source_document_id="doc_1",
            source_filename="a.txt",
            chunk_index=0,
            text="Bonjour",
            source_role=DocumentRole.FACTS,
            char_start=0,
            char_end=7,
        )
        assert chunk.text == "Bonjour"

    def test_char_end_egale_a_char_start_refuse(self):
        with pytest.raises(SourceDocumentError):
            DocumentChunk(
                source_document_id="doc_1",
                source_filename="a.txt",
                chunk_index=0,
                text="a",
                source_role=DocumentRole.FACTS,
                char_start=5,
                char_end=5,
            )

    def test_index_negatif_refuse(self):
        with pytest.raises(SourceDocumentError):
            DocumentChunk(
                source_document_id="doc_1",
                source_filename="a.txt",
                chunk_index=-1,
                text="a",
                source_role=DocumentRole.FACTS,
                char_start=0,
                char_end=1,
            )

    def test_page_absente_par_defaut_et_non_deduite(self):
        chunk = DocumentChunk(
            source_document_id="doc_1",
            source_filename="sans-pagination.txt",
            chunk_index=3,
            text="a",
            source_role=DocumentRole.FACTS,
            char_start=0,
            char_end=1,
        )
        assert chunk.page is None
        assert chunk.section is None

    def test_page_fournie_par_l_extracteur_est_conservee(self):
        chunk = DocumentChunk(
            source_document_id="doc_1",
            source_filename="scanne.pdf",
            chunk_index=0,
            text="a",
            source_role=DocumentRole.FACTS,
            char_start=0,
            char_end=1,
            page=4,
            section="Chapitre 2",
        )
        assert chunk.page == 4
        assert chunk.section == "Chapitre 2"

    def test_page_zero_refusee(self):
        with pytest.raises(SourceDocumentError):
            DocumentChunk(
                source_document_id="doc_1",
                source_filename="a.pdf",
                chunk_index=0,
                text="a",
                source_role=DocumentRole.FACTS,
                char_start=0,
                char_end=1,
                page=0,
            )

    def test_verification_contre_le_document_source(self):
        text = "Le service est disponible pour tous les clients."
        chunk = DocumentChunk(
            source_document_id="doc_1",
            source_filename="a.txt",
            chunk_index=0,
            text=text[4:16],
            source_role=DocumentRole.FACTS,
            char_start=4,
            char_end=16,
        )
        assert chunk.verify_against_document(text)

    def test_verification_echoue_si_position_fausse(self):
        chunk = DocumentChunk(
            source_document_id="doc_1",
            source_filename="a.txt",
            chunk_index=0,
            text="autre chose",
            source_role=DocumentRole.FACTS,
            char_start=0,
            char_end=11,
        )
        assert not chunk.verify_against_document("Le service est disponible.")

    def test_metadonnees_d_ingestion(self):
        chunk = DocumentChunk(
            source_document_id="doc_1",
            source_filename="a.txt",
            chunk_index=2,
            text="abc",
            source_role=DocumentRole.SCENARIO,
            char_start=10,
            char_end=13,
        )
        metadata = chunk.to_metadata()
        assert metadata["source_document_id"] == "doc_1"
        assert metadata["chunk_index"] == 2
        assert metadata["source_role"] == "scenario"
        assert metadata["char_start"] == 10
        assert metadata["char_end"] == 13


# --- AC8 : conservation des deux sources et règles déclarées ---


def make_reference(document_id, *, priority=1, date=None, status=None, filename="a.txt"):
    return SourceReference(
        document_id=document_id,
        filename=filename,
        role=DocumentRole.FACTS,
        priority=priority,
        date=date,
        validation_status=status or DocumentValidationStatus.UNVALIDATED,
        chunk_index=0,
        char_start=0,
        char_end=10,
    )


class TestSourceConflict:
    def test_un_conflit_exige_deux_documents_distincts(self):
        reference = make_reference("doc_1")
        with pytest.raises(SourceConflictError):
            SourceConflict("c1", "une affirmation", [reference, reference])

    def test_les_deux_sources_sont_conservees_a_la_resolution(self):
        conflict = SourceConflict(
            "c1",
            "Le service Premium est disponible",
            [make_reference("doc_1"), make_reference("doc_2", priority=4)],
        )
        resolu = resolve_conflict(conflict, ConflictResolutionRule.PRIORITY)
        assert resolu.status is ConflictStatus.RESOLVED
        assert resolu.resolution == "doc_1"
        assert len(resolu.source_references) == 2
        assert {ref.document_id for ref in resolu.source_references} == {"doc_1", "doc_2"}

    def test_regle_qui_ne_departage_pas_laisse_le_conflit_ouvert(self):
        conflict = SourceConflict(
            "c1", "affirmation", [make_reference("doc_1"), make_reference("doc_2")]
        )
        resolu = resolve_conflict(conflict, ConflictResolutionRule.PRIORITY)
        assert resolu.status is ConflictStatus.OPEN
        assert resolu.resolution is None
        assert resolu.resolution_rule is ConflictResolutionRule.PRIORITY

    def test_la_regle_est_consignee_avec_la_decision(self):
        conflict = SourceConflict(
            "c1",
            "affirmation",
            [
                make_reference("doc_1"),
                make_reference("doc_2", status=DocumentValidationStatus.VALIDATED),
            ],
        )
        resolu = resolve_conflict(conflict, ConflictResolutionRule.VALIDATION_STATUS)
        assert resolu.resolution_rule is ConflictResolutionRule.VALIDATION_STATUS
        assert resolu.resolution == "doc_2"

    def test_regle_recency_refuse_une_date_absente(self):
        conflict = SourceConflict(
            "c1",
            "affirmation",
            [make_reference("doc_1", date="2026-01-01"), make_reference("doc_2")],
        )
        resolu = resolve_conflict(conflict, ConflictResolutionRule.RECENCY)
        assert resolu.status is ConflictStatus.OPEN
        assert resolu.resolution is None

    def test_regle_recency_departage_sur_la_date(self):
        conflict = SourceConflict(
            "c1",
            "affirmation",
            [
                make_reference("doc_1", date="2026-01-01"),
                make_reference("doc_2", date="2026-06-01"),
            ],
        )
        resolu = resolve_conflict(conflict, ConflictResolutionRule.RECENCY)
        assert resolu.resolution == "doc_2"

    def test_round_trip_du_conflit(self):
        conflict = SourceConflict(
            "c1",
            "affirmation",
            [make_reference("doc_1"), make_reference("doc_2", priority=5)],
        )
        resolu = resolve_conflict(conflict, ConflictResolutionRule.PRIORITY)
        relu = SourceConflict.from_dict(resolu.to_dict())
        assert relu.to_dict() == resolu.to_dict()


class TestDetectConflicts:
    def test_contradiction_lexicale_detectee(self):
        result = detect_conflicts(
            [
                {
                    "claim": "Le service Premium est disponible pour tous les comptes.",
                    "source_reference": make_reference("doc_1"),
                },
                {
                    "claim": "Le service Premium n'est pas disponible pour tous les comptes.",
                    "source_reference": make_reference("doc_2"),
                },
            ]
        )
        assert len(result.conflicts) == 1
        assert {ref.document_id for ref in result.conflicts[0].source_references} == {
            "doc_1",
            "doc_2",
        }

    def test_deux_affirmations_sans_rapport_ne_sont_pas_un_conflit(self):
        result = detect_conflicts(
            [
                {
                    "claim": "Le service Premium est disponible.",
                    "source_reference": make_reference("doc_1"),
                },
                {
                    "claim": "Aucun remboursement n'est possible.",
                    "source_reference": make_reference("doc_2"),
                },
            ]
        )
        assert result.conflicts == []

    def test_deux_fragments_du_meme_document_ne_sont_pas_un_conflit(self):
        result = detect_conflicts(
            [
                {
                    "claim": "Le service Premium est disponible.",
                    "source_reference": make_reference("doc_1"),
                },
                {
                    "claim": "Le service Premium n'est pas disponible.",
                    "source_reference": make_reference("doc_1"),
                },
            ]
        )
        assert result.conflicts == []

    def test_detection_bornee_declare_ce_qu_elle_n_a_pas_couvert(self):
        claims = [
            {
                "claim": f"Le sujet numero {index} est disponible pour le contrat {index}.",
                "source_reference": make_reference(f"doc_{index}"),
            }
            for index in range(12)
        ]
        result = detect_conflicts(claims, max_comparisons=5)
        assert result.comparisons_made <= 5
        assert result.comparisons_skipped > 0
        assert result.truncated_at is not None

    def test_une_affirmation_sans_source_est_refusee(self):
        with pytest.raises(SourceConflictError):
            detect_conflicts([{"claim": "une affirmation"}])


# --- AC7 : le cas long est généré, pas committé ---


def build_long_text(target_chars: int = 60_000) -> str:
    """Produit un texte déterministe de plus de 50 000 caractères."""

    sentence = (
        "MiroFish transforme des documents sources en un graphe de connaissances "
        "qui alimente des agents simules sur des plateformes sociales publiques. "
    )
    repetitions = target_chars // len(sentence) + 2
    return (sentence * repetitions)[:target_chars]


class TestLongCase:
    def test_le_cas_long_depasse_cinquante_mille_caracteres(self):
        text = build_long_text()
        assert len(text) > 50_000

    def test_le_cas_long_est_deterministe(self):
        assert build_long_text() == build_long_text()


class TestFixtureIntegrity:
    @pytest.mark.parametrize(
        "name", ["document_alpha.txt", "document_beta.txt"]
    )
    def test_les_fixtures_sont_lisibles_et_non_vides(self, name):
        text = load_document(name)
        assert text.strip()
        assert len(text) > 200

    def test_les_empreintes_des_fixtures_sont_stables(self):
        """Un fixture modifié ne doit pas passer inaperçu : son empreinte est notée ici."""
        attendu = {
            "document_alpha.txt": "cb137335026fedf4",
            "document_beta.txt": "897ca86aa512514c",
        }
        for name, prefix in attendu.items():
            data = (FIXTURES / name).read_bytes()
            assert hashlib.sha256(data).hexdigest().startswith(prefix), (
                f"le fixture {name} a changé : mets à jour son empreinte ici"
            )