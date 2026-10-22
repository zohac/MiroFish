"""Tests hermétiques — Story 014-2 : section « Sources & Provenance » honnête."""

import json
import os
import pytest

from app.models.project import ProjectManager
from app.models.report_claim import ReportClaim, ReportClaimRegistry, VerificationStatus, ClaimKind
from app.services.report_agent import ReportAgent


def _agent(tmp_path, monkeypatch, sim_id="sim_test"):
    agent = ReportAgent(graph_id="graph_test", simulation_id=sim_id, simulation_requirement="test")
    # éviter les accès disque réels pour actions/EvidencePack
    monkeypatch.setattr(agent.action_verifier, "load_simulation_actions", lambda sid: [])
    monkeypatch.setattr(agent.action_verifier, "analyze_intentions", lambda sid: [])
    return agent


def test_section_reads_claims_registry(tmp_path, monkeypatch):
    sim_id = "sim_test"
    agent = _agent(tmp_path, monkeypatch, sim_id)
    monkeypatch.setattr(agent, "_resolve_project", lambda: None)

    registry = ReportClaimRegistry(simulation_id=sim_id)
    # 2 claims avec evidence_refs, 1 avec provenance_regime
    c1 = ReportClaim(claim_id="", text="a", claim_kind=ClaimKind.ANALYST_INFERENCE, origin=__import__("app.models.source_document", fromlist=["InformationOrigin"]).InformationOrigin.INFERENCE, evidence_refs=["evt_1"], verification_status=VerificationStatus.UNSUPPORTED, provenance_regime=None)
    c2 = ReportClaim(claim_id="", text="b", claim_kind=ClaimKind.ANALYST_INFERENCE, origin=__import__("app.models.source_document", fromlist=["InformationOrigin"]).InformationOrigin.INFERENCE, evidence_refs=[], verification_status=VerificationStatus.UNSUPPORTED, provenance_regime="interview")
    registry.add_claim(c1)
    registry.add_claim(c2)

    section = agent.build_sources_provenance_section(claims_registry=registry)
    assert "Affirmations portant un `evidence_refs` non vide : 1" in section
    assert "Affirmations portant un `provenance_regime` : 1" in section


def test_verified_count_matches_registry(tmp_path, monkeypatch):
    sim_id = "sim_test"
    agent = _agent(tmp_path, monkeypatch, sim_id)
    monkeypatch.setattr(agent, "_resolve_project", lambda: None)

    registry = ReportClaimRegistry(simulation_id=sim_id)
    # empty registry
    section = agent.build_sources_provenance_section(claims_registry=registry)
    assert "Affirmations portant un `evidence_refs` non vide : 0" in section
    assert "Aucune traçabilité documentaire affirmée" in section


def test_no_uncalculated_traceability_claim(tmp_path, monkeypatch):
    sim_id = "sim_test"
    agent = _agent(tmp_path, monkeypatch, sim_id)
    monkeypatch.setattr(agent, "_resolve_project", lambda: None)
    section = agent.build_sources_provenance_section(claims_registry=None)
    # no literal certification
    assert "traçabilité non établie" in section.lower() or "Traçabilité non établie" in section


def test_both_event_populations_are_named(tmp_path, monkeypatch):
    sim_id = "sim_test"
    agent = _agent(tmp_path, monkeypatch, sim_id)
    monkeypatch.setattr(agent, "_resolve_project", lambda: None)
    monkeypatch.setattr(agent.action_verifier, "load_simulation_actions", lambda sid: [1, 2, 3])
    section = agent.build_sources_provenance_section(claims_registry=None)
    assert "actions.jsonl" in section
    assert "EvidencePack" in section
    assert "Réconciliation des affirmations" in section


def test_missing_registry_yields_not_established(tmp_path, monkeypatch):
    sim_id = "sim_test"
    agent = _agent(tmp_path, monkeypatch, sim_id)
    monkeypatch.setattr(agent, "_resolve_project", lambda: None)
    # point upload folder to tmp empty
    import app.config as cfg
    monkeypatch.setattr(cfg.Config, "UPLOAD_FOLDER", str(tmp_path))
    section = agent.build_sources_provenance_section()
    assert "Traçabilité non établie" in section


def test_unresolved_project_abstains(tmp_path, monkeypatch):
    sim_id = "sim_test"
    agent = _agent(tmp_path, monkeypatch, sim_id)
    monkeypatch.setattr(agent, "_resolve_project", lambda: None)
    section = agent.build_sources_provenance_section(claims_registry=None)
    assert "Aucun document source structuré" in section


def test_corrupt_project_does_not_break_others(tmp_path, monkeypatch):
    # create two project dirs, one corrupt
    base = tmp_path / "projects"
    base.mkdir()
    good = base / "proj_good"
    good.mkdir()
    (good / "project.json").write_text(json.dumps({"project_id": "proj_good", "name": "good", "status": "created", "created_at": "2026-01-01", "updated_at": "2026-01-01"}))
    bad = base / "proj_bad"
    bad.mkdir()
    (bad / "project.json").write_text("{truncated")
    monkeypatch.setattr(ProjectManager, "PROJECTS_DIR", str(base))
    # get_project corrupt returns None
    assert ProjectManager.get_project("proj_bad") is None
    assert ProjectManager.get_project("proj_good") is not None
    # list skips corrupt
    projects = ProjectManager.list_projects(limit=None)
    ids = [p.project_id for p in projects]
    assert "proj_good" in ids
    assert "proj_bad" not in ids
    # find_projects_by_graph_id doesn't raise
    res = ProjectManager.find_projects_by_graph_id("g")
    assert isinstance(res, list)


def test_list_projects_skips_corrupt(tmp_path, monkeypatch):
    base = tmp_path / "projects2"
    base.mkdir()
    bad = base / "proj_bad"
    bad.mkdir()
    (bad / "project.json").write_text("{truncated")
    monkeypatch.setattr(ProjectManager, "PROJECTS_DIR", str(base))
    assert ProjectManager.list_projects(limit=None) == []


def test_audit_archive_carries_claims_index(tmp_path, monkeypatch):
    import app.config as cfg
    monkeypatch.setattr(cfg.Config, "UPLOAD_FOLDER", str(tmp_path))
    # create sim dir and report_claims.json
    sim_dir = tmp_path / "simulations" / "sim_test"
    sim_dir.mkdir(parents=True)
    claims_file = sim_dir / "report_claims.json"
    claims_file.write_text(json.dumps({"simulation_id": "sim_test", "claims": []}))
    from app.services.simulation_audit_service import SimulationAuditService
    svc = SimulationAuditService(simulation_id="sim_test", report_id="")
    manifest = svc.build_run_manifest()
    assert "claims_index" in manifest
    assert manifest["claims_index"] is not None
    assert "sha256" in manifest["claims_index"]
    # archive contains claims_index.json
    files = svc.gather_audit_files()
    assert "claims_index.json" in files
