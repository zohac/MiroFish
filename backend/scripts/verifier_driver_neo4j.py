#!/usr/bin/env python3
"""Test comportemental du driver `neo4j` forcé — story 001-2.

L'ADR 0010 assume un risque : l'`override-dependencies` qui force
`neo4j 5.28.6` contre le pin `==5.23.0` de `camel-oasis` pourrait produire un
lock valide et un runtime cassé. La story 001-1 a vérifié le lock et les
imports ; **personne n'a ouvert de connexion**. Ce script est ce test.

Il **exerce** la surface que `camel-oasis` atteint à travers le driver — celle
relevée par l'ADR 0011 — au lieu de l'importer. Une surface importée et jamais
appelée ne prouve rien, et l'ADR 0011 le dit de `neo4j.Version`, qui
n'existait pas. Chaque symbole a donc son contrôle, avec son assertion.

Ce que ce script fait, et **seulement** cela (la story l'impose noir sur
blanc) : une connexion, une écriture, une relecture, un redémarrage. Il
n'écrit aucun épisode, n'appelle aucun LLM, ne touche pas à l'embedder. Deux
sources d'échec, ce serait deux causes possibles ; on n'en veut qu'une.

Phases :

    ecrire     surface + procédures + écriture du graphe de vérification
    relire     surface + procédures + relecture du graphe de vérification
    nettoyer   suppression du graphe de vérification

Survie au redémarrage : c'est l'orchestrateur qui arrête puis relance le
conteneur entre `ecrire` et `relire` — un script ne peut pas prouver qu'il a
survécu à un arrêt qu'il n'a pas subi. Le wrapper
`docs/plans/001-epreuve-graphiti-local/verifier-001-2.sh` enchaîne les deux.

Sortie : un rapport sur `stdout`, **exit non nul** dès qu'un contrôle exigé a
échoué. Les deux versions — serveur et driver — sont en tête du rapport : une
mesure sans les deux chiffres n'est pas rejouable.

Usage :

    cd backend && uv run python scripts/verifier_driver_neo4j.py ecrire
    cd backend && uv run python scripts/verifier_driver_neo4j.py relire
    cd backend && uv run python scripts/verifier_driver_neo4j.py ecrire --apoc attendu

La cible vient de l'environnement — `NEO4J_URI`, `NEO4J_USER`,
`NEO4J_PASSWORD` — lu dans le `.env` de la racine, comme les autres scripts.
"""

from __future__ import annotations

import argparse
import os
import re
import socket
import sys
import uuid
import warnings
from dataclasses import dataclass, field
from datetime import datetime, timezone
from importlib.metadata import version as distribution_version
from pathlib import Path

_scripts_dir = Path(__file__).resolve().parent
_backend_dir = _scripts_dir.parent
_project_root = _backend_dir.parent
sys.path.insert(0, str(_backend_dir))

from dotenv import load_dotenv  # noqa: E402  — après le sys.path, par convention des scripts

for _candidate in (_project_root / ".env", _backend_dir / ".env"):
    if _candidate.exists():
        load_dotenv(_candidate)

from neo4j import GraphDatabase, Query  # noqa: E402
from neo4j.exceptions import (  # noqa: E402
    AuthError,
    ClientError,
    ConstraintError,
    CypherSyntaxError,
    DriverError,
    GqlError,
    Neo4jError,
    ServiceUnavailable,
)

# Les requêtes d'indexation que `Graphiti.__init__` exécutera sur ce serveur,
# prises **de la bibliothèque installée** et non recopiées : une liste recopiée
# ici aurait drifté au premier `uv lock`, et le contrôle mesurerait autre chose
# que ce qui sera exécuté.
from graphiti_core.driver.driver import GraphProvider  # noqa: E402
from graphiti_core.graph_queries import get_fulltext_indices, get_range_indices  # noqa: E402

# La requête que `camel` lance au `__init__` de son `Neo4jGraph`, importée et non
# recopiée. C'est elle qui décide d'APOC : la story 001-2 n'exerce pas le chemin
# d'écriture de `camel` — c'est hors périmètre, et les notes de développement
# l'excluent nommément — mais la **disponibilité** de la procédure, elle, se
# mesure, sinon « APOC est-il nécessaire ? » reste une supposition. Recopier le
# `YIELD` à la main testerait une autre requête que celle de `camel`.
from camel.storages.graph_storages.neo4j_graph import (  # noqa: E402
    NODE_PROPERTY_QUERY,
    EXCLUDED_LABELS,
)

# --------------------------------------------------------------------------
# Le graphe de vérification
# --------------------------------------------------------------------------

# Préfixe reconnaissable : on doit pouvoir retrouver et nettoyer ce qu'on a
# écrit sans ambiguïté, et ne pas confondre avec le graphe de l'épreuve (001-5).
LABEL = "MiroFishVerification"
SONDE_LABEL = "MiroFishTransactionSonde"
APOC_LABEL = "ApocSonde"
PREFIX = "mirofish-verification"
RELATION = "VERIFIES"
NODE_ALPHA = f"{PREFIX}-alpha"
NODE_BETA = f"{PREFIX}-beta"
APOC_NODE = f"{PREFIX}-apoc"

# Les noms d'index et de contrainte sont des **identifiants Cypher**, pas des
# valeurs : le tiret de `PREFIX` y est une faute de syntaxe, pas un caractère
# permis. On le remplace donc pour ces trois noms — mesuré, pas supposé : un
# `DROP CONSTRAINT mirofish-verification_unique` se fait rejeter par le serveur
# en `CypherSyntaxError`.
IDENTIFIANT = PREFIX.replace("-", "_")
FULLTEXT_INDEX = f"{IDENTIFIANT}_fulltext"
VECTOR_INDEX = f"{IDENTIFIANT}_vector"
UNIQUE_CONSTRAINT = f"{IDENTIFIANT}_unique"

# Trois dimensions suffisent et c'est volontaire : ce contrôle ne mesure pas la
# qualité d'un embedding, il vérifie que la procédure **existe** sur cette
# édition. Un vecteur de 1536 dimensions n'en dirait pas davantage.
VECTOR = [0.1, 0.2, 0.3]


# --------------------------------------------------------------------------
# Rapport
# --------------------------------------------------------------------------

@dataclass
class Check:
    """Un contrôle, son résultat, et le symbole de surface qu'il exerce.

    Trois états et non deux. `connu=True` marque un **écart mesuré, assumé et
    documenté** : ni le driver ni le serveur n'ont bougé, mais une
    fonctionnalité manque, et le rapport doit le dire sans le confondre avec un
    échec du driver. Un rapport binaire oblige à choisir entre « tout va bien »
    et « ça casse » — deux verdicts faux dès qu'un écart est connu.
    """

    name: str
    ok: bool
    detail: str
    surface: str = ""
    connu: bool = False


@dataclass
class Report:
    checks: list[Check] = field(default_factory=list)

    def add(self, name: str, ok: bool, detail: str, surface: str = "", connu: bool = False) -> Check:
        check = Check(name=name, ok=ok, detail=detail, surface=surface, connu=connu)
        self.checks.append(check)
        return check

    def guard(self, name: str, detail: str = "", surface: str = "") -> Check:
        """Un contrôle qui n'a pas pu être conduit : on le dit, on ne l'invente pas.

        Distinguer « échec » de « non conduit » coûte une ligne et évite le
        rapport qui prétend avoir tout mesuré alors qu'il a sauté la moitié.
        """
        return self.add(name, False, detail or "non conduit", surface)

    @property
    def failures(self) -> list[Check]:
        return [c for c in self.checks if not c.ok]

    @property
    def connus(self) -> list[Check]:
        return [c for c in self.checks if c.connu]

    def render(self, header: list[str]) -> str:
        lines = list(header) + [""]
        width = max((len(c.name) for c in self.checks), default=0)
        for check in self.checks:
            if check.ok:
                mark = "OK   "
            elif check.connu:
                mark = "CONNU"
            else:
                mark = "ÉCHEC"
            surface = f"  [{check.surface}]" if check.surface else ""
            lines.append(f"  {mark} {check.name.ljust(width)}{surface}")
            if check.detail:
                lines.append(f"         {check.detail}")
        lines.append("")
        passes = len(self.checks) - len(self.failures)
        lines.append(f"  {passes}/{len(self.checks)} contrôles passés")
        if self.connus:
            lignes = ", ".join(c.name for c in self.connus)
            lines.append(f"  {len(self.connus)} écart(s) connu(s) et documenté(s) : {lignes}")
        if self.failures:
            lines.append("  en échec : " + ", ".join(c.name for c in self.failures))
        return "\n".join(lines)


# --------------------------------------------------------------------------
# Connexion
# --------------------------------------------------------------------------

def lire_cible() -> tuple[str, str, str]:
    """`(uri, user, mot_de_passe)` depuis l'environnement, ou une erreur claire.

    Pas de mot de passe par défaut : un serveur qui démarrerait avec une valeur
    implicite serait un serveur dont personne n'a choisi le secret.
    """
    uri = os.environ.get("NEO4J_URI")
    user = os.environ.get("NEO4J_USER")
    password = os.environ.get("NEO4J_PASSWORD")
    manquants = [
        nom
        for nom, valeur in (("NEO4J_URI", uri), ("NEO4J_USER", user), ("NEO4J_PASSWORD", password))
        if not valeur
    ]
    if manquants:
        raise SystemExit(
            f"variable(s) absente(s) : {', '.join(manquants)}\n"
            "Elles se lisent dans le .env de la racine du dépôt, jamais versionné."
        )
    return uri, user, password


def version_serveur(driver) -> tuple[str, str]:
    """`(version, édition)` du serveur, lues du serveur et non de l'image.

    Une image peut être re-tagée ; `CALL dbms.components()` ne ment pas.
    """
    with driver.session() as session:
        rows = session.run("CALL dbms.components()").data()
    versions: set[str] = set()
    editions: set[str] = set()
    for row in rows:
        versions.update(row.get("versions") or [])
        if row.get("edition"):
            editions.add(row["edition"])
    return "/".join(sorted(versions)) or "?", "/".join(sorted(editions)) or "?"


def une_ligne(texte: object, largeur: int = 140) -> str:
    """La première ligne d'un message d'erreur, bornée.

    Le message complet d'une erreur Neo4j tient parfois en dix lignes ; dans un
    rapport, ce sont les cent premiers caractères qui font le diagnostic.
    """
    return str(texte).splitlines()[0][:largeur]


# --------------------------------------------------------------------------
# La surface de l'ADR 0011 — exercée, pas importée
# --------------------------------------------------------------------------

def controler_hierarchie(report: Report) -> None:
    """Les exceptions qu'ADR 0011 recense doivent être celles qu'elles sont.

    Importées, elles ne seraient que des noms ; lues dans la hiérarchie, elles
    sont une garantie. C'est la partie du contrat qu'un réintégrage de l'amont
    pourrait casser en silence : `camel` attrape `ClientError` pour en déduire
    « GDS absent » et `CypherSyntaxError` pour en déduire « Cypher invalide ».
    Si la hiérarchie bouge, ces déductions deviennent fausses — silencieusement.

    > **Ce contrôle a échoué une fois, et c'était le test qui avait tort.** La
    > première version affirmait `Neo4jError ⊂ DriverError`. Mesuré : les deux
    > sont des branches **sœurs** sous `GqlError`, le socle commun — d'où son
    > nom, *GraphQL error*. Ce n'est donc pas une dérive de 5.23 → 5.28, c'est
    > une hiérarchie qui n'a jamais été celle qu'on imaginait. L'assertion est
    > écrite sur ce qui est **vrai**, et le lien commun réel (`GqlError`) est
    > vérifié à côté. Ce que `camel` attrape (`ClientError`) est bien le bon
    > : il couvre les quatre, et il ne couvre ni `ServiceUnavailable` ni
    > `SessionExpired`, que le driver ne fait pas remonter dessous.
    """
    attendus = {
        "CypherSyntaxError ⊂ ClientError": issubclass(CypherSyntaxError, ClientError),
        "ConstraintError ⊂ ClientError": issubclass(ConstraintError, ClientError),
        "AuthError ⊂ ClientError": issubclass(AuthError, ClientError),
        "ClientError ⊂ Neo4jError": issubclass(ClientError, Neo4jError),
        "Neo4jError ⊂ GqlError": issubclass(Neo4jError, GqlError),
        "ServiceUnavailable ⊂ DriverError": issubclass(ServiceUnavailable, DriverError),
        "DriverError ⊂ GqlError": issubclass(DriverError, GqlError),
    }
    casses = [nom for nom, ok in attendus.items() if not ok]
    soeurs = not issubclass(Neo4jError, DriverError) and not issubclass(DriverError, Neo4jError)
    report.add(
        "hiérarchie d'exceptions",
        not casses,
        (
            f"les {len(attendus)} liens tiennent ; Neo4jError et DriverError sont bien "
            "sœurs sous GqlError, et ClientError couvre les trois que camel attrape"
            if soeurs
            else "les liens tiennent"
        )
        if not casses
        else "liens rompus : " + ", ".join(casses),
        surface="ADR 0011",
    )


def controler_driver(report: Report, uri: str, user: str, password: str):
    """`GraphDatabase.driver()` puis `verify_connectivity()` — l'ouverture."""
    try:
        driver = GraphDatabase.driver(uri, auth=(user, password))
    except Exception as exc:  # noqa: BLE001 — on veut le message de n'importe quelle panne
        report.guard("ouverture du driver", f"{type(exc).__name__} : {une_ligne(exc)}", surface="GraphDatabase.driver")
        return None
    try:
        driver.verify_connectivity()
    except (AuthError, ServiceUnavailable) as exc:
        report.guard("ouverture du driver", f"{type(exc).__name__} : {une_ligne(exc)}", surface="GraphDatabase.driver")
        driver.close()
        return None
    report.add(
        "ouverture du driver",
        True,
        f"GraphDatabase.driver({uri}) puis verify_connectivity()",
        surface="GraphDatabase.driver",
    )
    return driver


def controler_auth(report: Report, uri: str, user: str, password: str) -> None:
    """`AuthError` doit être levé, pas déduit.

    On ouvre un second driver avec un mot de passe faux. C'est une tentative
    d'authentification ratée et rien d'autre : la donnée écrite reste celle de
    la session légitime, et le serveur n'a aucun mécanisme à déclencher.
    """
    faux = password + "-volontairement-faux"
    driver = None
    try:
        driver = GraphDatabase.driver(uri, auth=(user, faux))
        with driver.session() as session:
            session.run("RETURN 1")
    except AuthError as exc:
        report.add("AuthError sur mot de passe faux", True, f"{type(exc).__name__} : {une_ligne(exc, 100)}", surface="exceptions")
    except Exception as exc:  # noqa: BLE001
        report.guard(
            "AuthError sur mot de passe faux",
            f"{type(exc).__name__} au lieu de AuthError : {une_ligne(exc)}",
            surface="exceptions",
        )
    else:
        report.guard(
            "AuthError sur mot de passe faux",
            "aucune erreur : le serveur accepte n'importe quel mot de passe ?",
            surface="exceptions",
        )
    finally:
        if driver is not None:
            driver.close()


def controler_indisponible(report: Report, user: str) -> None:
    """`ServiceUnavailable` doit être levé sur un port où rien n'écoute.

    Le port vient d'une socket liée sur un port éphémère puis refermée : il est
    donc libre par construction, sans course possible avec un autre service du
    poste — contrairement à un port en dur, qui serait libre aujourd'hui et
    occupé la prochaine fois que le protocole est rejoué.
    """
    probe = socket.socket()
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
    probe.close()

    driver = GraphDatabase.driver(f"bolt://127.0.0.1:{port}", auth=(user, "peu-importe"), connection_timeout=5)
    try:
        driver.verify_connectivity()
    except ServiceUnavailable as exc:
        report.add(
            "ServiceUnavailable sur port fermé",
            True,
            f"port {port} : {type(exc).__name__} : {une_ligne(exc, 100)}",
            surface="exceptions",
        )
    except Exception as exc:  # noqa: BLE001
        report.guard(
            "ServiceUnavailable sur port fermé",
            f"{type(exc).__name__} au lieu de ServiceUnavailable : {une_ligne(exc)}",
            surface="exceptions",
        )
    else:
        report.guard("ServiceUnavailable sur port fermé", "aucune erreur sur un port où rien n'écoute", surface="exceptions")
    finally:
        driver.close()


def controler_query(report: Report, driver) -> None:
    """`Query` — la forme que `camel/storages/.../neo4j_graph.py:229` utilise.

    On reproduit l'appel exact : `session.run(Query(text=..., timeout=...), params)`.
    Une requête paramétrée, parce qu'une `Query` jamais paramétrée n'exerce pas
    le chemin que `camel` prend.
    """
    attendu = [{"a": PREFIX, "b": 1}]
    try:
        with driver.session() as session:
            obtenu = session.run(
                Query(text="RETURN $a AS a, $b AS b", timeout=10.0),
                {"a": PREFIX, "b": 1},
            ).data()
    except Exception as exc:  # noqa: BLE001
        report.guard("Query paramétrée", f"{type(exc).__name__} : {une_ligne(exc)}", surface="Query")
        return
    report.add(
        "Query paramétrée",
        obtenu == attendu,
        f"Query(text=..., timeout=...) puis .data() : {obtenu}"
        if obtenu == attendu
        else f"renvoie {obtenu}, attendu {attendu}",
        surface="Query",
    )


def controler_transactions(report: Report, driver) -> None:
    """Les trois transactions que le code amont utilise, pas seulement une.

    - `session.execute_write(fn, ...)` — la transaction gérée ;
    - `session.write_transaction(fn, ...)` et `session.read_transaction(fn, ...)`
      — dépréciées en 5.x, mais **c'est ce qu'appelle**
      `oasis/social_agent/agent_graph.py:34-46`. Déprécié ne veut pas dire
      retiré : si 5.28.6 les avait supprimées, `oasis` casserait à l'exécution
      sans qu'aucune résolution ne l'ait dit. On note donc ce que le driver dit
      de sa propre dépréciation, au lieu de la supposer muette.
    """

    def _ecrire(tx, valeur):
        requete = f"CREATE (n:{SONDE_LABEL} {{valeur: $v}}) RETURN n.valeur AS v"
        return tx.run(requete, v=valeur).single()["v"]

    for nom, appeler in (
        ("execute_write", lambda s: s.execute_write(_ecrire, "sonde-execute-write")),
        ("write_transaction", lambda s: s.write_transaction(_ecrire, "sonde-write-transaction")),
        ("read_transaction", lambda s: s.read_transaction(lambda tx: tx.run("RETURN 1 AS v").single()["v"])),
    ):
        with warnings.catch_warnings(record=True) as attrape:
            warnings.simplefilter("always")
            try:
                with driver.session() as session:
                    valeur = appeler(session)
            except Exception as exc:  # noqa: BLE001
                report.guard(f"transaction gérée — {nom}", f"{type(exc).__name__} : {une_ligne(exc)}", surface="transactions")
                continue
        deprecations = [str(w.message) for w in attrape if issubclass(w.category, DeprecationWarning)]
        rapport = f"session.{nom}() renvoie {valeur!r}"
        if deprecations:
            rapport += f" — dépréciée, présente : {une_ligne(deprecations[0], 90)}"
        report.add(f"transaction gérée — {nom}", True, rapport, surface="transactions")

    with driver.session() as session:
        session.run(f"MATCH (n:{SONDE_LABEL}) DELETE n")


def controler_exceptions_client(report: Report, driver) -> None:
    """`ClientError` et `CypherSyntaxError`, obtenus pour de vrai.

    Deux erreurs distinctes, donc deux contrôles :

    - une **contrainte d'unicité violée** : la base est en cause, pas la
      requête. `camel` attrape `ClientError` pour en déduire « GDS absent », et
      c'est exactement cette déduction qu'un `ClientError` mal placé rendrait
      fausse ;
    - une **faute de syntaxe** : `CypherSyntaxError`, sous-classe de
      `ClientError`. `camel` la déguise en `ValueError("Cypher invalide")` — si
      la sous-classe remontait plate, ce message mentirait.
    """
    with driver.session() as session:
        session.run(f"DROP CONSTRAINT {UNIQUE_CONSTRAINT} IF EXISTS")
        session.run(f"CREATE CONSTRAINT {UNIQUE_CONSTRAINT} IF NOT EXISTS FOR (n:{LABEL}) REQUIRE n.name IS UNIQUE")

    doublon = f"{PREFIX}-contrainte"
    creation = f"CREATE (:{LABEL} {{name: $n}})"
    try:
        with driver.session() as session:
            session.run(creation, n=doublon)
            session.run(creation, n=doublon)
    except ConstraintError as exc:
        report.add(
            "ClientError sur contrainte violée",
            True,
            f"{type(exc).__name__} ⊂ ClientError : {une_ligne(exc, 110)}",
            surface="exceptions",
        )
    except Exception as exc:  # noqa: BLE001
        report.guard(
            "ClientError sur contrainte violée",
            f"{type(exc).__name__} au lieu de ConstraintError/ClientError : {une_ligne(exc)}",
            surface="exceptions",
        )
    else:
        report.guard("ClientError sur contrainte violée", "la contrainte d'unicité n'a pas été levée", surface="exceptions")

    try:
        with driver.session() as session:
            session.run("RETURN 1 AS")
    except CypherSyntaxError as exc:
        report.add(
            "CypherSyntaxError sur requête invalide",
            True,
            f"{type(exc).__name__} ⊂ ClientError : {une_ligne(exc, 110)}",
            surface="exceptions",
        )
    except Exception as exc:  # noqa: BLE001
        report.guard(
            "CypherSyntaxError sur requête invalide",
            f"{type(exc).__name__} au lieu de CypherSyntaxError : {une_ligne(exc)}",
            surface="exceptions",
        )
    else:
        report.guard("CypherSyntaxError sur requête invalide", "la requête invalide n'a pas été refusée", surface="exceptions")

    with driver.session() as session:
        session.run(f"MATCH (n:{LABEL} {{name: $n}}) DELETE n", n=doublon)
        session.run(f"DROP CONSTRAINT {UNIQUE_CONSTRAINT} IF EXISTS")


# --------------------------------------------------------------------------
# Les procédures de graphiti-core, et APOC
# --------------------------------------------------------------------------

def preparer_procedures(driver) -> None:
    """Index fulltext et vector, seuls objets d'un test de procédure.

    Les requêtes sont **interpolées**, pas paramétrées : un nom d'index ne peut
    pas être un paramètre en Cypher. Toutes les valeurs viennent de constantes
    du module, aucune n'est une entrée utilisateur — l'injection n'a pas de
    source.
    """
    with driver.session() as session:
        session.run(f"DROP INDEX {FULLTEXT_INDEX} IF EXISTS")
        session.run(f"DROP INDEX {VECTOR_INDEX} IF EXISTS")
        session.run(f"CREATE FULLTEXT INDEX {FULLTEXT_INDEX} IF NOT EXISTS FOR (n:{LABEL}) ON EACH [n.name]")
        session.run(
            f"CREATE VECTOR INDEX {VECTOR_INDEX} IF NOT EXISTS FOR (n:{LABEL}) ON (n.embedding) "
            "OPTIONS {indexConfig: {`vector.dimensions`: 3, `vector.similarity_function`: 'cosine'}}"
        )


def controler_procedures(report: Report, driver) -> None:
    """Les procédures que `graphiti-core==0.30.2` appelle, sur ce serveur.

    C'est la tâche 7 de la story, et elle est **mesurée** : si l'une de ces
    procédures était absente de l'édition Community, l'épreuve de la 001-5
    échouerait pour une raison qui n'a rien à voir avec l'extraction, et mieux
    vaut le savoir maintenant.

    Sur le chemin Neo4j, `graphiti-core` n'utilise que deux procédures, et
    toutes deux sont **natives** à Neo4j 5 — `db.create.setNodeVectorProperty`
    pour poser un embedding, `db.index.fulltext.queryNodes` pour la recherche.
    C'est le fait que ce contrôle vérifie, pas une supposition : si l'une des
    deux demandait APOC, elle échouerait ici sur une installation sans plugin.

    Les variantes `db.idx.fulltext.createNodeIndex` et
    `db.index.fulltext.queryRelationships` appartiennent à d'autres
    fournisseurs ou à d'autres chemins ; elles ne sont pas exercées ici, et le
    dire évite de laisser croire à un relevé exhaustif.
    """
    preparer_procedures(driver)

    etapes = (
        (
            "db.create.setNodeVectorProperty",
            f"MERGE (n:{LABEL} {{name: $nom}}) SET n.embedding = [0.0, 0.0, 0.0] "
            "WITH n CALL db.create.setNodeVectorProperty(n, 'embedding', $v) RETURN n.name AS nom",
            {"nom": NODE_ALPHA, "v": VECTOR},
            lambda ligne: ligne["nom"] == NODE_ALPHA,
        ),
        (
            "db.index.fulltext.queryNodes",
            f"CALL db.index.fulltext.queryNodes('{FULLTEXT_INDEX}', $q) YIELD node, score "
            "RETURN node.name AS nom ORDER BY score DESC LIMIT 1",
            {"q": NODE_ALPHA},
            lambda ligne: ligne["nom"] == NODE_ALPHA,
        ),
    )
    for nom, requete, params, verifie in etapes:
        try:
            with driver.session() as session:
                ligne = session.run(requete, params).single()
                obtenu = dict(ligne) if ligne else None
        except Exception as exc:  # noqa: BLE001
            report.guard(
                f"procédure native {nom}",
                f"{type(exc).__name__} : {une_ligne(exc)}",
                surface="Graphiti",
            )
            continue
        report.add(
            f"procédure native {nom}",
            obtenu is not None and verifie(obtenu),
            f"disponible et vérifiée : {obtenu}",
            surface="Graphiti",
        )


def controler_index_de_verification(report: Report, driver) -> None:
    """Les deux index de la sonde, visibles par `SHOW INDEXES`.

    `SHOW INDEXES` et non `CALL db.indexes()` : la seconde forme est celle que
    `graphiti-core` utilise dans `delete_all_indexes`, et elle n'existe plus sur
    un serveur 5.x — voir `controler_procedure_absente`, qui le consigne. Une
    commande d'administration n'est pas une procédure, et le nom le laisse croire.
    """
    try:
        with driver.session() as session:
            noms = [ligne["name"] for ligne in session.run("SHOW INDEXES").data()]
    except Exception as exc:  # noqa: BLE001
        report.guard("index de la sonde visibles", f"{type(exc).__name__} : {une_ligne(exc)}", surface="Graphiti")
        return
    attendus = [FULLTEXT_INDEX, VECTOR_INDEX]
    presents = [nom for nom in attendus if nom in noms]
    report.add(
        "index de la sonde visibles",
        len(presents) == len(attendus),
        f"SHOW INDEXES renvoie {presents} sur {attendus} attendus",
        surface="Graphiti",
    )


def controler_schema_graphiti(report: Report, driver) -> None:
    """Le schéma que `Graphiti.__init__` construira, exécuté sur ce serveur.

    `build_indices_and_constraints()` part en tâche de fond dès le constructeur
    du driver (`neo4j_driver.py:96`) : si une seule de ses requêtes est refusée
    ici, elle le sera aussi à la 001-5, et l'extraction échouerait sur un
    détail de schéma qu'aucune résolution de dépendances ne peut voir.

    Les requêtes viennent de `graphiti_core.graph_queries`, **pas d'une copie** :
    c'est le cœur du chemin Neo4j de Graphiti — 4 index fulltext et 27 index
    range. On les crée, on vérifie leur présence par `SHOW INDEXES`, puis on les
    supprime tous, pour ne pas laisser derrière soi un graphe d'épreuve pollué.

    > `db.idx.fulltext.createNodeIndex` n'apparaît pas dans ce compte : c'est la
    > variante **FalkorDB** et **Kuzu**. Un relevé par `grep 'CALL db.'` sur le
    > paquet ne distingue pas les fournisseurs, et il surestime le nombre de
    > procédures utilisées sur Neo4j. C'est pour cela que la liste est tirée
    > de la bibliothèque, avec le fournisseur Neo4j, au lieu d'être recomptée.
    """
    fulltext = get_fulltext_indices(GraphProvider.NEO4J)
    rangee = get_range_indices(GraphProvider.NEO4J)
    noms = re.findall(r"INDEX\s+([A-Za-z_][A-Za-z_0-9]*)", "\n".join(fulltext + rangee))
    attendus = set(noms)

    avec_avant = set()
    try:
        with driver.session() as session:
            for requete in fulltext + rangee:
                session.run(requete).consume()
            avec_avant = {ligne["name"] for ligne in session.run("SHOW INDEXES").data()}
    except Exception as exc:  # noqa: BLE001
        creer = f"{type(exc).__name__} : {une_ligne(exc)}"
        avec_avant = set()
    else:
        creer = f"{len(fulltext)} index fulltext et {len(rangee)} index range créés"

    crees = attendus & avec_avant
    report.add(
        "schéma Graphiti (index fulltext + range)",
        len(crees) == len(attendus),
        f"{creer} — {len(crees)}/{len(attendus)} déclarés et visibles dans SHOW INDEXES",
        surface="Graphiti",
    )

    manquants = sorted(attendus - avec_avant)
    if manquants:
        report.add(
            "index Graphiti tous visibles",
            False,
            "non visibles dans SHOW INDEXES : " + ", ".join(manquants[:6]) + ("…" if len(manquants) > 6 else ""),
            surface="Graphiti",
        )

    with driver.session() as session:
        for nom in sorted(attendus & avec_avant):
            session.run(f"DROP INDEX {nom}").consume()

    controler_procedure_absente(report, driver, "CALL db.indexes() YIELD name")


def controler_procedure_absente(report: Report, driver, requete: str, surface: str = "Graphiti") -> None:
    """Une requête de la bibliothèque que ce serveur **ne** sait pas exécuter.

    On ne l'ignore pas et on ne la déclare pas cassée : on la mesure, et on
    consigne qui l'appelle et à quel moment. `CALL db.indexes()` est
    `delete_all_indexes` — atteint uniquement avec `delete_existing=True`, donc
    hors du chemin d'écriture d'épisodes. Un jour où la 001-5 voudra repartir
    de zéro par cette voie, elle butera dessus, et ce sera écrit ici plutôt
    que redécouvert.
    """
    try:
        with driver.session() as session:
            session.run(requete).consume()
    except ClientError as exc:
        report.add(
            f"{requete.splitlines()[0]} — absente, hors chemin d'écriture",
            True,
            f"{type(exc).__name__} : {une_ligne(exc, 120)} — relevée, elle pèse sur "
            "`build_indices_and_constraints(delete_existing=True)`, jamais sur `add_episode`",
            surface=surface,
            connu=True,
        )
    except Exception as exc:  # noqa: BLE001
        report.guard(f"{requete.splitlines()[0]} — absente, hors chemin d'écriture", f"{type(exc).__name__} : {une_ligne(exc)}", surface=surface)
    else:
        report.add(
            f"{requete.splitlines()[0]} — absente, hors chemin d'écriture",
            True,
            "disponible en fait : la mesure précédente datait d'une version de serveur antérieure",
            connu=True,
        )


def controler_apoc(report: Report, driver, attendu: str) -> None:
    """APOC est-il là ? La question de la tâche 7, répondue par la mesure.

    On exécute **la requête de `camel` elle-même** —
    `camel/storages/graph_storages/neo4j_graph.py:28`, celle que
    `refresh_schema()` lance dès le `__init__` de `Neo4jGraph`. Une
    approximation aurait répondu à une autre question : c'est ce
    `YIELD label, other, elementType, type, property` précis qui peut manquer, et
    une approximation qui marche ne prouverait rien sur lui.

    Ensuite on écrit un nœud **par `apoc.merge.node`**, la procédure
    d'écriture qu'utilise `add_nodes_from_df`, et on se relit. Un plugin
    installé mais muet sur les procédures d'écriture est plus trompeur que son
    absence : le message dit alors « plugin non installé » alors qu'il l'est —
    et `camel` est justement écrit pour dire cela.

    `--apoc` déclare ce que le protocole **attend** : `attendu`, `absent`, ou
    `indifférent`. Sans cette déclaration, « APOC répond » et « APOC est
    installé » seraient la même ligne, et la mesure ne décrirait pas le serveur
    qu'elle a réellement trouvé.
    """
    etiquette_apoc = APOC_LABEL
    try:
        with driver.session() as session:
            # La requête de `camel`, verbatim : c'est elle qui décide d'APOC.
            session.run(NODE_PROPERTY_QUERY, EXCLUDED_LABELS=EXCLUDED_LABELS).data()
            version = session.run("RETURN apoc.version() AS version").single()["version"]

            # Écriture par `apoc.merge.node`, comme `add_nodes_from_df` — deux
            # appels, pas un. Le premier crée avec `onCreateProps`, le second
            # passe par `onMatchProps`. Un seul appel ne prouverait que la
            # création : `onCreate` et `onMatch` sont deux chemins distincts
            # dans la procédure, et c'est `onMatch` que `camel` déclenche à
            # chaque réimport d'une entité déjà connue.
            # Étiquette éphémère par exécution, pour qu'un nœud laissé par un
            # passage précédent n'aille pas faire passer la sonde pour un
            # `onCreate` qui n'a pas eu lieu. Uniquement des lettres et des
            # chiffres : le tiret de `APOC_LABEL` serait une faute de syntaxe
            # dans `MATCH (n:…)`, et l'erreur direait « APOC indisponible » au
            # lieu de dire la vérité.
            etiquette_apoc = f"{APOC_LABEL}{uuid.uuid4().hex[:8]}"
            fusion = (
                "CALL apoc.merge.node($labels, {id: $id}, {vu: false}, {vu: true}) "
                "YIELD node RETURN node.id AS id"
            )
            cree = session.run(fusion, labels=[etiquette_apoc], id=APOC_NODE).single()
            relu = session.run(fusion, labels=[etiquette_apoc], id=APOC_NODE).single()
            vu = session.run(
                f"MATCH (n:{etiquette_apoc} {{id: $id}}) RETURN n.vu AS vu",
                id=APOC_NODE,
            ).single()["vu"]
    except Exception as exc:  # noqa: BLE001
        # Le nœud de la sonde est effacé même quand la sonde échoue : une
        # étiquette éphémère laissée en base ferait échouer les relectures
        # suivantes, et le protocole doit être rejouable sans nettoyage manuel —
        # c'est NFR-3, pas une précaution de confort.
        try:
            with driver.session() as session:
                session.run(f"MATCH (n:{etiquette_apoc}) DETACH DELETE n").consume()
        except Exception:  # noqa: BLE001, S110 — un nettoyage raté ne doit pas masquer l'erreur d'origine
            pass
        if attendu == "absent":
            report.add("APOC", True, f"absent comme le protocole l'annonce : {type(exc).__name__} : {une_ligne(exc, 100)}")
        elif attendu == "attendu":
            report.add(
                "APOC",
                False,
                f"attendu, et indisponible : {type(exc).__name__} : {une_ligne(exc)}",
                surface="camel-oasis",
            )
        else:
            report.add("APOC", True, f"indisponible, sans attente déclarée : {type(exc).__name__}")
        return
    if attendu == "absent":
        report.add(
            "APOC",
            False,
            "annoncé absent, et pourtant disponible : cette mesure ne décrit pas le serveur qu'elle a trouvé",
        )
    elif cree is None or relu is None or not vu:
        report.add(
            "APOC",
            False,
            f"apoc.merge.node n'a pas produit de nœud exploitable "
            f"(création={cree}, relecture={relu}, vu={vu}) : la sonde ne prouve pas "
            "que la procédure d'écriture agit",
            surface="camel-oasis",
        )
    else:
        report.add(
            "APOC",
            True,
            f"APOC {version} : la requête de camel (apoc.meta.data) répond, et apoc.merge.node "
            f"crée (onCreate) puis met à jour (onMatch) — relu vu={vu}",
            surface="camel-oasis",
        )

    with driver.session() as session:
        session.run(f"MATCH (n:{etiquette_apoc}) DETACH DELETE n").consume()


# --------------------------------------------------------------------------
# Écriture et relecture
# --------------------------------------------------------------------------

def ecrire_graphe(report: Report, driver) -> None:
    """Deux nœuds et une arête, dans une transaction gérée.

    Le graphe de vérification est **remis à zéro d'abord**. Sans cela, un `MERGE`
    sur un nœud déjà présent ne recrée rien, et la relecture qui suit prouverait
    la persistance d'une **exécution précédente** — ce qui est vrai, mais pas
    ce qu'on veut mesurer : deux protocoles lancés à la suite se contamineraient,
    et le second annoncerait un succès qui serait celui du premier. Chaque
    exécution écrit donc ce qu'elle va relire, et rien d'autre ne peut.

    Noms reconnaissables (`mirofish-verification-…`) pour les retrouver et les
    nettoyer sans ambiguïté. `valid_at` est posé parce que le critère C4 de
    l'épreuve portera dessus : mieux vaut l'écrire ici, sous un graphe de
    vérification, que le découvrir à la 001-5.
    """
    horodatage = datetime.now(timezone.utc).isoformat()

    def _remettre_a_zero(tx):
        tx.run(
            f"MATCH (n:{LABEL}) WHERE n.name IN $noms DETACH DELETE n",
            noms=[NODE_ALPHA, NODE_BETA],
        ).consume()

    def _creer(tx):
        tx.run(
            f"MERGE (a:{LABEL} {{name: $nom}}) ON CREATE SET a.genre = 'verification', "
            "a.created_at = datetime($ts) SET a.embedding = $vec",
            nom=NODE_ALPHA,
            ts=horodatage,
            vec=VECTOR,
        ).single()
        tx.run(
            f"MERGE (b:{LABEL} {{name: $nom}}) ON CREATE SET b.genre = 'verification', "
            "b.created_at = datetime($ts)",
            nom=NODE_BETA,
            ts=horodatage,
        ).single()
        tx.run(
            f"MATCH (a:{LABEL} {{name: $alpha}}), (b:{LABEL} {{name: $beta}}) "
            f"MERGE (a)-[r:{RELATION}]->(b) ON CREATE SET r.valid_at = datetime($ts), r.poids = 1.0 "
            "RETURN r.valid_at AS valid_at",
            alpha=NODE_ALPHA,
            beta=NODE_BETA,
            ts=horodatage,
        ).single()

    try:
        with driver.session() as session:
            session.execute_write(_remettre_a_zero)
            session.execute_write(_creer)
    except Exception as exc:  # noqa: BLE001
        report.guard("écriture du graphe de vérification", f"{type(exc).__name__} : {une_ligne(exc)}")
        return

    with driver.session() as session:
        compte = session.run(
            f"MATCH (n:{LABEL}) WHERE n.name IN $noms RETURN count(n) AS n",
            noms=[NODE_ALPHA, NODE_BETA],
        ).single()["n"]
    report.add(
        "écriture du graphe de vérification",
        compte == 2,
        f"deux transactions gérées : remise à zéro puis 2 nœuds {LABEL} et une arête "
        f"{RELATION} (valid_at={horodatage}), {compte} nœud(s) de la sonde en base",
    )


def relire_graphe(report: Report, driver) -> None:
    """Le graphe écrit est-il relisible, arête et horodatage compris ?

    La phase `relire` **échoue** si le graphe n'est pas là : c'est le critère C3,
    et son porteur doit pouvoir le constater par le code de sortie, pas en
    relisant un rapport pour deviner.
    """
    with driver.session() as session:
        noms = [
            ligne["nom"]
            for ligne in session.run(
                f"MATCH (n:{LABEL}) WHERE n.name IN $noms RETURN n.name AS nom ORDER BY n.name",
                noms=[NODE_ALPHA, NODE_BETA],
            ).data()
        ]
        arete = session.run(
            f"MATCH (a:{LABEL})-[r:{RELATION}]->(b:{LABEL}) WHERE a.name = $alpha "
            "RETURN a.name AS source, b.name AS cible, r.valid_at AS valid_at",
            alpha=NODE_ALPHA,
        ).single()

    attendus = sorted([NODE_ALPHA, NODE_BETA])
    if noms != attendus:
        report.add(
            "relecture après redémarrage",
            False,
            f"nœuds attendus {attendus}, trouvés {noms} — le volume nommé n'a pas tenu, "
            "ou l'écriture n'a jamais eu lieu",
        )
        return
    if arete is None or not arete["valid_at"]:
        report.add(
            "relecture après redémarrage",
            False,
            f"les deux nœuds sont là, mais l'arête {RELATION} n'a pas de valid_at : {dict(arete) if arete else None}",
        )
        return
    report.add(
        "relecture après redémarrage",
        True,
        f"{noms} reliés par {RELATION}, valid_at={arete['valid_at']} — le volume nommé a tenu",
    )


def nettoyer(driver) -> int:
    """Tout ce que la sonde a laissé, y compris les étiquettes éphémères.

    Le motif `STARTS WITH` sur les étiquettes est nécessaire : la sonde APOC
    crée un suffixe unique par exécution, donc une liste figée d'étiquettes
    laisserait un résidu à chaque passage. C'est le principe du protocole
    rejouable — un `nettoyer` qui ne nettoie que la moitié de ce que la sonde
    écrit est un `nettoyer` qui ment.
    """
    with driver.session() as session:
        session.run(f"DROP INDEX {FULLTEXT_INDEX} IF EXISTS")
        session.run(f"DROP INDEX {VECTOR_INDEX} IF EXISTS")
        session.run(f"DROP CONSTRAINT {UNIQUE_CONSTRAINT} IF EXISTS")
        return session.run(
            "MATCH (n) WHERE any(l IN labels(n) WHERE l IN $prefixes OR l STARTS WITH $apoc) "
            "DETACH DELETE n",
            prefixes=[LABEL, APOC_LABEL, SONDE_LABEL],
            apoc=APOC_LABEL,
        ).consume().counters.nodes_deleted


# --------------------------------------------------------------------------
# Programme
# --------------------------------------------------------------------------

def executer(phase: str, attente_apoc: str) -> int:
    uri, user, password = lire_cible()
    report = Report()

    driver = controler_driver(report, uri, user, password)
    if driver is None:
        print(
            report.render(
                [
                    f"Test comportemental du driver forcé — story 001-2 — phase « {phase} »",
                    "  aucun driver ouvert : la suite n'a pas été conduite",
                ]
            )
        )
        return 1

    try:
        version_driver = distribution_version("neo4j")
        version, edition = version_serveur(driver)
        en_tete = [
            f"Test comportemental du driver forcé — story 001-2 — phase « {phase} »",
            f"  horodatage : {datetime.now(timezone.utc).isoformat(timespec='seconds')}",
            f"  driver     : neo4j {version_driver} (locké par backend/uv.lock, forcé par l'override de l'ADR 0010)",
            f"  serveur    : Neo4j {version} ({edition})",
            f"  cible      : {uri}",
            f"  APOC       : attendu = {attente_apoc}",
            f"  écart      : driver {version_driver} / serveur {version} — assumé, et c'est l'objet de la mesure",
        ]

        controler_hierarchie(report)
        controler_auth(report, uri, user, password)
        controler_indisponible(report, user)
        controler_query(report, driver)
        controler_transactions(report, driver)
        controler_exceptions_client(report, driver)
        controler_schema_graphiti(report, driver)
        controler_procedures(report, driver)
        controler_index_de_verification(report, driver)
        controler_apoc(report, driver, attente_apoc)

        if phase == "ecrire":
            ecrire_graphe(report, driver)
        elif phase == "relire":
            relire_graphe(report, driver)
        else:
            effaces = nettoyer(driver)
            report.add("nettoyage", True, f"{effaces} nœud(s) de vérification supprimés, index et contrainte retirés")
    finally:
        driver.close()

    print(report.render(en_tete))
    return 1 if report.failures else 0


def main(argv: list[str] | None = None) -> int:
    analyseur = argparse.ArgumentParser(description="Test comportemental du driver neo4j forcé (story 001-2)")
    analyseur.add_argument("phase", choices=("ecrire", "relire", "nettoyer"))
    analyseur.add_argument(
        "--apoc",
        choices=("attendu", "absent", "indifférent"),
        default="indifférent",
        help="ce que le protocole attend du plugin APOC sur le serveur mesuré",
    )
    arguments = analyseur.parse_args(argv)
    return executer(arguments.phase, arguments.apoc)


if __name__ == "__main__":
    sys.exit(main())
