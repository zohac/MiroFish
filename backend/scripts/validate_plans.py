#!/usr/bin/env python3
"""Valide la structure de planification du dépôt.

Le constitution (AGENTS.md §2.8) exige des artefacts de plan par epic et un
fichier par story démarrée. Cette règle ne vaut que si quelqu'un la vérifie :
ce script est cette vérification, et il tourne en CI.

Trois invariants :
  1. un epic `in-progress` ou au-delà a un dossier de plan complet ;
  2. une story `in-progress` ou au-delà a un fichier ET est citée dans
     `epic-<NNN>.md` — le résumé des critères d'une story encore en backlog
     peut, lui, vivre uniquement dans le hub ;
  3. les états sont parmi les cinq autorisés, les `id` sont uniques, les
     champs obligatoires sont présents, une story en `review` ou `done` a
     toutes ses tâches cochées.

Usage :
    cd backend && uv run python scripts/validate_plans.py
    cd backend && uv run python scripts/validate_plans.py --quiet

Code de sortie : 0 si tout va bien, 1 sinon.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

STATES = {"backlog", "in-progress", "review", "done", "blocked"}
ACTIVE_STATES = {"in-progress", "review", "done"}

EPIC_REQUIRED = ("id", "slug", "titre", "statut")
STORY_REQUIRED = (
    "id",
    "titre",
    "epic",
    "statut",
    "definition_of_ready",
    "definition_of_done",
    "tasks",
    "notes_dev",
    "review",
    "completion_notes",
)
TASK_REQUIRED = ("titre", "fait")
PLAN_ARTEFACTS = ("prd.md", "architecture.md")


def repo_root() -> Path:
    """Racine du dépôt : backend/scripts/validate_plans.py -> ../../."""
    return Path(__file__).resolve().parents[2]


def _load_yaml(path: Path) -> tuple[object | None, str | None]:
    """Charge un YAML. Retourne (données, message d'erreur)."""
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8")), None
    except FileNotFoundError:
        return None, "fichier introuvable"
    except yaml.YAMLError as exc:
        return None, f"YAML invalide ({exc.__class__.__name__})"


def validate_sprint_status(root: Path) -> list[str]:
    """Contrôle l'agrégat d'epics."""
    path = root / "sprint-status.yaml"
    data, err = _load_yaml(path)
    if err:
        return [f"sprint-status.yaml : {err}"]
    if not isinstance(data, dict):
        return ["sprint-status.yaml : racine attendue en mapping"]

    problems: list[str] = []
    epics = data.get("epics")
    if not isinstance(epics, list) or not epics:
        return ["sprint-status.yaml : champ `epics` attendu, non vide"]

    seen: set[str] = set()
    for index, epic in enumerate(epics):
        where = f"sprint-status.yaml : epics[{index}]"
        if not isinstance(epic, dict):
            problems.append(f"{where} : entrée non mapping")
            continue
        for key in EPIC_REQUIRED:
            if not epic.get(key):
                problems.append(f"{where} : champ obligatoire manquant `{key}`")
        epic_id = str(epic.get("id", "?"))
        if epic_id in seen:
            problems.append(f"{where} : id dupliqué `{epic_id}`")
        seen.add(epic_id)

        statut = epic.get("statut")
        if statut not in STATES:
            problems.append(f"{where} : état inconnu `{statut}` (attendu : {sorted(STATES)})")

        # Un epic qui a démarré doit pointer un dossier de plan complet.
        if statut in ACTIVE_STATES:
            plan = epic.get("plan")
            if not plan:
                problems.append(f"{where} (epic {epic_id}) : `plan` obligatoire dès le statut {statut}")
                continue
            problems.extend(_validate_plan_folder(root / str(plan), epic_id))

    return problems


def _validate_plan_folder(folder: Path, epic_id: str) -> list[str]:
    """Contrôle les artefacts d'un dossier de plan."""
    problems: list[str] = []
    if not folder.is_dir():
        return [f"dossier de plan absent : {folder}"]

    for artefact in PLAN_ARTEFACTS:
        if not (folder / artefact).is_file():
            problems.append(f"{folder} : artefact obligatoire absent `{artefact}`")

    hub = folder / f"epic-{epic_id}.md"
    if not hub.is_file():
        problems.append(f"{folder} : hub obligatoire absent `epic-{epic_id}.md`")
    hub_text = hub.read_text(encoding="utf-8") if hub.is_file() else ""

    seen: set[str] = set()
    for path in sorted(folder.glob("story-*.yaml")):
        data, err = _load_yaml(path)
        where = str(path.relative_to(folder))
        if err:
            problems.append(f"{where} : {err}")
            continue
        if not isinstance(data, dict):
            problems.append(f"{where} : racine attendue en mapping")
            continue

        for key in STORY_REQUIRED:
            if key not in data:
                problems.append(f"{where} : champ obligatoire manquant `{key}`")

        story_id = str(data.get("id", "?"))
        if story_id in seen:
            problems.append(f"{where} : id de story dupliqué `{story_id}`")
        seen.add(story_id)

        if path.stem != f"story-{story_id}":
            problems.append(f"{where} : l'id `{story_id}` ne correspond pas au nom de fichier")

        if str(data.get("epic", "")) != epic_id:
            problems.append(f"{where} : `epic` vaut `{data.get('epic')}`, dossier du plan `{epic_id}`")

        statut = data.get("statut")
        if statut not in STATES:
            problems.append(f"{where} : état inconnu `{statut}` (attendu : {sorted(STATES)})")

        tasks = data.get("tasks")
        if not isinstance(tasks, list) or not tasks:
            problems.append(f"{where} : `tasks` attendu, non vide")
        else:
            for task_index, task in enumerate(tasks):
                if not isinstance(task, dict):
                    problems.append(f"{where} : tasks[{task_index}] n'est pas un mapping")
                    continue
                for key in TASK_REQUIRED:
                    if key not in task:
                        problems.append(f"{where} : tasks[{task_index}] sans `{key}`")
                if not isinstance(task.get("fait"), bool):
                    problems.append(f"{where} : tasks[{task_index}] — `fait` doit être un booléen")

            if statut in {"review", "done"}:
                restants = [t.get("titre", "?") for t in tasks
                            if isinstance(t, dict) and t.get("fait") is not True]
                if restants:
                    problems.append(
                        f"{where} : statut `{statut}` mais tâches non cochées : {', '.join(map(str, restants))}"
                    )

        if not isinstance(data.get("definition_of_ready"), list) or not data["definition_of_ready"]:
            problems.append(f"{where} : `definition_of_ready` attendu, non vide")

        if statut in ACTIVE_STATES and hub_text and story_id not in hub_text:
            problems.append(f"{where} : statut `{statut}` mais la story n'est pas citée dans epic-{epic_id}.md")

    return problems


def validate(root: Path) -> list[str]:
    """Toutes les vérifications. Retourne la liste des problèmes (vide = OK)."""
    return validate_sprint_status(root)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=None, help="racine du dépôt (défaut : déduite)")
    parser.add_argument("--quiet", action="store_true", help="n'affiche rien si tout va bien")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve() if args.root else repo_root()
    problems = validate(root)

    if problems:
        print(f"✗ {len(problems)} problème(s) de structure :\n", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1

    if not args.quiet:
        epics = (yaml.safe_load((root / "sprint-status.yaml").read_text(encoding="utf-8")) or {}).get("epics", [])
        stories = sum(len(list(p.glob("story-*.yaml")))
                      for p in (root / "docs" / "plans").glob("*") if p.is_dir())
        print(f"✓ structure de planification valide — {len(epics)} epics, {stories} fichier(s) de story")
    return 0


if __name__ == "__main__":
    sys.exit(main())