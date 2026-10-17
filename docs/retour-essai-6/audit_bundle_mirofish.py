#!/usr/bin/env python3
"""Contrôle hors ligne des exports MiroFish (audit de régression, non un correctif du moteur).

Usage: python audit_bundle_mirofish.py /chemin/vers/export [--json-out resultats.json]
Bibliothèque standard uniquement. Ne transmet aucune donnée sur un réseau.
"""
from __future__ import annotations

import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import re

REQUIRED = (
    "actors.json", "cohort_coverage.json", "observed_events.jsonl",
    "quality_checks.json", "report_claims.json", "report.md",
    "run_manifest.json", "simulation_brief.json", "source_manifest.json",
)
AGENT_ID_PATTERN = re.compile(r"^Agent_(\d+)$", flags=re.ASCII)
EVENT_ID_PATTERN = re.compile(r"^evt_(?:twitter|reddit)_(\d+)_(\d+)_")


def analyze(directory: Path) -> dict:
    findings: list[dict] = []

    def record(code: str, severity: str, message: str, **details: object) -> None:
        findings.append({"code": code, "severity": severity, "message": message, "details": details})

    missing = [f for f in REQUIRED if not (directory / f).is_file()]
    if missing:
        record("BUNDLE_INCOMPLETE", "ERROR", "Fichiers d'audit absents", missing=missing)
        return {"status": "FAIL", "findings": findings, "metrics": {}}

    docs = {name: json.loads((directory / name).read_text(encoding="utf-8"))
            for name in REQUIRED if name.endswith(".json")}
    events = [json.loads(line) for line in (directory / "observed_events.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    report = (directory / "report.md").read_text(encoding="utf-8")
    sim_ids = {x.get("simulation_id") for x in events}
    run_id = docs["run_manifest.json"].get("simulation_id")
    if sim_ids != {run_id}:
        record("RUN_MISMATCH", "ERROR", "Les événements appartiennent à plusieurs runs ou à un autre run", event_run_ids=sorted(str(i) for i in sim_ids), manifest_run_id=run_id)

    # Integrity is checked against declared checksums only; not proof of original generation.
    checksum_path = directory / "checksums.sha256"
    if checksum_path.is_file():
        mismatched = []
        for row in checksum_path.read_text(encoding="utf-8").splitlines():
            if not row.strip():
                continue
            expected, filename = row.split(None, 1)
            target = directory / filename.strip()
            if not target.is_file() or sha256(target.read_bytes()).hexdigest() != expected:
                mismatched.append(filename.strip())
        if mismatched:
            record("CHECKSUM_MISMATCH", "ERROR", "Intégrité SHA-256 non conforme", files=mismatched)
    else:
        record("CHECKSUM_MISSING", "WARN", "Aucun checksum d'export trouvé")

    all_ids = [e.get("event_id") for e in events]
    duplicates = [eid for eid, c in Counter(all_ids).items() if c > 1]
    if duplicates:
        record("EVENT_ID_COLLISION", "ERROR", "IDs d'événements non uniques", count=len(duplicates))

    coverage = docs["cohort_coverage.json"]
    claims = docs["report_claims.json"]
    quality = docs["quality_checks.json"]
    actor_sel = docs["actors.json"]
    ev_by_id = {e.get("event_id"): e for e in events}
    wrong_ids = []
    not_found_refs = []
    for member in coverage.get("members", []):
        name = member.get("persona_name", "")
        alias = AGENT_ID_PATTERN.fullmatch(name)
        for ref in member.get("observed_event_ids", []):
            ev = ev_by_id.get(ref)
            if ev is None:
                not_found_refs.append({"member": name, "event_id": ref})
            elif alias and int(alias.group(1)) != ev.get("agent_id"):
                wrong_ids.append({"member": name, "event_id": ref, "actual_agent_id": ev.get("agent_id")})
    if not_found_refs:
        record("COVERAGE_BROKEN_REFS", "ERROR", "Couverture citant des événements absents", count=len(not_found_refs), sample=not_found_refs[:5])
    if wrong_ids:
        record("COVERAGE_ALIAS_COLLISION", "ERROR", "Événements attribués à un autre identifiant d'agent", count=len(wrong_ids), sample=wrong_ids[:5])

    selected = actor_sel.get("actors", [])
    eligible = {a.get("entity_name") for a in selected if a.get("eligibility_status") == "eligible"}
    ineligible_with_activity = [m.get("persona_name") for m in coverage.get("members", [])
                                if m.get("persona_name") not in eligible
                                and not AGENT_ID_PATTERN.fullmatch(m.get("persona_name", ""))
                                and m.get("action_count", 0) > 0]
    if ineligible_with_activity:
        record("INELIGIBLE_COHORT_ACTIVITY", "ERROR", "Entités non éligibles recensées comme actives", names=ineligible_with_activity[:12])

    generic_aliases = [m for m in coverage.get("members", []) if AGENT_ID_PATTERN.fullmatch(m.get("persona_name", ""))]
    if generic_aliases:
        record("DUPLICATE_COHORT_VIEW", "WARN", "Cohorte contient des agents génériques en plus des profils nommés : risque de double comptage", aliases=len(generic_aliases), aggregate_actions=sum(m.get("action_count", 0) for m in generic_aliases))

    false_prospect = [m.get("persona_name") for m in coverage.get("members", [])
                      if m.get("persona_name") in {"Simon", "Sophie Jouan"} and m.get("scenario_role") == "PROSPECT"]
    if false_prospect:
        record("SCENARIO_ROLE_INVALID", "ERROR", "Fondateur/pilote de ce scénario étiqueté prospect", names=false_prospect)
    # Generic safeguard: adoption verdict must not be assigned to non-prospect stakeholders.
    nonprospect_adoption = [m.get("persona_name") for m in coverage.get("members", [])
                           if m.get("decision_status") == "ADOPTED" and m.get("scenario_role") != "PROSPECT"]
    if nonprospect_adoption:
        record("ADOPTION_NONPROSPECT", "ERROR", "Un statut ADOPTED est attribué à des rôles non prospects", names=nonprospect_adoption)

    raw_status = Counter(c.get("verification_status", "UNKNOWN") for c in claims.get("claims", []))
    action_like = [c for c in claims.get("claims", []) if c.get("claim_kind") == "OBSERVED_SOCIAL_ACTION"]
    action_unsupported = [c for c in action_like if c.get("verification_status") != "VERIFIED"]
    if action_unsupported:
        record("UNVERIFIED_OBSERVED_ACTION", "ERROR", "Des actions dites observées ne sont pas authentifiées", count=len(action_unsupported))
    if claims.get("total_claims", 0) > 0 and raw_status.get("VERIFIED", 0) == 0:
        record("ZERO_VERIFIED_CLAIMS", "ERROR", "Aucune affirmation du rapport n'a été vérifiée", claims_total=claims.get("total_claims"))
    if quality.get("is_publishable") and (raw_status.get("VERIFIED", 0) == 0 or action_unsupported):
        record("FAIL_OPEN_PUBLICATION", "ERROR", "Rapport déclaré publiable malgré une couverture de preuve non vérifiée", verification_ratio=claims.get("verification_ratio"))

    source = docs["source_manifest.json"]
    role_conflicts = [x.get("filename") for x in source.get("documents", []) if x.get("epistemic_kind") == "PERSONA_SPECIFICATION" and x.get("role") == "facts"]
    if role_conflicts:
        record("SOURCE_ROLE_CONFLICT", "WARN", "Documents de personas typés facts dans le contrat source", files=role_conflicts)
    no_chunks = [x.get("filename") for x in source.get("documents", []) if x.get("total_chunks") == 0]
    if no_chunks:
        record("SOURCE_CHUNK_METADATA_EMPTY", "WARN", "Métadonnées de fragments à zéro ; vérifier si c'est inconnu ou réellement absent", files=no_chunks)

    brief = docs["simulation_brief.json"]
    if not brief.get("time_horizon") and re.search(r"\b72\s*h(?:eures)?\b", brief.get("goal", ""), re.I):
        record("BRIEF_HORIZON_UNSTRUCTURED", "WARN", "Horizon exprimé dans le texte mais champ time_horizon vide")
    run = docs["run_manifest.json"]
    if not run.get("simulation", {}).get("completed_at") or run.get("git_commit") in (None, "", "unknown-git-commit"):
        record("INCOMPLETE_RUN_MANIFEST", "WARN", "Manifest incomplet pour le rejeu", git_commit=run.get("git_commit"), completed_at=run.get("simulation", {}).get("completed_at"))
    if "Sources & Provenance" not in report and "Sources et Provenance" not in report:
        record("REPORT_PROVENANCE_MISSING", "WARN", "Section de provenance absente du Markdown final")

    metrics = {
        "run_id": run_id,
        "event_rows": len(events),
        "unique_event_ids": len(set(all_ids)),
        "actors_total": len(selected),
        "eligible_actors": len(eligible),
        "cohort_members": len(coverage.get("members", [])),
        "cohort_total_action_references": sum(m.get("action_count", 0) for m in coverage.get("members", [])),
        "claims_total": claims.get("total_claims", 0),
        "claims_verified": raw_status.get("VERIFIED", 0),
        "claims_unsupported": raw_status.get("UNSUPPORTED", 0),
        "claims_contradicted": raw_status.get("CONTRADICTED", 0),
        "bundle_publishable": quality.get("is_publishable"),
        "diagnostics_errors": sum(f["severity"] == "ERROR" for f in findings),
        "diagnostics_warnings": sum(f["severity"] == "WARN" for f in findings),
    }
    return {"status": "FAIL" if any(f["severity"] == "ERROR" for f in findings) else "PASS_WITH_WARNINGS" if findings else "PASS", "metrics": metrics, "findings": findings}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--json-out", type=Path)
    args = parser.parse_args()
    result = analyze(args.directory)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.json_out:
        args.json_out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 1 if result["status"] == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
