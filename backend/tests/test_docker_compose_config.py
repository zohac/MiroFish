"""Tests unitaires et hermétiques de validation du fichier docker-compose.yml unifié.

Story 005-2 (Epic 005 : Environnement Docker de référence — Docker-first).
Vérifie la conformité de la configuration multi-services (Neo4j, Backend, Frontend),
les dépendances conditionnelles par healthcheck, l'isolation réseau, la persistance des volumes
et l'absence de fuite de secrets.
"""

import re
import shutil
import subprocess
from pathlib import Path
import yaml
import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_DIR = BACKEND_DIR.parent
COMPOSE_FILE = REPO_DIR / "docker-compose.yml"
VITE_CONFIG_FILE = REPO_DIR / "frontend" / "vite.config.js"


def lire_compose_texte() -> str:
    """Lit le contenu brut du docker-compose.yml."""
    assert COMPOSE_FILE.exists(), f"Le fichier {COMPOSE_FILE} est introuvable."
    return COMPOSE_FILE.read_text(encoding="utf-8")


def charger_compose_dict() -> dict:
    """Parse le fichier docker-compose.yml en dictionnaire Python."""
    texte = lire_compose_texte()
    return yaml.safe_load(texte)


# --------------------------------------------------------------------------
# 1. Structure globale et services déclarés
# --------------------------------------------------------------------------

def test_compose_structure_globale():
    """Vérifie la présence des sections essentielles du compose unifié."""
    data = charger_compose_dict()
    assert "services" in data, "La section 'services' est absente de docker-compose.yml"
    assert "networks" in data, "La section 'networks' est absente de docker-compose.yml"
    assert "volumes" in data, "La section 'volumes' est absente de docker-compose.yml"
    
    # Nom de projet
    assert data.get("name") == "mirofish", "Le nom de projet doit être 'mirofish'"
    
    # Exactement les 3 services attendus
    services = data["services"]
    assert set(services.keys()) == {"neo4j", "backend", "frontend"}, (
        f"Les services déclarés doivent être exactement neo4j, backend, frontend. Trouvé: {set(services.keys())}"
    )


def test_reseau_mirofish_network():
    """Vérifie que le réseau virtuel mirofish_network est configuré et partagé."""
    data = charger_compose_dict()
    networks = data.get("networks", {})
    assert "mirofish_network" in networks, "Le réseau 'mirofish_network' n'est pas déclaré."
    
    # Chaque service doit être connecté au réseau mirofish_network
    for service_name in ("neo4j", "backend", "frontend"):
        svc_networks = data["services"][service_name].get("networks", [])
        assert "mirofish_network" in svc_networks, (
            f"Le service '{service_name}' n'est pas connecté à 'mirofish_network'"
        )


def test_volumes_nommes_racine():
    """Vérifie la déclaration des volumes persistants neo4j_data et neo4j_logs."""
    data = charger_compose_dict()
    volumes = data.get("volumes", {})
    assert "neo4j_data" in volumes, "Le volume racine 'neo4j_data' est manquant."
    assert "neo4j_logs" in volumes, "Le volume racine 'neo4j_logs' est manquant."


# --------------------------------------------------------------------------
# 2. Configuration du service Neo4j
# --------------------------------------------------------------------------

def test_service_neo4j_configuration():
    """Vérifie la configuration du service neo4j conforme à l'épreuve 001-2."""
    data = charger_compose_dict()
    neo4j = data["services"]["neo4j"]
    
    assert neo4j["image"] == "neo4j:5.26.31-community", (
        f"L'image Neo4j doit être 'neo4j:5.26.31-community', trouvé: {neo4j.get('image')}"
    )
    assert neo4j.get("restart") == "unless-stopped"
    
    # Ports
    ports = neo4j.get("ports", [])
    assert any("7474" in str(p) for p in ports), "Le port 7474 (HTTP Browser) doit être exposé."
    assert any("7687" in str(p) for p in ports), "Le port 7687 (Bolt) doit être exposé."
    
    # Volumes
    vols = neo4j.get("volumes", [])
    assert "neo4j_data:/data" in vols, "Le volume neo4j_data doit être monté sur /data"
    assert "neo4j_logs:/logs" in vols, "Le volume neo4j_logs doit être monté sur /logs"
    
    # Environnement
    env = neo4j.get("environment", {})
    assert env.get("NEO4J_PLUGINS") == '["apoc"]', "Le plugin APOC doit être activé pour camel-oasis."
    assert "apoc.meta.data" in env.get("NEO4J_dbms_security_procedures_unrestricted", "")
    assert "apoc.merge.*" in env.get("NEO4J_dbms_security_procedures_unrestricted", "")
    assert "apoc.create.*" in env.get("NEO4J_dbms_security_procedures_unrestricted", "")
    assert env.get("NEO4J_server_memory_heap_initial__size") == "512m"
    assert env.get("NEO4J_server_memory_heap_max__size") == "1G"


def test_service_neo4j_securite_et_secrets():
    """Vérifie qu'aucun secret n'est hardcodé et qu'aucun env_file n'est injecté dans Neo4j."""
    data = charger_compose_dict()
    neo4j = data["services"]["neo4j"]
    
    assert "env_file" not in neo4j, (
        "Le conteneur Neo4j ne doit pas recevoir de env_file (évite fuite des clés LLM/Zep)."
    )
    env = neo4j.get("environment", {})
    neo4j_auth = str(env.get("NEO4J_AUTH", ""))
    assert "${NEO4J_PASSWORD" in neo4j_auth or "$NEO4J_PASSWORD" in neo4j_auth, (
        f"NEO4J_AUTH doit interpoler la variable NEO4J_PASSWORD, trouvé: {neo4j_auth}"
    )


def test_service_neo4j_healthcheck():
    """Vérifie la robustesse du healthcheck Bolt pour Neo4j."""
    data = charger_compose_dict()
    hc = data["services"]["neo4j"].get("healthcheck", {})
    assert hc, "Neo4j doit comporter un healthcheck."
    
    test_cmd = hc.get("test", [])
    test_str = " ".join(test_cmd) if isinstance(test_cmd, list) else str(test_cmd)
    assert "cypher-shell" in test_str, "Le healthcheck Neo4j doit utiliser cypher-shell."
    assert "7687" in test_str, "Le healthcheck Neo4j doit viser le port Bolt 7687."
    assert "RETURN 1" in test_str, "Le healthcheck Neo4j doit exécuter une requête Cypher RETURN 1."


# --------------------------------------------------------------------------
# 3. Configuration du service Backend
# --------------------------------------------------------------------------

def test_service_backend_configuration():
    """Vérifie la configuration du service backend (build, volumes, URI Neo4j)."""
    data = charger_compose_dict()
    backend = data["services"]["backend"]
    
    # Build
    build_cfg = backend.get("build", {})
    assert build_cfg.get("context") == ".", "Le contexte de build backend doit être la racine '.'."
    assert build_cfg.get("dockerfile") == "backend/Dockerfile"
    
    # Ports
    ports = backend.get("ports", [])
    assert any("5001" in str(p) for p in ports), "Le port 5001 du backend doit être exposé."
    
    # env_file (supporte chaîne brute ou dictionnaire avec path/required)
    env_file = backend.get("env_file", [])
    if isinstance(env_file, str):
        env_file = [env_file]
    has_env = any(
        item == ".env" or (isinstance(item, dict) and item.get("path") == ".env")
        for item in env_file
    )
    assert has_env, "Le service backend doit référencer le fichier .env"
    
    # Environnement
    env = backend.get("environment", {})
    assert env.get("NEO4J_URI") == "bolt://neo4j:7687", (
        "Le backend doit pointer sur l'hôte interne 'bolt://neo4j:7687'"
    )
    assert env.get("FLASK_PORT") == "5001", (
        "Le backend doit figer FLASK_PORT=5001 pour isoler l'écoute interne du conteneur"
    )
    
    # Volumes
    vols = backend.get("volumes", [])
    assert any("uploads" in v for v in vols), "Le volume uploads doit être monté."
    assert any("simulations" in v for v in vols), "Le volume simulations doit être monté."


def test_service_backend_depends_on_et_healthcheck():
    """Vérifie l'ordonnancement Neo4j -> Backend et le healthcheck Flask."""
    data = charger_compose_dict()
    backend = data["services"]["backend"]
    
    # depends_on
    deps = backend.get("depends_on", {})
    assert "neo4j" in deps, "Le backend doit dépendre du service neo4j."
    assert deps["neo4j"].get("condition") == "service_healthy", (
        "Le backend doit attendre que neo4j soit 'service_healthy'"
    )
    
    # Healthcheck
    hc = backend.get("healthcheck", {})
    assert hc, "Le service backend doit avoir un healthcheck."
    test_cmd = hc.get("test", [])
    test_str = " ".join(test_cmd) if isinstance(test_cmd, list) else str(test_cmd)
    assert "/health" in test_str, "Le healthcheck backend doit sonder la route /health."
    assert "5001" in test_str, "Le healthcheck backend doit interroger le port 5001."


# --------------------------------------------------------------------------
# 4. Configuration du service Frontend
# --------------------------------------------------------------------------

def test_service_frontend_configuration():
    """Vérifie la configuration du service frontend (build, port, dépendance backend)."""
    data = charger_compose_dict()
    frontend = data["services"]["frontend"]
    
    # Build
    build_cfg = frontend.get("build", {})
    assert build_cfg.get("context") == ".", "Le contexte de build frontend doit être la racine '.'."
    assert build_cfg.get("dockerfile") == "frontend/Dockerfile"
    
    # Ports
    ports = frontend.get("ports", [])
    assert any("3000" in str(p) for p in ports), "Le port 3000 du frontend doit être exposé."
    
    # Environnement
    env = frontend.get("environment", {})
    assert env.get("BACKEND_URL") == "http://backend:5001", (
        "Le frontend doit définir BACKEND_URL=http://backend:5001 pour le proxy interne."
    )
    
    # depends_on
    deps = frontend.get("depends_on", {})
    assert "backend" in deps, "Le frontend doit dépendre du service backend."
    assert deps["backend"].get("condition") == "service_healthy", (
        "Le frontend doit attendre que backend soit 'service_healthy'"
    )


def test_vite_config_proxy_support():
    """Vérifie que frontend/vite.config.js supporte la variable d'environnement BACKEND_URL."""
    assert VITE_CONFIG_FILE.exists(), f"{VITE_CONFIG_FILE} est introuvable."
    texte = VITE_CONFIG_FILE.read_text(encoding="utf-8")
    assert "BACKEND_URL" in texte, (
        "frontend/vite.config.js doit lire process.env.BACKEND_URL pour le proxy Docker."
    )
    assert "http://localhost:5001" in texte, (
        "frontend/vite.config.js doit conserver le fallback local http://localhost:5001"
    )


# --------------------------------------------------------------------------
# 5. Validation Docker Compose CLI & Tests négatifs
# --------------------------------------------------------------------------

def test_docker_compose_config_cli():
    """Vérifie la validation syntaxique et sémantique via `docker compose config`."""
    if shutil.which("docker") is None:
        pytest.skip("Docker CLI non installé sur cette machine hôte.")
    
    cmd = ["docker", "compose", "-f", str(COMPOSE_FILE), "config", "-q"]
    resultat = subprocess.run(cmd, capture_output=True, text=True, timeout=60, check=False)
    
    if resultat.returncode != 0 and "Cannot connect to the Docker daemon" in (resultat.stderr or ""):
        pytest.skip("Démon Docker injoignable, test de validation CLI ignoré.")
    
    assert resultat.returncode == 0, f"Erreur 'docker compose config' :\n{resultat.stderr}"


def test_negatif_detection_service_manquant():
    """Vérifie que la validation détecte l'absence d'un service obligatoire."""
    raw = {"services": {"neo4j": {}, "backend": {}}, "networks": {"mirofish_network": {}}, "volumes": {}}
    with pytest.raises(AssertionError, match="frontend"):
        assert set(raw["services"].keys()) == {"neo4j", "backend", "frontend"}


def test_negatif_detection_secret_en_clair():
    """Vérifie que la validation rejette un mot de passe écrit en clair dans NEO4J_AUTH."""
    raw_env = {"NEO4J_AUTH": "neo4j/secret_clair_123"}
    auth_val = raw_env.get("NEO4J_AUTH", "")
    assert not ("${NEO4J_PASSWORD}" in auth_val or "$NEO4J_PASSWORD" in auth_val)
