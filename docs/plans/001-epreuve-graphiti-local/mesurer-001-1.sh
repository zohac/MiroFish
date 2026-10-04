#!/usr/bin/env bash
# Protocole de mesure de la story 001-1 — rejouable à l'identique (NFR-3).
#
# Mesure une seule chose : `graphiti-core` et `camel-oasis` peuvent-ils
# cohabiter dans un même venv ? Le script ne conclut rien, il affiche. La
# lecture et le verdict sont dans `story-001-1.md` ; ici on ne trouve que la
# sortie brute, versionnée dans `mesure-001-1.txt`.
#
# Il ne doit rien laisser derrière lui : `pyproject.toml` et `uv.lock` sont
# sauvegardés au départ et restaurés par le trap, y compris si le script est
# interrompu. Le dépôt doit être propre avant de le lancer (`git status` vide),
# sans quoi la restauration écraserait du travail.
#
# ## Rejouabilité sur les deux arbres
#
# La story 001-1b pose l'`override-dependencies` de l'ADR 0010 dans
# `backend/pyproject.toml`. Ce protocole reste donc rejouable **sur les deux
# arbres** : avant le geste (ni `graphiti-core` ni override), et après (les deux
# présents). Pour cela il ne suppose plus l'état de l'arbre : il **normalise**
# `pyproject.toml` dans l'état qu'il veut mesurer, mesure, puis restaure l'octet
# initial. Ce qu'il refuse, c'est un arbre **ambigu** — un override d'un autre
# périmètre, ou un geste à moitié posé — qu'il ne devine pas.
#
# La constante `OVERRIDE` ci-dessous est celle de l'ADR 0010, reprise à
# l'identique par l'ADR 0011. Une implémentation qui en recopie une autre ne
# mesure pas la même chose.
#
# Usage, depuis `backend/` :
#     bash ../docs/plans/001-epreuve-graphiti-local/mesurer-001-1.sh | tee ../docs/plans/001-epreuve-graphiti-local/mesure-001-1.txt

set -uo pipefail

GRAPHITI_VERSION="${GRAPHITI_VERSION:-0.30.2}"
OVERRIDE='neo4j>=5.26.0,<6.0.0'

cd "$(dirname "$0")/../../.." || exit 1
ROOT=$(pwd)
BACKEND="$ROOT/backend"
PYPROJECT="$BACKEND/pyproject.toml"
LOCK="$BACKEND/uv.lock"
SITE=$(echo "$BACKEND"/.venv/lib/python*/site-packages)
SAVE=$(mktemp -d)

cp "$PYPROJECT" "$SAVE/pyproject.toml"
cp "$LOCK" "$SAVE/uv.lock"

# Ce que le venv contient **avant** que le script ne touche à quoi que ce soit.
# La restauration est jugée sur ces valeurs, pas sur des ».
# Le sync d'abord : après un `git checkout` des deux fichiers, le venv est
# encore celui de l'état précédent. Sans lui, l'attente porterait sur un venv
# fantôme — on a vu `graphiti_core` encore installé sur un lock qui ne l'a pas.
(cd "$BACKEND" && uv sync --frozen >/dev/null 2>&1)
EXPECT_NEO4J=$(cd "$BACKEND" && uv run python -c 'import neo4j; print(neo4j.__version__)' 2>/dev/null | tail -1)
if (cd "$BACKEND" && uv run python -c 'import graphiti_core' >/dev/null 2>&1); then
    EXPECT_GC="présent"
else
    EXPECT_GC="absent"
fi

restore() {
    cp "$SAVE/pyproject.toml" "$PYPROJECT"
    cp "$SAVE/uv.lock" "$LOCK"
    rm -rf "$SAVE"
    # Le venv aussi doit revenir : sans ce sync, l'override et `graphiti-core`
    # restent installés alors que les fichiers ont retrouvé leur état initial.
    (cd "$BACKEND" && uv sync --frozen >/dev/null 2>&1)
    echo "--- restauration ---"
    echo "pyproject.toml : $(shasum -a 256 "$PYPROJECT" | cut -c1-16)…"
    echo "uv.lock        : $(shasum -a 256 "$LOCK" | cut -c1-16)…"
    # `set -o pipefail` fait sortir le pipeline non nul dès que `uv run` échoue,
    # ce qui est le cas attendu sur l'arbre d'avant la 001-1 : on teste donc la
    # sortie, pas le statut.
    got_n=$(cd "$BACKEND" && uv run python -c 'import neo4j; print(neo4j.__version__)' 2>/dev/null | tail -1)
    if (cd "$BACKEND" && uv run python -c 'import graphiti_core' >/dev/null 2>&1); then
        got_gc="présent"
    else
        got_gc="absent"
    fi
    echo "venv           : neo4j ${got_n:-absent}"
    echo "graphiti_core  : ${got_gc}"
    if [ "$got_n" = "$EXPECT_NEO4J" ] && [ "$got_gc" = "$EXPECT_GC" ]; then
        echo "état           : identique au départ (neo4j ${EXPECT_NEO4J}, graphiti_core ${EXPECT_GC})"
    else
        echo "état           : ⚠️  INCOMPLET — attendu neo4j ${EXPECT_NEO4J}, graphiti_core ${EXPECT_GC}"
    fi
}
trap restore EXIT INT TERM

step() { printf '\n=== %s ===\n' "$1"; }

# ---------------------------------------------------------------------------
# Réécriture de pyproject.toml — toujours vers un état de mesure connu
# ---------------------------------------------------------------------------
# `refus`   : `graphiti-core` seule, sans override — le résolveur doit refuser.
# `override` : `graphiti-core` + l'override de l'ADR 0010 — le lock doit résoudre.
rewrite_pyproject() {
    python3 - "$PYPROJECT" "$GRAPHITI_VERSION" "$1" <<'PY'
import re
import sys
import tomllib

path, version, mode = sys.argv[1], sys.argv[2], sys.argv[3]
OVERRIDE = "neo4j>=5.26.0,<6.0.0"

text = open(path, encoding="utf-8").read()

# 1. Retirer toute table [tool.uv] : le protocole la repose lui-même. C'est ce
#    qui le rendait non rejouable — `>>` ajoutait une seconde table, et TOML
#    refuse « Cannot declare ('tool', 'uv') twice ».
kept, skipping = [], False
for line in text.splitlines(keepends=True):
    if skipping:
        if re.match(r"^\s*\[", line):
            skipping = False
        else:
            continue
    if re.match(r"^\[tool\.uv\]", line):
        skipping = True
        continue
    kept.append(line)
text = "".join(kept)

# 2. Retirer toute déclaration graphiti-core : le protocole la réinscrit à la
#    version qu'il mesure, quelle que soit celle déclarée dans l'arbre.
text = re.sub(r'^[ \t]*"graphiti-core[^"\n]*",?[ \t]*\n', "", text, flags=re.M)

# 3. La réinsérer, devant camel-oasis, comme la story 001-1 l'a fait.
needle = '"camel-oasis'
if needle not in text:
    sys.exit("pyproject.toml : la dépendance camel-oasis est introuvable")
text = text.replace(needle, f'"graphiti-core=={version}",\n    {needle}', 1)

# 4. Poser l'override, si on mesure le chemin « override ».
if mode == "override":
    text = text.rstrip("\n") + f'\n\n[tool.uv]\noverride-dependencies = ["{OVERRIDE}"]\n'

# Le fichier doit rester du TOML valide : un parseur qui passe, c'est la preuve
# que la réécriture n'a pas cassé la déclaration qu'elle voulait mesurer.
try:
    tomllib.loads(text)
except tomllib.TOMLDecodeError as exc:
    sys.exit(f"pyproject.toml : la réécriture a produit un TOML invalide — {exc}")

open(path, "w", encoding="utf-8").write(text)
print(f'graphiti-core=={version}' + (", [tool.uv] posé" if mode == "override" else ", pas d’override"))
PY
}

step "0. état de départ"
git status --porcelain || true
echo "uv.lock sha256 : $(shasum -a 256 "$LOCK" | cut -d' ' -f1)"
echo "venv au départ : neo4j ${EXPECT_NEO4J}, graphiti_core ${EXPECT_GC}"

# Quel arbre est-ce ? On l'affiche, et on refuse celui qu'on ne sait pas
# mesurer : deviner laisserait croire à une mesure qui n'a pas eu lieu.
STATE=$(python3 - "$PYPROJECT" "$OVERRIDE" <<'PY'
import sys
import tomllib

path, canonical = sys.argv[1], sys.argv[2]

try:
    with open(path, "rb") as fh:
        data = tomllib.load(fh)
except tomllib.TOMLDecodeError as exc:
    sys.exit(f"pyproject.toml ne se parse pas — arbre non mesurable : {exc}")

deps = data.get("project", {}).get("dependencies", [])
overrides = data.get("tool", {}).get("uv", {}).get("override-dependencies", [])
has_graphiti = any(d.split("[")[0].split("=")[0].strip() == "graphiti-core" for d in deps)

def refuse(reason):
    sys.exit(f"arbre ambigu, état refusé plutôt que deviné : {reason}")

if overrides and overrides != [canonical]:
    refuse(f"override {overrides} ≠ celui de l'ADR 0010 ({[canonical]})")
if has_graphiti and not overrides:
    refuse("graphiti-core est déclaré sans override — geste à moitié posé")
if overrides and not has_graphiti:
    refuse("override posé sans graphiti-core — geste à moitié posé")

# Le mot-clé seul sur stdout : le shell s'en sert pour choisir le libellé.
# Le pin va sur stderr, sinon il se retrouve dans la variable d'état.
print("override" if has_graphiti else "initial")
for dep in deps:
    if dep.startswith("graphiti-core"):
        print(f"pin de l'arbre : {dep}", file=sys.stderr)
PY
)
if [ -z "$STATE" ]; then
    echo
    echo "Protocole arrêté : l'arbre de départ n'est pas dans un état mesuré par ce script."
    exit 1
fi
case "$STATE" in
    initial)
        echo "état de l'arbre : AVANT la 001-1b — ni graphiti-core, ni override"
        ;;
    override)
        echo "état de l'arbre : APRÈS la 001-1b — graphiti-core + override de l'ADR 0010"
        ;;
esac
echo "dans les deux cas, la mesure porte sur le même couple de versions (voir étape 1)"

step "1. graphiti-core seule, sans arbitrage — on attend un refus"
rewrite_pyproject refus || exit 1
(cd "$BACKEND" && uv lock 2>&1 | tail -20)
# Un lock qui passe ici rendrait la mesure sans objet : le conflit ne serait pas
# celui qu'on croit. On le dit plutôt que de le laisser passer pour une preuve.
if (cd "$BACKEND" && uv lock --check >/dev/null 2>&1); then
    echo "⚠️  uv lock résout SANS l'override : le conflit ne se reproduit plus, la mesure ne prouve plus rien"
fi

step "2. même chose, avec l'override de l'ADR 0010"
rewrite_pyproject override || exit 1
(cd "$BACKEND" && uv lock 2>&1 | tail -5)
(cd "$BACKEND" && uv sync 2>&1 | tail -3)

# La version que la borne vient de résoudre est **consignée à côté d'elle**,
# comme l'impose l'ADR 0011. Sans cette ligne, l'arbre mesuré ne serait pas
# l'arbre que l'override décrit : le filet de tests de l'étape 6 lit ce
# commentaire, et la story 001-2 doit savoir quelle version elle teste.
LOCKED_NEO4J=$(basename "$(echo "$SITE"/neo4j-*.dist-info)" .dist-info | sed 's/^neo4j-//')
python3 - "$PYPROJECT" "$LOCKED_NEO4J" "$(date +%Y-%m-%d)" <<'PY' || exit 1
import re
import sys

path, version, day = sys.argv[1], sys.argv[2], sys.argv[3]
text = open(path, encoding="utf-8").read()
line = re.compile(
    r'^(override-dependencies = \[[^\]]*\])\n(?:# version effectivement résolue[^\n]*\n)?',
    re.MULTILINE,
)
comment = f"# version effectivement résolue au lock du {day} : neo4j {version}\n"
if not line.search(text):
    sys.exit("override-dependencies introuvable : la version résolue reste à consigner à la main")
open(path, "w", encoding="utf-8").write(line.sub(rf"\1\n{comment}", text, count=1))
print(f"version résolue consignée : neo4j {version}")
PY

step "3. ce que chacun des trois paquets exige du driver"
echo "borne déclarée   : $OVERRIDE"
echo "version lockée   : neo4j $(basename "$(echo "$SITE"/neo4j-*.dist-info)" .dist-info | sed 's/^neo4j-//')"
echo "exigences lues dans les METADATA installés :"
grep -rhoE "Requires-Dist: neo4j[^;]*" "$SITE"/*.dist-info/METADATA 2>/dev/null | sort -u | sed 's/^/  /'

step "4. imports dans l'ordre — camel-oasis, puis neo4j, puis graphiti_core"
(cd "$BACKEND" && uv run python -c "
import oasis, neo4j, graphiti_core
print('oasis         ok', oasis.__file__.rsplit('/', 2)[-2])
print('neo4j         ok', neo4j.__version__)
print('graphiti_core ok', graphiti_core.__name__)
" 2>&1 | tail -10)

step "5. surface du driver réellement utilisée par camel et oasis"
for symbol in 'neo4j.Version' 'GraphDatabase.driver' 'from neo4j import Query' 'neo4j.exceptions'; do
    count=$(grep -rIl "$symbol" "$SITE/camel" "$SITE/oasis" 2>/dev/null | wc -l | tr -d ' ')
    printf '%-24s %s fichier(s)\n' "$symbol" "$count"
done

step "6. filet de tests"
cd "$BACKEND" && uv run pytest tests/ -q 2>&1 | tail -3