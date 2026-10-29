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

# Expressions régulières pour la validation structurelle et sémantique des sections de limites/objections (Story 015-3)
_LIMITATIONS_HEADING_RE = re.compile(
    r"\b(objections?|limites?|contradictions?|r[ée]serves?|verrous?|blocages?|freins?|r[ée]ticences?|refus|obstacles?|risques?|limits?|caveats?|drawbacks?|concerns?|barriers?|blockers?|risks?)\b",
    re.IGNORECASE,
)
_LIMITATIONS_CONTENT_RE = re.compile(
    r"\b(objections?|limites?|contradictions?|r[ée]serves?|refus|rejets?|verrous?|blocages?|freins?|r[ée]ticences?|non[- ]adoptions?|abstentions?|ajournements?|obstacles?|risques?|limits?|caveats?|drawbacks?|concerns?|rejections?|refusals?|barriers?|blockers?|hesitations?)\b",
    re.IGNORECASE,
)

# Expression régulière robuste à frontières de mots pour la détection d'affirmation d'adoption (Story 015-3, D5)
_ADOPTION_CLAIM_RE = re.compile(
    r"\b(?:a\s+adopt[ée]|adopt[ée]s?|adopte|a\s+souscrit|souscrit|s['’]est\s+abonn[ée]e?s?|a\s+achet[ée]|achet[ée]s?|ach[èe]te|a\s+pay[ée]|pay[ée]s?|a\s+command[ée]|command[ée]s?|a\s+sign[ée]\s+(?:le\s+contrat|l['’]abonnement|l['’]offre|un\s+contrat)|adopted|subscribed|subscribes|purchased|bought|paid|ordered)\b",
    re.IGNORECASE,
)
_NEGATION_GUARD_RE = re.compile(
    r"\b(?:sans|aucun[e]?|pas|jamais|ni|refus[ée]?|rejet[ée]?|not|never|no|without)\b",
    re.IGNORECASE,
)

# Helper pour vérifier si la prose d'un rapport prétend narrer des actions simulées exécutées (Story 015-3, D4)
_SIMULATED_ACTION_NARRATIVE_RE = re.compile(
    r"\b(?:round\s+\d+|durant\s+la\s+simulation|pendant\s+la\s+simulation|during\s+(?:the\s+)?simulation|sur\s+reddit|sur\s+twitter|on\s+reddit|on\s+twitter|dans\s+la\s+simulation|sur\s+les\s+(?:deux\s+)?plateformes?|dans\s+les\s+(?:premières\s+)?heures|dans\s+le\s+run)\b",
    re.IGNORECASE,
)
_ACTION_EXECUTION_MARKERS_RE = re.compile(
    r"\b(?:a\s+publi[ée]|a\s+tweet[ée]|a\s+comment[ée]|a\s+r[ée]agi|a\s+r[ée]pondu|a\s+post[ée]|a\s+souscrit|a\s+adopt[ée]|a\s+achet[ée]|a\s+pay[ée]|a\s+command[ée]|a\s+partag[ée]|un\s+même\s+post\s+publi[ée]|post\s+publi[ée]|posted|tweeted|commented|reacted|responded|subscribed|adopted|purchased|ordered)\b",
    re.IGNORECASE,
)
_PURE_NEGATION_SENTENCE_RE = re.compile(
    r"\b(?:sans\s+actions?\s+simul[ée]es?|aucune\s+action(?:\s+simul[ée]e)?|without\s+simulated\s+actions?|no\s+simulated\s+actions?)\b",
    re.IGNORECASE,
)


def _markdown_alleges_simulated_actions(report_markdown: str) -> bool:
    """Détecte si le corps Markdown (hors Sources & Provenance et hors citations) narre des actions simulées."""
    if not report_markdown:
        return False
    # Retirer la section ## Sources & Provenance pour éviter les auto-citations
    parts = re.split(r"^##\s+.*sources.*provenance.*$", report_markdown, flags=re.IGNORECASE | re.MULTILINE)
    body = parts[0] if parts else report_markdown

    # Examiner ligne par ligne en ignorant les citations d'entretien (> ...)
    for line in body.splitlines():
        line_clean = line.strip()
        if not line_clean or line_clean.startswith(">"):
            continue
        if _PURE_NEGATION_SENTENCE_RE.search(line_clean):
            continue
        # Détection d'un événement OASIS explicite (evt_...)
        if "evt_" in line_clean:
            return True
        # Couplage d'un marqueur de simulation et d'un verbe d'action exécutée
        if _SIMULATED_ACTION_NARRATIVE_RE.search(line_clean) and _ACTION_EXECUTION_MARKERS_RE.search(line_clean):
            return True
        # Mention explicite d'agent avec verbe d'action exécutée (ex. @ Claire_Dumont a publié / agent_1 posted)
        if re.search(r"(?:@\s*\w+|agent_\d+)", line_clean, re.IGNORECASE) and _ACTION_EXECUTION_MARKERS_RE.search(line_clean):
            return True
    return False


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
        # Contrôle 4 : Présence obligatoire de la section d'objections et limites (Story 015-3, FR-04, C3)
        # -------------------------------------------------------------
        has_rejections_or_objections = False
        if cohort_table:
            # Vérifier s'il y a des réticences, refus ou objections
            hesitant = cohort_table.status_summary.get("hesitant", 0)
            rejected = cohort_table.status_summary.get("rejected", 0)
            objections_count = len(cohort_table.all_objections)
            if hesitant > 0 or rejected > 0 or objections_count > 0:
                has_rejections_or_objections = True

        limitations_heading_present = False
        limitations_role_matched = False
        matched_section_title = None

        # Helper pour extraire le corps d'une section Markdown de niveau 2 (## <title>)
        def _extract_markdown_section_body(title: str, full_md: str) -> Optional[str]:
            if not title or not full_md:
                return None
            # Recherche de ## <title> (insensible à la casse, espaces tolérés)
            escaped_title = re.escape(title.strip())
            pattern = re.compile(rf"^##\s+{escaped_title}\s*$", re.IGNORECASE | re.MULTILINE)
            m = pattern.search(full_md)
            if not m:
                # Essai par sous-chaîne dans l'en-tête ##
                pattern_sub = re.compile(rf"^##\s+[^\n]*{escaped_title}[^\n]*$", re.IGNORECASE | re.MULTILINE)
                m = pattern_sub.search(full_md)
            if not m:
                return None
            start_pos = m.end()
            # Chercher le début du prochain titre ## ou fin du texte
            next_heading = re.search(r"^##\s+", full_md[start_pos:], re.MULTILINE)
            if next_heading:
                end_pos = start_pos + next_heading.start()
                return full_md[start_pos:end_pos]
            return full_md[start_pos:]

        # 1. Voie primaire contractuelle : outline avec section_role == "limitations"
        outline_sections = []
        if outline:
            if hasattr(outline, "sections"):
                outline_sections = getattr(outline, "sections") or []
            elif isinstance(outline, dict):
                outline_sections = outline.get("sections") or []

        for sec in outline_sections:
            sec_role = getattr(sec, "section_role", None) if hasattr(sec, "section_role") else (sec.get("section_role") if isinstance(sec, dict) else None)
            sec_title = getattr(sec, "title", None) if hasattr(sec, "title") else (sec.get("title") if isinstance(sec, dict) else "")
            if sec_role == "limitations" and sec_title:
                body = _extract_markdown_section_body(sec_title, report_markdown)
                if body is not None and len(body.strip()) >= 50:
                    # Garde de pertinence sémantique (D3) : le titre ou le corps doit traiter des objections/limites/refus/verrous
                    if _LIMITATIONS_CONTENT_RE.search(sec_title) or _LIMITATIONS_CONTENT_RE.search(body):
                        limitations_role_matched = True
                        limitations_heading_present = True
                        matched_section_title = sec_title
                        break

        # 2. Voie de repli rétrocompatible (v1 ou outline sans section_role=="limitations")
        if not limitations_heading_present:
            # Scanner tous les titres ## du Markdown (en excluant ## Sources & Provenance)
            headings_matches = list(re.finditer(r"^##\s+([^\n]+)$", report_markdown, re.MULTILINE))
            for i, hm in enumerate(headings_matches):
                heading_text = hm.group(1).strip()
                heading_lower = heading_text.lower()
                if "sources" in heading_lower and "provenance" in heading_lower:
                    continue

                is_historical_candidate = (
                    "objections non levées, contradictions et limites" in heading_lower
                    or "objections et limites" in heading_lower
                    or "unresolved objections, contradictions, and limitations" in heading_lower
                    or "limitations and objections" in heading_lower
                    or bool(_LIMITATIONS_HEADING_RE.search(heading_text))
                )
                if is_historical_candidate:
                    start_pos = hm.end()
                    end_pos = headings_matches[i + 1].start() if i + 1 < len(headings_matches) else len(report_markdown)
                    body = report_markdown[start_pos:end_pos]
                    if len(body.strip()) >= 50 and _LIMITATIONS_CONTENT_RE.search(body):
                        limitations_heading_present = True
                        matched_section_title = heading_text
                        break

        if has_rejections_or_objections and not limitations_heading_present:
            checks.append(
                QualityCheckItem(
                    category=QualityCategory.LIMITATIONS_SECTION,
                    title="Section d'objections et limites",
                    status=QualityStatus.FAILED,
                    message="Des réticences ou refus ont été observés dans la cohorte, mais la section obligatoire d'objections et limites est absente ou non conforme.",
                    details={
                        "has_rejections_or_objections": True,
                        "limitations_heading_present": False,
                        "limitations_role_matched": limitations_role_matched,
                        "matched_section_title": matched_section_title,
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
                        "limitations_role_matched": limitations_role_matched,
                        "matched_section_title": matched_section_title,
                    },
                )
            )

        # -------------------------------------------------------------
        # -------------------------------------------------------------
        # Contrôle 5 : Vérification des claims, preuves et absence d'affabulation (Story 012-4, Story 015-3, FR-04, C3, C5)
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

            # Traçabilité complète des actions affirmées (Story 015-1 & Story 015-3, FR-04, D4) :
            # asserted_actions inclut les claims de type OBSERVED_SOCIAL_ACTION ainsi que
            # toute affirmation initialement émise comme action mais déclassée (asserted_as_action=True).
            asserted_actions = [
                c for c in claims_registry.claims
                if c.claim_kind == ClaimKind.OBSERVED_SOCIAL_ACTION
                or getattr(c, "asserted_as_action", False)
            ]
            strict_action_claims = [
                c for c in claims_registry.claims
                if c.claim_kind == ClaimKind.OBSERVED_SOCIAL_ACTION
            ]
            downgraded_action_claims = [
                c for c in asserted_actions
                if c.claim_kind != ClaimKind.OBSERVED_SOCIAL_ACTION
            ]
            verified_action_claims = [
                c for c in asserted_actions
                if c.claim_kind == ClaimKind.OBSERVED_SOCIAL_ACTION
                and c.verification_status == VerificationStatus.VERIFIED
            ]
            action_ratio = (len(verified_action_claims) / len(asserted_actions)) if asserted_actions else 1.0
            action_claims = asserted_actions
        else:
            total_claims = 0
            contradicted = 0
            verified = 0
            ratio = 0.0
            critical_contradictions = []
            asserted_actions = []
            strict_action_claims = []
            downgraded_action_claims = []
            action_claims = []
            verified_action_claims = []
            action_ratio = 1.0

        # 2. Vérification d'affabulation commerciale d'adoption non sourcée (AC5, Story 015-3, D5)
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
                # Utiliser l'expression régulière stricte à frontières de mots (_ADOPTION_CLAIM_RE)
                has_substantiating_action = False
                if claims_registry and claims_registry.claims:
                    for c in claims_registry.claims:
                        if c.verification_status == VerificationStatus.VERIFIED and c.claim_kind == ClaimKind.OBSERVED_SOCIAL_ACTION:
                            c_text = c.text or ""
                            # Garde de négation : ne pas compter "n'a pas adopté"
                            if _NEGATION_GUARD_RE.search(c_text):
                                continue
                            if _ADOPTION_CLAIM_RE.search(c_text):
                                # Contrôle supplémentaire : si agent_name est présent, il doit figurer dans les membres adoptés
                                if c.agent_name:
                                    member_names = {getattr(m, "name", "") for m in adopted_members}
                                    if c.agent_name in member_names:
                                        has_substantiating_action = True
                                        break
                                else:
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
                        "action_claims": len(asserted_actions),
                        "asserted_action_claims": len(asserted_actions),
                        "strict_action_claims": len(strict_action_claims),
                        "downgraded_action_claims": len(downgraded_action_claims),
                        "verified_action_claims": len(verified_action_claims),
                        "action_verification_ratio": action_ratio,
                        "verification_ratio": ratio,
                    },
                )
            )
        elif claims_registry and claims_registry.claims:
            if silence_contradictions and critical_contradictions:
                checks.append(
                    QualityCheckItem(
                        category=QualityCategory.CLAIM_VERIFICATION,
                        title="Intégrité des affirmations d'actions simulées",
                        status=QualityStatus.FAILED,
                        message=(
                            f"{len(silence_contradictions)} contradiction(s) de silence et "
                            f"{len(critical_contradictions)} contradiction(s) critique(s) détectée(s)."
                        ),
                        details={
                            "silence_contradictions_count": len(silence_contradictions),
                            "critical_contradictions_count": len(critical_contradictions),
                            "sample_contradictions": [(c.text or "")[:80] for c in (silence_contradictions + critical_contradictions)[:3]],
                            "total_claims": total_claims,
                            "contradicted": contradicted,
                        },
                    )
                )
            elif silence_contradictions:
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
            elif asserted_actions and len(verified_action_claims) == 0:
                # Anomalie R6 / QA-08 (Story 015-3, FR-04, C3, AT-12) :
                # Des actions ont été affirmées (qu'elles soient restées OBSERVED_SOCIAL_ACTION ou déclassées) mais 0 n'est vérifiée
                checks.append(
                    QualityCheckItem(
                        category=QualityCategory.CLAIM_VERIFICATION,
                        title="Intégrité des affirmations d'actions simulées",
                        status=QualityStatus.FAILED,
                        message=f"Absence totale de preuves authentiques : {len(asserted_actions)} action(s) simulée(s) affirmée(s), 0 vérifiée(s) par les traces d'exécution.",
                        details={
                            "total_claims": total_claims,
                            "action_claims": len(asserted_actions),
                            "asserted_action_claims": len(asserted_actions),
                            "strict_action_claims": len(strict_action_claims),
                            "downgraded_action_claims": len(downgraded_action_claims),
                            "verified_action_claims": 0,
                            "action_verification_ratio": 0.0,
                            "verification_ratio": ratio,
                            "r6_anomaly_detected": True,
                        },
                    )
                )
            elif asserted_actions and action_ratio < 0.50:
                # Taux de vérification d'actions insuffisant (< 50%) -> FAILED (Story 015-3, FR-04, C3)
                checks.append(
                    QualityCheckItem(
                        category=QualityCategory.CLAIM_VERIFICATION,
                        title="Intégrité des affirmations d'actions simulées",
                        status=QualityStatus.FAILED,
                        message=f"Taux de vérification des actions simulées insuffisant ({action_ratio*100:.1f}% < 50%) : seulement {len(verified_action_claims)}/{len(asserted_actions)} prouvées.",
                        details={
                            "total_claims": total_claims,
                            "action_claims": len(asserted_actions),
                            "asserted_action_claims": len(asserted_actions),
                            "strict_action_claims": len(strict_action_claims),
                            "downgraded_action_claims": len(downgraded_action_claims),
                            "verified_action_claims": len(verified_action_claims),
                            "action_verification_ratio": action_ratio,
                            "verification_ratio": ratio,
                        },
                    )
                )
            elif not asserted_actions:
                # Aucun claim d'action observée au registre : vérifier si le Markdown narre frauduleusement des actions simulées (AC3)
                if _markdown_alleges_simulated_actions(report_markdown):
                    checks.append(
                        QualityCheckItem(
                            category=QualityCategory.CLAIM_VERIFICATION,
                            title="Intégrité des affirmations d'actions simulées",
                            status=QualityStatus.FAILED,
                            message="Contournement de traçabilité détecté : le rapport narre des actions simulées alors qu'aucune action sociale n'est tracée au registre.",
                            details={
                                "total_claims": total_claims,
                                "action_claims": 0,
                                "asserted_action_claims": 0,
                                "unparseable_action_claims": True,
                                "r6_anomaly_detected": True,
                                "verification_ratio": ratio,
                            },
                        )
                    )
                else:
                    # Rapport avec registre mais véritablement sans allégation d'actions (conceptuel / théorique) -> WARNING (needs_review)
                    checks.append(
                        QualityCheckItem(
                            category=QualityCategory.CLAIM_VERIFICATION,
                            title="Intégrité des affirmations d'actions simulées",
                            status=QualityStatus.WARNING,
                            message=f"Rapport conceptuel sans allégation d'actions observées : {total_claims} assertion(s) analysée(s), 0 action simulée. À réviser avant publication.",
                            details={
                                "total_claims": total_claims,
                                "action_claims": 0,
                                "asserted_action_claims": 0,
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
                            "action_claims": len(asserted_actions),
                            "asserted_action_claims": len(asserted_actions),
                            "strict_action_claims": len(strict_action_claims),
                            "downgraded_action_claims": len(downgraded_action_claims),
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
                        message=f"Validation rigoureuse : {len(verified_action_claims)}/{len(asserted_actions)} actions vérifiées ({action_ratio*100:.1f}%), 0 contradiction critique sur {total_claims} assertions.",
                        details={
                            "total_claims": total_claims,
                            "action_claims": len(asserted_actions),
                            "asserted_action_claims": len(asserted_actions),
                            "strict_action_claims": len(strict_action_claims),
                            "downgraded_action_claims": len(downgraded_action_claims),
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
            if _markdown_alleges_simulated_actions(report_markdown):
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
