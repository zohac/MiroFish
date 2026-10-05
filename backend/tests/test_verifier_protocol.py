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
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parent
PROTOCOLE = REPO / "docs/plans/001-epreuve-graphiti-local/verifier-001-2.sh"

# Les deux modes du protocole. Ils ne sont pas interchangeables : l'un mesure ce
# que Graphiti réclame, l'autre ce que `camel` réclame, et les conclusions sont
# opposées.
MODES = ("sans-apoc", "compose")


def _corps_fonction_de(nom: str, source: Path) -> str:
    """Le corps d'une fonction bash, extrait d'un fichier donné.

    `source` est paramétré pour que le cas « la fonction n'est pas là » puisse
    être rejoué sur un fichier de.fixture : c'est ce cas qui prouve que
    l'extraction **échoue**, et non qu'elle renvoie silencieusement un corps vide.
    """
    texte = source.read_text(encoding="utf-8")
    trouve = re.search(rf"^{nom}\(\)\s*\{{\n.*?^\}}$", texte, re.MULTILINE | re.DOTALL)
    if not trouve:
        # Variante sur une seule ligne, pour les fonctions d'une expression.
        trouve = re.search(rf"^{nom}\(\)\s*\{{[^\n]*\}}$", texte, re.MULTILINE)
    assert trouve, f"{nom} est introuvable dans {source.name}"
    return trouve.group(0)


def _corps_fonction(nom: str) -> str:
    """Le corps d'une fonction bash, extrait du protocole réel.

    Les accolades de l'extension `.sh` sont tolérées : `identifiant() {` et
    `attendre_bolt() {` sont sur une seule ligne, alors que la fonction `case`
    du protocole est géolocalisée autrement. Une recherche trop stricte
    échouerait sur une forme stylistique — et un test qui échoue pour une
    question de regexp au lieu de la chose qu'il garde est un test qu'on
    finit par supprimer.
    """
    return _corps_fonction_de(nom, PROTOCOLE)


def _executer(fonction: str, corps: str, environnement: dict[str, str]) -> tuple[int, str]:
    """Exécute une fonction du protocole avec un environnement fabriqué.

    Le script extrait vit dans un **fichier temporaire du système**, jamais à la
    racine du dépôt. L'emplacement précédent se justifiait par « le protocole
    résout ses chemins par `dirname $0` », ce qui est faux : les extraits
    utilisés ici — le bloc `NEO4J_PASSWORD=$(grep …)`, le `case` de sélection —
    ne mentionnent jamais `$0`. Le second motif, « le protocole suivant exige un
    arbre propre », était également faux : le protocole n'appelle
    `git rev-parse --short HEAD`, qui n'a rien à exiger de l'arbre. Un fichier
    écrit dans le dépôt et effacé dans un `finally` reste un fichier non suivi
    dès qu'un `pytest -x` s'interrompt au milieu — et le dépôt n'a pas le droit
    d'en garder.
    """
    with tempfile.TemporaryDirectory(prefix="mirofish-protocole-") as dossier:
        script = Path(dossier) / "extrait.sh"
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
            timeout=30,
            env={**dict(**{"PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin"}), **environnement},
        )
        return fini.returncode, (fini.stdout + fini.stderr)


# --------------------------------------------------------------------------
# Le refus d'un mot de passe absent
# --------------------------------------------------------------------------

def test_un_mot_de_passe_absent_est_refuse():
    """Sans `NEO4J_PASSWORD`, le protocole ne démarre rien.

    Démarrer quand même donnerait un conteneur avec un mot de passe vide ou
    implicite — donc une base dont personne n'a choisi le secret, et une mesure
    qui compare des chiffres pris sur cette base. Le refus est la seule issue
    honnête.

    Le bloc extrait va de la lecture du `.env` au `fi` du refus, et **rien
    d'autre** : il ne dépend d'aucune autre variable du protocole. C'est ce qui
    rend le test exact — la version précédente extrayait jusqu'au `fi` d'un
    bloc qui contenait `rm -f "$SANS_APOC"`, variable non déclarée dans
    l'extrait : sous `set -u`, c'était cet échec qui produisait le code de
    sortie, pas le `exit 1` du refus. Le test passait donc sans garantir que le
    protocole sorte par là.
    """
    corps = re.search(
        r"NEO4J_PASSWORD=\$\(sed.*?^fi$",
        PROTOCOLE.read_text(encoding="utf-8"),
        re.MULTILINE | re.DOTALL,
    )
    assert corps, "le protocole ne lit plus NEO4J_PASSWORD depuis le .env"
    assert "SANS_APOC" not in corps.group(0), (
        "le bloc de refus dépend d'une variable du protocole : l'extraction "
        "échouerait sur `set -u` pour une raison étrangère au refus lui-même"
    )
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
    défaut, et une faute de frappe prend un mode inexistant. Si le `case` perdait
    sa branche de refus, le protocole partirait sur le `compose` livré en croyant
    mesurer une variante — et le rapport afficherait une configuration qui n'est
    pas celle qu'on a demandée.
    """
    texte = PROTOCOLE.read_text(encoding="utf-8")
    bloc = re.search(r"^case \"\$MODE\" in$.*?^esac$", texte, re.MULTILINE | re.DOTALL)
    assert bloc, "le protocole n'a plus de sélection de mode"
    assert "sans-apoc)" in bloc.group(0), "le mode « sans-apoc » a disparu du protocole"
    assert "compose)" in bloc.group(0), "le mode « compose » a disparu du protocole"

    # On rejoue la sélection seule, avec les deux modes et un mode inconnu.
    with tempfile.TemporaryDirectory(prefix="mirofish-protocole-") as dossier:
        script = Path(dossier) / "modes.sh"
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
                timeout=30,
            )
            assert fini.returncode == 0, f"le mode {mode} devrait être accepté : {fini.stderr}"
        fini = subprocess.run(
            ["bash", str(script), "compose-et-autre-chose"],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
        assert fini.returncode != 0, "un mode inconnu ne doit pas être accepté"
        assert "mode inconnu" in (fini.stdout + fini.stderr)


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

    # La fonction doit être **appelée** dans `attendre_bolt`, pas une variable
    # calculée une fois : c'est la distinction entre les deux bugs. On cherche
    # donc l'appel lui-même, et pas seulement le mot — l'assertion précédente
    # était `… is None or "identifiant" in attendre`, dont le second terme était
    # toujours vrai dès que la précédente passait : elle ne vérifiait rien.
    attendre = _corps_fonction("attendre_bolt")
    assert re.search(r"conteneur=\$\(\s*identifiant\s*\)", attendre), (
        "attendre_bolt n'appelle pas identifiant() : il utilise un identifiant "
        "figé, qui devient faux au premier recreate. L'identifiant doit être "
        "résolu à chaque itération, pas une fois."
    )
    assert not re.search(r"\$\{?CONTENEUR\b", attendre), (
        "attendre_bolt utilise $CONTENEUR : un identifiant figé au début du "
        "protocole casse dès que le conteneur est recréé — ce que fait tout "
        "changement d'environnement, donc précisément le mode « sans APOC »"
    )


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
    # **Toute** forme d'expansion de `$CONTENEUR` passée à un `docker exec`, pas
    # seulement la forme exacte `"$CONTENEUR"`. La version précédente ne voyait
    # que celle-là : `docker exec $CONTENEUR` ou `docker exec "${CONTENEUR}"`
    # seraient passés — et rejoueraient le bug.
    fige = re.findall(r'docker exec[^\n]*\$\{?CONTENEUR\b', dehors)
    assert not fige, (
        "un docker exec utilise encore l'identifiant figé hors de attendre_bolt : "
        + " / ".join(e.strip() for e in fige)
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
    """Le harnais refuse de s'extraire d'une source absente, plutôt que de passer.

    On vérifie ici que l'extraction **échoue** quand la fonction attendue n'est pas
    là. La version précédente affirmait
    `assert not (tmp_path / "verifier-001-2.sh").exists()` — une tautologie sur un
    répertoire vide — puis testait une chaîne littérale écrite sur place. Elle
    n'appelait jamais l'extraction, donc elle passait même si la fonction avait
    été supprimée, ou si l'extraction renvoyait silencieusement un corps vide.
    """
    # Le cas réel : un protocole refondu où `attendre_bolt` a disparu. La fixture
    # contient bien une fonction — sinon le cas serait trivialement absent et le
    # test ne prouverait rien.
    refondu = tmp_path / "verifier-001-2.sh"
    refondu.write_text("identifiant() { echo rien }\n", encoding="utf-8")
    with pytest.raises(AssertionError) as echec:
        _corps_fonction_de("attendre_bolt", refondu)
    assert "introuvable" in str(echec.value), (
        f"le refus ne nomme pas la fonction manquante : {echec.value}"
    )

    # Et le vrai protocole, lui, doit fournir les deux — sinon le test d'échec
    # passerait pour la bonne raison.
    assert "ps -q neo4j" in _corps_fonction_de("identifiant", PROTOCOLE)
    assert "identifiant" in _corps_fonction_de("attendre_bolt", PROTOCOLE)


def test_un_mode_sans_refus_laisse_passer_nimporte_quoi():
    """Le `case` sans branche `*)` accepterait un mode inconnu — on le vérifie.

    On rejoue une sélection **sans refus** et on vérifie qu'un mode inconnu y
    passe. Sans cette démonstration, « le protocole refuse un mode inconnu »
    ne serait qu'une affirmation sur la présence d'un `*)`.
    """
    with tempfile.TemporaryDirectory(prefix="mirofish-protocole-") as dossier:
        script = Path(dossier) / "sans-refus.sh"
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
            timeout=30,
        )
        assert fini.returncode == 0, "la fixture doit être un case sans refus"
        assert "aucun" in fini.stdout, "la fixture doit montrer que rien n'a été retenu"


def test_un_identifiant_fige_echouerait_reellement():
    """Montrer que l'identifiant figé est bien un défaut, pas une préférence.

    Sur une machine sans conteneur, un `docker exec <identifiant-inexistant>`
    échoue : c'est le cas que `identifiant()` évite. Le test le constate pour que
    la règle ait une cause, et non une intuition.

    Sans binaire `docker`, le test se déclare **non conduit**. La version
    précédente affirmait le contraire dans son commentaire — « sans Docker, la
    commande échoue aussi » — mais `subprocess.run` ne renvoie pas un code : il
    lève `FileNotFoundError`. Le test **échouait donc** sur un poste sans Docker,
    ce qui contredisait son propre module et la règle d'herméticité d'AGENTS.md
    §2.2. Un test qui casse selon la machine est un test qu'on corrige ou qu'on
    supprime ; on l'a corrigé.
    """
    if shutil.which("docker") is None:
        pytest.skip("docker absent : le cas « conteneur inexistant » n'est pas rejouable")
    fini = subprocess.run(
        ["docker", "exec", "mirofish-neo4j-neo4j-inexistant", "true"],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert fini.returncode != 0, (
        "docker exec sur un conteneur inexistant devrait échouer ; s'il réussit, "
        "le cas que identifiant() évite ne serait plus un défaut"
    )
