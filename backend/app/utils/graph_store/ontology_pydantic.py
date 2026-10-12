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
#: Un type d'ontologie portant un de ces noms poserait sur chaque nœud extrait un
#: label indistinguable d'un `:Episodic` ou d'un `:Community` : la relecture
#: ascendrait alors des nœuds d'entité comme des épisodes, et le typage métier
#: deviendrait faux. Ils sont refusés, pas renommés — un nom d'ontologie est un
#: choix explicite du domaine, pas une coquille à corriger en silence.
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


def _resolve_entity_types(ontology: Dict[str, Any]) -> List[ResolvedEntityType]:
    """Étape 1 : valide le schéma et résout chaque type d'entité déclaré."""
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
    declared_names: Set[str] = set()
    for raw in raw_types:
        if isinstance(raw, str):
            name, description, raw_attributes = raw.strip(), f"A {raw.strip()} entity.", []
        elif isinstance(raw, dict):
            name = str(raw.get("name", "")).strip()
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
            field_name = safe_ontology_attribute_name(str(normalized["name"]).strip())
            if not is_valid_ontology_name(field_name):
                raise OntologyValidationError(
                    f"L'attribut '{normalized['name']}' du type '{name}' n'est pas "
                    "un identifiant valide (lettres, chiffres et underscore, sans "
                    "commencer par un chiffre)"
                )
            if field_name in seen_fields:
                raise OntologyValidationError(
                    f"L'attribut '{field_name}' est déclaré deux fois sur le type '{name}'"
                )
            seen_fields.add(field_name)

            declared_type = _coerce_declared_type(normalized.get("type"))
            attribute_description = str(normalized.get("description", ""))

            if declared_type is None:
                # Pas de type déclaré : `text`, comme le fait déjà
                # `normalize_ontology_attribute` pour un attribut en chaîne.
                annotation: Any = str
                reference: Optional[str] = None
            elif declared_type.lower() in PRIMITIVE_FIELD_TYPES:
                annotation = PRIMITIVE_FIELD_TYPES[declared_type.lower()]
                reference = None
            elif declared_type.lower().endswith("[]"):
                # Notation « tableau » de l'ontologie (SQL-like) : liste de texte.
                annotation = List[str]
                reference = None
            elif declared_type in declared_names:
                # Référence à un autre type d'entité : aplatie en nom d'entité
                # related. Graphiti n'a pas de champ d'entité ; la référence est
                # conservée dans la description pour rester lisible.
                annotation = Optional[str]
                reference = declared_type
                references.setdefault(name, set()).add(declared_type)
                attribute_description = (
                    f"{attribute_description} "
                    f"(référence vers le type d'entité {declared_type})"
                ).strip()
            elif _GENERIC_TYPE_PATTERN.match(declared_type.lower()):
                raise OntologyValidationError(
                    f"L'attribut '{field_name}' du type '{name}' déclare le type "
                    f"'{declared_type}', qui est un conteneur générique : un nœud "
                    "n'accepte qu'un scalaire ou un tableau de scalaires"
                )
            elif _SIMPLE_TYPE_PATTERN.match(declared_type):
                # Vocabulaire inconnu du LLM (`enum`, `category`, `montant`…) :
                # on en fait un texte plutôt que de refuser une ontologie
                # entière. Le générateur produit ce genre de type, et un refus
                # ici ferait échouer la construction d'un graphe pour un mot.
                annotation = str
                reference = None
                logger.debug(
                    "Type d'attribut inconnu '%s' sur '%s.%s', traité comme texte",
                    declared_type,
                    name,
                    field_name,
                )
            else:
                raise OntologyValidationError(
                    f"L'attribut '{field_name}' du type '{name}' déclare le type "
                    f"'{declared_type}', qui n'est ni un primitif "
                    f"({', '.join(sorted(PRIMITIVE_FIELD_TYPES))}), ni un type "
                    "d'entité déclaré, ni un type scalaire"
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


def _resolve_edge_types(ontology: Dict[str, Any]) -> List[ResolvedEntityType]:
    """Résout les types de relation déclarés, avec la même sévérité que les entités.

    Une relation devient le **nom** de la relation dans le graphe, pas un label de
    nœud : la validation porte donc sur le nom et sur la description, et les
    attributs d'une relation sont traduisibles comme ceux d'une entité.
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
    for raw in raw_types:
        if isinstance(raw, str):
            name, description, raw_attributes = (
                raw.strip(),
                f"A {raw.strip()} relationship.",
                [],
            )
        elif isinstance(raw, dict):
            name = str(raw.get("name", "")).strip()
            description = raw.get("description") or f"A {name} relationship."
            raw_attributes = raw.get("attributes", [])
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

        fields: List[ResolvedField] = []
        for normalized in normalize_ontology_attributes(raw_attributes):
            field_name = safe_ontology_attribute_name(str(normalized["name"]).strip())
            if not is_valid_ontology_name(field_name):
                raise OntologyValidationError(
                    f"L'attribut '{normalized['name']}' de la relation '{name}' "
                    "n'est pas un identifiant valide"
                )
            if any(field.name == field_name for field in fields):
                raise OntologyValidationError(
                    f"L'attribut '{field_name}' est déclaré deux fois sur la "
                    f"relation '{name}'"
                )
            fields.append(
                ResolvedField(
                    name=field_name,
                    annotation=str,
                    description=str(normalized.get("description", "")),
                )
            )
            if len(fields) == MAX_ONTOLOGY_ATTRIBUTES:
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
        except Exception as error:
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
            et non le nom de la classe. **Vide** si l'ontologie ne déclare que
            des relations : elles sont alors transmises par
            `edge_types_from_dict`, et le graphe reste simplement non typé.

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
        edge_types = _resolve_edge_types(ontology)
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
        """
        if not isinstance(ontology, dict):
            raise OntologyValidationError(
                f"L'ontologie doit être un dictionnaire, reçu {_describe(ontology)}"
            )

        edge_types = _resolve_edge_types(ontology)
        if not edge_types:
            return {}
        return _build_pydantic_classes(edge_types, kind="relation")