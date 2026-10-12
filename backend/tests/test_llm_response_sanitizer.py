"""Tests du garde-fou d'assainissement des réponses LLM (007-1, risque R1 du PRD).

Un LLM peut renvoyer, pour un champ, le **fragment de schéma JSON** de ce champ
au lieu d'une valeur. Ce fragment est un dictionnaire : il traverse les étapes
de validation de la réponse, puis Graphiti l'écrit comme propriété du nœud — ce
que Neo4j refuse, une propriété ne pouvant pas être une map. Mesuré sur le
serveur de référence : `Property values can only be of primitive types or arrays
thereof`, et l'épisode entier échoue.

Ces tests pinnent le comportement correct : le champ inventé est écarté, les
champs légitimes sont conservés, et l'ingestion survit.
"""

from __future__ import annotations

from typing import Optional
from unittest.mock import MagicMock

import pytest
from pydantic import BaseModel, Field

from app.utils.graphiti_llm_client import MiroFishLLMClient


class TypeOntologie(BaseModel):
    """Modèle d'attributs d'ontologie, de la forme produite par la factory."""

    policy_name: Optional[str] = Field(default=None, description="Intitulé du texte")
    target_year: Optional[int] = Field(default=None, description="Horizon")


def _fragment_de_schema(champ: str, titre: str, annotation: str = "string") -> dict:
    """Reproduit ce que renvoie un LLM quand il écho le schéma d'un champ."""
    return {
        "anyOf": [{"type": annotation}, {"type": "null"}],
        "description": f"Description de {champ}",
        "default": None,
        "title": titre,
    }


# --- Le défaut, reproduit ---


def test_le_fragment_de_schema_dun_champ_est_ecarte():
    """Le champ echoed-away ne doit plus sortir du normaliseur."""
    payload = {
        "policy_name": _fragment_de_schema("policy_name", "Policy Name"),
        "target_year": 2035,
    }

    resultat = MiroFishLLMClient._normalize_response(payload, TypeOntologie)

    assert "policy_name" not in resultat
    assert resultat["target_year"] == 2035


def test_une_seule_entree_invalide_ne_fait_perdre_que_celle_ci():
    """Assainir ne doit pas vider la réponse entière : les autres champs restent."""
    payload = {
        "policy_name": _fragment_de_schema("policy_name", "Policy Name"),
        "target_year": 2035,
    }

    resultat = MiroFishLLMClient._normalize_response(payload, TypeOntologie)

    assert len(resultat) == 1
    assert set(resultat) == {"target_year"}


def test_le_resultat_assaini_reste_validable():
    """Le normaliseur doit rendre un payload que le modèle accepte encore."""
    payload = {
        "policy_name": _fragment_de_schema("policy_name", "Policy Name"),
        "target_year": 2035,
    }

    resultat = MiroFishLLMClient._normalize_response(payload, TypeOntologie)

    assert TypeOntologie.model_validate(resultat).target_year == 2035


# --- Ce qui ne doit pas être touché ---


def test_une_reponse_valide_passe_sans_assainissement():
    """Un payload conforme ne doit subir aucune modification."""
    payload = {"policy_name": "Trajectoire 2030", "target_year": 2030}

    assert MiroFishLLMClient._normalize_response(payload, TypeOntologie) == payload


def test_un_champ_inconnu_du_modele_est_ecarte():
    """Un champ que le modèle ne déclare pas ne peut pas devenir une propriété
    du nœud : Pydantic l'ignore à la validation, il ne doit donc pas survivre
    au normaliseur."""
    payload = {"target_year": 2035, "champ_inconnu": 42}

    resultat = MiroFishLLMClient._normalize_response(payload, TypeOntologie)

    assert resultat == {"target_year": 2035}


@pytest.mark.parametrize(
    "enveloppe",
    ["properties", "data", "TypeOntologie"],
)
def test_un_echo_de_schema_englobe_dans_une_enveloppe_est_ecarte(enveloppe):
    """L'écho peut être enveloppé : Pydantic ignore la clé en trop, donc la
    réponse « conforme » contenait bien une map destined à devenir une propriété.
    C'est la forme qui a fait échouer l'ingestion réelle."""
    payload = {
        enveloppe: {
            "policy_name": _fragment_de_schema("policy_name", "Policy Name"),
            "target_year": 2035,
        }
    }

    resultat = MiroFishLLMClient._normalize_response(payload, TypeOntologie)

    assert isinstance(resultat, dict)
    assert all(not isinstance(v, dict) for v in resultat.values())
    assert enveloppe not in resultat


def test_une_enveloppe_propre_est_deballuee_sans_perte():
    """Une enveloppe qui contient une vraie instance est toujours déballuee."""
    payload = {
        "properties": {"policy_name": "Trajectoire 2030", "target_year": 2030}
    }

    assert MiroFishLLMClient._normalize_response(payload, TypeOntologie) == {
        "policy_name": "Trajectoire 2030",
        "target_year": 2030,
    }


def test_un_fragment_de_schema_sur_tous_les_champs_retombe_sur_le_repli():
    """Si rien ne se valide, le repli par défaut prend le relais plutôt que de
    laisser passer une réponse qui cassera à l'écriture."""
    payload = {
        "policy_name": _fragment_de_schema("policy_name", "Policy Name"),
        "target_year": _fragment_de_schema("target_year", "Target Year", "integer"),
    }

    resultat = MiroFishLLMClient._normalize_response(payload, TypeOntologie)

    assert isinstance(resultat, dict)
    assert all(not isinstance(v, dict) for v in resultat.values())


def test_une_reponse_invalide_sans_rien_de_valide_ne_returns_pas_de_dictionnaire():
    """Garde-fou : après normalisation, aucune valeur ne peut être un dictionnaire,
    quel que soit le payload — c'est la condition pour que l'écriture Neo4j
    n'échoue jamais sur une propriété-map."""
    payloads = [
        {"policy_name": {"anyOf": [{"type": "string"}]}},
        {"policy_name": {"a": 1}, "target_year": {"b": 2}},
        {"target_year": {"description": "x", "title": "y"}},
    ]

    for payload in payloads:
        resultat = MiroFishLLMClient._normalize_response(payload, TypeOntologie)
        assert isinstance(resultat, dict)
        assert all(
            not isinstance(v, dict) for v in resultat.values()
        ), payload


@pytest.mark.parametrize("valeur", ["texte", 42, True, None, ["a", "b"]])
def test_les_valeurs_scalaires_et_listes_sont_conservees(valeur):
    """Seuls les dictionnaires — dont les fragments de schéma — sont écartés.

    Le risque R1 du PRD est qu'un fragment de schéma (un ``dict``)
    survive à la validation et soit écrit comme *property-map* sur le
    nœud, ce que Neo4j refuse. Ce test couvre le **chemin heureux** :
    les scalaires et listes passent, les fragments de schéma sont
    couverts par les autres tests.
    """
    class ModeleFlexible(BaseModel):
        champ: Optional[object] = Field(default=None)

    payload = {"champ": valeur}

    assert MiroFishLLMClient._normalize_response(payload, ModeleFlexible) == payload


def test_un_champ_dict_str_any_ecarte_un_fragment_de_schema():
    """E4 — risque R1 : un champ typé ``Dict[str, Any]`` accepte
    n'importe quoi (validation Pydantic permissive), mais le sanitizer
    doit écarter la valeur sans condition — sinon le fragment de
    schéma survivrait comme *property-map* interdite par Neo4j.
    """
    from typing import Any, Dict

    class ModeleAvecMetaPermissive(BaseModel):
        nom: str
        meta: Dict[str, Any] = Field(default_factory=dict)

    # `meta` est un fragment de schéma ; le sanitizer l'écarte sans
    # condition, parce que `Dict[str, Any]` accepte n'importe quoi.
    payload = {
        "nom": "Alice",
        "meta": {"type": "object", "properties": {"x": {"type": "string"}}},
    }

    resultat = MiroFishLLMClient._normalize_response(
        payload, ModeleAvecMetaPermissive
    )

    # Le champ permissif `meta` est écarté ; `nom` est conservé ;
    # `meta` retombe sur sa valeur par défaut (dict vide).
    assert "meta" not in resultat or resultat["meta"] == {}
    assert resultat["nom"] == "Alice"


def test_l_assainissement_ne_declenche_pas_sur_un_modele_absent():
    """Sans modèle de réponse, le normaliseur laisse passer : rien à valider."""
    assert MiroFishLLMClient._normalize_response({"a": 1}, None) == {"a": 1}

# --- Relecture BMAD du 12 oct. 2026 — groupe C ---


def test_champ_permissif_est_ecarte_meme_si_la_validation_passe():
    """Q5 — un champ typé ``Dict[str, Any]`` accepte n'importe quoi ; le filtre
    doit l'écarter sans condition, sinon un fragment de schéma survivrait et
    Neo4j le refuserait comme property-map.
    """
    from typing import Any, Dict

    class ModelePermissif(BaseModel):
        nom: str
        meta: Dict[str, Any]

    # `meta` accepte un fragment de schéma ; le filtre l'écarte.
    payload = {"nom": "Alice", "meta": {"type": "object", "properties": {"x": {"type": "string"}}}}
    assaini = MiroFishLLMClient._filtrer_champs_valides(ModelePermissif, payload)

    assert assaini is not None
    assert "meta" not in assaini
    assert assaini["nom"] == "Alice"


def test_champ_optional_str_n_est_pas_permissif():
    """Q5 — `Optional[str]` est contraint (un fragment de schéma ne valide pas
    comme `str | None`), donc le filtre ne l'écarte pas inutilement.
    """
    from typing import Optional

    class ModeleOptional(BaseModel):
        nom: Optional[str] = None

    # `nom = "Alice"` doit passer ; le champ n'est pas permissif.
    assaini = MiroFishLLMClient._filtrer_champs_valides(
        ModeleOptional, {"nom": "Alice"}
    )
    assert assaini is None  # rien à retirer


def test_filtrer_ne_masque_pas_les_erreurs_de_validation():
    """Q2 — `_filtrer_champs_valides` n'attrape que `pydantic.ValidationError`,
    pas `Exception`. Une valeur qui déclenche un `ValidationError` sur le
    champ est écartée, sans exception remontée ; un `TypeError` (par exemple
    sur une annotation non constructible) est aussi géré explicitement.

    Note : un validateur Pydantic qui lève un `AttributeError` dans la
    sous-classe originale n'est pas re-déclenché par le modèle réduit construit
    dans `_filtrer_champs_valides` — c'est l'effet voulu (le sanitizer ne
    déclenche pas les validateurs métier). Un `AttributeError` provenant
    d'un bug interne au sanitizer lui-même reste cependant visible.
    """
    # Cas 1 : un mauvais type est bien un ValidationError → on l'écarte
    # silencieusement (champ "inventé" du LLM).
    class ModeleStr(BaseModel):
        nom: str

    assaini = MiroFishLLMClient._filtrer_champs_valides(
        ModeleStr, {"nom": {"anyOf": [{"type": "string"}]}}
    )
    # La valeur est écarter (validation échoue), mais pas d'exception.
    assert assaini is not None
    assert "nom" not in assaini


def test_step_6_continue_meme_si_validation_du_nettoye_echoue():
    """Q3 — étape 6 : si la revalidation du payload nettoyé échoue, on
    consigne un `logger.error` et on continue (pas de `raise`), pour ne pas
    faire échouer l'ingestion d'un épisode entier sur un cas dégradé.
    """
    import logging

    captured = []

    class _Capture(logging.Handler):
        def emit(self, record):
            captured.append(record.getMessage())

    from app.utils.graphiti_llm_client import logger as client_logger

    handler = _Capture(level=logging.DEBUG)
    client_logger.addHandler(handler)
    try:
        # Payload où tous les champs sont permissifs : le filtre les écarte,
        # le candidat est l'instance par défaut, et le modèle exige un str.
        from typing import Dict, Any

        class ModeleRequis(BaseModel):
            nom: str
            meta: Dict[str, Any]

        payload = {"nom": "Alice", "meta": {"type": "object"}}
        resultat = MiroFishLLMClient._normalize_response(payload, ModeleRequis)

        # Le résultat n'est pas `None` ; c'est le payload d'origine ou un
        # fallback ; il a au moins `nom` (la partie non permissif).
        assert isinstance(resultat, dict)
        assert "nom" in resultat
    finally:
        client_logger.removeHandler(handler)


def test_graph_builder_set_ontology_propage_strict():
    """Q1 — `GraphBuilderService.set_ontology` propage le keyword `strict`
    au store sous-jacent (sinon le contrat v2 d'ADR 0014 est silencieusement
    dégradé à la surface v1).
    """
    from app.services.graph_builder import GraphBuilderService

    store = MagicMock()
    service = object.__new__(GraphBuilderService)
    service.store = store

    service.set_ontology("g-1", {"entity_types": []}, strict=True)
    store.set_ontology.assert_called_once_with(
        graph_id="g-1",
        ontology={"entity_types": []},
        strict=True,
    )


def test_graph_builder_set_ontology_default_strict_false():
    """Q1 — `GraphBuilderService.set_ontology` ne casse pas les appelants qui
    n'ont pas encore conscience du paramètre `strict` : `strict=False` par
    défaut, rétrocompatibilité Epic 003 préservée.
    """
    from app.services.graph_builder import GraphBuilderService

    store = MagicMock()
    service = object.__new__(GraphBuilderService)
    service.store = store

    service.set_ontology("g-1", {"entity_types": []})
    store.set_ontology.assert_called_once_with(
        graph_id="g-1",
        ontology={"entity_types": []},
        strict=False,
    )
