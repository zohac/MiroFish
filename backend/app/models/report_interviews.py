# -*- coding: utf-8 -*-
"""Modèles pour le journal d'entretiens de rédaction (Story 015-2).

Enveloppe structurée schema_version: "2.0" par session, tour et répondant,
offsets exacts de citations, lecture rétrocompatible v1 et assainissement anti-secrets.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import logging
import os
import re
from typing import Any, Dict, List, Optional, Tuple
import uuid

logger = logging.getLogger(__name__)

# Patterns pour l'assainissement anti-secrets (NFR-4)
_SECRET_PATTERNS = [
    re.compile(r"Bearer\s+[A-Za-z0-9_\-\.]{16,}", re.IGNORECASE),
    re.compile(r"sk-[A-Za-z0-9_\-]{16,}", re.IGNORECASE),
    re.compile(r"(?:api_key|apikey|token|password|secret)\s*[:=]\s*['\"]?[A-Za-z0-9_\-\.]{8,}['\"]?", re.IGNORECASE),
    re.compile(r"https?://[^/\s:@]+:[^/\s:@]+@[^\s/]+", re.IGNORECASE),
]


def sanitize_interview_text(text: str) -> str:
    """Masque tout secret, clé API, jeton ou mot de passe accidentellement présent (NFR-4)."""
    if not text or not isinstance(text, str):
        return ""
    sanitized = text
    for pat in _SECRET_PATTERNS:
        sanitized = pat.sub("[REDACTED_SECRET]", sanitized)
    return sanitized


def extract_quote_spans_from_answer(
    answer_text: str, candidate_quotes: List[str]
) -> List[InterviewQuoteSpan]:
    """Projette une liste de citations candidates sur answer_text pour produire des offsets exacts.

    Invariant garanti : answer_text[char_start:char_end] == quote.
    Toute citation introuvable exactement dans answer_text est nettoyée (ponctuation synthétique retirée,
    espaces condensés) ou écartée si elle n'apparaît pas en tranche contiguë.
    """
    spans: List[InterviewQuoteSpan] = []
    if not answer_text or not candidate_quotes:
        return spans

    for raw_quote in candidate_quotes:
        if not raw_quote or not isinstance(raw_quote, str):
            continue
        cleaned = raw_quote.strip()
        # Retirer d'éventuels guillemets englobants
        paired_delims = (
            ('"', '"'),
            ("'", "'"),
            ("«", "»"),
            ("“", "”"),
            ("「", "」"),
        )
        for op, cl in paired_delims:
            if cleaned.startswith(op) and cleaned.endswith(cl) and len(cleaned) >= (len(op) + len(cl)):
                cleaned = cleaned[len(op):-len(cl)].strip()

        if not cleaned:
            continue

        # 1. Recherche directe exacte
        pos = answer_text.find(cleaned)
        if pos != -1:
            spans.append(InterviewQuoteSpan(
                quote=cleaned,
                char_start=pos,
                char_end=pos + len(cleaned)
            ))
            continue

        # 2. Si un point terminal synthétique a été ajouté, essayer sans
        if cleaned.endswith((".", "。", "!", "！", "?", "？")):
            sub = cleaned[:-1].strip()
            if sub:
                pos = answer_text.find(sub)
                if pos != -1:
                    spans.append(InterviewQuoteSpan(
                        quote=sub,
                        char_start=pos,
                        char_end=pos + len(sub)
                    ))
                    continue

        # 3. Essai après retrait de marqueurs Markdown de début
        no_md = re.sub(r"^[*_`#\->\s]+", "", cleaned).strip()
        if no_md and no_md != cleaned:
            pos = answer_text.find(no_md)
            if pos != -1:
                spans.append(InterviewQuoteSpan(
                    quote=no_md,
                    char_start=pos,
                    char_end=pos + len(no_md)
                ))
                continue

    return spans


@dataclass(frozen=True)
class InterviewQuoteSpan:
    """Tranche contiguë exacte d'une citation extraite d'une réponse d'entretien."""
    quote: str
    char_start: int
    char_end: int

    def __post_init__(self) -> None:
        if self.char_start < 0:
            raise ValueError(f"char_start ({self.char_start}) doit être >= 0")
        if self.char_end <= self.char_start:
            raise ValueError(f"char_end ({self.char_end}) doit être > char_start ({self.char_start})")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "quote": sanitize_interview_text(self.quote),
            "char_start": self.char_start,
            "char_end": self.char_end,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> InterviewQuoteSpan:
        return cls(
            quote=str(data.get("quote", "")),
            char_start=int(data.get("char_start", 0)),
            char_end=int(data.get("char_end", 0)),
        )


@dataclass
class InterviewTurn:
    """Tour de parole individuel pour un répondant précis au sein d'une session."""
    turn_id: str
    turn_index: int
    agent_id: Optional[int]
    persona_name: str
    question: str
    answer_text: str
    key_quotes: List[InterviewQuoteSpan] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.turn_index < 1:
            raise ValueError(f"turn_index ({self.turn_index}) doit être >= 1")
        # Assainir systématiquement answer_text et question dès la construction (NFR-4)
        sanitized_ans = sanitize_interview_text(self.answer_text)
        if sanitized_ans != self.answer_text:
            self.answer_text = sanitized_ans
            # Recalculer les spans pour maintenir l'invariant exact sur answer_text assaini
            if self.key_quotes:
                raw_q = [sanitize_interview_text(q.quote) for q in self.key_quotes]
                self.key_quotes = extract_quote_spans_from_answer(self.answer_text, raw_q)
        self.question = sanitize_interview_text(self.question)

        # Invariant exact : answer_text[char_start:char_end] == quote
        for q in self.key_quotes:
            if not (0 <= q.char_start < q.char_end <= len(self.answer_text)):
                raise ValueError(
                    f"Offset [{q.char_start}:{q.char_end}] hors limites pour une réponse de longueur {len(self.answer_text)}"
                )
            actual_slice = self.answer_text[q.char_start:q.char_end]
            if actual_slice != q.quote:
                raise ValueError(
                    f"Invariant violé : answer_text[{q.char_start}:{q.char_end}] = {repr(actual_slice)} != {repr(q.quote)}"
                )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "turn_id": self.turn_id,
            "turn_index": self.turn_index,
            "agent_id": self.agent_id,
            "persona_name": self.persona_name,
            "question": sanitize_interview_text(self.question),
            "answer_text": sanitize_interview_text(self.answer_text),
            "key_quotes": [q.to_dict() for q in self.key_quotes],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> InterviewTurn:
        raw_quotes = data.get("key_quotes", []) or []
        quotes: List[InterviewQuoteSpan] = []
        for rq in raw_quotes:
            if isinstance(rq, dict) and "char_start" in rq and "char_end" in rq:
                quotes.append(InterviewQuoteSpan.from_dict(rq))
            elif isinstance(rq, str):
                # Ancien format string : tenter projection sur answer_text
                ans = str(data.get("answer_text", ""))
                spans = extract_quote_spans_from_answer(ans, [rq])
                quotes.extend(spans)

        aid = data.get("agent_id")
        if aid is not None:
            try:
                aid = int(aid)
            except (ValueError, TypeError):
                aid = None

        return cls(
            turn_id=str(data.get("turn_id", "")),
            turn_index=int(data.get("turn_index", 1)),
            agent_id=aid,
            persona_name=str(data.get("persona_name", "")),
            question=str(data.get("question", "")),
            answer_text=str(data.get("answer_text", "")),
            key_quotes=quotes,
        )


@dataclass
class InterviewSession:
    """Session d'entretien complète menée lors de la rédaction."""
    interview_id: str
    session_index: int
    subject: str
    questions: List[str]
    mode: str
    recorded_at: str
    turns: List[InterviewTurn] = field(default_factory=list)
    # Champs de repli pour formats historiques v1 (conservés en mémoire)
    legacy_agents: List[str] = field(default_factory=list)
    legacy_citations: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "interview_id": self.interview_id,
            "session_index": self.session_index,
            "subject": sanitize_interview_text(self.subject),
            "questions": [sanitize_interview_text(q) for q in self.questions],
            "mode": self.mode,
            "recorded_at": self.recorded_at,
            "turns": [t.to_dict() for t in self.turns],
        }
        if self.legacy_agents:
            d["legacy_agents"] = self.legacy_agents
        if self.legacy_citations:
            d["legacy_citations"] = self.legacy_citations
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> InterviewSession:
        raw_turns = data.get("turns", []) or []
        turns = [InterviewTurn.from_dict(t) for t in raw_turns if isinstance(t, dict)]
        return cls(
            interview_id=str(data.get("interview_id", "")),
            session_index=int(data.get("session_index", 1)),
            subject=str(data.get("subject", "")),
            questions=[str(q) for q in data.get("questions", []) or []],
            mode=str(data.get("mode", "live")),
            recorded_at=str(data.get("recorded_at", "")),
            turns=turns,
            legacy_agents=[str(a) for a in data.get("legacy_agents", []) or []],
            legacy_citations=[str(c) for c in data.get("legacy_citations", []) or []],
        )


@dataclass
class ReportInterviewsPayload:
    """Charge utile complète de l'artefact report_interviews.json v2."""
    simulation_id: str
    report_id: str
    sessions: List[InterviewSession] = field(default_factory=list)
    schema_version: str = "2.0"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "simulation_id": self.simulation_id,
            "report_id": self.report_id,
            "sessions": [s.to_dict() for s in self.sessions],
        }

    def save_to_file(self, file_path: str) -> None:
        """Écrit l'artefact sur disque de façon atomique via .tmp + os.replace."""
        dir_name = os.path.dirname(file_path)
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)
        unique_suffix = uuid.uuid4().hex[:8]
        tmp_path = f"{file_path}.tmp.{os.getpid()}.{unique_suffix}"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, file_path)

    @classmethod
    def from_raw(
        cls,
        raw_data: Any,
        simulation_id: str = "",
        report_id: str = "",
    ) -> ReportInterviewsPayload:
        """Parse de manière tolérante tout format (v2, v1 liste plate, enveloppe v1, format ad-hoc)."""
        if raw_data is None:
            return cls(simulation_id=simulation_id, report_id=report_id, sessions=[])

        # Cas 1 : Dictionnaire v2 standard
        if isinstance(raw_data, dict):
            # Format v2 explicite
            if raw_data.get("schema_version") == "2.0" or "sessions" in raw_data:
                raw_sessions = raw_data.get("sessions")
                sessions_list = raw_sessions if isinstance(raw_sessions, list) else []
                sessions = [
                    InterviewSession.from_dict(s)
                    for s in sessions_list
                    if isinstance(s, dict)
                ]
                return cls(
                    simulation_id=str(raw_data.get("simulation_id") or simulation_id),
                    report_id=str(raw_data.get("report_id") or report_id),
                    sessions=sessions,
                    schema_version="2.0",
                )

            # Enveloppe historique : {"report_id": "...", "interviews": [...]}
            if "interviews" in raw_data:
                sub_interviews = raw_data.get("interviews", []) or []
                rep_id = str(raw_data.get("report_id") or report_id)
                sim_id = str(raw_data.get("simulation_id") or simulation_id)
                return cls._from_v1_list(sub_interviews, simulation_id=sim_id, report_id=rep_id)

        # Cas 2 : Liste racine v1 ou liste de sessions/entretiens
        if isinstance(raw_data, list):
            return cls._from_v1_list(raw_data, simulation_id=simulation_id, report_id=report_id)

        # Repli défensif
        return cls(simulation_id=simulation_id, report_id=report_id, sessions=[])

    @classmethod
    def _from_v1_list(
        cls,
        items: List[Any],
        simulation_id: str = "",
        report_id: str = "",
    ) -> ReportInterviewsPayload:
        sessions: List[InterviewSession] = []
        for idx, item in enumerate(items, 1):
            if not isinstance(item, dict):
                continue
            # Cas v1 ad-hoc test: {"interviewee": "A", "transcript": "..."}
            if "interviewee" in item and ("transcript" in item or "response" in item):
                interviewee = str(item.get("interviewee", ""))
                transcript = str(item.get("transcript") or item.get("response") or "")
                ivw_id = f"ivw_{idx:02d}_{hashlib.sha256(f'{simulation_id}|{report_id}|{idx}|adhoc'.encode()).hexdigest()[:8]}"
                turn_id = f"{ivw_id}_t01"
                turn = InterviewTurn(
                    turn_id=turn_id,
                    turn_index=1,
                    agent_id=None,
                    persona_name=interviewee,
                    question="Entretien de rédaction (v1)",
                    answer_text=transcript,
                    key_quotes=[],
                )
                session = InterviewSession(
                    interview_id=ivw_id,
                    session_index=idx,
                    subject="Entretien ad-hoc v1",
                    questions=["Entretien de rédaction (v1)"],
                    mode="live",
                    recorded_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    turns=[turn],
                )
                sessions.append(session)
                continue

            # Cas v1 standard : {"subject", "agents", "mode", "citations"}
            subj = str(item.get("subject", f"Session {idx}"))
            mode = str(item.get("mode", "live"))
            agents = [str(a) for a in item.get("agents", []) or []]
            citations = [str(c) for c in item.get("citations", []) or []]
            h = hashlib.sha256(f"{simulation_id}|{report_id}|{idx}|{subj}".encode()).hexdigest()[:8]
            ivw_id = f"ivw_{idx:02d}_{h}"
            session = InterviewSession(
                interview_id=ivw_id,
                session_index=idx,
                subject=subj,
                questions=[subj],
                mode=mode,
                recorded_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                turns=[],
                legacy_agents=agents,
                legacy_citations=citations,
            )
            sessions.append(session)

        return cls(
            simulation_id=simulation_id,
            report_id=report_id,
            sessions=sessions,
            schema_version="1.0",
        )

    # Alias de classe rétrocompatible
    parse_payload = from_raw

    @classmethod
    def load_from_file(
        cls,
        file_path: str,
        simulation_id: str = "",
        report_id: str = "",
    ) -> Optional[ReportInterviewsPayload]:
        """Charge un fichier report_interviews.json en tolérant son absence ou corruption (NFR-1)."""
        if not file_path or not os.path.exists(file_path):
            return None
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read().strip()
            if not content:
                logger.warning(f"Fichier d'entretiens vide ignoré : {file_path}")
                return None
            data = json.loads(content)
            return cls.from_raw(data, simulation_id=simulation_id, report_id=report_id)
        except Exception as err:
            logger.warning(f"Lecture tolérante de report_interviews.json échouée pour {file_path}: {err}")
            return None

    def find_turn_by_id(self, turn_id: str) -> Optional[Tuple[InterviewSession, InterviewTurn]]:
        """Recherche un tour par son turn_id déterministe."""
        for s in self.sessions:
            for t in s.turns:
                if t.turn_id == turn_id:
                    return (s, t)
        return None

    def get_all_turns(self) -> List[Tuple[InterviewSession, InterviewTurn]]:
        """Renvoie la liste plate de tous les tours avec leur session associée."""
        result: List[Tuple[InterviewSession, InterviewTurn]] = []
        for s in self.sessions:
            for t in s.turns:
                result.append((s, t))
        return result

