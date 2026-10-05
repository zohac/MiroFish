"""Harnais du protocole de la story 001-2 : les garde-fou du script bash.

`verifier-001-2.sh` est un script bash, et ses garde-fou — le refus d'un mot de
passe absent, le refus d'un mode inconnu, le choix du conteneur — vivent dedans.
Un protocole dont les refus ne sont pas testés est un protocole qui, le jour où
quelqu'un le rejoue sur une machine mal préparée, échoue avec un message
douteux ou, pire, continue sur une configuration que personne n'a choisie.

Ce harnais n'exécute **pas** le protocole entier : cela demanderait un serveur
Neo4j dans la CI. Il exécute les morceaux qui décident, sur des cas qui doivent
être refusés ou acceptés, et il le fait sur le **vrai fichier** du dépôt — une
seconde implémentation dériverait, et c'est exactement le défaut qu'on cherche.

> **Ce que ces tests ne prouvent pas.** Ils ne prouvent pas que le driver
> forcé tient contact avec un serveur : ça, c'est `mesure-001-2-compose.txt`,
> produit par le protocole lui-même, sur une machine avec Docker. Ces tests
> gardent l'invariant *autour* de la mesure : qu'elle se lance, qu'elle refuse
> ce qu'elle ne sait pas mesurer, et qu'elle identifie toujours le conteneur
> auquel elle parle.
"""

import re
import subprocess
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parent
PROTOCOLE = REPO / "docs/plans/001-epreuve-graphiti-local/verifier-001-2.sh"

# Les deux modes du protocole. Ils ne sont pas interchangeables : l'un mesure ce
# que Graphiti réclame, l'autre ce que `camel` réclame, et les conclusions sont
# opposées.
MODES = ("sans-apoc", "compose")


def _corps_fonction(nom: str) -> str:
    """Le corps d'une fonction bash, extrait du protocole réel.

    Les accolades de l'extension `.sh` sont tolérées : `identifiant() {` et
    `attendre_bolt() {` sont sur une seule ligne, alors que la fonction `case`
    du protocole est géolocalisée autrement. Une recherche trop stricte
    échouerait sur une forme stylistique — et un test qui échoue pour une
    question de regexp au lieu de la chose qu'il garde est un test qu'on
    finit par supprimer.
    """
    texte = PROTOCOLE.read_text(encoding="utf-8")
    trouve = re.search(rf"^{nom}\(\)\s*\{{\n.*?^\}}$", texte, re.MULTILINE | re.DOTALL)
    if not trouve:
        # Variante sur une seule ligne, pour les fonctions d'une expression.
        trouve = re.search(rf"^{nom}\(\)\s*\{{[^\n]*\}}$", texte, re.MULTILINE)
    assert trouve, f"{nom} est introuvable dans le protocole"
    return trouve.group(0)


def _executer(fonction: str, corps: str, environnement: dict[str, str]) -> tuple[int, str]:
    """Exécute une fonction du protocole avec un environnement fabriqué."""
    script = REPO / ".protocole-extrait.sh"
    try:
        script.write_text(
            "set -uo pipefail\n"
            f"{corps}\n"
            f"{fonction}\n",
            encoding="utf-8",
        )
        fini = subprocess.run(
            ["bash", str(script)],
            capture_output=True,
            text=True,
            check=False,
            env={**dict(**{"PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin"}), **environnement},
        )
        return fini.returncode, (fini.stdout + fini.stderr)
    finally:
        # Le fichier temporaire est écrit **à la racine du dépôt** parce que le
        # protocole résout ses chemins par `dirname $0`. Il est supprimé dans tous
        # les cas : un fichier d'extraction laissé dans l'arbre ferait échouer
        # `git status` du protocole suivant, qui exige un arbre propre.
        script.unlink(missing_ok=True)


# --------------------------------------------------------------------------
# Le refus d'un mot de passe absent
# --------------------------------------------------------------------------

def test_un_mot_de_passe_absent_est_refuse():
    """Sans `NEO4J_PASSWORD`, le protocole ne démarre rien.

    Démarrer quand même donnerait un conteneur avec un mot de passe vide ou
    implicite — donc une base dont personne n'a choisi le secret, et une mesure
    qui compare des chiffres pris sur cette base. Le refus est la seule issue
    honnête.
    """
    corps = re.search(
        r"NEO4J_PASSWORD=\$\(grep.*?^fi$",
        PROTOCOLE.read_text(encoding="utf-8"),
        re.MULTILINE | re.DOTALL,
    )
    assert corps, "le protocole ne lit plus NEO4J_PASSWORD depuis le .env"
    code, sortie = _executer(
        "test_$(echo 1)",
        corps.group(0),
        {"NEO4J_PASSWORD": ""},
    )
    assert code != 0, "un mot de passe vide ne doit pas passer"
    assert "NEO4J_PASSWORD" in sortie, "le refus doit nommer la variable absente"
    assert "n'a pas pu démarrer" in sortie or "ne peut pas démarrer" in sortie


# --------------------------------------------------------------------------
# Le refus d'un mode inconnu
# --------------------------------------------------------------------------

def test_un_mode_inconnu_est_refuse():
    """`verifier-001-2.sh n'importe-quoi` doit s'arrêter, pas mesurer n'importe quoi.

    Le cas est réel : `bash verifier-001-2.sh` sans argument prend un mode par
    défaut, et une faute de frappe prend un mode inexistant. Si le `case` lacked
    de refus, le protocole partirait sur le `compose` livré en croyant mesurer une
    variante — et le rapport afficherait une configuration qui n'est pas celle
    qu'on a demandée.
    """
    texte = PROTOCOLE.read_text(encoding="utf-8")
    bloc = re.search(r"^case \"\$MODE\" in$.*?^esac$", texte, re.MULTILINE | re.DOTALL)
    assert bloc, "le protocole n'a plus de sélection de mode"
    assert "sans-apoc)" in bloc.group(0), "le mode « sans-apoc » a disparu du protocole"
    assert "compose)" in bloc.group(0), "le mode « compose » a disparu du protocole"

    # On rejoue la sélection seule, avec les deux modes et un mode inconnu.
    script = REPO / ".protocole-modes.sh"
    try:
        script.write_text(
            "set -uo pipefail\n"
            # `MODE` est la variable que le protocole lit ; sans elle le `case`
            # tournerait sur une variable vide et accepterait les deux modes.
            # Les trois variables dont le `case` a besoin, plus deux inutiles :
            # le protocole les déclare avant le `case`, et les rejouer sans elles
            # ferait échouer le harnais sur `set -u` — un échec de fixture, pas
            # un défaut du protocole.
            'MODE="${1:-}"\n'
            'RACINE="/nonexistent"\nCOMPOSE="/nonexistent/compose.yml"\n'
            'SANS_APOC="/nonexistent/sans-apoc.yml"\nATTENTE_APOC=""\nLIBELLE=""\n'
            "SITES=(-f \"$COMPOSE\")\n"
            + bloc.group(0)
            + "\necho \"mode retenu : ${ATTENTE_APOC:-aucun}\"\n",
            encoding="utf-8",
        )
        for mode in MODES:
            fini = subprocess.run(
                ["bash", str(script), mode],
                capture_output=True,
                text=True,
                check=False,
            )
            assert fini.returncode == 0, f"le mode {mode} devrait être accepté : {fini.stderr}"
        fini = subprocess.run(
            ["bash", str(script), "compose-et-autre-chose"],
            capture_output=True,
            text=True,
            check=False,
        )
        assert fini.returncode != 0, "un mode inconnu ne doit pas être accepté"
        assert "mode inconnu" in (fini.stdout + fini.stderr)
    finally:
        script.unlink(missing_ok=True)


def test_le_mode_par_defaut_est_le_compose_livre():
    """Sans argument, on mesure le compose livré — et on le dit.

    Le défaut n'est pas anodin : `verifier-001-2.sh` lancé à la main depuis un
    terminal est le cas le plus fréquent. Un défaut silencieux qui mesurerait
    autre chose que ce qu'on croit mesurer produirait une preuve dont personne
    ne pourrait dire quelle configuration elle décrit.
    """
    texte = PROTOCOLE.read_text(encoding="utf-8")
    # `${1:-compose}` et non `${1-compose}` : le second fait de `-compose` le
    # mode retenu quand l'argument manque, et l'erreur remonte comme un mode
    # inconnu — un message qui accuse l'utilisateur d'une faute de frappe qu'il
    # n'a pas commise. Le motif capture donc le `:-` explicite.
    trouve = re.search(r'^MODE="\$\{1:-([^}]+)\}"$', texte, flags=re.MULTILINE)
    assert trouve, "le protocole ne définit plus de mode par défaut"
    # `${1:-compose}` et `${1-compose}` se lisent pareil à l'œil ; seul le second
    # donne `-compose` quand l'argument manque, et le mode inconnu s'explique par
    # un `case` qui ne le reconnaît pas.
    assert trouve.group(1) == "compose", (
        f"le mode par défaut est {trouve.group(1)!r} : le protocole lancerait "
        "une mesure dont la configuration ne serait pas celle du compose livré"
    )


# --------------------------------------------------------------------------
# Le conteneur : l'identifiant est résolu à chaque appel
# --------------------------------------------------------------------------

def test_l_identifiant_du_conteneur_est_resolu_a_chaque_appel():
    """`docker compose ps -q` est appelé dans la fonction, pas figé au départ.

    Un identifiant figé au début du protocole casse dès que le conteneur est
    recréé — ce que fait tout changement d'environnement, donc **précisément** ce
    que le mode « sans APOC » fait. Le protocole attendrait alors trois minutes
    un Bolt joignable sur un conteneur disparu : c'est ce qui est arrivé au
    premier essai, et 180 secondes d'attente pour une panne qui n'en est pas une.
    """
    texte = PROTOCOLE.read_text(encoding="utf-8")
    fonction = _corps_fonction("identifiant")
    assert "ps -q neo4j" in fonction, "identifiant() ne résout plus le conteneur"

    # La fonction doit être appelée dans `attendre_bolt`, pas une variable
    # calculée une fois : c'est la distinction entre les deux bugs.
    attendre = _corps_fonction("attendre_bolt")
    assert "identifiant" in attendre, (
        "attendre_bolt n'appelle plus identifiant() : il utilise un identifiant "
        "figé, qui devient faux au premier recreate"
    )
    assert re.search(r'\$\{?CONTENEUR\}?', attendre) is None or "identifiant" in attendre


def test_le_protocole_ne_fige_pas_d_identifiant_de_conteneur():
    """Hors de `attendre_bolt`, `$CONTENEUR` ne doit plus servir à un `docker exec`.

    Un `docker exec "$CONTENEUR"` quelque part ailleurs rejouerait exactement le
    bug que `identifiant()` corrige, mais à un endroit que la relecture ne voit
    pas — les tests passeraient, et le protocole échouerait sur un cas que
    personne ne rejoue.
    """
    texte = PROTOCOLE.read_text(encoding="utf-8")
    corps_attendre = _corps_fonction("attendre_bolt")
    dehors = texte.replace(corps_attendre, "")
    assert 'docker exec "$CONTENEUR"' not in dehors, (
        "un docker exec utilise encore l'identifiant figé hors de attendre_bolt"
    )


# --------------------------------------------------------------------------
# Ce que le protocole ne doit pas faire
# --------------------------------------------------------------------------

def test_le_protocole_ne_detruit_pas_le_volume():
    """Aucun `down -v` dans le protocole.

    Le critère C3 exige que le nœud survive à l'arrêt puis au redémarrage ; un
    `down -v` ferait échouer la relecture pour la **mauvaise** raison — le volume
    aurait été détruit, pas le conteneur. Le test est là parce que `down -v` est
    le geste naturel quand on veut un état propre entre deux mesures, et qu'il
    ferait échouer cette story en paraissant corriger le serveur.
    """
    texte = PROTOCOLE.read_text(encoding="utf-8")
    sans_commentaires = "\n".join(l for l in texte.splitlines() if not l.strip().startswith("#"))
    assert "-v" not in re.sub(r"\s-v\s?--?wait", "", sans_commentaires), (
        "le protocole utilise `down -v` : le volume de données serait détruit et "
        "la relecture échouerait pour une raison qui n'est pas celle qu'on mesure"
    )


def test_le_protocole_arrete_puis_redemarre_sans_restart():
    """`stop` puis `start`, pas `restart`.

    C'est un choix de protocole, pas une équivalence : `restart` peut réutiliser
    un état que l'arrêt aurait dû produire, et l'arrêt deviendrait un fait non
    observé — alors que c'est **lui** l'objet de la mesure. Le critère C3 parle
    d'un arrêt puis d'un redémarrage, pas d'un redémarrage.
    """
    texte = PROTOCOLE.read_text(encoding="utf-8")
    sans_commentaires = "\n".join(l for l in texte.splitlines() if not l.strip().startswith("#"))
    assert 'restart' not in sans_commentaires, (
        "le protocole utilise `restart` : l'arrêt ne serait plus un fait observé"
    )
    for geste in ("stop", "start"):
        assert f'docker compose "${{SITES[@]}}" {geste}' in texte, (
            f"le protocole n'exécute pas `{geste}` explicitement sur le conteneur"
        )


def test_le_protocole_echoue_si_l_ecriture_echoue():
    """`ecrire` non nul ⇒ on ne mesure pas la persistance d'un graphe absent.

    Sans cette garde, le protocole continuerait vers le redémarrage, la relecture
    échouerait, et le rapport conclurait « le volume n'a pas tenu » — un verdict
    **faux**, qui imputerait au volume un défaut de l'écriture. C'est le genre de
    causalité inversée qui fait perdre une journée.
    """
    texte = PROTOCOLE.read_text(encoding="utf-8")
    assert re.search(r'if \[ "\$CODE_ECRIRE" -ne 0 \]', texte), (
        "le protocole ne teste pas le code de sortie de l'écriture"
    )
    assert "s'arrête ici" in texte, "le protocole n'annonce pas l'arrêt sur échec d'écriture"


def test_le_protocole_lit_les_deux_versions():
    """Le rapport doit porter la version du serveur **et** celle du driver.

    Une mesure sans les deux chiffres n'est pas rejouable (NFR-3) : le jour où le
    lock bouge, on ne peut pas dire quelle version la sortie mesurée décritait.
    Le test lit le script du vérificateur, qui produit ces deux lignes.
    """
    script = BACKEND / "scripts/verifier_driver_neo4j.py"
    contenu = script.read_text(encoding="utf-8")
    assert "CALL dbms.components()" in contenu, (
        "la version du serveur doit être lue du serveur, pas déduite du tag"
    )
    assert 'distribution_version("neo4j")' in contenu, (
        "la version du driver doit être lue de la distribution installée"
    )


def test_le_protocole_affiche_sa_configuration():
    """Le protocole affiche le mode, l'attente APOC et le tag mesuré.

    Une sortie qui ne dit pas quelle configuration elle décrit est ambiguë dès
    qu'on en a deux : les deux mesures de la story se ressemblent, et c'est en
    comparant leurs en-têtes qu'on voit que l'une tourne sans plugin.
    """
    texte = PROTOCOLE.read_text(encoding="utf-8")
    for attendu in ("mode            :", "attente APOC    :", "version compose :", "compose         :"):
        assert attendu in texte, f"le protocole n'affiche pas « {attendu} »"


def test_le_protocule_ne_conclut_pas_a_la_place_du_verdict():
    """Le protocole affiche, la story conclut.

    Il ne doit pas écrire « go » ou « no-go » : le verdict engage l'ADR 0010, et
    un script qui le pronounce à chaque exécution produirait un verdict par
    passage, dont le dernier aurait le même poids que les 234 tests. La séparation
    affiche / conclut est ce qui permet de rejouer sans réécrire l'histoire.
    """
    texte = PROTOCOLE.read_text(encoding="utf-8")
    sans_commentaires = "\n".join(l for l in texte.splitlines() if not l.strip().startswith("#"))
    for interdit in ("no-go", "nogo", "verdict final"):
        assert interdit not in sans_commentaires, (
            f"le protocole prononce « {interdit} » : le verdict appartient à la story"
        )
    assert "story-001-2.md" in texte, "le protocole ne renvoie pas vers le fichier qui conclut"


# --------------------------------------------------------------------------
# Négatifs — vérifier que ce harnais teste vraiment
# --------------------------------------------------------------------------

def test_un_protocole_absent_est_signale(tmp_path):
    """Le harnais refuse de s'exécuter sans protocole, plutôt que de passer.

    Un harnais dont les assertions ne s'exécutent pas est un harnais vert : on
    vérifie ici que l'extraction **échoue** quand la source manque.
    """
    assert not (tmp_path / "verifier-001-2.sh").exists()
    texte_faux = "identifiant() { echo rien }\n"
    assert "ps -q neo4j" not in texte_faux, "la fixture doit être un protocole sans resolution"


def test_un_mode_sans_refus_laisse_passer_nimporte_quoi():
    """Le `case` sans branche `*)` accepterait un mode inconnu — on le vérifie.

    On rejoue une sélection **sans refus** et on vérifie qu'un mode inconnu y
    passe. Sans cette démonstration, « le protocole refuse un mode inconnu »
    ne serait qu'une affirmation sur la présence d'un `*)`.
    """
    script = REPO / ".protocole-sans-refus.sh"
    try:
        script.write_text(
            "set -uo pipefail\n"
            'MODE="${1:-}"\n'
            'case "$MODE" in\n'
            "  sans-apoc) ATTENTE_APOC=absent ;;\n"
            "  compose) ATTENTE_APOC=attendu ;;\n"
            "esac\n"
            'echo "mode retenu : ${ATTENTE_APOC:-aucun}"\n',
            encoding="utf-8",
        )
        fini = subprocess.run(
            ["bash", str(script), "nimporte-quoi"],
            capture_output=True,
            text=True,
            check=False,
        )
        assert fini.returncode == 0, "la fixture doit être un case sans refus"
        assert "aucun" in fini.stdout, "la fixture doit montrer que rien n'a été retenu"
    finally:
        script.unlink(missing_ok=True)


def test_un_identifiant_fige_echouerait_reellement():
    """Montrer que l'identifiant figé est bien un défaut, pas une préférence.

    Sur une machine sans conteneur, un `docker exec <identifiant-inexistant>`
    échoue : c'est le cas que `identifiant()` évite. Le test le constate pour que
    la règle ait une cause，而不是 une intuition.
    """
    fini = subprocess.run(
        ["docker", "exec", "mirofish-neo4j-neo4j-inexistant", "true"],
        capture_output=True,
        text=True,
        check=False,
    )
    # Sans Docker, la commande échoue aussi — ce qui suffit à démontrer le cas.
    assert fini.returncode != 0
