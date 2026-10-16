"""Service d'extraction et d'indexation des traces d'actions OASIS (Story 011-2).

Ce service centralise la collecte, la normalisation et la recherche des faits
réellement exécutés par les agents au cours d'une simulation :
  - Extraction multi-sources : `twitter/actions.jsonl`, `reddit/actions.jsonl`,
    `actions.jsonl` racine et tables SQLite d'environnement (`post`, `comment`, `trace`).
  - Identifiant stable et déterministe `event_id` garanti via `SimulationActionVerifier.compute_event_id`.
  - Cache mémoire avec invalidation basée sur les horodatages `mtime`.
  - Construction d'`EvidencePack` et requêtage multi-critères (`query_events`).
"""

from __future__ import annotations

import json
import os
import sqlite3
from typing import Any, Dict, List, Optional, Tuple

from ..config import Config
from ..models.evidence_pack import EvidencePack, ObservedEvent
from ..services.simulation_action_verifier import SimulationActionVerifier
from ..utils.logger import get_logger

logger = get_logger("mirofish.oasis_log_reader")


def _safe_int(val: Any, default: int = 0) -> int:
    """Convertit de manière résiliente une valeur en entier sans lever d'exception."""
    if val is None:
        return default
    try:
        return int(val)
    except (ValueError, TypeError):
        return default


class OasisLogReaderService:
    """Service de collecte et d'indexation unifié des journaux d'actions de simulation."""

    def __init__(self, simulation_id: Optional[str] = None):
        self.simulation_id = simulation_id or "default"
        # Cache {sim_id: (latest_mtime, List[ObservedEvent])}
        self._cache: Dict[str, Tuple[float, List[ObservedEvent]]] = {}

    def get_simulation_dir(self, simulation_id: Optional[str] = None) -> str:
        target_sim_id = simulation_id or self.simulation_id
        return os.path.join(Config.UPLOAD_FOLDER, "simulations", target_sim_id)

    def _get_sources_latest_mtime(self, sim_dir: str) -> float:
        """Calcule le mtime le plus récent parmi toutes les sources potentielles."""
        candidate_paths = [
            os.path.join(sim_dir, "twitter", "actions.jsonl"),
            os.path.join(sim_dir, "reddit", "actions.jsonl"),
            os.path.join(sim_dir, "actions.jsonl"),
            os.path.join(sim_dir, "twitter_simulation.db"),
            os.path.join(sim_dir, "reddit_simulation.db"),
        ]
        latest_mtime = 0.0
        for p in candidate_paths:
            if os.path.isfile(p):
                try:
                    latest_mtime = max(latest_mtime, os.path.getmtime(p))
                except OSError:
                    pass
        return latest_mtime

    def load_events(
        self,
        simulation_id: Optional[str] = None,
        force_reload: bool = False,
    ) -> List[ObservedEvent]:
        """Charge, normalise et déduplique tous les événements observés de la simulation."""
        target_sim_id = simulation_id or self.simulation_id
        sim_dir = self.get_simulation_dir(target_sim_id)

        if not os.path.isdir(sim_dir):
            logger.debug(f"Répertoire de simulation introuvable : {sim_dir}")
            return []

        latest_mtime = self._get_sources_latest_mtime(sim_dir)

        if not force_reload and target_sim_id in self._cache:
            cached_mtime, cached_events = self._cache[target_sim_id]
            if cached_mtime >= latest_mtime and cached_mtime > 0 and latest_mtime > 0:
                return cached_events

        events: List[ObservedEvent] = []
        seen_event_ids = set()

        # 1. Charger depuis les fichiers actions.jsonl
        jsonl_sources = [
            ("twitter", os.path.join(sim_dir, "twitter", "actions.jsonl")),
            ("reddit", os.path.join(sim_dir, "reddit", "actions.jsonl")),
            ("generic", os.path.join(sim_dir, "actions.jsonl")),
        ]

        for default_platform, file_path in jsonl_sources:
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

                        # Ignorer les événements de contrôle du cycle de vie
                        action_type = data.get("action_type")
                        if not action_type or data.get("event_type"):
                            continue

                        try:
                            platform = str(data.get("platform") or default_platform)
                            round_val = data.get("round") if data.get("round") is not None else data.get("round_num")
                            round_num = _safe_int(round_val, 0)
                            agent_id = _safe_int(data.get("agent_id"), 0)
                            agent_name = str(data.get("agent_name") or f"Agent_{agent_id}")

                            timestamp = data.get("timestamp")
                            if not timestamp or not str(timestamp).strip():
                                timestamp = f"line:{line_num}:{default_platform}"
                            timestamp = str(timestamp)

                            action_args = data.get("action_args") or {}
                            result = data.get("result")
                            success = bool(data.get("success", True))

                            event_id = SimulationActionVerifier.compute_event_id(
                                target_sim_id,
                                platform,
                                round_num,
                                agent_id,
                                str(action_type),
                                timestamp,
                            )
                        except Exception as parse_err:
                            logger.debug(f"Ligne {line_num} ignorée dans {file_path}: {parse_err}")
                            continue

                        if event_id in seen_event_ids:
                            continue
                        seen_event_ids.add(event_id)

                        events.append(
                            ObservedEvent(
                                event_id=event_id,
                                simulation_id=target_sim_id,
                                platform=platform,
                                round_num=round_num,
                                agent_id=agent_id,
                                agent_name=agent_name,
                                action_type=str(action_type),
                                timestamp=timestamp,
                                action_args=action_args,
                                is_action_executed=True,
                                result=result,
                                success=success,
                                raw_payload=data,
                            )
                        )
            except Exception as e:
                logger.warning(f"Erreur lors de la lecture de {file_path}: {e}")

        # 2. Compléter depuis les bases SQLite de simulation si présentes
        sqlite_sources = [
            ("twitter", os.path.join(sim_dir, "twitter_simulation.db")),
            ("reddit", os.path.join(sim_dir, "reddit_simulation.db")),
        ]

        for platform_name, db_path in sqlite_sources:
            if not os.path.isfile(db_path):
                continue
            try:
                self._load_sqlite_records(
                    db_path=db_path,
                    target_sim_id=target_sim_id,
                    platform=platform_name,
                    seen_event_ids=seen_event_ids,
                    events=events,
                )
            except Exception as e:
                logger.debug(f"Erreur lors de l'extraction SQLite de {db_path}: {e}")

        # Trier chronologiquement par round et timestamp
        events.sort(key=lambda e: (e.round_num, e.timestamp))

        self._cache[target_sim_id] = (latest_mtime, events)
        return events

    def _load_sqlite_records(
        self,
        db_path: str,
        target_sim_id: str,
        platform: str,
        seen_event_ids: set,
        events: List[ObservedEvent],
    ) -> None:
        """Extrait les actions des tables SQLite (post, comment, trace) non présentes dans jsonl."""
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        try:
            # 1. Table post
            try:
                cursor.execute("SELECT * FROM post")
                for row in cursor.fetchall():
                    try:
                        row_dict = dict(row)
                        user_id_val = row_dict.get("user_id") if row_dict.get("user_id") is not None else row_dict.get("agent_id")
                        agent_id = _safe_int(user_id_val, 0)
                        agent_name = str(row_dict.get("user_name") or row_dict.get("author") or f"Agent_{agent_id}")
                        created_at = str(row_dict.get("created_at") or f"db_post_{row_dict.get('id', 0)}")
                        round_val = row_dict.get("round") if row_dict.get("round") is not None else row_dict.get("round_num")
                        round_num = _safe_int(round_val, 0)
                        content = row_dict.get("content", "")

                        event_id = SimulationActionVerifier.compute_event_id(
                            target_sim_id, platform, round_num, agent_id, "post", created_at
                        )
                        if event_id in seen_event_ids:
                            continue
                        seen_event_ids.add(event_id)

                        events.append(
                            ObservedEvent(
                                event_id=event_id,
                                simulation_id=target_sim_id,
                                platform=platform,
                                round_num=round_num,
                                agent_id=agent_id,
                                agent_name=agent_name,
                                action_type="post",
                                timestamp=created_at,
                                action_args={"content": content, "post_id": row_dict.get("id")},
                                is_action_executed=True,
                                raw_payload=row_dict,
                            )
                        )
                    except Exception as row_err:
                        logger.debug(f"Ligne post ignorée dans {db_path}: {row_err}")
            except sqlite3.OperationalError:
                pass

            # 2. Table comment
            try:
                cursor.execute("SELECT * FROM comment")
                for row in cursor.fetchall():
                    try:
                        row_dict = dict(row)
                        user_id_val = row_dict.get("user_id") if row_dict.get("user_id") is not None else row_dict.get("agent_id")
                        agent_id = _safe_int(user_id_val, 0)
                        agent_name = str(row_dict.get("user_name") or row_dict.get("author") or f"Agent_{agent_id}")
                        created_at = str(row_dict.get("created_at") or f"db_comm_{row_dict.get('id', 0)}")
                        round_val = row_dict.get("round") if row_dict.get("round") is not None else row_dict.get("round_num")
                        round_num = _safe_int(round_val, 0)
                        content = row_dict.get("content", "")

                        event_id = SimulationActionVerifier.compute_event_id(
                            target_sim_id, platform, round_num, agent_id, "comment", created_at
                        )
                        if event_id in seen_event_ids:
                            continue
                        seen_event_ids.add(event_id)

                        events.append(
                            ObservedEvent(
                                event_id=event_id,
                                simulation_id=target_sim_id,
                                platform=platform,
                                round_num=round_num,
                                agent_id=agent_id,
                                agent_name=agent_name,
                                action_type="comment",
                                timestamp=created_at,
                                action_args={
                                    "content": content,
                                    "comment_id": row_dict.get("id"),
                                    "post_id": row_dict.get("post_id"),
                                },
                                is_action_executed=True,
                                raw_payload=row_dict,
                            )
                        )
                    except Exception as row_err:
                        logger.debug(f"Ligne comment ignorée dans {db_path}: {row_err}")
            except sqlite3.OperationalError:
                pass

            # 3. Table trace (actions génériques et interviews)
            try:
                cursor.execute("SELECT * FROM trace")
                for row in cursor.fetchall():
                    try:
                        row_dict = dict(row)
                        action_name = str(row_dict.get("action", "action")).lower()
                        agent_id = _safe_int(row_dict.get("user_id"), 0)
                        created_at = str(row_dict.get("created_at") or f"db_trace_{row_dict.get('id', 0)}")
                        round_val = row_dict.get("round") if row_dict.get("round") is not None else row_dict.get("round_num")
                        round_num = _safe_int(round_val, 0)
                        info_raw = row_dict.get("info")
                        info_dict = {}
                        if info_raw:
                            try:
                                info_dict = json.loads(info_raw) if isinstance(info_raw, str) else dict(info_raw)
                            except Exception:
                                info_dict = {"raw": info_raw}

                        agent_name = info_dict.get("agent_name") or f"Agent_{agent_id}"

                        event_id = SimulationActionVerifier.compute_event_id(
                            target_sim_id, platform, round_num, agent_id, action_name, created_at
                        )
                        if event_id in seen_event_ids:
                            continue
                        seen_event_ids.add(event_id)

                        events.append(
                            ObservedEvent(
                                event_id=event_id,
                                simulation_id=target_sim_id,
                                platform=platform,
                                round_num=round_num,
                                agent_id=agent_id,
                                agent_name=agent_name,
                                action_type=action_name,
                                timestamp=created_at,
                                action_args=info_dict,
                                is_action_executed=True,
                                raw_payload=row_dict,
                            )
                        )
                    except Exception as row_err:
                        logger.debug(f"Ligne trace ignorée dans {db_path}: {row_err}")
            except sqlite3.OperationalError:
                pass
        finally:
            try:
                cursor.close()
            except Exception:
                pass
            try:
                conn.close()
            except Exception:
                pass

    def build_evidence_pack(self, simulation_id: Optional[str] = None) -> EvidencePack:
        """Construit le pack de preuves complet d'une simulation."""
        target_sim_id = simulation_id or self.simulation_id
        events = self.load_events(target_sim_id)
        return EvidencePack.from_events(target_sim_id, events)

    @classmethod
    def load_evidence_pack(cls, simulation_id: str) -> EvidencePack:
        """Méthode pratique pour instancier le service et charger l'EvidencePack."""
        reader = cls(simulation_id=simulation_id)
        return reader.build_evidence_pack()

    def query_events(
        self,
        simulation_id: Optional[str] = None,
        query: Optional[str] = None,
        agent_name: Optional[str] = None,
        agent_id: Optional[int] = None,
        platform: Optional[str] = None,
        round_min: Optional[int] = None,
        round_max: Optional[int] = None,
        action_type: Optional[str] = None,
        limit: int = 50,
    ) -> List[ObservedEvent]:
        """Interroge les événements d'une simulation avec filtres multi-critères."""
        pack = self.build_evidence_pack(simulation_id)
        return pack.filter_events(
            query=query,
            agent_name=agent_name,
            agent_id=agent_id,
            platform=platform,
            round_min=round_min,
            round_max=round_max,
            action_type=action_type,
            limit=limit,
        )
