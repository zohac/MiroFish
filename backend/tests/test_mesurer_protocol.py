"""Harnais : la vraie `rewrite_pyproject`, sur des arbres qui doivent être refusés.

Le protocole de mesure est un script bash ; ses garde-fou vivent dans un heredoc
Python. Ce harnais l'**extrait du vrai fichier** — il ne le réimplémente pas, une
seconde implémentation dériverait, et c'est précisément ce qu'on veut vérifier —
puis l'appelle sur des `pyproject.toml` fabriqués.

Un garde-fou qu'on n'a jamais vu échouer n'est pas un garde-fou : chaque cas
ci-dessous doit être **refusé**, et le refus doit nommer la cause.
"""

import re
import subprocess
import sys
import tomllib
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parent
SCRIPT = REPO / "docs/plans/001-epreuve-graphiti-local/mesurer-001-1.sh"
SHIPPED = BACKEND / "pyproject.toml"

# La borne que l'ADR 0010 fixe, et que le protocole doit reproduire à l'identique.
CANONICAL = "neo4j>=5.26.0,<6.0.0"


def _rewrite_function() -> str:
    """Le corps de `rewrite_pyproject`, extrait du script réel."""
    text = SCRIPT.read_text(encoding="utf-8")
    match = re.search(r"^rewrite_pyproject\(\) \{$.*?^\}$", text, re.MULTILINE | re.DOTALL)
    assert match, "rewrite_pyproject est introuvable dans le protocole"
    return match.group(0)


def _harness(tmp_path: Path, pyproject: str, mode: str = "override") -> tuple[int, str]:
    """Exécute la vraie fonction sur un `pyproject.toml` fabriqué."""
    target = tmp_path / "pyproject.toml"
    target.write_text(pyproject, encoding="utf-8")
    script = tmp_path / "run.sh"
    script.write_text(
        "set -uo pipefail\n"
        "GRAPHITI_VERSION=0.30.2\n"
        f"PYPROJECT={str(target)!r}\n"
        f"{_rewrite_function()}\n"
        f'rewrite_pyproject "{mode}"\n',
        encoding="utf-8",
    )
    done = subprocess.run(
        ["bash", str(script)], capture_output=True, text=True, check=False
    )
    return done.returncode, (done.stdout + done.stderr)


def _base() -> str:
    return SHIPPED.read_text(encoding="utf-8")


# --------------------------------------------------------------------------
# Le cas nominal : la vraie fonction produit exactement l'état mesuré
# --------------------------------------------------------------------------

def test_override_branch_produces_the_measured_state(tmp_path):
    code, output = _harness(tmp_path, _base())
    assert code == 0, output
    written = tomllib.loads((tmp_path / "pyproject.toml").read_text(encoding="utf-8"))
    assert written["tool"]["uv"]["override-dependencies"] == [CANONICAL]
    declared = [
        d
        for d in written["project"]["dependencies"]
        if d.split("=")[0].strip() == "graphiti-core"
    ]
    assert declared == ["graphiti-core==0.30.2"]


def test_inserted_declaration_keeps_the_indentation_of_its_neighbour(tmp_path):
    """L'indentation se prend sur la ligne visée, pas avant le dernier saut.

    Une insertion à la marge produit un pyproject valide — `uv` le résout sans
    protester — mais l'arbre mesuré n'est plus l'arbre du dépôt, et l'étape 6
    du protocole y lit un fichier que personne n'a relu. Vu pour la première fois
    parce que l'étape 6 lance cette suite sur l'arbre réécrit.
    """
    _code, _output = _harness(tmp_path, _base())
    lines = (tmp_path / "pyproject.toml").read_text(encoding="utf-8").splitlines()
    inserted = next(line for line in lines if line.lstrip().startswith('"graphiti-core'))
    camel = next(line for line in lines if line.lstrip().startswith('"camel-oasis'))
    assert inserted.startswith("    "), f"indentée à la marge : {inserted!r}"
    assert inserted[: len(inserted) - len(inserted.lstrip())] == (
        camel[: len(camel) - len(camel.lstrip())]
    )


def test_refus_branch_leaves_no_override(tmp_path):
    """L'état « refus » doit être l'arbre **sans** override — pas le même avec."""
    code, output = _harness(tmp_path, _base(), mode="refus")
    assert code == 0, output
    written = tomllib.loads((tmp_path / "pyproject.toml").read_text(encoding="utf-8"))
    assert "uv" not in written.get("tool", {}), written.get("tool", {}).get("uv")
    assert [
        d for d in written["project"]["dependencies"] if d.startswith("graphiti-core")
    ] == ["graphiti-core==0.30.2"]


# --------------------------------------------------------------------------
# Les refus — un arbre non mesuré doit être dit, pas réécrit
# --------------------------------------------------------------------------

def test_unknown_tool_uv_key_is_refused(tmp_path):
    """Un `index-url` survit à la réécriture : la mesure viserait un autre index."""
    altered = _base().replace(
        f'override-dependencies = ["{CANONICAL}"]',
        f'override-dependencies = ["{CANONICAL}"]\nno-build = false',
    )
    code, output = _harness(tmp_path, altered)
    assert code != 0, "un [tool.uv] enrichi doit être refusé"
    assert "no-build" in output
    assert "index" in output or "sources" in output or "mesure" in output


def test_duplicate_graphiti_declaration_is_refused(tmp_path):
    altered = _base().replace(
        '    "graphiti-core==0.30.2",\n',
        '    "graphiti-core==0.30.2",\n    "graphiti-core==0.29.0",\n',
    )
    code, output = _harness(tmp_path, altered)
    assert code != 0, "deux déclarations graphiti-core sont ambiguës"
    assert "2 fois" in output


def test_missing_camel_oasis_is_refused(tmp_path):
    altered = re.sub(r'^[ \t]*"camel-oasis[^\n]*\n', "", _base(), flags=re.MULTILINE)
    code, output = _harness(tmp_path, altered)
    assert code != 0
    assert "camel-oasis" in output


def test_unparseable_pyproject_is_refused(tmp_path):
    code, output = _harness(tmp_path, _base() + "\n[tool.uv\n")
    assert code != 0
    assert "parse" in output or "invalide" in output


def test_unknown_mode_is_refused(tmp_path):
    """Un mode mal orthographié ne doit pas mesurer la branche « refus »."""
    before = _base()
    code, output = _harness(tmp_path, before, mode="overide")
    assert code != 0
    assert "mode inconnu" in output
    assert code == 2, "le refus d'un mode doit être net, pas un code d'échec opaque"
    # L'arbre ne doit pas avoir bougé : un refus qui écrit quand même ferait
    # perdre le travail de la mesure.
    assert (tmp_path / "pyproject.toml").read_text(encoding="utf-8") == before