"""Service de barrière de qualité et garde anti-troncature des rapports (Epic 011, FR-09, FR-11, C9).

Fournit :
  - `SectionCompletionGuard` : composant d'analyse fine de troncature de section
    (fin de phrase abrupte, coupure de mot, bloc markdown non fermé, finish_reason)
    et de reprise ciblée sans couture (max 2 relances par section).
  - `ReportQualityGate` : barrière serveur d'évaluation avant publication exécutant
    5 contrôles canoniques (intégrité structurelle, anti-troncature, conformité linguistique,
    présence de la section d'objections et limites, et intégrité des claims sans affabulation).
"""

from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Optional, Tuple

from ..config import Config
from ..models.report_quality import (
    PublicationStatus,
    QualityCategory,
    QualityCheckItem,
    QualityGateResult,
    QualityStatus,
)
from ..models.report_claim import ReportClaimRegistry, ClaimKind, VerificationStatus
from ..models.cohort_coverage import CohortCoverageTable, DecisionStatus
from ..models.simulation_brief import SimulationBrief
from ..utils.logger import get_logger

logger = get_logger("mirofish.report_quality_gate")

# Ponctuations et clôtures finales acceptées indiquant qu'un paragraphe/section est achevé
_CANONICAL_TERMINAL_PUNCTUATION = (
    ".",
    "!",
    "?",
    "...",
    "…",
    "»",
    '"',
    "'",
    "”",
    "’",
    ")",
    "]",
    ":",  # Peut introduire une liste ou un tableau déjà complet
    ";",
    "|",  # Fin de ligne de tableau markdown
    "```",  # Clôture de bloc de code markdown
    "---",  # Séparateur markdown
)

# Mots de liaison ou conjonctions suspensives typiques signalant une phrase tronquée
_SUSPICIOUS_TRAILING_WORDS = {
    # Français
    "car", "mais", "parce", "que", "qui", "dont", "où", "pour", "dans", "avec", "sans",
    "donc", "or", "ni", "et", "afin", "lorsque", "puisque", "tandis", "pendant", "comme",
    "ainsi", "alors", "après", "avant", "entre", "vers", "selon", "sous", "sur", "enfin",
    "le", "la", "les", "un", "une", "des", "ce", "cet", "cette", "ces", "son", "sa", "ses",
    "leur", "leurs", "notre", "nos", "votre", "vos", "de", "du", "d'", "l'", "qu'", "c'",
    # Anglais
    "because", "and", "or", "but", "so", "for", "with", "without", "that", "which",
    "who", "whom", "whose", "where", "when", "while", "since", "although", "though",
    "the", "a", "an", "this", "that", "these", "those", "their", "our", "your", "its",
    "to", "in", "on", "at", "by", "from", "as",
}


class SectionCompletionGuard:
    """Composant anti-troncature de section et reprise ciblée (Story 011-5, FR-09, C9)."""

    MAX_RETRIES: int = 2

    @classmethod
    def is_text_truncated(cls, text: str) -> Tuple[bool, str]:
        """Vérifie si un texte de section se termine de façon tronquée ou interrompue.

        Returns:
            Tuple[bool, str] : (is_truncated, reason)
        """
        if not text or not text.strip():
            return True, "Texte vide ou absent"

        stripped = text.strip()

        # 1. Vérifier la clôture des blocs markdown (code blocks ```)
        code_fence_count = stripped.count("```")
        if code_fence_count % 2 != 0:
            return True, "Bloc de code markdown (```) non clôturé en fin de section"

        # 2. Vérifier la ponctuation terminale
        # Extraire la dernière ligne non vide
        lines = [line.strip() for line in stripped.splitlines() if line.strip()]
        if not lines:
            return True, "Aucune ligne de texte non vide"

        last_line = lines[-1]

        # Cas particulier : titres markdown (ex: '## Section') en fin de texte sans corps
        if last_line.startswith("#"):
            return True, "Titre markdown orphelin en fin de texte sans contenu associé"

        # Cas particulier : tableau markdown
        if last_line.startswith("|") and last_line.endswith("|"):
            return False, "Tableau markdown complet"

        # Cas particulier : clôture de bloc de code
        if last_line.endswith("```"):
            return False, "Bloc de code clôturé"

        # 3. Vérifier si le texte finit par une ponctuation terminale acceptée
        ends_with_terminal = any(stripped.endswith(punct) for punct in _CANONICAL_TERMINAL_PUNCTUATION)

        # 4. Vérifier les mots suspensifs en fin de phrase
        # Extraire le dernier mot alphabétique
        words = re.findall(r"\b[A-Za-zÀ-ÿ]+(?:'[A-Za-zÀ-ÿ]+)?\b", last_line)
        if words and words[-1].lower() in _SUSPICIOUS_TRAILING_WORDS and not ends_with_terminal:
            return True, f"Phrase interrompue sur le mot de liaison suspensif '{words[-1]}'"

        if not ends_with_terminal:
            return True, f"Absence de ponctuation terminale canonique en fin de section (fin sur: '{last_line[-25:]}')"

        return False, "Texte complet et correctement ponctué"

    @classmethod
    def assemble_continuation(cls, original_text: str, continuation_text: str) -> str:
        """Fusionne le texte d'origine et la suite renvoyée sans répétition au point de raccord."""
        if not continuation_text or not continuation_text.strip():
            return original_text

        orig_stripped = original_text.rstrip()
        cont_stripped = continuation_text.strip()

        # Supprimer les préfixes éventuels introduits par le LLM
        prefixes_to_clean = [
            "Suite :", "Suite du texte :", "Continuation :", "Voici la suite :",
            "Here is the continuation :", "Continuation:", "Suite:",
        ]
        for pfx in prefixes_to_clean:
            if cont_stripped.lower().startswith(pfx.lower()):
                cont_stripped = cont_stripped[len(pfx):].strip()

        # Recherche de chevauchement sur les derniers mots (jusqu'à 10 mots)
        orig_words = orig_stripped.split()
        cont_words = cont_stripped.split()

        overlap_found = 0
        max_overlap_check = min(len(orig_words), len(cont_words), 10)
        for k in range(max_overlap_check, 0, -1):
            tail_orig = " ".join(orig_words[-k:]).lower()
            head_cont = " ".join(cont_words[:k]).lower()
            if tail_orig == head_cont:
                overlap_found = k
                break

        if overlap_found > 0:
            cleaned_cont = " ".join(cont_words[overlap_found:])
        else:
            cleaned_cont = cont_stripped

        # Gérer la jointure (espace si coupure de phrase, ou continuité directe de mot)
        punctuation_marks = (".", ",", "!", "?", ";", ":", ")", "]", "»", '"', "”", "’")
        if orig_stripped and not orig_stripped[-1].isspace():
            if cleaned_cont.startswith(punctuation_marks):
                merged = orig_stripped + cleaned_cont
            elif orig_stripped[-1].isalnum() and cleaned_cont and cleaned_cont[0].isalnum():
                merged = orig_stripped + " " + cleaned_cont
            else:
                merged = orig_stripped + cleaned_cont
        else:
            merged = orig_stripped + " " + cleaned_cont

        return merged.strip()

    @classmethod
    def complete_section(
        cls,
        llm_client: Any,
        section_title: str,
        current_content: str,
        locale: str = "fr",
        max_retries: int = MAX_RETRIES,
    ) -> Tuple[str, int, bool]:
        """Tente de prolonger et réparer une section tronquée (max_retries tentatives).

        Returns:
            Tuple[str, int, bool] : (final_text, retries_count, is_fully_completed)
        """
        text = current_content
        retries = 0

        while retries < max_retries:
            is_truncated, reason = cls.is_text_truncated(text)
            if not is_truncated:
                return text, retries, True

            retries += 1
            logger.info(
                f"[SectionCompletionGuard] Troncature détectée pour '{section_title}' "
                f"({reason}). Tentative de prolongation {retries}/{max_retries}..."
            )

            # Extraire les 500 derniers caractères pour donner le contexte précis
            context_tail = text[-500:] if len(text) > 500 else text

            is_fr = locale.startswith("fr")
            if is_fr:
                prompt = (
                    f"La section suivante du rapport d'analyse sociale s'est interrompue avant sa conclusion :\n"
                    f"Titre de la section : « {section_title} »\n\n"
                    f"Dernier extrait du texte généré avant coupure :\n"
                    f"«««\n{context_tail}\n»»»\n\n"
                    f"Consigne impérative :\n"
                    f"Poursuis directement la phrase et termine cette section avec une analyse complète et rigoureuse. "
                    f"Ne répète pas le texte déjà fourni. Conclus impérativement par une ponctuation terminale valide "
                    f"et referme tous les blocs markdown ouverts. Rédige en français."
                )
            else:
                prompt = (
                    f"The following section of the social analysis report was truncated before completion:\n"
                    f"Section title: '{section_title}'\n\n"
                    f"Last excerpt before interruption:\n"
                    f"«««\n{context_tail}\n»»»\n\n"
                    f"Imperative instruction:\n"
                    f"Directly continue the interrupted sentence and complete the section with rigorous analysis. "
                    f"Do NOT repeat the already provided text. End with valid terminal punctuation and close any "
                    f"open markdown code blocks or tables. Write in English."
                )

            try:
                continuation = llm_client.chat(
                    messages=[
                        {"role": "system", "content": "Tu es un assistant de rédaction d'analyses sociales rigoureuses."},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.3,
                    max_tokens=2048,
                )
                if continuation and continuation.strip():
                    text = cls.assemble_continuation(text, continuation)
                else:
                    logger.warning("[SectionCompletionGuard] Le LLM a renvoyé une continuation vide.")
                    break
            except Exception as err:
                logger.error(f"[SectionCompletionGuard] Erreur lors de l'appel LLM de continuation : {err}")
                break

        # Re-vérifier l'état final
        final_truncated, final_reason = cls.is_text_truncated(text)
        return text, retries, not final_truncated


class ReportQualityGate:
    """Barrière serveur de publication du rapport (Story 011-5, FR-09, C9)."""

    def __init__(self, simulation_id: str, report_id: str, locale: str = "fr"):
        self.simulation_id = simulation_id
        self.report_id = report_id
        self.locale = locale or "fr"

    def evaluate_report(
        self,
        outline: Any,
        report_markdown: str,
        cohort_table: Optional[CohortCoverageTable] = None,
        claims_registry: Optional[ReportClaimRegistry] = None,
        brief: Optional[SimulationBrief] = None,
        section_retries: Optional[Dict[str, int]] = None,
    ) -> QualityGateResult:
        """Exécute les 5 contrôles de qualité préalables à la publication."""
        checks: List[QualityCheckItem] = []
        section_retries = section_retries or {}

        # -------------------------------------------------------------
        # Contrôle 1 : Intégrité structurelle (sections prévues présentes et non vides)
        # -------------------------------------------------------------
        expected_sections = []
        if outline and hasattr(outline, "sections"):
            expected_sections = [s.title for s in outline.sections]
        elif outline and isinstance(outline, dict):
            expected_sections = [s.get("title", "") for s in outline.get("sections", [])]

        empty_sections = []
        missing_sections = []
        total_expected = len(expected_sections)

        for sec_title in expected_sections:
            if not sec_title:
                continue
            # Rechercher la présence de la section dans le markdown
            pattern = rf"(?:^|\n)##\s+{re.escape(sec_title)}"
            match = re.search(pattern, report_markdown, re.IGNORECASE)
            if not match:
                missing_sections.append(sec_title)
            else:
                # Vérifier la longueur du contenu de la section
                start_pos = match.end()
                next_sec = re.search(r"(?:^|\n)##\s+", report_markdown[start_pos:])
                sec_body = (
                    report_markdown[start_pos : start_pos + next_sec.start()]
                    if next_sec
                    else report_markdown[start_pos:]
                ).strip()
                if len(sec_body) < 50:
                    empty_sections.append(sec_title)

        if missing_sections or empty_sections:
            msg_parts = []
            if missing_sections:
                msg_parts.append(f"{len(missing_sections)} section(s) manquante(s) : {', '.join(missing_sections[:3])}")
            if empty_sections:
                msg_parts.append(f"{len(empty_sections)} section(s) trop courte(s) (< 50 car.) : {', '.join(empty_sections[:3])}")
            checks.append(
                QualityCheckItem(
                    category=QualityCategory.STRUCTURAL_INTEGRITY,
                    title="Intégrité structurelle des sections",
                    status=QualityStatus.FAILED,
                    message=" ; ".join(msg_parts),
                    details={
                        "total_expected": total_expected,
                        "missing_sections": missing_sections,
                        "empty_sections": empty_sections,
                    },
                )
            )
        else:
            checks.append(
                QualityCheckItem(
                    category=QualityCategory.STRUCTURAL_INTEGRITY,
                    title="Intégrité structurelle des sections",
                    status=QualityStatus.PASSED,
                    message=f"100 % des sections prévues ({total_expected}) sont générées et complètes (> 50 caractères).",
                    details={"total_expected": total_expected, "empty_sections": 0, "missing_sections": 0},
                )
            )

        # -------------------------------------------------------------
        # Contrôle 2 : Anti-troncature de fin de section
        # -------------------------------------------------------------
        is_truncated, trunc_reason = SectionCompletionGuard.is_text_truncated(report_markdown)
        if is_truncated:
            checks.append(
                QualityCheckItem(
                    category=QualityCategory.COMPLETION_GUARD,
                    title="Anti-troncature et clôture du texte",
                    status=QualityStatus.FAILED,
                    message=f"Défaut de troncature non résolu : {trunc_reason}",
                    details={
                        "truncated": True,
                        "reason": trunc_reason,
                        "retries_applied": section_retries,
                    },
                )
            )
        else:
            total_retries = sum(section_retries.values())
            checks.append(
                QualityCheckItem(
                    category=QualityCategory.COMPLETION_GUARD,
                    title="Anti-troncature et clôture du texte",
                    status=QualityStatus.PASSED,
                    message="Toutes les sections se terminent par une ponctuation ou clôture terminale valide.",
                    details={
                        "truncated": False,
                        "total_retries_applied": total_retries,
                        "section_retries": section_retries,
                    },
                )
            )

        # -------------------------------------------------------------
        # Contrôle 3 : Conformité linguistique (FR)
        # -------------------------------------------------------------
        is_fr = self.locale.startswith("fr")
        foreign_sections = []
        if is_fr:
            # Vérifier les marqueurs typiques en anglais dans les titres de section
            english_title_keywords = [
                "Executive Summary",
                "Financial Analysis",
                "Simulation Events",
                "Key Findings",
                "Table of Contents",
                "Overview and Methodology",
            ]
            for kw in english_title_keywords:
                if re.search(rf"(?:^|\n)##\s+{re.escape(kw)}", report_markdown, re.IGNORECASE):
                    foreign_sections.append(kw)

        if foreign_sections:
            checks.append(
                QualityCheckItem(
                    category=QualityCategory.LANGUAGE_COMPLIANCE,
                    title="Conformité linguistique",
                    status=QualityStatus.WARNING,
                    message=f"Titres non localisés détectés en langue étrangère ({', '.join(foreign_sections)}) pour locale '{self.locale}'.",
                    details={"locale": self.locale, "foreign_titles": foreign_sections},
                )
            )
        else:
            checks.append(
                QualityCheckItem(
                    category=QualityCategory.LANGUAGE_COMPLIANCE,
                    title="Conformité linguistique",
                    status=QualityStatus.PASSED,
                    message=f"Texte et titres conformes à la locale active '{self.locale}'.",
                    details={"locale": self.locale, "foreign_titles": []},
                )
            )

        # -------------------------------------------------------------
        # Contrôle 4 : Présence obligatoire de la section d'objections et limites
        # -------------------------------------------------------------
        has_rejections_or_objections = False
        if cohort_table:
            # Vérifier s'il y a des réticences, refus ou objections
            hesitant = cohort_table.status_summary.get("hesitant", 0)
            rejected = cohort_table.status_summary.get("rejected", 0)
            objections_count = len(cohort_table.all_objections)
            if hesitant > 0 or rejected > 0 or objections_count > 0:
                has_rejections_or_objections = True

        md_lower = report_markdown.lower()
        limitations_heading_present = (
            "objections non levées, contradictions et limites" in md_lower
            or "objections et limites" in md_lower
            or "unresolved objections, contradictions, and limitations" in md_lower
            or "limitations and objections" in md_lower
        )

        if has_rejections_or_objections and not limitations_heading_present:
            checks.append(
                QualityCheckItem(
                    category=QualityCategory.LIMITATIONS_SECTION,
                    title="Section d'objections et limites",
                    status=QualityStatus.FAILED,
                    message="Des réticences ou refus ont été observés dans la cohorte, mais la section obligatoire d'objections et limites est absente.",
                    details={
                        "has_rejections_or_objections": True,
                        "limitations_heading_present": False,
                    },
                )
            )
        else:
            checks.append(
                QualityCheckItem(
                    category=QualityCategory.LIMITATIONS_SECTION,
                    title="Section d'objections et limites",
                    status=QualityStatus.PASSED,
                    message="Section d'objections et limites conforme aux observations de la cohorte.",
                    details={
                        "has_rejections_or_objections": has_rejections_or_objections,
                        "limitations_heading_present": limitations_heading_present,
                    },
                )
            )

        # -------------------------------------------------------------
        # -------------------------------------------------------------
        # Contrôle 5 : Vérification des claims, preuves et absence d'affabulation (Story 012-4, FR-05, C5)
        # -------------------------------------------------------------
        # 1. Préparation des métriques de claims si disponibles
        if claims_registry and claims_registry.claims:
            total_claims = claims_registry.total_claims
            contradicted = claims_registry.contradicted_claims
            verified = claims_registry.verified_claims
            ratio = claims_registry.verification_ratio

            critical_contradictions = [
                c for c in claims_registry.claims
                if c.verification_status == VerificationStatus.CONTRADICTED
                and c.claim_kind == ClaimKind.OBSERVED_SOCIAL_ACTION
            ]

            # Contradictions de silence (Story 014-3, AC3, FR-06) : un claim
            # CONTRADICTED imputé à un persona silencieux est critique pour la
            # barrière, quel que soit son ClaimKind (le reclassement en
            # SPECULATIVE_PROJECTION ne l'exonère pas).
            silence_contradictions = []
            if cohort_table is not None:
                for c in claims_registry.claims:
                    if c.verification_status != VerificationStatus.CONTRADICTED:
                        continue
                    if not getattr(c, "agent_name", None):
                        continue
                    try:
                        member = cohort_table.get_member(c.agent_name)
                    except Exception:
                        member = None
                    if member is not None and getattr(member, "is_silent", False):
                        silence_contradictions.append(c)

            action_claims = [
                c for c in claims_registry.claims
                if c.claim_kind == ClaimKind.OBSERVED_SOCIAL_ACTION
            ]
            verified_action_claims = [
                c for c in action_claims
                if c.verification_status == VerificationStatus.VERIFIED
            ]
            action_ratio = (len(verified_action_claims) / len(action_claims)) if action_claims else 1.0
        else:
            total_claims = 0
            contradicted = 0
            verified = 0
            ratio = 0.0
            critical_contradictions = []
            action_claims = []
            verified_action_claims = []
            action_ratio = 1.0

        # 2. Vérification d'affabulation commerciale d'adoption non sourcée (AC5)
        unverified_adoptions_detected = False
        adopted_members: List[Any] = []
        if cohort_table and getattr(cohort_table, "members", None):
            for m in cohort_table.members:
                st = getattr(m, "decision_status", None)
                st_str = st.value if hasattr(st, "value") else str(st or "")
                if st_str.upper() in ("ADOPTED_VERIFIED", "ADOPTED"):
                    adopted_members.append(m)

            if adopted_members:
                # Vérifier si au moins une preuve d'action ou claim vérifié soutient ces adoptions
                has_substantiating_action = False
                if claims_registry and claims_registry.claims:
                    for c in claims_registry.claims:
                        if c.verification_status == VerificationStatus.VERIFIED and c.claim_kind == ClaimKind.OBSERVED_SOCIAL_ACTION:
                            c_text_lower = (c.text or "").lower()
                            # Support bilingue FR/EN des termes d'adoption/conversion commerciale
                            if any(k in c_text_lower for k in ("adopt", "souscri", "subscri", "achet", "purchas", "buy", "abonn", "pay", "sign", "convert", "order")):
                                has_substantiating_action = True
                                break
                if not has_substantiating_action:
                    unverified_adoptions_detected = True

        if unverified_adoptions_detected:
            checks.append(
                QualityCheckItem(
                    category=QualityCategory.CLAIM_VERIFICATION,
                    title="Intégrité des affirmations d'actions simulées",
                    status=QualityStatus.FAILED,
                    message="Affabulation d'adoption détectée : des conversions (ADOPTED_VERIFIED) sont proclamées sans aucune preuve d'action probante dans le registre.",
                    details={
                        "unverified_adoptions": True,
                        "adopted_count": len(adopted_members),
                        "total_claims": total_claims,
                        "action_claims": len(action_claims),
                        "verified_action_claims": len(verified_action_claims),
                        "action_verification_ratio": action_ratio,
                        "verification_ratio": ratio,
                    },
                )
            )
        elif claims_registry and claims_registry.claims:
            if silence_contradictions:
                checks.append(
                    QualityCheckItem(
                        category=QualityCategory.CLAIM_VERIFICATION,
                        title="Intégrité des affirmations d'actions simulées",
                        status=QualityStatus.FAILED,
                        message=f"{len(silence_contradictions)} contradiction(s) de silence : action affirmée pour un persona silencieux (present_no_action).",
                        details={
                            "silence_contradictions_count": len(silence_contradictions),
                            "sample_contradictions": [(c.text or "")[:80] for c in silence_contradictions[:3]],
                            "total_claims": total_claims,
                            "contradicted": contradicted,
                        },
                    )
                )
            elif critical_contradictions:
                checks.append(
                    QualityCheckItem(
                        category=QualityCategory.CLAIM_VERIFICATION,
                        title="Intégrité des affirmations d'actions simulées",
                        status=QualityStatus.FAILED,
                        message=f"{len(critical_contradictions)} affirmation(s) d'action(s) simulée(s) contredite(s) par les traces d'exécution.",
                        details={
                            "critical_contradictions_count": len(critical_contradictions),
                            "sample_contradictions": [(c.text or "")[:80] for c in critical_contradictions[:3]],
                            "total_claims": total_claims,
                            "contradicted": contradicted,
                        },
                    )
                )
            elif action_claims and len(verified_action_claims) == 0:
                # Anomalie R6 / QA-08 : des actions simulées sont affirmées mais 0 n'est vérifiée
                checks.append(
                    QualityCheckItem(
                        category=QualityCategory.CLAIM_VERIFICATION,
                        title="Intégrité des affirmations d'actions simulées",
                        status=QualityStatus.FAILED,
                        message=f"Absence totale de preuves authentiques : {len(action_claims)} action(s) simulée(s) affirmée(s), 0 vérifiée(s) par les traces d'exécution.",
                        details={
                            "total_claims": total_claims,
                            "action_claims": len(action_claims),
                            "verified_action_claims": 0,
                            "verification_ratio": ratio,
                            "r6_anomaly_detected": True,
                        },
                    )
                )
            elif action_claims and action_ratio < 0.50:
                # Taux de vérification d'actions insuffisant (< 50%) -> FAILED
                checks.append(
                    QualityCheckItem(
                        category=QualityCategory.CLAIM_VERIFICATION,
                        title="Intégrité des affirmations d'actions simulées",
                        status=QualityStatus.FAILED,
                        message=f"Taux de vérification des actions simulées insuffisant ({action_ratio*100:.1f}% < 50%) : seulement {len(verified_action_claims)}/{len(action_claims)} prouvées.",
                        details={
                            "total_claims": total_claims,
                            "action_claims": len(action_claims),
                            "verified_action_claims": len(verified_action_claims),
                            "action_verification_ratio": action_ratio,
                            "verification_ratio": ratio,
                        },
                    )
                )
            elif not action_claims:
                # Rapport avec registre mais 0 assertion d'action observée (conceptuel / théorique) -> WARNING (needs_review)
                checks.append(
                    QualityCheckItem(
                        category=QualityCategory.CLAIM_VERIFICATION,
                        title="Intégrité des affirmations d'actions simulées",
                        status=QualityStatus.WARNING,
                        message=f"Rapport conceptuel sans allégation d'actions observées : {total_claims} assertion(s) analysée(s), 0 action simulée. À réviser avant publication.",
                        details={
                            "total_claims": total_claims,
                            "action_claims": 0,
                            "verified_action_claims": 0,
                            "action_verification_ratio": 0.0,
                            "verification_ratio": ratio,
                            "contradicted": contradicted,
                        },
                    )
                )
            elif action_ratio < 0.80 or contradicted > 0:
                # Taux intermédiaire (50% <= action_ratio < 80%) ou contradictions secondaires -> WARNING (NEEDS_REVIEW)
                warning_reasons = []
                if action_ratio < 0.80:
                    warning_reasons.append(f"taux de vérification des actions partiel ({action_ratio*100:.1f}% < 80%)")
                if contradicted > 0:
                    warning_reasons.append(f"{contradicted} affirmation(s) contredite(s) ou divergente(s)")
                checks.append(
                    QualityCheckItem(
                        category=QualityCategory.CLAIM_VERIFICATION,
                        title="Intégrité des affirmations d'actions simulées",
                        status=QualityStatus.WARNING,
                        message=f"Preuves partielles : {', '.join(warning_reasons)} répertoriée(s) dans le registre d'audit.",
                        details={
                            "total_claims": total_claims,
                            "action_claims": len(action_claims),
                            "verified_action_claims": len(verified_action_claims),
                            "action_verification_ratio": action_ratio,
                            "contradicted": contradicted,
                            "verification_ratio": ratio,
                        },
                    )
                )
            else:
                # >= 80% des actions vérifiées et 0 contradiction -> PASSED
                checks.append(
                    QualityCheckItem(
                        category=QualityCategory.CLAIM_VERIFICATION,
                        title="Intégrité des affirmations d'actions simulées",
                        status=QualityStatus.PASSED,
                        message=f"Validation rigoureuse : {len(verified_action_claims)}/{len(action_claims)} actions vérifiées ({action_ratio*100:.1f}%), 0 contradiction critique sur {total_claims} assertions.",
                        details={
                            "total_claims": total_claims,
                            "action_claims": len(action_claims),
                            "verified_action_claims": len(verified_action_claims),
                            "action_verification_ratio": action_ratio,
                            "verified_claims": verified,
                            "verification_ratio": ratio,
                        },
                    )
                )
        else:
            # Absence de registre de claims ou registre vide (QA-09)
            # Détecter si le rapport prétend relater des actions simulées ou des rounds
            md_lower = (report_markdown or "").lower()
            mentions_simulated_actions = bool(
                re.search(r"\bround\s+\d+\b", md_lower)
                or re.search(r"\b(agent_\d+)\b", md_lower)
                or re.search(r"\b(a publié|a tweeté|a commenté|a réagi|a répondu|posted|tweeted|commented)\b", md_lower)
            )

            if mentions_simulated_actions:
                # Des actions simulées sont revendiquées mais le registre d'audit est absent -> FAILED (QA-09)
                checks.append(
                    QualityCheckItem(
                        category=QualityCategory.CLAIM_VERIFICATION,
                        title="Intégrité des affirmations d'actions simulées",
                        status=QualityStatus.FAILED,
                        message="Absence de registre de preuves : le rapport relate des actions simulées mais aucun registre d'audit (ReportClaimRegistry) n'est disponible.",
                        details={"claims_registry_present": False, "simulated_actions_alleged": True},
                    )
                )
            else:
                # Rapport purement théorique / exploratoire sans mention d'actions -> WARNING / needs_review (QA-09, AC3)
                checks.append(
                    QualityCheckItem(
                        category=QualityCategory.CLAIM_VERIFICATION,
                        title="Intégrité des affirmations d'actions simulées",
                        status=QualityStatus.WARNING,
                        message="Contrôle direct des claims omis : rapport théorique sans allégation d'actions simulées (registre non fourni ou vide). À réviser avant publication.",
                        details={"claims_registry_present": False, "simulated_actions_alleged": False},
                    )
                )

        # Calculer le résumé et le verdict global en mode Fail-Closed (Story 012-4)
        failed_count = sum(1 for c in checks if c.status == QualityStatus.FAILED)
        warning_count = sum(1 for c in checks if c.status == QualityStatus.WARNING)
        passed_count = sum(1 for c in checks if c.status == QualityStatus.PASSED)

        if failed_count > 0:
            final_status = QualityStatus.FAILED
            publication_status = PublicationStatus.FAILED_VALIDATION
            is_publishable = False
            summary = f"Échec de la barrière qualité : {failed_count} contrôle(s) critique(s) en échec. Certification refusée."
        elif warning_count > 0:
            final_status = QualityStatus.WARNING
            publication_status = PublicationStatus.NEEDS_REVIEW
            is_publishable = False  # Fail-Closed : needs_review n'est pas certifié publiable directement
            summary = f"À réviser : {passed_count} réussis, {warning_count} avertissement(s). Publication sous réserve de revue."
        else:
            final_status = QualityStatus.PASSED
            publication_status = PublicationStatus.VERIFIED_PUBLISHABLE
            is_publishable = True
            summary = f"Validation intégrale réussie : {passed_count}/5 contrôles au vert. Rapport certifié publiable."

        result = QualityGateResult(
            simulation_id=self.simulation_id,
            report_id=self.report_id,
            is_publishable=is_publishable,
            final_status=final_status,
            publication_status=publication_status,
            summary=summary,
            checks=checks,
            metadata={"locale": self.locale},
        )

        return result

    def save_quality_result(self, result: QualityGateResult) -> str:
        """Sauvegarde quality_checks.json dans reports/<rep_id>/ et simulations/<sim_id>/."""
        # 1. Sauvegarde dans le dossier du rapport
        report_dir = os.path.join(Config.UPLOAD_FOLDER, "reports", self.report_id)
        report_quality_path = os.path.join(report_dir, "quality_checks.json")
        result.save_to_file(report_quality_path)

        # 2. Sauvegarde dans le dossier de la simulation
        sim_dir = os.path.join(Config.UPLOAD_FOLDER, "simulations", self.simulation_id)
        sim_quality_path = os.path.join(sim_dir, "quality_checks.json")
        try:
            result.save_to_file(sim_quality_path)
        except Exception as err:
            logger.warning(f"Impossible de synchroniser quality_checks.json dans simulation {self.simulation_id}: {err}")

        return report_quality_path
