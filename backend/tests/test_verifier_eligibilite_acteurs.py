"""Tests de protocole de la sonde d'éligibilité réelle (story 009-1, AC12)."""

import json
from types import SimpleNamespace

from scripts.verifier_eligibilite_acteurs import (
    DATASETS,
    _evaluate_domain,
    load_dataset,
    main,
    run_measurement,
)


def test_mock_measurement_passes_on_both_domains():
    report = run_measurement(use_mock=True)
    assert report["mode"] == "mock"
    assert report["passed"] is True
    assert set(report["domains"]) == set(DATASETS)
    for domain in report["domains"].values():
        assert len(domain["actors_retained"]) >= 2
        assert domain["false_actors"] == []
        assert domain["passed"] is True


def test_mock_report_contains_no_secret():
    report = run_measurement(use_mock=True)
    blob = json.dumps(report, ensure_ascii=False)
    assert "api_key" not in blob.lower()
    assert "sk-" not in blob


def test_actorless_domain_fails():
    dataset = load_dataset("logiciel_gestion")
    classification = SimpleNamespace(by_uuid=lambda: {}, summary=lambda: {"total": 0})
    result = _evaluate_domain(classification, dataset)
    assert result["passed"] is False
    assert result["actors_retained"] == []


def test_false_actor_is_detected():
    dataset = load_dataset("logiciel_gestion")
    product_case = next(
        case for case in dataset["cases"]
        if case["expected"]["status"] == "ineligible"
    )
    fake_qualification = SimpleNamespace(
        role=SimpleNamespace(value="person"),
        status=SimpleNamespace(value="eligible"),
        diagnostic=None,
    )
    by_uuid = {product_case["entity"]["uuid"]: fake_qualification}
    classification = SimpleNamespace(by_uuid=lambda: by_uuid, summary=lambda: {"total": 1})
    result = _evaluate_domain(classification, dataset)
    assert result["false_actors"] == [product_case["entity"]["name"]]
    assert result["passed"] is False


def test_review_activation_is_a_false_actor():
    dataset = load_dataset("logiciel_gestion")
    review_case = next(
        case for case in dataset["cases"]
        if case["expected"]["status"] == "review"
    )
    fake_qualification = SimpleNamespace(
        role=SimpleNamespace(value="collective"),
        status=SimpleNamespace(value="eligible"),
        diagnostic=None,
    )
    by_uuid = {review_case["entity"]["uuid"]: fake_qualification}
    classification = SimpleNamespace(by_uuid=lambda: by_uuid, summary=lambda: {"total": 1})
    result = _evaluate_domain(classification, dataset)
    assert result["false_actors"] == [review_case["entity"]["name"]]
    assert result["passed"] is False


def test_main_mock_mode_returns_zero(tmp_path):
    exit_code = main([
        "--mock",
        "--quiet",
        "--output-json", str(tmp_path / "report.json"),
        "--output-md", str(tmp_path / "report.md"),
    ])
    assert exit_code == 0
    written = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert written["mode"] == "mock"
