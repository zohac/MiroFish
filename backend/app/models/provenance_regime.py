"""Régime de provenance d'un passage de rapport (Story 014-1, FR-01, FR-02).

Ce module définit un **second axe** de provenance, distinct de
``InformationOrigin`` (ADR 0012, ADR 0013, dont les cinq valeurs sont gelées) :

- ``InformationOrigin`` répond à « quelle est la nature épistémique de
  l'information ? » ;
- ``ProvenanceRegime`` répond à « d'où vient ce fragment, et est-il
  auditable contre le paquet de preuves figé ? ».

L'attribution est **pure et déterministe** : aucune dépendance à un service,
à un modèle ni au réseau. Elle se fait par partage de 8-grammes normalisés
(NFKD, minuscules, tout non-alphanumérique remplacé par une espace).
"""

from __future__ import annotations

import re
import unicodedata
from enum import Enum
from typing import Any, Iterable, List, Optional, Tuple


class ProvenanceRegime(str, Enum):
    """Régime de provenance d'un fragment de rapport.

    Régimes de matériau :
      - ``document``  : fait issu d'un document source (auditable par positions).
      - ``event``     : fait issu de ``query_simulation_events`` (auditable par
        ``event_id`` contre le paquet figé).
      - ``action``    : action observée du run, hors du paquet figé.
      - ``graph``     : fait issu d'un outil de graphe (non scellé).
      - ``interview`` : parole tenue pendant la rédaction (hors du paquet figé).
      - ``inference`` : déduction analytique du LLM de rapport.
      - ``unknown``   : rattachement impossible.
    """

    DOCUMENT = "document"
    EVENT = "event"
    ACTION = "action"
    GRAPH = "graph"
    INTERVIEW = "interview"
    INFERENCE = "inference"
    UNKNOWN = "unknown"

    @classmethod
    def from_str(cls, value: Any) -> "ProvenanceRegime":
        if value is None:
            return cls.UNKNOWN
        if isinstance(value, cls):
            return value
        text = str(value).strip().lower()
        for member in cls:
            if member.value == text or member.name.lower() == text:
                return member
        # Synonymes tolérants
        if "interview" in text:
            return cls.INTERVIEW
        if "event" in text:
            return cls.EVENT
        if "graph" in text:
            return cls.GRAPH
        if "action" in text:
            return cls.ACTION
        if "document" in text or "doc" in text:
            return cls.DOCUMENT
        if "inference" in text or "deduction" in text or "analysis" in text:
            return cls.INFERENCE
        return cls.UNKNOWN


#: Correspondance exhaustive outil -> régime (Story 014-1, décision 4).
TOOL_TO_REGIME: dict = {
    "interview_agents": ProvenanceRegime.INTERVIEW,
    "insight_forge": ProvenanceRegime.GRAPH,
    "panorama_search": ProvenanceRegime.GRAPH,
    "quick_search": ProvenanceRegime.GRAPH,
    "get_edge_provenance": ProvenanceRegime.GRAPH,
    "get_applied_ontology": ProvenanceRegime.GRAPH,
    "query_simulation_events": ProvenanceRegime.EVENT,
    # verify_action / verify_citation sont des verdicts de vérification, pas du
    # matériau : ils ne nourrissent jamais un fragment.
    "verify_action": ProvenanceRegime.UNKNOWN,
    "verify_citation": ProvenanceRegime.UNKNOWN,
}


#: Ordre de priorité, du régime le MOINS auditable au plus auditable.
#: En cas de correspondance multiple, le régime le moins auditable l'emporte
#: (transposition du Fail-Closed à la provenance).
REGIME_PRIORITY: Tuple[ProvenanceRegime, ...] = (
    ProvenanceRegime.INTERVIEW,
    ProvenanceRegime.GRAPH,
    ProvenanceRegime.ACTION,
    ProvenanceRegime.EVENT,
    ProvenanceRegime.DOCUMENT,
    ProvenanceRegime.INFERENCE,
    ProvenanceRegime.UNKNOWN,
)


def _normalize_text(text: Any) -> str:
    """Normalise un texte pour la comparaison par n-grammes (NFR-3).

    NFKD, minuscules, tout non-alphanumérique remplacé par une espace.
    Les accents se rencontrent : ``Émilie`` et ``Emilie`` donnent le même
    résultat.
    """
    if text is None:
        return ""
    if not isinstance(text, str):
        text = str(text)
    normalized = unicodedata.normalize("NFKD", text)
    # Les marques combinantes (accents) sont supprimées, pas remplacées par
    # une espace : ainsi « Émilie » et « Emilie » se rencontrent.
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    # Tout le reste qui n'est pas alphanumérique (ponctuation, espaces) devient
    # une espace.
    normalized = re.sub(r"[^A-Za-z0-9]+", " ", normalized)
    return " ".join(normalized.lower().split())


def _ngrams(text: str, n: int = 8) -> set:
    words = text.split()
    if len(words) < n:
        return set()
    return {tuple(words[i : i + n]) for i in range(len(words) - n + 1)}


def _source_tool(source: Any) -> Optional[str]:
    if isinstance(source, dict):
        for key in ("tool", "tool_name", "name", "source", "toolname"):
            val = source.get(key)
            if val:
                return str(val)
        return None
    for attr in ("tool", "tool_name", "name", "source"):
        val = getattr(source, attr, None)
        if val:
            return str(val)
    # Tuple (tool, text) ou (tool_name, text)
    if isinstance(source, (tuple, list)) and len(source) >= 2 and isinstance(source[0], str):
        return str(source[0])
    return None


def _source_text(source: Any) -> str:
    if isinstance(source, dict):
        for key in ("text", "content", "result", "output", "response", "value"):
            val = source.get(key)
            if val:
                return str(val)
        return ""
    for attr in ("text", "content", "result", "output", "response", "value"):
        val = getattr(source, attr, None)
        if val:
            return str(val)
    if isinstance(source, (tuple, list)) and len(source) >= 2:
        return str(source[1])
    if isinstance(source, str):
        return source
    return str(source) if source is not None else ""


def attribute_provenance_regime(fragment: Any, sources: Any = None) -> ProvenanceRegime:
    """Attribue un régime de provenance à un fragment de rapport.

    ``sources`` est une collection d'observations d'outils. Chaque observation
    porte le nom de l'outil qui l'a produite et son texte. Le rattachement se
    fait par partage d'au moins 8 mots consécutifs normalisés.

    Retourne ``ProvenanceRegime.UNKNOWN`` si aucune correspondance n'existe,
    ou si le fragment fait moins de 8 mots.
    """
    normalized_fragment = _normalize_text(fragment)
    fragment_grams = _ngrams(normalized_fragment, 8)
    if not fragment_grams:
        return ProvenanceRegime.UNKNOWN

    # Normaliser la forme de `sources`.
    if sources is None:
        sources = []
    if isinstance(sources, dict):
        sources = [sources]
    if not isinstance(sources, (list, tuple, set)):
        sources = [sources]

    candidates: List[ProvenanceRegime] = []
    for source in sources:
        tool_name = _source_tool(source)
        explicit_regime = None
        if isinstance(source, dict):
            explicit_regime = source.get("regime") or source.get("provenance_regime") or source.get("regime_name")
        else:
            for attr in ("regime", "provenance_regime", "regime_name"):
                val = getattr(source, attr, None)
                if val:
                    explicit_regime = val
                    break
        if explicit_regime is not None:
            regime = ProvenanceRegime.from_str(explicit_regime)
        else:
            regime = TOOL_TO_REGIME.get(str(tool_name or "").strip(), ProvenanceRegime.UNKNOWN)
        source_grams = _ngrams(_normalize_text(_source_text(source)), 8)
        if fragment_grams & source_grams:
            candidates.append(regime)

    if not candidates:
        return ProvenanceRegime.UNKNOWN

    # Le régime le moins auditable l'emporte.
    for regime in REGIME_PRIORITY:
        if regime in candidates:
            return regime
    return candidates[0]


# Alias de compatibilité pour les tests / appelants qui utilisent un nom court.
attribute_regime = attribute_provenance_regime
resolve_provenance_regime = attribute_provenance_regime
