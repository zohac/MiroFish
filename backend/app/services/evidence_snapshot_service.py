"""Service de capture et de vérification d'empreinte EvidenceSnapshot (Epic 013, FR-04, FR-05, C3, C7).

Capture l'ensemble des fichiers de preuves et artefacts normalisés dans `simulations/<sim_id>/` :
  - `observed_events.jsonl` (ou base SQLite / logs réels)
  - `actors.json`
  - `simulation_config.json`
  - `simulation_brief.json`
  - `source_manifest.json`
  - `interviews_archive.json` (si présent)

Génère une empreinte SHA-256 déterministe et reproductible au bit près pour sceller le jeu de faits.
Vérifie la présence des preuves obligatoires sous peine d'erreur explicite `REPLAY_NOT_REPRODUCIBLE`.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from ..config import Config
from ..models.evidence_snapshot import EvidenceSnapshot
from ..models.project import ProjectManager
from ..services.oasis_log_reader import OasisLogReaderService
from ..services.simulation_manager import SimulationManager
from ..utils.logger import get_logger

logger = get_logger("mirofish.evidence_snapshot")


class ReplayNotReproducibleError(RuntimeError):
    """Exception levée lorsqu'une simulation ne dispose pas de toutes les preuves requises pour le replay."""
    pass


class EvidenceSnapshotService:
    """Service gérant la capture, le calcul de hash et la vérification des snapshots de preuves."""

    # Fichiers de preuves obligatoires pour garantir un rejeu déterministe
    REQUIRED_PROOF_FILES = [
        "observed_events.jsonl",
        "actors.json",
        "simulation_brief.json",
    ]

    # Tous les fichiers scellés dans le snapshot par ordre canonique strict
    CANONICAL_AUDIT_FILES = [
        "actors.json",
        "interviews_archive.json",
        "observed_events.jsonl",
        "simulation_brief.json",
        "simulation_config.json",
        "source_manifest.json",
    ]

    def __init__(self, simulation_id: str):
        self.simulation_id = simulation_id
        self.sim_dir = os.path.join(Config.UPLOAD_FOLDER, "simulations", self.simulation_id)

    def _resolve_simulation_brief_bytes(self) -> bytes:
        """Résout le contenu binaire de simulation_brief.json depuis le dossier ou le projet."""
        brief_path = os.path.join(self.sim_dir, "simulation_brief.json")
        if os.path.exists(brief_path):
            with open(brief_path, "rb") as f:
                return f.read()

        # Repli : projet associé
        sim_manager = SimulationManager()
        sim_state = sim_manager.get_simulation(self.simulation_id)
        project_id = getattr(sim_state, "project_id", "") if sim_state else ""
        brief_dict: Dict[str, Any] = {}
        if project_id and isinstance(project_id, str):
            proj = ProjectManager().get_project(project_id)
            if proj:
                raw_brief = getattr(proj, "simulation_brief", None)
                if isinstance(raw_brief, dict):
                    brief_dict = raw_brief
                elif hasattr(raw_brief, "to_dict"):
                    brief_dict = raw_brief.to_dict()
                elif getattr(proj, "simulation_requirement", None) and isinstance(proj.simulation_requirement, str):
                    brief_dict = {
                        "simulation_requirement": proj.simulation_requirement,
                        "project_id": project_id,
                    }
        try:
            return json.dumps(brief_dict, ensure_ascii=False, indent=2, sort_keys=True, default=str).encode("utf-8")
        except Exception:
            return b"{}"

    def _resolve_source_manifest_bytes(self) -> bytes:
        """Résout le contenu binaire de source_manifest.json depuis le dossier ou le projet."""
        manifest_path = os.path.join(self.sim_dir, "source_manifest.json")
        if os.path.exists(manifest_path):
            with open(manifest_path, "rb") as f:
                return f.read()

        sim_manager = SimulationManager()
        sim_state = sim_manager.get_simulation(self.simulation_id)
        project_id = getattr(sim_state, "project_id", "") if sim_state else ""
        manifest: Dict[str, Any] = {"simulation_id": self.simulation_id, "documents": []}
        if project_id and isinstance(project_id, str):
            proj = ProjectManager().get_project(project_id)
            if proj and hasattr(proj, "documents") and isinstance(proj.documents, list):
                manifest["documents"] = [
                    doc.to_dict() if hasattr(doc, "to_dict") else dict(doc)
                    for doc in proj.documents
                    if hasattr(doc, "to_dict") or isinstance(doc, dict)
                ]
        try:
            return json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True, default=str).encode("utf-8")
        except Exception:
            return json.dumps({"simulation_id": self.simulation_id, "documents": []}, indent=2, sort_keys=True).encode("utf-8")

    def _resolve_observed_events(self) -> Tuple[bytes, int]:
        """Résout le contenu binaire de observed_events.jsonl et le décompte total d'événements."""
        events_path = os.path.join(self.sim_dir, "observed_events.jsonl")
        if os.path.exists(events_path):
            with open(events_path, "rb") as f:
                content = f.read()
            lines = [ln for ln in content.decode("utf-8", errors="replace").splitlines() if ln.strip()]
            return content, len(lines)

        reader = OasisLogReaderService(simulation_id=self.simulation_id)
        events = reader.load_events()
        events_jsonl_lines = [json.dumps(ev.to_dict(), ensure_ascii=False) for ev in events]
        content = "\n".join(events_jsonl_lines).encode("utf-8")
        return content, len(events)

    def _resolve_actors(self) -> Tuple[bytes, int]:
        """Résout le contenu binaire de actors.json et le nombre total d'acteurs qualifiés."""
        actors_path = os.path.join(self.sim_dir, "actors.json")
        if os.path.exists(actors_path):
            with open(actors_path, "rb") as f:
                content = f.read()
            try:
                data = json.loads(content.decode("utf-8"))
                actors_list = data.get("actors", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
                return content, len(actors_list)
            except Exception:
                return content, 0
        return json.dumps({"simulation_id": self.simulation_id, "actors": []}, indent=2, sort_keys=True).encode("utf-8"), 0

    def gather_evidence_files(self, strict: bool = True) -> Tuple[Dict[str, bytes], int, int, bool]:
        """Rassemble tous les fichiers de preuves binaires canoniques.

        Args:
            strict: si True, vérifie que les fichiers essentiels existent et ont du contenu
                    (déclenche ReplayNotReproducibleError sinon).

        Returns:
            (files_dict, total_events, total_actors, has_archived_interviews)
        """
        files: Dict[str, bytes] = {}

        # 1. observed_events.jsonl
        events_bytes, total_events = self._resolve_observed_events()
        files["observed_events.jsonl"] = events_bytes

        # 2. actors.json
        actors_bytes, total_actors = self._resolve_actors()
        files["actors.json"] = actors_bytes

        # 3. simulation_brief.json
        brief_bytes = self._resolve_simulation_brief_bytes()
        files["simulation_brief.json"] = brief_bytes

        # 4. simulation_config.json (si présent)
        cfg_path = os.path.join(self.sim_dir, "simulation_config.json")
        if os.path.exists(cfg_path):
            with open(cfg_path, "rb") as f:
                files["simulation_config.json"] = f.read()
        else:
            files["simulation_config.json"] = json.dumps({}, indent=2, sort_keys=True).encode("utf-8")

        # 5. source_manifest.json
        manifest_bytes = self._resolve_source_manifest_bytes()
        files["source_manifest.json"] = manifest_bytes

        # 6. interviews_archive.json (si présent)
        interviews_path = os.path.join(self.sim_dir, "interviews_archive.json")
        has_archived_interviews = False
        if os.path.exists(interviews_path):
            with open(interviews_path, "rb") as f:
                interviews_bytes = f.read()
            files["interviews_archive.json"] = interviews_bytes
            has_archived_interviews = len(interviews_bytes.strip()) > 0

        # Vérification d'intégrité stricte pour le replay
        if strict:
            missing_or_empty: List[str] = []
            if total_events == 0 or len(files["observed_events.jsonl"].strip()) == 0:
                missing_or_empty.append("observed_events.jsonl (0 événement)")
            actors_stripped = files["actors.json"].strip()
            if total_actors == 0 or len(actors_stripped) == 0 or actors_stripped in (b"{}", b'{"actors": []}'):
                missing_or_empty.append("actors.json (0 acteur)")
            brief_stripped = files["simulation_brief.json"].strip()
            if len(brief_stripped) == 0 or brief_stripped == b"{}":
                missing_or_empty.append("simulation_brief.json (vide)")

            if missing_or_empty:
                raise ReplayNotReproducibleError(
                    f"REPLAY_NOT_REPRODUCIBLE: Simulation '{self.simulation_id}' manque de preuves requises : {', '.join(missing_or_empty)}"
                )

        return files, total_events, total_actors, has_archived_interviews

    def compute_sha256_footprint(self, files: Dict[str, bytes]) -> Tuple[str, Dict[str, str]]:
        """Calcule l'empreinte SHA-256 individuelle et combinée par ordre canonique strict.

        La concaténation utilise le format : `f"{filename}:{file_hash}\n"`.
        Le hash combiné est le SHA-256 de cette concaténation UTF-8.
        """
        file_hashes: Dict[str, str] = {}
        for filename in sorted(files.keys()):
            data = files[filename]
            file_hashes[filename] = hashlib.sha256(data).hexdigest()

        # Concaténation canonique pour l'empreinte globale
        footprint_lines = [f"{fn}:{file_hashes[fn]}\n" for fn in sorted(file_hashes.keys())]
        combined_payload = "".join(footprint_lines).encode("utf-8")
        sha256_hash = hashlib.sha256(combined_payload).hexdigest()

        return sha256_hash, file_hashes

    def capture_snapshot(self, strict: bool = True) -> EvidenceSnapshot:
        """Capture et fige l'empreinte EvidenceSnapshot pour la simulation."""
        import uuid

        files, total_events, total_actors, has_archived_interviews = self.gather_evidence_files(strict=strict)
        sha256_hash, file_hashes = self.compute_sha256_footprint(files)

        date_suffix = datetime.now().strftime("%Y%m%d")
        snapshot_id = f"snap_{uuid.uuid4().hex[:12]}_{date_suffix}"

        snapshot = EvidenceSnapshot(
            snapshot_id=snapshot_id,
            simulation_id=self.simulation_id,
            sha256_hash=sha256_hash,
            file_hashes=file_hashes,
            total_events=total_events,
            total_actors=total_actors,
            has_archived_interviews=has_archived_interviews,
            created_at=datetime.now().isoformat(),
        )

        logger.info(
            f"EvidenceSnapshot capturé pour simulation '{self.simulation_id}': "
            f"id={snapshot.snapshot_id}, hash={snapshot.sha256_hash[:16]}..., "
            f"events={total_events}, actors={total_actors}"
        )
        return snapshot

    def verify_snapshot(self, snapshot: EvidenceSnapshot) -> bool:
        """Vérifie si les preuves actuelles correspondent exactement à un snapshot donné."""
        try:
            files, _, _, _ = self.gather_evidence_files(strict=False)
            current_hash, _ = self.compute_sha256_footprint(files)
            return current_hash == snapshot.sha256_hash
        except Exception as e:
            logger.warning(f"Erreur lors de la vérification de snapshot: {e}")
            return False
