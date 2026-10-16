"""Modèle de données pour le registre d'événements observés et packs de preuves (Story 011-2).

Ce module implémente :
  - `ObservedEvent` : enregistrement normalisé et immuable d'une action ou d'un fait observé
    dans les traces de simulation (JSONL et SQLite).
  - `EvidencePack` : conteneur de preuves regroupant l'ensemble des événements
    d'un run, avec indexation et statistiques par plateforme, round, agent et type d'action.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set


@dataclass(frozen=True)
class ObservedEvent:
    """Événement observé normalisé au sein de la simulation (AC1).
    
    Garantit l'immutabilité et l'intégrité de l'action réelle simulée.
    """

    event_id: str
    simulation_id: str
    platform: str
    round_num: int
    agent_id: int
    agent_name: str
    action_type: str
    timestamp: str
    action_args: Dict[str, Any] = field(default_factory=dict)
    is_action_executed: bool = True
    result: Optional[str] = None
    success: bool = True
    raw_payload: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "simulation_id": self.simulation_id,
            "platform": self.platform,
            "round_num": self.round_num,
            "agent_id": self.agent_id,
            "agent_name": self.agent_name,
            "action_type": self.action_type,
            "timestamp": self.timestamp,
            "action_args": self.action_args,
            "is_action_executed": self.is_action_executed,
            "result": self.result,
            "success": self.success,
            "raw_payload": self.raw_payload,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ObservedEvent:
        return cls(
            event_id=str(data.get("event_id", "")),
            simulation_id=str(data.get("simulation_id", "")),
            platform=str(data.get("platform", "generic")),
            round_num=int(data.get("round_num", data.get("round", 0))),
            agent_id=int(data.get("agent_id", 0)),
            agent_name=str(data.get("agent_name", f"Agent_{data.get('agent_id', 0)}")),
            action_type=str(data.get("action_type", "unknown")),
            timestamp=str(data.get("timestamp", "")),
            action_args=dict(data.get("action_args") or {}),
            is_action_executed=bool(data.get("is_action_executed", True)),
            result=data.get("result"),
            success=bool(data.get("success", True)),
            raw_payload=dict(data.get("raw_payload") or {}),
        )


@dataclass
class EvidencePack:
    """Pack de preuves consolidé regroupant les faits observés d'une simulation (AC1)."""

    simulation_id: str
    total_events: int = 0
    events_by_platform: Dict[str, int] = field(default_factory=dict)
    events_by_type: Dict[str, int] = field(default_factory=dict)
    events_by_agent: Dict[str, int] = field(default_factory=dict)
    rounds_range: List[int] = field(default_factory=lambda: [0, 0])
    events: List[ObservedEvent] = field(default_factory=list)

    @classmethod
    def from_events(cls, simulation_id: str, events: List[ObservedEvent]) -> EvidencePack:
        """Construit un pack de preuves avec calcul automatique des statistiques."""
        by_platform: Dict[str, int] = {}
        by_type: Dict[str, int] = {}
        by_agent: Dict[str, int] = {}
        min_round = 0
        max_round = 0

        if events:
            min_round = min(e.round_num for e in events)
            max_round = max(e.round_num for e in events)

        for event in events:
            by_platform[event.platform] = by_platform.get(event.platform, 0) + 1
            by_type[event.action_type] = by_type.get(event.action_type, 0) + 1
            by_agent[event.agent_name] = by_agent.get(event.agent_name, 0) + 1

        return cls(
            simulation_id=simulation_id,
            total_events=len(events),
            events_by_platform=by_platform,
            events_by_type=by_type,
            events_by_agent=by_agent,
            rounds_range=[min_round, max_round],
            events=events,
        )

    def filter_events(
        self,
        query: Optional[str] = None,
        agent_name: Optional[str] = None,
        agent_id: Optional[int] = None,
        platform: Optional[str] = None,
        round_min: Optional[int] = None,
        round_max: Optional[int] = None,
        action_type: Optional[str] = None,
        limit: int = 50,
    ) -> List[ObservedEvent]:
        """Filtre les événements selon plusieurs critères."""
        matched = []
        q_lower = query.strip().lower() if query and query.strip() else None
        name_lower = agent_name.strip().lower() if agent_name and agent_name.strip() else None
        plat_lower = platform.strip().lower() if platform and platform.strip() else None
        act_lower = action_type.strip().lower() if action_type and action_type.strip() else None

        for ev in self.events:
            if plat_lower and ev.platform.lower() != plat_lower:
                continue
            if act_lower and ev.action_type.lower() != act_lower:
                continue
            if agent_id is not None and ev.agent_id != agent_id:
                continue
            if name_lower and name_lower not in ev.agent_name.lower():
                continue
            if round_min is not None and ev.round_num < round_min:
                continue
            if round_max is not None and ev.round_num > round_max:
                continue
            if q_lower:
                # Chercher dans content, message, text des action_args ou result
                text_corpus = []
                for val in ev.action_args.values():
                    if isinstance(val, (str, int, float, bool)):
                        text_corpus.append(str(val))
                    elif isinstance(val, (list, dict)):
                        text_corpus.append(str(val))
                if ev.result:
                    text_corpus.append(str(ev.result))
                text_corpus.append(ev.agent_name)
                text_corpus.append(ev.action_type)
                combined = " ".join(text_corpus).lower()
                if q_lower not in combined:
                    continue

            matched.append(ev)
            if len(matched) >= limit:
                break

        return matched

    def to_dict(self) -> Dict[str, Any]:
        return {
            "simulation_id": self.simulation_id,
            "total_events": self.total_events,
            "events_by_platform": self.events_by_platform,
            "events_by_type": self.events_by_type,
            "events_by_agent": self.events_by_agent,
            "rounds_range": self.rounds_range,
            "events": [e.to_dict() for e in self.events],
        }

    def to_text(self, limit: int = 20) -> str:
        """Génère une synthèse textuelle structurée exploitable par le LLM."""
        lines = [
            f"=== Registre d'Événements (EvidencePack) — Simulation {self.simulation_id} ===",
            f"Total événements observés: {self.total_events}",
            f"Plateformes: {dict(self.events_by_platform)}",
            f"Types d'actions: {dict(self.events_by_type)}",
            f"Rounds couverts: {self.rounds_range[0]} à {self.rounds_range[1]}",
        ]
        if self.events:
            lines.append(f"\nÉvénements récents / représentatifs (max {limit}):")
            for i, ev in enumerate(self.events[:limit], 1):
                args_preview = ""
                if ev.action_args:
                    if "content" in ev.action_args:
                        args_preview = f": \"{str(ev.action_args['content'])[:80]}\""
                    elif "message" in ev.action_args:
                        args_preview = f": \"{str(ev.action_args['message'])[:80]}\""
                    else:
                        args_preview = f" {ev.action_args}"
                lines.append(
                    f"{i}. [{ev.event_id}] (R{ev.round_num} | {ev.platform}) "
                    f"{ev.agent_name} -> {ev.action_type}{args_preview}"
                )
        return "\n".join(lines)
