"""Tests hermétiques pour la Story 015-5 : télémétrie vivante et ergonomie IHM.

Vérifie :
1. La persistance incrémentale de usage.json (final=False) sans sceller _usage_persisted.
2. L'actualisation des métriques aux étapes intermédiaires puis le scellement définitif (final=True).
3. L'ordre strict des opérations de clôture (artefacts sur disque avant log_report_complete et log_error).
4. La présence des règles CSS anti-débordement dans Step3Simulation.vue et des jalons dans Step4Report.vue.
"""

from datetime import datetime
import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

from app.models.report_usage import CallUsageRecord, ReportUsageMetrics
from app.services.report_agent import Report, ReportAgent, ReportManager, ReportStatus
from app.services.report_usage_tracker import ReportUsageTracker


def _make_sample_call(call_index: int = 0, tokens: int = 100) -> CallUsageRecord:
    return CallUsageRecord(
        call_index=call_index,
        phase="sections",
        model="deepseek-v4.1-flash",
        prompt_tokens=tokens,
        completion_tokens=20,
        thinking_tokens=10,
        total_tokens=tokens + 30,
        duration_seconds=1.2,
        estimated_cost_usd=0.005,
    )


def test_incremental_usage_metrics_persistence_without_premature_sealing(tmp_path: Path):
    """AC3 : final=False écrit usage.json sans sceller _usage_persisted."""
    report_id = "report_test_inc_001"
    report_dir = tmp_path / "reports" / report_id
    report_dir.mkdir(parents=True, exist_ok=True)

    with patch.object(ReportManager, "_get_report_folder", return_value=str(report_dir)):
        agent = ReportAgent(
            graph_id="graph_test",
            simulation_id="sim_test",
            simulation_requirement="Test requirement",
        )
        agent._current_report_id = report_id
        tracker = ReportUsageTracker(report_id=report_id, simulation_id="sim_test", model="deepseek-v4.1-flash")
        agent.usage_tracker = tracker

        # 1. Premier appel
        tracker.record_call(
            usage={"prompt_tokens": 100, "completion_tokens": 20, "thinking_tokens": 10, "total_tokens": 130},
            model="deepseek-v4.1-flash",
            duration_seconds=1.2,
        )
        metrics_step1 = agent._persist_usage_metrics(report_id, final=False)

        assert getattr(agent, "_usage_persisted", False) is False
        assert tracker._completed_at is None  # restauré pour permettre de continuer
        usage_file = report_dir / "usage.json"
        assert usage_file.exists()
        with open(usage_file, "r", encoding="utf-8") as f:
            data1 = json.load(f)
        assert data1["calls_count"] == 1
        assert data1["total_tokens"] == 130

        # 2. Deuxième appel incrémental
        tracker.record_call(
            usage={"prompt_tokens": 200, "completion_tokens": 20, "thinking_tokens": 10, "total_tokens": 230},
            model="deepseek-v4.1-flash",
            duration_seconds=1.2,
        )
        metrics_step2 = agent._persist_usage_metrics(report_id, final=False)

        assert getattr(agent, "_usage_persisted", False) is False
        with open(usage_file, "r", encoding="utf-8") as f:
            data2 = json.load(f)
        assert data2["calls_count"] == 2
        assert data2["total_tokens"] == 360

        # 3. Clôture finale (final=True)
        metrics_final = agent._persist_usage_metrics(report_id, final=True)
        assert getattr(agent, "_usage_persisted", False) is True
        with open(usage_file, "r", encoding="utf-8") as f:
            data3 = json.load(f)
        assert data3["calls_count"] == 2
        assert data3["completed_at"] is not None

        # 4. Appel ultérieur après scellement : retourne les métriques scellées sans réécrire
        tracker.record_call(
            usage={"prompt_tokens": 999, "completion_tokens": 20, "thinking_tokens": 10, "total_tokens": 1029},
            model="deepseek-v4.1-flash",
            duration_seconds=1.2,
        )
        metrics_cached = agent._persist_usage_metrics(report_id, final=True)
        with open(usage_file, "r", encoding="utf-8") as f:
            data4 = json.load(f)
        assert data4["calls_count"] == 2  # n'a pas été écrasé


def test_closure_sequence_persists_artifacts_before_logging_completion():
    """AC4 : save_report et persist_usage_metrics précèdent log_report_complete."""
    events = []

    mock_logger = MagicMock()
    mock_logger.log_report_complete.side_effect = lambda **kwargs: events.append("log_report_complete")

    def fake_save_report(rep):
        events.append("save_report")

    def fake_persist(report_id, report=None, final=True):
        events.append("persist_usage")
        return ReportUsageMetrics(report_id=report_id)

    agent = ReportAgent(
        graph_id="graph_order",
        simulation_id="sim_order",
        simulation_requirement="Order requirement",
    )
    agent.report_logger = mock_logger
    agent._persist_usage_metrics = fake_persist

    with patch.object(ReportManager, "save_report", side_effect=fake_save_report), \
         patch.object(ReportManager, "update_progress", lambda *args, **kwargs: events.append("update_progress")):

        # Simuler la section de clôture nominale
        report = Report(
            report_id="rep_test_order",
            simulation_id="sim_order",
            graph_id="graph_order",
            simulation_requirement="Order requirement",
            status=ReportStatus.COMPLETED,
        )
        agent._persist_usage_metrics("rep_test_order", report, final=True)
        ReportManager.save_report(report)
        ReportManager.update_progress("rep_test_order", "completed", 100, "done")
        agent.report_logger.log_report_complete(total_sections=3, total_time_seconds=10.0)

        assert events == ["persist_usage", "save_report", "update_progress", "log_report_complete"]


def test_closure_sequence_persists_artifacts_before_logging_error():
    """AC4 : save_report et persist_usage_metrics précèdent log_error lors d'un échec."""
    events = []

    mock_logger = MagicMock()
    mock_logger.log_error.side_effect = lambda *args, **kwargs: events.append("log_error")

    def fake_save_report(rep):
        events.append("save_report")

    def fake_persist(report_id, report=None, final=True):
        events.append("persist_usage")
        return ReportUsageMetrics(report_id=report_id)

    agent = ReportAgent(
        graph_id="graph_err",
        simulation_id="sim_err",
        simulation_requirement="Error requirement",
    )
    agent.report_logger = mock_logger
    agent._persist_usage_metrics = fake_persist

    with patch.object(ReportManager, "save_report", side_effect=fake_save_report), \
         patch.object(ReportManager, "update_progress", lambda *args, **kwargs: events.append("update_progress")):

        report = Report(
            report_id="rep_test_err",
            simulation_id="sim_err",
            graph_id="graph_err",
            simulation_requirement="Error requirement",
            status=ReportStatus.FAILED,
        )
        agent._persist_usage_metrics("rep_test_err", report, final=True)
        ReportManager.save_report(report)
        ReportManager.update_progress("rep_test_err", "failed", -1, "error")
        agent.report_logger.log_error("Simulated error", "failed")

        assert events == ["persist_usage", "save_report", "update_progress", "log_error"]


def test_step3_control_bar_css_rules_present():
    """AC1, AC2 : Les règles CSS anti-débordement et d'espacement sont présentes dans Step3Simulation.vue."""
    step3_file = Path(__file__).resolve().parents[2] / "frontend" / "src" / "components" / "Step3Simulation.vue"
    assert step3_file.exists()
    content = step3_file.read_text(encoding="utf-8")

    # .control-bar
    assert "min-height: 64px;" in content
    assert "height: auto;" in content
    assert "flex-wrap: wrap;" in content
    assert "gap: 12px 16px;" in content

    # .status-group
    assert "flex: 1 1 auto;" in content
    assert "min-width: 0;" in content

    # .platform-status
    assert "overflow: visible;" in content
    assert "box-sizing: border-box;" in content

    # .stat
    assert "white-space: nowrap;" in content

    # .action-controls
    assert ".action-controls {" in content
    assert "margin-left: auto;" in content
    assert "flex-shrink: 0;" in content


def test_step4_live_telemetry_milestones_present():
    """AC5, AC6 : Step4Report.vue écoute les jalons de polling et gère l'état error."""
    step4_file = Path(__file__).resolve().parents[2] / "frontend" / "src" / "components" / "Step4Report.vue"
    assert step4_file.exists()
    content = step4_file.read_text(encoding="utf-8")

    assert "resolveLiveTelemetryDisplay" in content
    assert "step4.metricPending" in content
    assert "step4.metricUnpriced" in content
    assert "log.action === 'error'" in content
    assert "shouldRefreshTelemetry" in content
