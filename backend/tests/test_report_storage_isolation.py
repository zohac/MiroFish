"""Tests unitaires et d'intégration hermétiques pour l'isolation multi-rapports sous reports/<report_id>/ et l'API d'historique (Story 013-3, FR-05, FR-06, C4).

Valide :
  - AC1 : Isolation stricte de 100% des artefacts sous reports/<report_id>/ (report_claims.json, cohort_coverage.json,
          quality_checks.json, run_manifest.json, ZIP d'audit). Deux rapports successifs sur une même simulation ne s'écrasent pas.
  - AC2 : Index d'historique atomique report_history.json et pointeur latest_report_id mis à jour sans corruption.
  - AC3 : Résolution déterministe dans ReportManager (get_report_by_simulation renvoie le dernier rapport actif, list_reports_by_simulation).
  - AC4 : Endpoints REST API d'historique (/simulation/<sim_id>/history) et consultation per-report (/<report_id>/claims, /<report_id>/cohort).
  - AC5 : Téléchargement d'audit autonome per-report (/api/report/<report_id>/audit/download).
  - AC6 : Rétrocompatibilité ascendante avec simulations existantes sans historique.
"""

import json
import os
import zipfile
import pytest

from app import create_app
from app.config import Config
from app.models.source_document import InformationOrigin
from app.models.report_claim import (
    ClaimKind,
    ReportClaim,
    ReportClaimRegistry,
    VerificationStatus,
)
from app.models.cohort_coverage import (
    CohortCoverageTable,
    CohortMemberStatus,
    DecisionStatus,
    ScenarioRole,
)
from app.models.report_quality import (
    PublicationStatus,
    QualityGateResult,
    QualityStatus,
)
from app.services.report_agent import Report, ReportManager, ReportOutline, ReportSection, ReportStatus
from app.services.simulation_audit_service import SimulationAuditService


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setattr(Config, "UPLOAD_FOLDER", str(tmp_path))
    application = create_app()
    application.config["TESTING"] = True
    return application


@pytest.fixture
def client(app):
    return app.test_client()


def _create_mock_report(report_id: str, simulation_id: str, status: ReportStatus = ReportStatus.COMPLETED, created_at: str = "2026-10-19T10:00:00Z", completed_at: str = "2026-10-19T10:10:00Z") -> Report:
    """Helper de création de rapport mock."""
    return Report(
        report_id=report_id,
        simulation_id=simulation_id,
        graph_id="graph_test",
        simulation_requirement="Test requirement",
        status=status,
        created_at=created_at,
        completed_at=completed_at,
        outline=ReportOutline(
            title=f"Report {report_id}",
            summary="Summary",
            sections=[ReportSection(title="Section 1", content="Content 1")],
        ),
        markdown_content=f"# Report {report_id}\n\nContent for {report_id}\n",
        profile_id="flash-medium",
        replay_mode="replay_frozen",
    )


class TestReportStorageIsolation:
    """Tests unitaires hermétiques pour l'isolation du stockage multi-rapports."""

    def test_per_report_paths_structure(self, tmp_path, monkeypatch):
        """Vérifie la cohérence des chemins canoniques par rapport."""
        monkeypatch.setattr(Config, "UPLOAD_FOLDER", str(tmp_path))
        rep_id = "report_test123"

        assert ReportManager._get_report_claims_path(rep_id) == str(tmp_path / "reports" / rep_id / "report_claims.json")
        assert ReportManager._get_cohort_coverage_path(rep_id) == str(tmp_path / "reports" / rep_id / "cohort_coverage.json")
        assert ReportManager._get_run_manifest_path(rep_id) == str(tmp_path / "reports" / rep_id / "run_manifest.json")
        assert ReportManager._get_audit_package_path(rep_id) == str(tmp_path / "reports" / rep_id / f"simulation_audit_{rep_id}.zip")

    def test_multi_report_isolation_no_destructive_overwrite(self, tmp_path, monkeypatch):
        """AC1: Deux générations successives sur le même simulation_id préservent leurs artefacts disjoints sans écrasement."""
        monkeypatch.setattr(Config, "UPLOAD_FOLDER", str(tmp_path))
        sim_id = "sim_multi_test"
        rep1_id = "report_run_01"
        rep2_id = "report_run_02"

        # 1. Premier rapport run_01
        rep1 = _create_mock_report(rep1_id, sim_id, created_at="2026-10-19T10:00:00Z")
        ReportManager.save_report(rep1)

        # Créer les artefacts isolés pour rep1
        claims1 = ReportClaimRegistry(simulation_id=sim_id)
        claims1.add_claim(ReportClaim(
            claim_id="claim_01",
            text="Claim 1 from run 1",
            claim_kind=ClaimKind.SOURCE_FACT,
            origin=InformationOrigin.DOCUMENTARY,
            verification_status=VerificationStatus.VERIFIED,
        ))
        claims1.save_to_file(ReportManager._get_report_claims_path(rep1_id))

        cohort1 = CohortCoverageTable(
            simulation_id=sim_id,
            members=[
                CohortMemberStatus(persona_name=f"User_{i}", action_count=1, observed_event_ids=[f"ev_{i}"])
                for i in range(4)
            ] + [
                CohortMemberStatus(persona_name="Silent_User", action_count=0, observed_event_ids=[])
            ]
        )
        cohort1.save_to_file(ReportManager._get_cohort_coverage_path(rep1_id))

        audit_svc1 = SimulationAuditService(simulation_id=sim_id, report_id=rep1_id)
        audit_svc1.build_audit_package()

        # Enregistrer rep1 dans l'historique
        ReportManager._append_to_history(sim_id, {
            "report_id": rep1_id,
            "simulation_id": sim_id,
            "created_at": "2026-10-19T10:00:00Z",
            "completed_at": "2026-10-19T10:10:00Z",
            "status": "completed",
            "profile_id": "flash-medium",
            "total_claims": 1,
            "supported_claims": 1,
        })

        # 2. Deuxième rapport run_02 sur la MÊME simulation
        rep2 = _create_mock_report(rep2_id, sim_id, created_at="2026-10-19T11:00:00Z")
        ReportManager.save_report(rep2)

        claims2 = ReportClaimRegistry(simulation_id=sim_id)
        claims2.add_claim(ReportClaim(
            claim_id="claim_02",
            text="Claim 2 from run 2 with high effort",
            claim_kind=ClaimKind.OBSERVED_SOCIAL_ACTION,
            origin=InformationOrigin.SIMULATION,
            verification_status=VerificationStatus.VERIFIED,
        ))
        claims2.save_to_file(ReportManager._get_report_claims_path(rep2_id))

        cohort2 = CohortCoverageTable(
            simulation_id=sim_id,
            members=[
                CohortMemberStatus(persona_name=f"User_{i}", action_count=2, observed_event_ids=[f"ev_{i}_1", f"ev_{i}_2"])
                for i in range(5)
            ]
        )
        cohort2.save_to_file(ReportManager._get_cohort_coverage_path(rep2_id))

        audit_svc2 = SimulationAuditService(simulation_id=sim_id, report_id=rep2_id)
        audit_svc2.build_audit_package()

        ReportManager._append_to_history(sim_id, {
            "report_id": rep2_id,
            "simulation_id": sim_id,
            "created_at": "2026-10-19T11:00:00Z",
            "completed_at": "2026-10-19T11:12:00Z",
            "status": "completed",
            "profile_id": "flash-high",
            "total_claims": 1,
            "supported_claims": 1,
        })

        # VÉRIFICATIONS AC1 :
        # rep1 est intact et n'a pas été écrasé par rep2
        assert os.path.exists(ReportManager._get_report_claims_path(rep1_id))
        assert os.path.exists(ReportManager._get_report_claims_path(rep2_id))
        loaded_claims1 = ReportClaimRegistry.load_from_file(ReportManager._get_report_claims_path(rep1_id))
        loaded_claims2 = ReportClaimRegistry.load_from_file(ReportManager._get_report_claims_path(rep2_id))
        assert loaded_claims1.claims[0].claim_id == "claim_01"
        assert loaded_claims2.claims[0].claim_id == "claim_02"

        # cohort_coverage.json disjoints
        assert os.path.exists(ReportManager._get_cohort_coverage_path(rep1_id))
        assert os.path.exists(ReportManager._get_cohort_coverage_path(rep2_id))
        loaded_cohort1 = CohortCoverageTable.load_from_file(ReportManager._get_cohort_coverage_path(rep1_id))
        loaded_cohort2 = CohortCoverageTable.load_from_file(ReportManager._get_cohort_coverage_path(rep2_id))
        assert loaded_cohort1.silent_members == 1
        assert loaded_cohort2.silent_members == 0

        # run_manifest.json et simulation_audit_<rep_id>.zip disjoints
        assert os.path.exists(ReportManager._get_run_manifest_path(rep1_id))
        assert os.path.exists(ReportManager._get_run_manifest_path(rep2_id))
        assert os.path.exists(ReportManager._get_audit_package_path(rep1_id))
        assert os.path.exists(ReportManager._get_audit_package_path(rep2_id))

        # Vérifier que les contenus des deux ZIP contiennent leurs run_manifest respectifs
        with zipfile.ZipFile(ReportManager._get_audit_package_path(rep1_id), "r") as z1:
            man1 = json.loads(z1.read("run_manifest.json").decode("utf-8"))
            assert man1["report_id"] == rep1_id

        with zipfile.ZipFile(ReportManager._get_audit_package_path(rep2_id), "r") as z2:
            man2 = json.loads(z2.read("run_manifest.json").decode("utf-8"))
            assert man2["report_id"] == rep2_id

    def test_report_history_atomic_index(self, tmp_path, monkeypatch):
        """AC2: Index d'historique report_history.json et latest_report_id atomiques."""
        monkeypatch.setattr(Config, "UPLOAD_FOLDER", str(tmp_path))
        sim_id = "sim_hist_test"

        # Ajout 1er rapport
        entry1 = {
            "report_id": "rep_1",
            "simulation_id": sim_id,
            "created_at": "2026-10-19T09:00:00Z",
            "status": "completed",
            "profile_id": "flash-medium",
        }
        ReportManager._append_to_history(sim_id, entry1)

        hist = ReportManager._load_history(sim_id)
        assert hist["simulation_id"] == sim_id
        assert hist["latest_report_id"] == "rep_1"
        assert len(hist["reports"]) == 1

        with open(ReportManager._get_latest_report_id_path(sim_id), "r") as lf:
            assert lf.read().strip() == "rep_1"

        # Ajout 2e rapport
        entry2 = {
            "report_id": "rep_2",
            "simulation_id": sim_id,
            "created_at": "2026-10-19T10:00:00Z",
            "status": "completed",
            "profile_id": "flash-high",
        }
        ReportManager._append_to_history(sim_id, entry2)

        hist2 = ReportManager._load_history(sim_id)
        assert hist2["latest_report_id"] == "rep_2"
        assert len(hist2["reports"]) == 2
        assert [r["report_id"] for r in hist2["reports"]] == ["rep_1", "rep_2"]

        with open(ReportManager._get_latest_report_id_path(sim_id), "r") as lf:
            assert lf.read().strip() == "rep_2"

        # Idempotence: mise à jour de rep_2
        entry2_updated = dict(entry2)
        entry2_updated["status"] = "verified_publishable"
        ReportManager._append_to_history(sim_id, entry2_updated)

        hist3 = ReportManager._load_history(sim_id)
        assert len(hist3["reports"]) == 2
        assert hist3["reports"][1]["status"] == "verified_publishable"

    def test_deterministic_resolution_in_report_manager(self, tmp_path, monkeypatch):
        """AC3: get_report_by_simulation résout de façon déterministe le dernier rapport sans dépendre de l'ordre os.listdir."""
        monkeypatch.setattr(Config, "UPLOAD_FOLDER", str(tmp_path))
        sim_id = "sim_determ_test"

        # Créer rep_A (ancien) et rep_B (récent)
        rep_a = _create_mock_report("report_A", sim_id, created_at="2026-10-19T08:00:00Z", completed_at="2026-10-19T08:10:00Z")
        rep_b = _create_mock_report("report_B", sim_id, created_at="2026-10-19T12:00:00Z", completed_at="2026-10-19T12:10:00Z")
        ReportManager.save_report(rep_a)
        ReportManager.save_report(rep_b)

        # Configurer l'historique avec latest_report_id pointant sur report_B
        ReportManager._append_to_history(sim_id, {
            "report_id": "report_A",
            "created_at": "2026-10-19T08:00:00Z",
            "completed_at": "2026-10-19T08:10:00Z",
            "status": "completed",
        })
        ReportManager._append_to_history(sim_id, {
            "report_id": "report_B",
            "created_at": "2026-10-19T12:00:00Z",
            "completed_at": "2026-10-19T12:10:00Z",
            "status": "completed",
        })

        # Résolution
        active = ReportManager.get_report_by_simulation(sim_id)
        assert active is not None
        assert active.report_id == "report_B"

        # list_reports_by_simulation
        full_hist = ReportManager.list_reports_by_simulation(sim_id)
        assert len(full_hist) == 2
        assert full_hist[0]["report_id"] == "report_A"
        assert full_hist[1]["report_id"] == "report_B"

    def test_retrocompatibility_without_history(self, tmp_path, monkeypatch):
        """AC6: Les simulations existantes sans report_history.json continuent de fonctionner."""
        monkeypatch.setattr(Config, "UPLOAD_FOLDER", str(tmp_path))
        sim_id = "sim_legacy"
        rep_legacy = _create_mock_report("report_legacy", sim_id, created_at="2026-10-15T10:00:00Z")
        ReportManager.save_report(rep_legacy)

        # Aucun report_history.json ni latest_report_id n'a été créé
        assert not os.path.exists(ReportManager._get_history_path(sim_id))
        assert not os.path.exists(ReportManager._get_latest_report_id_path(sim_id))

        # get_report_by_simulation doit quand même retrouver report_legacy
        resolved = ReportManager.get_report_by_simulation(sim_id)
        assert resolved is not None
        assert resolved.report_id == "report_legacy"

        # list_reports_by_simulation doit inclure le rapport sur disque
        hist_list = ReportManager.list_reports_by_simulation(sim_id)
        assert len(hist_list) == 1
        assert hist_list[0]["report_id"] == "report_legacy"

    def test_history_update_older_report_preserves_latest_report_id(self, tmp_path, monkeypatch):
        """Vérifie que la mise à jour d'un ancien rapport ne corrompt pas latest_report_id (Patch 2)."""
        monkeypatch.setattr(Config, "UPLOAD_FOLDER", str(tmp_path))
        sim_id = "sim_hist_order"

        ReportManager._append_to_history(sim_id, {
            "report_id": "rep_1",
            "created_at": "2026-10-19T09:00:00Z",
            "status": "in_progress",
        })
        ReportManager._append_to_history(sim_id, {
            "report_id": "rep_2",
            "created_at": "2026-10-19T10:00:00Z",
            "status": "completed",
        })

        hist = ReportManager._load_history(sim_id)
        assert hist["latest_report_id"] == "rep_2"

        # Mise à jour rétroactive de rep_1
        ReportManager._append_to_history(sim_id, {
            "report_id": "rep_1",
            "created_at": "2026-10-19T09:00:00Z",
            "status": "failed_validation",
        })

        hist_after = ReportManager._load_history(sim_id)
        assert hist_after["latest_report_id"] == "rep_2"
        with open(ReportManager._get_latest_report_id_path(sim_id), "r") as lf:
            assert lf.read().strip() == "rep_2"
        assert hist_after["reports"][0]["report_id"] == "rep_1"
        assert hist_after["reports"][0]["status"] == "failed_validation"
        assert hist_after["reports"][1]["report_id"] == "rep_2"

    def test_audit_package_rebuilds_per_report_when_simulation_zip_exists(self, tmp_path, monkeypatch):
        """Vérifie que SimulationAuditService construit l'archive per-report sans replier sur un ZIP simulation pré-existant (Patch 4)."""
        monkeypatch.setattr(Config, "UPLOAD_FOLDER", str(tmp_path))
        sim_id = "sim_audit_isolation"
        rep_id = "rep_audit_01"

        sim_dir = tmp_path / "simulations" / sim_id
        sim_dir.mkdir(parents=True, exist_ok=True)

        # Créer un faux ZIP legacy au niveau simulation
        legacy_zip = sim_dir / f"simulation_audit_{sim_id}.zip"
        with zipfile.ZipFile(legacy_zip, "w") as zf:
            zf.writestr("legacy.txt", "legacy simulation data")

        svc = SimulationAuditService(simulation_id=sim_id, report_id=rep_id)
        pkg_path = svc.get_audit_package_path()
        assert pkg_path is not None
        assert str(rep_id) in pkg_path
        assert pkg_path == ReportManager._get_audit_package_path(rep_id)
        assert os.path.exists(pkg_path)

        with zipfile.ZipFile(pkg_path, "r") as zf:
            assert "run_manifest.json" in zf.namelist()
            assert "legacy.txt" not in zf.namelist()


class TestReportStorageIsolationAPI:
    """Tests d'intégration Flask API pour l'historique et la consultation per-report."""

    def test_api_simulation_history_endpoint(self, client, monkeypatch, tmp_path):
        """AC4: GET /api/report/simulation/<sim_id>/history renvoie la liste ordonnée."""
        monkeypatch.setattr(Config, "UPLOAD_FOLDER", str(tmp_path))
        sim_id = "sim_api_hist"
        sim_dir = tmp_path / "simulations" / sim_id
        sim_dir.mkdir(parents=True, exist_ok=True)

        # Initialiser 2 rapports avec historique
        rep1 = _create_mock_report("rep_1", sim_id, created_at="2026-10-19T10:00:00Z")
        rep2 = _create_mock_report("rep_2", sim_id, created_at="2026-10-19T11:00:00Z")
        ReportManager.save_report(rep1)
        ReportManager.save_report(rep2)

        ReportManager._append_to_history(sim_id, {
            "report_id": "rep_1",
            "created_at": "2026-10-19T10:00:00Z",
            "status": "completed",
            "profile_id": "flash-medium",
            "is_publishable": True,
            "total_claims": 10,
        })
        ReportManager._append_to_history(sim_id, {
            "report_id": "rep_2",
            "created_at": "2026-10-19T11:00:00Z",
            "status": "completed",
            "profile_id": "flash-high",
            "is_publishable": True,
            "total_claims": 12,
        })

        res = client.get(f"/api/report/simulation/{sim_id}/history")
        assert res.status_code == 200
        data = res.get_json()
        assert data["success"] is True
        assert data["data"]["simulation_id"] == sim_id
        assert data["data"]["latest_report_id"] == "rep_2"
        assert data["data"]["count"] == 2
        assert len(data["data"]["reports"]) == 2
        assert data["data"]["reports"][0]["report_id"] == "rep_1"
        assert data["data"]["reports"][1]["report_id"] == "rep_2"

    def test_api_report_claims_per_report(self, client, monkeypatch, tmp_path):
        """AC4: GET /api/report/<report_id>/claims renvoie les claims spécifiques au rapport."""
        monkeypatch.setattr(Config, "UPLOAD_FOLDER", str(tmp_path))
        sim_id = "sim_api_claims"
        rep_id = "rep_target_claims"

        rep = _create_mock_report(rep_id, sim_id)
        ReportManager.save_report(rep)

        claims = ReportClaimRegistry(simulation_id=sim_id)
        claims.add_claim(ReportClaim(
            claim_id="claim_xyz",
            text="Exemple d'assertion",
            claim_kind=ClaimKind.SOURCE_FACT,
            origin=InformationOrigin.DOCUMENTARY,
            verification_status=VerificationStatus.VERIFIED,
        ))
        claims.save_to_file(ReportManager._get_report_claims_path(rep_id))

        res = client.get(f"/api/report/{rep_id}/claims")
        assert res.status_code == 200
        payload = res.get_json()
        assert payload["success"] is True
        assert payload["data"]["total_claims"] == 1
        assert payload["data"]["claims"][0]["claim_id"] == "claim_xyz"

        # 404 sur rapport inexistant
        res_404 = client.get("/api/report/rep_inexistant/claims")
        assert res_404.status_code == 404

    def test_api_report_cohort_per_report(self, client, monkeypatch, tmp_path):
        """AC4: GET /api/report/<report_id>/cohort renvoie le tableau de cohorte spécifique."""
        monkeypatch.setattr(Config, "UPLOAD_FOLDER", str(tmp_path))
        sim_id = "sim_api_cohort"
        rep_id = "rep_target_cohort"

        rep = _create_mock_report(rep_id, sim_id)
        ReportManager.save_report(rep)

        cohort = CohortCoverageTable(
            simulation_id=sim_id,
            members=[
                CohortMemberStatus(persona_name="A1", action_count=1, observed_event_ids=["e1"]),
                CohortMemberStatus(persona_name="A2", action_count=1, observed_event_ids=["e2"]),
                CohortMemberStatus(persona_name="A3", action_count=0, observed_event_ids=[]),
            ]
        )
        cohort.save_to_file(ReportManager._get_cohort_coverage_path(rep_id))

        res = client.get(f"/api/report/{rep_id}/cohort")
        assert res.status_code == 200
        payload = res.get_json()
        assert payload["success"] is True
        assert payload["data"]["total_members"] == 3
        assert payload["data"]["silent_members"] == 1

        # 404 sur rapport inexistant
        res_404 = client.get("/api/report/rep_inexistant/cohort")
        assert res_404.status_code == 404

    def test_api_audit_download_per_report(self, client, monkeypatch, tmp_path):
        """AC5: GET /api/report/<report_id>/audit/download sert l'archive ZIP per-report sans collision."""
        monkeypatch.setattr(Config, "UPLOAD_FOLDER", str(tmp_path))
        sim_id = "sim_api_audit_pkg"
        rep_id = "rep_pkg_01"

        rep = _create_mock_report(rep_id, sim_id)
        ReportManager.save_report(rep)

        # Préparer et générer le zip d'audit pour rep_pkg_01
        audit_svc = SimulationAuditService(simulation_id=sim_id, report_id=rep_id)
        audit_svc.build_audit_package()

        res = client.get(f"/api/report/{rep_id}/audit/download")
        assert res.status_code == 200
        assert res.mimetype == "application/zip"
        # Le contenu téléchargé est bien un ZIP valide avec run_manifest.json associé à rep_pkg_01
        import io
        buf = io.BytesIO(res.data)
        with zipfile.ZipFile(buf, "r") as zf:
            names = zf.namelist()
            assert "run_manifest.json" in names
            manifest = json.loads(zf.read("run_manifest.json").decode("utf-8"))
            assert manifest["report_id"] == rep_id

    def test_api_claims_fallback_isolation_multi_report(self, client, monkeypatch, tmp_path):
        """Vérifie que le fallback sur simulations/<sim_id>/ ne fuite pas vers un ancien rapport dans une simulation multi-rapports (Patch 3)."""
        monkeypatch.setattr(Config, "UPLOAD_FOLDER", str(tmp_path))
        sim_id = "sim_multi_fallback_guard"
        sim_dir = tmp_path / "simulations" / sim_id
        sim_dir.mkdir(parents=True, exist_ok=True)

        # Créer les rapports mock rep_1 et rep_2
        rep1 = _create_mock_report("rep_1", sim_id, created_at="2026-10-19T09:00:00Z")
        rep2 = _create_mock_report("rep_2", sim_id, created_at="2026-10-19T10:00:00Z")
        ReportManager.save_report(rep1)
        ReportManager.save_report(rep2)

        ReportManager._append_to_history(sim_id, {
            "report_id": "rep_1",
            "created_at": "2026-10-19T09:00:00Z",
            "status": "completed",
        })
        ReportManager._append_to_history(sim_id, {
            "report_id": "rep_2",
            "created_at": "2026-10-19T10:00:00Z",
            "status": "completed",
        })

        # Créer un fichier de claims au niveau simulation (émulant par ex. un résidu du dernier run rep_2)
        sim_claims_path = sim_dir / "report_claims.json"
        claims = ReportClaimRegistry(simulation_id=sim_id)
        claims.add_claim(ReportClaim(
            claim_id="claim_latest_run",
            text="Claim from run 2",
            claim_kind=ClaimKind.SOURCE_FACT,
            origin=InformationOrigin.DOCUMENTARY,
            verification_status=VerificationStatus.VERIFIED,
        ))
        claims.save_to_file(str(sim_claims_path))

        # rep_1 n'a pas de report_claims.json sous reports/rep_1/
        # En multi-rapports, GET /api/report/rep_1/claims NE DOIT PAS renvoyer le fichier simulation de rep_2
        res1 = client.get("/api/report/rep_1/claims")
        assert res1.status_code == 404

        # De même pour la cohorte
        res1_cohort = client.get("/api/report/rep_1/cohort")
        assert res1_cohort.status_code == 404
