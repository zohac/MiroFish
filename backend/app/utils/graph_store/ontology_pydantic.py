"""Traduction d'un dict d'ontologie en classes Pydantic (ADR 0014 §4).

`OntologyGenerator` produit un dict d'ontologie ; Graphiti consomme des
**classes** Pydantic dont le nom devient le label Cypher du nœud extrait
(`node_operations.py` : `labels = list({'Entity', str(entity_type_name)})`).
Cette factory est le seul endroit où le dict devient des classes : les deux
stores ne partagent pas la même cible, donc ils ne partagent pas la même
traduction, mais ils partagent sa **validation**.

Validation en deux temps, dans cet ordre :

1. **schéma** — nom de type identifiant (le nom est un label Cypher), au plus
   `MAX_ONTOLOGY_TYPES` types, attributs nommés et typés primitivement ou par
   référence à un type déclaré, sans cycle de références ;
2. **constructibilité** — un stub de chaque classe est instancié, et l'éventuelle
   `pydantic.ValidationError` devient un refus.

Un refus lève `OntologyValidationError`, sous-classe de `GraphValidationError`.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Dict, List, Optional, Set, Tuple

from pydantic import BaseModel, Field, ValidationError

from ..logger import get_logger
from ..ontology import (
    MAX_ONTOLOGY_ATTRIBUTES,
    MAX_ONTOLOGY_TYPES,
    is_valid_ontology_name,
    normalize_ontology_attributes,
    safe_ontology_attribute_name,
)
from .errors import OntologyValidationError

logger = get_logger("mirofish.graph_store.ontology")


#: Types Python acceptables derrière les noms de type émis par un LLM. Un type
#: qui n'est ni dans cette table ni le nom d'un `entity_type` déclaré est refusé.
PRIMITIVE_FIELD_TYPES: Dict[str, Any] = {
    "text": str,
    "string": str,
    "str": str,
    "varchar": str,
    "char": str,
    "date": str,
    "datetime": str,
    "url": str,
    "integer": int,
    "int": int,
    "number": float,
    "float": float,
    "double": float,
    "boolean": bool,
    "bool": bool,
    "list": List[str],
    "list[str]": List[str],
    "array": List[str],
    "array[str]": List[str],
}

#: Noms de types que le moteur de graphe réserve pour ses nœuds internes.
#: Un type d'entité portant un de ces noms poserait sur chaque nœud extrait un
#: label indistinguable d'un `:Episodic` ou d'un `:Community` : la relecture
#: ascendrait alors des nœuds d'entité comme des épisodes, et le typage métier
#: deviendrait faux. Ils sont refusés, pas renommés — un nom d'ontologie est un
#: choix explicite du domaine, pas une coquille à corriger en silence.
#:
#: **Uniformité délibérée sur les types d'arête.** Cypher distingue labels de
#: nœuds et types de relations dans des namespaces séparés, donc `[:Episodic]`
#: est légal. Le validateur applique pourtant le même ensemble aux deux
#: (`valider_nom_de_type` est appelé avec `genre="type"` puis
#: `genre="relation"`). C'est une sur-restriction commode pour la mémoisation,
#: sans cas d'ontologie réel qui morde — un nom d'arête comme « Episodic »
#: n'a pas de sens métier. La relecture BMAD du 12 oct. 2026 a tranché : on
#: garde l'uniformité, plutôt que de splitter en deux sets.
RESERVED_ONTOLOGY_TYPE_NAMES = frozenset({"Entity", "Node", "Episodic", "Community"})

#: Un type déclaré qui est un **conteneur générique** (`List[Any]`, `Dict[str, int]`,
#: `Union[...]`) ne peut pas devenir un champ de nœud : Neo4j n'accepte qu'un
#: scalaire ou un tableau, et Graphiti écrit chaque attribut comme une propriété.
_GENERIC_TYPE_PATTERN = re.compile(r"^(list|set|tuple|dict|frozenset|union|optional)\[")
_SIMPLE_TYPE_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


@dataclass(frozen=True)
class ResolvedField:
    """Un attribut d'ontologie résolu en champ Pydantic."""

    name: str
    annotation: Any
    description: str
    #: Nom du type d'entité référencé, ou ``None`` pour un champ primitif.
    reference: Optional[str] = None


@dataclass(frozen=True)
class ResolvedEntityType:
    """Un type d'entité résolu, prêt à être traduit en classe Pydantic."""

    name: str
    description: str
    fields: Tuple[ResolvedField, ...]


def _describe(value: Any) -> str:
    """Rend une valeur illisible dans un message d'erreur, sans jamais l'invoquer."""
    return f"{type(value).__name__}"


def valider_nom_de_type(nom: str, genre: str) -> None:
    """Valide un nom de type d'ontologie, pour les **deux** implémentations.

    Une seule implémentation : c'est la seule façon que Zep et Graphiti refusent
    le même nom pour la même raison. Un nom refusé chez l'un produirait chez
    l'autre une erreur de syntaxe Cypher ou une relecture fausse, en aval et
    sans lien visible avec sa cause.
    """
    if not is_valid_ontology_name(nom):
        raise OntologyValidationError(
            f"Le nom de {genre} '{nom}' n'est pas un identifiant valide : il "
            "devient un label Cypher, donc lettres, chiffres et underscore "
            "uniquement, sans commencer par un chiffre"
        )
    if nom in RESERVED_ONTOLOGY_TYPE_NAMES:
        raise OntologyValidationError(
            f"Le nom de {genre} '{nom}' est réservé par le moteur de graphe : un "
            "nœud portant ce label serait relu comme un nœud interne "
            f"({', '.join(sorted(RESERVED_ONTOLOGY_TYPE_NAMES))})"
        )


def _coerce_declared_type(raw_type: Any) -> Optional[str]:
    """Normalise le type déclaré d'un attribut en chaîne, ou ``None``."""
    if isinstance(raw_type, str):
        cleaned = raw_type.strip()
        return cleaned or None
    return None


def _resolve_attribute_annotation(
    declared_type: Optional[str],
    declared_names: Set[str],
    *,
    owner: str,
    field_name: str,
    attribute_kind: str,
) -> Tuple[Any, Optional[str], str]:
    """Résout le type déclaré d'un attribut en annotation Pydantic, ou lève.

    Une seule mécanique pour les attributs d'entité et d'arête : primitif,
    référence à un type déclaré, conteneur générique refusé, type simple
    inconnu traité comme texte. La référence est insensible à la casse :
    `Person` et `person` désignent la même entité déclarée.

    Args:
        declared_type: Chaîne du type déclarée, normalisée par
            `_coerce_declared_type`, ou `None` si l'attribut n'a pas de type.
        declared_names: Ensemble des noms de types d'entité déclarés dans
            l'ontologie. Utilisé pour résoudre les références, en
            comparaison insensible à la casse.
        owner: Nom du type propriétaire de l'attribut (« Person », «
            REGULATES », etc.), utilisé pour les messages d'erreur.
        field_name: Nom de l'attribut, utilisé pour les messages d'erreur.
        attribute_kind: Genre de l'attribut — `"attribut d'entité"` ou
            `"attribut d'arête"`. Sert uniquement à la rédaction des
            messages d'erreur.

    Returns:
        Tuple `(annotation, reference, description)` :
        - `annotation` : la classe Python à utiliser comme annotation
          Pydantic (`str`, `int`, `List[str]`, `Optional[str]` pour une
          référence) ;
        - `reference` : nom du type référencé si l'attribut est une
          référence, sinon `None` ;
        - `description` : description enrichie si l'attribut est une
          référence (`"(référence vers le type d'entité Person)"`),
          sinon la description d'origine (vide si absente).
    """
    attribute_description = ""

    if declared_type is None:
        # Pas de type déclaré : `text`, comme le fait déjà
        # `normalize_ontology_attribute` pour un attribut en chaîne.
        return str, None, attribute_description

    lowered = declared_type.lower()

    if lowered in PRIMITIVE_FIELD_TYPES:
        return PRIMITIVE_FIELD_TYPES[lowered], None, attribute_description

    if lowered.endswith("[]"):
        # Notation « tableau » de l'ontologie (SQL-like) : liste de texte.
        return List[str], None, attribute_description

    # Référence à un type d'entité déclaré : comparaison insensible à la
    # casse. Si plusieurs entités matchent en casse différente, lever une
    # ambiguïté plutôt que d'en choisir une silencieusement.
    matches = [n for n in declared_names if n.lower() == lowered]
    if matches:
        target = matches[0]
        if len(matches) > 1:
            raise OntologyValidationError(
                f"L'{attribute_kind} '{field_name}' du type '{owner}' réfère à "
                f"'{declared_type}' qui correspond à plusieurs entités déclarées "
                f"en casse différente : {', '.join(sorted(matches))}"
            )
        attribute_description = (
            f"(référence vers le type d'entité {target})"
        )
        return Optional[str], target, attribute_description

    if _GENERIC_TYPE_PATTERN.match(lowered):
        raise OntologyValidationError(
            f"L'{attribute_kind} '{field_name}' du type '{owner}' déclare le "
            f"type '{declared_type}', qui est un conteneur générique : un nœud "
            "n'accepte qu'un scalaire ou un tableau de scalaires"
        )

    if _SIMPLE_TYPE_PATTERN.match(declared_type):
        # Vocabulaire inconnu du LLM (`enum`, `category`, `montant`…) :
        # on en fait un texte plutôt que de refuser une ontologie
        # entière. Le générateur produit ce genre de type, et un refus
        # ici ferait échouer la construction d'un graphe pour un mot.
        logger.debug(
            "Type d'attribut inconnu '%s' sur '%s.%s', traité comme texte",
            declared_type,
            owner,
            field_name,
        )
        return str, None, attribute_description

    raise OntologyValidationError(
        f"L'{attribute_kind} '{field_name}' du type '{owner}' déclare le type "
        f"'{declared_type}', qui n'est ni un primitif "
        f"({', '.join(sorted(PRIMITIVE_FIELD_TYPES))}), ni un type d'entité "
        "déclaré, ni un type scalaire"
    )


def _resolve_entity_types(
    ontology: Dict[str, Any],
    *,
    declared_entity_names: Optional[Set[str]] = None,
) -> List[ResolvedEntityType]:
    """Étape 1 : valide le schéma et résout chaque type d'entité déclaré.

    Si `declared_entity_names` est fourni, la résolution des attributs
    peut aussi reconnaître des références à des types déclarés dans une
    passe précédente (utile pour les arêtes, qui peuvent référencer des
    entités déclarées ailleurs dans l'ontologie).
    """
    raw_types = ontology.get("entity_types", [])
    if raw_types is None:
        raw_types = []
    if not isinstance(raw_types, list):
        raise OntologyValidationError(
            f"entity_types doit être une liste, reçu {_describe(raw_types)}"
        )

    if len(raw_types) > MAX_ONTOLOGY_TYPES:
        raise OntologyValidationError(
            f"Ontologie refusée : {len(raw_types)} types d'entité déclarés, "
            f"maximum {MAX_ONTOLOGY_TYPES}"
        )

    # Passe 1 — collecting des noms, pour résoudre les références ensuite.
    entries: List[Tuple[str, str, Any]] = []
    declared_names: Set[str] = set(declared_entity_names or set())
    for raw in raw_types:
        if isinstance(raw, str):
            name, description, raw_attributes = raw.strip(), f"A {raw.strip()} entity.", []
        elif isinstance(raw, dict):
            # Distinction stricte :
            # - clé `name` absente → nom vide → « sans nom exploitable » ;
            # - clé `name` présente avec valeur non-string (None, booléen,
            #   entier, liste, dict) → refus explicite avec le type fautif ;
            # - clé `name` présente et chaîne → strip et validation.
            if "name" not in raw:
                name = ""
            else:
                raw_name = raw["name"]
                if isinstance(raw_name, str):
                    name = raw_name.strip()
                else:
                    raise OntologyValidationError(
                        f"Type d'entité avec un nom de type {_describe(raw_name)} : "
                        "le nom doit être une chaîne non vide (sans `null`, sans "
                        "booléen, sans entier — tous stringifiés en 'None', 'True', "
                        "'123' par accident)"
                    )
            description = raw.get("description") or f"A {name} entity."
            raw_attributes = raw.get("attributes", [])
        else:
            raise OntologyValidationError(
                f"Type d'entité inutilisable : {raw!r} (type {_describe(raw)})"
            )

        if not name:
            raise OntologyValidationError(
                f"Type d'entité sans nom exploitable : {raw!r}"
            )
        valider_nom_de_type(name, "type")
        if name in declared_names:
            raise OntologyValidationError(
                f"Le nom de type '{name}' est déclaré deux fois dans l'ontologie"
            )
        declared_names.add(name)
        entries.append((name, str(description), raw_attributes))

    # Passe 2 — résolution des attributs, références comprises.
    resolved: List[ResolvedEntityType] = []
    references: Dict[str, Set[str]] = {}
    for name, description, raw_attributes in entries:
        fields: List[ResolvedField] = []
        seen_fields: Set[str] = set()
        for normalized in normalize_ontology_attributes(raw_attributes):
            raw_field_name = normalized["name"]
            field_name = safe_ontology_attribute_name(
                str(raw_field_name).strip() if isinstance(raw_field_name, str) else ""
            )
            if not is_valid_ontology_name(field_name):
                raise OntologyValidationError(
                    f"L'attribut '{raw_field_name}' du type '{name}' n'est pas "
                    "un identifiant valide (lettres, chiffres et underscore, sans "
                    "commencer par un chiffre)"
                )
            if field_name in seen_fields:
                raise OntologyValidationError(
                    f"L'attribut '{field_name}' est déclaré deux fois sur le type '{name}'"
                )
            seen_fields.add(field_name)

            declared_type = _coerce_declared_type(normalized.get("type"))
            base_description = str(normalized.get("description", ""))
            annotation, reference, ref_description = _resolve_attribute_annotation(
                declared_type,
                declared_names,
                owner=name,
                field_name=field_name,
                attribute_kind="attribut d'entité",
            )
            attribute_description = (
                f"{base_description} {ref_description}".strip() if ref_description else base_description
            )

            fields.append(
                ResolvedField(
                    name=field_name,
                    annotation=annotation,
                    description=attribute_description,
                    reference=reference,
                )
            )
            if reference is not None:
                references.setdefault(name, set()).add(reference)
            if len(fields) == MAX_ONTOLOGY_ATTRIBUTES:
                logger.debug(
                    "Type d'ontologie '%s' tronqué à %d attributs",
                    name,
                    MAX_ONTOLOGY_ATTRIBUTES,
                )
                break

        resolved.append(
            ResolvedEntityType(
                name=name, description=description, fields=tuple(fields)
            )
        )

    if references:
        _reject_reference_cycles(references, declared_names)
    return resolved


def _reject_reference_cycles(
    references: Dict[str, Set[str]], declared_names: Set[str]
) -> None:
    """Refuse un cycle de références entre types d'entité.

    Aplatir une référence en chaîne rend un cycle silencieusement inoffensif ;
    on le refuse donc explicitement, en nommant le cycle : une ontologie dont
    les types se référencent mutuellement est incohérente, et le dire vaut mieux
    que de l'écrire dans le vide.
    """
    state: Dict[str, int] = {}
    path: List[str] = []

    def visit(name: str) -> None:
        state[name] = 1
        path.append(name)
        for target in sorted(references.get(name, ())):
            if target not in declared_names:
                continue
            if state.get(target, 0) == 1:
                cycle = " -> ".join(path[path.index(target):] + [target])
                raise OntologyValidationError(
                    f"Cycle de références entre types d'entité : {cycle}"
                )
            if state.get(target, 0) == 0:
                visit(target)
        path.pop()
        state[name] = 2

    for name in sorted(declared_names):
        if state.get(name, 0) == 0:
            visit(name)


def _resolve_edge_endpoints(
    raw_endpoints: Any,
    declared_names: Set[str],
    *,
    edge_name: str,
    endpoint_kind: str,
) -> None:
    """Valide que chaque source/cible déclarée d'une arête référence une entité.

    Une arête `ORGANISES → ["PersonEntity"]` contraint ses extrémités ; un
    nom d'entité non déclaré — ou un nom qui n'est pas une chaîne —
    produit une erreur claire plutôt qu'une relecture fausse en aval.

    Si `declared_names` est vide (l'ontologie ne déclare aucune entité
    dans cette passe), la cohérence n'est pas vérifiable : les
    extrémités sont présumées pointer vers des types d'entité existants
    par ailleurs (côté serveur Zep, par exemple).

    Args:
        raw_endpoints: Liste brute déclarée sur l'arête (`source_types` ou
            `target_types`). Peut être `None` (clé absente), une liste, ou
            toute autre valeur (levée).
        declared_names: Ensemble des noms de types d'entité déclarés dans
            l'ontologie, en casse d'origine.
        edge_name: Nom de l'arête, utilisé pour les messages d'erreur.
        endpoint_kind: `"source"` ou `"target"`, pour le message d'erreur.
    """
    if raw_endpoints is None:
        return
    if not isinstance(raw_endpoints, list):
        raise OntologyValidationError(
            f"L'arête '{edge_name}' a un champ '{endpoint_kind}_types' qui "
            f"n'est pas une liste : reçu {_describe(raw_endpoints)}"
        )
    if not declared_names:
        # Aucune entité déclarée dans cette passe : les extrémités sont
        # présumées pointer vers des types existants par ailleurs.
        return
    for endpoint in raw_endpoints:
        if not isinstance(endpoint, str):
            raise OntologyValidationError(
                f"L'arête '{edge_name}' déclare un {endpoint_kind} "
                f"{_describe(endpoint)} qui n'est pas une chaîne"
            )
        if endpoint not in declared_names:
            raise OntologyValidationError(
                f"L'arête '{edge_name}' déclare un {endpoint_kind} '{endpoint}' "
                "qui ne référence aucun type d'entité déclaré dans l'ontologie"
            )


def _resolve_edge_types(
    ontology: Dict[str, Any],
    *,
    declared_entity_names: Optional[Set[str]] = None,
) -> List[ResolvedEntityType]:
    """Résout les types de relation déclarés, avec la même sévérité que les entités.

    Une relation devient le **nom** de la relation dans le graphe, pas un label de
    nœud : la validation porte donc sur le nom, sur la description, sur les
    attributs (traduisibles comme ceux d'une entité — primitif, référence,
    conteneur refusé), et sur les extrémités (`source_types` / `target_types`)
    qui doivent référencer des types d'entité déclarés.

    Si `declared_entity_names` est fourni, la résolution des attributs d'arête
    peut reconnaître des références à des types d'entité déclarés dans la
    même ontologie (par défaut : l'ensemble des noms d'arêtes résolus dans
    cette passe, ce qui est en pratique vide).
    """
    raw_types = ontology.get("edge_types", [])
    if raw_types is None:
        raw_types = []
    if not isinstance(raw_types, list):
        raise OntologyValidationError(
            f"edge_types doit être une liste, reçu {_describe(raw_types)}"
        )
    if len(raw_types) > MAX_ONTOLOGY_TYPES:
        raise OntologyValidationError(
            f"Ontologie refusée : {len(raw_types)} types de relation déclarés, "
            f"maximum {MAX_ONTOLOGY_TYPES}"
        )

    resolved: List[ResolvedEntityType] = []
    seen: Set[str] = set()
    # Les attributs d'arête peuvent référencer des types d'entité déclarés
    # dans la même ontologie. Si l'appelant a déjà résolu les noms d'entité,
    # on les réutilise ; sinon on retombe sur les noms d'arêtes (qui ne
    # référencent jamais rien, mais qui servent de filet de cohérence).
    ref_names = declared_entity_names if declared_entity_names is not None else seen

    for raw in raw_types:
        if isinstance(raw, str):
            name = raw.strip()
            description = f"A {name} relationship."
            raw_attributes: List[Any] = []
            raw_source_targets: List[Any] = []
        elif isinstance(raw, dict):
            if "name" not in raw:
                name = ""
            else:
                raw_name = raw["name"]
                if isinstance(raw_name, str):
                    name = raw_name.strip()
                else:
                    raise OntologyValidationError(
                        f"Type de relation avec un nom {_describe(raw_name)} : "
                        "le nom doit être une chaîne non vide"
                    )
            description = raw.get("description") or f"A {name} relationship."
            raw_attributes = raw.get("attributes", [])
            raw_source_targets = raw.get("source_targets", [])
        else:
            raise OntologyValidationError(
                f"Type de relation inutilisable : {raw!r} (type {_describe(raw)})"
            )

        if not name:
            raise OntologyValidationError(
                f"Type de relation sans nom exploitable : {raw!r}"
            )
        valider_nom_de_type(name, "relation")
        if name in seen:
            raise OntologyValidationError(
                f"Le nom de relation '{name}' est déclaré deux fois dans l'ontologie"
            )
        seen.add(name)

        # Extrémités : la spec d'ontologie contraint `source` et `target`
        # à des types d'entité déclarés (architecture §2.1). On accepte les
        # deux clés — `source_targets` (forme canonique générée par
        # `OntologyGenerator`) et `source_types` / `target_types` (forme
        # courte déjà utilisée par certains tests). Toute valeur ni-liste
        # ni-`None` est refusée.
        if isinstance(raw, dict):
            for endpoints_key in (
                "source_types",
                "target_types",
                "source_targets",
                "target_targets",
            ):
                value = raw.get(endpoints_key)
                if value is None:
                    continue
                if not isinstance(value, list):
                    raise OntologyValidationError(
                        f"L'arête '{name}' a un champ '{endpoints_key}' qui "
                        f"n'est pas une liste : reçu {_describe(value)}"
                    )
                if endpoints_key == "source_targets":
                    _resolve_edge_endpoints(
                        [pair.get("source") for pair in value if isinstance(pair, dict)],
                        ref_names,
                        edge_name=name,
                        endpoint_kind="source",
                    )
                    _resolve_edge_endpoints(
                        [pair.get("target") for pair in value if isinstance(pair, dict)],
                        ref_names,
                        edge_name=name,
                        endpoint_kind="target",
                    )
                elif endpoints_key == "target_targets":
                    _resolve_edge_endpoints(
                        [pair.get("target") for pair in value if isinstance(pair, dict)],
                        ref_names,
                        edge_name=name,
                        endpoint_kind="target",
                    )
                elif endpoints_key == "source_types":
                    _resolve_edge_endpoints(
                        value, ref_names, edge_name=name, endpoint_kind="source"
                    )
                elif endpoints_key == "target_types":
                    _resolve_edge_endpoints(
                        value, ref_names, edge_name=name, endpoint_kind="target"
                    )
        _ = raw_source_targets  # conservé pour la compatibilité de signature

        fields: List[ResolvedField] = []
        seen_fields: Set[str] = set()
        for normalized in normalize_ontology_attributes(raw_attributes):
            raw_field_name = normalized["name"]
            field_name = safe_ontology_attribute_name(
                str(raw_field_name).strip() if isinstance(raw_field_name, str) else ""
            )
            if not is_valid_ontology_name(field_name):
                raise OntologyValidationError(
                    f"L'attribut '{raw_field_name}' de la relation '{name}' "
                    "n'est pas un identifiant valide"
                )
            if field_name in seen_fields:
                raise OntologyValidationError(
                    f"L'attribut '{field_name}' est déclaré deux fois sur la "
                    f"relation '{name}'"
                )
            seen_fields.add(field_name)

            declared_type = _coerce_declared_type(normalized.get("type"))
            base_description = str(normalized.get("description", ""))
            annotation, reference, ref_description = _resolve_attribute_annotation(
                declared_type,
                ref_names,
                owner=name,
                field_name=field_name,
                attribute_kind="attribut d'arête",
            )
            attribute_description = (
                f"{base_description} {ref_description}".strip() if ref_description else base_description
            )

            fields.append(
                ResolvedField(
                    name=field_name,
                    annotation=annotation,
                    description=attribute_description,
                    reference=reference,
                )
            )
            if len(fields) == MAX_ONTOLOGY_ATTRIBUTES:
                logger.debug(
                    "Type d'arête '%s' tronqué à %d attributs",
                    name,
                    MAX_ONTOLOGY_ATTRIBUTES,
                )
                break

        resolved.append(
            ResolvedEntityType(
                name=name, description=str(description), fields=tuple(fields)
            )
        )

    return resolved


def _build_pydantic_classes(
    entity_types: List[ResolvedEntityType],
    *,
    kind: str = "entité",
) -> Dict[str, type[BaseModel]]:
    """Étape 2 : construit les classes, puis prouve qu'elles sont instanciables."""
    classes: Dict[str, type[BaseModel]] = {}
    for entity_type in entity_types:
        namespace: Dict[str, Any] = {
            "__doc__": entity_type.description,
            "__annotations__": {
                field.name: Optional[field.annotation] for field in entity_type.fields
            },
        }
        for field in entity_type.fields:
            namespace[field.name] = Field(
                default=None, description=field.description
            )

        try:
            model = type(entity_type.name, (BaseModel,), namespace)
            model.__doc__ = entity_type.description
            model.__module__ = __name__
            model()
        except ValidationError as error:
            raise OntologyValidationError(
                f"Le type d'{kind} '{entity_type.name}' n'est pas constructible : "
                f"{error}"
            ) from error

        classes[entity_type.name] = model

    return classes


class OntologyToPydantic:
    """Traduit un dict d'ontologie en classes Pydantic, ou le refuse (ADR 0014 §4)."""

    @staticmethod
    def from_dict(ontology: Dict[str, Any]) -> Dict[str, type[BaseModel]]:
        """Retourne `{nom_de_type: classe}`, prêt pour `entity_types` de Graphiti.

        Args:
            ontology: Dict d'ontologie produit par `OntologyGenerator`. Une
                chaîne seule ou une entrée sans nom est acceptée : ce sont des
                formes que le générateur produit déjà.

        Returns:
            Un dictionnaire indexé par nom de type — un **dictionnaire**, parce
            que c'est la clé qu'il en fait qui devient le label Cypher du nœud,
            et non le nom de la classe.

            **Vide** si l'ontologie ne déclare que des relations : les classes
            d'arête sont alors à construire séparément par
            `edge_types_from_dict`. Le graphe reste non typé en entités.

            **Soulève** `OntologyValidationError` si l'ontologie ne déclare ni
            entité exploitable ni relation exploitable.

        Raises:
            OntologyValidationError: Ontologie non dictionnaire, trop de types,
                nom inexploitable ou réservé, attribut non scalaire, cycle de
                références, ou classe non constructible.
        """
        if not isinstance(ontology, dict):
            raise OntologyValidationError(
                f"L'ontologie doit être un dictionnaire, reçu {_describe(ontology)}"
            )

        entity_types = _resolve_entity_types(ontology)
        entity_names = {resolved.name for resolved in entity_types}
        edge_types = _resolve_edge_types(ontology, declared_entity_names=entity_names)
        if not entity_types and not edge_types:
            raise OntologyValidationError(
                "Ontologie refusée : aucun type d'entité ni type de relation "
                "exploitable"
            )
        return _build_pydantic_classes(entity_types)

    @staticmethod
    def edge_types_from_dict(ontology: Dict[str, Any]) -> Dict[str, type[BaseModel]]:
        """Retourne `{nom_de_relation: classe}`, prêt pour `edge_types` de Graphiti.

        Les types de relation sont **optionnels** : une ontologie qui n'en
        déclare aucun donne un dictionnaire vide, jamais un refus. C'est ce qui
        permet à `from_dict` d'exiger un type d'entité — le graphe ne peut pas
        être typé sans — tout en laissant les relations à la discrétion du
        générateur.

        Les attributs d'arête qui référencent des types d'entité déclarés
        dans la même ontologie résolvent leur cible ; les `source_types` /
        `target_types` / `source_targets` doivent référencer des types
        d'entité déclarés dans la même ontologie (cf.
        `_resolve_edge_endpoints`).
        """
        if not isinstance(ontology, dict):
            raise OntologyValidationError(
                f"L'ontologie doit être un dictionnaire, reçu {_describe(ontology)}"
            )

        # Résoudre d'abord les entités pour avoir la liste des noms déclarés
        # que les arêtes peuvent référencer (source/target/attribut).
        entity_types = _resolve_entity_types(ontology)
        entity_names = {resolved.name for resolved in entity_types}
        edge_types = _resolve_edge_types(
            ontology, declared_entity_names=entity_names
        )
        if not edge_types:
            return {}
        return _build_pydantic_classes(edge_types, kind="relation")
