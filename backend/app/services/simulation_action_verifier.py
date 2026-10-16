"""Vérificateur de traçabilité des actions et de véracité du rapport (Story 009-4).

Ce module met en œuvre les exigences FR-7, NFR-5 et les critères C6-C7 :
  1. Chaînage et authentification des observations simulées (AC3) via les traces
     du run (`actions.jsonl`) avec identifiants stables d'événements.
  2. Règle anti-affabulation C7 (AC4) : un post d'intention simulé ne peut pas
     être promu en action observée sans événement effectif enregistré.
  3. Traitement transparent des contradictions documentaires (AC5) avec
     conservation des deux sources et mention « à confirmer » ou règle appliquée.
  4. Contrôleur de véracité des citations documentaires (AC6) par comparaison
     stricte au texte normalisé [char_start:char_end].
"""

from __future__ import annotations

import difflib
import hashlib
import json
import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from ..config import Config
from ..models.evidence_pack import EvidencePack, ObservedEvent
from ..models.report_claim import ClaimKind, ReportClaim, VerificationStatus
from ..models.source_document import (
    ConflictStatus,
    InformationOrigin,
    SourceConflict,
)
from ..utils.logger import get_logger

logger = get_logger("mirofish.simulation_action_verifier")


@dataclass(frozen=True)
class ActionEventRecord:
    """Événement d'action simulée authentifié par le journal du run (AC3)."""

    event_id: str
    simulation_id: str
    platform: str
    round_num: int
    agent_id: int
    agent_name: str
    action_type: str
    timestamp: str
    action_args: Dict[str, Any] = field(default_factory=dict)
    result: Optional[str] = None
    success: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "simulation_id": self.simulation_id,
            "platform": self.platform,
            "round": self.round_num,
            "agent_id": self.agent_id,
            "agent_name": self.agent_name,
            "action_type": self.action_type,
            "timestamp": self.timestamp,
            "action_args": self.action_args,
            "result": self.result,
            "success": self.success,
        }


@dataclass(frozen=True)
class IntentionAnalysisResult:
    """Résultat de l'analyse intention vs action pour un persona (AC4)."""

    agent_id: int
    agent_name: str
    post_content: str
    intended_action: str
    has_executed_action: bool
    status: str
    qualification: str
    matching_event_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "agent_name": self.agent_name,
            "post_content": self.post_content,
            "intended_action": self.intended_action,
            "has_executed_action": self.has_executed_action,
            "status": self.status,
            "qualification": self.qualification,
            "matching_event_id": self.matching_event_id,
        }


@dataclass(frozen=True)
class CitationVerificationResult:
    """Résultat de la vérification d'une citation textuelle (AC6)."""

    valid: bool
    exact_match: bool
    claimed_citation: str
    source_filename: Optional[str] = None
    char_start: Optional[int] = None
    char_end: Optional[int] = None
    actual_fragment: Optional[str] = None
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "valid": self.valid,
            "exact_match": self.exact_match,
            "claimed_citation": self.claimed_citation,
            "source_filename": self.source_filename,
            "char_start": self.char_start,
            "char_end": self.char_end,
            "actual_fragment": self.actual_fragment,
            "error": self.error,
        }


class SimulationActionVerifier:
    """Service d'authentification des actions et de véracité du rapport."""

    # Motifs d'intention textuelle (FR et EN).
    # Couverture étendue au-delà des 4 types initiaux (unsubscribe, boycott,
    # vote, purchase) : signature de pétition, don, partage, commentaire,
    # réclamation, dépôt de plainte. Le mapping `pattern -> action_type` reste
    # aligné sur les valeurs effectivement observées dans les journaux OASIS.
    INTENTION_PATTERNS: List[Tuple[re.Pattern, str]] = [
        # Résiliation / désabonnement
        (
            re.compile(
                r"(?:je vais|j'ai l'intention de|je compte|je prévois de|je songe à)\s+(?:résilier|me désabonner|quitter|abandonner)",
                re.IGNORECASE,
            ),
            "unsubscribe",
        ),
        (
            re.compile(
                r"(?:i will|i'm going to|i plan to|i intend to)\s+(?:cancel|unsubscribe|quit|boycott)",
                re.IGNORECASE,
            ),
            "unsubscribe",
        ),
        # Boycott
        (
            re.compile(
                r"(?:je vais|j'ai l'intention de|je compte)\s+boycotter",
                re.IGNORECASE,
            ),
            "boycott",
        ),
        # Vote
        (
            re.compile(
                r"(?:je vais|j'ai l'intention de|je compte)\s+voter",
                re.IGNORECASE,
            ),
            "vote",
        ),
        (
            re.compile(
                r"(?:i will|i'm going to|i intend to)\s+vote",
                re.IGNORECASE,
            ),
            "vote",
        ),
        # Achat / Souscription
        (
            re.compile(
                r"(?:je vais|j'ai l'intention d'|je compte)\s+(?:acheter|souscrire|commander)",
                re.IGNORECASE,
            ),
            "purchase",
        ),
        (
            re.compile(
                r"(?:i will|i'm going to|i plan to)\s+(?:buy|purchase|subscribe)",
                re.IGNORECASE,
            ),
            "purchase",
        ),
        # Pétition
        (
            re.compile(
                r"(?:je vais|j'ai l'intention de|je compte)\s+(?:signer|parrainer)\s+(?:une |la )?pétition",
                re.IGNORECASE,
            ),
            "sign_petition",
        ),
        (
            re.compile(
                r"(?:i will|i'm going to|i plan to)\s+sign\s+(?:a |the )?petition",
                re.IGNORECASE,
            ),
            "sign_petition",
        ),
        # Don
        (
            re.compile(
                r"(?:je vais|j'ai l'intention de|je compte)\s+(?:faire un don|donner|contribuer)",
                re.IGNORECASE,
            ),
            "donate",
        ),
        (
            re.compile(
                r"(?:i will|i'm going to|i plan to)\s+(?:donate|contribute|give)",
                re.IGNORECASE,
            ),
            "donate",
        ),
        # Partage / retweet
        (
            re.compile(
                r"(?:je vais|j'ai l'intention de|je compte)\s+(?:partager|relayer|retweeter)",
                re.IGNORECASE,
            ),
            "share",
        ),
        (
            re.compile(
                r"(?:i will|i'm going to|i plan to)\s+(?:share|retweet|repost)",
                re.IGNORECASE,
            ),
            "share",
        ),
        # Commentaire / réplique publique
        (
            re.compile(
                r"(?:je vais|j'ai l'intention de|je compte)\s+(?:commenter|répondre|dénoncer|condamner)",
                re.IGNORECASE,
            ),
            "comment",
        ),
        (
            re.compile(
                r"(?:i will|i'm going to|i plan to)\s+(?:comment|reply|denounce|condemn)",
                re.IGNORECASE,
            ),
            "comment",
        ),
        # Réclamation / plainte
        (
            re.compile(
                r"(?:je vais|j'ai l'intention de|je compte)\s+(?:déposer (?:une )?plainte|saisir|saisir le médiateur|réclamer|contester)",
                re.IGNORECASE,
            ),
            "file_complaint",
        ),
        (
            re.compile(
                r"(?:i will|i'm going to|i plan to)\s+(?:file a complaint|complain|appeal|contest)",
                re.IGNORECASE,
            ),
            "file_complaint",
        ),
    ]

    def __init__(self, simulation_id: Optional[str] = None):
        self.simulation_id = simulation_id or "default"
        self._action_cache: Dict[str, List[ActionEventRecord]] = {}

    @staticmethod
    def compute_event_id(
        simulation_id: str,
        platform: str,
        round_num: int,
        agent_id: int,
        action_type: str,
        timestamp: str,
    ) -> str:
        """Génère un identifiant d'événement stable et déterministe (AC3).

        Lève `ValueError` si un champ identifiant est manquant : un identifiant
        non déterministe (par exemple bâti sur `datetime.now()` quand le
        timestamp est absent) romprait la règle d'or C7, qui exige qu'un même
        événement produise toujours le même `event_id` indépendamment du
        moment du calcul.
        """
        if not timestamp or not str(timestamp).strip():
            raise ValueError(
                "compute_event_id exige un timestamp non vide pour rester "
                "déterministe (AC3) — un horodatage calculé rendrait l'identifiant "
                "fonction de l'horloge au moment du calcul."
            )
        raw = f"{simulation_id}:{platform}:{round_num}:{agent_id}:{action_type}:{timestamp}"
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
        return f"evt_{platform}_{round_num}_{agent_id}_{digest}"

    def load_simulation_actions(
        self,
        simulation_id: Optional[str] = None,
        sim_dir: Optional[str] = None,
    ) -> List[ActionEventRecord]:
        """Charge et indexe l'ensemble des événements d'actions d'un run.

        Le cache en mémoire est invalidé dès qu'un des fichiers sources a été
        modifié depuis le dernier chargement : la simulation continue d'écrire
        dans `actions.jsonl` et un cache figé rendrait la règle anti-affabulation
        C7 inactive sur les nouveaux événements.
        """
        target_sim_id = simulation_id or self.simulation_id
        target_dir = sim_dir or os.path.join(Config.UPLOAD_FOLDER, "simulations", target_sim_id)
        candidate_files = [
            ("twitter", os.path.join(target_dir, "twitter", "actions.jsonl")),
            ("reddit", os.path.join(target_dir, "reddit", "actions.jsonl")),
            ("generic", os.path.join(target_dir, "actions.jsonl")),
        ]
        latest_mtime = 0.0
        for _, file_path in candidate_files:
            if os.path.isfile(file_path):
                try:
                    latest_mtime = max(latest_mtime, os.path.getmtime(file_path))
                except OSError:
                    continue
        cached = self._action_cache.get(target_sim_id)
        if cached is not None:
            cached_mtime, cached_records = cached
            if cached_mtime >= latest_mtime:
                return cached_records

        records: List[ActionEventRecord] = []

        candidate_files = [
            ("twitter", os.path.join(target_dir, "twitter", "actions.jsonl")),
            ("reddit", os.path.join(target_dir, "reddit", "actions.jsonl")),
            ("generic", os.path.join(target_dir, "actions.jsonl")),
        ]

        for default_platform, file_path in candidate_files:
            if not os.path.isfile(file_path):
                continue
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    for line_num, line in enumerate(f, 1):
                        line_str = line.strip()
                        if not line_str:
                            continue
                        try:
                            data = json.loads(line_str)
                        except Exception:
                            continue

                        # Ne conserver que les actions effectives (ignorer round_start, simulation_end, etc.)
                        action_type = data.get("action_type")
                        if not action_type or data.get("event_type"):
                            continue

                        platform = data.get("platform") or default_platform
                        round_num = int(data.get("round", data.get("round_num", 0)))
                        agent_id = int(data.get("agent_id", 0))
                        agent_name = str(data.get("agent_name", f"Agent_{agent_id}"))
                        # Si le timestamp manque, on synthétise un identifiant
                        # déterministe à partir de la position dans le fichier
                        # (la ligne JSONL reste stable d'un rechargement à
                        # l'autre) plutôt que de tomber sur `datetime.now()`,
                        # qui romprait AC3.
                        timestamp = data.get("timestamp")
                        if not timestamp or not str(timestamp).strip():
                            logger.warning(
                                f"Action {action_type} (round {round_num}, "
                                f"agent {agent_id}) sans timestamp à la ligne "
                                f"{line_num} de {file_path} — timestamp de "
                                f"secours dérivé de la position."
                            )
                            timestamp = f"line:{line_num}:{default_platform}"
                        timestamp = str(timestamp)
                        action_args = data.get("action_args") or {}
                        result = data.get("result")
                        success = bool(data.get("success", True))

                        event_id = self.compute_event_id(
                            target_sim_id, platform, round_num, agent_id, action_type, timestamp
                        )

                        records.append(
                            ActionEventRecord(
                                event_id=event_id,
                                simulation_id=target_sim_id,
                                platform=platform,
                                round_num=round_num,
                                agent_id=agent_id,
                                agent_name=agent_name,
                                action_type=action_type,
                                timestamp=timestamp,
                                action_args=action_args,
                                result=result,
                                success=success,
                            )
                        )
            except Exception as e:
                logger.warning(f"Erreur de lecture du fichier {file_path}: {e}")

        # Tri chronologique déterministe
        records.sort(key=lambda r: (r.round_num, r.timestamp, r.event_id))
        self._action_cache[target_sim_id] = (latest_mtime, records)
        return records

    def refresh_simulation_actions(
        self,
        simulation_id: Optional[str] = None,
        sim_dir: Optional[str] = None,
    ) -> List[ActionEventRecord]:
        """Force le rechargement des actions d'un run, en ignorant le cache.

        À utiliser quand un consommateur sait que le journal a été mis à jour
        en cours de processus (par exemple après un appel à
        `PlatformActionLogger.log`).
        """
        target_sim_id = simulation_id or self.simulation_id
        self._action_cache.pop(target_sim_id, None)
        return self.load_simulation_actions(simulation_id=target_sim_id, sim_dir=sim_dir)

    def verify_observed_action(
        self,
        simulation_id: str,
        agent_id_or_name: Any,
        action_type: str,
        round_num: Optional[int] = None,
    ) -> Optional[ActionEventRecord]:
        """Vérifie si une action observée correspond à un événement effectif (AC3)."""
        actions = self.load_simulation_actions(simulation_id)
        norm_type = action_type.strip().lower()

        for act in actions:
            # Vérifier succès
            if not act.success:
                continue
            # Vérifier type
            if act.action_type.lower() != norm_type:
                continue
            # Vérifier agent
            match_agent = False
            if isinstance(agent_id_or_name, int) and act.agent_id == agent_id_or_name:
                match_agent = True
            elif str(agent_id_or_name).isdigit() and act.agent_id == int(agent_id_or_name):
                match_agent = True
            elif str(agent_id_or_name).lower() == act.agent_name.lower():
                match_agent = True

            if not match_agent:
                continue

            if round_num is not None and act.round_num != round_num:
                continue

            return act

        return None

    def analyze_intentions(
        self,
        simulation_id: str,
        posts: Optional[List[Dict[str, Any]]] = None,
    ) -> List[IntentionAnalysisResult]:
        """Détecte les déclarations d'intention et vérifie si une action a suivi (AC4)."""
        actions = self.load_simulation_actions(simulation_id)
        results: List[IntentionAnalysisResult] = []

        # Si aucun post explicite fourni, extraire les posts parmi les actions de type POST
        post_items = posts
        if post_items is None:
            post_items = []
            for act in actions:
                if act.action_type.upper() in ("CREATE_POST", "POST", "TWEET", "COMMENT"):
                    content = act.action_args.get("content", "") or str(act.result or "")
                    if content:
                        post_items.append(
                            {
                                "agent_id": act.agent_id,
                                "agent_name": act.agent_name,
                                "content": content,
                                "round_num": act.round_num,
                            }
                        )

        for p in post_items:
            content = str(p.get("content", ""))
            agent_id = int(p.get("agent_id", 0))
            agent_name = str(p.get("agent_name", f"Agent_{agent_id}"))

            for pattern, intended_action in self.INTENTION_PATTERNS:
                if pattern.search(content):
                    # Vérifier si l'agent a posé une action réelle correspondante
                    matching_event = self.verify_observed_action(
                        simulation_id, agent_id, intended_action
                    )
                    if matching_event:
                        results.append(
                            IntentionAnalysisResult(
                                agent_id=agent_id,
                                agent_name=agent_name,
                                post_content=content,
                                intended_action=intended_action,
                                has_executed_action=True,
                                status="action_observee",
                                qualification=f"Action observée et exécutée (trace: {matching_event.event_id})",
                                matching_event_id=matching_event.event_id,
                            )
                        )
                    else:
                        # RÈGLE D'OR C7 : Simple intention, AUCUNE promotion en action observée
                        results.append(
                            IntentionAnalysisResult(
                                agent_id=agent_id,
                                agent_name=agent_name,
                                post_content=content,
                                intended_action=intended_action,
                                has_executed_action=False,
                                status="intention_simulee_exprimee",
                                qualification="Intention simulée exprimée (aucune action concrète constatée dans le run)",
                                matching_event_id=None,
                            )
                        )
                    break

        return results

    def validate_report_claim(
        self,
        simulation_id: str,
        claim_text: str,
        claimed_agent: Any,
        claimed_action_type: str,
    ) -> Dict[str, Any]:
        """Vérifie une affirmation du rapport sur le comportement d'un agent (AC4)."""
        event = self.verify_observed_action(simulation_id, claimed_agent, claimed_action_type)
        if event:
            return {
                "allowed_as_observed_action": True,
                "qualification": "action_observee",
                "event_id": event.event_id,
                "message": f"Action observée vérifiée avec l'événement {event.event_id}",
            }

        # Aucune action trouvée : vérifier s'il s'agit d'une intention simulée
        intentions = self.analyze_intentions(simulation_id)
        matching_intent = next(
            (
                it
                for it in intentions
                if it.intended_action.lower() == claimed_action_type.lower()
                and (
                    it.agent_id == claimed_agent
                    or str(it.agent_id) == str(claimed_agent)
                    or it.agent_name.lower() == str(claimed_agent).lower()
                )
            ),
            None,
        )

        if matching_intent:
            return {
                "allowed_as_observed_action": False,
                "qualification": "intention_simulee_exprimee",
                "event_id": None,
                "warning": (
                    "Interdiction anti-affabulation (C7) : l'énoncé relève d'une simple intention "
                    "simulée sans trace d'action enregistrée dans actions.jsonl. "
                    "Le rapport doit impérativement le qualifier d'« intention simulée exprimée »."
                ),
                "original_claim": claim_text,
            }

        return {
            "allowed_as_observed_action": False,
            "qualification": "non_constatee",
            "event_id": None,
            "warning": (
                "Interdiction anti-affabulation (C7) : aucune trace d'action ni d'intention "
                "trouvée pour cet agent dans le run."
            ),
            "original_claim": claim_text,
        }

    @staticmethod
    def verify_citation(
        document_text: str,
        claimed_citation: str,
        char_start: Optional[int] = None,
        char_end: Optional[int] = None,
        source_filename: Optional[str] = None,
    ) -> CitationVerificationResult:
        """Contrôleur de véracité des citations documentaires (AC6).

        Garantit que toute citation attribuée à un document source correspond
        exactement au fragment normalisé sous-jacent.
        """
        if not claimed_citation or not str(claimed_citation).strip():
            return CitationVerificationResult(
                valid=False,
                exact_match=False,
                claimed_citation=claimed_citation,
                source_filename=source_filename,
                error="Citation vide ou non renseignée",
            )

        target_quote = claimed_citation.strip()

        # Cas 1 : Positions fournies -> vérification d'adéquation stricte
        if char_start is not None and char_end is not None:
            if not isinstance(char_start, int) or not isinstance(char_end, int):
                return CitationVerificationResult(
                    valid=False,
                    exact_match=False,
                    claimed_citation=claimed_citation,
                    source_filename=source_filename,
                    char_start=char_start,
                    char_end=char_end,
                    error="Les positions char_start et char_end doivent être des entiers",
                )

            if char_start < 0 or char_end > len(document_text) or char_start >= char_end:
                return CitationVerificationResult(
                    valid=False,
                    exact_match=False,
                    claimed_citation=claimed_citation,
                    source_filename=source_filename,
                    char_start=char_start,
                    char_end=char_end,
                    error=f"Positions [{char_start}:{char_end}] hors limites du texte (longueur: {len(document_text)})",
                )

            actual_fragment = document_text[char_start:char_end]
            # Comparaison stricte, octet pour octet. Une citation qui diffère
            # par un simple espace serait silencieusement validée si on
            # normalisait — c'est exactement la « citation altérée » que la
            # garantie AC6 doit refuser.
            if actual_fragment == target_quote:
                return CitationVerificationResult(
                    valid=True,
                    exact_match=True,
                    claimed_citation=claimed_citation,
                    source_filename=source_filename,
                    char_start=char_start,
                    char_end=char_end,
                    actual_fragment=actual_fragment,
                )
            return CitationVerificationResult(
                valid=False,
                exact_match=False,
                claimed_citation=claimed_citation,
                source_filename=source_filename,
                char_start=char_start,
                char_end=char_end,
                actual_fragment=actual_fragment,
                error="Altération textuelle : l'extrait à cette position diffère de la citation déclarée",
            )

        # Cas 2 : Positions non fournies -> recherche exacte dans le texte
        if target_quote in document_text:
            pos = document_text.index(target_quote)
            return CitationVerificationResult(
                valid=True,
                exact_match=True,
                claimed_citation=claimed_citation,
                source_filename=source_filename,
                char_start=pos,
                char_end=pos + len(target_quote),
                actual_fragment=target_quote,
            )

        return CitationVerificationResult(
            valid=False,
            exact_match=False,
            claimed_citation=claimed_citation,
            source_filename=source_filename,
            error="Citation textuelle non retrouvée dans le document source (citation fabriquée)",
        )

    @staticmethod
    def format_conflicts_for_report(conflicts: List[SourceConflict]) -> str:
        """Présentation transparente des contradictions documentaires (AC5).

        Conserve les deux sources contradictoires et affiche soit la règle
        appliquée, soit la mention explicite « à confirmer ».
        """
        if not conflicts:
            return "Aucune contradiction documentaire détectée sur les sources."

        lines = ["### Contradictions documentaires identifiées\n"]
        for idx, conflict in enumerate(conflicts, 1):
            lines.append(f"**Contradiction #{idx} :** {conflict.claim}")
            lines.append("- Sources en présence :")
            for ref in conflict.source_references:
                pos_info = ""
                if ref.char_start is not None and ref.char_end is not None:
                    pos_info = f" (chunk {ref.chunk_index}, pos {ref.char_start}-{ref.char_end})"
                lines.append(
                    f"  - Document `{ref.filename}` [priorité: {ref.priority}, statut: {ref.validation_status.value}]{pos_info}"
                )

            if conflict.is_resolved:
                rule_name = (
                    conflict.resolution_rule.value if conflict.resolution_rule else "déclarée"
                )
                lines.append(
                    f"- **Statut :** Résolu selon la règle `{rule_name}` (source retenue : `{conflict.resolution}`)."
                )
            else:
                lines.append(
                    "- **Statut :** **À confirmer** (aucune règle univoque appliquée, les deux thèses sont conservées)."
                )
            lines.append("")

        return "\n".join(lines)

    @classmethod
    def normalize_text_for_comparison(cls, text: str) -> str:
        """Normalise un texte pour comparaison souple de citation (espaces, ponctuation, casse)."""
        if not text:
            return ""
        # Remplacer toute ponctuation par un espace et condenser les espaces
        cleaned = re.sub(r"[^\w\s]", " ", text, flags=re.UNICODE)
        return " ".join(cleaned.lower().split())

    @classmethod
    def verify_simulated_citation(
        cls,
        agent_name: str,
        claimed_text: str,
        evidence_pack: Optional[EvidencePack] = None,
        actions: Optional[List[Any]] = None,
    ) -> Tuple[bool, bool, Optional[str]]:
        """Contrôle de conformité d'une citation simulée attribuée à un persona (AC5, Critère C4).

        Compare le texte cité aux messages effectifs publiés par l'agent dans le run.
        Retourne : (valid, exact_match, matching_event_id ou None).
        """
        if not claimed_text or not claimed_text.strip():
            return False, False, None

        target_norm = cls.normalize_text_for_comparison(claimed_text)
        target_raw = claimed_text.strip().lower()
        if not target_norm:
            return False, False, None

        name_lower = agent_name.strip().lower()

        # Extraire les événements pertinents
        candidate_events: List[Any] = []
        if evidence_pack and evidence_pack.events:
            for ev in evidence_pack.events:
                ev_agent = (ev.agent_name or "").lower()
                if name_lower in ev_agent or ev_agent in name_lower:
                    candidate_events.append(ev)
        elif actions:
            for act in actions:
                act_name = getattr(act, "agent_name", "") or (act.get("agent_name") if isinstance(act, dict) else "") or ""
                act_lower = str(act_name).strip().lower()
                if name_lower in act_lower or act_lower in name_lower:
                    candidate_events.append(act)

        for ev in candidate_events:
            # Récupérer les textes émis dans l'événement
            args = getattr(ev, "action_args", None) or (ev.get("action_args") if isinstance(ev, dict) else {}) or {}
            res = getattr(ev, "result", None) or (ev.get("result") if isinstance(ev, dict) else None)
            ev_id = getattr(ev, "event_id", None) or (ev.get("event_id") if isinstance(ev, dict) else None)

            texts_to_check: List[str] = []
            if isinstance(args, dict):
                for val in args.values():
                    if isinstance(val, str) and val.strip():
                        texts_to_check.append(val.strip())
            if isinstance(res, str) and res.strip():
                texts_to_check.append(res.strip())

            for txt in texts_to_check:
                txt_raw = txt.lower()
                txt_norm = cls.normalize_text_for_comparison(txt)

                # 1. Correspondance exacte verbatim
                if target_raw in txt_raw:
                    return True, True, ev_id

                # 2. Correspondance normalisée (ponctuation/espaces)
                if target_norm in txt_norm:
                    return True, False, ev_id

                # 3. Correspondance de quasi-égalité (légères variations sans affabulation)
                if len(txt_norm) >= 15 and len(target_norm) >= 15:
                    ratio = difflib.SequenceMatcher(None, target_norm, txt_norm).ratio()
                    if ratio >= 0.85:
                        return True, False, ev_id

        return False, False, None

    @classmethod
    def verify_report_claim(
        cls,
        claim: ReportClaim,
        evidence_pack: Optional[EvidencePack] = None,
        canonical_documents: Optional[List[Any]] = None,
        cohort_table: Optional[Any] = None,
        horizon_hours: Optional[float] = None,
    ) -> ReportClaim:
        """Vérificateur serveur déterministe d'une affirmation de rapport (AC4, Critères C4, C5, C7, C8).

        Applique les règles fondamentales :
          - Règle des personas silencieux C7 (Story 011-4) : si l'affirmation concerne un membre
            noté `is_silent` / `present_no_action`, interdiction absolue de lui attribuer une action observée.
          - Règle anti-affabulation C4 : Une affirmation OBSERVED_SOCIAL_ACTION sans event_id valide
            exécuté (is_action_executed = True) est automatiquement déclassée en REPORTED_INTENTION (UNSUPPORTED).
          - Respect de l'horizon temporel C8 (Story 011-4) : toute observation située au-delà de `horizon_hours`
            est automatiquement déclassée en SPECULATIVE_PROJECTION (UNSUPPORTED).
          - Neutralisation des métriques fantômes C8 (Story 011-4) : toute métrique péremptoire non calculable
            est déclassée en ANALYST_INFERENCE ou SPECULATIVE_PROJECTION.
          - Étanchéité épistémique C5 : Une affirmation issue d'un persona fictif ne peut être SOURCE_FACT
            ni DOCUMENTARY.
          - Contrôle verbatim des citations simulées : si une citation est invoquée sans trace dans l'evidence_pack,
            marquage UNSUPPORTED.
        """
        from .time_horizon_guard import TimeHorizonGuard

        # RÈGLE DES PERSONAS SILENCIEUX C7 (Story 011-4) :
        # Priorité absolue : un persona silencieux n'ayant produit aucune action ne peut se voir
        # imputer aucune action sociale observée (interdiction d'affabulation, marquage CONTRADICTED).
        if cohort_table and claim.agent_name:
            member = cohort_table.get_member(claim.agent_name)
            if member and member.is_silent:
                limitations = list(claim.limitations)
                limitations.append(
                    f"Règle de silence C7 : Le persona '{member.persona_name}' est consigné comme "
                    f"present_no_action (0 action observée). Aucune action ne peut lui être imputée."
                )
                return ReportClaim(
                    claim_id=claim.claim_id,
                    text=claim.text,
                    claim_kind=ClaimKind.SPECULATIVE_PROJECTION,
                    origin=InformationOrigin.HYPOTHESIS,
                    evidence_refs=[],
                    verification_status=VerificationStatus.CONTRADICTED,
                    agent_name=claim.agent_name,
                    round_num=claim.round_num,
                    confidence=0.0,
                    limitations=limitations,
                )

        # RÈGLE DU TEMPS SIMULÉ C8 (Story 011-4) :
        if horizon_hours and horizon_hours > 0:
            time_res = TimeHorizonGuard.validate_claim_time_horizon(
                claim_text=claim.text,
                horizon_hours=horizon_hours,
                round_num=claim.round_num,
            )
            if time_res.is_out_of_bounds:
                limitations = list(claim.limitations)
                limitations.append(time_res.reason or "Affirmation située au-delà de l'horizon temporel simulé.")
                return ReportClaim(
                    claim_id=claim.claim_id,
                    text=claim.text,
                    claim_kind=ClaimKind.SPECULATIVE_PROJECTION,
                    origin=InformationOrigin.HYPOTHESIS,
                    evidence_refs=list(claim.evidence_refs),
                    verification_status=VerificationStatus.UNSUPPORTED,
                    agent_name=claim.agent_name,
                    round_num=claim.round_num,
                    confidence=min(claim.confidence, 0.4),
                    limitations=limitations,
                )

        # RÈGLE DES MÉTRIQUES FANTÔMES C8 (Story 011-4) :
        metric_res = TimeHorizonGuard.detect_unsupported_quantitative_metrics(claim.text, evidence_pack)
        if metric_res.has_unsupported_metrics:
            limitations = list(claim.limitations)
            limitations.append(metric_res.reason or "Métrique quantitative non calculable dans le run.")
            new_kind = (
                ClaimKind.SPECULATIVE_PROJECTION
                if claim.claim_kind in (ClaimKind.OBSERVED_SOCIAL_ACTION, ClaimKind.SOURCE_FACT)
                else ClaimKind.ANALYST_INFERENCE
            )
            return ReportClaim(
                claim_id=claim.claim_id,
                text=claim.text,
                claim_kind=new_kind,
                origin=InformationOrigin.INFERENCE,
                evidence_refs=list(claim.evidence_refs),
                verification_status=VerificationStatus.UNSUPPORTED,
                agent_name=claim.agent_name,
                round_num=claim.round_num,
                confidence=min(claim.confidence, 0.5),
                limitations=limitations,
            )

        # Si la claim est de type OBSERVED_SOCIAL_ACTION
        if claim.claim_kind == ClaimKind.OBSERVED_SOCIAL_ACTION:
            # Événements candidats
            candidate_events: List[ObservedEvent] = []
            if evidence_pack and claim.evidence_refs:
                for ref in claim.evidence_refs:
                    matching = [e for e in evidence_pack.events if e.event_id == ref and e.is_action_executed]
                    candidate_events.extend(matching)

            if not candidate_events and evidence_pack and claim.agent_name:
                agent_lower = claim.agent_name.strip().lower()
                agent_evts = [
                    e for e in evidence_pack.events
                    if e.is_action_executed and (agent_lower in (e.agent_name or "").lower() or (e.agent_name or "").lower() in agent_lower)
                ]
                if claim.round_num is not None:
                    agent_evts = [e for e in agent_evts if e.round_num == claim.round_num]
                candidate_events = agent_evts

            # Vérifier si l'un des événements candidats est une action concrète d'exécution (et non un simple post d'intention)
            has_valid_event = False
            matching_events: List[ObservedEvent] = []

            for ev in candidate_events:
                # Si l'affirmation prétend un achat/souscription/boycott/etc. alors que l'événement est un simple POST/TWEET
                ev_type = ev.action_type.upper()
                is_pure_messaging = ev_type in ("CREATE_POST", "POST", "TWEET", "COMMENT", "MESSAGE")
                
                # Examiner le texte du post si c'est de la messagerie
                args = ev.action_args or {}
                content = str(args.get("content", "") or ev.result or "")
                has_intent_pattern = any(pat.search(content) for pat, _ in cls.INTENTION_PATTERNS)

                # Si l'événement est un post contenant une déclaration d'intention ou si la claim affirme une action transactionnelle
                claim_text_lower = claim.text.lower()
                claims_transaction = any(k in claim_text_lower for k in ("acheté", "souscrit", "payé", "commandé", "résilié", "quitté", "boycotté", "voté", "bought", "purchased", "subscribed", "canceled"))

                if is_pure_messaging and (has_intent_pattern or claims_transaction):
                    # Ce n'est pas une action concrète exécutée mais un post de parole/intention
                    continue

                has_valid_event = True
                matching_events.append(ev)

            if has_valid_event:
                new_refs = list(claim.evidence_refs)
                for ev in matching_events:
                    if ev.event_id not in new_refs:
                        new_refs.append(ev.event_id)
                return ReportClaim(
                    claim_id=claim.claim_id,
                    text=claim.text,
                    claim_kind=ClaimKind.OBSERVED_SOCIAL_ACTION,
                    origin=InformationOrigin.SIMULATION,
                    evidence_refs=new_refs,
                    verification_status=VerificationStatus.VERIFIED,
                    agent_name=claim.agent_name,
                    round_num=claim.round_num,
                    confidence=claim.confidence,
                    limitations=list(claim.limitations),
                )
            else:
                # DÉCLASSEMENT STRICT (Critère C4) :
                # Aucune action exécutée correspondante n'a été prouvée.
                limitations = list(claim.limitations)
                limitations.append(
                    "Déclassement anti-affabulation (C4) : aucune action exécutée "
                    "n'a été observée dans les traces du run pour cette affirmation."
                )
                return ReportClaim(
                    claim_id=claim.claim_id,
                    text=claim.text,
                    claim_kind=ClaimKind.REPORTED_INTENTION,
                    origin=claim.origin if claim.origin != InformationOrigin.DOCUMENTARY else InformationOrigin.HYPOTHESIS,
                    evidence_refs=list(claim.evidence_refs),
                    verification_status=VerificationStatus.UNSUPPORTED,
                    agent_name=claim.agent_name,
                    round_num=claim.round_num,
                    confidence=min(claim.confidence, 0.5),
                    limitations=limitations,
                )

        # Si la claim est de type REPORTED_INTENTION
        if claim.claim_kind == ClaimKind.REPORTED_INTENTION:
            if claim.agent_name and evidence_pack:
                # Vérifier si l'agent a au moins émis un message
                valid, exact, ev_id = cls.verify_simulated_citation(
                    agent_name=claim.agent_name,
                    claimed_text=claim.text,
                    evidence_pack=evidence_pack,
                )
                if valid:
                    new_refs = list(claim.evidence_refs)
                    if ev_id and ev_id not in new_refs:
                        new_refs.append(ev_id)
                    return ReportClaim(
                        claim_id=claim.claim_id,
                        text=claim.text,
                        claim_kind=ClaimKind.REPORTED_INTENTION,
                        origin=InformationOrigin.SIMULATION,
                        evidence_refs=new_refs,
                        verification_status=VerificationStatus.VERIFIED,
                        agent_name=claim.agent_name,
                        round_num=claim.round_num,
                        confidence=claim.confidence,
                        limitations=list(claim.limitations),
                    )

            # Intention sans citation vérifiable
            limitations = list(claim.limitations)
            if not any("citation" in lim.lower() for lim in limitations):
                limitations.append("Déclaration d'intention sans trace verbatim vérifiée dans les événements observés.")
            return ReportClaim(
                claim_id=claim.claim_id,
                text=claim.text,
                claim_kind=ClaimKind.REPORTED_INTENTION,
                origin=claim.origin,
                evidence_refs=list(claim.evidence_refs),
                verification_status=VerificationStatus.UNSUPPORTED,
                agent_name=claim.agent_name,
                round_num=claim.round_num,
                confidence=min(claim.confidence, 0.7),
                limitations=limitations,
            )

        # Si la claim est de type SOURCE_FACT
        if claim.claim_kind == ClaimKind.SOURCE_FACT:
            # BARRIÈRE ÉPISTÉMIQUE C5 (AC3) :
            # Si l'assertion concerne un persona fictif ou un brief, interdiction absolue d'être DOCUMENTARY.
            fn_refs = " ".join(claim.evidence_refs).lower()
            is_fictional_source = any(k in fn_refs for k in ("persona", "cible", "profile", "brief", "scenario"))
            if claim.origin == InformationOrigin.DOCUMENTARY and is_fictional_source:
                limitations = list(claim.limitations)
                limitations.append(
                    "Barrière épistémique C5 : transfert documentaire interdit depuis une spécification de persona fictif ou consigne de scénario."
                )
                return ReportClaim(
                    claim_id=claim.claim_id,
                    text=claim.text,
                    claim_kind=ClaimKind.SCENARIO_HYPOTHESIS,
                    origin=InformationOrigin.HYPOTHESIS,
                    evidence_refs=list(claim.evidence_refs),
                    verification_status=VerificationStatus.UNSUPPORTED,
                    agent_name=claim.agent_name,
                    round_num=claim.round_num,
                    confidence=min(claim.confidence, 0.5),
                    limitations=limitations,
                )

            status = VerificationStatus.VERIFIED if claim.evidence_refs else VerificationStatus.UNSUPPORTED
            return ReportClaim(
                claim_id=claim.claim_id,
                text=claim.text,
                claim_kind=ClaimKind.SOURCE_FACT,
                origin=claim.origin,
                evidence_refs=list(claim.evidence_refs),
                verification_status=status,
                agent_name=claim.agent_name,
                round_num=claim.round_num,
                confidence=claim.confidence,
                limitations=list(claim.limitations),
            )

        # Autres types (ANALYST_INFERENCE, SCENARIO_HYPOTHESIS, SPECULATIVE_PROJECTION)
        status = VerificationStatus.VERIFIED if claim.evidence_refs else VerificationStatus.UNSUPPORTED
        return ReportClaim(
            claim_id=claim.claim_id,
            text=claim.text,
            claim_kind=claim.claim_kind,
            origin=claim.origin,
            evidence_refs=list(claim.evidence_refs),
            verification_status=status,
            agent_name=claim.agent_name,
            round_num=claim.round_num,
            confidence=claim.confidence,
            limitations=list(claim.limitations),
        )

    @classmethod
    def check_executive_summary_bias(
        cls,
        summary_text: str,
        cohort_table: Any,
    ) -> Dict[str, Any]:
        """Contrôle anti-biais de confirmation sur la synthèse exécutive (Story 011-4, FR-07, C7).

        Vérifie qu'une synthèse n'affirme pas un consensus unanime, une adhésion totale
        ou l'absence de rejet lorsque la cohorte compte des refus (REJECTED), des hésitations
        ou des objections non résolues.
        """
        if not summary_text or not cohort_table:
            return {"has_bias": False, "warnings": [], "contradictions": []}

        summary_lower = summary_text.lower()
        warnings: List[str] = []
        contradictions: List[str] = []

        status_counts = getattr(cohort_table, "status_summary", {})
        rejected_count = status_counts.get("rejected", 0)
        hesitant_count = status_counts.get("hesitant", 0)

        # Motifs d'affirmation de consensus ou triomphe total (FR et EN)
        consensus_patterns = [
            (r"\b(?:tous\s+les\s+(?:clients|prospects|agents|utilisateurs|membres))\b", "Généralisation à l'ensemble de la cohorte"),
            (r"\b(?:adhésion|conversion)\s+(?:totale|unanime|massive\s+de\s+l'ensemble|de\s+100\s*%)\b", "Affirmation de conversion totale"),
            (r"\b(?:unanimité|aucun\s+refus|zéro\s+objection|sans\s+aucune\s+résistance)\b", "Affirmation d'unanimité absolue"),
            (r"\b(?:convertit\s+l'ensemble|emporte\s+l'adhésion\s+de\s+tous)\b", "Affirmation d'adoption universelle"),
            # Variantes anglaises (Epic 008, i18n)
            (r"\b(?:all\s+(?:clients|prospects|agents|users|members))\b", "Cohort-wide generalization"),
            (r"\b(?:total|unanimous|100%|full)\s+(?:conversion|adoption)\b", "Total conversion claim"),
            (r"\b(?:unanimity|zero\s+rejections?|no\s+rejection|zero\s+objections?|no\s+resistance)\b", "Absolute unanimity claim"),
            (r"\b(?:converts?\s+all|unanimous\s+support)\b", "Universal adoption claim"),
        ]

        if rejected_count > 0:
            for pat, desc in consensus_patterns:
                if re.search(pat, summary_lower):
                    contradictions.append(
                        f"Biais de confirmation critique : la synthèse affirme '{desc}' alors que la cohorte "
                        f"comporte {rejected_count} refus avéré(s) (ex: statuts REJECTED)."
                    )

        if hesitant_count > 0:
            hesitation_pat = r"\b(?:sans\s+hésitation|pleine\s+confiance|alignement\s+parfait|without\s+hesitation|full\s+confidence|perfect\s+alignment)\b"
            if re.search(hesitation_pat, summary_lower):
                warnings.append(
                    f"Avertissement anti-biais : la synthèse minimise les réserves alors que la cohorte "
                    f"comporte {hesitant_count} membre(s) hésitant(s)."
                )

        return {
            "has_bias": len(contradictions) > 0 or len(warnings) > 0,
            "contradictions": contradictions,
            "warnings": warnings,
        }

