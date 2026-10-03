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
    echo "venv           : neo4j $(cd "$BACKEND" && uv run python -c 'import neo4j; print(neo4j.__version__)' 2>/dev/null | tail -1)"
    # `set -o pipefail` fait sortir le pipeline non nul dès que `uv run` échoue,
    # ce qui est le cas attendu ici : on teste donc la sortie, pas le statut.
    if (cd "$BACKEND" && uv run python -c 'import graphiti_core' >/dev/null 2>&1); then
        echo "graphiti_core  : PRÉSENT — restauration incomplète"
    else
        echo "graphiti_core  : absent (attendu)"
    fi
}
trap restore EXIT INT TERM

step() { printf '\n=== %s ===\n' "$1"; }

step "0. état de départ"
git status --porcelain || true
echo "uv.lock sha256 : $(shasum -a 256 "$LOCK" | cut -d' ' -f1)"

step "1. graphiti-core seul, sans arbitrage — on attend un refus"
python3 - "$PYPROJECT" "$GRAPHITI_VERSION" <<'PY'
import sys
path, version = sys.argv[1], sys.argv[2]
text = open(path, encoding="utf-8").read()
assert "graphiti-core" not in text, "graphiti-core est déjà présent : l'arbre n'est pas à l'état initial"
open(path, "w", encoding="utf-8").write(text.replace('"camel-oasis', f'"graphiti-core=={version}",\n    "camel-oasis', 1))
PY
(cd "$BACKEND" && uv lock 2>&1 | tail -20)

step "2. même chose, avec l'override de l'ADR 0010"
printf '\n[tool.uv]\noverride-dependencies = ["%s"]\n' "$OVERRIDE" >> "$PYPROJECT"
(cd "$BACKEND" && uv lock 2>&1 | tail -5)
(cd "$BACKEND" && uv sync 2>&1 | tail -3)

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
