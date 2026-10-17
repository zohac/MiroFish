"""Modèle de couverture de cohorte, engagement des personas et intégrité des silencieux (Story 011-4).

Ce module implémente :
  - `ScenarioRole` : typologie des rôles attribués aux acteurs dans le scénario (FR-07).
  - `DecisionStatus` : statut d'adoption ou d'engagement final simulé d'un persona.
  - `CohortMemberStatus` : état individuel immuable vérifiant la règle stricte des personas silencieux (Critère C7).
  - `CohortCoverageTable` : conteneur de cohorte avec calcul des métriques globales,
    agrégation déterministe depuis `actors.json` / `EvidencePack`, et rendu en tableau Markdown.
"""

from __future__ import annotations

import json
import os
import re
import unicodedata
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence, Set

from .actor_selection import ActorItem, ActorRole, ActorSelection
from .evidence_pack import EvidencePack, ObservedEvent
from .simulation_brief import SimulationBrief


AGENT_ALIAS_RE = re.compile(r"^agent_(\d+)$", re.IGNORECASE)


def normalize_agent_name(name: str) -> str:
    """Normalisation canonique stricte pour la comparaison nominative d'acteurs.

    Supprime les espaces surnuméraires, décompose l'Unicode (NFKD) et
    passe en minuscules sans diacritiques pour une égalité insensible
    aux accents et à la casse, mais stricte en termes de tokens complets (0 sous-chaîne).
    """
    if not name or not isinstance(name, str):
        return ""
    nfkd = unicodedata.normalize("NFKD", name.strip())
    without_accents = "".join(c for c in nfkd if not unicodedata.combining(c))
    return " ".join(without_accents.lower().split())


class AgentIdentityResolver:
    """Résolveur déterministe d'identités d'agents pour l'attribution d'événements (Story 012-1, AC1-AC5).

    Élimine 100 % des collisions par sous-chaîne (ex: Agent_1 vs Agent_16)
    et unifie les alias techniques OASIS vers leurs personas nommés réels.
    """

    def __init__(
        self,
        simulation_id: str,
        actor_selection: Optional[ActorSelection] = None,
        agent_id_map: Optional[Dict[Any, str]] = None,
    ):
        self.simulation_id = simulation_id
        # agent_id int -> canonical persona name
        self.id_to_name: Dict[int, str] = {}
        # alias canonical ("agent_1") -> canonical persona name
        self.alias_to_name: Dict[str, str] = {}
        # normalized name -> canonical persona name
        self.name_to_canonical: Dict[str, str] = {}

        # 0. Initialiser depuis agent_id_map s'il est fourni (conversion int tolérante)
        if agent_id_map:
            for aid_raw, pname in agent_id_map.items():
                aid_int: Optional[int] = None
                if aid_raw is not None:
                    try:
                        aid_int = int(aid_raw)
                    except (ValueError, TypeError):
                        aid_int = None
                self.register_persona(aid_int, pname)

        # 1. Tenter de charger simulation_config.json s'il existe
        self._load_from_simulation_config()

        # 2. Enregistrer les acteurs issus de actor_selection
        if actor_selection and actor_selection.actors:
            for item in actor_selection.actors:
                raw_status = getattr(item, "eligibility_status", None)
                status_str = raw_status.value if hasattr(raw_status, "value") else str(raw_status or "")
                if status_str.lower() == "ineligible":
                    continue
                name = item.entity_name.strip()
                if not name:
                    continue
                norm = normalize_agent_name(name)
                self.name_to_canonical[norm] = name

    def _load_from_simulation_config(self) -> None:
        """Tente de charger simulation_config.json pour lier agent_id -> entity_name."""
        if not self.simulation_id:
            return
        try:
            from ..config import Config
            sim_dir = os.path.join(Config.UPLOAD_FOLDER, "simulations", self.simulation_id)
            cfg_path = os.path.join(sim_dir, "simulation_config.json")
            if os.path.isfile(cfg_path):
                with open(cfg_path, "r", encoding="utf-8") as f:
                    cfg_data = json.load(f)
                agent_configs = cfg_data.get("agent_configs") or []
                for ac in agent_configs:
                    aid = ac.get("agent_id")
                    ename = (ac.get("entity_name") or "").strip()
                    if aid is not None and ename:
                        try:
                            aid_int = int(aid)
                        except (ValueError, TypeError):
                            continue
                        self.register_persona(aid_int, ename)
        except Exception:
            pass

    def register_persona(self, agent_id: Optional[int], persona_name: str) -> None:
        """Enregistre un persona nommé et son identifiant technique optionnel."""
        pname = persona_name.strip()
        if not pname:
            return
        norm = normalize_agent_name(pname)
        self.name_to_canonical[norm] = pname
        if agent_id is not None:
            self.id_to_name[agent_id] = pname
            self.alias_to_name[f"agent_{agent_id}"] = pname

    def resolve_event_actor(self, ev: ObservedEvent) -> str:
        """Résout le persona canonique pour un événement donné.

        Priorité stricte :
        1. ev.agent_id s'il est mappé à un persona nommé dans id_to_name
        2. ev.agent_name si c'est un alias technique Agent_X et X est dans id_to_name
        3. ev.agent_name normalisé égal strictement (==) à un persona enregistré
        4. Si ev.agent_name est de la forme Agent_X (numérique), on renvoie f"Agent_{X}" canonique
        5. Sinon, le nom d'agent nettoyé tel quel.

        Garantie : aucune correspondance par sous-chaîne (in).
        """
        # 1. Résolution par agent_id entier OASIS
        if ev.agent_id is not None and ev.agent_id in self.id_to_name:
            return self.id_to_name[ev.agent_id]

        ev_name = (ev.agent_name or "").strip()

        # 2. Vérifier si ev_name est un alias technique Agent_X
        match = AGENT_ALIAS_RE.match(ev_name)
        if match:
            aid = int(match.group(1))
            if aid in self.id_to_name:
                return self.id_to_name[aid]
            # Si pas de persona nommé associé, l'acteur canonique est Agent_{aid} strict
            return f"Agent_{aid}"

        # 3. Correspondance nominative stricte par égalité normalisée (==)
        norm_ev = normalize_agent_name(ev_name)
        if norm_ev in self.name_to_canonical:
            return self.name_to_canonical[norm_ev]

        # 4. Fallback vers le nom d'origine ou l'identifiant numérique
        if ev_name:
            return ev_name
        return f"Agent_{ev.agent_id}"


class ScenarioRole(str, Enum):
    """Rôle fonctionnel d'un membre de la cohorte au sein du scénario (Story 011-4, FR-07)."""

    PROSPECT = "PROSPECT"
    EXISTING_USER = "EXISTING_USER"
    FOUNDER = "FOUNDER"
    PRESCRIBER = "PRESCRIBER"
    OBSERVER = "OBSERVER"
    STAKEHOLDER = "STAKEHOLDER"
    UNKNOWN = "UNKNOWN"

    @classmethod
    def from_str(cls, value: Optional[str]) -> "ScenarioRole":
        """Convertit une chaîne ou rôle brut en ScenarioRole de manière robuste."""
        if not value or not isinstance(value, str):
            return cls.UNKNOWN
        val = value.strip().upper()
        for member in cls:
            if member.value == val or member.name == val:
                return member
        # Synonymes & déductions
        if any(k in val for k in ("PROSPECT", "LEAD", "CIBLE", "CLIENT_POTENTIEL")):
            return cls.PROSPECT
        if any(k in val for k in ("USER", "UTILISATEUR", "CLIENT", "EXISTING")):
            return cls.EXISTING_USER
        if any(k in val for k in ("FOUNDER", "FONDATEUR", "DIRIGEANT", "CREATOR")):
            return cls.FOUNDER
        if any(k in val for k in ("PRESCRIBER", "PRESCRIPTEUR", "EXPERT", "ADVISOR")):
            return cls.PRESCRIBER
        if any(k in val for k in ("OBSERVER", "OBSERVATEUR", "TEMOIN")):
            return cls.OBSERVER
        if any(k in val for k in ("STAKEHOLDER", "PARTENAIRE", "INVESTISSEUR", "INSTITUTION")):
            return cls.STAKEHOLDER
        return cls.UNKNOWN

    @classmethod
    def from_actor_role(cls, actor_role: Optional[ActorRole]) -> "ScenarioRole":
        """Déduit le rôle de scénario depuis l'ActorRole d'ActorSelection."""
        if not actor_role:
            return cls.UNKNOWN
        if actor_role == ActorRole.PERSON:
            return cls.PROSPECT
        if actor_role == ActorRole.ORGANIZATION:
            return cls.STAKEHOLDER
        if actor_role == ActorRole.COLLECTIVE:
            return cls.OBSERVER
        return cls.UNKNOWN


class DecisionStatus(str, Enum):
    """Statut d'adoption, de rejet ou d'engagement final d'un persona (Story 011-4, FR-07)."""

    ADOPTED = "ADOPTED"
    REJECTED = "REJECTED"
    HESITANT = "HESITANT"
    UNDECIDED = "UNDECIDED"
    PRESENT_NO_ACTION = "PRESENT_NO_ACTION"
    ABSENT_FROM_SIMULATION = "ABSENT_FROM_SIMULATION"

    @classmethod
    def from_str(cls, value: Optional[str]) -> "DecisionStatus":
        """Convertit une chaîne en DecisionStatus."""
        if not value or not isinstance(value, str):
            return cls.UNDECIDED
        val = value.strip().upper()
        for member in cls:
            if member.value == val or member.name == val:
                return member
        if any(k in val for k in ("ADOPT", "CONVERT", "VALIDE", "ACCORD")):
            return cls.ADOPTED
        if any(k in val for k in ("REJECT", "REFUS", "REJET", "ABANDON", "CONTRE")):
            return cls.REJECTED
        if any(k in val for k in ("HESIT", "REPORT", "RESERVE", "ATTENTE")):
            return cls.HESITANT
        if any(k in val for k in ("SILENT", "NO_ACTION", "AUCUNE")):
            return cls.PRESENT_NO_ACTION
        if "ABSENT" in val:
            return cls.ABSENT_FROM_SIMULATION
        return cls.UNDECIDED


@dataclass(frozen=True)
class CohortMemberStatus:
    """État individuel d'un persona dans la cohorte simulée (Story 011-4, AC1).
    
    Garantit l'immutabilité et l'intégrité de la règle C7 :
    Si action_count == 0, is_silent DOIT valoir True et decision_status DOIT valoir PRESENT_NO_ACTION.
    """

    persona_name: str
    scenario_role: ScenarioRole = ScenarioRole.UNKNOWN
    action_count: int = 0
    observed_event_ids: List[str] = field(default_factory=list)
    objections: List[str] = field(default_factory=list)
    decision_status: DecisionStatus = DecisionStatus.UNDECIDED
    is_silent: bool = False
    verbatim_citations: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        # Invariant de silence C7 :
        if self.action_count == 0 or len(self.observed_event_ids) == 0:
            object.__setattr__(self, "is_silent", True)
            if self.decision_status not in (
                DecisionStatus.PRESENT_NO_ACTION,
                DecisionStatus.ABSENT_FROM_SIMULATION,
            ):
                object.__setattr__(self, "decision_status", DecisionStatus.PRESENT_NO_ACTION)
        else:
            object.__setattr__(self, "is_silent", False)
            if self.decision_status == DecisionStatus.PRESENT_NO_ACTION:
                object.__setattr__(self, "decision_status", DecisionStatus.UNDECIDED)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "persona_name": self.persona_name,
            "scenario_role": self.scenario_role.value,
            "action_count": self.action_count,
            "observed_event_ids": list(self.observed_event_ids),
            "objections": list(self.objections),
            "decision_status": self.decision_status.value,
            "is_silent": self.is_silent,
            "verbatim_citations": list(self.verbatim_citations),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> CohortMemberStatus:
        return cls(
            persona_name=str(data.get("persona_name", "")),
            scenario_role=ScenarioRole.from_str(data.get("scenario_role")),
            action_count=int(data.get("action_count", 0)),
            observed_event_ids=[str(e) for e in (data.get("observed_event_ids") or [])],
            objections=[str(o) for o in (data.get("objections") or [])],
            decision_status=DecisionStatus.from_str(data.get("decision_status")),
            is_silent=bool(data.get("is_silent", False)),
            verbatim_citations=[str(v) for v in (data.get("verbatim_citations") or [])],
        )


@dataclass
class CohortCoverageTable:
    """Tableau de couverture consolidé de la cohorte (Story 011-4, FR-07, C7)."""

    simulation_id: str
    horizon_hours: float = 0.0
    total_rounds: int = 0
    members: List[CohortMemberStatus] = field(default_factory=list)

    @property
    def total_members(self) -> int:
        return len(self.members)

    @property
    def active_members(self) -> int:
        return sum(1 for m in self.members if not m.is_silent)

    @property
    def silent_members(self) -> int:
        return sum(1 for m in self.members if m.is_silent)

    @property
    def status_summary(self) -> Dict[str, int]:
        summary: Dict[str, int] = {}
        for m in self.members:
            key = m.decision_status.value.lower()
            summary[key] = summary.get(key, 0) + 1
        return summary

    @property
    def all_objections(self) -> List[Dict[str, Any]]:
        """Retourne la liste complète des objections répertoriées avec auteur."""
        objs = []
        for m in self.members:
            for obj in m.objections:
                objs.append({
                    "persona_name": m.persona_name,
                    "role": m.scenario_role.value,
                    "objection": obj,
                    "status": m.decision_status.value,
                })
        return objs

    def get_member(self, persona_name: str) -> Optional[CohortMemberStatus]:
        """Recherche un persona par son nom (normalisation stricte sans sous-chaîne)."""
        target = normalize_agent_name(persona_name)
        for m in self.members:
            if normalize_agent_name(m.persona_name) == target:
                return m
        return None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "simulation_id": self.simulation_id,
            "horizon_hours": self.horizon_hours,
            "total_rounds": self.total_rounds,
            "total_members": self.total_members,
            "active_members": self.active_members,
            "silent_members": self.silent_members,
            "status_summary": self.status_summary,
            "members": [m.to_dict() for m in self.members],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> CohortCoverageTable:
        members_data = data.get("members", [])
        members = [CohortMemberStatus.from_dict(m) for m in members_data]
        return cls(
            simulation_id=str(data.get("simulation_id", "")),
            horizon_hours=float(data.get("horizon_hours", 0.0)),
            total_rounds=int(data.get("total_rounds", 0)),
            members=members,
        )

    def to_markdown_table(self, locale: str = "fr") -> str:
        """Génère le tableau Markdown canonique de couverture de cohorte."""
        is_en = locale.startswith("en")
        if is_en:
            headers = [
                "| Persona | Scenario Role | Observed Actions | Major Objections | Simulated Decision | Coverage Status |",
                "|---|---|---|---|---|---|",
            ]
        else:
            headers = [
                "| Persona | Rôle Scénario | Actions Observées | Objections Majeures | Décision Simulée | Statut Couverture |",
                "|---|---|---|---|---|---|",
            ]
        rows = []
        for m in self.members:
            if m.is_silent:
                obs_text = "0 action"
                coverage_badge = "`present_no_action`"
                decision_label = "No observation" if is_en else "Aucune observation"
                objections_text = "None" if is_en else "Aucune"
            else:
                actions_label = "actions"
                events_label = "events" if is_en else "événements"
                obs_text = f"{m.action_count} {actions_label} ({len(m.observed_event_ids)} {events_label})"
                coverage_badge = "`observed_active`"
                decision_label = m.decision_status.value.replace("_", " ").title()
                if m.objections:
                    objections_text = "; ".join(m.objections)
                else:
                    objections_text = "No major objection" if is_en else "Aucune objection majeure"

            role_label = m.scenario_role.value.replace("_", " ").title()
            rows.append(
                f"| {m.persona_name} | {role_label} | {obs_text} | {objections_text} | {decision_label} | {coverage_badge} |"
            )

        return "\n".join(headers + rows)

    @classmethod
    def build_from_simulation(
        cls,
        simulation_id: str,
        actor_selection: Optional[ActorSelection] = None,
        evidence_pack: Optional[EvidencePack] = None,
        brief: Optional[SimulationBrief] = None,
        total_rounds: int = 40,
    ) -> CohortCoverageTable:
        """Agrège déterministement la cohorte depuis les acteurs et les faits observés (Story 012-1, AC1-AC5)."""
        # 1. Résolution de l'horizon (garantit un repli par défaut de 72.0h)
        from ..services.time_horizon_guard import TimeHorizonGuard

        horizon_hours = TimeHorizonGuard.parse_horizon_hours(
            brief.time_horizon if brief else None,
            default_hours=72.0,
        )

        # 2. Initialisation du résolveur d'identités et recensement des membres requis
        resolver = AgentIdentityResolver(
            simulation_id=simulation_id,
            actor_selection=actor_selection,
        )
        members_map: Dict[str, Dict[str, Any]] = {}

        if actor_selection and actor_selection.actors:
            for item in actor_selection.actors:
                # Filtrer strictement les entités inéligibles (Story 012-1, AC3)
                raw_status = getattr(item, "eligibility_status", None)
                status_str = raw_status.value if hasattr(raw_status, "value") else str(raw_status or "")
                if status_str.lower() == "ineligible":
                    continue
                name = item.entity_name.strip()
                if not name:
                    continue
                role = ScenarioRole.from_actor_role(item.qualified_role)
                norm_key = normalize_agent_name(name)
                members_map[norm_key] = {
                    "persona_name": name,
                    "scenario_role": role,
                    "actions": [],
                    "objections": [],
                    "citations": [],
                }
                resolver.register_persona(None, name)
        elif brief and brief.target_audiences:
            for aud in brief.target_audiences:
                name = aud.strip()
                if not name:
                    continue
                role = ScenarioRole.PROSPECT
                norm_key = normalize_agent_name(name)
                members_map[norm_key] = {
                    "persona_name": name,
                    "scenario_role": role,
                    "actions": [],
                    "objections": [],
                    "citations": [],
                }
                resolver.register_persona(None, name)

        # 3. Association des événements réels issus de EvidencePack (sans matching par sous-chaîne)
        if evidence_pack and evidence_pack.events:
            for ev in evidence_pack.events:
                # Résolution stricte et déterministe (AC1, AC2, AC4)
                resolved_name = resolver.resolve_event_actor(ev)
                if not resolved_name or not resolved_name.strip():
                    continue

                norm_key = normalize_agent_name(resolved_name)
                if norm_key in members_map:
                    matched_key = norm_key
                else:
                    # Persona présent dans les traces mais non pré-enregistré dans actor_selection
                    matched_key = norm_key
                    members_map[matched_key] = {
                        "persona_name": resolved_name,
                        "scenario_role": ScenarioRole.UNKNOWN,
                        "actions": [],
                        "objections": [],
                        "citations": [],
                    }
                    resolver.register_persona(ev.agent_id if ev.agent_id is not None else None, resolved_name)

                entry = members_map[matched_key]
                # Garantie d'unicité de l'événement (AC5)
                if ev.event_id and any(a.event_id == ev.event_id for a in entry["actions"]):
                    continue
                entry["actions"].append(ev)

                # Extraction d'arguments textuels récursive pour détecter les objections et citations
                def _extract_strings(obj: Any) -> List[str]:
                    collected: List[str] = []
                    if isinstance(obj, str):
                        s = obj.strip()
                        if s:
                            collected.append(s)
                    elif isinstance(obj, dict):
                        for v in obj.values():
                            collected.extend(_extract_strings(v))
                    elif isinstance(obj, (list, tuple, set)):
                        for item in obj:
                            collected.extend(_extract_strings(item))
                    return collected

                parts: List[str] = []
                if ev.action_args:
                    parts.extend(_extract_strings(ev.action_args))
                if ev.result:
                    parts.extend(_extract_strings(ev.result))
                text_content = " ".join(parts).strip()

                if text_content:
                    entry["citations"].append(text_content[:160])
                    # Détection d'objections par motifs lexicaux
                    lower_text = text_content.lower()
                    objection_markers = [
                        "trop cher", "tarif", "engagement", "refus", "complexe", "pas adapté",
                        "doute", "hésite", "trop lourd", "manque de flexibilité", "litige",
                        "onboarding", "scalabilité", "bloquant", "problème", "désaccord",
                        "too expensive", "pricing", "hesitate", "refusal", "rejection",
                    ]
                    for marker in objection_markers:
                        if marker in lower_text:
                            extracted_obj = f"Réserve sur : {marker}"
                            if extracted_obj not in entry["objections"]:
                                entry["objections"].append(extracted_obj)

        # 4. Construction des CohortMemberStatus
        built_members: List[CohortMemberStatus] = []
        for key, entry in members_map.items():
            actions: List[ObservedEvent] = entry["actions"]
            action_count = len(actions)
            ev_ids = [a.event_id for a in actions if a.event_id]

            # Inférence de la décision finale basée sur les objections et actions
            if action_count == 0:
                decision = DecisionStatus.PRESENT_NO_ACTION
            elif any("refus" in o.lower() or "trop cher" in o.lower() or "rejection" in o.lower() or "refusal" in o.lower() for o in entry["objections"]):
                decision = DecisionStatus.REJECTED
            elif entry["objections"]:
                decision = DecisionStatus.HESITANT
            else:
                decision = DecisionStatus.ADOPTED

            status = CohortMemberStatus(
                persona_name=entry["persona_name"],
                scenario_role=entry["scenario_role"],
                action_count=action_count,
                observed_event_ids=ev_ids,
                objections=entry["objections"],
                decision_status=decision,
                is_silent=(action_count == 0),
                verbatim_citations=entry["citations"][:5],
            )
            built_members.append(status)

        # Tri stable par nom
        built_members.sort(key=lambda m: m.persona_name.lower())

        return cls(
            simulation_id=simulation_id,
            horizon_hours=horizon_hours,
            total_rounds=total_rounds,
            members=built_members,
        )

    def save_to_file(self, filepath: str) -> None:
        """Sauvegarde atomique du tableau de cohorte en JSON."""
        os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
        tmp_path = f"{filepath}.tmp.{os.getpid()}"
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, filepath)
        finally:
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass

    @classmethod
    def load_from_file(cls, filepath: str) -> Optional[CohortCoverageTable]:
        """Charge un tableau de cohorte depuis le disque."""
        if not os.path.exists(filepath):
            return None
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls.from_dict(data)
