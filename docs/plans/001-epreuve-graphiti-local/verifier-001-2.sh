#!/usr/bin/env bash
# Protocole de la story 001-2 — rejouable à l'identique (NFR-3).
#
# Mesure une seule chose : **`neo4j 5.28.6`, forcé par l'`override-dependencies`
# de l'ADR 0010 contre le pin `==5.23.0` de `camel-oasis`, tient-il contact avec
# un vrai serveur ?** C'est le premier test comportemental du driver forcé ; si
# la réponse est non, l'ADR 0010 est supersédé, pas réécrit.
#
# Le script ne conclut rien : il affiche. Le verdict est dans
# `story-001-2.md`, la sortie brute dans `mesure-001-2.txt`.
#
# ## Ce que le protocole fait, dans l'ordre
#
# 1. démarre le serveur du compose d'épreuve, avec le mot de passe du `.env` ;
# 2. attend le healthcheck (le Bolt, pas le processus) ;
# 3. **écrit** le graphe de vérification et exerce toute la surface relevée par
#    l'ADR 0011 ;
# 4. **arrête** le conteneur, puis le **relance** — le cas C3 ;
# 5. **relit** : le nœud est-il toujours là, avec son arête et son `valid_at` ?
# 6. compare les deux versions — driver locké et serveur effectif.
#
# ## Deux exécutions, et pourquoi
#
# Le protocole se lance deux fois sur deux configurations de serveur :
#
#     SANS_APOC=1  le serveur sans le plugin APOC
#     defaut       le serveur du compose livré, plugin compris
#
# Ce n'est pas de la redondance, c'est la seule façon de répondre à « APOC est-il
# nécessaire ? ». Sur le serveur **sans** plugin, ce que `graphiti-core`
# réclame passe intégralement — donc Graphiti n'a pas besoin d'APOC. Sur le
# serveur **avec**, la requête que `camel` lance au `__init__` de son
# `Neo4jGraph` passe aussi — donc `camel` en a besoin. Deux mesures séparées,
# deux conclusions opposées, et une seule installation de plugin qui est justifiée
# par la seconde. Une seule exécution ne pouvait pas distinguer « aucun des deux
# n'en a besoin » de « seul Graphiti n'en a pas besoin ».
#
# ## Ce que le protocole refuse de faire
#
# - Il ne touche à aucune donnée hors du graphe de vérification : le nettoyage
#   filtre sur les étiquettes de la sonde (`mirofish_verification*`, `ApocSonde*`,
#   `MiroFishTransactionSonde`), jamais sur `DETACH DELETE` global.
# - Il ne détruit pas le volume : le cas C3 **exige** que le nœud survive, et
#   `down -v` ferait échouer la relecture pour la mauvaise raison.
# - Il n'écrit aucun épisode, n'appelle aucun LLM, ne touche pas à l'embedder.
#
# Usage, depuis la racine du dépôt :
#     bash docs/plans/001-epreuve-graphiti-local/verifier-001-2.sh sans-apoc
#     bash docs/plans/001-epreuve-graphiti-local/verifier-001-2.sh compose
#
# Le premier laisse le serveur du compose livré en place ; le second aussi. En cas
# d'échec, le conteneur reste arrêté ou démarré selon l'étape atteinte : le
# redémarrage est un objet de mesure, l'abandonner en cours de route laisserait un
# état que personne ne sait interpréter.

set -uo pipefail

MODE="${1:-compose}"
RACINE=$(cd "$(dirname "$0")/../../.." && pwd)
COMPOSE="$RACINE/docker-compose.neo4j.yml"
SANS_APOC=$(mktemp -t apoc-off-XXXXXX.yml)
SORTIE_SERVEUR=0

# Surcharge qui retire le plugin APOC. Un fichier, et non un `sed` sur le compose :
# le compose livré reste le compose livré, et la variante mesurée est visible en
# entier dans un fichier de trois lignes.
cat >"$SANS_APOC" <<'YAML'
services:
  neo4j:
    environment:
      NEO4J_PLUGINS: "[]"
      NEO4J_dbms_security_procedures_unrestricted: ""
YAML

etape() { printf '\n=========== %s ===========\n' "$1"; }

# Attendre que le Bolt réponde, sans dépendre du healthcheck Docker. Le
# healthcheck est lui-même une assertion de la story, mais l'échec d'un
# `--wait` ne dit pas *où* ça a coincé ; ici on distingue « le conteneur n'a pas
# démarré » de « le conteneur démarre mais ne devient jamais joignable ».
# L'identifiant est résolu **à chaque appel** : un changement d'environnement
# (`NEO4J_PLUGINS`) fait recréer le conteneur, donc son ID change en cours de
# protocole, et un ID figé au départ produirait un `docker exec` vers un
# conteneur disparu — 180 secondes d'attente sur une panne qui n'en est pas une.
# C'est ce qui est arrivé au premier essai : le conteneur recréé était healthy,
# et le protocole a attendu trois minutes un Bolt joignable qui l'était déjà.
identifiant() { docker compose "${SITES[@]}" ps -q neo4j 2>/dev/null | head -1; }

attendre_bolt() {
    local i conteneur
    conteneur=$(identifiant)
    if [ -z "$conteneur" ]; then
        echo "plus de conteneur neo4j à interroger" >&2
        return 1
    fi
    for i in $(seq 1 60); do
        conteneur=$(identifiant)
        [ -n "$conteneur" ] || continue
        if docker exec "$conteneur" cypher-shell -a bolt://localhost:7687 \
            -u neo4j -p "${NEO4J_PASSWORD:?mot de passe absent}" "RETURN 1" >/dev/null 2>&1; then
            echo "Bolt joignable après $((i * 3))s environ"
            return 0
        fi
        sleep 3
    done
    echo "le Bolt ne répond pas après 180s" >&2
    return 1
}

# Le mot de passe vient du `.env`, comme le compose. Le lire ici plutôt que de le
# passer en variable d'environnement évite qu'il atterrisse dans l'historique du
# shell ou dans la sortie capturée.
NEO4J_PASSWORD=$(grep '^NEO4J_PASSWORD=' "$RACINE/.env" 2>/dev/null | cut -d= -f2-)
if [ -z "${NEO4J_PASSWORD:-}" ]; then
    echo "NEO4J_PASSWORD absent du .env — le protocole ne peut pas démarrer le serveur" >&2
    rm -f "$SANS_APOC"
    exit 1
fi

case "$MODE" in
    sans-apoc)
        ATTENTE_APOC="absent"
        SITES=(-f "$COMPOSE" -f "$SANS_APOC")
        LIBELLE="serveur SANS le plugin APOC"
        ;;
    compose)
        ATTENTE_APOC="attendu"
        SITES=(-f "$COMPOSE")
        LIBELLE="serveur du compose livré, plugin APOC compris"
        ;;
    *)
        echo "mode inconnu : « $MODE » (attendu : sans-apoc ou compose)" >&2
        rm -f "$SANS_APOC"
        exit 1
        ;;
esac

cd "$RACINE" || exit 1
if ! docker compose "${SITES[@]}" up -d --wait >/dev/null 2>&1; then
    echo "le conteneur neo4j n'a pas pu démarrer — la mesure s'arrête ici" >&2
    docker compose "${SITES[@]}" logs --tail 40 neo4j >&2 || true
    exit 1
fi
CONTENEUR=$(identifiant)
if [ -z "$CONTENEUR" ]; then
    echo "le conteneur neo4j n'a pas été créé — la mesure s'arrête ici" >&2
    exit 1
fi

etape "0. configuration mesurée"
echo "mode            : $MODE"
echo "configuration   : $LIBELLE"
echo "attente APOC    : $ATTENTE_APOC"
echo "compose         : $(cd "$RACINE" && git rev-parse --short HEAD 2>/dev/null) · $(shasum -a 256 "$COMPOSE" | cut -c1-16)…"
echo "conteneur       : $CONTENEUR"
echo "version compose : $(grep -E '^\s+image: neo4j:' "$COMPOSE" | sed 's/.*image: *//')"

etape "1. démarrage et healthcheck"
# `--wait` bloque jusqu'au healthcheck vert : c'est déjà une assertion de la
# story — un healthcheck qui ne passe jamais ferait échouer la commande, donc
# aucun diagnostic n'aurait à être produit à la main.
if ! docker compose "${SITES[@]}" up -d --wait; then
    echo "le conteneur ne devient pas healthy — la mesure s'arrête ici" >&2
    docker compose "${SITES[@]}" logs --tail 40 neo4j >&2 || true
    exit 1
fi
docker compose "${SITES[@]}" ps --format '  {{.Name}}  {{.State}}  {{.Status}}'
attendre_bolt || exit 1

etape "2. version effective du serveur et du driver"
# La version du serveur est lue **du serveur** (`CALL dbms.components()` dans le
# script) et non du tag : une image peut être re-tagée, `CALL` ne ment pas. Le
# tag est affiché à côté pour que l'écart soit lisible.
docker exec "$(identifiant)" cypher-shell -a bolt://localhost:7687 -u neo4j -p "$NEO4J_PASSWORD" \
    "CALL dbms.components() YIELD name, versions, edition RETURN name, versions, edition" 2>&1 | sed 's/^/  /'
(cd "$RACINE/backend" && uv run python -c "import importlib.metadata as m; print('  driver locké : neo4j', m.version('neo4j'))")
(cd "$RACINE/backend" && uv run python -c "import importlib.metadata as m; print('  graphiti-core:', m.version('graphiti-core'))")

etape "3. écriture, surface de l'ADR 0011, procédures Graphiti, APOC"
(cd "$RACINE/backend" && uv run python scripts/verifier_driver_neo4j.py ecrire --apoc "$ATTENTE_APOC")
CODE_ECRIRE=$?
echo "code de sortie : $CODE_ECRIRE"
if [ "$CODE_ECRIRE" -ne 0 ]; then
    echo "l'écriture ou un contrôle a échoué : on ne mesure pas la persistance d'un graphe" >&2
    echo "qui n'a pas été écrit — la mesure s'arrête ici" >&2
    exit "$CODE_ECRIRE"
fi

etape "4. arrêt puis redémarrage du conteneur — le cas C3"
# `stop` puis `start`, et non `restart` : `restart` pourrait réutiliser un état
# que le stop aurait dû produire, et on veut que l'arrêt soit un fait observé.
docker compose "${SITES[@]}" stop
echo "--- après stop ---"
docker compose "${SITES[@]}" ps -a --format '  {{.Name}}  {{.State}}'
docker compose "${SITES[@]}" start
attendre_bolt || exit 1
docker compose "${SITES[@]}" ps --format '  {{.Name}}  {{.State}}  {{.Status}}'

etape "5. relecture après redémarrage"
(cd "$RACINE/backend" && uv run python scripts/verifier_driver_neo4j.py relire --apoc "$ATTENTE_APOC")
CODE_RELEIRE=$?
echo "code de sortie : $CODE_RELEIRE"

etape "6. verdict de cette exécution"
if [ "$CODE_RELEIRE" -eq 0 ]; then
    echo "  driver 5.28.6 : tient contact avec le serveur, écriture et relecture comprises"
    echo "  surface ADR 0011 : exercée, hiérarchie d'exceptions comprise"
    echo "  volume nommé : le nœud a survécu à l'arrêt puis au redémarrage"
else
    echo "  ⚠️  échec — voir les contrôles en échec ci-dessus"
fi
echo "  configuration : $LIBELLE"
echo "  APOC attendu  : $ATTENTE_APOC"
echo
echo "Le verdict global de la story est dans story-001-2.md, pas ici : ce"
echo "protocole affiche, il ne conclut pas."

rm -f "$SANS_APOC"
exit "$CODE_RELEIRE"
