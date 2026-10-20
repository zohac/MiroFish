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
from typing import Any, Dict, List, Optional, Sequence, Set, Union

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
        # normalized name -> ScenarioRole optionnel déduit de la config
        self.name_to_role: Dict[str, ScenarioRole] = {}

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
        """Tente de charger simulation_config.json pour lier agent_id -> entity_name et rôles."""
        if not self.simulation_id:
            return
        try:
            from ..config import Config
            sim_dir = os.path.join(Config.UPLOAD_FOLDER, "simulations", self.simulation_id)
            cfg_path = os.path.join(sim_dir, "simulation_config.json")
            if os.path.isfile(cfg_path):
                with open(cfg_path, "r", encoding="utf-8") as f:
                    cfg_data = json.load(f)
                agent_configs = cfg_data.get("agent_configs") or cfg_data.get("profiles") or cfg_data.get("agents") or []
                for ac in agent_configs:
                    aid = ac.get("agent_id")
                    ename = (ac.get("entity_name") or ac.get("name") or "").strip()
                    raw_role = ac.get("scenario_role") or ac.get("role") or ac.get("entity_type")
                    role = ScenarioRole.from_str(str(raw_role)) if raw_role else None
                    aid_int: Optional[int] = None
                    if aid is not None:
                        try:
                            aid_int = int(aid)
                        except (ValueError, TypeError):
                            aid_int = None
                    if ename:
                        self.register_persona(aid_int, ename, role=role)
        except Exception:
            pass

    def register_persona(self, agent_id: Optional[int], persona_name: str, role: Optional[ScenarioRole] = None) -> None:
        """Enregistre un persona nommé, son identifiant technique et son rôle optionnel."""
        pname = persona_name.strip()
        if not pname:
            return
        norm = normalize_agent_name(pname)
        self.name_to_canonical[norm] = pname
        if role is not None and role != ScenarioRole.UNKNOWN:
            self.name_to_role[norm] = role
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

    def get_known_names(self) -> Set[str]:
        """Retourne l'ensemble des noms canoniques de personas connus (Story 012-3, AC1)."""
        names = {
            v for v in self.name_to_canonical.values()
            if v and isinstance(v, str) and v.strip()
        }
        names.update(
            v for v in self.id_to_name.values()
            if v and isinstance(v, str) and v.strip()
        )
        return names

    def resolve_name(self, candidate_name: Optional[str]) -> Optional[str]:
        """Résout un nom brut ou candidat vers son persona canonique strict (== normalisé) (Story 012-3, AC1, AC4).

        Ne réalise AUCUNE correspondance par sous-chaîne. Retourne le nom canonique si trouvé,
        ou None si non réconciliable avec les participants connus.
        """
        if not candidate_name or not isinstance(candidate_name, str):
            return None
        c_stripped = candidate_name.strip()
        if not c_stripped:
            return None

        # Alias technique Agent_X
        match = AGENT_ALIAS_RE.match(c_stripped)
        if match:
            aid = int(match.group(1))
            if aid in self.id_to_name:
                return self.id_to_name[aid]
            return None

        norm = normalize_agent_name(c_stripped)
        if norm in self.name_to_canonical:
            return self.name_to_canonical[norm]

        return None


class ScenarioRole(str, Enum):
    """Rôle fonctionnel d'un membre de la cohorte au sein du scénario (Story 011-4, FR-07, Story 012-2, FR-03)."""

    PROSPECT = "PROSPECT"
    EXISTING_USER = "EXISTING_USER"
    FOUNDER = "FOUNDER"
    TEAM_MEMBER = "TEAM_MEMBER"
    PRESCRIBER = "PRESCRIBER"
    OBSERVER = "OBSERVER"
    STAKEHOLDER = "STAKEHOLDER"
    PARTNER = "PARTNER"
    INSTITUTION = "INSTITUTION"
    UNKNOWN = "UNKNOWN"

    @classmethod
    def from_str(cls, value: Optional[str]) -> "ScenarioRole":
        """Convertit une chaîne ou rôle brut en ScenarioRole de manière robuste."""
        if not value or not isinstance(value, str):
            return cls.UNKNOWN
        val = value.strip().upper()
        if val in cls.__members__:
            return cls[val]
        for member in cls:
            if member.value == val or member.name == val:
                return member
        # Normalisation sans accent pour les synonymes
        val_norm = unicodedata.normalize("NFKD", val).encode("ASCII", "ignore").decode("utf-8")
        val = val_norm
        if any(k in val for k in ("PROSPECT", "LEAD", "CIBLE", "CLIENT_POTENTIEL")):
            return cls.PROSPECT
        if any(k in val for k in ("USER", "UTILISATEUR", "CLIENT", "EXISTING")):
            return cls.EXISTING_USER
        if any(k in val for k in ("FOUNDER", "FONDATEUR", "DIRIGEANT", "CREATOR")):
            return cls.FOUNDER
        if any(k in val for k in ("TEAM", "COLLABORATEUR", "EMPLOYE", "SALARIE", "DEVELOPPEUR", "INTERNE")):
            return cls.TEAM_MEMBER
        if any(k in val for k in ("PRESCRIBER", "PRESCRIPTEUR", "EXPERT", "ADVISOR")):
            return cls.PRESCRIBER
        if any(k in val for k in ("OBSERVER", "OBSERVATEUR", "TEMOIN")):
            return cls.OBSERVER
        if any(k in val for k in ("PARTNER", "PARTENAIRE", "ALLIE", "FOURNISSEUR", "PRESTATAIRE")):
            return cls.PARTNER
        if any(k in val for k in ("INSTITUTION", "REGULATEUR", "ORGANISME", "MINISTERE", "ETAT", "OFFICIEL")):
            return cls.INSTITUTION
        if any(k in val for k in ("STAKEHOLDER", "INVESTISSEUR", "ACTIONNAIRE")):
            return cls.STAKEHOLDER
        return cls.UNKNOWN

    @classmethod
    def from_actor_role(cls, actor_role: Optional[Union[ActorRole, str]]) -> "ScenarioRole":
        """Déduit le rôle de scénario depuis l'ActorRole d'ActorSelection (Story 012-2, AC1).
        
        Supprime le forçage aveugle ActorRole.PERSON -> ScenarioRole.PROSPECT.
        Sans qualification explicite, les personnes et rôles inconnus sont ScenarioRole.UNKNOWN.
        Supporte les instances ActorRole ou les chaînes brutes insensibles à la casse.
        """
        if not actor_role:
            return cls.UNKNOWN
        role_val = actor_role.value if isinstance(actor_role, ActorRole) else str(actor_role).strip().lower()
        if role_val == ActorRole.PERSON.value:
            return cls.UNKNOWN
        if role_val == ActorRole.ORGANIZATION.value:
            return cls.INSTITUTION
        if role_val == ActorRole.COLLECTIVE.value:
            return cls.OBSERVER
        return cls.UNKNOWN


class DecisionStatus(str, Enum):
    """Statut d'adoption, de rejet ou d'engagement final d'un persona (Story 011-4, FR-07, Story 012-2, FR-03)."""

    NOT_APPLICABLE = "NOT_APPLICABLE"
    PRESENT_NO_ACTION = "PRESENT_NO_ACTION"
    NO_DECISION = "NO_DECISION"
    INTERESTED = "INTERESTED"
    DEMO_REQUESTED = "DEMO_REQUESTED"
    HESITANT = "HESITANT"
    REJECTED_EXPRESSED = "REJECTED_EXPRESSED"
    ADOPTED_VERIFIED = "ADOPTED_VERIFIED"
    ABSENT_FROM_SIMULATION = "ABSENT_FROM_SIMULATION"
    # Rétrocompatibilité alias historiques
    ADOPTED = "ADOPTED_VERIFIED"
    REJECTED = "REJECTED_EXPRESSED"
    UNDECIDED = "NO_DECISION"

    @classmethod
    def from_str(cls, value: Optional[str]) -> "DecisionStatus":
        """Convertit une chaîne en DecisionStatus avec rétrocompatibilité transparente (Story 012-2, AC6)."""
        if not value or not isinstance(value, str):
            return cls.NO_DECISION
        val = value.strip().upper()
        if val in cls.__members__:
            return cls[val]
        # Correspondance exacte par valeur ou nom de membre
        for member in cls:
            if member.value == val or member.name == val:
                return member
        # Normalisation sans accent pour les synonymes
        val_norm = unicodedata.normalize("NFKD", val).encode("ASCII", "ignore").decode("utf-8")
        val = val_norm
        # Synonymes & correspondances historiques
        if any(k in val for k in ("NOT_APPLICABLE", "NON_APPLICABLE", "INAPPLICABLE", "N/A", "NA")):
            return cls.NOT_APPLICABLE
        if any(k in val for k in ("DEMO", "DEMONSTRATION", "CONTACT_COMMERCIAL", "DEVIS")):
            return cls.DEMO_REQUESTED
        if any(k in val for k in ("INTEREST", "INTERESSE", "CURIEUX", "EXPLORATION", "POSITIVE_INQUIRY")):
            return cls.INTERESTED
        if any(k in val for k in ("REJECTED_EXPRESSED", "REJECT", "REFUS", "REJET", "ABANDON", "CONTRE")):
            return cls.REJECTED_EXPRESSED
        if any(k in val for k in ("ADOPTED_VERIFIED", "ADOPT", "CONVERT", "VALIDE", "ACCORD", "SOUSCRIPTION")):
            return cls.ADOPTED_VERIFIED
        if any(k in val for k in ("HESIT", "REPORT", "RESERVE", "ATTENTE")):
            return cls.HESITANT
        if any(k in val for k in ("SILENT", "NO_ACTION", "AUCUNE")):
            return cls.PRESENT_NO_ACTION
        if "ABSENT" in val:
            return cls.ABSENT_FROM_SIMULATION
        if any(k in val for k in ("NO_DECISION", "UNDECIDED", "INDECIS", "NEUTRE")):
            return cls.NO_DECISION
        return cls.NO_DECISION


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
                DecisionStatus.NOT_APPLICABLE,
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
            val_lower = m.decision_status.value.lower()
            summary[val_lower] = summary.get(val_lower, 0) + 1
            # Rétrocompatibilité alias historiques pour les consommateurs existants
            if m.decision_status == DecisionStatus.REJECTED_EXPRESSED:
                summary["rejected"] = summary.get("rejected", 0) + 1
            elif m.decision_status == DecisionStatus.ADOPTED_VERIFIED:
                summary["adopted"] = summary.get("adopted", 0) + 1
            elif m.decision_status == DecisionStatus.NO_DECISION:
                summary["undecided"] = summary.get("undecided", 0) + 1
        return summary

    @property
    def prospect_members(self) -> List[CohortMemberStatus]:
        """Retourne uniquement les membres éligibles à l'adoption (exclut strictement NOT_APPLICABLE, fondateurs, institutions)."""
        return [
            m for m in self.members
            if m.decision_status != DecisionStatus.NOT_APPLICABLE
            and m.scenario_role not in (ScenarioRole.FOUNDER, ScenarioRole.TEAM_MEMBER, ScenarioRole.INSTITUTION)
        ]

    @property
    def adopted_prospects(self) -> List[CohortMemberStatus]:
        """Retourne les prospects ayant un statut d'adoption avéré."""
        return [
            m for m in self.prospect_members
            if m.decision_status == DecisionStatus.ADOPTED_VERIFIED
        ]

    @property
    def adoption_rate(self) -> float:
        """Calcule le taux d'adoption de la cohorte assaini (Story 012-2, AC5).

        Exclut strictement les membres non-clients (fondateurs, équipe interne, institutions, NOT_APPLICABLE)
        du dénominateur afin de ne pas fausser le taux de conversion réel des prospects.
        Retourne un ratio entre 0.0 et 1.0 (ou 0.0 si aucun prospect).
        """
        prospects = self.prospect_members
        if not prospects:
            return 0.0
        adopted = sum(1 for m in prospects if m.decision_status == DecisionStatus.ADOPTED_VERIFIED)
        return round(adopted / len(prospects), 4)

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
            "adoption_rate": self.adoption_rate,
            # Dénominateur du taux d'adoption, publié explicitement :
            # `adoption_rate` vaut 0.0 quand aucun prospect n'est éligible, ce
            # qui est un « non applicable » sérialisé en zéro. Sans le
            # dénominateur, un taux de 0 % et un taux indéfini sont
            # indiscernables pour le lecteur (story 013-6, revue BMAD).
            "adoption_denominator": len(self.prospect_members),
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
                if m.decision_status == DecisionStatus.NOT_APPLICABLE:
                    decision_label = "Not applicable" if is_en else "Non applicable"
                else:
                    decision_label = "No observation" if is_en else "Aucune observation"
                objections_text = "None" if is_en else "Aucune"
            else:
                actions_label = "actions"
                events_label = "events" if is_en else "événements"
                obs_text = f"{m.action_count} {actions_label} ({len(m.observed_event_ids)} {events_label})"
                coverage_badge = "`observed_active`"
                if m.decision_status == DecisionStatus.NOT_APPLICABLE:
                    decision_label = "Not applicable" if is_en else "Non applicable"
                elif m.decision_status == DecisionStatus.NO_DECISION:
                    decision_label = "No decision" if is_en else "Sans décision"
                elif m.decision_status == DecisionStatus.ADOPTED_VERIFIED:
                    decision_label = "Adopted" if is_en else "Adopté"
                elif m.decision_status == DecisionStatus.REJECTED_EXPRESSED:
                    decision_label = "Rejected"
                elif m.decision_status == DecisionStatus.DEMO_REQUESTED:
                    decision_label = "Demo requested" if is_en else "Démo demandée"
                elif m.decision_status == DecisionStatus.INTERESTED:
                    decision_label = "Interested" if is_en else "Intéressé"
                elif m.decision_status == DecisionStatus.HESITANT:
                    decision_label = "Hesitant" if is_en else "Hésitant"
                else:
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

        # 2.1 Extraction des rôles explicites issus du brief de simulation (Étape 1)
        brief_roles: Dict[str, ScenarioRole] = {}
        if brief:
            # Recherche de fondateurs dans le texte du brief ou des consignes
            founder_patterns = [
                r"(?i:\b(?:fondateur|fondatrice|fondateurs|créateur|créatrice|founder|ceo|cofondateur|cofondatrice)\s*(?:est|sont|:|de)?\s*)([A-ZÀ-ÖØ-ß][a-zA-ZÀ-ÖØ-ß0-9_\-]+(?:\s+(?!(?i:et|ou|de|du|le|la|les|un|une|qui|avec)\b)[A-ZÀ-ÖØ-ß][a-zA-ZÀ-ÖØ-ß0-9_\-]+)?)",
                r"([A-ZÀ-ÖØ-ß][a-zA-ZÀ-ÖØ-ß0-9_\-]+(?:\s+(?!(?i:et|ou|de|du|le|la|les|un|une|qui|avec)\b)[A-ZÀ-ÖØ-ß][a-zA-ZÀ-ÖØ-ß0-9_\-]+)?)\s*(?:\(|,)\s*(?i:(?:fondateur|fondatrice|founder|ceo|cofondateur|cofondatrice))",
            ]
            full_brief_text = " ".join([
                brief.goal,
                brief.initial_state,
                brief.additional_context,
                " ".join(brief.rules),
                " ".join(brief.hypotheses),
            ])
            for pat in founder_patterns:
                for match in re.finditer(pat, full_brief_text):
                    c_name = match.group(1).strip()
                    # Ne garder que des noms plausibles (pas des phrases entières)
                    if 2 <= len(c_name) <= 30 and not any(k in c_name.lower() for k in ("le ", "la ", "les ", "un ", "une ")):
                        brief_roles[normalize_agent_name(c_name)] = ScenarioRole.FOUNDER

            # Target audiences -> PROSPECT par défaut si nommés explicitement
            for aud in brief.target_audiences:
                norm_aud = normalize_agent_name(aud)
                if norm_aud and norm_aud not in brief_roles:
                    brief_roles[norm_aud] = ScenarioRole.PROSPECT

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
                norm_key = normalize_agent_name(name)

                # Résolution hiérarchique du rôle (Story 012-2, AC1) :
                # 1. Brief explicite (fondateur, target audience)
                # 2. Config d'agent OASIS (simulation_config.json)
                # 3. Qualification d'acteurs (actor_selection)
                # 4. Repli ScenarioRole.UNKNOWN (interdiction de forcer PROSPECT sans preuve)
                if norm_key in brief_roles:
                    role = brief_roles[norm_key]
                elif norm_key in resolver.name_to_role:
                    role = resolver.name_to_role[norm_key]
                else:
                    role = ScenarioRole.from_actor_role(item.qualified_role)

                members_map[norm_key] = {
                    "persona_name": name,
                    "scenario_role": role,
                    "actions": [],
                    "objections": [],
                    "citations": [],
                    "full_texts": [],
                }
                resolver.register_persona(None, name, role=role)
        elif brief and brief.target_audiences:
            for aud in brief.target_audiences:
                name = aud.strip()
                if not name:
                    continue
                norm_key = normalize_agent_name(name)
                role = brief_roles.get(norm_key, ScenarioRole.PROSPECT)
                members_map[norm_key] = {
                    "persona_name": name,
                    "scenario_role": role,
                    "actions": [],
                    "objections": [],
                    "citations": [],
                    "full_texts": [],
                }
                resolver.register_persona(None, name, role=role)

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
                    # Rôle déduit de la config ou du brief, sinon UNKNOWN
                    dyn_role = brief_roles.get(norm_key) or resolver.name_to_role.get(norm_key) or ScenarioRole.UNKNOWN
                    members_map[matched_key] = {
                        "persona_name": resolved_name,
                        "scenario_role": dyn_role,
                        "actions": [],
                        "objections": [],
                        "citations": [],
                        "full_texts": [],
                    }
                    resolver.register_persona(ev.agent_id if ev.agent_id is not None else None, resolved_name, role=dyn_role)

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

                if ev.action_args and isinstance(ev.action_args, dict):
                    explicit_obj = ev.action_args.get("objection") or ev.action_args.get("objections")
                    if explicit_obj:
                        if isinstance(explicit_obj, list):
                            for eo in explicit_obj:
                                if str(eo).strip() and str(eo).strip() not in entry["objections"]:
                                    entry["objections"].append(str(eo).strip())
                        elif str(explicit_obj).strip() and str(explicit_obj).strip() not in entry["objections"]:
                            entry["objections"].append(str(explicit_obj).strip())

                if text_content:
                    entry["citations"].append(text_content[:160])
                    entry.setdefault("full_texts", []).append(text_content)
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

        # 4. Construction des CohortMemberStatus avec qualification honnête (Story 012-2, AC2-AC4)
        # Motifs probants d'adoption vérifiée (souscription formelle, achat, contrat signé, passage à l'acte)
        ADOPTION_PROOF_PATTERNS = [
            r"\b(?:souscri\w+|souscription|ach[eè]t\w+|achat|abonn\w+|abonnement|sign[ée]\w*\s+le\s+contrat|valid[ée]\w*\s+la\s+commande|pass(?:é|er?|e)\s+commande)\b",
            r"\b(?:subscrib\w+|purchas\w+|bought|signed\s+the\s+contract|order\s+confirmed|placed\s+an?\s+order)\b",
            r"\b(?:pass[ée]\s+au\s+plan|migr[ée]\s+sur|adopt[ée]\s+définitivement|converted\s+to\s+paid)\b",
        ]
        # Motifs de demande de démo ou contact commercial
        DEMO_REQUEST_PATTERNS = [
            r"\b(?:demand\w+\s+(?:une\s+|de\s+|d['\x27]une\s+)?d[eé]mo|souhait\w+\s+(?:une\s+)?d[eé]mo|prendre\s+rendez-vous|planifier\s+un\s+[eé]change|contact\s+commercial|devis)\b",
            r"\b(?:demo\s+request|request(?:ed|ing)?\s+a\s+demo|schedule\s+a\s+call|sales\s+contact|quote\s+request)\b",
        ]
        # Motifs d'intérêt exploratoire
        INTEREST_PATTERNS = [
            r"\b(?:int[eé]ress\w+|tr[eè]s\s+prometteur|bonne\s+initiative|curieu[sx]\s+d['\x27]en\s+savoir\s+plus|[aà]\s+suivre|bravo)\b",
            r"\b(?:interesting|promising|looks\s+great|curious\s+to\s+know\s+more|worth\s+watching)\b",
        ]

        built_members: List[CohortMemberStatus] = []
        for key, entry in members_map.items():
            actions: List[ObservedEvent] = entry["actions"]
            action_count = len(actions)
            ev_ids = [a.event_id for a in actions if a.event_id]
            role = entry["scenario_role"]

            # Règle AC2 : les fondateurs, membres internes et institutions sont NOT_APPLICABLE
            if role in (ScenarioRole.FOUNDER, ScenarioRole.TEAM_MEMBER, ScenarioRole.INSTITUTION):
                decision = DecisionStatus.NOT_APPLICABLE
            elif action_count == 0:
                decision = DecisionStatus.PRESENT_NO_ACTION
            elif any("refus" in o.lower() or "trop cher" in o.lower() or "rejection" in o.lower() or "refusal" in o.lower() for o in entry["objections"]):
                decision = DecisionStatus.REJECTED_EXPRESSED
            elif entry["objections"]:
                decision = DecisionStatus.HESITANT
            else:
                # Analyse probante des textes d'actions (Anti-Affabulation AC3, AC4)
                full_text = " ".join(entry.get("full_texts") or entry["citations"]).lower()
                is_adopted = any(re.search(pat, full_text) for pat in ADOPTION_PROOF_PATTERNS)
                is_demo = any(re.search(pat, full_text) for pat in DEMO_REQUEST_PATTERNS)
                is_interested = any(re.search(pat, full_text) for pat in INTEREST_PATTERNS)

                if is_adopted:
                    decision = DecisionStatus.ADOPTED_VERIFIED
                elif is_demo:
                    decision = DecisionStatus.DEMO_REQUESTED
                elif is_interested:
                    decision = DecisionStatus.INTERESTED
                else:
                    # Règle anti-affabulation absolue C3 : activité sans objection = NO_DECISION, JAMAIS ADOPTED
                    decision = DecisionStatus.NO_DECISION

            status = CohortMemberStatus(
                persona_name=entry["persona_name"],
                scenario_role=role,
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
