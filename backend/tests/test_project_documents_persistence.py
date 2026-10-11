"""Persistance des documents, du brief et d'`additional_context` (AC1, AC2, AC6).

Ces tests écrivent dans un répertoire temporaire : aucun upload réel, aucun LLM.
"""

import json
from pathlib import Path

import pytest

from app.models.project import Project, ProjectManager, ProjectStatus
from app.models.source_document import create_source_document

FIXTURES = Path(__file__).parent / "fixtures" / "source_documents"
LEGACY = json.loads((FIXTURES / "project_legacy.json").read_text(encoding="utf-8"))


@pytest.fixture
def project_store(tmp_path, monkeypatch):
    """Redirige le stockage des projets vers un répertoire temporaire."""
    monkeypatch.setattr(
        ProjectManager, "PROJECTS_DIR", str(tmp_path / "projects")
    )
    ProjectManager._ensure_projects_dir()
    return tmp_path


class TestProjectRoundTrip:
    def test_un_projet_neuf_conserve_documents_et_brief(self, project_store):
        project = ProjectManager.create_project(name="Test 009-2")
        document = create_source_document(
            filename="rapport.pdf", saved_filename="deadbeef.pdf"
        )
        project.source_documents = [document.to_dict()]
        project.additional_context = "Le budget média est limité."
        project.simulation_brief = {
            "goal": "Explorer la reaction au lancement.",
            "additional_context": "Le budget média est limité.",
            "schema_version": 1,
        }
        ProjectManager.save_project(project)

        relu = ProjectManager.get_project(project.project_id)
        assert relu.additional_context == "Le budget média est limité."
        assert [doc.filename for doc in relu.get_source_documents()] == ["rapport.pdf"]
        assert relu.get_brief().goal == "Explorer la reaction au lancement."

    def test_le_texte_normalise_par_document_est_conserve(self, project_store):
        project = ProjectManager.create_project(name="Textes par document")
        texte = "Un document avec du contenu normalise."
        document = create_source_document(
            filename="a.txt", saved_filename="a.txt"
        )
        ProjectManager.save_document_text(
            project.project_id, document.document_id, texte
        )
        relu = ProjectManager.get_document_text(
            project.project_id, document.document_id
        )
        assert relu == texte

    def test_les_textes_de_tous_les_documents_sont_retrouves(self, project_store):
        project = ProjectManager.create_project(name="Plusieurs documents")
        ProjectManager.save_document_text(project.project_id, "doc_a", "texte A")
        ProjectManager.save_document_text(project.project_id, "doc_b", "texte B")
        textes = ProjectManager.get_all_document_texts(project.project_id)
        assert textes == {"doc_a": "texte A", "doc_b": "texte B"}

    def test_un_document_id_ne_peut_pas_sortir_du_repertoire(self, project_store):
        project = ProjectManager.create_project(name="Securite")
        with pytest.raises(ValueError):
            ProjectManager.save_document_text(project.project_id, "../evasion", "x")

    def test_un_texte_absent_retourne_none(self, project_store):
        project = ProjectManager.create_project(name="Absent")
        assert ProjectManager.get_document_text(project.project_id, "doc_inconnu") is None


class TestLegacyProjectRead:
    def test_un_ancien_project_json_reste_lisible(self, project_store):
        project = Project.from_dict(LEGACY)
        assert project.project_id == LEGACY["project_id"]
        assert project.get_brief() is None
        assert project.get_source_documents() == []

    def test_un_ancien_projet_ne_fabrique_ni_document_ni_position(self, project_store):
        project = Project.from_dict(LEGACY)
        assert project.source_documents == []
        assert project.additional_context is None
        textes = ProjectManager.get_all_document_texts(project.project_id)
        assert textes == {}

    def test_un_ancien_projet_reste_reutilisable(self, project_store):
        project = Project.from_dict(LEGACY)
        project.status = ProjectStatus.FAILED
        project.error = "reprise"
        payload = project.to_dict()
        relu = Project.from_dict(payload)
        assert relu.status is ProjectStatus.FAILED
        assert relu.files == LEGACY["files"]


class TestConflictStorage:
    """AC8 : un conflit conservant ses deux sources est réellement stocké."""

    def _reference(self, document_id):
        from app.models.source_document import DocumentValidationStatus, SourceReference, DocumentRole

        return SourceReference(
            document_id=document_id,
            filename=f"{document_id}.txt",
            role=DocumentRole.FACTS,
            priority=1,
            date=None,
            validation_status=DocumentValidationStatus.UNVALIDATED,
            chunk_index=0,
            char_start=0,
            char_end=10,
        )

    def test_un_conflit_detecte_est_stocke_dans_le_projet(self, project_store):
        from app.models.source_document import detect_conflicts

        project = ProjectManager.create_project(name="Conflits")
        scan = detect_conflicts(
            [
                {
                    "claim": "Le service Premium est disponible pour tous.",
                    "source_reference": self._reference("doc_1"),
                },
                {
                    "claim": "Le service Premium n'est pas disponible pour tous.",
                    "source_reference": self._reference("doc_2"),
                },
            ]
        )
        assert scan.conflicts
        project.record_source_conflicts(scan.conflicts)
        ProjectManager.save_project(project)

        relu = ProjectManager.get_project(project.project_id)
        conflicts = relu.get_source_conflicts()
        assert len(conflicts) == 1
        assert len(conflicts[0].source_references) == 2

    def test_un_projet_ancien_n_a_aucun_conflit(self, project_store):
        project = Project.from_dict(LEGACY)
        assert project.get_source_conflicts() == []


class TestPartialDocumentFallback:
    """Un texte manquant ne prive pas les autres documents de leur provenance."""

    def test_les_documents_presents_gardent_leur_provenance(self, project_store):
        from app.api.graph import _plan_project_chunks

        project = ProjectManager.create_project(name="Partiel")
        d1 = create_source_document(filename="a.txt", saved_filename="a.txt")
        d2 = create_source_document(filename="b.txt", saved_filename="b.txt")
        project.source_documents = [d1.to_dict(), d2.to_dict()]
        # Seul d1 a un texte normalisé.
        ProjectManager.save_document_text(project.project_id, d1.document_id, "Texte de A.")

        plan = _plan_project_chunks(
            project, "concat", chunk_size=100, chunk_overlap=10
        )
        assert plan.chunk_metadata
        assert all(
            entry["source_document_id"] == d1.document_id
            for entry in plan.chunk_metadata
        )
        assert any(
            entry["document_id"] == d2.document_id
            for entry in plan.diagnostics["documents_omitted"]
        )

    def test_aucun_document_typé_retombe_sur_la_concaténation(self, project_store):
        from app.api.graph import _plan_project_chunks

        project = ProjectManager.create_project(name="Ancien")
        plan = _plan_project_chunks(
            project, "un texte concatené", chunk_size=100, chunk_overlap=10
        )
        assert plan.chunks
        assert plan.chunk_metadata == []


class TestApiFormMetadata:
    def test_les_metadonnees_de_formulaire_illisibles_sont_ignorees(self):
        from app.api.graph import _parse_document_form_map

        assert _parse_document_form_map(None) == {}
        assert _parse_document_form_map("") == {}
        assert _parse_document_form_map("pas du json") == {}
        assert _parse_document_form_map("[1, 2, 3]") == {}

    def test_un_role_demande_est_respecte(self):
        from app.api.graph import _requested_role

        raw = json.dumps({"rapport.pdf": "reference"})
        role = _requested_role(raw, "rapport.pdf")
        assert role is not None
        assert role.value == "reference"

    def test_un_nom_de_fichier_ne_donne_pas_de_role_implicite(self):
        from app.api.graph import _requested_role

        assert _requested_role(None, "official.pdf") is None

    def test_une_priorite_invalide_est_ignoree(self):
        from app.api.graph import _requested_priority

        assert _requested_priority(json.dumps({"a": 9}), "a") is None
        assert _requested_priority(json.dumps({"a": "x"}), "a") is None
        assert _requested_priority(json.dumps({"a": 3}), "a") == 3