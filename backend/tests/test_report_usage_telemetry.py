"""Tests hermétiques de télémétrie d'usage et des plafonds budgétaires (Story 013-4).

Valide :
  - AC1 : ``ReportUsageMetrics``, ``CallUsageRecord`` et ``PricingTable``
          (calcul de coût, modèles inconnus, gratuité des passerelles locales).
  - AC2 : cumul fidèle des tokens par phase et par job, durée totale.
  - AC3 : absence d'``usage`` fournisseur => ``usage_available = False``,
          ``estimated_cost_usd = None`` et ``reasoning_effort_effective`` inconnu.
  - AC4 : plafonds ``max_total_cost_usd`` / ``max_wall_seconds`` avec arrêt
          contrôlé avant toute requête supplémentaire, sans escalade de modèle.
  - AC5 : persistance ``reports/<report_id>/usage.json``, résumé dans
          ``report_history.json`` et inclusion dans ``run_manifest.json``.
  - AC6 : endpoint ``GET /api/report/<report_id>/usage`` et étanchéité des secrets.
"""

from __future__ import annotations

import json
import os
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app import create_app
from app.config import Config
from app.models.report_llm_profile import ReportLLMProfile
from app.models.report_quality import (
    PublicationStatus,
    QualityGateResult,
    QualityStatus,
)
from app.models.report_usage import (
    CallUsageRecord,
    PricingTable,
    ReportUsageMetrics,
    sanitize_usage_payload,
)
from app.services.report_agent import (
    Report,
    ReportAgent,
    ReportManager,
    ReportOutline,
    ReportSection,
    ReportStatus,
)
from app.services.report_usage_tracker import (
    BudgetGuard,
    ReportBudgetExceededError,
    ReportTimeoutError,
    ReportUsageTracker,
    extract_usage_counts,
)
from app.services.simulation_audit_service import SimulationAuditService
from app.utils.llm_client import LLMClient
from app.utils.openai_chat_compat import create_chat_completion


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────


class FakeClock:
    """Horloge monotone contrôlable, sans attente réelle."""

    def __init__(self, start: float = 1000.0):
        self.now = float(start)

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += float(seconds)


def _usage(
    prompt: int = 100,
    completion: int = 50,
    total: int | None = None,
    thinking: int = 20,
) -> SimpleNamespace:
    return SimpleNamespace(
        prompt_tokens=prompt,
        completion_tokens=completion,
        total_tokens=total if total is not None else prompt + completion,
        completion_tokens_details=SimpleNamespace(reasoning_tokens=thinking),
    )


def _record(
    tracker: ReportUsageTracker,
    *,
    phase: str = "sections",
    prompt: int = 100,
    completion: int = 50,
    thinking: int = 20,
) -> CallUsageRecord:
    tracker.set_phase(phase)
    return tracker.record_call(
        usage=_usage(prompt=prompt, completion=completion, thinking=thinking),
        duration_seconds=1.5,
    )


# ──────────────────────────────────────────────────────────────────────────────
# AC1 — Modèle de métriques et table de tarification
# ──────────────────────────────────────────────────────────────────────────────


class TestPricingTable:
    def test_known_model_cost_is_exact(self):
        table = PricingTable()
        # gemini-3.8-flash : 1.50 $/M entrée, 7.50 $/M sortie.
        cost = table.calculate_cost(
            "gemini-3.8-flash", prompt_tokens=1000, completion_tokens=500
        )
        assert cost == pytest.approx(0.00525)

    def test_local_provider_is_free_but_theoretical_cost_remains(self):
        table = PricingTable()
        billed = table.calculate_cost(
            "gemini-3.8-flash",
            prompt_tokens=1000,
            completion_tokens=500,
            provider_id="antigravity-local",
        )
        theoretical = table.theoretical_cost(
            "gemini-3.8-flash", prompt_tokens=1000, completion_tokens=500
        )
        assert billed == 0.0
        assert theoretical == pytest.approx(0.00525)

    def test_local_provider_unknown_model_is_still_free(self):
        table = PricingTable()
        assert (
            table.calculate_cost(
                "claude-opus-5.5", prompt_tokens=1000, completion_tokens=500,
                provider_id="antigravity-local",
            )
            == 0.0
        )

    def test_paid_and_free_models_on_opencode_go_are_distinguished(self):
        table = PricingTable()
        assert (
            table.calculate_cost(
                "deepseek-v4-pro", prompt_tokens=1000, completion_tokens=500,
                provider_id="opencode-go",
            )
            == pytest.approx(0.00366)
        )
        assert (
            table.calculate_cost(
                "space-bunny-free", prompt_tokens=1000, completion_tokens=500,
                provider_id="opencode-go",
            )
            == 0.0
        )

    def test_explicit_free_billing_mode_does_not_zero_a_billable_model(self):
        profile = ReportLLMProfile(
            profile_id="opencode-free",
            model="gemini-3.8-flash",
            provider_id="opencode-go",
            billing_mode="free",
        )
        tracker = ReportUsageTracker(profile=profile, model="gemini-3.8-flash")
        tracker.begin("report_billing_free")
        _record(tracker, phase="planning", prompt=1000, completion=500)
        metrics = tracker.build_metrics()
        # La grille prouve que le modèle est facturable : « free » déclaratif
        # ne peut pas annuler le coût ni neutraliser le plafond.
        assert metrics.estimated_cost_usd == pytest.approx(0.00525)
        assert metrics.theoretical_cost_usd == pytest.approx(0.00525)

    def test_explicit_free_billing_mode_zeroes_an_unpriced_model(self):
        profile = ReportLLMProfile(
            profile_id="local-free",
            model="modele-local-maison",
            provider_id="mon-passage-local",
            billing_mode="free",
        )
        tracker = ReportUsageTracker(profile=profile, model="modele-local-maison")
        tracker.begin("report_billing_free_unknown")
        _record(tracker, phase="planning", prompt=1000, completion=500)
        metrics = tracker.build_metrics()
        assert metrics.estimated_cost_usd == 0.0
        # Aucun coût théorique n'est inventé pour un modèle hors grille.
        assert metrics.theoretical_cost_usd is None
        assert tracker.unpriced_model_calls == 0

    def test_invalid_billing_mode_is_rejected(self):
        with pytest.raises(ValueError, match="billing_mode"):
            ReportLLMProfile(
                profile_id="bad", model="gemini-3.8-flash", billing_mode="freeish"
            )

    def test_billing_mode_survives_from_dict_and_to_dict(self):
        profile = ReportLLMProfile.from_dict(
            {"profile_id": "p", "model": "m", "billing_mode": "metered"}
        )
        assert profile.billing_mode == "metered"
        assert profile.to_dict()["billing_mode"] == "metered"

    def test_null_billing_mode_falls_back_to_auto(self):
        profile = ReportLLMProfile.from_dict(
            {"profile_id": "p", "model": "m", "billing_mode": None}
        )
        assert profile.billing_mode == "auto"

    def test_negative_cost_cap_is_rejected(self):
        with pytest.raises(ValueError, match="max_total_cost_usd"):
            ReportLLMProfile(
                profile_id="p", model="m", max_total_cost_usd=-1.0
            )

    def test_non_finite_cost_cap_is_rejected(self):
        with pytest.raises(ValueError, match="max_total_cost_usd"):
            ReportLLMProfile(
                profile_id="p", model="m", max_total_cost_usd=float("nan")
            )

    def test_unknown_model_has_no_invented_price(self):
        table = PricingTable()
        assert table.get_pricing("modele-inconnu-xyz") is None
        assert (
            table.calculate_cost(
                "modele-inconnu-xyz", prompt_tokens=1000, completion_tokens=500
            )
            is None
        )

    def test_alias_model_resolves_longest_known_prefix(self):
        table = PricingTable()
        pricing = table.get_pricing("gemini-3.8-flash-tiered")
        assert pricing is not None
        assert pricing.model == "gemini-3.8-flash"

    def test_model_merely_containing_a_known_name_is_not_aliased(self):
        # `key in lowered` résolvait n'importe quel nom contenant un modèle
        # tarifé, en sous-estimant le coût et en contournant le plafond.
        assert PricingTable().get_pricing("my-gemini-3.8-flash-clone") is None

    def test_metrics_roundtrip_and_atomic_persistence(self, tmp_path):
        metrics = ReportUsageMetrics(
            report_id="report_rt",
            simulation_id="sim_rt",
            profile_id="flash-high",
            model="gemini-3.8-flash",
            provider_id="opencode-go",
            reasoning_effort_requested="high",
            reasoning_effort_effective="unknown",
            prompt_tokens=100,
            completion_tokens=50,
            thinking_tokens=20,
            total_tokens=150,
            duration_seconds=12.5,
            calls_count=1,
            estimated_cost_usd=0.000045,
            calls=[
                CallUsageRecord(
                    call_index=1,
                    phase="planning",
                    model="gemini-3.8-flash",
                    provider_id="opencode-go",
                    prompt_tokens=100,
                    completion_tokens=50,
                    thinking_tokens=20,
                    total_tokens=150,
                    duration_seconds=12.5,
                    estimated_cost_usd=0.000045,
                )
            ],
        )
        target = tmp_path / "reports" / "report_rt" / "usage.json"
        metrics.save_to_file(str(target))
        assert target.exists()

        loaded = ReportUsageMetrics.load_from_file(str(target))
        assert loaded is not None
        assert loaded.report_id == "report_rt"
        assert loaded.total_tokens == 150
        assert loaded.calls_count == 1
        assert loaded.calls[0].phase == "planning"

        raw = target.read_text(encoding="utf-8")
        assert "api_key" not in raw
        assert "prompt_messages" not in raw
        # Aucun fichier temporaire résiduel et écrasement atomique supporté.
        assert not [p for p in target.parent.iterdir() if ".tmp." in p.name]
        metrics.total_tokens = 999
        metrics.save_to_file(str(target))
        assert ReportUsageMetrics.load_from_file(str(target)).total_tokens == 999
        assert not [p for p in target.parent.iterdir() if ".tmp." in p.name]


# ──────────────────────────────────────────────────────────────────────────────
# AC2 / AC3 — Traqueur, cumuls par phase et usage manquant
# ──────────────────────────────────────────────────────────────────────────────


class TestReportUsageTracker:
    def test_accumulates_tokens_by_phase_and_duration(self):
        clock = FakeClock()
        tracker = ReportUsageTracker(
            model="gemini-3.8-flash",
            provider_id="opencode-go",
            clock=clock,
        )
        tracker.begin("report_acc")
        _record(tracker, phase="planning", prompt=100, completion=50, thinking=10)
        clock.advance(2.0)
        _record(tracker, phase="sections", prompt=200, completion=100, thinking=30)
        clock.advance(3.0)
        _record(tracker, phase="sections", prompt=300, completion=150, thinking=60)

        metrics = tracker.build_metrics()
        assert metrics.calls_count == 3
        assert metrics.prompt_tokens == 600
        assert metrics.completion_tokens == 300
        assert metrics.thinking_tokens == 100
        assert metrics.total_tokens == 900
        assert metrics.phase_totals["planning"]["calls_count"] == 1
        assert metrics.phase_totals["sections"]["calls_count"] == 2
        assert metrics.phase_totals["sections"]["total_tokens"] == 750
        # duration_seconds = temps d'inférence cumulé (3 × 1,5 s) ;
        # wall_seconds = temps mural du job (5,0 s, outils et E/S compris).
        assert metrics.duration_seconds == pytest.approx(4.5)
        assert metrics.wall_seconds == pytest.approx(5.0)

    def test_thinking_tokens_are_extracted_from_dict_usage(self):
        result = extract_usage_counts(
            {
                "prompt_tokens": 10,
                "completion_tokens": 5,
                "total_tokens": 15,
                "completion_tokens_details": {"reasoning_tokens": 3},
            }
        )
        assert result["thinking_tokens"] == 3
        assert result["usage_available"] is True

    def test_missing_usage_marks_unknown_without_inventing_cost(self):
        tracker = ReportUsageTracker(
            model="gemini-3.8-flash", provider_id="opencode-go"
        )
        tracker.begin("report_no_usage")
        tracker.set_phase("planning")
        tracker.record_call(usage=None, duration_seconds=1.0, reasoning_effort_requested="high")

        metrics = tracker.build_metrics()
        assert metrics.usage_available is False
        assert metrics.estimated_cost_usd is None
        assert metrics.reasoning_effort_effective == "unknown"
        assert metrics.total_tokens == 0
        assert metrics.calls_count == 1

    def test_unknown_model_marks_pricing_unavailable(self):
        tracker = ReportUsageTracker(model="modele-inconnu-xyz")
        tracker.begin("report_unknown_model")
        _record(tracker, phase="planning")

        metrics = tracker.build_metrics()
        assert metrics.pricing_available is False
        assert metrics.estimated_cost_usd is None

    def test_callback_never_breaks_llm_request(self):
        tracker = ReportUsageTracker(model="gemini-3.8-flash")
        tracker.begin("report_cb")
        # Une charge exotique ne doit jamais lever.
        assert tracker.handle_llm_usage(usage=object(), model="x") is not None

    def test_unreadable_usage_object_is_not_treated_as_available(self):
        counts = extract_usage_counts(object())
        assert counts["usage_available"] is False
        assert counts["total_tokens"] == 0

        tracker = ReportUsageTracker(
            model="gemini-3.8-flash", provider_id="opencode-go"
        )
        tracker.begin("report_unreadable")
        tracker.set_phase("planning")
        tracker.record_call(usage=object(), duration_seconds=1.0)
        metrics = tracker.build_metrics()
        assert metrics.usage_available is False
        assert metrics.estimated_cost_usd is None

    def test_local_gateway_provider_is_inferred_from_base_url(self):
        profile = ReportLLMProfile(
            profile_id="local",
            model="gemini-3.8-flash",
            provider_id="custom",
            base_url="http://127.0.0.1:18081/v1",
        )
        tracker = ReportUsageTracker(profile=profile, model="gemini-3.8-flash")
        tracker.begin("report_local")
        _record(tracker, phase="sections")
        metrics = tracker.build_metrics()
        assert metrics.provider_id == "antigravity-local"
        assert metrics.estimated_cost_usd == 0.0
        assert metrics.theoretical_cost_usd is not None
        assert metrics.theoretical_cost_usd > 0.0

    def test_confirmed_effort_is_recorded_when_caller_provides_it(self):
        tracker = ReportUsageTracker(
            model="gemini-3.8-flash", provider_id="antigravity-local"
        )
        tracker.begin("report_effort")
        tracker.mark_reasoning_effort_effective("high")
        _record(tracker, phase="planning")
        assert tracker.build_metrics().reasoning_effort_effective == "high"

    def test_antigravity_effort_is_effective_only_with_usage(self):
        profile = ReportLLMProfile(
            profile_id="flash-high",
            model="gemini-3.8-flash",
            provider_id="antigravity-local",
            reasoning_effort="high",
        )
        fake_response = SimpleNamespace(
            usage=_usage(prompt=10, completion=5, thinking=8),
            choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))],
        )
        with patch("app.utils.llm_client.OpenAI"), patch(
            "app.utils.llm_client.create_chat_completion",
            return_value=fake_response,
        ):
            client = LLMClient(
                api_key="test-key",
                base_url="http://127.0.0.1:18081/v1",
                model="gemini-3.8-flash",
            )
            tracker = ReportUsageTracker(
                profile=profile,
                model="gemini-3.8-flash",
                base_url="http://127.0.0.1:18081/v1",
            )
            tracker.attach_to(client)
            tracker.begin("report_effort_usage")
            tracker.set_phase("planning")
            client.chat([{"role": "user", "content": "ping"}])

        assert tracker.build_metrics().reasoning_effort_effective == "high"

    def test_antigravity_effort_stays_unknown_without_usage(self):
        profile = ReportLLMProfile(
            profile_id="flash-high",
            model="gemini-3.8-flash",
            provider_id="antigravity-local",
            reasoning_effort="high",
        )
        tracker = ReportUsageTracker(
            profile=profile,
            model="gemini-3.8-flash",
            provider_id="antigravity-local",
        )
        tracker.begin("report_effort_missing")
        tracker.set_phase("planning")
        tracker.record_call(usage=None, duration_seconds=1.0)
        metrics = tracker.build_metrics()
        assert metrics.usage_available is False
        assert metrics.reasoning_effort_effective == "unknown"

    def test_detach_restores_the_previous_usage_callback(self):
        previous = lambda **kwargs: None  # noqa: E731
        client = MagicMock()
        client.usage_callback = previous
        tracker = ReportUsageTracker(model="gemini-3.8-flash")
        tracker.attach_to(client)
        assert client.usage_callback is tracker._bound_callback
        tracker.detach(client)
        assert client.usage_callback is previous


# ──────────────────────────────────────────────────────────────────────────────
# AC4 — Plafonds budgétaire et temporel
# ──────────────────────────────────────────────────────────────────────────────


class TestBudgetGuard:
    def test_budget_raises_before_next_request_without_model_escalation(self):
        clock = FakeClock()
        tracker = ReportUsageTracker(
            model="gemini-3.8-flash",
            provider_id="opencode-go",
            clock=clock,
        )
        tracker.begin("report_budget")
        _record(tracker, phase="sections", prompt=1000, completion=500)
        calls_before = tracker.calls_count
        model_before = tracker.model

        guard = BudgetGuard(tracker, max_total_cost_usd=0.0001)
        with pytest.raises(ReportBudgetExceededError, match="Plafond budgétaire"):
            guard.check(phase="sections")

        assert tracker.calls_count == calls_before  # aucune requête supplémentaire
        assert tracker.model == model_before  # aucune escalade de modèle
        metrics = tracker.build_metrics()
        assert metrics.budget_exceeded is True
        assert metrics.stop_reason == "budget_exceeded"

    def test_timeout_raises_and_records_reason(self):
        clock = FakeClock()
        tracker = ReportUsageTracker(model="gemini-3.8-flash", clock=clock)
        tracker.begin("report_timeout")
        clock.advance(900.0)

        guard = BudgetGuard(tracker, max_wall_seconds=900)
        with pytest.raises(ReportTimeoutError, match="Durée maximale"):
            guard.check(phase="sections")

        metrics = tracker.build_metrics()
        assert metrics.timeout_exceeded is True
        assert metrics.stop_reason == "timeout"

    def test_zero_budget_stops_immediately(self):
        tracker = ReportUsageTracker(model="gemini-3.8-flash")
        tracker.begin("report_zero")
        guard = BudgetGuard(tracker, max_total_cost_usd=0.0)
        with pytest.raises(ReportBudgetExceededError):
            guard.check(phase="planning")

    def test_unpriced_paid_model_fails_closed(self):
        profile = ReportLLMProfile(
            profile_id="metered-unpriced",
            model="claude-opus-5.5",
            provider_id="opencode-go",
            billing_mode="metered",
        )
        tracker = ReportUsageTracker(profile=profile, model="claude-opus-5.5")
        tracker.begin("report_unpriced")
        _record(tracker, phase="sections", prompt=1000, completion=500)
        guard = BudgetGuard.from_profile(tracker, profile)
        with pytest.raises(ReportBudgetExceededError, match="non vérifiable"):
            guard.check(phase="sections")
        assert tracker.build_metrics().stop_reason == "pricing_unavailable"

    def test_unpriced_model_does_not_fail_closed_on_auto_profile(self):
        profile = ReportLLMProfile(
            profile_id="auto-unpriced",
            model="qwen-plus",
            provider_id="env",
            billing_mode="auto",
        )
        tracker = ReportUsageTracker(profile=profile, model="qwen-plus")
        tracker.begin("report_unpriced_auto")
        _record(tracker, phase="planning", prompt=1000, completion=500)
        guard = BudgetGuard.from_profile(tracker, profile)
        # Un run non déclaré payant ne doit pas être interrompu faute de tarif.
        guard.check(phase="sections")
        metrics = tracker.build_metrics()
        assert metrics.estimated_cost_usd is None
        assert metrics.stop_reason is None


# ──────────────────────────────────────────────────────────────────────────────
# AC2 — Branchement effectif sur LLMClient
# ──────────────────────────────────────────────────────────────────────────────


class TestLLMClientTelemetryHook:
    def test_usage_callback_is_invoked_for_each_completion(self):
        seen = []

        def _callback(**kwargs):
            seen.append(kwargs)

        fake_response = SimpleNamespace(
            usage=_usage(), choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))]
        )
        with patch("app.utils.llm_client.OpenAI"), patch(
            "app.utils.llm_client.create_chat_completion",
            return_value=fake_response,
        ):
            client = LLMClient(
                api_key="test-key",
                base_url="http://127.0.0.1:18081/v1",
                model="gemini-3.8-flash",
                reasoning_effort="high",
                usage_callback=_callback,
            )
            client._create_completion(
                messages=[{"role": "user", "content": "ping"}],
                temperature=0.0,
                max_tokens=16,
                response_format=None,
            )

        assert len(seen) == 1
        assert seen[0]["usage"] is fake_response.usage
        assert seen[0]["model"] == "gemini-3.8-flash"
        assert seen[0]["reasoning_effort"] == "high"
        assert seen[0]["duration_seconds"] >= 0.0

    def test_callback_failure_does_not_break_completion(self):
        def _callback(**kwargs):
            raise RuntimeError("telemetry down")

        fake_response = SimpleNamespace(usage=None)
        with patch("app.utils.llm_client.OpenAI"), patch(
            "app.utils.llm_client.create_chat_completion",
            return_value=fake_response,
        ):
            client = LLMClient(
                api_key="test-key",
                base_url="http://127.0.0.1:18081/v1",
                model="gemini-3.8-flash",
                usage_callback=_callback,
            )
            response = client._create_completion(
                messages=[],
                temperature=0.0,
                max_tokens=8,
                response_format=None,
            )
        assert response is fake_response

    def test_pre_request_callback_blocks_before_http_call(self):
        def _block(**_kwargs):
            raise ReportBudgetExceededError("plafond atteint")

        with patch("app.utils.llm_client.OpenAI"), patch(
            "app.utils.llm_client.create_chat_completion"
        ) as create_mock:
            client = LLMClient(
                api_key="test-key",
                base_url="http://127.0.0.1:18081/v1",
                model="gemini-3.8-flash",
                pre_request_callback=_block,
            )
            with pytest.raises(ReportBudgetExceededError):
                client.chat([{"role": "user", "content": "ping"}])

        create_mock.assert_not_called()

    def test_pre_request_callback_blocks_json_retry_before_http_call(self):
        def _block(**_kwargs):
            raise ReportBudgetExceededError("plafond atteint")

        with patch("app.utils.llm_client.OpenAI"), patch(
            "app.utils.llm_client.create_chat_completion"
        ) as create_mock:
            client = LLMClient(
                api_key="test-key",
                base_url="http://127.0.0.1:18081/v1",
                model="gemini-3.8-flash",
                pre_request_callback=_block,
            )
            with pytest.raises(ReportBudgetExceededError):
                client.chat_json(
                    [{"role": "user", "content": "ping"}], max_attempts=2
                )

        create_mock.assert_not_called()

    def test_request_timeout_is_forwarded_to_the_sdk_call(self):
        fake_response = SimpleNamespace(
            usage=None, choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))]
        )
        with patch("app.utils.llm_client.OpenAI"), patch(
            "app.utils.llm_client.create_chat_completion",
            return_value=fake_response,
        ) as create_mock:
            client = LLMClient(
                api_key="test-key",
                base_url="http://127.0.0.1:18081/v1",
                model="gemini-3.8-flash",
                request_timeout=30.0,
            )
            client.chat([{"role": "user", "content": "ping"}])

        assert create_mock.call_args.kwargs["timeout"] == 30.0

    def test_create_chat_completion_puts_timeout_in_sdk_kwargs(self):
        recorder = MagicMock()
        create_chat_completion(
            recorder, model="gemini-3.8-flash", messages=[], timeout=12.5
        )
        assert recorder.chat.completions.create.call_args.kwargs["timeout"] == 12.5


# ──────────────────────────────────────────────────────────────────────────────
# AC2 / AC5 — Intégration ReportAgent, persistance et historique
# ──────────────────────────────────────────────────────────────────────────────


def _build_agent(
    tmp_path,
    monkeypatch,
    *,
    max_total_cost_usd: float = 2.0,
    max_wall_seconds: int = 900,
) -> ReportAgent:
    monkeypatch.setattr(Config, "UPLOAD_FOLDER", str(tmp_path))
    profile = ReportLLMProfile(
        profile_id="flash-high",
        model="gemini-3.8-flash",
        provider_id="opencode-go",
        reasoning_effort="high",
        max_total_cost_usd=max_total_cost_usd,
        max_wall_seconds=max_wall_seconds,
    )
    fake_llm = MagicMock()
    fake_llm.model = "gemini-3.8-flash"
    fake_llm.profile = profile
    agent = ReportAgent(
        graph_id="graph_usage",
        simulation_id="sim_usage",
        simulation_requirement="Analyse de test",
        llm_client=fake_llm,
        zep_tools=MagicMock(),
        action_verifier=MagicMock(),
        profile=profile,
    )
    return agent


def _patch_generation(monkeypatch, outline: ReportOutline):
    """Neutralise les dépendances lourdes tout en laissant la télémétrie réelle."""

    def fake_plan(self, progress_callback=None):
        self.usage_tracker.set_phase("planning")
        self.usage_tracker.record_call(usage=_usage(prompt=100, completion=50), duration_seconds=1.0)
        return outline

    def fake_section(
        self,
        section,
        outline,
        previous_sections,
        progress_callback=None,
        section_index=0,
    ):
        self.usage_tracker.set_phase("sections")
        self.usage_tracker.record_call(usage=_usage(prompt=100, completion=50), duration_seconds=2.0)
        return f"Contenu {section.title}"

    def fake_quality(self, **kwargs):
        report_id = kwargs.get("report_id") or self.report_id
        return QualityGateResult(
            simulation_id=self.simulation_id,
            report_id=report_id,
            is_publishable=True,
            final_status=QualityStatus.PASSED,
            summary="ok",
            publication_status=PublicationStatus.VERIFIED_PUBLISHABLE,
        )

    monkeypatch.setattr(ReportAgent, "plan_outline", fake_plan)
    monkeypatch.setattr(ReportAgent, "_generate_section_react", fake_section)
    monkeypatch.setattr(ReportAgent, "generate_and_save_cohort_coverage", lambda self, *a, **k: None)
    monkeypatch.setattr(
        ReportAgent,
        "audit_and_save_report_claims",
        lambda self, *a, **k: __import__(
            "app.models.report_claim", fromlist=["ReportClaimRegistry"]
        ).ReportClaimRegistry(simulation_id=self.simulation_id),
    )
    monkeypatch.setattr(
        ReportAgent,
        "build_sources_provenance_section",
        lambda self: "## Sources & Provenance\n",
    )
    monkeypatch.setattr(
        "app.services.report_quality_gate.ReportQualityGate.evaluate_report",
        fake_quality,
    )
    monkeypatch.setattr(
        "app.services.report_quality_gate.ReportQualityGate.save_quality_result",
        lambda self, result: None,
    )
    monkeypatch.setattr(
        "app.services.report_quality_gate.SectionCompletionGuard.complete_section",
        staticmethod(lambda **kwargs: (kwargs.get("current_content", ""), 0, True)),
    )
    monkeypatch.setattr(
        "app.services.simulation_audit_service.SimulationAuditService.build_audit_package",
        lambda self: b"zip",
    )


class TestReportAgentUsageIntegration:
    def test_real_llm_client_callback_reaches_tracker(self, tmp_path, monkeypatch):
        monkeypatch.setattr(Config, "UPLOAD_FOLDER", str(tmp_path))
        fake_response = SimpleNamespace(
            usage=_usage(prompt=12, completion=7, thinking=3),
            choices=[SimpleNamespace(message=SimpleNamespace(content="Bonjour"))],
        )
        with patch("app.utils.llm_client.OpenAI"), patch(
            "app.utils.llm_client.create_chat_completion",
            return_value=fake_response,
        ):
            client = LLMClient(
                api_key="test-key",
                base_url="http://127.0.0.1:18081/v1",
                model="gemini-3.8-flash",
            )
            agent = ReportAgent(
                graph_id="graph_real",
                simulation_id="sim_real",
                simulation_requirement="Test",
                llm_client=client,
                zep_tools=MagicMock(),
                action_verifier=MagicMock(),
            )
            agent.usage_tracker.begin("report_real")
            agent.usage_tracker.set_phase("planning")
            assert agent.llm.chat([{"role": "user", "content": "ping"}]) == "Bonjour"

        assert agent.usage_tracker.calls_count == 1
        assert agent.usage_tracker.prompt_tokens == 12
        assert agent.usage_tracker.completion_tokens == 7
        assert agent.usage_tracker.thinking_tokens == 3
        assert agent.usage_tracker.provider_id == "antigravity-local"

    def test_default_agent_falls_back_to_env_profile_guard(self, tmp_path, monkeypatch):
        monkeypatch.setattr(Config, "UPLOAD_FOLDER", str(tmp_path))
        monkeypatch.setattr(Config, "LLM_MODEL_NAME", "gemini-3.8-flash")
        monkeypatch.setattr(Config, "LLM_API_KEY", "test-key")
        fake_llm = MagicMock()
        fake_llm.model = "gemini-3.8-flash"
        fake_llm.profile = None

        agent = ReportAgent(
            graph_id="graph_env",
            simulation_id="sim_env",
            simulation_requirement="Test",
            llm_client=fake_llm,
            zep_tools=MagicMock(),
            action_verifier=MagicMock(),
        )

        assert agent.usage_tracker.profile is not None
        assert agent.usage_tracker.profile.profile_id == "env-default"
        assert agent.budget_guard.max_total_cost_usd == pytest.approx(2.0)
        assert agent.budget_guard.max_wall_seconds == pytest.approx(900)

    def test_tools_receive_the_profiled_llm_client(self, tmp_path, monkeypatch):
        monkeypatch.setattr(Config, "UPLOAD_FOLDER", str(tmp_path))
        fake_llm = MagicMock()
        fake_llm.model = "gemini-3.8-flash"
        fake_llm.profile = None

        with patch("app.services.report_agent.ZepToolsService") as tools_cls:
            tools_cls.return_value.llm = fake_llm
            ReportAgent(
                graph_id="graph_tools",
                simulation_id="sim_tools",
                simulation_requirement="Test",
                llm_client=fake_llm,
            )

        tools_cls.assert_called_once_with(llm_client=fake_llm)

    def test_pre_request_guard_blocks_after_budget(self, tmp_path, monkeypatch):
        agent = _build_agent(tmp_path, monkeypatch, max_total_cost_usd=0.0)
        callback = agent.llm.pre_request_callback
        assert callable(callback)
        with pytest.raises(ReportBudgetExceededError):
            callback()

    def test_pre_request_guard_forwards_remaining_wall_timeout(self, tmp_path, monkeypatch):
        agent = _build_agent(tmp_path, monkeypatch, max_wall_seconds=60)
        clock = FakeClock()
        agent.usage_tracker._clock = clock
        agent.usage_tracker._start_monotonic = clock()
        clock.advance(10.0)

        agent.llm.pre_request_callback()

        assert agent.llm.request_timeout == pytest.approx(50.0)

    def test_interview_tool_uses_interviews_phase_then_restores(self, tmp_path, monkeypatch):
        agent = _build_agent(tmp_path, monkeypatch)
        agent.usage_tracker.begin("report_phase")
        agent.usage_tracker.set_phase("sections")
        agent.zep_tools.interview_agents.return_value.to_text.return_value = "ok"

        result = agent._execute_tool(
            "interview_agents", {"interview_topic": "sujet", "max_agents": 1}
        )

        assert result == "ok"
        assert agent.usage_tracker.current_phase == "sections"

    def test_execute_tool_is_blocked_above_budget(self, tmp_path, monkeypatch):
        agent = _build_agent(tmp_path, monkeypatch, max_total_cost_usd=0.0)
        agent.usage_tracker.begin("report_tool_budget")
        agent.zep_tools.query_simulation_events = MagicMock()

        with pytest.raises(ReportBudgetExceededError):
            agent._execute_tool("query_simulation_events", {"query": "x"})

        agent.zep_tools.query_simulation_events.assert_not_called()

    def test_bind_telemetry_reattaches_after_detach(self, tmp_path, monkeypatch):
        agent = _build_agent(tmp_path, monkeypatch)
        agent.llm.usage_callback = None
        agent.llm.pre_request_callback = None
        agent._bind_telemetry()

        assert agent.llm.usage_callback is agent.usage_tracker._bound_callback
        assert callable(agent.llm.pre_request_callback)

        agent.usage_tracker.detach(agent.llm)
        agent.llm.pre_request_callback = None
        agent._bind_telemetry()

        assert agent.llm.usage_callback is agent.usage_tracker._bound_callback
        assert callable(agent.llm.pre_request_callback)

    def test_usage_is_accumulated_and_persisted(self, tmp_path, monkeypatch):
        agent = _build_agent(tmp_path, monkeypatch)
        outline = ReportOutline(
            title="Rapport",
            summary="Résumé",
            sections=[ReportSection("S1"), ReportSection("S2")],
        )
        _patch_generation(monkeypatch, outline)

        report = agent.generate_report(report_id="report_usage_ok")

        assert report.status == ReportStatus.COMPLETED
        usage_path = ReportManager._get_usage_path("report_usage_ok")
        assert os.path.exists(usage_path)

        metrics = ReportUsageMetrics.load_from_file(usage_path)
        assert metrics is not None
        assert metrics.calls_count == 3
        assert metrics.prompt_tokens == 300
        assert metrics.completion_tokens == 150
        assert metrics.phase_totals["planning"]["calls_count"] == 1
        assert metrics.phase_totals["sections"]["calls_count"] == 2
        assert metrics.estimated_cost_usd == pytest.approx(0.001575)
        assert metrics.reasoning_effort_requested == "high"
        assert metrics.reasoning_effort_effective == "unknown"
        assert report.usage_metrics is not None
        assert report.usage_metrics["calls_count"] == 3

        meta = json.loads(
            open(ReportManager._get_report_path("report_usage_ok"), encoding="utf-8").read()
        )
        assert meta["usage_metrics"]["calls_count"] == 3

        history = json.loads(
            open(
                ReportManager._get_history_path("sim_usage"),
                encoding="utf-8",
            ).read()
        )
        assert history["reports"][-1]["usage_summary"]["calls_count"] == 3

    def test_budget_stops_before_second_section(self, tmp_path, monkeypatch):
        agent = _build_agent(tmp_path, monkeypatch, max_total_cost_usd=0.0012)
        outline = ReportOutline(
            title="Rapport",
            summary="Résumé",
            sections=[ReportSection("S1"), ReportSection("S2")],
        )
        _patch_generation(monkeypatch, outline)

        report = agent.generate_report(report_id="report_budget_stop")

        assert report.status == ReportStatus.FAILED
        assert "Plafond budgétaire" in (report.error or "")

        metrics = ReportUsageMetrics.load_from_file(
            ReportManager._get_usage_path("report_budget_stop")
        )
        assert metrics is not None
        assert metrics.budget_exceeded is True
        assert metrics.stop_reason == "budget_exceeded"
        # planning + première section seulement : zéro requête après le plafond.
        assert metrics.calls_count == 2
        assert not os.path.exists(
            ReportManager._get_section_path("report_budget_stop", 2)
        )
        # La section déjà écrite reste exploitable : sortie partielle assemblée.
        assert os.path.exists(
            ReportManager._get_section_path("report_budget_stop", 1)
        )
        assert os.path.exists(
            ReportManager._get_report_markdown_path("report_budget_stop")
        )

        history = json.loads(
            open(ReportManager._get_history_path("sim_usage"), encoding="utf-8").read()
        )
        failed_entry = history["reports"][-1]
        assert failed_entry["status"] == "failed"
        assert failed_entry["usage_summary"]["stop_reason"] == "budget_exceeded"

    def test_budget_zero_is_a_controlled_stop(self, tmp_path, monkeypatch):
        agent = _build_agent(tmp_path, monkeypatch, max_total_cost_usd=0.0)
        outline = ReportOutline(
            title="Rapport", summary="Résumé", sections=[ReportSection("S1")]
        )
        _patch_generation(monkeypatch, outline)

        report = agent.generate_report(report_id="report_budget_zero")

        assert report.status == ReportStatus.FAILED
        assert "Plafond budgétaire" in (report.error or "")
        metrics = ReportUsageMetrics.load_from_file(
            ReportManager._get_usage_path("report_budget_zero")
        )
        assert metrics is not None
        assert metrics.stop_reason == "budget_exceeded"
        assert metrics.calls_count == 0
        assert os.path.exists(
            ReportManager._get_report_path("report_budget_zero")
        )

    def test_wall_timeout_is_a_controlled_stop(self, tmp_path, monkeypatch):
        agent = _build_agent(tmp_path, monkeypatch, max_wall_seconds=1)
        outline = ReportOutline(
            title="Rapport", summary="Résumé", sections=[ReportSection("S1")]
        )
        _patch_generation(monkeypatch, outline)
        clock = FakeClock()

        def slow_plan(self, progress_callback=None):
            clock.advance(2.0)
            return outline

        monkeypatch.setattr(ReportAgent, "plan_outline", slow_plan)
        agent.usage_tracker._clock = clock
        agent.usage_tracker._start_monotonic = clock()

        report = agent.generate_report(report_id="report_timeout_stop")

        assert report.status == ReportStatus.FAILED
        assert "Durée maximale" in (report.error or "")
        metrics = ReportUsageMetrics.load_from_file(
            ReportManager._get_usage_path("report_timeout_stop")
        )
        assert metrics is not None
        assert metrics.timeout_exceeded is True
        assert metrics.stop_reason == "timeout"
        assert not os.path.exists(
            ReportManager._get_section_path("report_timeout_stop", 1)
        )

    def test_history_backfills_usage_summary_from_usage_file(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.setattr(Config, "UPLOAD_FOLDER", str(tmp_path))
        report = Report(
            report_id="report_legacy_usage",
            simulation_id="sim_legacy",
            graph_id="graph_legacy",
            simulation_requirement="Test",
            status=ReportStatus.COMPLETED,
            created_at="2026-10-19T10:00:00Z",
        )
        ReportManager.save_report(report)
        ReportUsageMetrics(
            report_id="report_legacy_usage",
            model="gemini-3.8-flash",
            calls_count=2,
            total_tokens=30,
            estimated_cost_usd=0.1,
        ).save_to_file(ReportManager._get_usage_path("report_legacy_usage"))
        ReportManager._append_to_history(
            "sim_legacy",
            {
                "report_id": "report_legacy_usage",
                "simulation_id": "sim_legacy",
                "created_at": "2026-10-19T10:00:00Z",
                "status": "completed",
            },
        )

        entries = ReportManager.list_reports_by_simulation("sim_legacy")
        entry = next(
            item for item in entries if item["report_id"] == "report_legacy_usage"
        )
        assert entry["usage_summary"]["calls_count"] == 2
        assert entry["usage_summary"]["total_tokens"] == 30


# ──────────────────────────────────────────────────────────────────────────────
# AC5 — Inclusion dans le dossier d'audit / run_manifest
# ──────────────────────────────────────────────────────────────────────────────


class TestAuditUsageInclusion:
    def test_usage_json_and_summary_are_included_in_audit(self, tmp_path, monkeypatch):
        monkeypatch.setattr(Config, "UPLOAD_FOLDER", str(tmp_path))
        report_id = "report_audit_usage"
        metrics = ReportUsageMetrics(
            report_id=report_id,
            simulation_id="sim_audit",
            model="gemini-3.8-flash",
            provider_id="opencode-go",
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
            calls_count=1,
            estimated_cost_usd=0.000045,
        )
        metrics.save_to_file(ReportManager._get_usage_path(report_id))

        with patch.object(
            SimulationAuditService, "_get_git_commit", return_value="test-commit"
        ):
            service = SimulationAuditService(
                simulation_id="sim_audit", report_id=report_id
            )
            files = service.gather_audit_files()

        assert "usage.json" in files
        persisted = json.loads(files["usage.json"].decode("utf-8"))
        assert persisted["total_tokens"] == 150

        manifest = json.loads(files["run_manifest.json"].decode("utf-8"))
        assert manifest["version"] == "1.1.0"
        assert manifest["llm"]["gateway"]
        assert manifest["usage"]["total_tokens"] == 150
        assert manifest["usage"]["estimated_cost_usd"] == pytest.approx(0.000045)
        assert manifest["llm"]["model_name"] == "gemini-3.8-flash"
        assert manifest["llm"]["provider"] == "opencode-go"
        assert "base_url" not in manifest["llm"]
        assert "api_key" not in json.dumps(manifest)

        checksums = files["checksums.sha256"].decode("utf-8")
        usage_hash = __import__("hashlib").sha256(files["usage.json"]).hexdigest()
        assert f"{usage_hash}  usage.json" in checksums

    def test_audit_declares_missing_usage_instead_of_omitting_it(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.setattr(Config, "UPLOAD_FOLDER", str(tmp_path))
        with patch.object(
            SimulationAuditService, "_get_git_commit", return_value="test-commit"
        ):
            files = SimulationAuditService(
                simulation_id="sim_sans_usage", report_id="report_sans_usage"
            ).gather_audit_files()

        payload = json.loads(files["usage.json"].decode("utf-8"))
        assert payload["report_id"] == "report_sans_usage"
        assert payload["usage_available"] is False
        assert payload["reason"] == "absent"


# ──────────────────────────────────────────────────────────────────────────────
# AC6 — Endpoint REST et étanchéité des secrets
# ──────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setattr(Config, "UPLOAD_FOLDER", str(tmp_path))
    application = create_app()
    application.config["TESTING"] = True
    return application


@pytest.fixture
def client(app):
    return app.test_client()


def _mock_report(report_id: str = "report_api_usage") -> Report:
    return Report(
        report_id=report_id,
        simulation_id="sim_api",
        graph_id="graph_api",
        simulation_requirement="Test API",
        status=ReportStatus.COMPLETED,
        created_at="2026-10-19T10:00:00Z",
        completed_at="2026-10-19T10:05:00Z",
        markdown_content="# Rapport\n",
    )


class TestUsageApi:
    def test_list_reports_omits_call_level_telemetry(self, client):
        report = _mock_report("report_list_usage")
        report.usage_metrics = ReportUsageMetrics(
            report_id="report_list_usage",
            model="gemini-3.8-flash",
            calls_count=1,
            calls=[
                CallUsageRecord(
                    call_index=1, phase="planning", model="gemini-3.8-flash"
                )
            ],
        ).to_dict()
        ReportManager.save_report(report)

        payload = client.get("/api/report/list").get_json()

        item = next(
            entry
            for entry in payload["data"]
            if entry["report_id"] == "report_list_usage"
        )
        assert "calls" not in item["usage_metrics"]
        assert item["usage_metrics"]["calls_count"] == 1

    def test_usage_endpoint_returns_complete_metrics(self, client):
        report = _mock_report()
        ReportManager.save_report(report)
        metrics = ReportUsageMetrics(
            report_id=report.report_id,
            simulation_id=report.simulation_id,
            profile_id="flash-high",
            model="gemini-3.8-flash",
            provider_id="opencode-go",
            reasoning_effort_requested="high",
            reasoning_effort_effective="unknown",
            prompt_tokens=100,
            completion_tokens=50,
            thinking_tokens=20,
            total_tokens=150,
            duration_seconds=4.2,
            calls_count=1,
            estimated_cost_usd=0.000045,
        )
        metrics.save_to_file(ReportManager._get_usage_path(report.report_id))

        response = client.get(f"/api/report/{report.report_id}/usage")

        assert response.status_code == 200
        payload = response.get_json()
        assert payload["success"] is True
        data = payload["data"]
        assert data["report_id"] == report.report_id
        assert data["calls_count"] == 1
        assert data["total_tokens"] == 150
        assert data["thinking_tokens"] == 20
        assert data["reasoning_effort_requested"] == "high"
        assert data["reasoning_effort_effective"] == "unknown"
        assert data["estimated_cost_usd"] == pytest.approx(0.000045)

    def test_usage_endpoint_returns_404_for_unknown_report(self, client):
        response = client.get("/api/report/report_inexistant/usage")
        assert response.status_code == 404
        assert response.get_json()["success"] is False

    def test_usage_endpoint_returns_404_when_metrics_absent(self, client):
        report = _mock_report("report_no_usage")
        ReportManager.save_report(report)
        response = client.get(f"/api/report/{report.report_id}/usage")
        assert response.status_code == 404
        assert "traceback" not in response.get_json()

    def test_usage_endpoint_reports_corrupt_file_without_traceback(self, client):
        report = _mock_report("report_corrupt_usage")
        ReportManager.save_report(report)
        usage_path = ReportManager._get_usage_path(report.report_id)
        os.makedirs(os.path.dirname(usage_path), exist_ok=True)
        with open(usage_path, "w", encoding="utf-8") as handle:
            handle.write("{ not valid json")

        response = client.get(f"/api/report/{report.report_id}/usage")

        assert response.status_code == 500
        assert response.get_json()["success"] is False
        assert "traceback" not in response.get_json()

    def test_usage_endpoint_scrubs_secrets_and_prompts(self, client):
        report = _mock_report("report_api_secret")
        ReportManager.save_report(report)
        usage_path = ReportManager._get_usage_path(report.report_id)
        os.makedirs(os.path.dirname(usage_path), exist_ok=True)
        with open(usage_path, "w", encoding="utf-8") as handle:
            json.dump(
                {
                    "report_id": report.report_id,
                    "api_key": "sk-super-secret",
                    "base_url": "http://private-host/v1",
                    "prompt": "contenu personnel brut",
                    "messages": [{"role": "user", "content": "secret"}],
                    "total_tokens": 42,
                    "usage_available": True,
                },
                handle,
            )

        response = client.get(f"/api/report/{report.report_id}/usage")

        assert response.status_code == 200
        raw = json.dumps(response.get_json())
        assert "sk-super-secret" not in raw
        assert "private-host" not in raw
        assert "contenu personnel brut" not in raw
        assert response.get_json()["data"]["total_tokens"] == 42


# ──────────────────────────────────────────────────────────────────────────────
# Garanties transverses
# ──────────────────────────────────────────────────────────────────────────────


def test_sanitizer_is_recursive_and_key_aware():
    payload = {
        "usage": {
            "total_tokens": 10,
            "api_key": "secret",
            "baseUrl": "http://private",
            "access-token": "secret-token",
            "prompt_messages": ["raw"],
            "nested": [{"prompt": "raw"}, {"safe": 1}],
        },
        "label": "ok",
    }
    cleaned = sanitize_usage_payload(payload)
    assert cleaned == {
        "usage": {"total_tokens": 10, "nested": [{}, {"safe": 1}]},
        "label": "ok",
    }
