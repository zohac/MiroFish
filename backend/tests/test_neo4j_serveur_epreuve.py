"""Garde-fous du serveur Neo4j d'épreuve — story 001-2.

La story a fait deux choses qu'aucun outil ne vérifie, et les deux se paient
plus tard si on les laisse diverger.

**1. Le serveur supporté est compatible avec le driver locké.** Le compose
épreuve un serveur `5.26.31` alors que `backend/uv.lock` force un driver
`5.28.6` (ADR 0010, borne `neo4j>=5.26.0,<6.0.0`). Cet écart a été **mesuré**
le 5 octobre 2026 — écriture, relecture, surface de l'ADR 0011, les quatre types
d'exceptions — et il tient. Mais le compose est un fichier Living : quelqu'un
peut y écrire `neo4j:latest`, ou `5.26` pour « simplifier », et l'écart devient
alors 5.28 / 5.x inconnu sans qu'aucun avertissement ne s'affiche. Ces tests
lisent le **vrai** `docker-compose.neo4j.yml` et échouent si l'écart sort de ce
qui a été mesuré.

**2. Le tag du serveur est figé.** `neo4j:5.26` est flottant : vérifié sur Docker
Hub, il pointait déjà sur `5.26.31` le 5 octobre 2026, et il bouge à chaque
sortie. Un tag flottant dans un compose versionné signifie qu'un `up` six mois
après démarre autre chose que ce qu'on a mesuré — c'est le même raisonnement que
la version résolue de l'override, consignée à côté dans `pyproject.toml`
(ADR 0011).

Ces tests sont **hermétiques** : aucun conteneur n'est démarré, aucun port
n'est ouvert. Ils portent sur des fichiers du dépôt, ce qui veut dire qu'ils
tournent dans la CI et sur un poste sans Docker — sinon ils ne garderaient que
les postes qui ont déjà le serveur, c'est-à-dire aucun.

> **Pourquoi aucun de ces tests ne démarre de serveur.** Le test
> comportemental existe : `backend/scripts/verifier_driver_neo4j.py`, rejoué par
> `docs/plans/001-epreuve-graphiti-local/verifier-001-2.sh`, et ses deux sorties
> sont versionnées dans le dossier de l'epic. Il est **hors de la CI** : la CI
> n'a pas de service Neo4j, et y en ajouter un pour 17 contrôles coûtait plus,
> à chaque commit, que ce qu'il prouvait. Ces tests gardent donc l'invariant
> *statique* — le serveur que le dépôt déclare reste celui qu'on a mesuré — et la
> preuve d'exécution reste versionnée et rejouable à la main.
"""

import re
import shutil
import subprocess
import sys
import tomllib
from importlib import util as import_util
from importlib.metadata import PackageNotFoundError, distribution
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parent
PYPROJECT = BACKEND / "pyproject.toml"
LOCK = BACKEND / "uv.lock"
COMPOSE = REPO / "docker-compose.neo4j.yml"

# --------------------------------------------------------------------------
# Ce que la story 001-2 a mesuré — les chiffres sont dans
# docs/plans/001-epreuve-graphiti-local/mesure-001-2-compose.txt
# --------------------------------------------------------------------------

# Le serveur tel que la story l'a mesuré : tag figé, patch figé, édition
# Community. Une implémentation qui écrit autre chose ne mesure pas la même
# chose — même principe que la forme canonique de l'override (ADR 0011).
IMAGE_CANONIQUE = "neo4j:5.26.31-community"

# Le préfixe des ressources Docker. Il décide du nom du volume — donc de
# l'identité de la base. Le protocole l'affiche dans son étape 0 : c'est ce
# qu'on lit pour savoir si deux exécutions ont bien parle à la même base.
PREFIXE_PROJET = "mirofish-neo4j"

# La borne de l'override, à l'identique de l'ADR 0010 et de l'ADR 0011.
BORNE_DRIVER = "neo4j>=5.26.0,<6.0.0"

# L'écart mesuré. Le driver locké n'est pas le serveur : 5.28.6 contre 5.26.31,
# et c'est délibéré — 5.26 est le plancher que déclare `graphiti-core` et une
# LTS. Un serveur plus récent que le driver, ou de deux minesures d'écart, n'a
# pas été mesuré : on refuse de le laisser passer en silence.
SERVEUR_MESURE = (5, 26, 31)


def version_triplet(version: str) -> tuple[int, ...] | None:
    """`5.26.31` → `(5, 26, 31)`. `None` si la version est illisible.

    Le suffixe d'édition (`-community`, `-enterprise`) et celui de pre-release
    (`-rc1`) sont retirés : ce sont des chaînes d'image, pas des versions.
    """
    core = version.strip().split("-")[0]
    morceaux = core.split(".")
    if not core or not all(m.isdigit() for m in morceaux):
        return None
    return tuple(int(m) for m in morceaux)


def tag_serveur(compose: str) -> str | None:
    """Le tag d'image du service `neo4j`, dans le compose livré.

    On lit le fichier **réellement livré**, pas une copie de fixture : un
    garde-fou qui lirait sa propre fixture prouverait que la fixture est
    conforme, pas que le compose l'est.

    Le tag cherché est celui du **service `neo4j`**, pas la première ligne
    `image:` du fichier. Sans cette précision, la fonction renvoyait l'image du
    premier service venu : invisible aujourd'hui — le compose d'épreuve n'a qu'un
    service — mais l'epic 005 va lui ajouter des voisins, et un test mesurerait
    alors l'image du mauvais service **silencieusement**.
    """
    bloc = re.search(
        r"^  neo4j:\s*$(.*?)(?=^  \S|\Z)",
        lignes_actives(compose),
        flags=re.MULTILINE | re.DOTALL,
    )
    if bloc is None:
        return None
    correspond = re.search(r"^\s+image:\s*(\S+)\s*$", bloc.group(1), flags=re.MULTILINE)
    return correspond.group(1) if correspond else None


def corps_tag(compose: str) -> str:
    """La version du tag d'image, ou une erreur qui nomme le tag fautif.

    `tag.split(":", 1)[1]` sans garde levait `IndexError` sur une image sans
    tag — un échec de fixture, là où il fallait un message sur le compose. Un
    test qui casse pour une raison étrangère à ce qu'il garde finit supprimé.
    """
    tag = tag_serveur(compose)
    assert tag is not None, "aucune image de service neo4j dans le compose"
    corps = tag.split(":", 1)[1] if ":" in tag else ""
    assert corps, f"tag sans version : {tag!r} — le serveur d'épreuve n'est pas figé"
    return corps


def lire_compose() -> str:
    assert COMPOSE.exists(), (
        f"{COMPOSE} est absent : le serveur d'épreuve n'est plus déclaré. "
        "La story 001-2 l'a créé ; sans lui, la preuve du driver forcé n'est plus rejouable."
    )
    return COMPOSE.read_text(encoding="utf-8")


def lignes_actives(texte: str) -> str:
    """Le compose **sans ses commentaires**.

    Un test qui cherche une clé dans un YAML commentsé trouve l'explication de
    son propre interdit : le compose livré dit pourquoi il n'y a pas
    d'`env_file` et pourquoi le tag est figé, et ces phrases contiennent les mots
    cherchés. Séparer l'observation de l'explication n'est pas une
    coquetterie : sans ça, la règle à garder et sa justification ne
    pourraient pas cohabiter dans le même fichier, donc la règle pousserait
    à écrire moins de commentaires.
    """
    return "\n".join(ligne for ligne in texte.splitlines() if not ligne.strip().startswith("#"))


def lire_sortie_versionnee(dossier: Path, mode: str) -> str | None:
    """Le texte d'une sortie de mesure versionnée, ou `None` si elle manque.

    La lecture passe par ici pour que le cas « absente » ait un endroit unique à
    tester. Avant, chaque test lisait le fichier à sa main, et le test censé
    vérifier le cas « absent » attrapait l'exception de `pathlib` au lieu de
    celle de cette fonction.
    """
    sortie = dossier / f"mesure-001-2-{mode}.txt"
    if not sortie.exists():
        return None
    return sortie.read_text(encoding="utf-8")


def version_driver_lockee() -> str:
    lock = tomllib.loads(LOCK.read_text(encoding="utf-8"))
    versions = {p["version"] for p in lock.get("package", []) if p.get("name") == "neo4j"}
    if len(versions) != 1:
        raise AssertionError(f"le lock porte {len(versions)} versions de neo4j : {sorted(versions)}")
    return versions.pop()


def version_driver_resolue() -> str:
    """La version **consignée** dans `pyproject.toml`, pas celle du lock.

    Les deux doivent concorder, et c'est `test_pyproject_override.py` qui
    vérifie ça. Ici on lit le commentaire parce que c'est lui que la story 001-2
    teste : si quelqu'un aligne le serveur sur le driver, il faut que ce soit un
    geste visible dans `pyproject.toml`, pas une édition du compose.
    """
    texte = PYPROJECT.read_text(encoding="utf-8")
    # La ligne est un **commentaire** — « version effectivement résolue au lock
    # du … : neo4j 5.28.6 ». On la lit telle que l'ADR 0011 l'impose : à côté de
    # la borne, sous la ligne `override-dependencies`. `test_pyproject_override.py`
    # vérifie l'adjacence et l'accord avec le lock ; ici on ne lit que le chiffre,
    # pour pouvoir le comparer à la sortie de mesure.
    trouve = re.search(r"^#.*\bneo4j\s+(\S+)\s*$", texte, flags=re.MULTILINE)
    assert trouve, "aucune version de neo4j consignée dans backend/pyproject.toml (ADR 0011)"
    return trouve.group(1)


# --------------------------------------------------------------------------
# Ce que le compose livré doit contenir
# --------------------------------------------------------------------------

def test_le_serveur_mesure_est_celui_du_compose_livre():
    """Le tag est-il exactement celui que la story a mesuré ?

    Un `5.26` ou un `latest` ici ne « marcherait pas moins bien » : il
    dirait autre chose que ce qu'on mesure.
    """
    tag = tag_serveur(lire_compose())
    assert tag == IMAGE_CANONIQUE, (
        f"le compose déclare {tag!r}, la story 001-2 a mesuré {IMAGE_CANONIQUE!r}. "
        "Le tag du serveur est figé sur un patch : `5.26` est flottant, et "
        "`neo4j:<version>` sans suffixe est l'édition Enterprise, qui réclame "
        "un accord de licence."
    )


def test_le_patch_du_serveur_est_fige():
    """Un patch flottant dans un compose versionné est une mesure non rejouable.

    Le test vérifie la forme du tag, pas son contenu : `5.26` est un patch
    flottant, `5.26.31` n'en est pas un. C'est le seul endroit où la règle
    « figer » est vérifiable sans lancer Docker.
    """
    corps = corps_tag(lire_compose())
    assert corps.count(".") >= 2, (
        f"le tag « {corps} » ne fige pas son patch : « 5.26 » glisse à chaque "
        "sortie de Neo4j. Un `up` six mois après démarrerait un serveur "
        "qu'on n'a pas mesuré."
    )


def test_le_compose_est_separe_de_celui_de_l_application():
    """`docker-compose.yml` ne doit pas mentionner Neo4j.

    Le compose de l'application pointe l'image **amont** (AGENTS.md §2.9) : y
    ajouter un service `neo4j` ferait dépendre le test comportemental du driver
    forcé d'un environnement qui n'est pas le nôtre. C'est la raison du fichier
    séparé, écrite dans les notes de la story.
    """
    compose_app = (REPO / "docker-compose.yml").read_text(encoding="utf-8")
    assert "neo4j" not in compose_app.lower(), (
        "docker-compose.yml mentionne neo4j : le serveur d'épreuve doit rester "
        "dans docker-compose.neo4j.yml, séparé de l'image amont"
    )


def test_le_mot_de_passe_ne_vient_pas_d_un_env_file():
    """Le mot de passe passe par l'interpolation, pas par `env_file`.

    `env_file: .env` passerait `LLM_API_KEY` et `ZEP_API_KEY` dans un conteneur
    Neo4j qui n'a rien à en faire (AGENTS.md §2.4). L'interpolation lit le
    `.env` sans l'injecter en bloc.

    Le test regarde les **lignes actives** du compose, commentaires exclus : le
    compose livré explique *pourquoi* il n'y a pas d'`env_file`, donc chercher
    le mot dans tout le fichier échouerait sur sa propre justification.
    """
    compose = lignes_actives(lire_compose())
    assert "env_file" not in compose, (
        "le compose d'épreuve utilise env_file : les secrets du LLM et de Zep "
        "seraient passés au conteneur Neo4j, sans raison"
    )
    assert "${NEO4J_PASSWORD}" in compose, (
        "le mot de passe n'est pas interpolé depuis le .env : il serait alors "
        "écrit en clair dans un fichier versionné"
    )


def test_le_healthcheck_interroge_le_bolt():
    """Un healthcheck qui teste le processus ne prouve pas que le Bolt répond.

    Le healthcheck amont de Neo4j (`wget localhost:7474`) passe dès que le HTTP
    écoute, donc avant que la base n'accepte une transaction — et la transaction,
    c'est ce que le driver va faire. Celui d'ici ouvre une session Bolt.
    """
    compose = lignes_actives(lire_compose())
    bloc = re.search(r"^\s+healthcheck:\n(.*?)(?=^\s{4}\w|\Z)", compose, flags=re.DOTALL | re.MULTILINE)
    assert bloc, "aucun healthcheck dans le compose d'épreuve"
    corps = bloc.group(1)
    # Le port **et** un vrai client : `wget localhost:7474` passe dès que le HTTP
    # écoute, donc avant que la base n'accepte une transaction. Le port seul ne
    # suffit pas à disqualifier ce test — c'est `cypher-shell` qui le fait, par
    # son `RETURN` sur le port Bolt.
    assert "7687" in corps, (
        "le healthcheck n'interroge pas le port Bolt 7687 : un test qui vise le "
        "HTTP passe avant que la base n'accepte une transaction"
    )
    assert "cypher-shell" in corps, (
        "le healthcheck n'exécute aucune requête : il vérifie qu'un processus "
        "tourne, pas que le Bolt répond. Il faut `cypher-shell … \"RETURN 1\"`."
    )
    # L'**extraction du mot de passe**, pas seulement sa présence. Le healthcheck
    # lit `${NEO4J_AUTH#neo4j/}` : sans le `#neo4j/`, `-p` reçoit
    # `neo4j/<mot de passe>` au lieu du mot de passe, la connexion échoue, et le
    # conteneur ne devient jamais `healthy` — donc `up --wait` ne rend jamais la
    # main et le protocole expire. Vérifié par mutation : avec `-p "$${NEO4J_AUTH}"`
    # les 41 tests passaient.
    assert re.search(r"-p\s+\"?\$\$\{NEO4J_AUTH#neo4j/\}", corps), (
        "le healthcheck ne retire pas le préfixe `neo4j/` de NEO4J_AUTH : il passe "
        "`neo4j/<mot de passe>` comme mot de passe, la sonde échoue, et le "
        "conteneur ne devient jamais healthy"
    )


def test_les_ports_sont_explicites():
    """7474 et 7687 exposés, et le volume nommé présent.

    AGENTS.md §2.9 : les ports sont exposés explicitement, et les données
    persistantes vivent dans un volume **nommé** — c'est la moitié du critère C3
    qui ne dépend pas de l'extraction.
    """
    compose = lignes_actives(lire_compose())
    for port in ("7474:7474", "7687:7687"):
        assert port in compose, f"le port {port} n'est pas exposé explicitement"
    # Le volume est cherché **dans le service**, pas dans la déclaration de
    # volume racine : c'est le montage qui fait la persistance. Une déclaration
    # racine sans montage (`neo4j_data:` orphelin) donne un volume créé et jamais
    # utilisé — le pire des deux, puisque `docker volume ls` le montre et que la
    # donnée, elle, disparaît.
    service = re.search(r"^services:\n(.*?)^volumes:", compose, flags=re.DOTALL | re.MULTILINE)
    assert service, "aucune section services dans le compose d'épreuve"
    for montage in ("neo4j_data:/data", "neo4j_logs:/logs"):
        assert montage in service.group(1), (
            f"le service ne monte pas {montage} : la donnée ou les journaux "
            "mourraient avec le conteneur, et le critère C3 échouerait"
        )
    racine = re.search(r"^volumes:\n(.*)\Z", compose, flags=re.DOTALL | re.MULTILINE)
    assert racine, "aucun volume nommé déclaré à la racine du compose"
    # Les deux volumes sont vérifiés : `/data` porte le graphe et `/logs` les
    # journaux du serveur. Le second paraît secondaire, mais un montage retiré
    # fait écrire les logs dans la couche du conteneur — donc les perdre à chaque
    # `up`, alors que c'est là qu'on lit la trace d'un démarrage qui rate.
    for nom in ("neo4j_data", "neo4j_logs"):
        assert re.search(rf"^  {nom}:\s*$", racine.group(1), flags=re.MULTILINE), (
            f"le volume {nom} est monté mais pas déclaré à la racine : Docker le "
            "créerait implicitement, hors du périmètre du projet"
        )


def test_le_plugin_apoc_est_installe():
    """APOC est mesuré nécessaire — à `camel-oasis`, pas à Graphiti.

    `graphiti-core==0.30.2` n'appelle aucune procédure APOC (zéro occurrence
    dans le paquet, mesuré). En revanche `Neo4jGraph.__init__` lance
    `refresh_schema()`, qui exécute `CALL apoc.meta.data()` ; et
    `add_nodes_from_df` utilise `apoc.merge.node`, `apoc.merge.relationship` et
    `apoc.create.addLabels`. Sans le plugin, le chemin Neo4j de `camel` casse
    sur un `ClientError` dès le premier `refresh_schema`.

    Le test garde donc le plugin **et** la ligne qui l'autorise en écriture : un
    plugin installé mais muet sur `apoc.merge.*` est plus trompeur que son
    absence, et `camel` étant écrit pour dire « plugin absent » dans les deux
    cas, l'erreur serait fausse.
    """
    compose = lignes_actives(lire_compose())
    plugins = re.search(r"^\s*NEO4J_PLUGINS:\s*(.+?)\s*$", compose, flags=re.MULTILINE)
    assert plugins, (
        "NEO4J_PLUGINS a disparu du compose : le plugin ne se téléchargerait "
        "plus tout seul au premier démarrage"
    )
    # On lit la **valeur**, pas le fichier : `apoc` apparaît ailleurs dans le
    # compose — dans `dbms.security.procedures.unrestricted`. Un `grep 'apoc'`
    # passerait donc avec le plugin désinstallé, et le garde-fou ne garderait
    # rien. C'est la même raison qui fait qu'un test doit muter le vrai fichier.
    assert "apoc" in plugins.group(1), (
        f"NEO4J_PLUGINS vaut {plugins.group(1)!r}, sans apoc : camel-oasis en a "
        "besoin, son Neo4jGraph casse dès le premier refresh_schema"
    )
    # La **valeur** de la dérogation, et pas sa clé : une liste restreinte à
    # `apoc.read.*` laisserait le plugin installé et muet sur l'écriture, l'état
    # exact que la story nomme « le pire des deux ». Vérifié par mutation :
    # `procedures_unrestricted: "apoc.read.*"` faisait passer les 41 tests.
    debridage = re.search(r"^\s*NEO4J_dbms_security_procedures_unrestricted:\s*(.+?)\s*$", compose, flags=re.MULTILINE)
    assert debridage, (
        "apoc.merge.* et apoc.create.* sont des procédures d'écriture : sans "
        "dbms.security.procedures.unrestricted, Neo4j les refuse même avec le "
        "plugin installé"
    )
    debride = debridage.group(1).strip().strip('"').strip("'")
    for procedure in ("apoc.merge.", "apoc.create."):
        assert procedure in debride, (
            f"la dérogation vaut {debride!r} et ne couvre pas `{procedure}*` : "
            "camel-oasis écrit par ces procédures, et l'erreur qu'il produirait "
            "accuserait un plugin absent alors qu'il est présent"
        )


# --------------------------------------------------------------------------
# L'écart driver / serveur — le cœur de la story
# --------------------------------------------------------------------------

def test_le_driver_locke_est_celui_de_la_borne_de_l_adrs():
    """Le serveur doit être compatible avec le driver **locké**.

    On compare à la borne de l'override, pas à une version relue quelque part :
    la borne est la déclaration de l'ADR 0010, et c'est elle que le compose doit
    servir.
    """
    compose = lire_compose()
    tag = tag_serveur(compose)
    serveur = version_triplet(corps_tag(compose))
    assert serveur, f"version de serveur illisible dans le tag {tag!r}"
    driver = version_triplet(version_driver_lockee())
    assert driver, f"version de driver illisible : {version_driver_lockee()!r}"

    meme_majeure = serveur[0] == driver[0]
    assert meme_majeure, (
        f"serveur {serveur[0]}.x et driver {driver[0]}.x : deux versions "
        "majeures différentes n'ont jamais été mesurées ensemble. Neo4j ne "
        "promet la compatibilité que sur la même majeure."
    )
    borne = BORNE_DRIVER.replace("neo4j", "").strip()
    plancher = version_triplet(borne.split(",")[0].lstrip(">="))
    assert plancher is not None, f"borne illisible : {BORNE_DRIVER!r}"
    assert serveur >= plancher, (
        f"serveur {'.'.join(map(str, serveur))} sous le plancher "
        f"{'.'.join(map(str, plancher))} que déclare graphiti-core"
    )


def test_l_ecart_driver_serveur_reste_dans_ce_qui_a_ete_mesure():
    """L'écart mesuré est 5.28.6 / 5.26.31 — rien de plus large.

    Le jour où quelqu'un aligne les deux « pour simplifier », il faut que ce soit
    un geste visible : c'est tout l'intérêt d'avoir consigné l'écart et de le
    garder par un test. Un serveur aligné sur le driver n'est pas faux, il
    n'est simplement **plus mesuré** — et il faut rejouer le protocole, pas
    supposer que ça marche.
    """
    compose = lire_compose()
    corps = corps_tag(compose)
    serveur = version_triplet(corps)
    driver = version_triplet(version_driver_resolue())
    assert serveur and driver, "version illisible"
    # Une **égalité**, pas un écart maximal. La version précédente calculait
    # `abs(serveur[0] - driver[0])`, un écart de **majeures** : entre deux `5.x`
    # il vaut toujours 0, donc l'assertion ne pouvait pas échouer — et son
    # commentaire annonçait « trois versions majeures » pour une constante
    # valant 2. Une borne sur une grandeur constante n'est pas une borne.
    if serveur != SERVEUR_MESURE:
        raise AssertionError(
            f"le compose déclare un serveur {'.'.join(map(str, serveur))}, "
            f"la story a mesuré {'.'.join(map(str, SERVEUR_MESURE))} contre un "
            f"driver {'.'.join(map(str, driver))} — si c'est délibéré, rejouer "
            "verifier-001-2.sh et versionner la nouvelle sortie ; le test ne se "
            "met pas à jour tout seul, sinon il ne garderait plus rien."
        )


def test_le_serveur_declares_la_version_qui_a_ete_mesuree():
    """Le tag et la version effective doivent coïncider.

    Le tag est ce qu'on **écrit** ; la version effective a été lue du serveur
    par `CALL dbms.components()`. Une image peut être re-tagée sans que son
    contenu change : le test ne peut pas le voir tout seul, mais il vérifie que
    la sortie mesurée porte bien le même chiffre que le compose — donc qu'une
    divergence serait un fait consigné et non un oubli.
    """
    compose = lire_compose()
    declare = version_triplet(corps_tag(compose))
    mesure = re.search(
        r"Neo4j Kernel\", \[\"([\d.]+)\"\], \"community\"",
        (REPO / "docs/plans/001-epreuve-graphiti-local/mesure-001-2-compose.txt").read_text(encoding="utf-8")
        if (REPO / "docs/plans/001-epreuve-graphiti-local/mesure-001-2-compose.txt").exists()
        else "",
    )
    assert mesure, (
        "la sortie mesurée du compose livré est absente : "
        "docs/plans/001-epreuve-graphiti-local/mesure-001-2-compose.txt. "
        "Rejouer verifier-001-2.sh compose et versionner sa sortie."
    )
    assert declare == version_triplet(mesure.group(1)), (
        f"le compose annonce {'.'.join(map(str, declare))}, la mesure/versionnée "
        f"annonce {mesure.group(1)} : ce n'est pas le même serveur"
    )


def test_le_driver_consigne_est_celui_de_la_sortie_versionnee():
    """La sortie versionnée doit porter le driver locké, pas un autre.

    C'est le garde-fou de l'ADR 0011 : la borne est une plage, donc elle se
    résout sur la dernière 5.x au jour du lock. Si le lock a bougé depuis la
    mesure, alors la preuve ne porte plus sur la version déployée — et le dire
    vaut mieux que le supposer.
    """
    sortie = REPO / "docs/plans/001-epreuve-graphiti-local/mesure-001-2-compose.txt"
    assert sortie.exists(), (
        "docs/plans/001-epreuve-graphiti-local/mesure-001-2-compose.txt est absent : "
        "sans la sortie versionnée, la preuve n'est pas rejouable (NFR-3)"
    )
    texte = sortie.read_text(encoding="utf-8")
    trouve = re.search(r"driver\s+: neo4j ([\d.]+)", texte)
    assert trouve, "la sortie mesurée ne consigne aucune version de driver"
    assert trouve.group(1) == version_driver_resolue(), (
        f"la sortie mesurée porte le driver {trouve.group(1)}, pyproject.toml "
        f"consigne {version_driver_resolue()} : la preuve ne porte plus sur la "
        "version déployée"
    )
    assert version_driver_lockee() == version_driver_resolue(), (
        f"le lock porte neo4j {version_driver_lockee()}, pyproject.toml consigne "
        f"{version_driver_resolue()} — la version mesurée n'est pas celle qui part"
    )


# --------------------------------------------------------------------------
# Le compose livré doit rester propre
# --------------------------------------------------------------------------

def test_aucun_secret_en_clair_dans_le_compose():
    """Pas de mot de passe littéral dans le compose.

    `NEO4J_AUTH: neo4j/${NEO4J_PASSWORD}` est la forme attendue. Un mot de passe
    écrit en clair serait dans l'historique git pour toujours (AGENTS.md §2.4).

    La ligne `NEO4J_AUTH` est donc **analysée explicitement** : la boucle ne la
    saute pas. La version précédente la sautait sur un filtre qui eliminait toute
    ligne contenant `AUTH` — et `NEO4J_AUTH:` en contient — si bien que la
    branche qui vérifiait la valeur ne pouvait pas s'exécuter, pour aucune
    composition du fichier. Un test qui ne peut pas échouer n'est pas un test :
    c'est le genre de garde-fou que l'on compte à l'inventaire et qui ne garde
    rien.
    """
    compose = lire_compose()
    vues = 0
    for ligne in compose.splitlines():
        nu = ligne.strip()
        if nu.startswith("#") or "NEO4J_AUTH:" not in nu:
            continue
        vues += 1
        valeur = nu.split("NEO4J_AUTH:", 1)[1].strip().strip('"').strip("'")
        assert "${" in valeur, (
            f"secret en clair dans le compose : NEO4J_AUTH={valeur!r}. "
            "Le mot de passe vient du .env, jamais d'un fichier versionné."
        )
    assert vues, (
        "le compose livré ne déclare plus NEO4J_AUTH : ce test n'a rien vérifié, "
        "et un serveur démarrerait avec un secret implicite"
    )


def test_le_compose_livre_ne_depend_d_aucun_fichier_de_surcharge():
    """Le compose livré doit suffire : `docker compose -f docker-compose.neo4j.yml`.

    Une dépendance à une surcharge non versionnée ferait que la mesure rejouable
    ne l'est que sur la machine qui l'a produite — exactement le défaut que la
    001-1 a corrigé pour `mesurer-001-1.sh`. Le test regarde les lignes actives :
    le compose livré mentionne l'`override-dependencies` de Python dans ses
    commentaires, ce qui n'est pas une dépendance de compose.
    """
    compose = lignes_actives(lire_compose()).lower()
    for interdit in ("-f ", "extends:", "include:"):
        assert interdit not in compose, (
            f"le compose livré référence « {interdit} » : lancé seul, il ne "
            "mesurerait pas la configuration versionnée"
        )


# --------------------------------------------------------------------------
# Négatifs — vérifier que ces tests testent vraiment
#
# Un test négatif ne vaut que s'il **exerce le garde-fou** qu'il prétend
# vérifier. Une assertion sur une fixture littérale est une arithmétique sur du
# texte local : elle passe quoi qu'il arrive au dépôt. La section précédente
# faisait précisément cela — six tests sans aucun code du dépôt, dont les
# docstrings annonçaient le contraire. Chacun appelle désormais le code réel,
# sur un cas qu'il doit refuser.
# --------------------------------------------------------------------------

def _compose_avec_image(image: str) -> str:
    """Un compose minimal dont le service `neo4j` porte l'image donnée."""
    return f"services:\n  neo4j:\n    image: {image}\n"


def _patch_fige(serveur: tuple[int, ...], driver: tuple[int, ...]) -> str | None:
    """Ce que dit `test_le_driver_locke_est_celui_de_la_borne_de_l_adrs`.

    La même règle, isolated : même majeure, et serveur au moins au plancher que
    déclare l'override. `None` signifie « la règle passe ».
    """
    if serveur[0] != driver[0]:
        return (
            f"serveur {serveur[0]}.x et driver {driver[0]}.x : deux versions "
            "majeures différentes n'ont jamais été mesurées ensemble"
        )
    borne = BORNE_DRIVER.replace("neo4j", "").strip()
    plancher = version_triplet(borne.split(",")[0].lstrip(">="))
    if plancher is not None and serveur < plancher:
        return f"serveur {'.'.join(map(str, serveur))} sous le plancher que déclare graphiti-core"
    return None


def test_un_tag_sans_patch_est_reporte():
    """Le saut que la règle du patch figé interdit : `neo4j:5.26`.

    Le test livré compte les points du tag ; ici on vérifie que **ce compte est
    bien la règle qui refuse**, en appliquant la même expression au cas
    flottant puis au cas figé. Une fixture qui porterait elle-même l'assertion
    ne prouverait que sa propre fixture.
    """
    corps = corps_tag(_compose_avec_image("neo4j:5.26"))
    assert corps.count(".") < 2, "la fixture n'est pas un tag flottant"
    assert corps_tag(_compose_avec_image("neo4j:5.26.31-community")).count(".") >= 2


def test_un_tag_enterprise_est_reporte():
    """Le tag nu est l'édition Enterprise, qui réclame un accord de licence.

    `test_le_serveur_mesure_est_celui_du_compose_livre` compare le tag livré à
    `IMAGE_CANONIQUE`. Ici on vérifie que cette comparaison **refuse** le tag nu,
    et que le refus tient à l'édition, pas à un hasard de chaîne.
    """
    nu = tag_serveur(_compose_avec_image("neo4j:5.26.31"))
    assert nu is not None
    assert nu != IMAGE_CANONIQUE, "le tag nu passerait pour l'image canonique"
    assert "community" not in nu, (
        "un tag sans suffixe est l'édition Enterprise, qui réclame un accord de "
        "licence — hors de question pour une épreuve à 0 € (NFR-1)"
    )


def test_un_ecart_de_majeure_est_reporte():
    """Deux majeures d'écart n'ont jamais été mesurées ensemble.

    La règle qui porte l'écart driver / serveur est « même majeure, et serveur
    au moins au plancher que déclare l'override ». Ce test la rejoue par
    `_patch_fige`, sur un cas qu'elle doit refuser et sur le cas réellement
    mesuré qu'elle doit accepter.
    """
    refus = _patch_fige((8, 0, 0), (5, 28, 6))
    assert refus, "un serveur 8.x passerait pour compatible avec un driver 5.x"
    assert _patch_fige((5, 26, 31), (5, 28, 6)) is None, (
        "le cas réellement mesuré (5.26.31 / 5.28.6) devrait passer : si ce "
        "test échoue, la règle elle-même est fausse"
    )
    sous_plancher = _patch_fige((5, 25, 0), (5, 28, 6))
    assert sous_plancher, "un serveur sous le plancher de graphiti-core passerait"


def test_une_version_illisible_est_refusee_plutot_que_devinee():
    """`version_triplet` ne devine pas une version qu'elle ne sait pas lire.

    Le cas qui compte n'est pas « cinq » : c'est une image épinglée par digest,
    ou un tag sans version. Les deux doivent rendre `None`, jamais produire
    `(5, 26, 31)` par défaut.
    """
    assert version_triplet("cinq") is None
    assert version_triplet("") is None
    assert version_triplet("5.26.") is None
    assert version_triplet("latest") is None
    assert version_triplet("5.26.31-community") == (5, 26, 31)
    assert version_triplet("5.26.31-rc1") == (5, 26, 31)


def test_un_serveur_sous_le_plancher_de_graphiti_est_reporte():
    """Le plancher est celui de la **borne de l'ADR 0010**, pas une copie.

    Un test dont la référence est une version écrite en dur ne survit pas à la
    décision qu'elle codifie : le jour où la borne bouge, le test continuerait
    d'exiger l'ancienne, ou cesserait d'exiger quoi que ce soit.
    """
    borne = BORNE_DRIVER.replace("neo4j", "").strip()
    plancher = version_triplet(borne.split(",")[0].lstrip(">="))
    assert plancher is not None, f"borne illisible : {BORNE_DRIVER!r}"
    assert version_triplet("5.25.0") < plancher
    assert version_triplet("5.26.31") >= plancher


def test_une_sortie_absente_est_signalee_et_non_ignoree(tmp_path):
    """Une sortie de mesure absente doit être **signalée**, pas contournée.

    Le test vérifie `lire_sortie_versionnee` — la fonction du dépôt qui lit les
    sorties — et non `pathlib`. La version précédente lisait un chemin absent
    dans un `tmp_path` vide, attrapait le `FileNotFoundError` de `pathlib`, puis
    retournait : elle passait pour n'importe quelle version de Python, et
    supprimer l'assertion `mesure` de la fonction l'aurait laissée verte.
    """
    absente = lire_sortie_versionnee(tmp_path, "compose")
    assert absente is None, "une sortie absente ne doit pas se lire sans erreur"
    # Et le même appel sur le fichier réellement livré doit, lui, aboutir.
    presente = lire_sortie_versionnee(REPO / "docs/plans/001-epreuve-graphiti-local", "compose")
    assert presente, "la sortie versionnée du compose livré est introuvable"
    assert "serveur    : Neo4j " in presente


def test_les_deux_modes_du_protocole_sont_couverts_par_une_sortie():
    """Les deux mesures de la story sont versionnées, pas seulement la facile.

    La mesure « sans APOC » est celle qui prouve que Graphiti n'a pas besoin du
    plugin ; la mesure « compose » est celle qui prouve que `camel` en a besoin.
    N'en garder qu'une laisse l'affirmation sur APOC sans preuve d'un côté ou de
    l'autre — et une affirmation à moitié prouvée est celle qu'on croit le plus
    vite.
    """
    dossier = REPO / "docs/plans/001-epreuve-graphiti-local"
    for nom in ("mesure-001-2-compose.txt", "mesure-001-2-sans-apoc.txt"):
        sortie = dossier / nom
        assert sortie.exists(), (
            f"{nom} est absent : les deux mesures de la 001-2 sont versionnées, "
            "celle « compose » comme celle « sans APOC »"
        )
        texte = sortie.read_text(encoding="utf-8")
        assert "APOC       : attendu = " in texte, f"{nom} ne déclare pas son attente APOC"


def test_le_verdict_de_la_sortie_versionnee_est_lisible():
    """La sortie versionnée doit porter les deux versions et le verdict.

    Une sortie sans chiffres ne prouve rien : c'est la raison d'être de
    `NFR-3`. On lit donc le fichier **livré** et on vérifie qu'il contient ce
    qu'un lecteur doit pouvoir)y lire sans lance quoi que ce soit.
    """
    sortie = REPO / "docs/plans/001-epreuve-graphiti-local/mesure-001-2-compose.txt"
    texte = sortie.read_text(encoding="utf-8")
    for attendu in ("driver     : neo4j ", "serveur    : Neo4j "):
        assert attendu in texte, f"la sortie versionnée ne porte pas « {attendu} »"
    # Le **résultat**, pas seulement la présence de la mention : la version
    # précédente cherchait la chaîne « contrôles passés », que porterait aussi
    # bien un `0/17`. Une sortie vide de résultat satisfait un test qui ne lit
    # pas le résultat.
    rapport = re.search(r"(\d+)/(\d+) contrôles passés", texte)
    assert rapport, "la sortie versionnée ne porte aucun compte de contrôles"
    passes, total = int(rapport.group(1)), int(rapport.group(2))
    assert total > 0, "la sortie versionnée ne décrit aucun contrôle"
    assert passes == total, (
        f"la sortie versionnée porte {passes}/{total} contrôles passés : la "
        "preuve doit décrire une exécution sans échec, ou l'ADR 0010 doit être "
        "réexaminé"
    )
    assert "code de sortie : 0" in texte, (
        "la sortie versionnée ne consigne pas un code de sortie nul : une mesure "
        "qui a échoué ne prouve pas ce qu'elle prétend avoir mesuré"
    )


def test_le_protocole_est_versionne_et_executable():
    """Le protocole de la story existe, et il est lançable.

    Sans lui, la preuve est une anecdote : quelqu'un l'a écrite une fois, et on
    ne peut pas la rejouer. NFR-3.
    """
    protocole = REPO / "docs/plans/001-epreuve-graphiti-local/verifier-001-2.sh"
    assert protocole.exists(), "le protocole de mesure de la 001-2 est absent"
    assert protocole.stat().st_mode & 0o111, "le protocole n'est pas exécutable"
    contenu = protocole.read_text(encoding="utf-8")
    assert "sans-apoc" in contenu and "compose" in contenu, (
        "le protocole ne connaît pas ses deux modes : la mesure APOC ne peut "
        "donc pas être rejouée"
    )


def test_le_script_de_verification_est_versionne():
    """Le script exercé doit exister, et rester exécutable par phases.

    Le fichier est l'autre moitié de la preuve : le protocole l'appelle, donc un
    script renommé ferait échouer le protocole — mais un script qui n'exercerait
    plus la surface de l'ADR 0011 passerait encore. On vérifie donc qu'il en
    garde les symboles.
    """
    script = BACKEND / "scripts/verifier_driver_neo4j.py"
    assert script.exists(), "backend/scripts/verifier_driver_neo4j.py est absent"
    contenu = script.read_text(encoding="utf-8")
    for symbole in ("GraphDatabase.driver", "Query", "AuthError", "ServiceUnavailable", "CypherSyntaxError"):
        assert symbole in contenu, f"le script n'exerce plus {symbole}"
    for phase in ("ecrire", "relire", "nettoyer"):
        assert phase in contenu, f"la phase {phase} a disparu du script"


def test_le_script_sort_non_nul_en_cas_d_echec():
    """Un script de mesure qui sort 0 quand il échoue ne prouve rien.

    On vérifie la **forme** du code de retour, pas son comportement : un test
    d'intégration qui vérifierait le vrai `sys.exit` demanderait un serveur
    Neo4j dans la CI. Ce qui est vérifiable sans serveur, c'est que la sortie
    non nulle est bien produite depuis le compte des contrôles échoués.
    """
    contenu = (BACKEND / "scripts/verifier_driver_neo4j.py").read_text(encoding="utf-8")
    assert "return 1 if report.failures else 0" in contenu, (
        "le script ne dérive pas son code de retour des contrôles échoués : "
        "une mesure qui sort 0 malgré un échec est pire que pas de mesure"
    )


def test_le_compose_est_valide_pour_docker_compose():
    """`docker compose config` valide le YAML du compose livré.

    Le test est **conditionnel** : sans Docker, il se déclare non conduit plutôt
    que de passer en vert — un `pytest.skip`, jamais un `return`. Un `return`
    ferait enregistrer un succès à pytest, donc un test vert qui n'a rien fait :
    c'est exactement ce qu'AGENTS.md §2.2 interdit, et c'est ce qu'un `return`
    faisait ici. Un `pytest.skip` se voit dans le rapport de sortie.
    """
    if shutil.which("docker") is None:
        pytest.skip("docker absent : le compose livré n'a pas pu être validé")
    fini = subprocess.run(
        ["docker", "compose", "-f", str(COMPOSE), "config", "-q"],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    if fini.returncode != 0:
        # `config` n'a pas besoin du démon : s'il échoue, c'est le YAML ou la
        # configuration qui est en cause. Seuls les messages qui disent que le
        # démon est injoignable entrent dans le cas « non conduit ».
        if "Cannot connect to the Docker daemon" in (fini.stderr or ""):
            pytest.skip("démoneur Docker injoignable : le compose n'a pas pu être validé")
    assert fini.returncode == 0, f"docker compose config refuse le compose :\n{fini.stderr}"


def test_le_service_neo4j_est_nomme_dans_le_compose():
    """Le compose déclare un service `neo4j` — le nom qu'appelle le protocole.

    Un service renommé ferait échouer `docker compose ps -q neo4j`, donc le
    protocole, et l'erreur serait celle du protocole.
    """
    compose = lignes_actives(lire_compose())
    assert re.search(r"^services:\n\s+neo4j:", compose, flags=re.MULTILINE), (
        "le compose ne déclare pas de service neo4j"
    )


def test_le_prefixe_du_projet_est_fige():
    """`name:` fixe le préfixe des ressources, donc le nom du volume.

    Sans lui, Docker dérive le nom du projet du répertoire d'invocation : le
    volume s'appellerait `mirofish_neo4j_data` depuis la racine et
    `ne4j_neo4j_data` depuis `backend/`. Le même volume ne serait plus le même,
    et le critère C3 dépend de lui — deux exécutions du protocole depuis deux
    répertoires iraient dans deux bases différentes, et la relecture « prouverait »
    une persistance qui n'a pas eu lieu.
    """
    compose = lignes_actives(lire_compose())
    trouve = re.search(r"^name:\s*(\S+)\s*$", compose, flags=re.MULTILINE)
    assert trouve, (
        "le compose ne fixe pas `name:` : le préfixe des ressources dépendrait "
        "du répertoire d'invocation, et le volume de données ne serait plus le "
        "même selon l'endroit d'où on lance le protocole"
    )
    assert trouve.group(1) == PREFIXE_PROJET, (
        f"préfixe de projet {trouve.group(1)!r} au lieu de {PREFIXE_PROJET!r} : "
        "un préfixe différent pointe un volume différent, et le graphe "
        "paraîtrait vide après un simple changement de répertoire"
    )


# --------------------------------------------------------------------------
# Les faits que la story tire des bibliothèques — gardés, pas seulement racontés
# --------------------------------------------------------------------------

def test_graphiti_ne_appelle_aucune_procedure_apoc():
    """`graphiti-core` n'a besoin d'aucune procédure APOC — mesuré, donc gardé.

    L'affirmation est reprise dans le compose, `architecture.md`, `AGENTS.md`,
    `docs/STATUS.md`, `sprint-status.yaml` et les notes de la story. Elle est
    aussi ce qui justifie de garder le plugin APOC **pour `camel` et non pour
    Graphiti**. Aucun test ne la vérifiait : un `uv lock` qui ferait monter
    `graphiti-core` à une version appelant `apoc.merge.*` laisserait ces six
    documents faux, et le compose garderait un plugin installé pour rien — sans
    qu'aucune suite bronche.

    On lit donc le paquet installé. Zéro occurrence de `apoc` est le résultat
    mesuré ; la première suffit à faire échouer, avec le fichier nommé.
    """
    try:
        racine = Path(distribution("graphiti_core").locate_file("graphiti_core"))
    except PackageNotFoundError:  # pragma: no cover — la dépendance est lockée
        pytest.skip("graphiti-core absent du venv : rien à vérifier ici")
    occurrences = []
    for fichier in sorted(racine.rglob("*.py")):
        contenu = fichier.read_text(encoding="utf-8", errors="replace")
        for numero, ligne in enumerate(contenu.splitlines(), 1):
            if "apoc" in ligne.lower():
                occurrences.append(f"{fichier.relative_to(racine)}:{numero}")
    assert not occurrences, (
        "graphiti-core appelle désormais une procédure APOC : "
        + ", ".join(occurrences[:5])
        + " — la conclusion « Graphiti n'a pas besoin d'APOC, camel en a besoin » "
        "et la justification du plugin dans le compose sont à refaire."
    )


def test_le_script_de_verification_importe_ce_qui_a_ete_mesure():
    """Le script doit **s'importer**, pas seulement compiler.

    `test_script_compiles` vérifie la syntaxe, et
    `test_le_script_de_verification_est_versionne` cherche des noms de symboles
    par `grep` — or ces noms figurent aussi dans les commentaires du script, donc
    le test passait sur un script devenu **inimportable**. C'est le couplage le
    plus fragile du script : cinq symboles viennent de `graphiti_core` et de
    `camel`, deux bibliothèques dont l'ADR 0011 mesure justement qu'elles
    bougent.

    L'import est hermétique : aucune connexion n'est ouverte, aucun embedder
    n'est construit — ces imports portent des requêtes Cypher et des constantes.
    """
    script = BACKEND / "scripts" / "verifier_driver_neo4j.py"
    spec = import_util.spec_from_file_location("verifier_driver_neo4j_sous_test", script)
    assert spec and spec.loader, f"{script} n'est pas importable"
    module = import_util.module_from_spec(spec)
    # Le module est inscrit **avant** l'exécution : `@dataclass` relit
    # `sys.modules[cls.__module__].__dict__`, donc un module créé mais jamais
    # enregistré fait échouer l'import — ce qui aurait rendu ce test rouge pour
    # une raison étrangère à ce qu'il vérifie.
    precedent = sys.modules.get(spec.name)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        if precedent is None:
            del sys.modules[spec.name]
        else:
            sys.modules[spec.name] = precedent

    # La surface relevée par l'ADR 0011, résolue par le **module importé** et
    # non par une chaîne de caractères.
    for nom in ("GraphDatabase", "Query", "GqlError", "ClientError", "DriverError", "Neo4jError"):
        assert hasattr(module, nom), (
            f"le script n'expose plus {nom} : la surface de l'ADR 0011 a bougé, "
            "et ce qu'il mesure n'est plus ce que camel atteint"
        )
    for nom in ("get_fulltext_indices", "get_range_indices", "GraphProvider", "NODE_PROPERTY_QUERY", "EXCLUDED_LABELS"):
        assert getattr(module, nom, None), (
            f"le script n'importe plus `{nom}` : les requêtes d'indexation et la "
            "requête qui décide d'APOC ne seraient plus celles des bibliothèques "
            "installées, donc ce serait un autre serveur qui serait mesuré"
        )
