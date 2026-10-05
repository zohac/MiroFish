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

# Le protocole exige Python 3.11+ pour `tomllib`, qui sert à refuser un
# pyproject illisible plutôt que de le réécrire à l'aveugle. Le python système du
# macOS est plus ancien : on le dit clairement au lieu de laisser un ImportError
# au milieu d'une étape.
if ! python3 -c 'import tomllib' 2>/dev/null; then
    echo "python 3.11 ou plus récent requis (tomllib absent) — python3 : $(python3 --version 2>&1)" >&2
    exit 1
fi

cd "$(dirname "$0")/../../.." || exit 1
ROOT=$(pwd)
BACKEND="$ROOT/backend"
PYPROJECT="$BACKEND/pyproject.toml"
LOCK="$BACKEND/uv.lock"
SITE=$(echo "$BACKEND"/.venv/lib/python*/site-packages)
SAVE=$(mktemp -d)

cp "$PYPROJECT" "$SAVE/pyproject.toml"
cp "$LOCK" "$SAVE/uv.lock"

# Le trap est posé **avant** le premier sync : un sync qui mute le venv suivi
# d'une interruption laisserait un venv modifié que rien ne restaure. Le script
# promet de ne rien laisser derrière lui — cette promesse doit survivre à un
# Ctrl-C entre deux étapes.

restore() {
    cp "$SAVE/pyproject.toml" "$PYPROJECT"
    cp "$SAVE/uv.lock" "$LOCK"
    rm -rf "$SAVE"
    # Le venv aussi doit revenir : sans ce sync, l'override et `graphiti-core`
    # restent installés alors que les fichiers ont retrouvé leur état initial.
    (cd "$BACKEND" && uv sync --locked >/dev/null 2>&1)
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
        RESTORED=1
    else
        # La restauration est la seule chose qui rend cette mesure crédible. On
        # l'annonce bruyamment, et on laisse un statut au shell appelant.
        echo "état           : ⚠️  INCOMPLET — attendu neo4j ${EXPECT_NEO4J}, graphiti_core ${EXPECT_GC}"
        echo
        echo "L'arbre est revenu dans ses fichiers, mais le venv ne correspond plus" >&2
        echo "à l'état de départ. Rejouer : cd backend && uv sync --locked" >&2
        RESTORED=0
    fi
}
trap restore EXIT INT TERM

# Ce que le venv contient **avant** que le script ne touche à quoi que ce soit.
# La restauration est jugée sur ces valeurs, pas sur une impression.
# Le sync d'abord : après un `git checkout` des deux fichiers, le venv est encore
# celui de l'état précédent. Sans lui, l'attente porterait sur un venv fantôme —
# on a vu `graphiti_core` encore installé sur un lock qui ne l'a pas.
(cd "$BACKEND" && uv sync --locked >/dev/null 2>&1)
EXPECT_NEO4J=$(cd "$BACKEND" && uv run python -c 'import neo4j; print(neo4j.__version__)' 2>/dev/null | tail -1)
# Un venv illisible ne doit pas passer pour un venv conforme : comparaison vide
# contre vide, le script conclurait « identique au départ » sur un fantôme.
if [ -z "$EXPECT_NEO4J" ]; then
    echo "venv illisible au départ (neo4j absent ?) — la mesure serait sans valeur" >&2
    exit 1
fi
if (cd "$BACKEND" && uv run python -c 'import graphiti_core' >/dev/null 2>&1); then
    EXPECT_GC="présent"
else
    EXPECT_GC="absent"
fi

step() { printf '\n=== %s ===\n' "$1"; }

# ---------------------------------------------------------------------------
# Réécriture de pyproject.toml — toujours vers un état de mesure connu
# ---------------------------------------------------------------------------
# `refus`   : `graphiti-core` seule, sans override — le résolveur doit refuser.
# `override` : `graphiti-core` + l'override de l'ADR 0010 — le lock doit résoudre.
rewrite_pyproject() {
    local mode="$1"
    # Un mode inconnu ne doit pas mesurer la branche « refus » en silence : le
    # script announce alors « override » alors qu'il n'a rien posé.
    case "$mode" in
        refus|override) ;;
        *)
            echo "mode inconnu : « $mode » (attendu : refus ou override)" >&2
            return 2
            ;;
    esac
    python3 - "$PYPROJECT" "$GRAPHITI_VERSION" "$mode" <<'PY'
import re
import sys
import tomllib

path, version, mode = sys.argv[1], sys.argv[2], sys.argv[3]
OVERRIDE = "neo4j>=5.26.0,<6.0.0"

text = open(path, encoding="utf-8").read()

# 1. Retirer toute table [tool.uv] : le protocole la repose lui-même. C'est ce
#    qui le rendait non rejouable — `>>` ajoutait une seconde table, et TOML
#    refuse alors de déclarer deux fois la même table `tool.uv`.
#
#    Une table qui porte d'autres clés (`index-url`, `sources`, `no-build`,
#    `required-version`…) serait **supprimée sans bruit**, et la mesure se ferait
#    alors contre un index différent de celui de la production : le protocole
#    afficherait un résultat qui ne correspond à rien de déployable. On refuse
#    donc un `[tool.uv]` qui ne contient pas *uniquement* l'override — le refus
#    vaut mieux qu'une mesure fausse, silencieuse et reproductible.
try:
    original = tomllib.loads(text)
except tomllib.TOMLDecodeError as exc:
    sys.exit(f"pyproject.toml ne se parse pas — arbre non mesurable : {exc}")
uv_table = original.get("tool", {}).get("uv", {})
unknown = set(uv_table) - {"override-dependencies"}
if unknown:
    sys.exit(
        "arbre ambigu, état refusé plutôt que deviné : [tool.uv] porte "
        f"{sorted(unknown)}, que ce protocole ne sait pas mesurer — la mesure se "
        "ferait contre une configuration différente de celle de la production"
    )

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
#    Un `graphiti-core` que le motif ne retire pas passerait au résolveur en
#    double : TOML tolère deux fois la même entrée dans un tableau, et le
#    motif d'insertion pourrait tomber sur un commentaire qui cite le paquet.
text = re.sub(r'^[ \t]*"graphiti-core[^"\n]*",?[ \t]*\n', "", text, flags=re.M)
remaining = [
    entry
    for entry in original.get("project", {}).get("dependencies", [])
    if entry.split("[")[0].split("=")[0].strip() == "graphiti-core"
]
if len(remaining) > 1:
    sys.exit(
        f"pyproject.toml déclare graphiti-core {len(remaining)} fois dans ses dépendances "
        "produit — le protocole ne sait pas mesurer un arbre aussi ambigu"
    )

# 3. La réinsérer, devant camel-oasis, comme la story 001-1 l'a fait. L'insertion
#    se fait sur la ligne qui *déclare* camel-oasis (celle qui commence par la
#    guillemet), pas sur un commentaire qui le mentionne.
#    L'indentation est celle de la ligne visée — la prendre « avant le dernier
#    saut de ligne » donnait une chaîne vide et produisait une dépendance
#    collée à la marge, ce que le harnais de test voit et que `uv` ne voyait pas.
needle = '"camel-oasis'
matches = [m for m in re.finditer(r'^[ \t]*"camel-oasis[^\n]*$', text, flags=re.M)]
if not matches:
    sys.exit("pyproject.toml : la déclaration de camel-oasis est introuvable")
match = matches[0]
indent = match.group(0)[: match.group(0).index('"')]
text = text[: match.start()] + f'{indent}"graphiti-core=={version}",\n' + text[match.start() :]

# 4. Poser l'override, si on mesure le chemin « override ».
if mode == "override":
    text = text.rstrip("\n") + f'\n\n[tool.uv]\noverride-dependencies = ["{OVERRIDE}"]\n'

# Le fichier doit rester du TOML valide : un parseur qui passe, c'est la preuve
# que la réécriture n'a pas cassé la déclaration qu'elle voulait mesurer. Et il
# doit contenir **exactement** ce qu'on croit y avoir mis.
try:
    written = tomllib.loads(text)
except tomllib.TOMLDecodeError as exc:
    sys.exit(f"pyproject.toml : la réécriture a produit un TOML invalide — {exc}")
declared = [
    entry
    for entry in written.get("project", {}).get("dependencies", [])
    if entry.split("[")[0].split("=")[0].strip() == "graphiti-core"
]
if declared != [f"graphiti-core=={version}"]:
    sys.exit(
        "la réécriture n'a pas produit l'état mesuré — graphiti-core déclaré "
        f"{declared} au lieu de ['graphiti-core=={version}']"
    )
written_overrides = written.get("tool", {}).get("uv", {}).get("override-dependencies")
if mode == "override" and written_overrides != [OVERRIDE]:
    sys.exit(f"l'override posé n'est pas celui de l'ADR 0010 : {written_overrides}")
if mode == "refus" and written_overrides:
    sys.exit(f"un override a survécu à la réécriture : {written_overrides}")

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
# Tous les endroits où graphiti-core peut être déclaré : produit, groupes de
# dépendances, extras. Un `graphiti-core` caché dans `dev` reste une
# déclaration, et l'arbre serait alors étiqueté à tort « AVANT la 001-1b ».
declared_everywhere = list(deps)
for group in data.get("dependency-groups", {}).values():
    declared_everywhere += list(group)
for extra in data.get("project", {}).get("optional-dependencies", {}).values():
    declared_everywhere += list(extra)
has_graphiti = any(d.split("[")[0].split("=")[0].strip() == "graphiti-core" for d in deps)
has_graphiti_anywhere = any(
    d.split("[")[0].split("=")[0].strip() == "graphiti-core" for d in declared_everywhere
)
# `[tool.uv]` porte d'autres leviers que l'override : `index-url`, `sources`,
# `no-build`, `required-version`… Le protocole retire la table entière pour la
# reposer, donc il mesurerait contre une configuration **différente** de celle
# de la production — un index privé, par exemple. Une mesure fausse, silencieuse
# et reproductible est pire que pas de mesure : on refuse avant l'étape 0.
uv_unknown = set(data.get("tool", {}).get("uv", {})) - {"override-dependencies"}
if uv_unknown:
    sys.exit(
        "arbre ambigu, état refusé plutôt que deviné : [tool.uv] porte "
        f"{sorted(uv_unknown)}, que ce protocole ne sait pas mesurer — la mesure "
        "se ferait contre une configuration différente de celle de la production"
    )

def refuse(reason):
    sys.exit(f"arbre ambigu, état refusé plutôt que deviné : {reason}")

if overrides and overrides != [canonical]:
    refuse(f"override {overrides} ≠ celui de l'ADR 0010 ({[canonical]})")
if has_graphiti and not overrides:
    refuse("graphiti-core est déclaré sans override — geste à moitié posé")
if has_graphiti_anywhere and not has_graphiti:
    # Testé **avant** le refus générique « override sans graphiti-core » : un
    # `graphiti-core` caché dans `dev` n'est pas un geste à moitié posé, c'est
    # une déclaration mal placée. Un message exact vaut mieux qu'un message
    # vrai mais trompeur — c'est tout l'intérêt de refuser plutôt que deviner.
    where = [
        section
        for section, entries in (
            ("groupe de dépendances", data.get("dependency-groups", {})),
            ("extra", data.get("project", {}).get("optional-dependencies", {})),
        )
        if any(
            e.split("[")[0].split("=")[0].strip() == "graphiti-core"
            for group in entries.values()
            for e in group
        )
    ]
    refuse(
        f"graphiti-core est déclaré dans {' et '.join(where)} mais pas dans les "
        "dépendances produit — le protocole ne mesure que la déclaration produit, "
        "et dirait « AVANT la 001-1b » sur un arbre qui l'a déjà"
    )
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
# Le lock et le sync sont **asservis**. Sans cela, un échec passe inaperçu :
# `$LOCKED_NEO4J` serait lu dans le venv resté sur l'état précédent, et le
# protocole consignerait comme « version résolue » celle d'avant l'override —
# le mensonge exact que l'ADR 0011 veut empêcher.
(cd "$BACKEND" && uv lock 2>&1 | tail -5) || {
    echo "l'override de l'ADR 0010 ne résout pas — la mesure s'arrête ici" >&2
    exit 1
}
(cd "$BACKEND" && uv sync 2>&1 | tail -3) || {
    echo "le lock résout mais l'installation échoue — la mesure s'arrête ici" >&2
    exit 1
}

# La version résolue est lue **dans le lock**, qui est la source de vérité, et
# non dans le venv : c'est le lock que l'ADR 0011 veut voir consigné, et la
# lecture par glob sur `*.dist-info` échouerait en silence sur un venv absent.
LOCKED_NEO4J=$(python3 - "$LOCK" <<'PY'
import sys
import tomllib

with open(sys.argv[1], "rb") as fh:
    lock = tomllib.load(fh)
versions = {p["version"] for p in lock.get("package", []) if p.get("name") == "neo4j"}
if len(versions) != 1:
    sys.exit(f"le lock porte {len(versions)} versions de neo4j : {sorted(versions)}")
print(versions.pop())
PY
) || {
    echo "version lockée de neo4j illisible — la mesure s'arrête ici" >&2
    exit 1
}
# Le lock dit 5.28.6, le venv peut dire autre chose : on ne consigne pas la
# version d'un environnement, mais celle qui sera déployée.
INSTALLED_NEO4J=$(cd "$BACKEND" && uv run python -c 'import neo4j; print(neo4j.__version__)' 2>/dev/null | tail -1)
if [ "$INSTALLED_NEO4J" != "$LOCKED_NEO4J" ]; then
    echo "le venv porte neo4j ${INSTALLED_NEO4J:-absent}, le lock ${LOCKED_NEO4J} — mesure incohérente" >&2
    exit 1
fi

# La version que la borne vient de résoudre est **consignée à côté d'elle**,
# comme l'impose l'ADR 0011. Sans cette ligne, l'arbre mesuré ne serait pas
# l'arbre que l'override décrit : le filet de tests de l'étape 6 lit ce
# commentaire, et la story 001-2 doit savoir quelle version elle teste.
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
written = line.sub(rf"\1\n{comment}", text, count=1)
if comment not in written:
    sys.exit("la version résolue n'a pas pu être consignée à côté de la borne")
open(path, "w", encoding="utf-8").write(written)
print(f"version résolue consignée : neo4j {version}")
PY

step "3. ce que chacun des trois paquets exige du driver"
echo "borne déclarée   : $OVERRIDE"
echo "version lockée   : neo4j $LOCKED_NEO4J"
echo "exigences lues dans les METADATA installés :"
grep -rhoE "Requires-Dist: neo4j[^;]*" "$SITE"/*.dist-info/METADATA 2>/dev/null | sort -u | sed 's/^/  /'

step "4. imports dans l'ordre — camel-oasis, puis neo4j, puis graphiti_core"
# Le script est écrit sur un heredoc `PY` plutôt que sur un `-c "…" 2>&1 | tail`
# à la ligne : un `)` de fin de pipeline sur la même ligne que la substitution
# de commande rendait le fichier illisible pour bash (le `)` de `tail -10)` était
# compté comme un groupement non fermé).
(
    cd "$BACKEND" || exit 1
    uv run python - <<'PY'
import oasis, neo4j, graphiti_core
print('oasis         ok', oasis.__file__.rsplit('/', 2)[-2])
print('neo4j         ok', neo4j.__version__)
print('graphiti_core ok', graphiti_core.__name__)
PY
) 2>&1 | tail -10

step "5. surface du driver réellement utilisée par camel et oasis"
for symbol in 'neo4j.Version' 'GraphDatabase.driver' 'from neo4j import Query' 'neo4j.exceptions'; do
    count=$(grep -rIl "$symbol" "$SITE/camel" "$SITE/oasis" 2>/dev/null | wc -l | tr -d ' ')
    printf '%-24s %s fichier(s)\n' "$symbol" "$count"
done

step "6. filet de tests"
cd "$BACKEND" && uv run pytest tests/ -q 2>&1 | tail -3