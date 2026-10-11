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