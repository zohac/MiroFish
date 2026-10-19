"""Tests unitaires hermétiques pour EvidenceSnapshot et mode replay_frozen (Story 013-2, AC1-AC5).

Vérifie :
1. Immuabilité et roundtrip de la dataclass EvidenceSnapshot (AC1).
2. Déterminisme strict du calcul de hash SHA-256 et sensibilité aux altérations (AC2).
3. Rejet avec ReplayNotReproducibleError si une preuve obligatoire est absente en mode strict.
4. Intégration dans ReportAgent en mode replay_frozen :
   - Neutralisation des appels interactifs live vers OASIS (AC3).
   - Rattachement du snapshot de preuves au rapport (AC3).
   - Pas de clôture physique de l'environnement interactif OASIS en mode replay_frozen (AC3).
5. Rétrocompatibilité par défaut du mode "live" (AC4).
6. Exposition et validation dans l'endpoint POST /api/report/generate (AC5).
"""

import json
import os
from unittest.mock import MagicMock, patch

import pytest
from app.models.evidence_snapshot import EvidenceSnapshot
from app.services.evidence_snapshot_service import (
    EvidenceSnapshotService,
    ReplayNotReproducibleError,
)
from app.services.report_agent import ReportAgent, ReportManager, ReportStatus


class TestEvidenceSnapshotModel:
    """AC1: Dataclass EvidenceSnapshot immuable et sérialisable."""

    def test_evidence_snapshot_immutability(self):
        snapshot = EvidenceSnapshot(
            snapshot_id="snap_123",
            simulation_id="sim_abc",
            sha256_hash="abcdef0123456789",
            file_hashes={"observed_events.jsonl": "hash1"},
            total_events=10,
            total_actors=3,
            has_archived_interviews=True,
            created_at="2026-10-19T10:00:00",
        )
        with pytest.raises(Exception):
            snapshot.sha256_hash = "new_hash"  # type: ignore

    def test_evidence_snapshot_roundtrip_serialization(self):
        original = EvidenceSnapshot(
            snapshot_id="snap_123",
            simulation_id="sim_abc",
            sha256_hash="abcdef0123456789",
            file_hashes={"actors.json": "h1", "observed_events.jsonl": "h2"},
            total_events=42,
            total_actors=5,
            has_archived_interviews=False,
            created_at="2026-10-19T10:00:00",
        )
        d = original.to_dict()
        assert isinstance(d, dict)
        assert d["snapshot_id"] == "snap_123"
        assert d["total_events"] == 42
        assert d["total_actors"] == 5
        assert d["has_archived_interviews"] is False

        restored = EvidenceSnapshot.from_dict(d)
        assert restored == original
        assert restored.file_hashes == original.file_hashes

    def test_report_to_dict_serializes_evidence_snapshot_instance(self):
        from app.services.report_agent import Report, ReportStatus
        snapshot = EvidenceSnapshot(
            snapshot_id="snap_inst",
            simulation_id="sim_inst",
            sha256_hash="hash123",
            file_hashes={"actors.json": "h1"},
            total_events=5,
            total_actors=2,
            has_archived_interviews=False,
            created_at="2026-10-19T10:00:00",
        )
        report = Report(
            report_id="rep_inst",
            simulation_id="sim_inst",
            graph_id="g1",
            simulation_requirement="req",
            status=ReportStatus.COMPLETED,
            replay_mode="replay_frozen",
            evidence_snapshot=snapshot,  # passed as EvidenceSnapshot object
        )
        d = report.to_dict()
        assert isinstance(d["evidence_snapshot"], dict)
        assert d["evidence_snapshot"]["snapshot_id"] == "snap_inst"
        assert d["evidence_snapshot"]["sha256_hash"] == "hash123"


class TestEvidenceSnapshotService:
    """AC2: Calcul déterministe d'empreinte SHA-256 et sensibilité."""

    def test_compute_sha256_footprint_determinism(self):
        service = EvidenceSnapshotService(simulation_id="sim_test")
        files_a = {
            "actors.json": b'{"actors": [{"name": "A"}]}',
            "observed_events.jsonl": b'{"event_id": "1", "action": "post"}\n',
            "simulation_brief.json": b'{"brief": "test"}',
        }
        # Inverser l'ordre des clés dans le dict pour vérifier le tri canonique
        files_b = {
            "simulation_brief.json": b'{"brief": "test"}',
            "observed_events.jsonl": b'{"event_id": "1", "action": "post"}\n',
            "actors.json": b'{"actors": [{"name": "A"}]}',
        }

        hash_a, hashes_dict_a = service.compute_sha256_footprint(files_a)
        hash_b, hashes_dict_b = service.compute_sha256_footprint(files_b)

        assert hash_a == hash_b
        assert hashes_dict_a == hashes_dict_b
        assert len(hash_a) == 64

    def test_compute_sha256_footprint_sensitivity(self):
        service = EvidenceSnapshotService(simulation_id="sim_test")
        files_base = {
            "actors.json": b'{"actors": [{"name": "A"}]}',
            "observed_events.jsonl": b'{"event_id": "1", "action": "post"}\n',
            "simulation_brief.json": b'{"brief": "test"}',
        }
        files_altered = {
            "actors.json": b'{"actors": [{"name": "A"}]}',
            "observed_events.jsonl": b'{"event_id": "1", "action": "post"}\n\n',  # saut de ligne supplémentaire
            "simulation_brief.json": b'{"brief": "test"}',
        }

        hash_base, _ = service.compute_sha256_footprint(files_base)
        hash_alt, _ = service.compute_sha256_footprint(files_altered)
        assert hash_base != hash_alt

    def test_capture_snapshot_strict_failure_when_missing_proofs(self, tmp_path):
        sim_id = "sim_empty_proofs"
        sim_dir = tmp_path / "simulations" / sim_id
        sim_dir.mkdir(parents=True, exist_ok=True)

        with patch("app.services.evidence_snapshot_service.Config.UPLOAD_FOLDER", str(tmp_path)):
            with patch("app.services.evidence_snapshot_service.ProjectManager"):
                with patch("app.services.evidence_snapshot_service.SimulationManager"):
                    with patch("app.services.evidence_snapshot_service.OasisLogReaderService") as mock_reader_cls:
                        mock_reader_cls.return_value.load_events.return_value = []
                        service = EvidenceSnapshotService(simulation_id=sim_id)
                        with pytest.raises(ReplayNotReproducibleError) as exc_info:
                            service.capture_snapshot(strict=True)
                        assert "REPLAY_NOT_REPRODUCIBLE" in str(exc_info.value)

    def test_capture_snapshot_strict_failure_isolated_missing_actors(self, tmp_path):
        sim_id = "sim_missing_actors"
        sim_dir = tmp_path / "simulations" / sim_id
        sim_dir.mkdir(parents=True, exist_ok=True)

        # Événements et brief présents, mais pas d'acteurs
        (sim_dir / "observed_events.jsonl").write_text('{"event": 1}\n', encoding="utf-8")
        (sim_dir / "simulation_brief.json").write_text('{"brief": "valid"}', encoding="utf-8")

        with patch("app.services.evidence_snapshot_service.Config.UPLOAD_FOLDER", str(tmp_path)):
            service = EvidenceSnapshotService(simulation_id=sim_id)
            with pytest.raises(ReplayNotReproducibleError) as exc_info:
                service.capture_snapshot(strict=True)
            assert "actors.json (0 acteur)" in str(exc_info.value)

    def test_capture_snapshot_strict_failure_isolated_missing_brief(self, tmp_path):
        sim_id = "sim_missing_brief"
        sim_dir = tmp_path / "simulations" / sim_id
        sim_dir.mkdir(parents=True, exist_ok=True)

        # Événements et acteurs présents, mais pas de brief
        (sim_dir / "observed_events.jsonl").write_text('{"event": 1}\n', encoding="utf-8")
        (sim_dir / "actors.json").write_text('{"actors": [{"name": "A"}]}', encoding="utf-8")

        with patch("app.services.evidence_snapshot_service.Config.UPLOAD_FOLDER", str(tmp_path)):
            with patch("app.services.evidence_snapshot_service.ProjectManager") as mock_pm:
                mock_pm.return_value.get_project.return_value = None
                service = EvidenceSnapshotService(simulation_id=sim_id)
                with pytest.raises(ReplayNotReproducibleError) as exc_info:
                    service.capture_snapshot(strict=True)
                assert "simulation_brief.json (vide)" in str(exc_info.value)

    def test_capture_snapshot_success(self, tmp_path):
        sim_id = "sim_valid_proofs"
        sim_dir = tmp_path / "simulations" / sim_id
        sim_dir.mkdir(parents=True, exist_ok=True)

        # Créer les fichiers requis
        (sim_dir / "observed_events.jsonl").write_text('{"event": 1}\n{"event": 2}\n', encoding="utf-8")
        (sim_dir / "actors.json").write_text('{"actors": [{"name": "A"}, {"name": "B"}]}', encoding="utf-8")
        (sim_dir / "simulation_brief.json").write_text('{"brief": "valid"}', encoding="utf-8")

        with patch("app.services.evidence_snapshot_service.Config.UPLOAD_FOLDER", str(tmp_path)):
            service = EvidenceSnapshotService(simulation_id=sim_id)
            snapshot = service.capture_snapshot(strict=True)

            assert snapshot.simulation_id == sim_id
            assert snapshot.total_events == 2
            assert snapshot.total_actors == 2
            assert len(snapshot.sha256_hash) == 64
            assert "observed_events.jsonl" in snapshot.file_hashes
            assert "actors.json" in snapshot.file_hashes
            assert "simulation_brief.json" in snapshot.file_hashes

            # Vérification de cohérence via verify_snapshot
            assert service.verify_snapshot(snapshot) is True


class TestReportAgentReplayFrozen:
    """AC3 & AC4: Mode replay_frozen hermétique et rétrocompatibilité mode live."""

    def test_report_agent_replay_frozen_hermetic(self, tmp_path):
        sim_id = "sim_replay_1"
        report_id = "rep_replay_1"
        sim_dir = tmp_path / "simulations" / sim_id
        sim_dir.mkdir(parents=True, exist_ok=True)

        (sim_dir / "observed_events.jsonl").write_text('{"event": 1}\n', encoding="utf-8")
        (sim_dir / "actors.json").write_text('{"actors": [{"name": "A"}]}', encoding="utf-8")
        (sim_dir / "simulation_brief.json").write_text('{"brief": "test"}', encoding="utf-8")

        with patch("app.services.report_agent.Config.UPLOAD_FOLDER", str(tmp_path)):
            with patch("app.services.evidence_snapshot_service.Config.UPLOAD_FOLDER", str(tmp_path)):
                mock_llm = MagicMock()
                mock_zep_tools = MagicMock()
                mock_action_verifier = MagicMock()

                agent = ReportAgent(
                    graph_id="graph_test",
                    simulation_id=sim_id,
                    simulation_requirement="Test requirement",
                    llm_client=mock_llm,
                    zep_tools=mock_zep_tools,
                    action_verifier=mock_action_verifier,
                    replay_mode="replay_frozen",
                )

                assert agent.replay_mode == "replay_frozen"

                # Tester l'outil interview_agents en mode replay_frozen
                mock_zep_tools.interview_agents.return_value = MagicMock(to_text=lambda: "Offline interview text")
                tool_result = agent._execute_tool("interview_agents", {"interview_topic": "Sujet"})

                assert tool_result == "Offline interview text"
                # Vérifier que replay_mode="replay_frozen" a bien été transmis
                mock_zep_tools.interview_agents.assert_called_once_with(
                    simulation_id=sim_id,
                    interview_requirement="Sujet",
                    simulation_requirement="Test requirement",
                    max_agents=5,
                    replay_mode="replay_frozen",
                )

    def test_report_agent_invalid_replay_mode_raises(self):
        with pytest.raises(ValueError) as exc_info:
            ReportAgent(
                graph_id="g1",
                simulation_id="sim1",
                simulation_requirement="req",
                replay_mode="invalid_mode",
            )
        assert "Invalid replay_mode" in str(exc_info.value)

    def test_report_agent_normalizes_replay_mode(self):
        agent = ReportAgent(
            graph_id="g1",
            simulation_id="sim1",
            simulation_requirement="req",
            llm_client=MagicMock(),
            replay_mode="  REPLAY_FROZEN  ",
        )
        assert agent.replay_mode == "replay_frozen"

    def test_report_agent_generate_report_replay_frozen_no_oasis_close(self, tmp_path):
        sim_id = "sim_replay_gen"
        report_id = "rep_replay_gen"
        sim_dir = tmp_path / "simulations" / sim_id
        sim_dir.mkdir(parents=True, exist_ok=True)

        (sim_dir / "observed_events.jsonl").write_text('{"event": 1}\n', encoding="utf-8")
        (sim_dir / "actors.json").write_text('{"actors": [{"name": "A"}]}', encoding="utf-8")
        (sim_dir / "simulation_brief.json").write_text('{"brief": "test"}', encoding="utf-8")

        with patch("app.services.report_agent.Config.UPLOAD_FOLDER", str(tmp_path)):
            with patch("app.services.evidence_snapshot_service.Config.UPLOAD_FOLDER", str(tmp_path)):
                mock_llm = MagicMock()
                agent = ReportAgent(
                    graph_id="graph_test",
                    simulation_id=sim_id,
                    simulation_requirement="Test requirement",
                    llm_client=mock_llm,
                    replay_mode="replay_frozen",
                )

                with patch.object(agent, "plan_outline") as mock_plan:
                    outline_mock = MagicMock()
                    outline_mock.title = "Titre"
                    outline_mock.summary = "Résumé"
                    outline_mock.sections = []
                    outline_mock.to_dict.return_value = {"title": "Titre", "summary": "Résumé", "sections": []}
                    mock_plan.return_value = outline_mock

                    with patch.object(ReportManager, "assemble_full_report", return_value="# Titre\n\nContenu"):
                        with patch.object(agent, "build_sources_provenance_section", return_value="## Sources"):
                            with patch("app.services.report_quality_gate.ReportQualityGate") as mock_qg:
                                qg_inst = mock_qg.return_value
                                qg_res = MagicMock()
                                from app.models.report_quality import PublicationStatus, QualityStatus
                                qg_res.publication_status = PublicationStatus.VERIFIED_PUBLISHABLE
                                qg_res.final_status = QualityStatus.PASSED
                                qg_res.summary = "OK"
                                qg_inst.evaluate_report.return_value = qg_res

                                with patch("app.services.simulation_runner.SimulationRunner.close_simulation_environment") as mock_close_oasis:
                                    report = agent.generate_report(report_id=report_id)

                                    # AC3: Aucun appel de fermeture OASIS physique en mode replay_frozen
                                    mock_close_oasis.assert_not_called()

                                    # AC3: Empreinte attachée au rapport
                                    assert report.replay_mode == "replay_frozen"
                                    assert report.evidence_snapshot is not None
                                    assert "sha256_hash" in report.evidence_snapshot
                                    assert report.status == ReportStatus.COMPLETED

                                    # Vérifier la persistance via ReportManager
                                    reloaded = ReportManager.get_report(report_id)
                                    assert reloaded is not None
                                    assert reloaded.replay_mode == "replay_frozen"
                                    assert reloaded.evidence_snapshot == report.evidence_snapshot

    def test_report_agent_live_mode_default_calls_oasis_close(self, tmp_path):
        sim_id = "sim_live_gen"
        report_id = "rep_live_gen"
        sim_dir = tmp_path / "simulations" / sim_id
        sim_dir.mkdir(parents=True, exist_ok=True)

        (sim_dir / "observed_events.jsonl").write_text('{"event": 1}\n', encoding="utf-8")
        (sim_dir / "actors.json").write_text('{"actors": [{"name": "A"}]}', encoding="utf-8")
        (sim_dir / "simulation_brief.json").write_text('{"brief": "test"}', encoding="utf-8")

        with patch("app.services.report_agent.Config.UPLOAD_FOLDER", str(tmp_path)):
            with patch("app.services.evidence_snapshot_service.Config.UPLOAD_FOLDER", str(tmp_path)):
                mock_llm = MagicMock()
                # AC4: Mode live par défaut
                agent = ReportAgent(
                    graph_id="graph_test",
                    simulation_id=sim_id,
                    simulation_requirement="Test requirement",
                    llm_client=mock_llm,
                )

                assert agent.replay_mode == "live"

                with patch.object(agent, "plan_outline") as mock_plan:
                    outline_mock = MagicMock()
                    outline_mock.title = "Titre"
                    outline_mock.summary = "Résumé"
                    outline_mock.sections = []
                    outline_mock.to_dict.return_value = {"title": "Titre", "summary": "Résumé", "sections": []}
                    mock_plan.return_value = outline_mock

                    with patch.object(ReportManager, "assemble_full_report", return_value="# Titre\n\nContenu"):
                        with patch.object(agent, "build_sources_provenance_section", return_value="## Sources"):
                            with patch("app.services.report_quality_gate.ReportQualityGate") as mock_qg:
                                qg_inst = mock_qg.return_value
                                qg_res = MagicMock()
                                from app.models.report_quality import PublicationStatus, QualityStatus
                                qg_res.publication_status = PublicationStatus.VERIFIED_PUBLISHABLE
                                qg_res.final_status = QualityStatus.PASSED
                                qg_res.summary = "OK"
                                qg_inst.evaluate_report.return_value = qg_res

                                with patch("app.services.simulation_runner.SimulationRunner.close_simulation_environment") as mock_close_oasis:
                                    report = agent.generate_report(report_id=report_id)

                                    # En mode live, la clôture OASIS physique est invoquée
                                    mock_close_oasis.assert_called_once_with(sim_id)
                                    assert report.replay_mode == "live"


class TestReportApiReplayMode:
    """AC5: Exposition et validation de replay_mode dans POST /api/report/generate."""

    def test_api_generate_report_validates_replay_mode(self):
        from app import create_app
        app = create_app()
        app.config["TESTING"] = True
        client = app.test_client()

        # Mode invalide
        resp = client.post(
            "/api/report/generate",
            json={"simulation_id": "sim_123", "replay_mode": "invalid_mode"},
        )
        assert resp.status_code == 400
        data = resp.get_json()
        assert data["success"] is False
        assert "replay_mode must be either 'live' or 'replay_frozen'" in data["error"]

    def test_api_generate_report_accepts_replay_frozen(self):
        from app import create_app
        from app.models.project import Project, ProjectStatus
        from app.services.simulation_manager import SimulationState, SimulationStatus
        from app.services.simulation_runner import RunnerStatus, SimulationRunState

        app = create_app()
        app.config["TESTING"] = True
        client = app.test_client()

        with patch("app.api.report.SimulationManager.get_simulation") as mock_get_sim:
            with patch("app.api.report.SimulationRunner.get_run_state") as mock_get_run_state:
                with patch("app.api.report.ZepGraphMemoryManager.get_updater", return_value=None):
                    with patch("app.api.report.ProjectManager.get_project") as mock_get_proj:
                        with patch("app.api.report.TaskManager.create_task", return_value="task_123"):
                            with patch("app.api.report.register_graph_reader"):
                                with patch("threading.Thread.start"):
                                    mock_get_sim.return_value = SimulationState(
                                        simulation_id="sim_123",
                                        project_id="proj_123",
                                        graph_id="graph_123",
                                        status=SimulationStatus.COMPLETED,
                                    )
                                    mock_get_run_state.return_value = SimulationRunState(
                                        simulation_id="sim_123",
                                        runner_status=RunnerStatus.COMPLETED,
                                    )
                                    mock_get_proj.return_value = Project(
                                        project_id="proj_123",
                                        name="Test Project",
                                        graph_id="graph_123",
                                        status=ProjectStatus.GRAPH_COMPLETED,
                                        created_at="2026-10-19T10:00:00",
                                        updated_at="2026-10-19T10:00:00",
                                        simulation_requirement="Requirement",
                                    )

                                    resp = client.post(
                                        "/api/report/generate",
                                        json={
                                            "simulation_id": "sim_123",
                                            "replay_mode": "replay_frozen",
                                            "force_regenerate": True,
                                        },
                                    )
                                    assert resp.status_code == 200
                                    res_data = resp.get_json()
                                    assert res_data["success"] is True
                                    assert res_data["data"]["replay_mode"] == "replay_frozen"
                                    assert res_data["data"]["status"] == "generating"
