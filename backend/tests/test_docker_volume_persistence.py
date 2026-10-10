"""Tests unitaires et hermétiques de validation de la persistance des volumes Docker.

Story 005-4 (Epic 005 : Environnement Docker de référence — Docker-first).
Valide les invariants d'infrastructure liés au cycle de vie des volumes :
  - Déclaration et montage des volumes nommés (neo4j_data, neo4j_logs) et bind (uploads, simulations).
  - Préservation intégrale des données de graphes lors des arrêts normaux (Critère C3).
  - Réinitialisation propre lors d'une purge explicite (down -v).
  - Détection des altérations et corruption de données.
"""

from io import StringIO
import json
from pathlib import Path
import sys
import unittest.mock as mock
import pytest
import yaml

from scripts.verifier_persistance_neo4j_docker import (
    LABEL_WITNESS,
    DonneesTemoin,
    MockNeo4jDriver,
    ecrire_fichiers_bind_temoins,
    ecrire_graphe_temoin,
    executer_cycle_persistance_complet,
    generer_donnees_temoin,
    main,
    nettoyer_fichiers_bind_temoins,
    nettoyer_graphe_temoin,
    relire_graphe_temoin,
    verifier_fichiers_bind_temoins,
)

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_DIR = BACKEND_DIR.parent
COMPOSE_FILE = REPO_DIR / "docker-compose.yml"


# --------------------------------------------------------------------------
# 1. Validation de la configuration des volumes dans docker-compose.yml
# --------------------------------------------------------------------------

def test_docker_compose_volume_declarations():
    """Vérifie la présence et la conformité des volumes déclarés dans docker-compose.yml."""
    assert COMPOSE_FILE.exists(), f"{COMPOSE_FILE} introuvable."
    compose_data = yaml.safe_load(COMPOSE_FILE.read_text(encoding="utf-8"))

    # Volumes racine
    volumes = compose_data.get("volumes", {})
    assert "neo4j_data" in volumes, "Le volume 'neo4j_data' doit être déclaré à la racine."
    assert "neo4j_logs" in volumes, "Le volume 'neo4j_logs' doit être déclaré à la racine."

    # Montages Neo4j
    neo4j_vols = compose_data["services"]["neo4j"].get("volumes", [])
    assert "neo4j_data:/data" in neo4j_vols, "Le conteneur neo4j doit monter neo4j_data sur /data."
    assert "neo4j_logs:/logs" in neo4j_vols, "Le conteneur neo4j doit monter neo4j_logs sur /logs."

    # Montages Backend
    backend_vols = compose_data["services"]["backend"].get("volumes", [])
    assert any("./backend/uploads:/app/backend/uploads" in v for v in backend_vols), (
        "Le conteneur backend doit monter ./backend/uploads sur /app/backend/uploads."
    )
    assert any("./backend/simulations:/app/backend/simulations" in v for v in backend_vols), (
        "Le conteneur backend doit monter ./backend/simulations sur /app/backend/simulations."
    )


# --------------------------------------------------------------------------
# 2. Génération des données témoins
# --------------------------------------------------------------------------

def test_generer_donnees_temoin_structure():
    """Vérifie la composition et l'intégrité du jeu de données témoin."""
    donnees = generer_donnees_temoin(tag="test_tag_123")
    assert donnees.tag == "test_tag_123"
    assert len(donnees.nodes) == 5
    assert len(donnees.edges) == 4

    # Chaque nœud possède le tag et des propriétés variées
    for node in donnees.nodes:
        assert "Entity_" in node.name
        assert node.category in {"Organization", "Person", "Concept", "Location", "Document"}
        assert node.score > 0.0
        assert node.properties.get("tag") == "test_tag_123"

    # Relations orientées valides
    node_names = {n.name for n in donnees.nodes}
    for edge in donnees.edges:
        assert edge.source_name in node_names
        assert edge.target_name in node_names
        assert edge.weight > 0.0
        assert edge.valid_at != ""


# --------------------------------------------------------------------------
# 3. Opérations sur le graphe témoin en mémoire (Mock Driver)
# --------------------------------------------------------------------------

def test_ecriture_et_relecture_mock_driver():
    """Vérifie l'écriture, la lecture et l'empreinte sha256 sur le driver simulé."""
    store = {"nodes": {}, "edges": {}}
    driver = MockNeo4jDriver(store)
    donnees = generer_donnees_temoin(tag="test_rw")

    # Écriture
    res_ecriture = ecrire_graphe_temoin(driver, donnees)
    assert res_ecriture["nodes_crees"] == 5
    assert res_ecriture["edges_crees"] == 4

    # Lecture
    lecture = relire_graphe_temoin(driver, "test_rw")
    assert lecture["count_nodes"] == 5
    assert lecture["count_edges"] == 4
    assert len(lecture["hash_sha256"]) == 64

    # Nettoyage
    deleted = nettoyer_graphe_temoin(driver, "test_rw")
    assert deleted == 5

    lecture_apres = relire_graphe_temoin(driver, "test_rw")
    assert lecture_apres["count_nodes"] == 0
    assert lecture_apres["count_edges"] == 0


# --------------------------------------------------------------------------
# 4. Fichiers de montage bind témoins
# --------------------------------------------------------------------------

def test_fichiers_bind_temoins_cycle_vie(tmp_path):
    """Vérifie la création, validation et nettoyage des fichiers dans les dossiers bind."""
    tag = "test_bind_vol"
    fichiers = ecrire_fichiers_bind_temoins(tmp_path, tag)

    assert len(fichiers) == 2
    assert any("uploads" in k for k in fichiers)
    assert any("simulations" in k for k in fichiers)

    # Vérification OK
    valide, erreurs = verifier_fichiers_bind_temoins(tmp_path, fichiers)
    assert valide is True
    assert len(erreurs) == 0

    # Nettoyage
    nettoyer_fichiers_bind_temoins(tmp_path, fichiers)
    for rel_path in fichiers.keys():
        assert not (tmp_path / rel_path).exists()


def test_detection_alteration_fichier_bind(tmp_path):
    """Vérifie qu'une modification d'un fichier bind est immédiatement détectée."""
    tag = "test_bind_alt"
    fichiers = ecrire_fichiers_bind_temoins(tmp_path, tag)

    # Altération d'un fichier
    premier_fichier = list(fichiers.keys())[0]
    (tmp_path / premier_fichier).write_text("Contenu corrompu", encoding="utf-8")

    valide, erreurs = verifier_fichiers_bind_temoins(tmp_path, fichiers)
    assert valide is False
    assert len(erreurs) == 1
    assert "Altération" in erreurs[0]

    nettoyer_fichiers_bind_temoins(tmp_path, fichiers)


def test_detection_fichier_bind_manquant(tmp_path):
    """Vérifie qu'un fichier bind supprimé est détecté."""
    tag = "test_bind_missing"
    fichiers = ecrire_fichiers_bind_temoins(tmp_path, tag)

    # Suppression d'un fichier
    premier_fichier = list(fichiers.keys())[0]
    (tmp_path / premier_fichier).unlink()

    valide, erreurs = verifier_fichiers_bind_temoins(tmp_path, fichiers)
    assert valide is False
    assert len(erreurs) == 1
    assert "manquant" in erreurs[0]

    nettoyer_fichiers_bind_temoins(tmp_path, fichiers)


# --------------------------------------------------------------------------
# 5. Cycle complet de persistance en mode simulé (Mock)
# --------------------------------------------------------------------------

def test_executer_cycle_persistance_mock_succes(tmp_path):
    """Vérifie le déroulement nominal du cycle de persistance complet en mode simulé."""
    rapport = executer_cycle_persistance_complet(
        compose_file=COMPOSE_FILE,
        backend_dir=tmp_path,
        tag="test_mock_cycle",
        mock=True,
    )

    assert rapport.succes_global is True
    assert rapport.mode == "mock"
    assert len(rapport.controles) == 7

    noms_controles = [c.nom for c in rapport.controles]
    assert "1_ecriture_graphe_temoin" in noms_controles
    assert "2_relecture_baseline" in noms_controles
    assert "3_arret_conteneurs_sans_purge" in noms_controles
    assert "4_redemarrage_conteneurs" in noms_controles
    assert "5_persistance_neo4j_critere_c3" in noms_controles
    assert "6_persistance_bind_mounts" in noms_controles
    assert "7_purge_volume_down_v" in noms_controles

    for ctrl in rapport.controles:
        assert ctrl.statut == "OK", f"Le contrôle {ctrl.nom} a échoué : {ctrl.message}"


def test_detection_perte_de_noeud_apres_redemarrage(tmp_path):
    """Vérifie que la perte d'un nœud lors du redémarrage fait échouer le critère C3 dans le rapport."""
    store = {"nodes": {}, "edges": {}}
    tag = "test_fail_node"

    # Surcharge : on simule une perte de données lors de la relecture post-restart
    class FlakyMockDriver(MockNeo4jDriver):
        def __init__(self, data_store):
            super().__init__(data_store)
            self._call_count = 0

        def session(self):
            sess = super().session()
            original_run = sess.run

            def hooked_run(query: str, parameters=None):
                if f"MATCH (n:{LABEL_WITNESS}" in query and "RETURN n.name AS name" in query:
                    self._call_count += 1
                    # Lors du 2ème appel de lecture (post-restart pour contrôle C3), on supprime un nœud
                    if self._call_count >= 2 and tag in self._data_store.get("nodes", {}):
                        keys = list(self._data_store["nodes"][tag].keys())
                        if keys:
                            self._data_store["nodes"][tag].pop(keys[0])
                return original_run(query, parameters)

            sess.run = hooked_run
            return sess

    flaky_driver = FlakyMockDriver(store)
    rapport = executer_cycle_persistance_complet(
        compose_file=COMPOSE_FILE,
        backend_dir=tmp_path,
        tag=tag,
        mock=True,
        driver_override=flaky_driver,
    )

    # Le rapport global doit impérativement être en échec
    assert rapport.succes_global is False

    # Le contrôle C3 doit être marqué ECHEC
    ctrl_c3 = next((c for c in rapport.controles if c.nom == "5_persistance_neo4j_critere_c3"), None)
    assert ctrl_c3 is not None
    assert ctrl_c3.statut == "ECHEC"
    assert "Altération constatée" in ctrl_c3.message


# --------------------------------------------------------------------------
# 6. Tests CLI et Fallback
# --------------------------------------------------------------------------

def test_cli_cycle_complet_mock(monkeypatch):
    """Vérifie l'exécution CLI en mode cycle-complet --mock."""
    monkeypatch.setattr(
        sys,
        "argv",
        ["verifier_persistance_neo4j_docker.py", "cycle-complet", "--mock", "--json"],
    )
    captured = StringIO()
    monkeypatch.setattr(sys, "stdout", captured)

    exit_code = main()
    assert exit_code == 0

    output = captured.getvalue()
    data = json.loads(output)
    assert data["succes_global"] is True
    assert data["mode"] == "mock"


def test_cli_commandes_pas_a_pas_mock(tmp_path, monkeypatch):
    """Vérifie les commandes CLI individuelles ecrire, verifier, purger en mode mock."""
    monkeypatch.setattr("scripts.verifier_persistance_neo4j_docker._backend_dir", tmp_path)

    # 1. ecrire
    monkeypatch.setattr(
        sys,
        "argv",
        ["verifier_persistance_neo4j_docker.py", "ecrire", "--tag", "cli_test", "--mock"],
    )
    assert main() == 0

    # 2. verifier
    monkeypatch.setattr(
        sys,
        "argv",
        ["verifier_persistance_neo4j_docker.py", "verifier", "--tag", "cli_test", "--mock"],
    )
    assert main() == 0

    # 3. purger
    monkeypatch.setattr(
        sys,
        "argv",
        ["verifier_persistance_neo4j_docker.py", "purger", "--tag", "cli_test", "--mock"],
    )
    assert main() == 0


def test_docker_absence_fallback(tmp_path, monkeypatch):
    """Vérifie le repli gracieux si Docker CLI est absent."""
    monkeypatch.setattr("shutil.which", lambda cmd: None if cmd == "docker" else "/bin/true")

    rapport = executer_cycle_persistance_complet(
        compose_file=COMPOSE_FILE,
        backend_dir=tmp_path,
        tag="test_nodocker",
        mock=False,
    )
    assert rapport.succes_global is False
    assert any("Docker CLI introuvable" in c.message for c in rapport.controles)


def test_docker_command_failure_handling(tmp_path, monkeypatch):
    """Vérifie la robustesse du rapport en cas d'échec d'une commande Docker CLI."""
    monkeypatch.setattr("shutil.which", lambda cmd: "/usr/local/bin/docker")

    # Mock du driver pour isoler le test sans dépendance réseau
    store = {"nodes": {}, "edges": {}}
    mock_driver = MockNeo4jDriver(store)
    monkeypatch.setattr("scripts.verifier_persistance_neo4j_docker.creer_driver_neo4j", lambda **kwargs: mock_driver)

    # Simuler un échec de docker compose down
    def fake_exec_docker(cmd, cwd):
        if "down" in cmd:
            return 1, "", "Erreur démon Docker : conteneur verrouillé"
        return 0, "", ""

    monkeypatch.setattr("scripts.verifier_persistance_neo4j_docker.executer_commande_docker", fake_exec_docker)

    rapport = executer_cycle_persistance_complet(
        compose_file=COMPOSE_FILE,
        backend_dir=tmp_path,
        tag="test_docker_err",
        mock=False,
    )

    assert rapport.succes_global is False
    ctrl_down = next((c for c in rapport.controles if c.nom == "3_arret_conteneurs_sans_purge"), None)
    assert ctrl_down is not None
    assert ctrl_down.statut == "ECHEC"
    assert "Erreur démon Docker" in ctrl_down.message

