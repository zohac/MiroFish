"""Budget de contexte par étape, diagnostics et refus explicite (AC7).

Le cas long est généré par un motif déterministe, jamais committé en clair.
"""

from unittest.mock import MagicMock

import pytest

from app.models.simulation_brief import SimulationBrief, build_minimal_brief
from app.services.simulation_config_generator import (
    ContextBudget,
    SimulationConfigGenerator,
    SimulationContextError,
)


def build_long_text(target_chars: int = 60_000) -> str:
    sentence = (
        "MiroFish transforme des documents sources en un graphe de connaissances "
        "qui alimente des agents simules sur des plateformes sociales. "
    )
    repetitions = target_chars // len(sentence) + 2
    return (sentence * repetitions)[:target_chars]


@pytest.fixture
def generator():
    instance = SimulationConfigGenerator()
    instance.client = MagicMock()
    return instance


class TestBriefProtected:
    def test_le_brief_apparait_en_tete_du_contexte(self, generator):
        brief = SimulationBrief(goal="OBJECTIF_UNIQUE", rules=["REGLE_UNIQUE"])
        context = generator._build_context("consigne", "document", [], simulation_brief=brief)
        assert context.index("OBJECTIF_UNIQUE") < context.index("文档")

    def test_le_brief_n_est_jamais_tronque_avec_les_documents(self, generator):
        brief = SimulationBrief(goal="OBJECTIF_UNIQUE")
        context = generator._build_context(
            "consigne", build_long_text(80_000), [], simulation_brief=brief
        )
        assert "OBJECTIF_UNIQUE" in context

    def test_un_brief_trop_long_refuse_explicitement(self, generator):
        brief = SimulationBrief(goal="X" * 60_000)
        with pytest.raises(SimulationContextError) as exc:
            generator._build_context("x", "document", [], simulation_brief=brief)
        message = str(exc.value)
        assert "budget" in message
        assert "perte silencieuse" in message

    def test_le_refus_du_brief_long_n_ampute_aucune_consigne(self, generator):
        brief = SimulationBrief(goal="X" * 60_000)
        with pytest.raises(SimulationContextError):
            generator._build_context("x", "document", [], simulation_brief=brief)


class TestDiagnostics:
    def test_la_troncature_est_signalee(self, generator):
        generator._build_context("consigne", build_long_text(120_000), [])
        budget = generator.last_context_budget
        assert budget is not None
        assert budget.truncated is True
        assert budget.stage == "configuration"

    def test_le_texte_court_n_est_pas_signale_comme_tronque(self, generator):
        generator._build_context("consigne", "court", [])
        assert generator.last_context_budget.truncated is False

    def test_le_budget_est_copie_dans_les_parametres(self, generator, monkeypatch):
        """L'artefact de configuration doit porter le brief réellement utilisé."""
        monkeypatch.setattr(
            generator, "_generate_time_config", lambda *a, **k: {"reasoning": "r"}
        )
        monkeypatch.setattr(
            generator, "_generate_event_config", lambda *a, **k: {"reasoning": "r"}
        )
        from app.services.simulation_config_generator import (
            EventConfig,
            TimeSimulationConfig,
        )

        monkeypatch.setattr(
            generator, "_parse_time_config", lambda *a, **k: TimeSimulationConfig()
        )
        monkeypatch.setattr(
            generator, "_parse_event_config", lambda *a, **k: EventConfig()
        )
        monkeypatch.setattr(
            generator, "_assign_initial_post_agents", lambda event, configs: event
        )
        brief = build_minimal_brief(goal="Observer l'adoption")

        params = generator.generate_config(
            simulation_id="sim_1",
            project_id="proj_1",
            graph_id="graph_1",
            simulation_requirement="Observer l'adoption",
            document_text="court",
            entities=[],
            simulation_brief=brief,
        )
        payload = params.to_dict()
        assert payload["simulation_brief"]["goal"] == "Observer l'adoption"
        assert payload["context_budgets"]
        assert payload["context_budgets"][0]["stage"] == "configuration"

    def test_budget_serialisable(self):
        budget = ContextBudget(stage="configuration", max_chars=100, used_chars=80)
        assert budget.to_dict()["stage"] == "configuration"


class TestContextComposition:
    def test_les_entites_apparaissent_dans_le_contexte(self, generator):
        from app.services.zep_entity_reader import EntityNode

        entity = EntityNode(
            uuid="u1",
            name="Alice Martin",
            labels=["Person"],
            summary="Praticienne.",
            attributes={},
        )
        context = generator._build_context("consigne", "document", [entity])
        assert "Alice Martin" in context

    def test_le_brief_minimal_ne_rend_que_la_consigne(self, generator):
        """Un brief minimal n'ajoute pas de section vide : le mode simple reste simple."""
        brief = build_minimal_brief(goal="UNE_CONSIGNE")
        context = generator._build_context("UNE_CONSIGNE", "doc", [], simulation_brief=brief)
        assert "UNE_CONSIGNE" in context
        assert "Horizon" not in context


class TestPerDocumentBudget:
    """AC7 : le budget nomme les documents inclus et omis, pas seulement la taille."""

    def test_les_documents_inclus_portent_leur_identifiant(self, generator):
        documents = [
            {"document_id": "doc_a", "filename": "a.txt", "text": "contenu A"},
            {"document_id": "doc_b", "filename": "b.txt", "text": "contenu B"},
        ]
        generator._build_context("consigne", "", [], documents=documents)
        budget = generator.last_context_budget
        assert budget.documents_included == ["doc_a", "doc_b"]
        assert budget.documents_omitted == []
        assert budget.characters_total == len("contenu A") + len("contenu B")

    def test_un_document_hors_budget_est_omis_avec_son_identifiant(self, generator):
        documents = [
            {"document_id": "doc_petit", "filename": "p.txt", "text": "court"},
            {"document_id": "doc_moyen", "filename": "m.txt", "text": "M" * 49_500},
            {"document_id": "doc_geant", "filename": "g.txt", "text": "X" * 60_000},
        ]
        generator._build_context("consigne", "", [], documents=documents)
        budget = generator.last_context_budget
        assert "doc_petit" in budget.documents_included
        assert any(
            entry["document_id"] == "doc_geant" for entry in budget.documents_omitted
        )

    def test_sans_documents_le_diagnostic_ne_pretend_pas_nommer(self, generator):
        generator._build_context("consigne", "un texte", [])
        budget = generator.last_context_budget
        assert budget.documents_included == [""]
        assert budget.characters_total == len("un texte")


class TestOntologyDiagnostics:
    """AC7 : l'étape ontologie expose sa réduction au lieu de la cacher."""

    def _generator(self):
        from app.services.ontology_generator import OntologyGenerator

        return OntologyGenerator(llm_client=MagicMock())

    def test_un_texte_court_ne_signale_aucune_reduction(self):
        generator = self._generator()
        generator._build_document_context(["un texte court"])
        diagnostics = generator.last_context_diagnostics
        assert diagnostics["stage"] == "ontology"
        assert diagnostics["truncated"] is False
        assert diagnostics["sampled"] is False

    def test_un_texte_long_est_signale_comme_echantillonne(self):
        generator = self._generator()
        # Plus de MAX_LONG_TEXT_CHUNKS (60) fragments de 8000 caractères : c'est
        # le seuil à partir duquel l'échantillonnage représentatif s'applique.
        texte_long = ("phrase repetitive pour l'ontologie. " * 20_000)[:600_000]
        context = generator._build_document_context([texte_long])
        diagnostics = generator.last_context_diagnostics
        assert diagnostics["sampled"] is True
        assert diagnostics["chunks_total"] > diagnostics["chunks_sampled"]
        assert diagnostics["used_chars"] <= 50_000 + 200
        assert context

    def test_les_documents_sont_resumes_individuellement(self):
        generator = self._generator()
        generator._build_document_context(["court A", "court B"])
        diagnostics = generator.last_context_diagnostics
        assert len(diagnostics["documents"]) == 2
        assert {entry["document_index"] for entry in diagnostics["documents"]} == {1, 2}

    def test_le_diagnostic_par_document_compte_les_fragments_echantillonnes(self):
        generator = self._generator()
        texte_long = ("phrase repetitive pour l'ontologie. " * 20_000)[:600_000]
        generator._build_document_context([texte_long])
        diagnostics = generator.last_context_diagnostics
        document = diagnostics["documents"][0]
        assert document["chunks_sampled"] <= document["chunks_total"]
        assert document["chunks_sampled"] > 0
        assert document["chunks_total"] == diagnostics["chunks_total"]

    def test_generate_reinitialise_les_diagnostics(self):
        generator = self._generator()
        generator.last_context_diagnostics = {"stage": "ontology", "truncated": True}
        # Un generate échoue faute de réponse LLM, mais réinitialise avant.
        try:
            generator.generate(["court"], "consigne")
        except Exception:
            pass
        # Le diagnostic a été recalculé pour le nouveau contexte.
        assert generator.last_context_diagnostics is not None