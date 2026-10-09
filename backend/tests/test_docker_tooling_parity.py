"""Tests unitaires hermétiques validant la parité et la conformité de l'outillage sous Docker (Story 005-3).

Valide :
1. La présence des artefacts de gouvernance, documentation et configuration dans le contexte backend.
2. L'étanchéité de .dockerignore (préservation de .env.example pour les tests, exclusion stricte des secrets).
3. La parité d'exécution de l'outillage de test et de validation de plans (validate_plans.py, ruff).
4. La cohérence du répertoire de travail (/app/backend) et des chemins relatifs hôte/conteneur.
"""

from __future__ import annotations

import importlib.util
import tomllib
from pathlib import Path

import yaml


def _load_validate_plans():
    path = Path(__file__).resolve().parents[1] / "scripts" / "validate_plans.py"
    spec = importlib.util.spec_from_file_location("validate_plans", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Impossible de charger validate_plans depuis {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


validate_plans = _load_validate_plans()


def get_repo_root() -> Path:
    """Retourne la racine absolue du dépôt."""
    return Path(__file__).resolve().parents[2]


class TestDockerToolingParity:
    """Tests de conformité de l'outillage conteneurisé Docker."""

    @property
    def repo_root(self) -> Path:
        return get_repo_root()

    def test_backend_dockerfile_includes_tooling_and_docs_context(self):
        """Vérifie que backend/Dockerfile copie la documentation et les manifestes nécessaires aux tests."""
        dockerfile = self.repo_root / "backend" / "Dockerfile"
        assert dockerfile.is_file(), "backend/Dockerfile doit exister"
        content = dockerfile.read_text(encoding="utf-8")

        assert "COPY docs/ ./docs/" in content, "backend/Dockerfile doit copier docs/ pour les tests de plans"
        assert "COPY locales/ ./locales/" in content, "backend/Dockerfile doit copier locales/"
        assert "AGENTS.md" in content, "backend/Dockerfile doit copier AGENTS.md"
        assert "docker-compose.yml" in content, "backend/Dockerfile doit copier docker-compose.yml"
        assert ".env.example" in content, "backend/Dockerfile doit copier .env.example"

    def test_dockerignore_allows_env_example_while_blocking_secrets(self):
        """Vérifie que .dockerignore bloque .env tout en autorisant le template .env.example."""
        root_ignore = self.repo_root / ".dockerignore"
        assert root_ignore.is_file(), ".dockerignore racine doit exister"
        content = root_ignore.read_text(encoding="utf-8")

        lines = [line.strip() for line in content.splitlines() if line.strip() and not line.strip().startswith("#")]
        assert ".env" in lines, ".dockerignore doit ignorer .env"
        assert ".env.*" in lines, ".dockerignore doit ignorer .env.*"
        assert "!.env.example" in lines, ".dockerignore doit autoriser !.env.example pour les tests"

    def test_validate_plans_succeeds_on_repo_root(self):
        """Vérifie que validate_plans s'exécute avec 0 erreur sur la racine du dépôt."""
        problems = validate_plans.validate(self.repo_root)
        assert problems == [], f"validate_plans ne doit trouver aucune anomalie : {problems}"

    def test_pyproject_ruff_configuration_exists(self):
        """Vérifie que backend/pyproject.toml déclare la configuration ruff nécessaire au linter."""
        pyproject_file = self.repo_root / "backend" / "pyproject.toml"
        assert pyproject_file.is_file(), "backend/pyproject.toml doit exister"
        data = tomllib.loads(pyproject_file.read_text(encoding="utf-8"))

        assert "tool" in data and "ruff" in data["tool"], "La section [tool.ruff] doit être présente dans pyproject.toml"
        ruff_config = data["tool"]["ruff"]
        assert "line-length" in ruff_config, "line-length doit être configuré dans [tool.ruff]"

    def test_docker_compose_backend_volumes_and_workdir_parity(self):
        """Vérifie la parité des montages de volumes backend dans docker-compose.yml."""
        compose_file = self.repo_root / "docker-compose.yml"
        assert compose_file.is_file(), "docker-compose.yml doit exister"
        content = yaml.safe_load(compose_file.read_text(encoding="utf-8"))

        backend_service = content["services"]["backend"]
        volumes = backend_service.get("volumes", [])
        assert any("./backend/uploads:/app/backend/uploads" in v for v in volumes), "Le volume backend/uploads doit être monté"
        assert any("./backend/simulations:/app/backend/simulations" in v for v in volumes), "Le volume backend/simulations doit être monté"

    def test_docker_compose_run_no_deps_environment_is_sound(self):
        """Vérifie que le service backend possède des variables d'environnement compatibles avec l'exécution isolée."""
        compose_file = self.repo_root / "docker-compose.yml"
        content = yaml.safe_load(compose_file.read_text(encoding="utf-8"))

        backend_service = content["services"]["backend"]
        raw_env = backend_service.get("environment", {})
        if isinstance(raw_env, list):
            env = {}
            for item in raw_env:
                if "=" in item:
                    k, v = item.split("=", 1)
                    env[k.strip()] = v.strip()
        else:
            env = dict(raw_env)
        assert env.get("FLASK_PORT") == "5001", "FLASK_PORT doit valoir 5001"
        assert env.get("NEO4J_URI") == "bolt://neo4j:7687", "NEO4J_URI doit pointer vers le conteneur neo4j"
