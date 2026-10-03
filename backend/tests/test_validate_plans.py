"""Tests du script de validation de la structure de planification.

Le script est un garde-fou de la constitution (AGENTS.md §2.8) : sans test, il
peut mentir — notamment en « validant » une structure incomplète, ce qui est
pire que de ne rien valider du tout.
"""

import importlib.util
from pathlib import Path

import pytest
import yaml


def _load_script():
    path = Path(__file__).resolve().parents[1] / "scripts" / "validate_plans.py"
    spec = importlib.util.spec_from_file_location("validate_plans", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


validate_plans = _load_script()


# --------------------------------------------------------------------------
# Fixtures : un dépôt minimal conforme
# --------------------------------------------------------------------------

def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _valid_story(story_id: str, epic: str, statut: str, *, tasks_checked: bool | None = None) -> str:
    """Un fichier de story conforme. `tasks_checked` force l'état des cases."""
    checked = (statut in {"review", "done"}) if tasks_checked is None else tasks_checked
    mark = "x" if checked else " "
    meta = yaml.safe_dump(
        {"id": story_id, "epic": epic, "titre": "Une story de test", "statut": statut, "auteur": "test"},
        allow_unicode=True,
        sort_keys=False,
    ).strip()
    return (
        f"---\n{meta}\n---\n\n"
        f"# Story {story_id} — Une story de test\n\n"
        "## Pourquoi cette story\n\n"
        "Parce que.\n\n"
        "## Définition de prêt\n\n"
        "- [x] Critères écrits\n- [x] Stratégie de test identifiée\n\n"
        "## Définition de fini\n\n"
        "- tests verts\n\n"
        "## Tâches\n\n"
        f"- [{mark}] 1. faire un truc\n\n"
        "## Notes de développement\n\n"
        "Rien.\n\n"
        "## Revue\n\n"
        "Aucun.\n\n"
        "## Notes de complétion\n\n"
        "_Rien à signaler._\n"
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """Un dépôt minimal mais conforme : les tests partent de là."""
    plan = tmp_path / "docs" / "plans" / "001-truc"
    _write(plan / "prd.md", "# PRD")
    _write(plan / "architecture.md", "# Architecture")
    _write(plan / "epic-001.md", "# Epic 001\n\n| 001-1 | story | `backlog` | story-001-1.md |")
    _write(plan / "story-001-1.md", _valid_story("001-1", "001", "backlog"))
    _write(
        tmp_path / "sprint-status.yaml",
        yaml.safe_dump(
            {
                "projet": "test",
                "branche": "local-first",
                "mis_a_jour": "2026-10-03",
                "epics": [
                    {
                        "id": "001",
                        "slug": "truc",
                        "titre": "Un truc",
                        "statut": "in-progress",
                        "plan": "docs/plans/001-truc",
                    }
                ],
            },
            allow_unicode=True,
            sort_keys=False,
        ),
    )
    return tmp_path


def _break_story(repo: Path, old: str, new: str) -> None:
    """Remplace un fragment dans le fichier de story du dépôt de test."""
    path = repo / "docs/plans/001-truc/story-001-1.md"
    path.write_text(path.read_text(encoding="utf-8").replace(old, new), encoding="utf-8")


# --------------------------------------------------------------------------
# Cas nominal
# --------------------------------------------------------------------------

def test_valid_repo_has_no_problem(repo: Path):
    assert validate_plans.validate(repo) == []


def test_real_repo_is_valid():
    """Le dépôt réel doit passer. C'est le test le plus utile du fichier."""
    assert validate_plans.validate(validate_plans.repo_root()) == []


def test_quiet_mode_is_silent_on_success(repo: Path, capsys):
    assert validate_plans.main(["--root", str(repo), "--quiet"]) == 0
    assert capsys.readouterr().out == ""


def test_non_quiet_mode_reports_counts(repo: Path, capsys):
    assert validate_plans.main(["--root", str(repo)]) == 0
    assert "1 epics" in capsys.readouterr().out


# --------------------------------------------------------------------------
# Artefacts manquants
# --------------------------------------------------------------------------

def test_missing_prd_is_reported(repo: Path):
    (repo / "docs/plans/001-truc/prd.md").unlink()
    problems = validate_plans.validate(repo)
    assert any("prd.md" in p for p in problems)


def test_missing_epic_hub_is_reported(repo: Path):
    (repo / "docs/plans/001-truc/epic-001.md").unlink()
    problems = validate_plans.validate(repo)
    assert any("epic-001.md" in p for p in problems)


def test_missing_plan_folder_is_reported(repo: Path):
    for path in (repo / "docs/plans/001-truc").iterdir():
        path.unlink()
    (repo / "docs/plans/001-truc").rmdir()
    problems = validate_plans.validate(repo)
    assert any("dossier de plan absent" in p for p in problems)


def test_started_epic_without_plan_field_is_reported(repo: Path):
    data = yaml.safe_load((repo / "sprint-status.yaml").read_text())
    del data["epics"][0]["plan"]
    _write(repo / "sprint-status.yaml", yaml.safe_dump(data, allow_unicode=True))
    problems = validate_plans.validate(repo)
    assert any("`plan` obligatoire" in p for p in problems)


def test_backlog_epic_needs_no_plan(repo: Path):
    data = yaml.safe_load((repo / "sprint-status.yaml").read_text())
    del data["epics"][0]["plan"]
    data["epics"][0]["statut"] = "backlog"
    _write(repo / "sprint-status.yaml", yaml.safe_dump(data, allow_unicode=True))
    assert validate_plans.validate(repo) == []


# --------------------------------------------------------------------------
# États et identifiants
# --------------------------------------------------------------------------

def test_unknown_state_is_reported(repo: Path):
    data = yaml.safe_load((repo / "sprint-status.yaml").read_text())
    data["epics"][0]["statut"] = "en-cours"
    _write(repo / "sprint-status.yaml", yaml.safe_dump(data, allow_unicode=True))
    problems = validate_plans.validate(repo)
    assert any("état inconnu" in p for p in problems)


def test_duplicate_epic_id_is_reported(repo: Path):
    data = yaml.safe_load((repo / "sprint-status.yaml").read_text())
    data["epics"].append(dict(data["epics"][0]))
    _write(repo / "sprint-status.yaml", yaml.safe_dump(data, allow_unicode=True))
    problems = validate_plans.validate(repo)
    assert any("id dupliqué" in p for p in problems)


def test_story_id_must_match_filename(repo: Path):
    _write(repo / "docs/plans/001-truc/story-001-1.md", _valid_story("001-9", "001", "backlog"))
    problems = validate_plans.validate(repo)
    assert any("ne correspond pas au nom de fichier" in p for p in problems)


def test_story_epic_must_match_folder(repo: Path):
    _write(repo / "docs/plans/001-truc/story-001-1.md", _valid_story("001-1", "999", "backlog"))
    problems = validate_plans.validate(repo)
    assert any("dossier du plan" in p for p in problems)


def test_missing_meta_field_is_reported(repo: Path):
    _break_story(repo, "auteur: test", "# auteur déplacé")
    problems = validate_plans.validate(repo)
    assert any("`auteur`" in p for p in problems)


def test_missing_front_matter_is_reported(repo: Path):
    _break_story(repo, "---\n", "")
    problems = validate_plans.validate(repo)
    assert any("en-tête" in p for p in problems)


# --------------------------------------------------------------------------
# Sections et tâches
# --------------------------------------------------------------------------

def test_missing_section_is_reported(repo: Path):
    _break_story(repo, "## Revue", "## Autre chose")
    problems = validate_plans.validate(repo)
    assert any("section obligatoire absente « Revue »" in p for p in problems)


def test_done_story_with_open_task_is_reported(repo: Path):
    _write(repo / "docs/plans/001-truc/story-001-1.md",
           _valid_story("001-1", "001", "done", tasks_checked=False))
    _write(repo / "docs/plans/001-truc/epic-001.md", "# Epic 001\n\n001-1")
    problems = validate_plans.validate(repo)
    assert any("tâches ouvertes" in p for p in problems)


def test_review_story_with_checked_tasks_passes(repo: Path):
    _write(repo / "docs/plans/001-truc/story-001-1.md", _valid_story("001-1", "001", "review"))
    _write(repo / "docs/plans/001-truc/epic-001.md", "# Epic 001\n\n001-1")
    assert validate_plans.validate(repo) == []


def test_empty_tasks_is_reported(repo: Path):
    _break_story(repo, "- [ ] 1. faire un truc", "- 1. faire un truc")
    problems = validate_plans.validate(repo)
    assert any("« Tâches » vide" in p for p in problems)


def test_done_story_with_placeholder_notes_is_reported(repo: Path):
    _write(repo / "docs/plans/001-truc/story-001-1.md", _valid_story("001-1", "001", "done"))
    _break_story(repo, "_Rien à signaler._", "_À remplir à la fin : ce qui a divergé._")
    _write(repo / "docs/plans/001-truc/epic-001.md", "# Epic 001\n\n001-1")
    problems = validate_plans.validate(repo)
    assert any("notes de complétion encore en remplissage" in p for p in problems)


# --------------------------------------------------------------------------
# Le cœur de la règle : une story démarrée doit être traçable
# --------------------------------------------------------------------------

def test_started_story_must_be_cited_in_hub(repo: Path):
    _write(repo / "docs/plans/001-truc/story-001-1.md", _valid_story("001-1", "001", "in-progress"))
    _write(repo / "docs/plans/001-truc/epic-001.md", "# Epic 001\n\nrien à voir")
    problems = validate_plans.validate(repo)
    assert any("n'est pas citée dans" in p for p in problems)


def test_backlog_story_need_not_be_cited(repo: Path):
    _write(repo / "docs/plans/001-truc/epic-001.md", "# Epic 001\n\nrien à voir")
    assert validate_plans.validate(repo) == []


def test_story_without_file_is_allowed_while_epic_is_backlog(repo: Path):
    data = yaml.safe_load((repo / "sprint-status.yaml").read_text())
    data["epics"][0]["statut"] = "backlog"
    del data["epics"][0]["plan"]
    _write(repo / "sprint-status.yaml", yaml.safe_dump(data, allow_unicode=True))
    (repo / "docs/plans/001-truc/story-001-1.md").unlink()
    assert validate_plans.validate(repo) == []


def test_duplicate_story_id_is_reported(repo: Path):
    _write(repo / "docs/plans/001-truc/story-001-1-b.md", _valid_story("001-1", "001", "backlog"))
    problems = validate_plans.validate(repo)
    assert any("id de story dupliqué" in p for p in problems)


# --------------------------------------------------------------------------
# Robustesse
# --------------------------------------------------------------------------

def test_unclosed_quote_in_front_matter_is_reported(repo: Path):
    # PyYAML n'écrit `id: 001-1` sans guillemets (scalaire simple) : c'est la
    # chaîne à viser. Un guillemet double laissé ouvert fait passer le scalaire
    # à la ligne et finit en "unexpected end of stream" : PyYAML lève, et le
    # script doit le rapporter au lieu de laisser remonter l'exception à la CI.
    _break_story(repo, "id: 001-1", 'id: "001-1')
    problems = validate_plans.validate(repo)
    assert any("en-tête YAML invalide" in p for p in problems)


def test_missing_sprint_status_is_reported(tmp_path: Path):
    problems = validate_plans.validate(tmp_path)
    assert any("sprint-status.yaml" in p for p in problems)


def test_empty_epic_list_is_reported(repo: Path):
    _write(repo / "sprint-status.yaml", yaml.safe_dump({"epics": []}, allow_unicode=True))
    problems = validate_plans.validate(repo)
    assert any("non vide" in p for p in problems)


def test_main_returns_one_on_problems(repo: Path, capsys):
    (repo / "docs/plans/001-truc/prd.md").unlink()
    assert validate_plans.main(["--root", str(repo)]) == 1
    assert "problème" in capsys.readouterr().err