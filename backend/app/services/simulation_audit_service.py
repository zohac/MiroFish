"""Service de confection du dossier d'audit autonome exportable (Epic 011, FR-10, C10).

Rassemble dans une archive ZIP canonique (`simulation_audit_<sim_id>.zip`)
l'ensemble des 11 artefacts de preuve vérifiables hors-ligne par un tiers,
scellés par un condensat cryptographique SHA-256 (`checksums.sha256`) :
  1. `run_manifest.json` : versions, modèle, provider, passerelle, locale, git sha, dates ISO.
  2. `simulation_brief.json` : brief, scénario, hypothèses et horizon temporel.
  3. `actors.json` : sélection formelle d'acteurs, rôles de scénario et empreinte SHA-256.
  4. `source_manifest.json` : inventaire des documents sources avec typage épistémique.
  5. `observed_events.jsonl` : traces chronologiques réelles normalisées avec event_id déterministes.
  6. `cohort_coverage.json` : tableau de couverture de cohorte et statuts décisionnels.
  7. `report_claims.json` : registre des affirmations du rapport, preuves et statuts.
  8. `quality_checks.json` : journal d'inspection de la barrière ReportQualityGate.
  9. `usage.json` : télémétrie d'usage LLM (tokens, durée, coût estimé) ; présent
     même lorsqu'elle est indisponible, avec `usage_available: false`.
 10. `report.md` : texte final intégral du rapport publié (ou partiel sur arrêt contrôlé).
 11. `checksums.sha256` : hachages SHA-256 scellant l'intégrité de tous les fichiers ci-dessus.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import subprocess
import zipfile
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from ..config import Config
from ..models.report_claim import ReportClaimRegistry
from ..models.cohort_coverage import CohortCoverageTable
from ..models.project import ProjectManager
from ..models.report_usage import ReportUsageMetrics, sanitize_usage_payload
from ..models.source_document import SourceDocument, EpistemicSourceKind
from ..services.simulation_manager import SimulationManager
from ..services.oasis_log_reader import OasisLogReaderService
from ..utils.logger import get_logger

logger = get_logger("mirofish.simulation_audit")


class SimulationAuditService:
    """Service de génération du dossier d'audit exportable scellé par SHA-256."""

    def __init__(self, simulation_id: str, report_id: Optional[str] = None):
        self.simulation_id = simulation_id
        self.report_id = report_id or ""

    def _get_git_commit(self) -> str:
        """Récupère l'empreinte git commit active ou un repli."""
        # Priorité aux variables d'environnement (CI/CD, conteneurs Docker sans montage .git)
        for env_var in ("GIT_COMMIT", "COMMIT_SHA", "GITHUB_SHA"):
            val = os.environ.get(env_var, "").strip()
            if val:
                return val

        try:
            res = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
                timeout=2,
            )
            if res.returncode == 0 and res.stdout.strip():
                return res.stdout.strip()
        except Exception:
            pass
        return "unknown-git-commit"

    def build_run_manifest(self) -> Dict[str, Any]:
        """Génère les métadonnées d'exécution de la simulation et du rapport."""
        sim_manager = SimulationManager()
        sim_state = sim_manager.get_simulation(self.simulation_id)

        # Récupération de completed_at depuis sim_state, SimulationRunner ou run_state.json direct
        completed_at = getattr(sim_state, "completed_at", None)
        sim_dir = os.path.join(Config.UPLOAD_FOLDER, "simulations", self.simulation_id)
        if not completed_at:
            try:
                from ..services.simulation_runner import SimulationRunner
                run_state = SimulationRunner.get_run_state(self.simulation_id, reconcile=False)
                if run_state and run_state.completed_at:
                    completed_at = run_state.completed_at
            except Exception:
                pass
        if not completed_at:
            state_p = os.path.join(sim_dir, "run_state.json")
            if os.path.exists(state_p):
                try:
                    with open(state_p, "r", encoding="utf-8") as sf:
                        s_data = json.load(sf)
                        completed_at = s_data.get("completed_at")
                except Exception:
                    pass
        if not completed_at and sim_state:
            status_val = sim_state.status.value if hasattr(sim_state.status, "value") else str(getattr(sim_state, "status", ""))
            if status_val.lower() == "completed" and getattr(sim_state, "updated_at", None):
                completed_at = getattr(sim_state, "updated_at", None)

        # Récupération de time_horizon et d'informations de scénario depuis simulation_brief
        time_horizon = None
        brief_path = os.path.join(sim_dir, "simulation_brief.json")
        if os.path.exists(brief_path):
            try:
                with open(brief_path, "r", encoding="utf-8") as bf:
                    b_data = json.load(bf)
                    time_horizon = b_data.get("time_horizon")
                    if (not time_horizon or str(time_horizon).lower() in ("unknown", "none", "null")) and b_data.get("goal"):
                        from ..models.simulation_brief import extract_inferred_horizon
                        inferred = extract_inferred_horizon(b_data["goal"], "")
                        if inferred.time_horizon and inferred.time_horizon != "unknown":
                            time_horizon = inferred.time_horizon
            except Exception:
                pass

        # Récupération du nombre d'agents instanciés
        agent_count = 0
        config_path = os.path.join(sim_dir, "simulation_config.json")
        if os.path.exists(config_path):
            try:
                with open(config_path, "r", encoding="utf-8") as cf:
                    c_data = json.load(cf)
                    agents_list = c_data.get("agents") or c_data.get("agent_configs") or []
                    agent_count = len(agents_list)
            except Exception:
                pass
        if agent_count == 0:
            actors_path = os.path.join(sim_dir, "actors.json")
            if os.path.exists(actors_path):
                try:
                    with open(actors_path, "r", encoding="utf-8") as af:
                        a_data = json.load(af)
                        agents_list = a_data.get("actors") or []
                        agent_count = len(agents_list)
                except Exception:
                    pass
        if agent_count == 0 and sim_state:
            agent_count = getattr(sim_state, "actors_count", 0) or getattr(sim_state, "profiles_count", 0)

        # Télémétrie d'usage par rapport (Story 013-4, FR-08, C5)
        usage_summary = self._load_usage_summary()

        # Bloc LLM : le profil du job prime sur la configuration globale, et
        # l'URL privée n'est jamais exposée dans un manifeste scellé (NFR-4).
        # La passerelle est identifiée par un alias, jamais par son adresse.
        from .report_usage_tracker import infer_provider_id

        gateway = infer_provider_id(None, None, Config.LLM_BASE_URL) or "external"
        llm_block: Dict[str, Any] = {
            "model_name": Config.LLM_MODEL_NAME,
            "provider": "local-openai-compatible",
            "gateway": gateway,
            "base_url_configured": bool(Config.LLM_BASE_URL),
        }
        if usage_summary:
            llm_block["model_name"] = usage_summary.get("model") or llm_block["model_name"]
            llm_block["provider"] = usage_summary.get("provider_id") or llm_block["provider"]
            llm_block["reasoning_effort_requested"] = usage_summary.get(
                "reasoning_effort_requested"
            )
            llm_block["reasoning_effort_effective"] = usage_summary.get(
                "reasoning_effort_effective"
            )

        manifest = {
            "version": "1.1.0",
            "simulation_id": self.simulation_id,
            "report_id": self.report_id,
            "git_commit": self._get_git_commit(),
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "llm": llm_block,
            "locale": getattr(sim_state, "locale", "fr") if sim_state else "fr",
            "simulation": {
                "status": sim_state.status.value if sim_state and hasattr(sim_state.status, "value") else str(getattr(sim_state, "status", "unknown")),
                "created_at": getattr(sim_state, "created_at", None),
                "completed_at": completed_at,
                "platform": getattr(sim_state, "platform", "all"),
                "time_horizon": time_horizon,
                "agent_count": agent_count,
            },
        }

        # Télémétrie d'usage par rapport (Story 013-4, FR-08, C5)
        if usage_summary is not None:
            manifest["usage"] = usage_summary
        return manifest

    def _load_usage_summary(self) -> Optional[Dict[str, Any]]:
        """Charge le résumé de télémétrie du rapport, sans jamais exposer de secret."""
        if not self.report_id:
            return None
        # Réutilise le chemin canonique de ReportManager (DRY, layout 013-3).
        from .report_agent import ReportManager

        usage_path = ReportManager._get_usage_path(self.report_id)
        metrics = ReportUsageMetrics.load_from_file(usage_path)
        if metrics is None:
            return None
        return sanitize_usage_payload(metrics.summary())

    def build_source_manifest(self) -> Dict[str, Any]:
        """Génère l'inventaire des documents sources du projet avec typage épistémique."""
        sim_manager = SimulationManager()
        sim_state = sim_manager.get_simulation(self.simulation_id)
        project_id = getattr(sim_state, "project_id", "") if sim_state else ""

        documents = []
        if project_id:
            project_manager = ProjectManager()
            project = project_manager.get_project(project_id)
            if project and project.source_documents:
                for doc_entry in project.source_documents:
                    if isinstance(doc_entry, dict):
                        doc = SourceDocument.from_dict(doc_entry)
                        documents.append(doc.to_dict())
                    elif hasattr(doc_entry, "to_dict"):
                        documents.append(doc_entry.to_dict())

        return {
            "simulation_id": self.simulation_id,
            "project_id": project_id,
            "total_documents": len(documents),
            "documents": documents,
        }

    def gather_audit_files(self) -> Dict[str, bytes]:
        """Rassemble les contenus binaires des artefacts indispensables pour l'archive."""
        files: Dict[str, bytes] = {}

        sim_dir = os.path.join(Config.UPLOAD_FOLDER, "simulations", self.simulation_id)
        rep_dir = os.path.join(Config.UPLOAD_FOLDER, "reports", self.report_id) if self.report_id else ""

        # 1. run_manifest.json
        run_manifest = self.build_run_manifest()
        run_manifest_bytes = json.dumps(run_manifest, ensure_ascii=False, indent=2).encode("utf-8")
        files["run_manifest.json"] = run_manifest_bytes
        if rep_dir:
            try:
                import uuid
                os.makedirs(rep_dir, exist_ok=True)
                manifest_path = os.path.join(rep_dir, "run_manifest.json")
                tmp_mf = f"{manifest_path}.tmp.{os.getpid()}_{uuid.uuid4().hex[:8]}"
                try:
                    with open(tmp_mf, "wb") as mf:
                        mf.write(run_manifest_bytes)
                        mf.flush()
                        os.fsync(mf.fileno())
                    os.replace(tmp_mf, manifest_path)
                finally:
                    if os.path.exists(tmp_mf):
                        try:
                            os.remove(tmp_mf)
                        except OSError:
                            pass
            except Exception as mf_err:
                logger.warning(f"Impossible de sauvegarder run_manifest.json dans {rep_dir}: {mf_err}")

        # 2. simulation_brief.json
        brief_path = os.path.join(sim_dir, "simulation_brief.json")
        if os.path.exists(brief_path):
            with open(brief_path, "rb") as f:
                files["simulation_brief.json"] = f.read()
        else:
            # Essayer de lire depuis project
            sim_manager = SimulationManager()
            sim_state = sim_manager.get_simulation(self.simulation_id)
            project_id = getattr(sim_state, "project_id", "") if sim_state else ""
            brief_dict = {}
            if project_id:
                proj = ProjectManager().get_project(project_id)
                if proj and proj.simulation_brief:
                    brief_dict = proj.simulation_brief
            files["simulation_brief.json"] = json.dumps(brief_dict, ensure_ascii=False, indent=2).encode("utf-8")

        # 3. actors.json
        actors_path = os.path.join(sim_dir, "actors.json")
        if os.path.exists(actors_path):
            with open(actors_path, "rb") as f:
                files["actors.json"] = f.read()
        else:
            files["actors.json"] = json.dumps({"simulation_id": self.simulation_id, "actors": []}, indent=2).encode("utf-8")

        # 4. source_manifest.json
        source_manifest = self.build_source_manifest()
        files["source_manifest.json"] = json.dumps(source_manifest, ensure_ascii=False, indent=2).encode("utf-8")

        # 5. observed_events.jsonl
        # Concaténer les traces normalisées d'événements observés
        reader = OasisLogReaderService(simulation_id=self.simulation_id)
        events = reader.load_events()
        events_jsonl_lines = [json.dumps(ev.to_dict(), ensure_ascii=False) for ev in events]
        files["observed_events.jsonl"] = "\n".join(events_jsonl_lines).encode("utf-8")

        # 6. cohort_coverage.json (priorité rep_dir)
        cohort_path = ""
        if rep_dir:
            cohort_path = os.path.join(rep_dir, "cohort_coverage.json")
        if not cohort_path or not os.path.exists(cohort_path):
            cohort_path = os.path.join(sim_dir, "cohort_coverage.json")
        if os.path.exists(cohort_path):
            with open(cohort_path, "rb") as f:
                files["cohort_coverage.json"] = f.read()
        else:
            files["cohort_coverage.json"] = json.dumps({"simulation_id": self.simulation_id, "members": []}, indent=2).encode("utf-8")

        # 7. report_claims.json (priorité rep_dir)
        claims_path = ""
        if rep_dir:
            claims_path = os.path.join(rep_dir, "report_claims.json")
        if not claims_path or not os.path.exists(claims_path):
            claims_path = os.path.join(sim_dir, "report_claims.json")
        if os.path.exists(claims_path):
            with open(claims_path, "rb") as f:
                files["report_claims.json"] = f.read()
        else:
            files["report_claims.json"] = json.dumps({"simulation_id": self.simulation_id, "claims": []}, indent=2).encode("utf-8")

        # 8. quality_checks.json (priorité rep_dir)
        quality_path = ""
        if rep_dir:
            quality_path = os.path.join(rep_dir, "quality_checks.json")
        if not quality_path or not os.path.exists(quality_path):
            quality_path = os.path.join(sim_dir, "quality_checks.json")
        if os.path.exists(quality_path):
            with open(quality_path, "rb") as f:
                files["quality_checks.json"] = f.read()
        else:
            files["quality_checks.json"] = json.dumps({"simulation_id": self.simulation_id, "checks": []}, indent=2).encode("utf-8")

        # 8 bis. usage.json (télémétrie d'usage per-report, Story 013-4)
        if self.report_id:
            usage_path = (
                os.path.join(rep_dir, "usage.json") if rep_dir else ""
            )
            usage_metrics = (
                ReportUsageMetrics.load_from_file(usage_path) if usage_path else None
            )
            if usage_metrics is not None:
                usage_payload = sanitize_usage_payload(usage_metrics.to_dict())
            else:
                # L'absence de télémétrie n'est jamais silencieuse : l'artefact
                # est présent et déclare explicitement son indisponibilité.
                usage_payload = {
                    "report_id": self.report_id,
                    "usage_available": False,
                    "reason": (
                        "absent"
                        if not usage_path or not os.path.exists(usage_path)
                        else "unreadable"
                    ),
                }
            files["usage.json"] = json.dumps(
                usage_payload, ensure_ascii=False, indent=2
            ).encode("utf-8")

        # 9. report.md (priorité rep_dir full_report.md)
        report_md_path = ""
        if rep_dir:
            report_md_path = os.path.join(rep_dir, "full_report.md")
        if not report_md_path or not os.path.exists(report_md_path):
            # Rechercher un markdown dans rep_dir
            if rep_dir and os.path.exists(rep_dir):
                candidates = [f for f in os.listdir(rep_dir) if f.endswith(".md")]
                if candidates:
                    report_md_path = os.path.join(rep_dir, candidates[0])

        if report_md_path and os.path.exists(report_md_path):
            with open(report_md_path, "rb") as f:
                files["report.md"] = f.read()
        else:
            files["report.md"] = b"# Rapport d'analyse sociale\n\nAucun contenu de rapport disponible.\n"

        # 10. checksums.sha256
        checksum_lines = []
        for filename in sorted(files.keys()):
            data = files[filename]
            sha256_hash = hashlib.sha256(data).hexdigest()
            checksum_lines.append(f"{sha256_hash}  {filename}")
        files["checksums.sha256"] = "\n".join(checksum_lines).encode("utf-8")

        return files

    def build_audit_package(self) -> bytes:
        """Génère et compresse en mémoire l'archive ZIP d'audit complète (Story 013-3)."""
        files = self.gather_audit_files()

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
            for filename, data in files.items():
                zf.writestr(filename, data)

        zip_bytes = buf.getvalue()

        # 1. Sauvegarde canonique sous reports/<report_id>/simulation_audit_<report_id>.zip (si report_id)
        if self.report_id:
            rep_dir = os.path.join(Config.UPLOAD_FOLDER, "reports", self.report_id)
            os.makedirs(rep_dir, exist_ok=True)
            rep_zip_path = os.path.join(rep_dir, f"simulation_audit_{self.report_id}.zip")
            try:
                with open(rep_zip_path, "wb") as f:
                    f.write(zip_bytes)
            except Exception as rep_err:
                logger.warning(f"Impossible de cacher le zip d'audit per-report dans {rep_dir}: {rep_err}")

        # 2. Sauvegarde miroir pour compatibilité sous simulations/<sim_id>/simulation_audit_<sim_id>.zip
        sim_dir = os.path.join(Config.UPLOAD_FOLDER, "simulations", self.simulation_id)
        os.makedirs(sim_dir, exist_ok=True)
        sim_zip_path = os.path.join(sim_dir, f"simulation_audit_{self.simulation_id}.zip")
        try:
            with open(sim_zip_path, "wb") as f:
                f.write(zip_bytes)
        except Exception as err:
            logger.warning(f"Impossible de cacher le zip d'audit sur disque : {err}")

        return zip_bytes

    def get_audit_package_path(self, force_rebuild: bool = False) -> str:
        """Retourne le chemin disque du zip s'il existe ou le génère (Story 013-3)."""
        # 1. Si un report_id est spécifié, vérifier ou générer en priorité sous reports/<report_id>/
        if self.report_id:
            rep_dir = os.path.join(Config.UPLOAD_FOLDER, "reports", self.report_id)
            rep_zip_path = os.path.join(rep_dir, f"simulation_audit_{self.report_id}.zip")
            if not force_rebuild and os.path.exists(rep_zip_path):
                return rep_zip_path
            # S'il n'existe pas ou si rebuild forcé, construire et retourner le zip per-report
            self.build_audit_package()
            if os.path.exists(rep_zip_path):
                return rep_zip_path

        # 2. Vérifier sous simulations/<sim_id>/
        sim_dir = os.path.join(Config.UPLOAD_FOLDER, "simulations", self.simulation_id)
        sim_zip_path = os.path.join(sim_dir, f"simulation_audit_{self.simulation_id}.zip")
        if force_rebuild or not os.path.exists(sim_zip_path):
            self.build_audit_package()
            # Si on a report_id, le chemin per-report est privilégié
            if self.report_id:
                rep_zip_path = os.path.join(Config.UPLOAD_FOLDER, "reports", self.report_id, f"simulation_audit_{self.report_id}.zip")
                if os.path.exists(rep_zip_path):
                    return rep_zip_path

        return sim_zip_path
