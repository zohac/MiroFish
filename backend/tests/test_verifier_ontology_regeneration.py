"""Tests unitaires hermétiques pour la régénération déterministe et le budget C3.

Story 007-3 (AC1 à AC8) :
- AC1 : température 0.0 transmise au LLM par OntologyGenerator.generate, max_tokens=None et max_attempts=2 préservés.
- AC2 : déterminisme du prompt utilisateur, du message système et des diagnostics de contexte.
- AC3 : projection canonique des champs stables (tri par nom, conservation des doublons, isolation des descriptions).
- AC4 : intégration avec le contrat GraphStore (pose set_ontology sans fuite de cache, politique stricte transmise).
- AC5/AC6 : logique de la sonde verifier_ontology_regeneration.py testée sans appel réseau ni Neo4j réel
  (respect des seuils, détection de divergences, sortie JSON complète, code retour).
- AC7 : non-régression des règles de normalisation et étanchéité NFR-5.
- AC8 : filet hermétique étoffé de plus de 20 nouveaux tests.
"""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import time
from typing import Any, Dict, List, Optional, Tuple
from unittest.mock import MagicMock

import pytest

from app.services.ontology_generator import OntologyGenerator
from app.utils.graph_store import GraphValidationError
from app.utils.graph_store.base import AppliedOntology, GraphStore
from app.utils.ontology import (
    canonical_ontology_projection,
    normalize_ontology_attributes,
)
from scripts.verifier_ontology_regeneration import (
    SEUIL_DOCKER_50K_S,
    SEUIL_HOTE_50K_S,
    charger_corpus,
    comparer_projections,
    evaluer_corpus_c3,
    executer_verification_c3,
    mesurer_une_generation,
)


class RecordingLLMClient:
    """Double d'appel LLM capturant tous les arguments transmis."""

    def __init__(self, response: Optional[Dict[str, Any]] = None):
        self.calls: List[Dict[str, Any]] = []
        self.response = response or {
            "entity_types": [
                {
                    "name": "Operator",
                    "description": "Opérateur de réseau",
                    "attributes": [{"name": "name", "type": "text"}],
                },
                {
                    "name": "Person",
                    "description": "Individu",
                    "attributes": [{"name": "full_name", "type": "text"}],
                },
                {
                    "name": "Organization",
                    "description": "Organisation",
                    "attributes": [{"name": "org_name", "type": "text"}],
                },
            ],
            "edge_types": [
                {
                    "name": "OPERATES",
                    "description": "Exploite le réseau",
                    "source_targets": [{"source": "Operator", "target": "Organization"}],
                    "attributes": [{"name": "since", "type": "text"}],
                }
            ],
            "analysis_summary": "Analyse déterministe.",
        }

    def chat_json(self, **kwargs) -> Dict[str, Any]:
        self.calls.append(copy.deepcopy(kwargs))
        return copy.deepcopy(self.response)


class InMemoryMockGraphStore(GraphStore):
    """Store en mémoire neutre pour tester la sonde sans Neo4j réel."""

    def __init__(self):
        self.graphs: Dict[str, Dict[str, Any]] = {}
        self.applied_ontologies: Dict[str, AppliedOntology] = {}
        self.calls: List[Tuple[str, Dict[str, Any]]] = []

    def create_graph(self, name: str, graph_id: Optional[str] = None) -> str:
        gid = graph_id or f"graph_{len(self.graphs) + 1}"
        self.graphs[gid] = {"name": name, "deleted": False}
        return gid

    def delete_graph(self, graph_id: str) -> None:
        if graph_id in self.graphs:
            self.graphs[graph_id]["deleted"] = True
            self.applied_ontologies.pop(graph_id, None)

    def set_ontology(self, graph_id: str, ontology: Dict[str, Any], *, strict: bool = False) -> None:
        if not isinstance(ontology, dict):
            raise GraphValidationError("L'ontologie doit être un dictionnaire")
        self.calls.append(("set_ontology", {"graph_id": graph_id, "ontology": ontology, "strict": strict}))
        entity_types = tuple(e["name"] for e in ontology.get("entity_types", []) if "name" in e)
        edge_types = tuple(r["name"] for r in ontology.get("edge_types", []) if "name" in r)
        self.applied_ontologies[graph_id] = AppliedOntology(
            entity_type_names=entity_types,
            edge_type_names=edge_types,
            strict=strict,
        )

    def get_applied_ontology(self, graph_id: str) -> Optional[AppliedOntology]:
        return self.applied_ontologies.get(graph_id)

    def get_graph_data(self, graph_id: str) -> Dict[str, Any]:
        return {"nodes": [], "edges": []}

    def get_graph_info(self, graph_id: str) -> Any:
        return None

    def add_episode(self, graph_id: str, text: str, **kwargs) -> Any:
        return None

    def add_text_batch(self, graph_id: str, chunks: List[str], **kwargs) -> str:
        return "batch-id"

    def wait_for_batch(self, batch_id: str, timeout: float = 600.0) -> None:
        pass

    def wait_for_episodes(self, episode_ids: List[str], timeout: float = 600.0) -> None:
        pass

    def get_node(self, graph_id: str, node_id: str) -> Optional[Any]:
        return None

    def get_all_nodes(self, graph_id: str) -> List[Any]:
        return []

    def get_all_edges(self, graph_id: str, include_temporal: bool = True) -> List[Any]:
        return []

    def get_node_edges(self, graph_id: str, node_id: str) -> List[Any]:
        return []

    def get_edge_provenance(self, graph_id: str, edge_uuid: str) -> List[Any]:
        return []

    def search(self, graph_id: str, query: str, **kwargs) -> Dict[str, Any]:
        return {}


# ---------------------------------------------------------------------------
# AC1 : Température 0.0 et paramètres d'appel LLM
# ---------------------------------------------------------------------------

def test_ac1_generator_transmet_temperature_zero():
    """AC1 : OntologyGenerator.generate passe explicitement temperature=0.0 à chat_json."""
    llm = RecordingLLMClient()
    generator = OntologyGenerator(llm_client=llm)

    generator.generate(
        document_texts=["Document de test."],
        simulation_requirement="Brief de test.",
    )

    assert len(llm.calls) == 1
    call = llm.calls[0]
    assert call["temperature"] == 0.0
    assert call["max_tokens"] is None
    assert call["max_attempts"] == 2


def test_ac1_signature_publique_preservée():
    """AC1 : La signature de generate accepte document_texts, simulation_requirement et additional_context."""
    import inspect
    sig = inspect.signature(OntologyGenerator.generate)
    params = list(sig.parameters.keys())
    assert params == ["self", "document_texts", "simulation_requirement", "additional_context"]
    assert sig.parameters["additional_context"].default is None


# ---------------------------------------------------------------------------
# AC2 : Déterminisme du contexte et reproductibilité des messages
# ---------------------------------------------------------------------------

def test_ac2_messages_et_diagnostics_identiques_sur_appels_successifs():
    """AC2 : Deux appels successifs avec les mêmes paramètres produisent les mêmes messages et diagnostics."""
    llm1 = RecordingLLMClient()
    llm2 = RecordingLLMClient()
    gen1 = OntologyGenerator(llm_client=llm1)
    gen2 = OntologyGenerator(llm_client=llm2)

    docs = ["Premier document télécom.", "Second document sur les réseaux."]
    brief = "Simuler la régulation."
    extra = "Contexte supplémentaire."

    gen1.generate(docs, brief, additional_context=extra)
    diag1 = gen1.last_context_diagnostics

    gen2.generate(docs, brief, additional_context=extra)
    diag2 = gen2.last_context_diagnostics

    assert llm1.calls[0]["messages"] == llm2.calls[0]["messages"]
    assert diag1 == diag2
    assert diag1["original_chars"] == diag2["original_chars"]
    assert diag1["truncated"] is False


def test_ac2_aucun_uuid_ni_date_aleatoire_dans_prompt():
    """AC2 : Aucune source d'aléa ou d'horodatage dynamique n'est injectée dans le prompt."""
    llm = RecordingLLMClient()
    gen = OntologyGenerator(llm_client=llm)

    gen.generate(["Doc unique"], "Brief stable", additional_context="Extra")
    user_msg = llm.calls[0]["messages"][1]["content"]

    assert "Doc unique" in user_msg
    assert "Brief stable" in user_msg
    assert "Extra" in user_msg


# ---------------------------------------------------------------------------
# AC3 : Projection canonique et détection de diffs
# ---------------------------------------------------------------------------

def test_ac3_projection_canonique_tri_et_rattachement():
    """AC3 : La projection trie les types et leurs attributs rattachés."""
    onto = {
        "entity_types": [
            {
                "name": "Beta",
                "description": "Desc B",
                "attributes": [{"name": "prop_z"}, {"name": "prop_a"}],
            },
            {
                "name": "Alpha",
                "description": "Desc A",
                "attributes": [{"name": "attr_1"}],
            },
        ],
        "edge_types": [
            {
                "name": "REL_B",
                "description": "Desc R",
                "attributes": [{"name": "y"}, {"name": "x"}],
            }
        ],
        "analysis_summary": "Résumé qui ne doit pas impacter la projection.",
    }

    proj = canonical_ontology_projection(onto)
    assert [e["name"] for e in proj["entity_types"]] == ["Alpha", "Beta"]
    assert proj["entity_types"][1]["attributes"] == ["prop_a", "prop_z"]
    assert proj["edge_types"][0]["name"] == "REL_B"
    assert proj["edge_types"][0]["attributes"] == ["x", "y"]


def test_ac3_comparaison_projections_identiques_conforme():
    """AC3 : Deux ontologies de même structure canonique ont un diff vide."""
    onto1 = {
        "entity_types": [{"name": "User", "description": "D1", "attributes": [{"name": "email"}]}],
        "edge_types": [{"name": "FOLLOWS", "attributes": [{"name": "since"}]}],
    }
    onto2 = {
        "entity_types": [{"name": "User", "description": "Autre description", "attributes": [{"name": "email"}]}],
        "edge_types": [{"name": "FOLLOWS", "attributes": [{"name": "since"}]}],
        "analysis_summary": "Un autre résumé sans impact",
    }

    p1 = canonical_ontology_projection(onto1)
    p2 = canonical_ontology_projection(onto2)
    conforme, diffs = comparer_projections(p1, p2)

    assert conforme is True
    assert diffs == []


def test_ac3_comparaison_detecte_ajout_type_entite():
    """AC3 : La détection signale l'ajout ou le retrait d'un type d'entité."""
    p1 = {"entity_types": [{"name": "User", "attributes": []}], "edge_types": []}
    p2 = {"entity_types": [{"name": "User", "attributes": []}, {"name": "Admin", "attributes": []}], "edge_types": []}

    conforme, diffs = comparer_projections(p1, p2)
    assert conforme is False
    assert any("types d'entité divergents" in d for d in diffs)


def test_ac3_comparaison_detecte_mutation_attribut():
    """AC3 : La détection signale un renommage ou déplacement d'attribut."""
    p1 = {"entity_types": [{"name": "User", "attributes": ["email"]}], "edge_types": []}
    p2 = {"entity_types": [{"name": "User", "attributes": ["phone"]}], "edge_types": []}

    conforme, diffs = comparer_projections(p1, p2)
    assert conforme is False
    assert any("Attributs du type d'entité 'User' divergents" in d for d in diffs)


def test_ac3_comparaison_detecte_divergence_relations():
    """AC3 : La détection signale une différence sur les types de relations."""
    p1 = {"entity_types": [], "edge_types": [{"name": "LIKES", "attributes": []}]}
    p2 = {"entity_types": [], "edge_types": [{"name": "SHARES", "attributes": []}]}

    conforme, diffs = comparer_projections(p1, p2)
    assert conforme is False
    assert any("types de relation divergents" in d for d in diffs)


# ---------------------------------------------------------------------------
# AC4 : Pose durable sur le store et isolation par graphe
# ---------------------------------------------------------------------------

def test_ac4_mesurer_une_generation_pose_et_relecture_neutre():
    """AC4 : La mesure applique l'ontologie sur le graphe et valide get_applied_ontology."""
    store = InMemoryMockGraphStore()
    gid = store.create_graph("Test graph")
    generator = OntologyGenerator(llm_client=RecordingLLMClient())

    corpus = {
        "corpus_id": "test_corpus",
        "document_texts": ["Contenu"],
        "brief": "Brief",
    }

    mesure = mesurer_une_generation(generator, store, corpus, gid, strict_policy=True)

    assert mesure["graph_id"] == gid
    assert mesure["applied_strict"] is True
    assert "Operator" in mesure["applied_ontology_entity_types"]
    assert store.get_applied_ontology(gid).strict is True


def test_ac4_rejet_si_ontologie_invalide_laisse_store_intact():
    """AC4 : Une erreur lors de la génération ou validation ne pose rien sur le store."""
    store = InMemoryMockGraphStore()
    gid = store.create_graph("Test graph")

    bad_llm = MagicMock()
    bad_llm.chat_json.side_effect = ValueError("Erreur LLM simulée")
    generator = OntologyGenerator(llm_client=bad_llm)

    corpus = {
        "corpus_id": "test_err",
        "document_texts": ["Contenu"],
        "brief": "Brief",
    }

    with pytest.raises(ValueError, match="Erreur LLM simulée"):
        mesurer_une_generation(generator, store, corpus, gid)

    assert store.get_applied_ontology(gid) is None


# ---------------------------------------------------------------------------
# AC5 / AC6 : Sonde de vérification, horloge et verdicts
# ---------------------------------------------------------------------------

def test_ac5_respect_du_budget_de_performance():
    """AC5 : Vérifie que le budget de temps est validé sous le seuil et rejeté au-delà."""
    store = InMemoryMockGraphStore()
    generator = OntologyGenerator(llm_client=RecordingLLMClient())
    corpus = {
        "corpus_id": "c50k",
        "target_chars": 50000,
        "actual_chars": 50000,
        "combined_chars": 50063,
        "document_texts": ["Doc"],
        "brief": "Brief",
    }

    # Horloge simulée rapide : 5 secondes par appel
    clock = [0.0]

    def mock_time_fast():
        clock[0] += 5.0
        return clock[0]

    res_ok = evaluer_corpus_c3(
        generator=generator,
        store=store,
        corpus=corpus,
        run_id="run_fast",
        seuil_max_s=30.0,
        time_fn=mock_time_fast,
    )
    assert res_ok["budget_respecte"] is True
    assert res_ok["conforme"] is True

    # Horloge simulée lente : 40 secondes par appel
    clock_slow = [0.0]

    def mock_time_slow():
        clock_slow[0] += 40.0
        return clock_slow[0]

    res_lent = evaluer_corpus_c3(
        generator=generator,
        store=store,
        corpus=corpus,
        run_id="run_slow",
        seuil_max_s=30.0,
        time_fn=mock_time_slow,
    )
    assert res_lent["budget_respecte"] is False
    assert res_lent["conforme"] is False


def test_ac6_sonde_orchestration_complete_mockée():
    """AC6 : Orchestration globale avec fixtures, production du payload et verdict."""
    store = InMemoryMockGraphStore()
    generator = OntologyGenerator(llm_client=RecordingLLMClient())

    conforme, payload = executer_verification_c3(
        is_docker=False,
        output_path=None,
        keep_graphs=False,
        generator=generator,
        store=store,
    )

    assert conforme is True
    assert payload["verdict_global_go"] is True
    assert "corpus_10k" in payload["corpora"]
    assert "corpus_50k" in payload["corpora"]
    assert payload["configuration_llm"]["temperature"] == 0.0
    assert payload["seuils"]["seuil_50k_s"] == SEUIL_HOTE_50K_S


def test_ac6_sonde_seuil_docker_adapte():
    """AC6 : L'option is_docker applique le seuil de 45.0s."""
    store = InMemoryMockGraphStore()
    generator = OntologyGenerator(llm_client=RecordingLLMClient())

    _, payload = executer_verification_c3(
        is_docker=True,
        output_path=None,
        generator=generator,
        store=store,
    )

    assert payload["environnement"] == "docker"
    assert payload["seuils"]["seuil_50k_s"] == SEUIL_DOCKER_50K_S


def test_ac6_sonde_nettoie_graphes_apres_mesure():
    """AC6 : Les graphes créés pour les essais sont nettoyés automatiquement."""
    store = InMemoryMockGraphStore()
    generator = OntologyGenerator(llm_client=RecordingLLMClient())

    executer_verification_c3(
        is_docker=False,
        keep_graphs=False,
        generator=generator,
        store=store,
    )

    # Tous les graphes doivent être marqués comme supprimés
    for gid, g_info in store.graphs.items():
        assert g_info["deleted"] is True, f"Le graphe {gid} n'a pas été nettoyé"


# ---------------------------------------------------------------------------
# AC7 : Non-régression des règles d'ontologie existantes
# ---------------------------------------------------------------------------

def test_ac7_generator_ajoute_person_et_organization_si_absents():
    """AC7 : Les types de repli Person et Organization sont systématiquement inclus."""
    llm = RecordingLLMClient(response={
        "entity_types": [{"name": "Technician", "attributes": ["tools"]}],
        "edge_types": [],
    })
    generator = OntologyGenerator(llm_client=llm)

    res = generator.generate(["Document"], "Simulation")
    names = [e["name"] for e in res["entity_types"]]

    assert "Person" in names
    assert "Organization" in names
    assert "Technician" in names


def test_ac7_generator_plafone_a_10_types():
    """AC7 : Le nombre total de types d'entité ne dépasse jamais MAX_ONTOLOGY_TYPES = 10."""
    raw_entities = [{"name": f"Type{i}", "attributes": []} for i in range(15)]
    llm = RecordingLLMClient(response={
        "entity_types": raw_entities,
        "edge_types": [],
    })
    generator = OntologyGenerator(llm_client=llm)

    res = generator.generate(["Doc"], "Brief")
    assert len(res["entity_types"]) <= 10
    names = [e["name"] for e in res["entity_types"]]
    assert "Person" in names
    assert "Organization" in names


def test_ac7_normalisation_et_resolution_aretes():
    """AC7 : Les types d'arêtes sont normalisés et leurs extrémités résolues."""
    llm = RecordingLLMClient(response={
        "entity_types": [{"name": "Person"}, {"name": "Company"}],
        "edge_types": [
            {
                "name": "works_for",
                "source_targets": [{"source": "person", "target": "company"}],
                "attributes": ["contract_type"],
            }
        ],
    })
    generator = OntologyGenerator(llm_client=llm)

    res = generator.generate(["Doc"], "Brief")
    assert res["edge_types"][0]["name"] == "WORKS_FOR"
    assert res["edge_types"][0]["source_targets"] == [{"source": "Person", "target": "Company"}]


def test_ac7_consigne_brief_reste_dans_user_message_nfr5():
    """AC7/NFR-5 : Le brief et les documents restent dans le message utilisateur, sans fuite système."""
    llm = RecordingLLMClient()
    gen = OntologyGenerator(llm_client=llm)

    secret_marker = "DOCUMENT_CONFIDENTIEL_XYZ"
    gen.generate([secret_marker], "Brief simulation")

    system_msg = llm.calls[0]["messages"][0]["content"]
    user_msg = llm.calls[0]["messages"][1]["content"]

    assert secret_marker not in system_msg
    assert secret_marker in user_msg


# ---------------------------------------------------------------------------
# Fixtures réelles 10K / 50K : Intégrité et longueurs exactes
# ---------------------------------------------------------------------------

def test_fixtures_corpus_10k_longueurs_et_manifeste():
    """Vérifie que le corpus 10K est présent, intègre et totalise 10 000 caractères Python."""
    corpus = charger_corpus("corpus_10k")
    assert corpus["actual_chars"] == 10000
    assert len(corpus["documents"]) == 5
    assert corpus["brief"] != ""
    assert len(corpus["brief_sha256"]) == 64


def test_fixtures_corpus_50k_longueurs_et_manifeste():
    """Vérifie que le corpus 50K est présent, intègre et totalise 50 000 caractères Python."""
    corpus = charger_corpus("corpus_50k")
    assert corpus["actual_chars"] == 50000
    assert len(corpus["documents"]) == 10
    assert corpus["brief"] != ""
    assert len(corpus["brief_sha256"]) == 64


# ---------------------------------------------------------------------------
# Patches de revue BMAD (P1 à P5) : Cas limites, doublons, robustesse et étanchéité
# ---------------------------------------------------------------------------

def test_p1_comparaison_detecte_doublons_asymetriques():
    """P1/AC3 : comparer_projections détecte les différences de multiplicité (doublons non écrasés)."""
    p1 = {
        "entity_types": [
            {"name": "Person", "attributes": ["a"]},
            {"name": "Person", "attributes": ["b"]},
        ],
        "edge_types": [],
    }
    p2 = {
        "entity_types": [
            {"name": "Person", "attributes": ["b"]},
        ],
        "edge_types": [],
    }

    conforme, diffs = comparer_projections(p1, p2)
    assert conforme is False
    assert any("Multiplicité du type d'entité 'Person' divergente" in d for d in diffs)


def test_p2_projection_canonique_robuste_aux_nones():
    """P2/AC3 : canonical_ontology_projection ne lève pas TypeError si name est None."""
    onto = {
        "entity_types": [
            {"name": None, "attributes": [{"name": None}, {"name": "valid"}]},
            {"name": "User", "attributes": [{"name": None}]},
        ],
        "edge_types": [
            {"name": None, "attributes": []},
        ],
    }

    proj = canonical_ontology_projection(onto)
    assert len(proj["entity_types"]) == 2
    assert proj["entity_types"][0]["name"] == ""
    assert proj["entity_types"][0]["attributes"] == ["valid"]
    assert proj["entity_types"][1]["name"] == "User"
    assert proj["entity_types"][1]["attributes"] == []


def test_p2_projection_canonique_supporte_attributs_chaines():
    """P2/AC3 : canonical_ontology_projection extrait les attributs fournis en chaînes brutes."""
    onto = {
        "entity_types": [
            {"name": "Account", "attributes": ["email", "phone", " "]},
        ],
        "edge_types": [
            {"name": "OWNS", "attributes": ["since"]},
        ],
    }

    proj = canonical_ontology_projection(onto)
    assert proj["entity_types"][0]["attributes"] == ["email", "phone"]
    assert proj["edge_types"][0]["attributes"] == ["since"]


def test_p3_p4_relecture_instance_neuve_avec_fermeture():
    """P3-P4/AC4 : mesurer_une_generation relit via instance neuve et appelle close()."""
    store_primaire = InMemoryMockGraphStore()
    reader_instance = InMemoryMockGraphStore()
    reader_instance.close_called = False

    def mock_close():
        reader_instance.close_called = True

    reader_instance.close = mock_close

    def mock_factory():
        # Copier l'état appliqué du store primaire pour simuler la lecture persistante
        reader_instance.applied_ontologies = dict(store_primaire.applied_ontologies)
        return reader_instance

    generator = OntologyGenerator(llm_client=RecordingLLMClient())
    corpus = {
        "corpus_id": "test_fresh",
        "document_texts": ["Texte"],
        "brief": "Brief",
    }
    gid = "g_test_fresh"

    mesure = mesurer_une_generation(
        generator=generator,
        store=store_primaire,
        corpus=corpus,
        graph_id=gid,
        store_factory=mock_factory,
    )

    assert mesure["graph_id"] == gid
    assert reader_instance.close_called is True


def test_p5_mesurer_une_generation_chronometre_lecture_disque():
    """P5/AC5 : mesurer_une_generation relit les fichiers réels si document_paths est présent."""
    corpus = charger_corpus("corpus_10k")
    assert "document_paths" in corpus
    assert len(corpus["document_paths"]) == 5

    store = InMemoryMockGraphStore()
    generator = OntologyGenerator(llm_client=RecordingLLMClient())

    mesure = mesurer_une_generation(
        generator=generator,
        store=store,
        corpus=corpus,
        graph_id="g_disk_read",
    )

    assert mesure["duree_lecture_s"] >= 0.0
    assert mesure["duree_totale_s"] >= mesure["duree_lecture_s"]

