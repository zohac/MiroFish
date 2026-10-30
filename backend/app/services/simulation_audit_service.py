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
import uuid
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
        # Priorité aux variables d'environnement explicites (CI/CD, conteneurs Docker sans montage .git)
        # NFR-5 / AT-15 : ignorer les valeurs vides ou égales à la sentinelle par défaut "unknown-git-commit"
        for env_var in ("GIT_COMMIT", "COMMIT_SHA", "GITHUB_SHA"):
            val = os.environ.get(env_var, "").strip()
            if val and val.lower() not in ("unknown-git-commit", "unknown"):
                return val

        # Vérification d'un fichier GIT_COMMIT cuit à la construction Docker
        for c_file in ("/app/backend/GIT_COMMIT", "/app/GIT_COMMIT", "backend/GIT_COMMIT", "GIT_COMMIT"):
            if os.path.exists(c_file):
                try:
                    with open(c_file, "r", encoding="utf-8") as f_gc:
                        c_val = f_gc.read().strip()
                        if c_val and c_val.lower() not in ("unknown-git-commit", "unknown"):
                            return c_val
                except Exception:
                    pass

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

    def _resolve_time_horizon_metadata(self) -> Dict[str, Any]:
        """Résout de manière déterministe l'horizon temporel en cascade avec traçabilité (Story 015-6, D5, C7, AT-16)."""
        sim_dir = os.path.join(Config.UPLOAD_FOLDER, "simulations", self.simulation_id)
        report_dir = os.path.join(Config.UPLOAD_FOLDER, "reports", self.report_id) if self.report_id else ""

        # 1. simulation_brief.json dans le dossier de la simulation
        brief_path = os.path.join(sim_dir, "simulation_brief.json")
        if os.path.exists(brief_path):
            try:
                with open(brief_path, "r", encoding="utf-8") as bf:
                    b_data = json.load(bf)
                    th = b_data.get("time_horizon")
                    if th and str(th).strip().lower() not in ("unknown", "inconnu", "none", "null", ""):
                        is_inf = bool(b_data.get("time_horizon_is_inferred", False))
                        src = b_data.get("time_horizon_source") or ("inferred_brief" if is_inf else "explicit_brief")
                        return {
                            "time_horizon": str(th).strip(),
                            "time_horizon_is_inferred": is_inf,
                            "time_horizon_source": src,
                        }
                    if b_data.get("goal"):
                        from ..models.simulation_brief import extract_inferred_horizon
                        inferred = extract_inferred_horizon(b_data["goal"], "")
                        if inferred.time_horizon and inferred.time_horizon.lower() != "unknown":
                            return {
                                "time_horizon": inferred.time_horizon,
                                "time_horizon_is_inferred": True,
                                "time_horizon_source": "inferred_from_goal",
                            }
            except Exception as e:
                logger.debug(f"Erreur lecture simulation_brief.json pour time_horizon: {e}")

        # 2. Brief du projet associé via ProjectManager
        try:
            sim_manager = SimulationManager()
            sim_state = sim_manager.get_simulation(self.simulation_id)
            project_id = getattr(sim_state, "project_id", "") if sim_state else ""
            if project_id:
                proj = ProjectManager().get_project(project_id)
                if proj and getattr(proj, "simulation_brief", None):
                    p_brief = proj.simulation_brief
                    th = p_brief.get("time_horizon") if isinstance(p_brief, dict) else getattr(p_brief, "time_horizon", None)
                    if th and str(th).strip().lower() not in ("unknown", "inconnu", "none", "null", ""):
                        return {
                            "time_horizon": str(th).strip(),
                            "time_horizon_is_inferred": False,
                            "time_horizon_source": "explicit_brief",
                        }
                    goal = p_brief.get("goal") if isinstance(p_brief, dict) else getattr(p_brief, "goal", "")
                    if goal:
                        from ..models.simulation_brief import extract_inferred_horizon
                        inferred = extract_inferred_horizon(goal, "")
                        if inferred.time_horizon and inferred.time_horizon.lower() != "unknown":
                            return {
                                "time_horizon": inferred.time_horizon,
                                "time_horizon_is_inferred": True,
                                "time_horizon_source": "inferred_from_goal",
                            }
        except Exception as e:
            logger.debug(f"Erreur résolution brief projet pour time_horizon: {e}")

        # 3. simulation_requirement ou config_reasoning lu depuis state.json ou simulation_config.json
        for filename in ("state.json", "simulation_config.json"):
            file_p = os.path.join(sim_dir, filename)
            if os.path.exists(file_p):
                try:
                    with open(file_p, "r", encoding="utf-8") as f:
                        cfg_data = json.load(f)
                        req_text = (
                            cfg_data.get("simulation_requirement")
                            or cfg_data.get("config_reasoning")
                            or cfg_data.get("goal")
                            or ""
                        )
                        if req_text:
                            from ..models.simulation_brief import extract_inferred_horizon
                            inferred = extract_inferred_horizon(req_text, "")
                            if inferred.time_horizon and inferred.time_horizon.lower() != "unknown":
                                return {
                                    "time_horizon": inferred.time_horizon,
                                    "time_horizon_is_inferred": True,
                                    "time_horizon_source": "inferred_from_simulation_requirement",
                                }
                except Exception as e:
                    logger.debug(f"Erreur lecture {filename} pour time_horizon: {e}")

        # 4. Titre / début de full_report.md ou outline.json
        if report_dir and os.path.exists(report_dir):
            for candidate_file in ("full_report.md", "outline.json"):
                rep_file_p = os.path.join(report_dir, candidate_file)
                if os.path.exists(rep_file_p):
                    try:
                        with open(rep_file_p, "r", encoding="utf-8") as rf:
                            head_text = ""
                            if candidate_file.endswith(".json"):
                                try:
                                    out_data = json.load(rf)
                                    head_text = str(out_data.get("title") or "")
                                    for s in out_data.get("sections", []):
                                        head_text += " " + str(s.get("title") or "")
                                except Exception:
                                    rf.seek(0)
                                    head_text = rf.read(1500)
                            else:
                                head_text = rf.read(1500)
                            from ..models.simulation_brief import extract_inferred_horizon
                            inferred = extract_inferred_horizon(head_text, "")
                            if inferred.time_horizon and inferred.time_horizon.lower() != "unknown":
                                return {
                                    "time_horizon": inferred.time_horizon,
                                    "time_horizon_is_inferred": True,
                                    "time_horizon_source": "inferred_from_report",
                                }
                    except Exception as e:
                        logger.debug(f"Erreur lecture {candidate_file} pour time_horizon: {e}")

        # 5. Non résolu
        return {
            "time_horizon": None,
            "time_horizon_is_inferred": False,
            "time_horizon_source": "unresolved",
        }

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

        # Récupération de time_horizon et traçabilité d'inférence en cascade (Story 015-6, D5, C7, AT-16)
        horizon_meta = self._resolve_time_horizon_metadata()
        time_horizon = horizon_meta.get("time_horizon")
        time_horizon_is_inferred = bool(horizon_meta.get("time_horizon_is_inferred", False))
        time_horizon_source = str(horizon_meta.get("time_horizon_source", "unresolved"))

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

        # Index d'attribution des affirmations (Story 014-2, AC7 / FR-09, C7)
        claims_index = None
        try:
            sim_dir = os.path.join(Config.UPLOAD_FOLDER, "simulations", self.simulation_id)
            rep_dir = os.path.join(Config.UPLOAD_FOLDER, "reports", self.report_id) if self.report_id else ""
            claims_path = ""
            if rep_dir and os.path.exists(os.path.join(rep_dir, "report_claims.json")):
                claims_path = os.path.join(rep_dir, "report_claims.json")
            elif os.path.exists(os.path.join(sim_dir, "report_claims.json")):
                claims_path = os.path.join(sim_dir, "report_claims.json")
            if claims_path and os.path.exists(claims_path):
                h = hashlib.sha256()
                with open(claims_path, "rb") as cf:
                    for chunk in iter(lambda: cf.read(8192), b""):
                        h.update(chunk)
                claims_index = {
                    "path": claims_path,
                    "sha256": h.hexdigest(),
                }
        except Exception as ci_err:
            logger.warning(f"Index d'attribution des claims indisponible : {ci_err}")
            claims_index = None

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
                "time_horizon_is_inferred": time_horizon_is_inferred,
                "time_horizon_source": time_horizon_source,
                "agent_count": agent_count,
            },
        }

        manifest["claims_index"] = claims_index
        manifest["report_claims_path"] = (claims_index or {}).get("path")
        manifest["report_claims_sha256"] = (claims_index or {}).get("sha256")
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
        time_horizon = run_manifest.get("simulation", {}).get("time_horizon")
        time_horizon_is_inferred = bool(run_manifest.get("simulation", {}).get("time_horizon_is_inferred", False))
        time_horizon_source = str(run_manifest.get("simulation", {}).get("time_horizon_source", "unresolved"))

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

        # 2. simulation_brief.json (enrichi de l'horizon inféré si présent, AT-16)
        brief_dict: Dict[str, Any] = {}
        brief_path = os.path.join(sim_dir, "simulation_brief.json")
        if os.path.exists(brief_path):
            try:
                with open(brief_path, "r", encoding="utf-8") as f_bf:
                    brief_dict = json.load(f_bf)
            except Exception:
                brief_dict = {}
        else:
            # Essayer de lire depuis project
            sim_manager = SimulationManager()
            sim_state = sim_manager.get_simulation(self.simulation_id)
            project_id = getattr(sim_state, "project_id", "") if sim_state else ""
            if project_id:
                proj = ProjectManager().get_project(project_id)
                if proj and proj.simulation_brief:
                    brief_dict = (
                        proj.simulation_brief.to_dict()
                        if hasattr(proj.simulation_brief, "to_dict")
                        else dict(proj.simulation_brief)
                    )

        # Si un horizon a été inféré ou résolu par le run_manifest, synchroniser le brief (AT-16)
        if time_horizon and (
            not brief_dict.get("time_horizon")
            or str(brief_dict.get("time_horizon")).strip().lower() in ("unknown", "inconnu", "none", "null", "")
        ):
            brief_dict["time_horizon"] = time_horizon
            brief_dict["time_horizon_is_inferred"] = time_horizon_is_inferred
            brief_dict["time_horizon_source"] = time_horizon_source

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

        # 7 bis. report_interviews.json (entretiens de rédaction, Story 014-1 ; Story 015-2 v2) —
        # hors du paquet figé, mais présent dans le dossier du rapport et dans checksums.sha256.
        interviews_path = ""
        if rep_dir:
            interviews_path = os.path.join(rep_dir, "report_interviews.json")
        if interviews_path and os.path.exists(interviews_path):
            with open(interviews_path, "rb") as f:
                files["report_interviews.json"] = f.read()
        else:
            files["report_interviews.json"] = json.dumps(
                {
                    "schema_version": "2.0",
                    "simulation_id": self.simulation_id,
                    "report_id": self.report_id or "",
                    "sessions": [],
                },
                indent=2,
            ).encode("utf-8")

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

        # Index d'attribution des affirmations (Story 014-2, AC7) : copie dédiée
        try:
            files["claims_index.json"] = json.dumps(
                run_manifest.get("claims_index"), ensure_ascii=False, indent=2
            ).encode("utf-8")
        except Exception:
            files["claims_index.json"] = json.dumps(None, ensure_ascii=False, indent=2).encode("utf-8")

        # 9 bis. brief_consistency.json (Story 014-4, FR-07, AC6 ; Story 015-6, D6, AC4)
        rep_bc_path = os.path.join(rep_dir, "brief_consistency.json") if rep_dir else ""
        sim_bc_path = os.path.join(sim_dir, "brief_consistency.json")
        bc_bytes: Optional[bytes] = None

        if rep_bc_path and os.path.exists(rep_bc_path):
            with open(rep_bc_path, "rb") as f_rbc:
                bc_bytes = f_rbc.read()
        elif os.path.exists(sim_bc_path):
            with open(sim_bc_path, "rb") as f_sbc:
                bc_bytes = f_sbc.read()

        bc_dict: Dict[str, Any] = {}
        if bc_bytes:
            try:
                bc_dict = json.loads(bc_bytes.decode("utf-8"))
            except Exception:
                bc_dict = {"is_consistent": True, "contradictions": [], "diagnostics": {}}
        else:
            bc_dict = {"is_consistent": True, "contradictions": [], "diagnostics": {"note": "non_audit_ou_historique"}}

        # Si le rapport contient de la prose et que prose_is_consistent n'est pas encore présent, l'évaluer
        if "prose_is_consistent" not in bc_dict:
            try:
                from .brief_consistency import audit_prose_persona_consistency
                mgr = SimulationManager()
                profiles: List[Dict[str, Any]] = []
                seen_prof_names = set()
                for plat in ("reddit", "twitter"):
                    try:
                        p_list = mgr.get_profiles(self.simulation_id, platform=plat)
                        for p in (p_list or []):
                            p_name = p.get("name") or p.get("realname") or p.get("username")
                            if p_name and p_name not in seen_prof_names:
                                seen_prof_names.add(p_name)
                                profiles.append(p)
                    except Exception:
                        pass
                markdown_text = ""
                if "report.md" in files:
                    markdown_text = files["report.md"].decode("utf-8", errors="replace")
                if markdown_text and profiles:
                    prose_res = audit_prose_persona_consistency(
                        markdown_content=markdown_text,
                        profiles=profiles,
                    )
                    bc_dict["prose_is_consistent"] = prose_res.is_consistent
                    bc_dict["prose_contradictions"] = [c.to_dict() for c in prose_res.contradictions]
                    bc_dict["is_consistent"] = bool(bc_dict.get("is_consistent", True)) and prose_res.is_consistent
                    if "diagnostics" not in bc_dict:
                        bc_dict["diagnostics"] = {}
                    bc_dict["diagnostics"].update(prose_res.diagnostics)
                    # Synchroniser sur disque si rep_bc_path existe
                    if self.report_id:
                        rep_bc_p = os.path.join(Config.UPLOAD_FOLDER, "reports", self.report_id, "brief_consistency.json")
                        try:
                            os.makedirs(os.path.dirname(rep_bc_p), exist_ok=True)
                            tmp_p = f"{rep_bc_p}.tmp.{uuid.uuid4().hex[:8]}"
                            with open(tmp_p, "w", encoding="utf-8") as f_tmp:
                                json.dump(bc_dict, f_tmp, ensure_ascii=False, indent=2)
                            os.replace(tmp_p, rep_bc_p)
                        except Exception as _sync_err:
                            logger.debug(f"Erreur synchronisation disque brief_consistency.json: {_sync_err}")
            except Exception as _eval_err:
                logger.debug(f"Audit automatique prose brief_consistency dans gather_audit_files: {_eval_err}")

        files["brief_consistency.json"] = json.dumps(
            bc_dict,
            ensure_ascii=False,
            indent=2,
        ).encode("utf-8")

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
