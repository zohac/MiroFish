#!/usr/bin/env python3
"""Sonde de mesure réelle du classifieur d'éligibilité (story 009-1, AC12 / C2).

Cette sonde est **hors pytest et hors CI** : elle exécute le classifieur sur les
fixtures annotées des deux domaines, enregistre les messages et les sorties, et
compare le résultat obtenu aux annotations. Elle n'écrit jamais dans un graphe et
ne lance aucune simulation sociale.

Code retour :
    0  => tous les domaines satisfont leurs seuils ;
    1  => au moins un domaine échoue (aucun acteur retenu, faux acteur, ou
          classifieur indisponible).

Un mode `--mock` déterministe existe pour valider la plomberie hors ligne ; il est
explicitement identifié comme tel dans le rapport et ne vaut jamais mesure C2.
Aucun credential n'apparaît dans les sorties.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.models.actor_eligibility import (  # noqa: E402
    ACTOR_ELIGIBILITY_POLICY_VERSION,
    DEFAULT_CONFIDENCE_THRESHOLD,
)
from app.services.actor_classifier import ActorClassifierService  # noqa: E402
from app.services.zep_entity_reader import EntityNode  # noqa: E402


FIXTURE_DIR = BACKEND_ROOT / "tests" / "fixtures" / "actor_eligibility"
DATASETS = ("logiciel_gestion", "evenement_culturel")
MIN_ACTORS_PER_DOMAIN = 2
MAX_FALSE_ACTORS_PER_DOMAIN = 0


def _git_commit() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=BACKEND_ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except Exception:
        return "inconnu"


def _versions() -> Dict[str, str]:
    versions = {"python": sys.version.split()[0]}
    try:
        import pydantic

        versions["pydantic"] = pydantic.VERSION
    except Exception:
        pass
    try:
        import openai

        versions["openai"] = openai.__version__
    except Exception:
        pass
    return versions


def load_dataset(name: str) -> Dict[str, Any]:
    return json.loads((FIXTURE_DIR / f"{name}.json").read_text(encoding="utf-8"))


def fixture_entities(dataset: Dict[str, Any]) -> List[EntityNode]:
    return [EntityNode(**case["entity"]) for case in dataset["cases"]]


class FixtureOracleClient:
    """Mode `--mock` : reproduit les annotations attendues, sans réseau.

    Utilisé uniquement pour valider la plomberie de la sonde. Jamais une mesure.
    """

    def __init__(self, dataset: Dict[str, Any]):
        self.by_key = {
            (case["entity"]["name"], case["entity"]["summary"]): case["expected"]
            for case in dataset["cases"]
        }

    def chat_json(self, messages, **kwargs):
        payload = json.loads(messages[1]["content"].split("\n", 1)[1])
        entity = payload["entite"]
        expected = self.by_key.get((entity["nom"], entity["resume"]))
        if expected is None:
            return {"role": "unknown", "status": "review", "rationale": "inconnu", "confidence": 0.0}
        return {
            "role": expected["role"],
            "status": expected["status"],
            "rationale": expected["rationale"],
            "confidence": 0.95,
        }


class RecordingClient:
    """Enveloppe un client LLM réel et consigne les messages/sorties utiles."""

    def __init__(self, delegate):
        self.delegate = delegate
        self.records: List[Dict[str, Any]] = []

    def chat_json(self, messages, **kwargs):
        response = self.delegate.chat_json(messages, **kwargs)
        self.records.append({
            "system": messages[0]["content"] if messages else "",
            "user": messages[1]["content"] if len(messages) > 1 else "",
            "response": response,
        })
        return response


def _evaluate_domain(classification, dataset: Dict[str, Any]) -> Dict[str, Any]:
    by_uuid = classification.by_uuid()
    matrix = []
    actors_retained = []
    false_actors = []
    for case in dataset["cases"]:
        entity = case["entity"]
        expected = case["expected"]
        qualification = by_uuid.get(entity["uuid"])
        obtained_role = qualification.role.value if qualification else "absente"
        obtained_status = qualification.status.value if qualification else "absente"
        match = (
            obtained_role == expected["role"] and obtained_status == expected["status"]
        )
        entry = {
            "uuid": entity["uuid"],
            "name": entity["name"],
            "expected_role": expected["role"],
            "expected_status": expected["status"],
            "obtained_role": obtained_role,
            "obtained_status": obtained_status,
            "match": match,
            "diagnostic": (qualification.diagnostic if qualification else "aucune qualification"),
        }
        matrix.append(entry)
        if expected["status"] == "eligible" and obtained_status == "eligible":
            actors_retained.append(entity["name"])
        if expected["status"] != "eligible" and obtained_status == "eligible":
            # Toute activation d'une entité non attendue comme acteur est un
            # faux acteur : les produits/URLs/tarifs (ineligible) comme les
            # collectifs et identités ambiguës (review) qui doivent rester
            # passifs (AC5, AC12).
            false_actors.append(entity["name"])

    passed = (
        len(actors_retained) >= MIN_ACTORS_PER_DOMAIN
        and len(false_actors) <= MAX_FALSE_ACTORS_PER_DOMAIN
    )
    return {
        "thresholds": {
            "min_actors": MIN_ACTORS_PER_DOMAIN,
            "max_false_actors": MAX_FALSE_ACTORS_PER_DOMAIN,
        },
        "counts": classification.summary(),
        "actors_retained": actors_retained,
        "false_actors": false_actors,
        "passed": passed,
        "matrix": matrix,
    }


def run_measurement(use_mock: bool = False) -> Dict[str, Any]:
    domains: Dict[str, Any] = {}
    records: List[Dict[str, Any]] = []
    classifier_available = True
    global_passed = True

    for name in DATASETS:
        dataset = load_dataset(name)
        entities = fixture_entities(dataset)
        recording = None
        if use_mock:
            client = FixtureOracleClient(dataset)
        else:
            try:
                recording = RecordingClient(_default_client())
                client = recording
            except Exception:
                classifier_available = False
                client = None
        classifier = ActorClassifierService(llm_client=client)
        classification = classifier.classify_entities(
            entities, dataset["simulation_requirement"]
        )
        if recording is not None:
            records.extend(recording.records)
        domains[name] = _evaluate_domain(classification, dataset)
        global_passed = global_passed and domains[name]["passed"]

    return {
        "schema_version": 1,
        "mode": "mock" if use_mock else "real",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "commit": _git_commit(),
        "policy_version": ACTOR_ELIGIBILITY_POLICY_VERSION,
        "versions": _versions(),
        "model": _model_metadata(use_mock),
        "parameters": {"confidence_threshold": DEFAULT_CONFIDENCE_THRESHOLD},
        "classifier_available": classifier_available,
        "domains": domains,
        "exchanges": records,
        "passed": global_passed and classifier_available,
    }


def _default_client():
    from app.utils.llm_client import LLMClient

    return LLMClient()


def _model_metadata(use_mock: bool) -> Dict[str, Any]:
    if use_mock:
        return {"client": "fixture-oracle", "model_name": "mock"}
    return {
        "client": "LLMClient (OpenAI compatible)",
        "model_name": os.environ.get("LLM_MODEL_NAME") or "inconnu",
        "base_url": os.environ.get("LLM_BASE_URL") or "inconnu",
    }


def _render_markdown(report: Dict[str, Any]) -> str:
    lines = [
        "# Mesure 009-1 — Classifieur d'éligibilité des acteurs",
        "",
        f"- **Mode** : {report['mode']}",
        f"- **Date** : {report['generated_at']}",
        f"- **Commit** : {report['commit']}",
        f"- **Politique** : {report['policy_version']}",
        f"- **Classifieur disponible** : {report['classifier_available']}",
        f"- **Modèle** : {report['model'].get('model_name')}",
        f"- **Résultat global** : {'SUCCÈS' if report['passed'] else 'ÉCHEC'}",
        "",
    ]
    for domain, data in report["domains"].items():
        lines.append(f"## Domaine `{domain}` — {'SUCCÈS' if data['passed'] else 'ÉCHEC'}")
        lines.append("")
        lines.append(f"- Acteurs retenus : {len(data['actors_retained'])} / seuil {data['thresholds']['min_actors']}")
        lines.append(f"- Faux acteurs : {len(data['false_actors'])} / seuil {data['thresholds']['max_false_actors']}")
        lines.append(f"- Compteurs : {data['counts']}")
        lines.append("")
        lines.append("| Entité | Attendu | Obtenu | Correspond |")
        lines.append("|---|---|---|---|")
        for entry in data["matrix"]:
            lines.append(
                f"| {entry['name'] or '(vide)'} | {entry['expected_role']}/{entry['expected_status']} "
                f"| {entry['obtained_role']}/{entry['obtained_status']} | {'oui' if entry['match'] else 'non'} |"
            )
        lines.append("")
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Mesure réelle du classifieur d'éligibilité 009-1")
    parser.add_argument("--mock", action="store_true", help="Mode déterministe hors ligne (non mesurant)")
    parser.add_argument("--output-json", default="mesure-009-1.json")
    parser.add_argument("--output-md", default="mesure-009-1.md")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    report = run_measurement(use_mock=args.mock)

    Path(args.output_json).write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    Path(args.output_md).write_text(_render_markdown(report), encoding="utf-8")

    if not args.quiet:
        print(f"Mode: {report['mode']} | Résultat: {'SUCCÈS' if report['passed'] else 'ÉCHEC'}")
        for domain, data in report["domains"].items():
            print(
                f"  {domain}: acteurs={len(data['actors_retained'])} "
                f"faux={len(data['false_actors'])} -> {'OK' if data['passed'] else 'KO'}"
            )

    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
