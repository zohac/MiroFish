"""Tests unitaires hermétiques de `OntologyToPydantic` (story 007-1, AC3).

La factory est le seul endroit où un dict d'ontologie devient des classes
Pydantic. Sa validation se fait **en deux temps** — schéma, puis
constructibilité — et chaque temps a ses cas de refus. Ces tests exercent les
deux séparément : un refus au premier temps ne doit pas être confondu avec un
refus au second.

Aucun appel réseau, aucun `.env`, aucun serveur : la sortie est un dictionnaire
de classes, rien de plus.
"""

from __future__ import annotations

from typing import List, Optional

import pytest

from graphiti_core.nodes import EntityNode
from graphiti_core.utils.ontology_utils.entity_types_utils import validate_entity_types

from app.utils.graph_store.errors import (
    GraphValidationError,
    OntologyValidationError,
)
from app.utils.graph_store.ontology_pydantic import (
    PRIMITIVE_FIELD_TYPES,
    OntologyToPydantic,
)
from app.utils.ontology import MAX_ONTOLOGY_TYPES, RESERVED_ONTOLOGY_ATTRIBUTE_NAMES


def ontology_with(*entity_types, **kwargs):
    """Construit un dict d'ontologie minimal à partir de types d'entité."""
    payload = {"entity_types": list(entity_types)}
    payload.update(kwargs)
    return payload


# --- AC3(a) — ontologie valide minimale ---


def test_ontologie_valide_minimale_transuit_une_classe():
    """Un seul type d'entité produit une seule classe Pydantic indexée par son nom."""
    classes = OntologyToPydantic.from_dict(
        ontology_with({"name": "PersonEntity", "description": "Une personne"})
    )

    assert list(classes) == ["PersonEntity"]
    assert classes["PersonEntity"].__doc__ == "Une personne"


def test_ontologie_valide_minimale_expose_ses_attributs():
    """Les attributs déclarés deviennent des champs de la classe traduite."""
    classes = OntologyToPydantic.from_dict(
        ontology_with(
            {
                "name": "PersonEntity",
                "description": "Une personne",
                "attributes": [
                    {"name": "full_name", "type": "text", "description": "Nom complet"},
                    {"name": "birth_year", "type": "integer", "description": "Année"},
                ],
            }
        )
    )

    model = classes["PersonEntity"]
    assert set(model.model_fields) == {"full_name", "birth_year"}
    assert model(full_name="Ada", birth_year=1815).full_name == "Ada"


# --- AC3(b) et AC3(c) — la limite de 10 types ---


def test_ontologie_aux_dix_types_max_est_acceptee():
    """Dix types — la limite de `OntologyGenerator` — passent."""
    types = [{"name": f"Type{index}"} for index in range(MAX_ONTOLOGY_TYPES)]
    classes = OntologyToPydantic.from_dict(ontology_with(*types))

    assert len(classes) == MAX_ONTOLOGY_TYPES


def test_ontologie_au_dela_de_dix_types_est_refusee():
    """Onze types sont refusés, et le refus nomme la limite."""
    types = [{"name": f"Type{index}"} for index in range(MAX_ONTOLOGY_TYPES + 1)]

    with pytest.raises(OntologyValidationError) as exc_info:
        OntologyToPydantic.from_dict(ontology_with(*types))

    assert str(MAX_ONTOLOGY_TYPES) in str(exc_info.value)


def test_la_limite_de_types_est_celle_du_module_partage():
    """La limite vient de `utils.ontology`, pas d'un dix en dur dans la factory."""
    assert MAX_ONTOLOGY_TYPES == 10


# --- AC3(d) — champ non primitif sans référence déclarée ---


def test_champ_non_primitif_sans_reference_est_refuse():
    """Un type déclaré qui n'est ni primitif ni type d'entité est refusé."""
    with pytest.raises(OntologyValidationError) as exc_info:
        OntologyToPydantic.from_dict(
            ontology_with(
                {
                    "name": "PersonEntity",
                    "attributes": [{"name": "tags", "type": "List[Any]"}],
                }
            )
        )

    assert "List[Any]" in str(exc_info.value)


def test_type_primitif_alias_est_traduit():
    """Les alias textuels émis par un LLM sont traduits en annotations Pydantic."""
    classes = OntologyToPydantic.from_dict(
        ontology_with(
            {
                "name": "Decision",
                "attributes": [
                    {"name": "year", "type": "integer"},
                    {"name": "weight", "type": "number"},
                    {"name": "binding", "type": "boolean"},
                    {"name": "refs", "type": "list"},
                ],
            }
        )
    )

    fields = classes["Decision"].model_fields
    assert fields["year"].annotation == Optional[int]
    assert fields["weight"].annotation == Optional[float]
    assert fields["binding"].annotation == Optional[bool]
    assert fields["refs"].annotation == Optional[List[str]]


def test_attribut_sans_type_declare_devient_texte():
    """Sans type déclaré, l'attribut est un texte — comme le fait déjà le générateur."""
    classes = OntologyToPydantic.from_dict(
        ontology_with({"name": "Decision", "attributes": [{"name": "reference"}]})
    )

    assert classes["Decision"].model_fields["reference"].annotation == Optional[str]


# --- AC3(e) — références entre types, et cycle ---


def test_reference_vers_un_type_declare_est_acceptee():
    """Un attribut qui référence un type d'entité est aplati en nom, et dit pourquoi."""
    classes = OntologyToPydantic.from_dict(
        ontology_with(
            {"name": "PersonEntity"},
            {"name": "CompanyEntity", "attributes": [{"name": "employer", "type": "PersonEntity"}]},
        )
    )

    field = classes["CompanyEntity"].model_fields["employer"]
    assert field.annotation == Optional[str]
    assert "PersonEntity" in (field.description or "")


def test_cycle_de_references_entre_types_est_refuse():
    """Deux types qui se référencent mutuellement forment un cycle, et il est nommé."""
    with pytest.raises(OntologyValidationError) as exc_info:
        OntologyToPydantic.from_dict(
            ontology_with(
                {"name": "Alpha", "attributes": [{"name": "peer", "type": "Beta"}]},
                {"name": "Beta", "attributes": [{"name": "peer", "type": "Alpha"}]},
            )
        )

    assert "Cycle de références" in str(exc_info.value)
    assert "Alpha" in str(exc_info.value)
    assert "Beta" in str(exc_info.value)


def test_cycle_de_trois_types_est_refuse():
    """Le cycle est détecté au-delà de deux types aussi."""
    with pytest.raises(OntologyValidationError) as exc_info:
        OntologyToPydantic.from_dict(
            ontology_with(
                {"name": "Alpha", "attributes": [{"name": "next", "type": "Beta"}]},
                {"name": "Beta", "attributes": [{"name": "next", "type": "Gamma"}]},
                {"name": "Gamma", "attributes": [{"name": "next", "type": "Alpha"}]},
            )
        )

    assert "Cycle de références" in str(exc_info.value)


def test_reference_en_etoile_n_est_pas_un_cycle():
    """Deux types qui référencent le même tiers ne forment pas un cycle."""
    classes = OntologyToPydantic.from_dict(
        ontology_with(
            {"name": "PersonEntity", "attributes": [{"name": "employer", "type": "CompanyEntity"}]},
            {"name": "CustomerEntity", "attributes": [{"name": "employer", "type": "CompanyEntity"}]},
            {"name": "CompanyEntity"},
        )
    )

    assert len(classes) == 3


# --- AC3(g) — constructibilité : le refus que le schéma ne peut pas voir ---


def test_classe_non_constructible_est_refusee():
    """`model_config` passe le schéma et casse la construction : le refus vient du second temps."""
    with pytest.raises(OntologyValidationError) as exc_info:
        OntologyToPydantic.from_dict(
            ontology_with(
                {
                    "name": "PersonEntity",
                    "attributes": [{"name": "model_config", "type": "text"}],
                }
            )
        )

    assert "PersonEntity" in str(exc_info.value)
    assert "constructible" in str(exc_info.value)


def test_le_refus_de_constructibilite_survit_a_un_autre_type_valide():
    """Le refus vise le type fautif, pas l'ontologie entière."""
    with pytest.raises(OntologyValidationError) as exc_info:
        OntologyToPydantic.from_dict(
            ontology_with(
                {"name": "ValidType"},
                {"name": "BrokenType", "attributes": [{"name": "model_config"}]},
            )
        )

    assert "BrokenType" in str(exc_info.value)
    assert "ValidType" not in str(exc_info.value)


# --- Noms : ils deviennent des labels Cypher et des champs Pydantic ---


def test_nom_de_type_invalide_comme_label_cypher_est_refuse():
    """Un espace dans un nom de type produirait une erreur Cypher en aval."""
    with pytest.raises(OntologyValidationError) as exc_info:
        OntologyToPydantic.from_dict(ontology_with({"name": "Media Organization"}))

    assert "Media Organization" in str(exc_info.value)
    assert "label Cypher" in str(exc_info.value)


def test_nom_de_type_commencant_par_un_chiffre_est_refuse():
    """Un label Cypher ne commence pas par un chiffre."""
    with pytest.raises(OntologyValidationError):
        OntologyToPydantic.from_dict(ontology_with({"name": "2Organisations"}))


def test_nom_d_attribut_invalide_est_refuse():
    """Un nom d'attribut non identifiant produirait une classe Pydantic refusée."""
    with pytest.raises(OntologyValidationError) as exc_info:
        OntologyToPydantic.from_dict(
            ontology_with(
                {"name": "PersonEntity", "attributes": [{"name": "full name"}]}
            )
        )

    assert "full name" in str(exc_info.value)


def test_nom_reserve_est_prefixe_pour_quitter_entitynode():
    """Un attribut nommé comme une propriété gérée est préfixé, pas refusé."""
    classes = OntologyToPydantic.from_dict(
        ontology_with(
            {
                "name": "PersonEntity",
                "attributes": [{"name": "summary"}, {"name": "labels"}],
            }
        )
    )

    assert set(classes["PersonEntity"].model_fields) == {
        "entity_summary",
        "entity_labels",
    }


def test_aucun_champ_genere_ne_collisionne_avec_entitynode():
    """Garde-fou : la liste réservée couvre `EntityNode.model_fields`, mesuré.

    Sans ce test, ajouter un nom à la liste réservée pourrait laisser un champ
    en collision, et Graphiti refuserait la classe au moment de l'extraction,
    loin de sa cause.
    """
    assert set(EntityNode.model_fields) <= RESERVED_ONTOLOGY_ATTRIBUTE_NAMES


def test_ontologie_generee_passe_la_validation_graphiti():
    """Garde-fou : la traduction produit un `entity_types` que Graphiti accepte.

    On appelle le validateur réel de `graphiti_core` plutôt que de le simuler :
    c'est lui qui refusera une classe dont un champ entre en collision avec
    `EntityNode`.
    """
    attributes = [
        {"name": name} for name in sorted(RESERVED_ONTOLOGY_ATTRIBUTE_NAMES)
    ] + [{"name": "extra"}]
    classes = OntologyToPydantic.from_dict(
        ontology_with({"name": "PersonEntity", "attributes": attributes})
    )

    assert validate_entity_types(classes) is True


# --- Formes d'ontologie réellement produites par OntologyGenerator ---


def test_type_entite_en_chaine_simple_est_accepte():
    """Une entrée en chaîne est une forme que le générateur produit déjà."""
    classes = OntologyToPydantic.from_dict(ontology_with("Person", "Organization"))

    assert sorted(classes) == ["Organization", "Person"]


def test_description_par_defaut_quand_absente():
    """Un type sans description reçoit une description qui le nomme."""
    classes = OntologyToPydantic.from_dict(ontology_with({"name": "MediaOrganization"}))

    assert "MediaOrganization" in (classes["MediaOrganization"].__doc__ or "")


def test_entree_en_chaine_simple_est_refusee():
    """Le contrat est un dictionnaire : une chaîne est refusée."""
    with pytest.raises(OntologyValidationError):
        OntologyToPydantic.from_dict("PersonEntity")


def test_entite_sans_nom_exploitable_est_refusee():
    """Un type sans nom ne peut pas devenir un label : il est refusé."""
    with pytest.raises(OntologyValidationError) as exc_info:
        OntologyToPydantic.from_dict(ontology_with({"description": "sans nom"}))

    assert "sans nom exploitable" in str(exc_info.value)


def test_type_entite_non_string_non_dictionnaire_est_refuse():
    """Une entrée parasite dans `entity_types` est refusée, pas ignorée."""
    with pytest.raises(OntologyValidationError) as exc_info:
        OntologyToPydantic.from_dict(ontology_with({"name": "PersonEntity"}, 42))

    assert "42" in str(exc_info.value)


def test_nom_de_type_duplique_est_refuse():
    """Deux types de même nom produiraient un label Cypher ambigu."""
    with pytest.raises(OntologyValidationError) as exc_info:
        OntologyToPydantic.from_dict(ontology_with("Person", "Person"))

    assert "Person" in str(exc_info.value)


def test_ontologie_sans_type_exploitable_est_refusee():
    """Une ontologie vide ne « poserait » rien : elle est refusée."""
    with pytest.raises(OntologyValidationError) as exc_info:
        OntologyToPydantic.from_dict({"entity_types": []})

    assert "aucun type d'entité ni type de relation exploitable" in str(exc_info.value)


def test_ontologie_de_relations_seules_est_acceptee():
    """Déclarer des relations sans entité reste une ontologie valide : le graphe
    sera simplement non typé, et les relations seront transmises à part."""
    classes = OntologyToPydantic.from_dict(
        {"entity_types": [], "edge_types": [{"name": "RELATED_TO"}]}
    )

    assert classes == {}


def test_les_relations_seules_sont_bien_traduites():
    relation = OntologyToPydantic.edge_types_from_dict(
        {"entity_types": [], "edge_types": [{"name": "RELATED_TO", "attributes": ["reason"]}]}
    )

    assert list(relation) == ["RELATED_TO"]
    assert "reason" in relation["RELATED_TO"].model_fields


@pytest.mark.parametrize("nom", ["Entity", "Node", "Episodic", "Community"])
def test_un_nom_reserve_par_le_moteur_est_refuse(nom):
    """Ces labels appartiennent au moteur : un nœud qui les porte serait relu
    comme un nœud interne, et le typage métier deviendrait faux."""
    with pytest.raises(OntologyValidationError) as exc_info:
        OntologyToPydantic.from_dict({"entity_types": [{"name": nom}]})

    assert "réservé" in str(exc_info.value)


@pytest.mark.parametrize("nom_relation", ["Entity", "Episodic"])
def test_un_nom_de_relation_reserve_est_refuse(nom_relation):
    """La même protection s'applique aux relations : un nom de relation interne
    produirait des arêtes illisibles."""
    with pytest.raises(OntologyValidationError):
        OntologyToPydantic.edge_types_from_dict(
            {"entity_types": [{"name": "Person"}], "edge_types": [{"name": nom_relation}]}
        )


def test_un_type_d_attribut_inconnu_du_llm_est_traite_comme_texte():
    """`enum`, `category`, `text[]` sont produits par le générateur : les refuser
    ferait échouer toute une construction de graphe pour un mot."""
    classes = OntologyToPydantic.from_dict(
        ontology_with(
            {
                "name": "Decision",
                "attributes": [
                    {"name": "category", "type": "enum"},
                    {"name": "tags", "type": "text[]"},
                ],
            }
        )
    )

    assert classes["Decision"].model_fields["category"].annotation == Optional[str]
    assert classes["Decision"].model_fields["tags"].annotation == Optional[List[str]]


@pytest.mark.parametrize("type_declare", ["List[Any]", "Dict[str, int]", "set[str]", "Union[int, str]"])
def test_un_conteneur_generique_reste_refuse(type_declare):
    """Un nœud n'accepte qu'un scalaire ou un tableau de scalaires : la rigueur
    sur les conteneurs génériques, c'est la moitié utile de la règle."""
    with pytest.raises(OntologyValidationError) as exc_info:
        OntologyToPydantic.from_dict(
            ontology_with(
                {"name": "Decision", "attributes": [{"name": "valeur", "type": type_declare}]}
            )
        )

    assert "conteneur générique" in str(exc_info.value)


def test_entity_types_non_liste_est_refuse():
    """Un `entity_types` de mauvaise forme est refusé avant toute itération."""
    with pytest.raises(OntologyValidationError) as exc_info:
        OntologyToPydantic.from_dict({"entity_types": {"name": "Person"}})

    assert "entity_types" in str(exc_info.value)


def test_attributs_plafonnes_par_type():
    """Un type qui déclare plus de dix attributs est tronqué, comme chez Zep."""
    attributes = [{"name": f"field_{index}"} for index in range(14)]
    classes = OntologyToPydantic.from_dict(
        ontology_with({"name": "PersonEntity", "attributes": attributes})
    )

    assert len(classes["PersonEntity"].model_fields) == 10


def test_attribut_reserve_et_son_prefixe_ne_collident_pas():
    """Préfixer un nom réservé ne doit pas produire deux fois le même champ."""
    with pytest.raises(OntologyValidationError) as exc_info:
        OntologyToPydantic.from_dict(
            ontology_with(
                {
                    "name": "PersonEntity",
                    "attributes": [{"name": "summary"}, {"name": "entity_summary"}],
                }
            )
        )

    assert "entity_summary" in str(exc_info.value)


def test_les_alias_primitifs_couvrent_les_types_de_donnees_usuels():
    """Garde-fou : la table d'alias ne perd pas un type de donnée courant."""
    for alias in ("text", "string", "integer", "number", "boolean", "list", "date"):
        assert alias in PRIMITIVE_FIELD_TYPES


# --- Hiérarchie d'exceptions ---


def test_ontology_validation_error_est_une_graph_validation_error():
    """Un appelant qui ignore l'ontologie attrape la même exception qu'une entrée invalide."""
    assert issubclass(OntologyValidationError, GraphValidationError)


def test_ontology_validation_error_est_une_graph_store_error():
    """Un appelant qui n'attrape que `GraphStoreError` voit aussi le refus."""
    from app.utils.graph_store.errors import GraphStoreError

    assert issubclass(OntologyValidationError, GraphStoreError)