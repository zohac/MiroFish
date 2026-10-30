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
from dataclasses import dataclass, field, replace
from typing import Any, Dict, List, Optional, Set, Tuple

from ..config import Config
from ..models.evidence_pack import EvidencePack, ObservedEvent
from ..models.provenance_regime import ProvenanceRegime
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

    # Motifs compilés Unicode pour la concordance des familles d'interaction (Story 015-1, D8 / BMAD)
    APPROVAL_CLAIM_RE = re.compile(
        r"\b(?<!n['’])(?<!ne\s)(?:aime|aiment|aimé|liké|like|upvote|approuve|approuvé|likes|liked|upvoted|approved)\b",
        re.IGNORECASE | re.UNICODE,
    )
    DISAPPROVAL_CLAIM_RE = re.compile(
        r"\b(?:désapprouve|désapprouvent|downvote|downvotes|downvoted|dislike|dislikes|disliked|n['’]aime\s+pas|n['’]aiment\s+pas|n['’]a\s+pas\s+aimé|n['’]ont\s+pas\s+aimé)\b",
        re.IGNORECASE | re.UNICODE,
    )
    FOLLOW_CLAIM_RE = re.compile(
        r"\b(?<!comme\s)(?<!s['’]en\s)(?<!ce qui\s)(?<!qui\s)(?:(?:le|la|les)\s+suit|(?:suit|suivent)\s+(?:le\s+compte|la\s+page|[A-ZÀ-ÖØ-ß][\wÀ-ÿ'-]+)|suivi|s['’]abonne|s['’]abonnent|abonné|abonnée|abonnés|abonnées|follows?|followed)\b",
        re.IGNORECASE | re.UNICODE,
    )
    UNFOLLOW_CLAIM_RE = re.compile(
        r"\b(?:ne\s+suit\s+plus|ne\s+suivent\s+plus|n['’]a\s+pas\s+suivi|n['’]ont\s+pas\s+suivi|s['’]est\s+désabonné|s['’]est\s+désabonnée|se\s+sont\s+désabonnés|se\s+désabonne|se\s+désabonnent|désabonné|désabonnée|désabonnés|unfollows?|unfollowed|mutes?|muted)\b",
        re.IGNORECASE | re.UNICODE,
    )
    REPOST_CLAIM_RE = re.compile(
        r"\b(?:republie|republient|republié|repost|reposts|reposté|retweet|retweets|retweeté|partage|partagent|partagé)\b",
        re.IGNORECASE | re.UNICODE,
    )

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
    def check_company_facts_contradiction(
        cls,
        claim_text: str,
        canonical_documents: Optional[List[Any]],
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """Vérifie si une allégation d'un agent d'entreprise contredit un fait canonique validé (QA-12, AC5).

        Générique (NFR-1) : Sans terme en dur spécifique à une simulation d'audit.
        Retourne (is_contradicted, conflict_reason, conflicting_source_filename).
        """
        if not claim_text or not canonical_documents:
            return False, None, None

        from ..models.source_document import (
            DocumentValidationStatus,
            EpistemicSourceKind,
            _content_terms,
            _polarity,
        )

        claim_pol = _polarity(claim_text)
        claim_terms = _content_terms(claim_text)
        if not claim_terms:
            return False, None, None

        for doc_item in canonical_documents:
            # Inspection d'un document ou d'un fragment
            doc_dict = doc_item if isinstance(doc_item, dict) else (
                doc_item.to_dict() if hasattr(doc_item, "to_dict") else {}
            )
            v_status = doc_dict.get("validation_status")
            if hasattr(v_status, "value"):
                v_status = v_status.value
            v_status_str = str(v_status or "").lower()

            # Uniquement documents ou fragments validés
            if v_status_str != DocumentValidationStatus.VALIDATED.value:
                continue

            epistemic = doc_dict.get("epistemic_kind")
            if hasattr(epistemic, "value"):
                epistemic = epistemic.value
            epistemic_str = str(epistemic or "").upper()
            if epistemic_str not in (
                EpistemicSourceKind.CANONICAL_DOCUMENT.value,
                "CANONICAL_DOCUMENT",
            ):
                continue

            doc_fn = str(
                doc_dict.get("filename")
                or getattr(doc_item, "filename", None)
                or doc_dict.get("source_filename")
                or getattr(doc_item, "source_filename", None)
                or "source_canonique"
            )
            doc_text = str(
                doc_dict.get("text")
                or getattr(doc_item, "text", None)
                or doc_dict.get("content")
                or getattr(doc_item, "content", None)
                or ""
            )
            if not doc_text:
                continue

            # Découper en phrases ou propositions pour comparaison de polarité
            propositions = re.split(r"(?<=\D)\.(?=\s|\Z)|[\n;!]+", doc_text)
            for prop in propositions:
                prop_cleaned = prop.strip()
                if not prop_cleaned or len(prop_cleaned) < 10:
                    continue
                prop_terms = _content_terms(prop_cleaned)
                if not prop_terms:
                    continue

                # Intersection significative de termes : au moins 2 termes partagés ou 1 terme si court
                shared = claim_terms & prop_terms
                min_shared = 1 if (len(claim_terms) <= 2 or len(prop_terms) <= 2) else 2
                if len(shared) >= min_shared:
                    prop_pol = _polarity(prop_cleaned)
                    # Contradiction stricte de polarité sur le même objet
                    if {claim_pol, prop_pol} == {"positive", "negative"}:
                        reason = (
                            f"Contradiction formelle avec la source canonique validée '{doc_fn}' : "
                            f"l'assertion affirme '{claim_text.strip()}' en opposition directe avec "
                            f"'{prop_cleaned}'."
                        )
                        return True, reason, doc_fn

        return False, None, None

    @classmethod
    def normalize_text_for_comparison(cls, text: str) -> str:
        """Normalise un texte pour comparaison souple de citation (espaces, ponctuation, casse)."""
        if not text:
            return ""
        # Remplacer toute ponctuation par un espace et condenser les espaces
        cleaned = re.sub(r"[^\w\s]", " ", text, flags=re.UNICODE)
        return " ".join(cleaned.lower().split())

    @classmethod
    def verify_interview_citation(
        cls,
        claim: ReportClaim,
        report_interviews: Any,
        resolver: Optional[Any] = None,
    ) -> Optional[ReportClaim]:
        """Authentifie une citation ou déclaration d'entretien par répondant (Story 015-2).

        Garanties strictes :
          - Jamais de promotion en ClaimKind.OBSERVED_SOCIAL_ACTION ni en InformationOrigin.SIMULATION.
          - Jamais asserted_as_action = True.
          - VERIFIED (+ turn_id) si la citation/8-gramme appartient au bon répondant résolu.
          - CONTRADICTED (confidence=0.0, evidence_refs=[]) si la citation/8-gramme appartient à un autre répondant.
          - UNSUPPORTED si citation entre guillemets altérée/fabriquée, référence ivw_* inexistante,
            ou déclaration non rattachable à un tour individuel.
        """
        from dataclasses import replace
        from ..models.cohort_coverage import normalize_agent_name
        from ..models.report_interviews import ReportInterviewsPayload

        payload = report_interviews
        if not isinstance(payload, ReportInterviewsPayload):
            try:
                payload = ReportInterviewsPayload.from_raw(payload)
            except Exception:
                return None

        if payload is None:
            return None

        claim_agent = claim.agent_name
        active_resolver = resolver
        resolved_claim_agent = (
            active_resolver.resolve_name(claim_agent)
            if active_resolver and claim_agent
            else claim_agent
        ) or claim_agent
        norm_claim_agent = normalize_agent_name(resolved_claim_agent) if resolved_claim_agent else None

        all_turns = payload.get_all_turns()

        # Extraire les références ivw_* explicites présentes dans claim.evidence_refs ou claim.text
        explicit_ivw_refs: List[str] = []
        for ref in claim.evidence_refs:
            if ref.startswith("ivw_"):
                explicit_ivw_refs.append(ref)
        for m in re.finditer(r"\b(ivw_[a-z0-9_]+)\b", claim.text):
            r = m.group(1)
            if r not in explicit_ivw_refs:
                explicit_ivw_refs.append(r)

        # 1. Contrôle des références explicites ivw_*
        explicit_turn_constraint: Optional[str] = None
        if explicit_ivw_refs:
            for ivw_ref in explicit_ivw_refs:
                found_match = None
                is_turn_ref = "_t" in ivw_ref
                if is_turn_ref:
                    explicit_turn_constraint = ivw_ref

                for sess, t in all_turns:
                    if t.turn_id == ivw_ref:
                        found_match = (sess, t)
                        break
                    elif sess.interview_id == ivw_ref:
                        # Pour une référence de session, chercher en priorité le tour du répondant ciblé
                        t_agent = (
                            active_resolver.resolve_name(t.persona_name)
                            if active_resolver
                            else t.persona_name
                        ) or t.persona_name
                        norm_t_agent = normalize_agent_name(t_agent)
                        if norm_claim_agent and norm_t_agent == norm_claim_agent:
                            found_match = (sess, t)
                            break
                        elif found_match is None:
                            found_match = (sess, t)

                if found_match:
                    sess, t = found_match
                    t_agent = (
                        active_resolver.resolve_name(t.persona_name)
                        if active_resolver
                        else t.persona_name
                    ) or t.persona_name
                    norm_t_agent = normalize_agent_name(t_agent)

                    # Si attribué à un autre répondant
                    if norm_claim_agent and norm_t_agent and norm_claim_agent != norm_t_agent:
                        limitations = list(claim.limitations)
                        limitations.append(
                            f"Contradiction d'attribution d'entretien (Story 015-2) : la référence "
                            f"'{ivw_ref}' appartient à '{t.persona_name}' (turn_id '{t.turn_id}'), "
                            f"non à '{resolved_claim_agent}'."
                        )
                        return replace(
                            claim,
                            claim_kind=ClaimKind.REPORTED_INTENTION,
                            origin=InformationOrigin.INFERENCE,
                            evidence_refs=[],
                            verification_status=VerificationStatus.CONTRADICTED,
                            confidence=0.0,
                            limitations=limitations,
                            provenance_regime=ProvenanceRegime.INTERVIEW,
                            asserted_as_action=False,
                        )
                else:
                    # Référence ivw_* inexistante dans le registre
                    limitations = list(claim.limitations)
                    limitations.append(
                        f"Référence d'entretien introuvable (Story 015-2) : '{ivw_ref}' "
                        f"n'existe pas dans le journal des entretiens de rédaction."
                    )
                    return replace(
                        claim,
                        claim_kind=ClaimKind.REPORTED_INTENTION,
                        origin=InformationOrigin.INFERENCE,
                        evidence_refs=[],
                        verification_status=VerificationStatus.UNSUPPORTED,
                        confidence=min(claim.confidence, 0.5),
                        limitations=limitations,
                        provenance_regime=ProvenanceRegime.INTERVIEW,
                        asserted_as_action=False,
                    )

        # Extraire les citations entre guillemets
        raw_quotes: List[str] = []
        for q_m in re.finditer(r'[«“"「]([^»”"」]{4,})[»”"」]', claim.text):
            q_clean = q_m.group(1).strip()
            if q_clean:
                raw_quotes.append(q_clean)

        # Déterminer si ce claim est sous régime INTERVIEW ou éligible au rattrapage
        is_interview_regime = (
            claim.provenance_regime == ProvenanceRegime.INTERVIEW
            or str(getattr(claim.provenance_regime, "value", claim.provenance_regime)) == "interview"
            or bool(explicit_ivw_refs)
        )

        def normalize_exact_slice(s: str) -> str:
            # Normalisation typographique bijective pour recherche contiguë
            s = s.replace("’", "'").replace("\u00a0", " ").replace("“", '"').replace("”", '"')
            return " ".join(s.split()).lower()

        # Helper pour tester la présence en tranche exacte avec repli ponctuation
        def find_exact_in_text(quote_str: str, full_text: str) -> bool:
            if not quote_str or not full_text:
                return False
            q_norm = normalize_exact_slice(quote_str)
            t_norm = normalize_exact_slice(full_text)
            if not q_norm or not t_norm:
                return False

            def matches(q: str, t: str) -> bool:
                if len(q) < 8:
                    return bool(re.search(rf"\b{re.escape(q)}\b", t, flags=re.IGNORECASE))
                return q in t

            if matches(q_norm, t_norm):
                return True

            q_stripped = q_norm.rstrip(".!?,;:。！？，；：")
            if q_stripped and q_stripped != q_norm:
                if matches(q_stripped, t_norm):
                    return True

            return False

        # Helper pour 8-grammes (tokenisation sans ponctuation)
        def get_8grams(text_str: str) -> set:
            cleaned = re.sub(r"[^\w\s]", " ", text_str.lower(), flags=re.UNICODE)
            words = cleaned.split()
            if len(words) < 8:
                return set()
            return {" ".join(words[i:i + 8]) for i in range(len(words) - 7)}

        claim_8grams = get_8grams(claim.text)
        searchable_turns = (
            [(sess, t) for sess, t in all_turns if t.turn_id == explicit_turn_constraint]
            if explicit_turn_constraint
            else all_turns
        )

        # Cas A : Présence de citations entre guillemets
        if raw_quotes:
            matched_own_turn_ids: List[str] = []
            quote_found_on_other: Optional[Tuple[str, str]] = None
            all_quotes_valid_for_own = True

            for quote in raw_quotes:
                # Filtrer les guillemets courts hors régime interview
                if not is_interview_regime and (len(quote) < 12 or len(quote.split()) < 3):
                    continue

                quote_matched_own = False
                for sess, t in searchable_turns:
                    t_agent = (
                        active_resolver.resolve_name(t.persona_name)
                        if active_resolver
                        else t.persona_name
                    ) or t.persona_name
                    norm_t_agent = normalize_agent_name(t_agent)

                    is_own = (norm_claim_agent is None) or (norm_t_agent == norm_claim_agent)

                    if find_exact_in_text(quote, t.answer_text):
                        if is_own:
                            quote_matched_own = True
                            if t.turn_id not in matched_own_turn_ids:
                                matched_own_turn_ids.append(t.turn_id)

                if not quote_matched_own:
                    all_quotes_valid_for_own = False
                    for sess, t in all_turns:
                        t_agent = (
                            active_resolver.resolve_name(t.persona_name)
                            if active_resolver
                            else t.persona_name
                        ) or t.persona_name
                        norm_t_agent = normalize_agent_name(t_agent)
                        is_own = (norm_claim_agent is None) or (norm_t_agent == norm_claim_agent)
                        if not is_own and find_exact_in_text(quote, t.answer_text):
                            if quote_found_on_other is None:
                                quote_found_on_other = (t.persona_name, t.turn_id)

            # Si toutes les citations ont été validées chez le bon répondant
            if matched_own_turn_ids and all_quotes_valid_for_own:
                clean_refs = [r for r in claim.evidence_refs if not r.startswith("evt_")]
                for tid in matched_own_turn_ids:
                    if tid not in clean_refs:
                        clean_refs.append(tid)
                return replace(
                    claim,
                    claim_kind=ClaimKind.REPORTED_INTENTION,
                    origin=InformationOrigin.INFERENCE,
                    evidence_refs=clean_refs,
                    verification_status=VerificationStatus.VERIFIED,
                    limitations=list(claim.limitations),
                    provenance_regime=ProvenanceRegime.INTERVIEW,
                    asserted_as_action=False,
                )

            # Si une citation appartient en réalité à un autre répondant
            if quote_found_on_other and norm_claim_agent:
                other_name, other_turn_id = quote_found_on_other
                limitations = list(claim.limitations)
                limitations.append(
                    f"Contradiction d'attribution d'entretien (Story 015-2) : la citation entre guillemets "
                    f"appartient en réalité à '{other_name}' (turn_id '{other_turn_id}'), non à '{resolved_claim_agent}'."
                )
                return replace(
                    claim,
                    claim_kind=ClaimKind.REPORTED_INTENTION,
                    origin=InformationOrigin.INFERENCE,
                    evidence_refs=[],
                    verification_status=VerificationStatus.CONTRADICTED,
                    confidence=0.0,
                    limitations=limitations,
                    provenance_regime=ProvenanceRegime.INTERVIEW,
                    asserted_as_action=False,
                )

            # Si régime interview ou tentative de citation d'entretien infructueuse
            if is_interview_regime:
                limitations = list(claim.limitations)
                limitations.append(
                    "Citation d'entretien non conforme (Story 015-2) : l'extrait entre guillemets "
                    "n'a pas été retrouvé en tranche exacte dans les réponses d'entretien "
                    f"attribuées à '{resolved_claim_agent}' (altération lexicale/numérique ou propos non tenu)."
                )
                return replace(
                    claim,
                    claim_kind=ClaimKind.REPORTED_INTENTION,
                    origin=InformationOrigin.INFERENCE,
                    evidence_refs=[],
                    verification_status=VerificationStatus.UNSUPPORTED,
                    confidence=min(claim.confidence, 0.5),
                    limitations=limitations,
                    provenance_regime=ProvenanceRegime.INTERVIEW,
                    asserted_as_action=False,
                )

        # Cas B : Déclarations d'entretien sans guillemets sous régime INTERVIEW (8-grammes)
        if is_interview_regime:
            matched_own_turn_ids = []
            matched_other_turn: Optional[Tuple[str, str]] = None

            if claim_8grams:
                for sess, t in searchable_turns:
                    t_agent = (
                        active_resolver.resolve_name(t.persona_name)
                        if active_resolver
                        else t.persona_name
                    ) or t.persona_name
                    norm_t_agent = normalize_agent_name(t_agent)
                    is_own = (norm_claim_agent is None) or (norm_t_agent == norm_claim_agent)

                    t_8grams = get_8grams(t.answer_text)
                    if claim_8grams & t_8grams and is_own:
                        if t.turn_id not in matched_own_turn_ids:
                            matched_own_turn_ids.append(t.turn_id)

                if not matched_own_turn_ids:
                    for sess, t in all_turns:
                        t_agent = (
                            active_resolver.resolve_name(t.persona_name)
                            if active_resolver
                            else t.persona_name
                        ) or t.persona_name
                        norm_t_agent = normalize_agent_name(t_agent)
                        is_own = (norm_claim_agent is None) or (norm_t_agent == norm_claim_agent)
                        t_8grams = get_8grams(t.answer_text)
                        if claim_8grams & t_8grams and not is_own:
                            if matched_other_turn is None:
                                matched_other_turn = (t.persona_name, t.turn_id)

            if matched_own_turn_ids:
                clean_refs = [r for r in claim.evidence_refs if not r.startswith("evt_")]
                for tid in matched_own_turn_ids:
                    if tid not in clean_refs:
                        clean_refs.append(tid)
                return replace(
                    claim,
                    claim_kind=ClaimKind.REPORTED_INTENTION,
                    origin=InformationOrigin.INFERENCE,
                    evidence_refs=clean_refs,
                    verification_status=VerificationStatus.VERIFIED,
                    limitations=list(claim.limitations),
                    provenance_regime=ProvenanceRegime.INTERVIEW,
                    asserted_as_action=False,
                )

            if matched_other_turn and norm_claim_agent:
                other_name, other_turn_id = matched_other_turn
                limitations = list(claim.limitations)
                limitations.append(
                    f"Contradiction d'attribution d'entretien (Story 015-2) : les propos tenus "
                    f"correspondent au tour de parole de '{other_name}' (turn_id '{other_turn_id}'), non à '{resolved_claim_agent}'."
                )
                return replace(
                    claim,
                    claim_kind=ClaimKind.REPORTED_INTENTION,
                    origin=InformationOrigin.INFERENCE,
                    evidence_refs=[],
                    verification_status=VerificationStatus.CONTRADICTED,
                    confidence=0.0,
                    limitations=limitations,
                    provenance_regime=ProvenanceRegime.INTERVIEW,
                    asserted_as_action=False,
                )

            # Déclaration d'entretien sans tour de parole individuel vérifié (ou issue du résumé global)
            limitations = list(claim.limitations)
            limitations.append(
                "Entretien non vérifiable par tour individuel (Story 015-2) : aucun tour de parole "
                f"correspondant n'a été validé pour '{resolved_claim_agent}'."
            )
            return replace(
                claim,
                claim_kind=ClaimKind.REPORTED_INTENTION,
                origin=InformationOrigin.INFERENCE,
                evidence_refs=[],
                verification_status=VerificationStatus.UNSUPPORTED,
                confidence=min(claim.confidence, 0.5),
                limitations=limitations,
                provenance_regime=ProvenanceRegime.INTERVIEW,
                asserted_as_action=False,
            )

        return None


    @classmethod
    def verify_simulated_citation(
        cls,
        agent_name: str,
        claimed_text: str,
        evidence_pack: Optional[EvidencePack] = None,
        actions: Optional[List[Any]] = None,
        resolver: Optional[Any] = None,
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

        # Extraire les événements pertinents (Story 012-3 : égalité stricte, résolution univoque sans collision)
        from ..models.cohort_coverage import AgentIdentityResolver, normalize_agent_name

        active_resolver = resolver
        if active_resolver is None and evidence_pack and evidence_pack.simulation_id:
            try:
                active_resolver = AgentIdentityResolver(simulation_id=evidence_pack.simulation_id)
            except Exception:
                active_resolver = None

        resolved_agent = (
            active_resolver.resolve_name(agent_name)
            if active_resolver
            else agent_name
        ) or agent_name
        norm_target_agent = normalize_agent_name(resolved_agent)

        candidate_events: List[Any] = []
        if evidence_pack and evidence_pack.events:
            for ev in evidence_pack.events:
                if active_resolver:
                    resolved_ev = active_resolver.resolve_event_actor(ev)
                    ev_norm = normalize_agent_name(resolved_ev)
                else:
                    ev_agent = getattr(ev, "agent_name", "") or ""
                    ev_norm = normalize_agent_name(ev_agent)
                if ev_norm == norm_target_agent:
                    candidate_events.append(ev)
        elif actions:
            for act in actions:
                act_name = getattr(act, "agent_name", "") or (act.get("agent_name") if isinstance(act, dict) else "") or ""
                if active_resolver:
                    resolved_act = active_resolver.resolve_name(str(act_name)) or str(act_name)
                    act_norm = normalize_agent_name(resolved_act)
                else:
                    act_norm = normalize_agent_name(str(act_name))
                if act_norm == norm_target_agent:
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
        resolver: Optional[Any] = None,
        report_interviews: Optional[Any] = None,
        persona_profiles: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> ReportClaim:
        """Vérificateur serveur déterministe d'une affirmation de rapport (AC4, Critères C4, C5, C7, C8).

        Applique les règles fondamentales :
          - Préservation de provenance_regime et traçabilité asserted_as_action (Story 015-1, D1, D3).
          - Règle des personas silencieux C7 (Story 011-4) : si l'affirmation concerne un membre
            noté `is_silent` / `present_no_action`, interdiction absolue de lui attribuer une action observée.
          - Règle anti-affabulation C4 : Une affirmation OBSERVED_SOCIAL_ACTION sans event_id valide
            exécuté (is_action_executed = True) est automatiquement déclassée en REPORTED_INTENTION (UNSUPPORTED).
          - Réconciliation déterministe (Story 012-3, AC4) : Résolution univoque de l'acteur via
            AgentIdentityResolver (ou normalize_agent_name ==), 0 sous-chaîne `in`.
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
        from ..models.cohort_coverage import AgentIdentityResolver, normalize_agent_name

        is_interview = (
            claim.provenance_regime == ProvenanceRegime.INTERVIEW
            or str(getattr(claim.provenance_regime, "value", claim.provenance_regime)) == "interview"
        )
        was_asserted_action = (not is_interview) and bool(
            getattr(claim, "asserted_as_action", False)
            or claim.claim_kind == ClaimKind.OBSERVED_SOCIAL_ACTION
        )

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
                return replace(
                    claim,
                    claim_kind=ClaimKind.SPECULATIVE_PROJECTION,
                    origin=InformationOrigin.HYPOTHESIS,
                    evidence_refs=[],
                    verification_status=VerificationStatus.CONTRADICTED,
                    confidence=0.0,
                    limitations=limitations,
                    asserted_as_action=was_asserted_action,
                )

        # CONTRAT DE FAITS NON NÉGOCIABLES DE L'ENTREPRISE (QA-12, Story 012-5, AC5) :
        # Si un agent incarnant l'entreprise (FOUNDER, TEAM_MEMBER) émet une allégation contraire
        # à une source canonique validée, marquage immédiat CONTRADICTED (COMPANY_FACT_CONTRADICTION).
        if canonical_documents and claim.agent_name:
            agent_role = None
            if cohort_table:
                member = cohort_table.get_member(claim.agent_name)
                if member and hasattr(member, "scenario_role"):
                    agent_role = member.scenario_role
            if agent_role is None and resolver:
                agent_role = resolver.get_role(claim.agent_name)

            from ..models.cohort_coverage import ScenarioRole
            role_enum = ScenarioRole.from_str(str(agent_role or ""))
            if role_enum in (ScenarioRole.FOUNDER, ScenarioRole.TEAM_MEMBER):
                is_contradicted, reason, src_fn = cls.check_company_facts_contradiction(
                    claim.text, canonical_documents
                )
                if is_contradicted:
                    limitations = list(claim.limitations)
                    limitations.append(
                        f"Contrat de faits de l'entreprise (AC5 / QA-12) : Allégation d'un agent incarnant "
                        f"l'entreprise ({role_enum.value}) en contradiction avec la source validée '{src_fn}'. "
                        f"{reason}"
                    )
                    evidence_refs = list(claim.evidence_refs)
                    if src_fn and src_fn not in evidence_refs:
                        evidence_refs.append(src_fn)
                    # Sceau INTERVIEW (D4) : même sur QA-12, un entretien ne devient jamais OBSERVED_SOCIAL_ACTION
                    forced_kind = (
                        ClaimKind.REPORTED_INTENTION
                        if is_interview
                        else ClaimKind.OBSERVED_SOCIAL_ACTION
                    )
                    return replace(
                        claim,
                        claim_kind=forced_kind,
                        origin=InformationOrigin.SIMULATION,
                        evidence_refs=evidence_refs,
                        verification_status=VerificationStatus.CONTRADICTED,
                        confidence=0.0,
                        limitations=limitations,
                        asserted_as_action=was_asserted_action,
                    )

        # CONTRÔLE BIOGRAPHIQUE AVAL FICHES PERSONAS ↔ PROSE FINALE (Story 015-6, D2, D3, FR-07, C6, AT-11) :
        if persona_profiles and claim.agent_name:
            resolved_agent_name = (
                resolver.resolve_name(claim.agent_name) if resolver else claim.agent_name
            ) or claim.agent_name
            from .brief_consistency import check_claim_persona_biography
            is_bio_contradicted, bio_reason = check_claim_persona_biography(
                claim_text=claim.text,
                agent_name=resolved_agent_name,
                profiles_by_name=persona_profiles,
            )
            if is_bio_contradicted:
                limitations = list(claim.limitations)
                limitations.append(bio_reason)
                # Préserver strictement provenance_regime et ne jamais promouvoir un entretien en OBSERVED_SOCIAL_ACTION
                forced_kind = (
                    ClaimKind.REPORTED_INTENTION
                    if is_interview
                    else (claim.claim_kind or ClaimKind.REPORTED_INTENTION)
                )
                return replace(
                    claim,
                    claim_kind=forced_kind,
                    origin=claim.origin,
                    evidence_refs=list(claim.evidence_refs),
                    verification_status=VerificationStatus.CONTRADICTED,
                    confidence=0.0,
                    limitations=limitations,
                    asserted_as_action=was_asserted_action,
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
                return replace(
                    claim,
                    claim_kind=ClaimKind.SPECULATIVE_PROJECTION,
                    origin=InformationOrigin.HYPOTHESIS,
                    evidence_refs=list(claim.evidence_refs),
                    verification_status=VerificationStatus.UNSUPPORTED,
                    confidence=min(claim.confidence, 0.4),
                    limitations=limitations,
                    asserted_as_action=was_asserted_action,
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
            return replace(
                claim,
                claim_kind=new_kind,
                origin=InformationOrigin.INFERENCE,
                evidence_refs=list(claim.evidence_refs),
                verification_status=VerificationStatus.UNSUPPORTED,
                confidence=min(claim.confidence, 0.5),
                limitations=limitations,
                asserted_as_action=was_asserted_action,
            )

        # Si la claim est de type OBSERVED_SOCIAL_ACTION
        if claim.claim_kind == ClaimKind.OBSERVED_SOCIAL_ACTION:
            # Sceau d'entretien absolu (Story 014-1, D4) : si un appelant direct a passé
            # OBSERVED_SOCIAL_ACTION sous ProvenanceRegime.INTERVIEW, reclassement immédiat.
            if is_interview:
                limitations = list(claim.limitations)
                limitations.append(
                    "Sceau d'entretien (Story 014-1 / 015-1) : un passage issu d'un entretien "
                    "ne peut être qualifié d'action sociale observée dans la simulation."
                )
                return replace(
                    claim,
                    claim_kind=ClaimKind.REPORTED_INTENTION,
                    origin=InformationOrigin.INFERENCE,
                    verification_status=VerificationStatus.UNSUPPORTED,
                    confidence=min(claim.confidence, 0.7),
                    limitations=limitations,
                    asserted_as_action=False,
                )

            active_resolver = resolver
            if active_resolver is None and evidence_pack and evidence_pack.simulation_id:
                try:
                    active_resolver = AgentIdentityResolver(simulation_id=evidence_pack.simulation_id)
                except Exception:
                    active_resolver = None

            norm_claim_agent = None
            if claim.agent_name:
                resolved_claim_agent = (
                    active_resolver.resolve_name(claim.agent_name)
                    if active_resolver
                    else claim.agent_name
                ) or claim.agent_name
                norm_claim_agent = normalize_agent_name(resolved_claim_agent)

            # Événements candidats et références explicites (D7)
            candidate_events: List[ObservedEvent] = []
            valid_evidence_refs: List[str] = []
            explicit_ev_refs = [r for r in claim.evidence_refs if str(r).startswith("evt_")]
            has_explicit_ev_refs = len(explicit_ev_refs) > 0

            if evidence_pack and explicit_ev_refs:
                for ref in explicit_ev_refs:
                    matching = [e for e in evidence_pack.events if e.event_id == ref and e.is_action_executed]
                    for m_ev in matching:
                        if norm_claim_agent:
                            m_name = (
                                active_resolver.resolve_event_actor(m_ev)
                                if active_resolver
                                else (m_ev.agent_name or "")
                            )
                            if normalize_agent_name(m_name) != norm_claim_agent:
                                continue
                        candidate_events.append(m_ev)
                        if ref not in valid_evidence_refs:
                            valid_evidence_refs.append(ref)

                # D7 : Propriété stricte sans repli silencieux si des evt_* explicites étaient fournis
                # mais qu'aucun n'appartient à l'acteur ou n'est exécuté dans l'EvidencePack.
                if not candidate_events:
                    limitations = list(claim.limitations)
                    limitations.append(
                        f"Propriété d'événement (Story 015-1, FR-02) : les identifiants d'événements "
                        f"référencés {explicit_ev_refs} sont introuvables ou n'appartiennent pas à l'acteur "
                        f"résolu '{norm_claim_agent or claim.agent_name}'. Rejet strict sans repli."
                    )
                    clean_refs = [r for r in claim.evidence_refs if not str(r).startswith("evt_")]
                    return replace(
                        claim,
                        claim_kind=ClaimKind.REPORTED_INTENTION,
                        origin=claim.origin if claim.origin != InformationOrigin.DOCUMENTARY else InformationOrigin.HYPOTHESIS,
                        evidence_refs=clean_refs,
                        verification_status=VerificationStatus.UNSUPPORTED,
                        confidence=min(claim.confidence, 0.5),
                        limitations=limitations,
                        asserted_as_action=was_asserted_action,
                    )

            # Résolution d'acteur sans collision (Story 012-3, AC4) :
            # Uniquement activée en l'absence de références evt_* explicites
            if not has_explicit_ev_refs and not candidate_events and evidence_pack and norm_claim_agent:
                agent_evts: List[ObservedEvent] = []
                for e in evidence_pack.events:
                    if not e.is_action_executed:
                        continue
                    if active_resolver:
                        resolved_ev_name = active_resolver.resolve_event_actor(e)
                        if normalize_agent_name(resolved_ev_name) == norm_claim_agent:
                            agent_evts.append(e)
                    else:
                        if normalize_agent_name(e.agent_name or "") == norm_claim_agent:
                            agent_evts.append(e)

                # Priorité au round mentionné si précisé
                if claim.round_num is not None:
                    round_evts = [e for e in agent_evts if e.round_num == claim.round_num]
                    if round_evts:
                        agent_evts = round_evts

                candidate_events = agent_evts

            # Vérifier si l'un des événements candidats est une action concrète d'exécution (et non un simple post d'intention)
            has_valid_event = False
            matching_events: List[ObservedEvent] = []
            claim_text_lower = claim.text.lower()
            raw_transaction_detected = any(k in claim_text_lower for k in (
                "acheté", "souscrit", "payé", "commandé", "résilié", "quitté", "boycotté", "voté",
                "bought", "purchased", "subscribed", "canceled", "cancelled", "ordered", "paid"
            ))
            # Si le texte exprime un refus, une hésitation ou une négation explicite, ce n'est pas une affirmation de transaction réussie
            has_refusal_or_negation = any(k in claim_text_lower for k in (
                "refus", "refusé", "refuse", "n'a pas", "ne souhaite pas", "ne compte pas",
                "n'a point", "sans souscrire", "sans acheter", "hésite", "hesite",
                "refused", "refuses", "did not", "does not", "without subscribing", "without buying"
            ))
            claims_transaction = raw_transaction_detected and not has_refusal_or_negation

            # Extraire les citations entre guillemets du claim (« ... » ou " ... ")
            quote_matches = re.findall(r'[«"“]([^»"”]{4,})[»"”]', claim.text)

            # D8 : Familles d'action OASIS
            passive_event_types = {"DO_NOTHING", "REFRESH", "SIGN_UP", "SEARCH_POSTS", "SEARCH_USER", "TREND"}
            messaging_event_types = {"CREATE_POST", "POST", "TWEET", "COMMENT", "CREATE_COMMENT", "QUOTE_POST", "MESSAGE"}
            approval_event_types = {"LIKE_POST", "LIKE_COMMENT", "UPVOTE", "UPVOTE_POST", "UPVOTE_COMMENT"}
            disapproval_event_types = {"DISLIKE_POST", "DISLIKE_COMMENT", "DOWNVOTE", "DOWNVOTE_POST", "DOWNVOTE_COMMENT"}
            follow_event_types = {"FOLLOW"}
            unfollow_event_types = {"UNFOLLOW", "MUTE"}
            repost_event_types = {"REPOST", "RETWEET"}
            transaction_event_types = {"SUBSCRIBE", "BUY", "PURCHASE", "ORDER", "PAY"}

            claim_expresses_disapproval = bool(cls.DISAPPROVAL_CLAIM_RE.search(claim.text))
            claim_expresses_approval = bool(cls.APPROVAL_CLAIM_RE.search(claim.text)) and not claim_expresses_disapproval
            claim_expresses_unfollow = bool(cls.UNFOLLOW_CLAIM_RE.search(claim.text))
            claim_expresses_follow = bool(cls.FOLLOW_CLAIM_RE.search(claim.text)) and not claim_expresses_unfollow
            claim_expresses_repost = bool(cls.REPOST_CLAIM_RE.search(claim.text))

            for ev in candidate_events:
                ev_type = ev.action_type.upper()

                # 1. Événements techniques passifs : rejet absolu (D8.1)
                if ev_type in passive_event_types:
                    continue

                args = ev.action_args or {}
                content = str(args.get("content", "") or ev.result or "")
                has_intent_pattern = any(pat.search(content) for pat, _ in cls.INTENTION_PATTERNS)

                # 2. Messagerie textuelle (D8.2)
                if ev_type in messaging_event_types:
                    if has_intent_pattern or claims_transaction:
                        continue

                    # Contrôle sémantique et textuel :
                    if quote_matches:
                        quote_matched = False
                        for q in quote_matches:
                            q_norm = cls.normalize_text_for_comparison(q)
                            c_norm = cls.normalize_text_for_comparison(content)
                            if q.lower() in content.lower() or (len(q_norm) >= 8 and q_norm in c_norm):
                                quote_matched = True
                                break
                            if len(q_norm) >= 15 and len(c_norm) >= 15:
                                if difflib.SequenceMatcher(None, q_norm, c_norm).ratio() >= 0.80:
                                    quote_matched = True
                                    break
                        if not quote_matched:
                            continue
                    else:
                        words_in_claim = re.findall(r"\b\w{3,}\b", claim.text.lower(), re.UNICODE)
                        stop_words = {
                            "round", "tour", "agent", "post", "tweet", "message", "reddit", "twitter",
                            "cette", "dans", "pour", "avec", "sans", "suite", "afin", "alors", "après",
                            "selon", "fait", "faire", "plus", "très", "bien", "aussi", "avoir", "être",
                            "publié", "tweeté", "posté", "commenté", "réagi", "déclaré", "exprimé",
                            "posted", "tweeted", "commented", "replied", "reacted", "son", "ses", "des",
                            "les", "une", "par", "sur", "aux", "leur", "leurs", "qui", "que", "dont",
                        }
                        if claim.agent_name:
                            for part in claim.agent_name.lower().split():
                                stop_words.add(part)
                                stop_words.add(cls.normalize_text_for_comparison(part))

                        meaningful_words = [
                            w for w in words_in_claim
                            if w not in stop_words and cls.normalize_text_for_comparison(w) not in stop_words
                        ]

                        if meaningful_words and content:
                            c_norm = cls.normalize_text_for_comparison(content)
                            c_lower = content.lower()
                            matched_words = [
                                w for w in meaningful_words
                                if w in c_lower or cls.normalize_text_for_comparison(w) in c_norm
                            ]
                            min_required = 1 if len(meaningful_words) <= 3 else 2
                            if len(matched_words) < min_required:
                                continue
                        elif meaningful_words and not content:
                            continue

                # 3. Interactions sociales non textuelles (D8.3)
                elif ev_type in approval_event_types:
                    if claims_transaction or not claim_expresses_approval:
                        continue
                elif ev_type in disapproval_event_types:
                    if claims_transaction or not claim_expresses_disapproval:
                        continue
                elif ev_type in follow_event_types:
                    if claims_transaction or not claim_expresses_follow:
                        continue
                elif ev_type in unfollow_event_types:
                    if claims_transaction or not claim_expresses_unfollow:
                        continue
                elif ev_type in repost_event_types:
                    if claims_transaction or not claim_expresses_repost:
                        continue

                # 4. Transactions métier dédiées (D8.4)
                elif ev_type in transaction_event_types:
                    if not claims_transaction:
                        continue
                else:
                    # Événement inconnu ou non supporté : rejet strict fail-closed (D8)
                    continue

                has_valid_event = True
                matching_events.append(ev)

            if has_valid_event:
                clean_refs = [r for r in claim.evidence_refs if not str(r).startswith("evt_")]
                new_refs = list(clean_refs)
                for ref in valid_evidence_refs:
                    if ref not in new_refs:
                        new_refs.append(ref)
                for ev in matching_events:
                    if ev.event_id not in new_refs:
                        new_refs.append(ev.event_id)
                return replace(
                    claim,
                    claim_kind=ClaimKind.OBSERVED_SOCIAL_ACTION,
                    origin=InformationOrigin.SIMULATION,
                    evidence_refs=new_refs,
                    verification_status=VerificationStatus.VERIFIED,
                    limitations=list(claim.limitations),
                    asserted_as_action=True,
                )
            else:
                # DÉCLASSEMENT STRICT (Critère C4, AC5) :
                limitations = list(claim.limitations)
                if claims_transaction:
                    limitations.append(
                        "Déclassement anti-affabulation (C4) transactionnelle (AC5) : les événements "
                        "de messagerie sociale ne peuvent prouver une transaction métier (achat/souscription) "
                        "en l'absence d'événement applicatif dédié."
                    )
                else:
                    limitations.append(
                        "Déclassement anti-affabulation (C4) : aucune action exécutée "
                        "n'a été observée dans les traces du run pour cette affirmation."
                    )
                return replace(
                    claim,
                    claim_kind=ClaimKind.REPORTED_INTENTION,
                    origin=claim.origin if claim.origin != InformationOrigin.DOCUMENTARY else InformationOrigin.HYPOTHESIS,
                    evidence_refs=list(valid_evidence_refs) if evidence_pack else list(claim.evidence_refs),
                    verification_status=VerificationStatus.UNSUPPORTED,
                    confidence=min(claim.confidence, 0.5),
                    limitations=limitations,
                    asserted_as_action=was_asserted_action,
                )

        # Traitement des claims d'entretien ou d'intention (Story 015-2, D7) :
        has_explicit_interview = (
            claim.provenance_regime == ProvenanceRegime.INTERVIEW
            or str(getattr(claim.provenance_regime, "value", claim.provenance_regime)) == "interview"
            or any(r.startswith("ivw_") for r in claim.evidence_refs)
            or bool(re.search(r"\b(ivw_[a-z0-9_]+)\b", claim.text))
        )

        # Si la claim cible explicitement un entretien, priorité à l'authentification d'entretien
        if has_explicit_interview and report_interviews is not None and not was_asserted_action:
            ivw_verified = cls.verify_interview_citation(
                claim=claim,
                report_interviews=report_interviews,
                resolver=resolver,
            )
            if ivw_verified is not None:
                return ivw_verified

        # Si la claim est de type REPORTED_INTENTION :
        # Priorité de vérification aux événements simulés réels dans evidence_pack (D7)
        if claim.claim_kind == ClaimKind.REPORTED_INTENTION:
            if claim.agent_name and evidence_pack:
                # Vérifier si l'agent a au moins émis un message
                valid, exact, ev_id = cls.verify_simulated_citation(
                    agent_name=claim.agent_name,
                    claimed_text=claim.text,
                    evidence_pack=evidence_pack,
                    resolver=resolver,
                )
                if valid:
                    new_refs = list(claim.evidence_refs)
                    if ev_id and ev_id not in new_refs:
                        new_refs.append(ev_id)
                    return replace(
                        claim,
                        claim_kind=ClaimKind.REPORTED_INTENTION,
                        origin=InformationOrigin.SIMULATION,
                        evidence_refs=new_refs,
                        verification_status=VerificationStatus.VERIFIED,
                        limitations=list(claim.limitations),
                        asserted_as_action=was_asserted_action,
                    )

            # Rattrapage d'entretien (Story 015-2, D7) : si la déclaration n'a pas été trouvée
            # dans evidence_pack, vérifier si elle provient d'une réponse d'entretien.
            if report_interviews is not None and not was_asserted_action:
                ivw_verified = cls.verify_interview_citation(
                    claim=claim,
                    report_interviews=report_interviews,
                    resolver=resolver,
                )
                if ivw_verified is not None:
                    return ivw_verified

            # Intention sans citation vérifiable
            limitations = list(claim.limitations)
            if not any("citation" in lim.lower() for lim in limitations):
                limitations.append("Déclaration d'intention sans trace verbatim vérifiée dans les événements observés.")
            return replace(
                claim,
                claim_kind=ClaimKind.REPORTED_INTENTION,
                origin=claim.origin,
                evidence_refs=list(claim.evidence_refs),
                verification_status=VerificationStatus.UNSUPPORTED,
                confidence=min(claim.confidence, 0.7),
                limitations=limitations,
                asserted_as_action=was_asserted_action,
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
                return replace(
                    claim,
                    claim_kind=ClaimKind.SCENARIO_HYPOTHESIS,
                    origin=InformationOrigin.HYPOTHESIS,
                    evidence_refs=list(claim.evidence_refs),
                    verification_status=VerificationStatus.UNSUPPORTED,
                    confidence=min(claim.confidence, 0.5),
                    limitations=limitations,
                    asserted_as_action=was_asserted_action,
                )

            status = VerificationStatus.VERIFIED if claim.evidence_refs else VerificationStatus.UNSUPPORTED
            return replace(
                claim,
                claim_kind=ClaimKind.SOURCE_FACT,
                origin=claim.origin,
                evidence_refs=list(claim.evidence_refs),
                verification_status=status,
                limitations=list(claim.limitations),
                asserted_as_action=was_asserted_action,
            )

        # Autres types (ANALYST_INFERENCE, SCENARIO_HYPOTHESIS, SPECULATIVE_PROJECTION)
        status = VerificationStatus.VERIFIED if claim.evidence_refs else VerificationStatus.UNSUPPORTED
        return replace(
            claim,
            claim_kind=claim.claim_kind,
            origin=claim.origin,
            evidence_refs=list(claim.evidence_refs),
            verification_status=status,
            limitations=list(claim.limitations),
            asserted_as_action=was_asserted_action,
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

