"""Contexte de simulation versionné et persistant (story 009-2, ADR 0013).

`additional_context` est aujourd'hui lu par l'API, passé à la génération
d'ontologie, puis **perdu** : `Project` ne le persiste pas. Ce modèle rend le
brief complet sérialisable, et le champ perdu devient un champ comme les autres.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

#: Version du schéma du brief. Le champ est persisté avec le brief et permet de
#: distinguer une écriture d'un lot antérieur d'une écriture courante.
SIMULATION_BRIEF_SCHEMA_VERSION = 1


class SimulationBriefError(ValueError):
    """Brief de simulation incohérent ou illisible."""


def _clean_text(value: Any, field_name: str, *, required: bool = False) -> str:
    """Normalise un texte, en distinguant l'absence du contenu vide."""

    if value is None:
        if required:
            raise SimulationBriefError(f"{field_name} est requis")
        return ""
    if not isinstance(value, str):
        raise SimulationBriefError(f"{field_name} doit être une chaîne")
    return value.strip()


def _clean_str_list(value: Any, field_name: str) -> List[str]:
    """Normalise une liste de consignes, en refusant une valeur non-liste.

    Un champ liste qui reçoit une chaîne nue est un bug d'appelant : il est
    refusé plutôt que transformé en liste d'un élément, parce que
    `"règle_a, règle_b"` deviendrait silencieusement une seule consigne.
    """

    if value is None:
        return []
    if isinstance(value, str):
        raise SimulationBriefError(
            f"{field_name} doit être une liste de chaînes, pas une chaîne"
        )
    if not isinstance(value, (list, tuple)):
        raise SimulationBriefError(f"{field_name} doit être une liste de chaînes")

    cleaned: List[str] = []
    for item in value:
        if item is None:
            continue
        if not isinstance(item, str):
            raise SimulationBriefError(
                f"{field_name} ne contient que des chaînes, reçu : {type(item).__name__}"
            )
        stripped = item.strip()
        if stripped:
            cleaned.append(stripped)
    return cleaned


@dataclass
class SimulationBrief:
    """Contexte de simulation versionné, consigne minimale et champs avancés.

    Le mode simple ne rend **aucun** champ avancé obligatoire : un brief
    minimal — `goal` seule, alimentée par la consigne existante — est un brief
    valide. Les champs avancés s'ajoutent sans casser les appels existants.
    """

    goal: str
    initial_state: str = ""
    target_audiences: List[str] = field(default_factory=list)
    excluded_actors: List[str] = field(default_factory=list)
    rules: List[str] = field(default_factory=list)
    hypotheses: List[str] = field(default_factory=list)
    additional_context: str = ""
    schema_version: int = SIMULATION_BRIEF_SCHEMA_VERSION
    time_horizon: str = ""
    trigger_event: str = ""
    expected_outputs: List[str] = field(default_factory=list)
    source_document_ids: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.goal = _clean_text(self.goal, "goal", required=True)
        if not self.goal:
            raise SimulationBriefError("goal ne peut pas être vide")

        self.initial_state = _clean_text(self.initial_state, "initial_state")
        self.additional_context = _clean_text(self.additional_context, "additional_context")
        self.time_horizon = _clean_text(self.time_horizon, "time_horizon")
        self.trigger_event = _clean_text(self.trigger_event, "trigger_event")

        self.target_audiences = _clean_str_list(self.target_audiences, "target_audiences")
        self.excluded_actors = _clean_str_list(self.excluded_actors, "excluded_actors")
        self.rules = _clean_str_list(self.rules, "rules")
        self.hypotheses = _clean_str_list(self.hypotheses, "hypotheses")
        self.expected_outputs = _clean_str_list(self.expected_outputs, "expected_outputs")
        self.source_document_ids = _clean_str_list(
            self.source_document_ids, "source_document_ids"
        )

        if isinstance(self.schema_version, bool) or not isinstance(self.schema_version, int):
            raise SimulationBriefError("schema_version doit être un entier")
        if self.schema_version < 1:
            raise SimulationBriefError("schema_version doit être >= 1")

    def to_dict(self) -> Dict[str, Any]:
        """Sérialisation complète : aucun champ n'est omis (AC6)."""

        return {
            "goal": self.goal,
            "initial_state": self.initial_state,
            "target_audiences": list(self.target_audiences),
            "excluded_actors": list(self.excluded_actors),
            "rules": list(self.rules),
            "hypotheses": list(self.hypotheses),
            "additional_context": self.additional_context,
            "schema_version": self.schema_version,
            "time_horizon": self.time_horizon,
            "trigger_event": self.trigger_event,
            "expected_outputs": list(self.expected_outputs),
            "source_document_ids": list(self.source_document_ids),
        }

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> Optional["SimulationBrief"]:
        """Relit un brief sérialisé.

        Un projet ancien sans brief n'est pas un brief : `from_dict` accepte
        `None` et renvoie `None`, plutôt que de fabriquer une consigne.
        """

        if data is None:
            return None
        if not isinstance(data, dict):
            raise SimulationBriefError("un brief se relit depuis un dictionnaire")

        return cls(
            goal=data.get("goal", ""),
            initial_state=data.get("initial_state", ""),
            target_audiences=data.get("target_audiences", []),
            excluded_actors=data.get("excluded_actors", []),
            rules=data.get("rules", []),
            hypotheses=data.get("hypotheses", []),
            additional_context=data.get("additional_context", ""),
            schema_version=data.get("schema_version", SIMULATION_BRIEF_SCHEMA_VERSION),
            time_horizon=data.get("time_horizon", ""),
            trigger_event=data.get("trigger_event", ""),
            expected_outputs=data.get("expected_outputs", []),
            source_document_ids=data.get("source_document_ids", []),
        )

    def is_minimal(self) -> bool:
        """Vrai si le brief se réduit à la consigne : c'est le mode simple.

        `source_document_ids` est volontairement ignoré : l'API le remplit
        toujours, et une liste de références n'est pas une consigne avancée. Le
        mode simple resterait sinon « minimal » uniquement sans document.
        """

        return not any(
            (
                self.initial_state,
                self.target_audiences,
                self.excluded_actors,
                self.rules,
                self.hypotheses,
                self.additional_context,
                self.time_horizon,
                self.trigger_event,
                self.expected_outputs,
            )
        )

    def advanced_text(self) -> str:
        """Champs avancés rendus en texte, pour les étapes qui les consomment.

        Le `goal` en est volontairement absent : il est transmis séparément, et
        le dupliquer ici ferait deux consignes là où l'utilisateur n'en a écrit
        qu'une.
        """

        sections: List[str] = []
        if self.time_horizon:
            sections.append(f"Horizon : {self.time_horizon}")
        if self.trigger_event:
            sections.append(f"Déclencheur : {self.trigger_event}")
        if self.initial_state:
            sections.append(f"État initial : {self.initial_state}")
        if self.target_audiences:
            sections.append(
                "Audiences cibles : " + ", ".join(self.target_audiences)
            )
        if self.excluded_actors:
            sections.append(
                "Acteurs exclus : " + ", ".join(self.excluded_actors)
            )
        if self.rules:
            sections.append("Règles : " + " ; ".join(self.rules))
        if self.hypotheses:
            sections.append("Hypothèses : " + " ; ".join(self.hypotheses))
        if self.expected_outputs:
            sections.append("Sorties attendues : " + ", ".join(self.expected_outputs))
        if self.additional_context:
            sections.append(f"Contexte supplémentaire : {self.additional_context}")
        return "\n".join(sections)

    def instructions_text(self) -> str:
        """Bloc de consignes destiné aux prompts.

        Il est **distinct** du texte documentaire : NFR-5 impose que les consignes
        de l'utilisateur et le contenu des fichiers ne soient jamais confondus
        dans la même zone d'un message.
        """

        lines = ["## Consignes de simulation (données de l'utilisateur)"]
        lines.append(f"Objectif : {self.goal}")
        advanced = self.advanced_text()
        if advanced:
            lines.append(advanced)
        return "\n".join(lines)


def build_minimal_brief(
    goal: str,
    additional_context: Optional[str] = None,
    source_document_ids: Optional[List[str]] = None,
) -> SimulationBrief:
    """Construit le brief du mode simple à partir de la consigne existante."""

    return SimulationBrief(
        goal=goal,
        additional_context=additional_context or "",
        source_document_ids=list(source_document_ids or []),
    )


@dataclass(frozen=True)
class InferredHorizonResult:
    """Résultat de l'extraction ou de l'inférence traçable d'horizon temporel (Story 012-5, AC3 / QA-11)."""

    time_horizon: str
    is_inferred: bool
    source_mention: Optional[str] = None
    diagnostics: List[str] = field(default_factory=list)


def extract_inferred_horizon(
    goal_text: Optional[str],
    current_horizon: Optional[str] = None,
) -> InferredHorizonResult:
    r"""Extrait ou infère de manière traçable l'horizon temporel depuis le champ goal si time_horizon est vide (AC3).

    Regex universelle : \b(\d+(?:[.,]\d+)?)\s*(h|heures?|hours?|j|jours?|days?|semaines?|weeks?|mois|months?)\b
    Si un horizon explicite est déjà fourni (non vide et non 'unknown'), il est conservé.
    Sinon, recherche dans goal_text :
      - Si trouvé : affecte la forme normalisée avec trace d'inférence.
      - Si non trouvé : affecte 'unknown' avec diagnostic explicite sans champ silencieusement vide.
    """
    import re

    cleaned_cur = str(current_horizon or "").strip()
    if cleaned_cur and cleaned_cur.lower() not in ("unknown", "inconnu", "none", "null", ""):
        return InferredHorizonResult(
            time_horizon=cleaned_cur,
            is_inferred=False,
            source_mention=None,
            diagnostics=[],
        )

    text = str(goal_text or "").strip()
    if not text:
        return InferredHorizonResult(
            time_horizon="unknown",
            is_inferred=False,
            source_mention=None,
            diagnostics=["Aucun texte d'objectif fourni pour inférer l'horizon temporel."],
        )

    # Regex universelle temporelle (heures, jours, semaines, mois)
    pattern = re.compile(
        r"\b(\d+(?:[.,]\d+)?)\s*(h(?:eures?)?|hours?|j(?:ours?)?|days?|semaines?|weeks?|mois|months?)\b",
        re.IGNORECASE,
    )
    match = pattern.search(text)
    if match:
        num_str = match.group(1).replace(",", ".")
        unit_str = match.group(2).lower()

        # Normalisation standard de l'unité
        if unit_str.startswith("h"):
            normalized_unit = "h"
        elif unit_str.startswith("j") or unit_str.startswith("day"):
            normalized_unit = "j"
        elif unit_str.startswith("sem") or unit_str.startswith("week"):
            normalized_unit = "semaine" if num_str in ("1", "1.0", "1,0") else "semaines"
        elif unit_str.startswith("moi") or unit_str.startswith("month"):
            normalized_unit = "mois"
        else:
            normalized_unit = unit_str

        # Format normalisé compact (ex: 72h, 3j, 2 semaines, 1 mois)
        inferred = f"{num_str}{normalized_unit}" if normalized_unit in ("h", "j") else f"{num_str} {normalized_unit}"
        raw_mention = match.group(0)
        return InferredHorizonResult(
            time_horizon=inferred,
            is_inferred=True,
            source_mention=raw_mention,
            diagnostics=[f"Horizon '{inferred}' inféré depuis le texte de consigne ('{raw_mention}')."],
        )

    return InferredHorizonResult(
        time_horizon="unknown",
        is_inferred=False,
        source_mention=None,
        diagnostics=["Aucune indication temporelle identifiable dans l'objectif : horizon marqué 'unknown'."],
    )


@dataclass(frozen=True)
class BriefAuditDiagnostic:
    """Diagnostic structuré d'audit sur l'intégrité et la structuration du brief (AC3)."""

    code: str
    field_name: str
    severity: str  # "warning" | "info"
    message: str


@dataclass
class BriefAuditResult:
    """Résultat de l'audit d'intégrité du brief (Story 012-5, AC3 / QA-11)."""

    has_lacunae: bool = False
    inferred_time_horizon: Optional[str] = None
    diagnostics: List[BriefAuditDiagnostic] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "has_lacunae": self.has_lacunae,
            "inferred_time_horizon": self.inferred_time_horizon,
            "diagnostics": [
                {
                    "code": d.code,
                    "field_name": d.field_name,
                    "severity": d.severity,
                    "message": d.message,
                }
                for d in self.diagnostics
            ],
        }


def audit_brief(brief: Optional[SimulationBrief]) -> BriefAuditResult:
    """Audite la complétude et l'intégrité structurée d'un brief de simulation (QA-11).

    Identifie les champs vides non renseignés (règles, audiences, horizon temporel)
    et procède à l'inférence traçable de l'horizon pour interdire les omissions silencieuses.
    """
    result = BriefAuditResult()
    if brief is None:
        result.has_lacunae = True
        result.diagnostics.append(
            BriefAuditDiagnostic(
                code="BRIEF_MISSING",
                field_name="simulation_brief",
                severity="warning",
                message="Aucun brief de simulation structuré n'est rattaché au projet.",
            )
        )
        return result

    # 1. Horizon temporel
    if not brief.time_horizon or brief.time_horizon.strip().lower() in ("", "unknown", "inconnu", "none", "null"):
        inferred_res = extract_inferred_horizon(brief.goal, brief.time_horizon)
        result.inferred_time_horizon = inferred_res.time_horizon
        if inferred_res.is_inferred:
            result.diagnostics.append(
                BriefAuditDiagnostic(
                    code="TIME_HORIZON_INFERRED",
                    field_name="time_horizon",
                    severity="info",
                    message=(
                        f"Le champ time_horizon était vide. Inférence traçable appliquée : "
                        f"'{inferred_res.time_horizon}' (trouvé dans goal)."
                    ),
                )
            )
        else:
            result.has_lacunae = True
            result.diagnostics.append(
                BriefAuditDiagnostic(
                    code="TIME_HORIZON_UNKNOWN",
                    field_name="time_horizon",
                    severity="warning",
                    message="time_horizon absent et indétectable dans l'objectif : marqué 'unknown'.",
                )
            )

    # 2. Audiences cibles et règles
    if not brief.target_audiences:
        result.has_lacunae = True
        result.diagnostics.append(
            BriefAuditDiagnostic(
                code="TARGET_AUDIENCES_EMPTY",
                field_name="target_audiences",
                severity="warning",
                message="Aucune audience cible structurée n'est déclarée dans le brief.",
            )
        )

    if not brief.rules:
        result.diagnostics.append(
            BriefAuditDiagnostic(
                code="RULES_EMPTY",
                field_name="rules",
                severity="info",
                message="Aucune règle négative ou contrainte spécifique définie dans le brief.",
            )
        )

    return result