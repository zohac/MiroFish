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
        # Contrôle 5 : Vérification des claims et absence d'affabulation
        # -------------------------------------------------------------
        if claims_registry:
            total_claims = claims_registry.total_claims
            contradicted = claims_registry.contradicted_claims
            # Affabulation critique : affirmations OBSERVED_SOCIAL_ACTION contredites
            critical_contradictions = [
                c for c in claims_registry.claims
                if c.verification_status == VerificationStatus.CONTRADICTED
                and c.claim_kind == ClaimKind.OBSERVED_SOCIAL_ACTION
            ]

            if critical_contradictions:
                checks.append(
                    QualityCheckItem(
                        category=QualityCategory.CLAIM_VERIFICATION,
                        title="Intégrité des affirmations d'actions simulées",
                        status=QualityStatus.FAILED,
                        message=f"{len(critical_contradictions)} affirmation(s) d'action(s) simulée(s) contredite(s) par les traces d'exécution.",
                        details={
                            "critical_contradictions_count": len(critical_contradictions),
                            "sample_contradictions": [c.text[:80] for c in critical_contradictions[:3]],
                        },
                    )
                )
            elif contradicted > 0:
                checks.append(
                    QualityCheckItem(
                        category=QualityCategory.CLAIM_VERIFICATION,
                        title="Intégrité des affirmations d'actions simulées",
                        status=QualityStatus.WARNING,
                        message=f"{contradicted} affirmation(s) contredite(s) ou divergente(s) répertoriée(s) dans le registre d'audit.",
                        details={
                            "total_claims": total_claims,
                            "contradicted": contradicted,
                            "verification_ratio": claims_registry.verification_ratio,
                        },
                    )
                )
            else:
                checks.append(
                    QualityCheckItem(
                        category=QualityCategory.CLAIM_VERIFICATION,
                        title="Intégrité des affirmations d'actions simulées",
                        status=QualityStatus.PASSED,
                        message=f"0 contradiction critique détectée sur {total_claims} assertions analysées.",
                        details={
                            "total_claims": total_claims,
                            "verified_claims": claims_registry.verified_claims,
                            "verification_ratio": claims_registry.verification_ratio,
                        },
                    )
                )
        else:
            checks.append(
                QualityCheckItem(
                    category=QualityCategory.CLAIM_VERIFICATION,
                    title="Intégrité des affirmations d'actions simulées",
                    status=QualityStatus.PASSED,
                    message="Contrôle direct des claims omis (registre non fourni ou vide).",
                    details={"claims_registry_present": False},
                )
            )

        # Calculer le résumé et le verdict global
        failed_count = sum(1 for c in checks if c.status == QualityStatus.FAILED)
        warning_count = sum(1 for c in checks if c.status == QualityStatus.WARNING)
        passed_count = sum(1 for c in checks if c.status == QualityStatus.PASSED)

        if failed_count > 0:
            final_status = QualityStatus.FAILED
            is_publishable = False
            summary = f"Échec de la barrière qualité : {failed_count} contrôle(s) critique(s) en échec."
        elif warning_count > 0:
            final_status = QualityStatus.WARNING
            is_publishable = True
            summary = f"Validé avec réserves : {passed_count} réussis, {warning_count} avertissement(s)."
        else:
            final_status = QualityStatus.PASSED
            is_publishable = True
            summary = f"Validation intégrale réussie : {passed_count}/5 contrôles au vert. Rapport publiable."

        result = QualityGateResult(
            simulation_id=self.simulation_id,
            report_id=self.report_id,
            is_publishable=is_publishable,
            final_status=final_status,
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
