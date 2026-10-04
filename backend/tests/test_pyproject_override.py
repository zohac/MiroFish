"""Garde-fou de l'`override-dependencies` posé par la story 001-1b.

L'ADR 0010 impose deux choses qu'aucun outil ne vérifie à la résolution :

1. **le périmètre de l'override est `neo4j` seul** (règle 1). Le conflit
   `sentence-transformers==3.0.0` contre `>=3.2.1` est de même nature mais
   n'est pas tranché — c'est la story 001-4. Élargir l'override reviendrait à
   trancher cette story sans le dire, et rien ne le signalerait : `uv lock`
   résoudrait sans bruit ;
2. **la version résolue est consignée à côté de la borne** (ADR 0011). La borne
   est une plage, elle se résout sur la dernière 5.x au jour du lock ; sans
   commentaire, la story 001-2 testerait une version qui n'est pas celle qui
   part en production.

Ces tests lisent le **vrai** `backend/pyproject.toml` et le **vrai**
`backend/uv.lock` — sur le modèle de `test_real_repo_is_valid`. Les tests
négatifs les rejouent sur des copies mutées : un garde-fou qu'on n'a jamais vu
échouer n'est pas un garde-fou.
"""

import re
import tomllib
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
PYPROJECT = BACKEND / "pyproject.toml"
LOCK = BACKEND / "uv.lock"

# La forme canonique de la borne, reprise à l'identique par l'ADR 0010 et
# l'ADR 0011. « Une implémentation qui recopie une forme différente de la borne
# n'implémente pas cet ADR. »
CANONICAL_OVERRIDE = "neo4j>=5.26.0,<6.0.0"

# Le commentaire de la version résolue, tel que l'ADR 0011 l'écrit.
RESOLVED_COMMENT = re.compile(
    r"^#\s*version effectivement résolue au lock du (?P<date>\d{4}-\d{2}-\d{2})\s*:\s*"
    r"neo4j\s+(?P<version>\S+)\s*$",
    re.MULTILINE,
)

REQUIREMENT = re.compile(
    r"^\s*(?P<name>[A-Za-z0-9._-]+)(?:\[(?P<extras>[^\]]*)\])?\s*(?P<specifier>[^;]*)"
)


# --------------------------------------------------------------------------
# Aides
# --------------------------------------------------------------------------

def parse_requirement(requirement: str) -> tuple[str, list[str]]:
    """`(nom, extras)` d'une dépendance déclarée : `graphiti-core[x]==1.0`."""
    match = REQUIREMENT.match(requirement)
    assert match, f"dépendance illisible : {requirement!r}"
    extras = match.group("extras") or ""
    return match.group("name").lower(), [e.strip() for e in extras.split(",") if e.strip()]


def overrides_of(data: dict) -> list[str]:
    return list(data.get("tool", {}).get("uv", {}).get("override-dependencies", []))


def product_dependencies(data: dict) -> list[str]:
    return list(data.get("project", {}).get("dependencies", []))


def overridden_packages(data: dict) -> list[str]:
    """Les paquets que l'override force, sans leur contrainte."""
    return [parse_requirement(entry)[0] for entry in overrides_of(data)]


def locked_neo4j_version(lock: dict) -> str | None:
    for package in lock.get("package", []):
        if package.get("name") == "neo4j":
            return package.get("version")
    return None


# --------------------------------------------------------------------------
# Invariant 1 — le périmètre de l'override est `neo4j` seul (ADR 0010, règle 1)
# --------------------------------------------------------------------------

def perimeter_problems(data: dict) -> list[str]:
    packages = overridden_packages(data)
    if not packages:
        return ["aucun override-dependencies : le driver ne serait pas forcé"]
    return [
        f"l'override force {paquet}, pas seulement neo4j — règle 1 de l'ADR 0010 ; "
        "le conflit sentence-transformers est celui de la story 001-4"
        for paquet in packages
        if paquet != "neo4j"
    ]


def specifier_problems(data: dict) -> list[str]:
    return [
        f"l'override écrit {entry!r} au lieu de {CANONICAL_OVERRIDE!r} — forme imposée par l'ADR 0011"
        for entry in overrides_of(data)
        if entry != CANONICAL_OVERRIDE
    ]


def graphiti_problems(data: dict) -> list[str]:
    """`graphiti-core` doit être une dépendance produit, sans extra.

    L'extra `sentence-transformers` exige `>=3.2.1` quand `camel-oasis==0.2.5`
    épingle `==3.0.0` : l'écrire ici ferait échouer `uv lock`, ou élargirait
    l'override pour le contourner.
    """
    found = False
    problems = []
    for requirement in product_dependencies(data):
        name, extras = parse_requirement(requirement)
        if name != "graphiti-core":
            continue
        found = True
        if extras:
            problems.append(
                f"graphiti-core est déclaré avec l'extra {extras} : le conflit "
                "sentence-transformers n'est pas tranché par cette story"
            )
    if not found:
        problems.append("graphiti-core n'est pas une dépendance produit")
    return problems


# --------------------------------------------------------------------------
# Invariant 2 — la version résolue est consignée, et elle est la bonne (ADR 0011)
# --------------------------------------------------------------------------

def resolved_version_problems(text: str, lock: dict) -> list[str]:
    match = RESOLVED_COMMENT.search(text)
    if not match:
        return [
            "aucun commentaire de version résolue à côté de l'override : "
            "la story 001-2 ne saurait pas quelle version elle teste"
        ]
    problems = []
    consigned = match.group("version")
    locked = locked_neo4j_version(lock)
    if locked is None:
        problems.append("le lock ne contient aucun paquet neo4j")
    elif consigned != locked:
        problems.append(
            f"version résolue consignée {consigned}, lock sur neo4j {locked} : "
            "relancer uv lock a fait dériver l'override"
        )
    return problems


def manifest_problems(lock: dict) -> list[str]:
    """Le lock doit avoir enregistré l'override, pas seulement le pyproject."""
    overrides = lock.get("manifest", {}).get("overrides", [])
    recorded = [(o.get("name"), o.get("specifier")) for o in overrides]
    if ("neo4j", ">=5.26.0,<6.0.0") not in recorded:
        return [f"le lock n'enregistre pas l'override de l'ADR 0010 : {recorded}"]
    return []


# --------------------------------------------------------------------------
# Le dépôt réel doit être conforme
# --------------------------------------------------------------------------

def test_override_targets_neo4j_only():
    data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    assert perimeter_problems(data) == []


def test_override_uses_the_canonical_specifier():
    data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    assert specifier_problems(data) == []


def test_graphiti_core_is_a_product_dependency_without_extra():
    data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    assert graphiti_problems(data) == []


def test_resolved_version_comment_matches_the_lock():
    text = PYPROJECT.read_text(encoding="utf-8")
    lock = tomllib.loads(LOCK.read_text(encoding="utf-8"))
    assert resolved_version_problems(text, lock) == []


def test_lock_records_the_override():
    lock = tomllib.loads(LOCK.read_text(encoding="utf-8"))
    assert manifest_problems(lock) == []


# --------------------------------------------------------------------------
# Négatifs — vérifier que les tests ci-dessus testent quelque chose
# --------------------------------------------------------------------------

def test_wider_override_is_reported():
    """Le saut que la règle 1 interdit : ajouter sentence-transformers."""
    data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    data["tool"]["uv"]["override-dependencies"] = [
        CANONICAL_OVERRIDE,
        "sentence-transformers>=3.2.1",
    ]
    problems = perimeter_problems(data)
    assert len(problems) == 1
    assert "sentence-transformers" in problems[0]


def test_missing_override_is_reported():
    data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    del data["tool"]["uv"]["override-dependencies"]
    assert perimeter_problems(data) != []


def test_other_specifier_is_reported():
    """Une borne recopiée autrement n'implémente pas l'ADR 0011."""
    data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    data["tool"]["uv"]["override-dependencies"] = ["neo4j>=5.26.0"]
    assert specifier_problems(data) != []


def test_extra_on_graphiti_core_is_reported():
    data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    data["project"]["dependencies"].append("graphiti-core[sentence-transformers]>=0.30.0")
    problems = graphiti_problems(data)
    assert len(problems) == 1
    assert "sentence-transformers" in problems[0]


def test_missing_graphiti_core_is_reported():
    data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    data["project"]["dependencies"] = [
        d for d in data["project"]["dependencies"] if not d.startswith("graphiti-core")
    ]
    assert graphiti_problems(data) != []


def test_drifted_resolved_version_is_reported():
    """Le cas que le commentaire existe pour voir : le lock a bougé, lui non."""
    text = PYPROJECT.read_text(encoding="utf-8")
    lock = tomllib.loads(LOCK.read_text(encoding="utf-8"))
    consigned = RESOLVED_COMMENT.search(text).group("version")
    drifted = text.replace(f"neo4j {consigned}", "neo4j 0.0.0")
    assert drifted != text, "la fixture ne modifie pas le commentaire visé"
    problems = resolved_version_problems(drifted, lock)
    assert len(problems) == 1
    assert locked_neo4j_version(lock) in problems[0]


def test_missing_resolved_version_comment_is_reported():
    text = PYPROJECT.read_text(encoding="utf-8")
    lock = tomllib.loads(LOCK.read_text(encoding="utf-8"))
    stripped = RESOLVED_COMMENT.sub("", text)
    assert resolved_version_problems(stripped, lock) != []