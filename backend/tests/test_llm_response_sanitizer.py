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
    """Seuls les dictionnaires — dont les fragments de schéma — sont écartés."""
    class ModeleFlexible(BaseModel):
        champ: Optional[object] = Field(default=None)

    payload = {"champ": valeur}

    assert MiroFishLLMClient._normalize_response(payload, ModeleFlexible) == payload


def test_l_assainissement_ne_declenche_pas_sur_un_modele_absent():
    """Sans modèle de réponse, le normaliseur laisse passer : rien à valider."""
    assert MiroFishLLMClient._normalize_response({"a": 1}, None) == {"a": 1}