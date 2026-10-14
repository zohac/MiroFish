"""Helpers for validating LLM-generated ontology structures."""

import re
from typing import Any, Dict, List, Optional


MAX_ONTOLOGY_TYPES = 10
MAX_ONTOLOGY_ATTRIBUTES = 10
MAX_ONTOLOGY_SOURCE_TARGETS = 10
#: Noms d'attributs d'ontologie que le store gère lui-même : ils sont préfixés
#: par `entity_` au lieu d'être refusés. La liste couvre :
#: - les propriétés de `EntityNode` (Graphiti) — mesuré sur `EntityNode.model_fields` ;
#: - le `graph_id` de partitionnement ;
#: - les noms de classe / d'instance réservés par Pydantic 2 — mesuré sur
#:   `pydantic 2.12.5`, où `graphiti_core` lit `entity_type.model_fields` en
#:   plusieurs endroits ; un attribut portant un de ces noms serait avalé par
#:   Pydantic comme configuration de classe, jamais posé en propriété de nœud
#:   (relecture BMAD du 12 oct. 2026, patch #6 groupe B).
#: Un attribut portant l'un de ces noms entrerait en collision avec une
#: propriété gérée, et Graphiti refuserait la classe **au moment de
#: l'extraction**, loin de sa cause (ADR 0014 §4).
RESERVED_ONTOLOGY_ATTRIBUTE_NAMES = frozenset({
    "uuid",
    "name",
    "group_id",
    "graph_id",
    "name_embedding",
    "summary",
    "created_at",
    "attributes",
    "labels",
    # Noms de classe Pydantic 2 (`pydantic 2.12.5`).
    "model_config",
    "model_fields",
    "model_post_init",
    "model_parametrized_name",
    "model_validate",
    "model_construct",
    "model_copy",
    "model_dump",
    "model_dump_json",
    "model_validate_json",
    "model_extra_fields",
    "model_post_root_validator",
    "model_rebuild",
    "model_rebuild_method",
})

_FALLBACK_ATTRIBUTE = {
    "name": "details",
    "type": "text",
    "description": "Additional details about this ontology type.",
}

#: Un nom d'attribut d'ontologie devient un nom de champ Pydantic, donc un
#: identifiant Python. Un nom libre produit une classe que Pydantic refuse à la
#: construction : on le refuse ici, avec le nom fautif dans le message.
ONTOLOGY_NAME_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def is_valid_ontology_name(name: Any) -> bool:
    """Indique si un nom de type ou d'attribut est utilisable tel quel.

    Le nom d'un type d'entité devient un **label Cypher** et le nom d'un
    attribut devient un champ Pydantic : tous deux doivent être des
    identifiants. Un nom contenant un tiret ou un espace produirait une erreur
    de syntaxe Cypher en aval, loin de sa cause.
    """
    return isinstance(name, str) and bool(ONTOLOGY_NAME_PATTERN.match(name))


def safe_ontology_attribute_name(name: str) -> str:
    """Préfixe un nom d'attribut qui entre en collision avec une propriété gérée.

    Une seule implémentation pour les deux stores : c'est la seule façon qu'ils
    traduisent le même dict d'ontologie de la même façon (ADR 0014 §4).
    Préfixer plutôt que refuser, parce qu'un nom résiduel produit par le LLM ne
    doit pas faire échouer une construction de graphe entière.
    """
    if name.lower() in RESERVED_ONTOLOGY_ATTRIBUTE_NAMES:
        return f"entity_{name}"
    return name


def normalize_ontology_attribute(attribute: Any) -> Optional[Dict[str, Any]]:
    """Return a safe attribute definition, or ``None`` for unusable values."""

    if isinstance(attribute, str):
        if not attribute.strip():
            return None
        return {
            "name": attribute,
            "type": "text",
            "description": attribute,
        }

    if not isinstance(attribute, dict):
        return None

    name = attribute.get("name")
    if not isinstance(name, str) or not name.strip():
        return None

    normalized = dict(attribute)
    description = normalized.get("description")
    if not isinstance(description, str) or not description:
        normalized["description"] = name
    return normalized


def normalize_ontology_attributes(attributes: Any) -> List[Dict[str, Any]]:
    """Return a non-empty Zep-compatible attribute list within service limits."""

    if not isinstance(attributes, list):
        attributes = []

    normalized_attributes: List[Dict[str, Any]] = []
    for attribute in attributes:
        normalized = normalize_ontology_attribute(attribute)
        if normalized is None:
            continue
        normalized_attributes.append(normalized)
        if len(normalized_attributes) == MAX_ONTOLOGY_ATTRIBUTES:
            break

    if not normalized_attributes:
        normalized_attributes.append(dict(_FALLBACK_ATTRIBUTE))

    return normalized_attributes


def normalize_ontology_source_targets(
    source_targets: Any,
    *,
    limit: int | None = MAX_ONTOLOGY_SOURCE_TARGETS,
) -> List[Dict[str, str]]:
    """Return unique, structurally valid source-target pairs within Zep limits."""

    if not isinstance(source_targets, list):
        return []

    normalized_targets: List[Dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for source_target in source_targets:
        if not isinstance(source_target, dict):
            continue
        source = source_target.get("source")
        target = source_target.get("target")
        if not isinstance(source, str) or not source.strip():
            continue
        if not isinstance(target, str) or not target.strip():
            continue

        pair = (source.strip(), target.strip())
        if pair in seen:
            continue
        seen.add(pair)
        normalized_targets.append({"source": pair[0], "target": pair[1]})
        if limit is not None and len(normalized_targets) == limit:
            break

    return normalized_targets


def canonical_ontology_projection(ontology: Dict[str, Any]) -> Dict[str, Any]:
    """Extrait la projection canonique des champs stables d'une ontologie (AC3).

    Les champs stables comparés pour la régénération déterministe sont :
    - Les noms de types d'entité et leurs attributs rattachés ;
    - Les noms de types de relation et leurs attributs rattachés.

    Les listes sont triées par nom de type et par nom d'attribut pour
    neutraliser les variations d'ordre tout en conservant les doublons
    éventuels. Les descriptions, exemples et `analysis_summary` sont
    délibérément exclus de cette projection.
    """
    if not isinstance(ontology, dict):
        return {"entity_types": [], "edge_types": []}

    def _extract_attrs(raw_item: Dict[str, Any]) -> List[str]:
        raw_attrs = raw_item.get("attributes", [])
        if not isinstance(raw_attrs, list):
            return []
        attrs: List[str] = []
        for a in raw_attrs:
            if isinstance(a, str):
                name = a.strip()
                if name:
                    attrs.append(name)
            elif isinstance(a, dict):
                raw_name = a.get("name")
                if isinstance(raw_name, str):
                    name = raw_name.strip()
                    if name:
                        attrs.append(name)
        attrs.sort()
        return attrs

    entity_types = []
    for raw_entity in ontology.get("entity_types", []):
        if not isinstance(raw_entity, dict):
            continue
        raw_name = raw_entity.get("name")
        name = str(raw_name).strip() if raw_name is not None else ""
        entity_types.append({
            "name": name,
            "attributes": _extract_attrs(raw_entity),
        })
    entity_types.sort(key=lambda item: (item["name"], item["attributes"]))

    edge_types = []
    for raw_edge in ontology.get("edge_types", []):
        if not isinstance(raw_edge, dict):
            continue
        raw_name = raw_edge.get("name")
        name = str(raw_name).strip() if raw_name is not None else ""
        edge_types.append({
            "name": name,
            "attributes": _extract_attrs(raw_edge),
        })
    edge_types.sort(key=lambda item: (item["name"], item["attributes"]))

    return {
        "entity_types": entity_types,
        "edge_types": edge_types,
    }


