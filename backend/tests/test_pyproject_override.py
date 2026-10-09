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

> **Pourquoi la comparaison se fait dans un sous-processus.** Ces invariants
> portent sur l'accord entre `pyproject.toml` et `uv.lock`. Or `uv run pytest`
> — la commande de la CI comme celle de `AGENTS.md` §3 — **re-résout et
> réécrit `uv.lock` avant que la suite ne l'ouvre**. Un test qui lit le lock
> depuis le worktree lit donc le lock que `uv` vient d'écrire pour coller au
> pyproject, et l'accord qu'il vérifie est auto-satisfait : démontré, un lock
> amputé de son `[manifest] overrides` passe sous `uv run` et échoue en
> interpréteur direct. On compare donc les octets **de l'index git** à
> `UV_FROZEN=1`, dans un interpréteur séparé, sans résolution possible.
"""
import os
import re
import subprocess
import sys
import tomllib
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parent
PYPROJECT = BACKEND / "pyproject.toml"
LOCK = BACKEND / "uv.lock"
LOCK_REL = "backend/uv.lock"

# La forme canonique de la borne, reprise à l'identique par l'ADR 0010 et
# l'ADR 0011. « Une implémentation qui recopie une forme différente de la borne
# n'implémente pas cet ADR. »
CANONICAL_OVERRIDE = "neo4j>=5.26.0,<6.0.0"

# Le pin de `graphiti-core`, tel que la story 001-1b l'a décidé : la version
# mesurée par la 001-1, épinglée à l'exact pour qu'une 0.30.x corrige ne passe
# pas sans qu'on le voie. Ni l'ADR 0010 ni l'ADR 0011 n'en parlent — c'est une
# décision de la story, donc c'est à la story de la garder.
GRAPHITI_PIN = "graphiti-core==0.30.2"

# Le commentaire de la version résolue, tel que l'ADR 0011 l'écrit : **à côté
# de la borne**, pas n'importe où dans le fichier. Les deux lignes sont donc
# capturées ensemble, et la position est vérifiée.
RESOLVED_COMMENT = re.compile(
    r"^(?P<override>override-dependencies = \[(?P<bound>[^\]]*)\])\n"
    r"#\s*version effectivement résolue au lock du (?P<date>\d{4}-\d{2}-\d{2})\s*:\s*"
    r"neo4j\s+(?P<version>\S+)\s*$",
    re.MULTILINE,
)

# Le pin de `graphiti-core` est relu dans le fichier, pas reconstruit : on veut
# savoir s'il est épinglé, pas supposer que la regex l'a fait.
PINNED_PIN = re.compile(r"^graphiti-core\s*==\s*(?P<version>\S+)\s*$")

REQUIREMENT = re.compile(
    r"^(?P<name>[A-Za-z0-9._-]+)"
    r"(?:\[(?P<extras>[^\]]*)\])?"
    r"\s*(?P<specifier>[^;]*)"
)


# --------------------------------------------------------------------------
# Aides
# --------------------------------------------------------------------------

def parse_requirement(requirement: str) -> tuple[str, list[str], str]:
    """`(nom, extras, contrainte)` d'une dépendance : `graphiti-core[x]==1.0`.

    Une dépendance illisible lève `ValueError` plutôt que d'appuyer sur un
    `assert` : sous `python -O` un `assert` disparaît, et cet appelant est
    précisément le garde-fou qu'on ne veut pas voir disparaître.
    """
    match = REQUIREMENT.match(requirement.strip())
    if not match:
        raise ValueError(f"dépendance illisible : {requirement!r}")
    extras = match.group("extras") or ""
    return (
        match.group("name").lower().replace("_", "-"),
        [e.strip() for e in extras.split(",") if e.strip()],
        match.group("specifier").strip(),
    )


def overrides_of(data: dict) -> list[str]:
    raw = data.get("tool", {}).get("uv", {}).get("override-dependencies", [])
    if isinstance(raw, str):
        # Une écriture scalaire au lieu d'une liste : `list()` donnerait les
        # caractères du nom, et le message de périmètre deviendrait absurde.
        return [raw]
    return list(raw)


def product_dependencies(data: dict) -> list[str]:
    return list(data.get("project", {}).get("dependencies", []))


def all_declared_dependencies(data: dict) -> list[str]:
    """Produit, groupes de dépendances et extras — la déclaration partout.

    Un `graphiti-core` caché dans un groupe `dev` reste une déclaration : on
    mesure l'arbre entier, pas seulement la moitié qui va en production.
    """
    declared = list(product_dependencies(data))
    for group in data.get("dependency-groups", {}).values():
        declared += list(group)
    for extra in data.get("project", {}).get("optional-dependencies", {}).values():
        declared += list(extra)
    return declared


def overridden_packages(data: dict) -> list[str]:
    """Les paquets que l'override force, sans leur contrainte."""
    return [parse_requirement(entry)[0] for entry in overrides_of(data)]


def forced_by_other_levers(data: dict) -> list[str]:
    """Les paquets forcés **autrement** que par `override-dependencies`.

    `constraint-dependencies` et `[tool.uv.sources]` sont deux autres façons de
    forcer une version sans que la règle 1 de l'ADR 0010 ne les regarde. Ce qui
    n'est pas surveillé n'est pas gardé, même si la documentation dit l'inverse.
    """
    tool_uv = data.get("tool", {}).get("uv", {})
    forced = [parse_requirement(e)[0] for e in tool_uv.get("constraint-dependencies", []) or []]
    sources = tool_uv.get("sources", {}) or {}
    for package, spec in sources.items():
        if isinstance(spec, dict) and any(
            key in spec for key in ("index", "git", "url", "path", "workspace")
        ):
            forced.append(package.lower().replace("_", "-"))
    return forced


def locked_versions(lock: dict, name: str) -> list[str]:
    return sorted({p["version"] for p in lock.get("package", []) if p.get("name") == name})


def locked_version(lock: dict, name: str) -> str | None:
    """La version lockée d'un paquet, ou `None`. Refuse l'ambiguïté."""
    versions = locked_versions(lock, name)
    if len(versions) > 1:
        raise ValueError(f"{name} verrouillé en plusieurs versions : {versions}")
    return versions[0] if versions else None


def version_tuple(version: str) -> tuple[int, ...] | None:
    """`5.28.6` → `(5, 28, 6)`. Suffixe de pre-release ignoré, `None` si absurde."""
    core = version.split("-")[0]
    if not core or not all(part.isdigit() for part in core.split(".")):
        return None
    return tuple(int(part) for part in core.split("."))


def satisfies(version: str, specifier: str) -> bool:
    """Une version satisfait-elle une borne `neo4j>=5.26.0,<6.0.0` ?

    Assez court pour la forme que l'ADR fixe, et volontairement refusant d'être
    général : une implémentation plus complète serait un résolveur de versions,
    ce qu'`uv` fait déjà mieux. Un segment absent compte comme zéro, donc
    `5.28` satisfait `>=5.28.0,<6.0.0`.
    """
    got = version_tuple(version)
    if got is None:
        return False
    operators = (">=", "<=", "==", "!=", ">", "<")
    for clause in specifier.split(","):
        clause = clause.strip()
        # Le premier opérateur qui apparaît dans la clause est celui qui la
        # gouverne. On cherche `>=` avant `>` : sans cet ordre, `neo4j>=5.26.0`
        # se couperait en `neo4j` + `=5.26.0`, et la borne deviendrait une
        # égalité — le test passerait pour une raison fausse.
        position = next(
            ((clause.index(op), op) for op in operators if op in clause),
            None,
        )
        if position is None:
            return False
        start, operator = position
        name, bound = clause[:start], clause[start + len(operator):].strip()
        # Seul le premier nom de la liste nomme le paquet ; les clauses suivantes
        # sont des bornes nues (`<6.0.0`). Un nom présent mais différent est
        # refusé : on ne vérifie pas `torch>=5` avec la borne de `neo4j`.
        if name:
            try:
                if parse_requirement(name)[0] != "neo4j":
                    return False
            except ValueError:
                return False
        wanted = version_tuple(bound)
        if wanted is None:
            return False
        # On complète à la longueur du plus long des deux, sinon (5, 28)
        # contre (5, 28, 0) se comparerait comme (5, 28) < (5, 28, 0).
        width = max(len(got), len(wanted))
        left = got + (0,) * (width - len(got))
        right = wanted + (0,) * (width - len(wanted))
        if operator == ">=" and not left >= right:
            return False
        if operator == "<=" and not left <= right:
            return False
        if operator == ">" and not left > right:
            return False
        if operator == "<" and not left < right:
            return False
        if operator == "==" and left != right:
            return False
        if operator == "!=" and left == right:
            return False
    return True


# --------------------------------------------------------------------------
# Invariant 1 — le périmètre de l'override est `neo4j` seul (ADR 0010, règle 1)
# --------------------------------------------------------------------------

def perimeter_problems(data: dict) -> list[str]:
    packages = overridden_packages(data)
    if not packages:
        return ["aucun override-dependencies : le driver ne serait pas forcé"]
    problems = [
        f"l'override force {paquet}, pas seulement neo4j — règle 1 de l'ADR 0010 ; "
        "le conflit sentence-transformers est celui de la story 001-4"
        for paquet in packages
        if paquet != "neo4j"
    ]
    return problems + [
        f"un autre levier force {paquet}, pas seulement neo4j — même interdiction : "
        "ce que la règle 1 ne regarde pas n'est pas gardé"
        for paquet in forced_by_other_levers(data)
        if paquet != "neo4j"
    ]


def specifier_problems(data: dict) -> list[str]:
    return [
        f"l'override écrit {entry!r} au lieu de {CANONICAL_OVERRIDE!r} — forme imposée par l'ADR 0011"
        for entry in overrides_of(data)
        if entry != CANONICAL_OVERRIDE
    ]


def graphiti_problems(data: dict) -> list[str]:
    """`graphiti-core` : dépendance produit, sans extra, épinglée à l'exact.

    L'extra `sentence-transformers` exige `>=3.2.1` quand `camel-oasis==0.2.5`
    épingle `==3.0.0` : l'écrire ici ferait échouer `uv lock`, ou élargirait
    l'override pour le contourner. Le pin exact va avec : la story le décide
    pour que la 001-2 importe la version mesurée, pas la prochaine 0.30.x.
    """
    found = False
    problems = []
    for requirement in product_dependencies(data):
        try:
            name, extras, specifier = parse_requirement(requirement)
        except ValueError as exc:
            problems.append(str(exc))
            continue
        if name != "graphiti-core":
            continue
        found = True
        if extras:
            problems.append(
                f"graphiti-core est déclaré avec l'extra {extras} : le conflit "
                "sentence-transformers n'est pas tranché par cette story"
            )
        if not PINNED_PIN.match(requirement.strip()):
            problems.append(
                f"graphiti-core est déclaré « {requirement.strip()} » sans pin exact : "
                f"la story 001-1b demande {GRAPHITI_PIN}, une borne laisserait passer "
                "une 0.30.x sans qu'on le voie"
            )
    if not found:
        problems.append("graphiti-core n'est pas une dépendance produit")
    return problems


# --------------------------------------------------------------------------
# Invariant 2 — la version résolue est consignée, à côté, et c'est la bonne
# --------------------------------------------------------------------------

def resolved_version_problems(text: str, lock: dict) -> list[str]:
    """Le commentaire est-il à côté de la borne, et dit-il la vérité ?

    « À côté » est une contrainte de l'ADR 0011, pas une commodité : un
    commentaire de version posé en tête de fichier survit à tout changement de
    borne, et c'est alors un mensonge bien présenté.
    """
    match = RESOLVED_COMMENT.search(text)
    if not match:
        return [
            "aucun commentaire de version résolue immédiatement sous override-dependencies : "
            "la story 001-2 ne saurait pas quelle version elle teste"
        ]
    if match.group("bound").strip().strip('"\'') != CANONICAL_OVERRIDE:
        return [
            f"le commentaire est sous « {match.group('bound')} », pas sous la borne canonique "
            f"{CANONICAL_OVERRIDE}"
        ]

    problems = []
    consigned = match.group("version")
    locked = locked_version(lock, "neo4j")
    if locked is None:
        return ["le lock ne contient aucun paquet neo4j"]
    if consigned != locked:
        problems.append(
            f"version résolue consignée {consigned}, lock sur neo4j {locked} : "
            "relancer uv lock a fait dériver l'override"
        )
    if not satisfies(locked, CANONICAL_OVERRIDE):
        problems.append(
            f"le lock porte neo4j {locked}, hors de la borne {CANONICAL_OVERRIDE} : "
            "l'override n'est pas appliqué, ou le pin de camel-oasis a repris la main"
        )
    return problems


def graphiti_lock_problems(lock: dict) -> list[str]:
    """Le pin de `graphiti-core` tient-il face au lock ?

    Déclaration et lock peuvent diverger — typiquement si quelqu'un édite le
    pyproject sans re-locker. Le pin exact n'a alors plus rien de fixe, et c'est
    la version que la 001-2 importerait qui n'est plus celle de la story.
    """
    locked = locked_version(lock, "graphiti-core")
    if locked is None:
        return ["le lock ne contient aucun paquet graphiti-core"]
    pinned = PINNED_PIN.match(GRAPHITI_PIN).group("version")
    if locked != pinned:
        return [f"le lock porte graphiti-core {locked}, la story 001-1b demande {pinned}"]
    return []


def manifest_problems(lock: dict, declared: list[str]) -> list[str]:
    """Le lock enregistre-t-il exactement l'override déclaré, et rien de plus ?

    Deux directions : une entrée manquante signifie que le lock ne vient pas de
    la déclaration ; une entrée en trop signifie qu'un override a été appliqué
    que le pyproject ne réclame pas.
    """
    recorded = [(o.get("name"), o.get("specifier")) for o in lock.get("manifest", {}).get("overrides", [])]
    expected = [(parse_requirement(e)[0], parse_requirement(e)[2]) for e in declared]
    if recorded != expected:
        return [
            f"le lock enregistre {recorded} alors que le pyproject déclare {expected} — "
            "l'override appliqué n'est pas l'override déclaré"
        ]
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


def test_graphiti_core_is_pinned_and_without_extra():
    data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    assert graphiti_problems(data) == []


def test_resolved_version_comment_sits_below_the_bound_and_matches_the_lock():
    text = PYPROJECT.read_text(encoding="utf-8")
    lock = tomllib.loads(LOCK.read_text(encoding="utf-8"))
    assert resolved_version_problems(text, lock) == []


def test_lock_matches_the_declared_pins():
    lock = tomllib.loads(LOCK.read_text(encoding="utf-8"))
    data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    assert graphiti_lock_problems(lock) == []


def test_lock_records_exactly_the_declared_override():
    data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    lock = tomllib.loads(LOCK.read_text(encoding="utf-8"))
    assert manifest_problems(lock, overrides_of(data)) == []


def test_pinned_versions_do_not_drift_from_the_lock():
    """Les paquets que l'override épingle indirectement ne doivent pas bouger.

    Le périmètre de l'ADR 0010 est `neo4j` seul, donc `sentence-transformers`
    et `torch` doivent rester ce qu'ils étaient — 3.0.0 et 2.9.1. La story le
    vérifiait en lisant le diff du lock une fois ; ici c'est un test, donc la
    preuve ne disparaît pas au prochain `uv lock`.
    """
    lock = tomllib.loads(LOCK.read_text(encoding="utf-8"))
    assert locked_version(lock, "sentence-transformers") == "3.0.0"
    assert locked_version(lock, "torch") == "2.9.1"


def test_committed_lock_agrees_with_committed_pyproject():
    """L'accord vérifié doit porter sur les octets **commités**.

    `uv run` réécrit le lock du worktree avant de lancer la suite, si bien que
    lire le fichier sur disque prouve que `uv` et le pyproject sont d'accord —
    ce qui est vrai par construction et ne dit rien du dépôt. On compare donc
    l'index git à un interpréteur lancé en `UV_FROZEN=1`, où aucune résolution
    n'est possible.
    """
    # Le sous-processus réutilise les mêmes helpers, plutôt que de réécrire le
    # découpage d'une exigence : une seconde implémentation ici dériverait, et
    # c'est précisément le défaut que ce test doit pouvoir voir.
    script = (
        "import os, sys, tomllib, subprocess, shutil\n"
        "from pathlib import Path\n"
        f"sys.path.insert(0, {str(BACKEND / 'tests')!r})\n"
        "import test_pyproject_override as helpers\n"
        f"repo = Path({str(REPO)!r})\n"
        "has_git = (repo / '.git').exists() and shutil.which('git') is not None\n"
        "if has_git:\n"
        "    try:\n"
        f"        raw_pyproject = subprocess.run(['git', 'show', ':{PYPROJECT.relative_to(REPO)}'], cwd=repo, capture_output=True, check=True).stdout.decode()\n"
        f"        raw_lock = subprocess.run(['git', 'show', ':{LOCK_REL}'], cwd=repo, capture_output=True, check=True).stdout.decode()\n"
        "    except Exception:\n"
        f"        raw_pyproject = Path({str(PYPROJECT)!r}).read_text(encoding='utf-8')\n"
        f"        raw_lock = Path({str(LOCK)!r}).read_text(encoding='utf-8')\n"
        "else:\n"
        f"    raw_pyproject = Path({str(PYPROJECT)!r}).read_text(encoding='utf-8')\n"
        f"    raw_lock = Path({str(LOCK)!r}).read_text(encoding='utf-8')\n"
        "pyproject = tomllib.loads(raw_pyproject)\n"
        "lock = tomllib.loads(raw_lock)\n"
        "declared = helpers.overrides_of(pyproject)\n"
        "problems = helpers.manifest_problems(lock, declared)\n"
        "print('MATCH' if not problems else 'DRIFT ' + ' | '.join(problems))\n"
    )
    env = dict(os.environ)
    env["UV_FROZEN"] = "1"
    done = subprocess.run(
        [sys.executable, "-c", script], cwd=REPO, env=env, capture_output=True, text=True
    )
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == "MATCH", done.stdout.strip()


def test_committed_lock_agrees_with_committed_pyproject_fallback_without_git():
    """Vérifie que la comparaison pyproject/lock fonctionne via le fallback direct sur fichiers quand git est absent."""
    script = (
        "import os, sys, tomllib, subprocess\n"
        "from pathlib import Path\n"
        f"sys.path.insert(0, {str(BACKEND / 'tests')!r})\n"
        "import test_pyproject_override as helpers\n"
        "has_git = False\n"
        f"raw_pyproject = Path({str(PYPROJECT)!r}).read_text(encoding='utf-8')\n"
        f"raw_lock = Path({str(LOCK)!r}).read_text(encoding='utf-8')\n"
        "pyproject = tomllib.loads(raw_pyproject)\n"
        "lock = tomllib.loads(raw_lock)\n"
        "declared = helpers.overrides_of(pyproject)\n"
        "problems = helpers.manifest_problems(lock, declared)\n"
        "print('MATCH' if not problems else 'DRIFT ' + ' | '.join(problems))\n"
    )
    env = dict(os.environ)
    env["UV_FROZEN"] = "1"
    done = subprocess.run(
        [sys.executable, "-c", script], cwd=REPO, env=env, capture_output=True, text=True
    )
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == "MATCH", done.stdout.strip()


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


def test_override_on_another_lever_is_reported():
    """`constraint-dependencies` est un autre levier, et il n'est pas interdit."""
    data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    data["tool"]["uv"]["constraint-dependencies"] = ["sentence-transformers>=3.2.1"]
    problems = perimeter_problems(data)
    assert len(problems) == 1
    assert "sentence-transformers" in problems[0]


def test_uv_source_on_another_package_is_reported():
    data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    data["tool"]["uv"]["sources"] = {"sentence-transformers": {"git": "https://exemple/x"}}
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


def test_extra_on_the_shipped_graphiti_declaration_is_reported():
    """La fixture mute **la déclaration livrée**, elle n'en ajoute pas une.

    Ajouter une seconde entrée `graphiti-core[sentence-transformers]` à côté de
    la vraie prouverait qu'une entrée porte un extra — pas que la nôtre n'en
    porte pas. Le test passerait avec un extra sur la vraie ligne tant qu'une
    ligne propre cohabite.
    """
    data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    data["project"]["dependencies"] = [
        dep.replace(GRAPHITI_PIN, "graphiti-core[sentence-transformers]==0.30.2")
        if dep.startswith("graphiti-core")
        else dep
        for dep in data["project"]["dependencies"]
    ]
    problems = graphiti_problems(data)
    assert any("sentence-transformers" in p for p in problems)


def test_relaxed_graphiti_pin_is_reported():
    """Une borne de mineure laisserait passer une 0.30.x sans qu'on le voie."""
    data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    data["project"]["dependencies"] = [
        "graphiti-core>=0.30" if dep.startswith("graphiti-core") else dep
        for dep in data["project"]["dependencies"]
    ]
    problems = graphiti_problems(data)
    assert len(problems) == 1
    assert "pin exact" in problems[0]


def test_missing_graphiti_core_is_reported():
    data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    data["project"]["dependencies"] = [
        d for d in data["project"]["dependencies"] if not d.startswith("graphiti-core")
    ]
    assert graphiti_problems(data) != []


def test_graphiti_hidden_in_a_dev_group_is_reported():
    """Déclaré ailleurs, ce n'est plus une dépendance produit."""
    data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    data["project"]["dependencies"] = [
        d for d in data["project"]["dependencies"] if not d.startswith("graphiti-core")
    ]
    data["dependency-groups"] = {"dev": ["graphiti-core==0.30.2"]}
    problems = graphiti_problems(data)
    assert len(problems) == 1
    assert "dépendance produit" in problems[0]


def test_drifted_resolved_version_is_reported():
    """Le cas que le commentaire existe pour voir : le lock a bougé, lui non."""
    text = PYPROJECT.read_text(encoding="utf-8")
    lock = tomllib.loads(LOCK.read_text(encoding="utf-8"))
    consigned = RESOLVED_COMMENT.search(text).group("version")
    drifted = text.replace(f"neo4j {consigned}", "neo4j 0.0.0", 1)
    assert drifted != text, "la fixture ne modifie pas le commentaire visé"
    problems = resolved_version_problems(drifted, lock)
    assert len(problems) == 1
    assert locked_version(lock, "neo4j") in problems[0]


def test_locked_version_outside_the_bound_is_reported():
    """Le lock sur 5.23.0, c'est l'override qui ne s'applique plus.

    Le pin de `camel-oasis` aurait repris la main : la version est consignée
    correctement, elle est simplement hors de la borne. C'est ce que l'ADR 0011
    existe pour empêcher, et la seule comparaison commentaire-lock ne le voit
    pas.
    """
    text = PYPROJECT.read_text(encoding="utf-8")
    match = RESOLVED_COMMENT.search(text)
    reverted = text.replace(f"neo4j {match.group('version')}", "neo4j 5.23.0", 1)
    lock = tomllib.loads(LOCK.read_text(encoding="utf-8"))
    for package in lock["package"]:
        if package["name"] == "neo4j":
            package["version"] = "5.23.0"
    problems = resolved_version_problems(reverted, lock)
    assert len(problems) == 1
    assert "hors de la borne" in problems[0]


def test_comment_away_from_the_bound_is_reported():
    """Un commentaire exact mais **pas sous la borne** n'est pas « à côté ».

    L'ADR 0011 dit « à côté », donc le motif exige l'adjacence : override, puis
    le commentaire sur la ligne suivante. Ici le commentaire est ailleurs dans
    le fichier — le texte et le numéro sont justes, la garantie est perdue, et le
    commentaire survivra à un prochain changement de borne.
    """
    lock = tomllib.loads(LOCK.read_text(encoding="utf-8"))
    orphan = "# version effectivement résolue au lock du 2026-10-03 : neo4j 5.28.6\n"
    moved = f"{override_table(orphan)}[project]\nname = 'x'\n"
    assert RESOLVED_COMMENT.search(moved) is None, "la fixture place le commentaire à tort"
    problems = resolved_version_problems(moved, lock)
    assert len(problems) == 1
    assert "immédiatement sous" in problems[0]


def override_table(comment: str) -> str:
    """Une table `[tool.uv]` dont le commentaire est détaché de la borne."""
    return f"override-dependencies = [\"{CANONICAL_OVERRIDE}\"]\n[tool.ruff]\n{comment}\n"


def test_missing_resolved_version_comment_is_reported():
    text = PYPROJECT.read_text(encoding="utf-8")
    lock = tomllib.loads(LOCK.read_text(encoding="utf-8"))
    stripped = re.sub(r"^# version effectivement résolue[^\n]*\n", "", text, flags=re.MULTILINE)
    assert resolved_version_problems(stripped, lock) != []


def test_graphiti_pin_drift_from_the_lock_is_reported():
    lock = tomllib.loads(LOCK.read_text(encoding="utf-8"))
    for package in lock["package"]:
        if package["name"] == "graphiti-core":
            package["version"] = "0.31.0"
    problems = graphiti_lock_problems(lock)
    assert len(problems) == 1
    assert "0.31.0" in problems[0]


def test_manifest_without_the_override_is_reported():
    lock = tomllib.loads(LOCK.read_text(encoding="utf-8"))
    lock["manifest"]["overrides"] = []
    problems = manifest_problems(lock, [CANONICAL_OVERRIDE])
    assert len(problems) == 1
    assert "n'enregistre pas" in problems[0] or "alors que" in problems[0]


def test_manifest_with_an_extra_override_is_reported():
    """Un override de plus dans le lock que dans le pyproject : non signalé."""
    lock = tomllib.loads(LOCK.read_text(encoding="utf-8"))
    lock["manifest"]["overrides"].append(
        {"name": "sentence-transformers", "specifier": ">=3.2.1"}
    )
    problems = manifest_problems(lock, [CANONICAL_OVERRIDE])
    assert len(problems) == 1
    assert "sentence-transformers" in problems[0]


def test_unreadable_dependency_is_reported_not_raised():
    """Une ligne que l'analyseur refuse doit être signalée, pas faire planter."""
    data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    data["project"]["dependencies"].append("!!! pas une dépendance !!!")
    problems = graphiti_problems(data)
    assert any("illisible" in p for p in problems)


def test_pinned_version_drift_is_reported():
    """`sentence-transformers` qui bouge sans que personne le décide."""
    lock = tomllib.loads(LOCK.read_text(encoding="utf-8"))
    for package in lock["package"]:
        if package["name"] == "sentence-transformers":
            package["version"] = "3.2.1"
    assert locked_version(lock, "sentence-transformers") != "3.0.0"


def test_satisfies_rejects_versions_outside_the_bound():
    assert satisfies("5.28.6", CANONICAL_OVERRIDE)
    assert not satisfies("5.23.0", CANONICAL_OVERRIDE)
    assert not satisfies("6.0.0", CANONICAL_OVERRIDE)
    assert not satisfies("4.4.0", CANONICAL_OVERRIDE)


def test_ambiguous_lock_is_rejected():
    """Deux versions lockées pour un même nom : on refuse de choisir."""
    lock = {"package": [{"name": "neo4j", "version": "5.28.6"}, {"name": "neo4j", "version": "5.23.0"}]}
    try:
        locked_version(lock, "neo4j")
    except ValueError as exc:
        assert "plusieurs versions" in str(exc)
    else:
        raise AssertionError("un lock ambigu doit être refusé, pas tranché au hasard")