#!/usr/bin/env python3
"""Valide la structure de planification du dépôt.

La constitution (AGENTS.md §2.8) exige des artefacts de plan par epic et un
fichier markdown par story démarrée. Cette règle ne vaut que si quelqu'un la
vérifie : ce script est cette vérification, et il tourne en CI.

Quatre invariants :
  1. un epic `in-progress` ou au-delà a un dossier de plan complet ;
  2. une story `in-progress` ou au-delà a un fichier ET est citée dans
     `epic-<NNN>.md` — le résumé des critères d'une story encore en backlog
     peut, lui, vivre uniquement dans le hub ;
  3. les états sont parmi les cinq autorisés, les `id` sont uniques et bien
     formés, les sections obligatoires sont présentes, et une story en
     `review` ou `done` n'a plus aucune case ouverte — ni dans `Tâches`, ni
     dans les deux définitions ;
  4. une story citée dans le hub comme `in-progress` ou au-delà a un fichier.

Ce que ce script ne contrôle pas, et qu'il ne prétend pas contrôler :
l'ordre des états. « Jamais de saut » (AGENTS.md §2.8) est une règle de
convention, pas un invariant vérifiable ici — un validateur qui lit des
fichiers n'a pas d'historique. Le dire ici vaut mieux que le laisser croire.

Les stories sont du markdown (ADR 0009) : un petit en-tête machine-readable
puis de la prose. C'est ce qui permet au script de lire l'état sans qu'il se
noie dans du YAML échappé.

Usage :
    cd backend && uv run python scripts/validate_plans.py
    cd backend && uv run python scripts/validate_plans.py --quiet

Code de sortie : 0 si tout va bien, 1 sinon.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import yaml

STATES = {"backlog", "in-progress", "review", "done", "blocked"}
ACTIVE_STATES = {"in-progress", "review", "done"}
CLOSED_STATES = {"review", "done"}

EPIC_REQUIRED = ("id", "slug", "titre", "statut")
STORY_META_REQUIRED = ("id", "epic", "titre", "statut", "auteur")

# Les six sections obligatoires sont en français depuis le format 2 (ADR 0011).
# Avant lui, elles portaient les titres anglais `Definition of Ready`,
# `Definition of Done`, `Tasks` et `Completion notes` : un fichier de story
# écrit avant cette décision est irréprochable et refusé quand même, sans que
# rien ne l'explique. Le marqueur de format rend la rupture explicite et donne
# un diagnostic unique au lieu de sept messages identiques.
STORY_FORMAT = "2"
STORY_FORMAT_HELP = (
    "format de story inconnu ou antérieur — les sections obligatoires sont en "
    "français depuis le format 2 (ADR 0011), un fichier au format 1 porte "
    "`## Tasks` et `## Completion notes`. Reprendre l'historique du fichier "
    "(git log) puis le mettre à jour, ou le reformater."
)
STORY_ID_RE = re.compile(r"\A\d+-\d+[a-z]*\Z")

STORY_SECTIONS = (
    "Définition de prêt",
    "Définition de fini",
    "Tâches",
    "Notes de développement",
    "Revue",
    "Notes de complétion",
)
# Sections dont les cases à cocher obéissent au même régime que `Tâches`
# pour une story en `review` ou `done`.
STORY_CHECKED_SECTIONS = ("Définition de prêt", "Définition de fini")
PLAN_ARTEFACTS = ("prd.md", "architecture.md")

FRONT_MATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.DOTALL)
CHECKBOX_RE = re.compile(r"^\s*-\s*\[( |x|X)\]\s*(\S.*)$", re.MULTILINE)
PLACEHOLDER_MARKERS = ("à remplir", "aucun pour l'instant")


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


def _split_story(path: Path) -> tuple[dict | None, str, list[str]]:
    """Sépare l'en-tête machine-readable du corps en prose.

    Retourne (métadonnées, corps, problèmes). Métadonnées à None si l'en-tête
    est absent ou illisible — le corps est tout de même renvoyé, pour que les
    vérifications de sections donnent un diagnostic complet.
    """
    problems: list[str] = []
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None, "", ["fichier introuvable"]

    match = FRONT_MATTER_RE.match(text)
    if not match:
        return None, text, ["en-tête manquant (attendu : bloc --- ... --- en tête de fichier)"]

    try:
        meta = yaml.safe_load(match.group(1))
    except yaml.YAMLError as exc:
        return None, text[match.end():], [f"en-tête YAML invalide ({exc.__class__.__name__})"]

    if not isinstance(meta, dict):
        return None, text[match.end():], ["en-tête : mapping attendu"]

    return meta, text[match.end():], problems


def _section(body: str, title: str) -> str | None:
    """Contenu d'une section de niveau 2, ou None si elle est absente."""
    pattern = re.compile(
        rf"^##\s+{re.escape(title)}\s*$(.*?)(?=^##\s|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    found = pattern.search(body)
    return found.group(1) if found else None


def _cited_in_hub(hub_text: str, story_id: str) -> bool:
    """La story est-elle citée dans le hub de l'epic ?

    Frontières de mot, jamais sous-chaîne nue : `001-1` est sous-chaîne de
    `001-1b`, et une story en revue dont la ligne a disparu du hub ne doit pas
    passer le contrôle sur celle de sa voisine. Les délimiteurs du hub (`|`,
    espace) ne sont pas des caractères de mot, donc une ligne de tableau comme
    une mention en prose comptent l'une et l'autre.
    """
    return re.search(rf"(?<![\w-]){re.escape(story_id)}(?![\w-])", hub_text) is not None


def _hub_started_stories(hub_text: str) -> list[tuple[str, str]]:
    """Stories du hub passées `in-progress` ou au-delà : (id, statut)."""
    started = []
    for line in hub_text.splitlines():
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) < 3:
            continue
        story_id, statut = cells[0], cells[2].strip("`")
        if story_id and statut in ACTIVE_STATES:
            started.append((story_id, statut))
    return started


def validate_sprint_status(root: Path) -> list[str]:
    """Contrôle l'agrégat d'epics."""
    path = root / "sprint-status.yaml"
    data, err = _load_yaml(path)
    if err:
        return [f"sprint-status.yaml : {err}"]
    if not isinstance(data, dict):
        return ["sprint-status.yaml : racine attendue en mapping"]

    epics = data.get("epics")
    if not isinstance(epics, list) or not epics:
        return ["sprint-status.yaml : champ `epics` attendu, non vide"]

    problems: list[str] = []
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


def _validate_story(path: Path, epic_id: str, hub_text: str) -> list[str]:
    """Contrôle un fichier de story markdown."""
    where = path.name
    meta, body, problems = _split_story(path)

    if meta is None:
        return [f"{where} : {p}" for p in problems]

    for key in STORY_META_REQUIRED:
        if not meta.get(key):
            problems.append(f"{where} : en-tête sans `{key}`")

    story_id = str(meta.get("id", "?"))
    if path.stem != f"story-{story_id}":
        problems.append(f"{where} : l'id `{story_id}` ne correspond pas au nom de fichier")
    if not STORY_ID_RE.match(story_id):
        problems.append(
            f"{where} : id de story mal formé `{story_id}` "
            "(attendu : `<epic>-<n>`, avec un suffixe alphabétique facultatif "
            "pour une story dérivée — AGENTS.md §2.8)"
        )
    if str(meta.get("epic", "")) != epic_id:
        problems.append(f"{where} : `epic` vaut `{meta.get('epic')}`, dossier du plan `{epic_id}`")

    # Format : on sort avant les sections, sinon un fichier au format 1 produit
    # sept messages identiques qui ne disent pas pourquoi il est refusé.
    if str(meta.get("format", "")) != STORY_FORMAT:
        problems.append(f"{where} : {STORY_FORMAT_HELP}")
        return problems

    statut = meta.get("statut")
    if statut not in STATES:
        problems.append(f"{where} : état inconnu `{statut}` (attendu : {sorted(STATES)})")

    for section in STORY_SECTIONS:
        if _section(body, section) is None:
            problems.append(f"{where} : section obligatoire absente « {section} »")

    tasks_section = _section(body, "Tâches") or ""
    tasks = CHECKBOX_RE.findall(tasks_section)
    if not tasks:
        problems.append(f"{where} : « Tâches » vide — au moins une case à cocher attendue")
    elif statut in CLOSED_STATES:
        ouvertes = [label.strip() for done, label in tasks if done.lower() != "x"]
        if ouvertes:
            problems.append(
                f"{where} : statut `{statut}` mais tâches ouvertes : {' / '.join(ouvertes)}"
            )
        # Les deux définitions obéissent au même régime : une Définition de fini
        # non cochée sur une story en revue est une story qui n'est pas prête.
        for section in STORY_CHECKED_SECTIONS:
            section_ouvertes = [
                label.strip()
                for done, label in CHECKBOX_RE.findall(_section(body, section) or "")
                if done.lower() != "x"
            ]
            if section_ouvertes:
                problems.append(
                    f"{where} : statut `{statut}` mais cases ouvertes dans "
                    f"« {section} » : {' / '.join(section_ouvertes)}"
                )

    if statut == "done":
        notes = (_section(body, "Notes de complétion") or "").strip().lower()
        if any(marker in notes for marker in PLACEHOLDER_MARKERS):
            problems.append(f"{where} : statut `done` mais notes de complétion encore en remplissage")

    # La citation se cherche par ligne de tableau, pas par sous-chaîne :
    # « 001-1 » est sous-chaîne de « 001-1b », et une story en revue dont la
    # ligne a disparu du hub passerait sinon le contrôle sur celle de sa
    # voisine.
    if statut in ACTIVE_STATES and hub_text and not _cited_in_hub(hub_text, story_id):
        problems.append(f"{where} : statut `{statut}` mais la story n'est pas citée dans epic-{epic_id}.md")

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

    # Invariant 2, moitié « a un fichier » : une ligne du hub passée
    # `in-progress` sans fichier derrière, le plan et son index divergent en
    # silence. Le résumé d'une story encore en backlog peut vivre sans fichier.
    for story_id, statut in _hub_started_stories(hub_text):
        if not (folder / f"story-{story_id}.md").is_file():
            problems.append(
                f"epic-{epic_id}.md : story `{story_id}` citée `{statut}` "
                "mais aucun fichier story — créer le fichier ou repasser la ligne "
                "en `backlog` (AGENTS.md §2.8)"
            )

    seen: set[str] = set()
    for path in sorted(folder.glob("story-*.md")):
        meta, _body, _ = _split_story(path)
        story_id = str((meta or {}).get("id", path.stem.removeprefix("story-")))
        if story_id in seen:
            problems.append(f"{path.name} : id de story dupliqué `{story_id}`")
        seen.add(story_id)
        problems.extend(_validate_story(path, epic_id, hub_text))

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
        stories = sum(len(list(p.glob("story-*.md")))
                      for p in (root / "docs" / "plans").glob("*") if p.is_dir())
        print(f"✓ structure de planification valide — {len(epics)} epics, {stories} fichier(s) de story")
    return 0


if __name__ == "__main__":
    sys.exit(main())