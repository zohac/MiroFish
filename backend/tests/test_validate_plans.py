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


def _valid_story(story_id: str, epic: str, statut: str) -> str:
    return yaml.safe_dump(
        {
            "id": story_id,
            "titre": "Une story de test",
            "epic": epic,
            "statut": statut,
            "definition_of_ready": [{"ok": "critères écrits", "vrai": True}],
            "definition_of_done": ["tests verts"],
            "tasks": [{"id": 1, "titre": "faire un truc", "fait": statut in {"review", "done"}}],
            "notes_dev": {"architecture": "rien", "strategie_test": "rien"},
            "review": {"follow_ups": []},
            "completion_notes": [],
        },
        allow_unicode=True,
        sort_keys=False,
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """Un dépôt minimal mais conforme : les tests partent de là."""
    plan = tmp_path / "docs" / "plans" / "001-truc"
    _write(plan / "prd.md", "# PRD")
    _write(plan / "architecture.md", "# Architecture")
    _write(plan / "epic-001.md", "# Epic 001\n\n| 001-1 | story | `backlog` | story-001-1.yaml |")
    _write(plan / "story-001-1.yaml", _valid_story("001-1", "001", "backlog"))
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
    twin = dict(data["epics"][0])
    data["epics"].append(twin)
    _write(repo / "sprint-status.yaml", yaml.safe_dump(data, allow_unicode=True))
    problems = validate_plans.validate(repo)
    assert any("id dupliqué" in p for p in problems)


def test_story_id_must_match_filename(repo: Path):
    _write(repo / "docs/plans/001-truc/story-001-1.yaml", _valid_story("001-9", "001", "backlog"))
    problems = validate_plans.validate(repo)
    assert any("ne correspond pas au nom de fichier" in p for p in problems)


def test_story_epic_must_match_folder(repo: Path):
    _write(repo / "docs/plans/001-truc/story-001-1.yaml", _valid_story("001-1", "999", "backlog"))
    problems = validate_plans.validate(repo)
    assert any("dossier du plan" in p for p in problems)


def test_missing_required_field_is_reported(repo: Path):
    data = yaml.safe_load((repo / "docs/plans/001-truc/story-001-1.yaml").read_text())
    del data["notes_dev"]
    _write(repo / "docs/plans/001-truc/story-001-1.yaml",
           yaml.safe_dump(data, allow_unicode=True, sort_keys=False))
    problems = validate_plans.validate(repo)
    assert any("`notes_dev`" in p for p in problems)


# --------------------------------------------------------------------------
# Tâches
# --------------------------------------------------------------------------

def test_done_story_with_unchecked_task_is_reported(repo: Path):
    data = yaml.safe_load(_valid_story("001-1", "001", "done"))
    data["tasks"][0]["fait"] = False
    _write(repo / "docs/plans/001-truc/story-001-1.yaml",
           yaml.safe_dump(data, allow_unicode=True, sort_keys=False))
    _write(repo / "docs/plans/001-truc/epic-001.md", "# Epic 001\n\n001-1")
    problems = validate_plans.validate(repo)
    assert any("tâches non cochées" in p for p in problems)


def test_non_boolean_task_flag_is_reported(repo: Path):
    data = yaml.safe_load((repo / "docs/plans/001-truc/story-001-1.yaml").read_text())
    data["tasks"][0]["fait"] = "oui"
    _write(repo / "docs/plans/001-truc/story-001-1.yaml",
           yaml.safe_dump(data, allow_unicode=True, sort_keys=False))
    problems = validate_plans.validate(repo)
    assert any("doit être un booléen" in p for p in problems)


def test_empty_tasks_is_reported(repo: Path):
    data = yaml.safe_load((repo / "docs/plans/001-truc/story-001-1.yaml").read_text())
    data["tasks"] = []
    _write(repo / "docs/plans/001-truc/story-001-1.yaml",
           yaml.safe_dump(data, allow_unicode=True, sort_keys=False))
    problems = validate_plans.validate(repo)
    assert any("`tasks` attendu, non vide" in p for p in problems)


# --------------------------------------------------------------------------
# Le cœur de la règle : une story démarrée doit être traçable
# --------------------------------------------------------------------------

def test_started_story_must_be_cited_in_hub(repo: Path):
    _write(repo / "docs/plans/001-truc/story-001-1.yaml", _valid_story("001-1", "001", "in-progress"))
    _write(repo / "docs/plans/001-truc/epic-001.md", "# Epic 001\n\nrien à voir")
    problems = validate_plans.validate(repo)
    assert any("n'est pas citée dans" in p for p in problems)


def test_backlog_story_need_not_be_cited(repo: Path):
    _write(repo / "docs/plans/001-truc/epic-001.md", "# Epic 001\n\nrien à voir")
    assert validate_plans.validate(repo) == []


def test_story_without_file_is_allowed_while_backlog(repo: Path):
    data = yaml.safe_load((repo / "sprint-status.yaml").read_text())
    data["epics"][0]["statut"] = "backlog"
    del data["epics"][0]["plan"]
    _write(repo / "sprint-status.yaml", yaml.safe_dump(data, allow_unicode=True))
    (repo / "docs/plans/001-truc/story-001-1.yaml").unlink()
    assert validate_plans.validate(repo) == []


# --------------------------------------------------------------------------
# Robustesse
# --------------------------------------------------------------------------

def test_broken_yaml_is_reported_not_raised(repo: Path):
    _write(repo / "docs/plans/001-truc/story-001-1.yaml", "id: [non fermé")
    problems = validate_plans.validate(repo)
    assert any("YAML invalide" in p for p in problems)


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