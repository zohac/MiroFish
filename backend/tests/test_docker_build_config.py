"""Tests unitaires hermétiques pour la configuration Docker et Dockerfiles (Story 005-1).

Valide :
1. La structure, l'isolation et les directives de backend/Dockerfile (Python 3.11, uv, locked).
2. La structure, l'isolation et les directives de frontend/Dockerfile (Node 20, pnpm, frozen-lockfile).
3. L'optimisation du cache de couches Docker (fichiers de lock copiés avant le code source).
4. La configuration stricte des fichiers .dockerignore (exclusion de .env, secrets, venv, node_modules).
5. L'absence formelle de fuite de secrets ou de clés dans les définitions de conteneurs (AGENTS.md §2.4).
"""

from __future__ import annotations

import re
from pathlib import Path


def get_repo_root() -> Path:
    """Retourne la racine absolue du dépôt."""
    return Path(__file__).resolve().parents[2]


class TestBackendDockerfile:
    """Vérifications du Dockerfile backend."""

    @property
    def dockerfile_path(self) -> Path:
        return get_repo_root() / "backend" / "Dockerfile"

    def test_backend_dockerfile_exists(self):
        assert self.dockerfile_path.is_file(), f"Le fichier {self.dockerfile_path} doit exister"

    def test_backend_dockerfile_base_image(self):
        content = self.dockerfile_path.read_text(encoding="utf-8")
        assert re.search(r"FROM\s+python:3\.11-slim", content), "backend/Dockerfile doit être basé sur python:3.11-slim"

    def test_backend_dockerfile_uses_official_uv(self):
        content = self.dockerfile_path.read_text(encoding="utf-8")
        assert "ghcr.io/astral-sh/uv:0.9.26" in content, "backend/Dockerfile doit copier uv depuis ghcr.io/astral-sh/uv:0.9.26"

    def test_backend_dockerfile_uses_locked_sync(self):
        content = self.dockerfile_path.read_text(encoding="utf-8")
        assert "uv sync --locked" in content, "backend/Dockerfile doit synchroniser les dépendances avec uv sync --locked"

    def test_backend_dockerfile_layer_caching_order(self):
        content = self.dockerfile_path.read_text(encoding="utf-8")
        lines = [line.strip() for line in content.splitlines() if line.strip() and not line.strip().startswith("#")]

        # Vérifier que la copie des manifestes précède uv sync, qui précède la copie du code source
        copy_locks_idx = next(i for i, line in enumerate(lines) if "uv.lock" in line and "COPY" in line)
        sync_idx = next(i for i, line in enumerate(lines) if "uv sync --locked" in line)
        copy_code_idx = next(i for i, line in enumerate(lines) if "COPY backend/ ./backend/" in line or "COPY backend/ ." in line)

        assert copy_locks_idx < sync_idx, "Les fichiers de lock doivent être copiés avant uv sync"
        assert sync_idx < copy_code_idx, "uv sync doit être exécuté avant la copie du code source pour optimiser le cache"

    def test_backend_dockerfile_port_and_cmd(self):
        content = self.dockerfile_path.read_text(encoding="utf-8")
        assert "EXPOSE 5001" in content, "backend/Dockerfile doit exposer le port 5001"
        assert 'CMD ["uv", "run", "python", "run.py"]' in content or "run.py" in content, "backend/Dockerfile doit démarrer run.py via uv"

    def test_backend_dockerfile_has_no_secrets_or_env_copy(self):
        content = self.dockerfile_path.read_text(encoding="utf-8")
        assert "COPY .env" not in content, "backend/Dockerfile ne doit jamais copier le fichier .env (AGENTS.md §2.4)"
        assert not re.search(r"ENV\s+.*(KEY|SECRET|PASSWORD)\s*=", content, re.IGNORECASE), "Aucun secret en dur dans backend/Dockerfile"

    def test_backend_dockerfile_installs_build_dependencies(self):
        content = self.dockerfile_path.read_text(encoding="utf-8")
        assert "gcc" in content and "python3-dev" in content, "backend/Dockerfile doit installer gcc et python3-dev pour les dépendances C"

    def test_backend_dockerfile_has_no_node_or_frontend_tools(self):
        content = self.dockerfile_path.read_text(encoding="utf-8")
        assert not re.search(r"\b(node|npm|pnpm|yarn|corepack)\b", content, re.IGNORECASE), "backend/Dockerfile ne doit contenir aucun outil Node/frontend"


class TestFrontendDockerfile:
    """Vérifications du Dockerfile frontend."""

    @property
    def dockerfile_path(self) -> Path:
        return get_repo_root() / "frontend" / "Dockerfile"

    def test_frontend_dockerfile_exists(self):
        assert self.dockerfile_path.is_file(), f"Le fichier {self.dockerfile_path} doit exister"

    def test_frontend_dockerfile_base_image(self):
        content = self.dockerfile_path.read_text(encoding="utf-8")
        assert re.search(r"FROM\s+node:20-slim", content), "frontend/Dockerfile doit être basé sur node:20-slim"

    def test_frontend_dockerfile_uses_corepack_pnpm(self):
        content = self.dockerfile_path.read_text(encoding="utf-8")
        assert "corepack enable" in content, "frontend/Dockerfile doit activer corepack"
        assert "pnpm" in content, "frontend/Dockerfile doit configurer pnpm"

    def test_frontend_dockerfile_uses_frozen_lockfile(self):
        content = self.dockerfile_path.read_text(encoding="utf-8")
        assert "--frozen-lockfile" in content, "frontend/Dockerfile doit utiliser --frozen-lockfile (ADR 0008)"

    def test_frontend_dockerfile_layer_caching_order(self):
        content = self.dockerfile_path.read_text(encoding="utf-8")
        lines = [line.strip() for line in content.splitlines() if line.strip() and not line.strip().startswith("#")]

        copy_locks_idx = next(i for i, line in enumerate(lines) if "pnpm-lock.yaml" in line and "COPY" in line)
        install_idx = next(i for i, line in enumerate(lines) if "pnpm" in line and "install" in line)
        copy_code_idx = next(i for i, line in enumerate(lines) if "COPY frontend/ ./frontend/" in line or "COPY frontend/ ." in line)

        assert copy_locks_idx < install_idx, "pnpm-lock.yaml doit être copié avant pnpm install"
        assert install_idx < copy_code_idx, "pnpm install doit être exécuté avant la copie du code source"

    def test_frontend_dockerfile_port_and_cmd(self):
        content = self.dockerfile_path.read_text(encoding="utf-8")
        assert "EXPOSE 3000" in content, "frontend/Dockerfile doit exposer le port 3000"
        assert 'CMD ["pnpm", "run", "dev"]' in content or "vite" in content, "frontend/Dockerfile doit lancer le serveur frontend"

    def test_frontend_dockerfile_has_no_secrets_or_env_copy(self):
        content = self.dockerfile_path.read_text(encoding="utf-8")
        assert "COPY .env" not in content, "frontend/Dockerfile ne doit jamais copier .env"
        assert not re.search(r"ENV\s+.*(KEY|SECRET|PASSWORD)\s*=", content, re.IGNORECASE), "Aucun secret en dur dans frontend/Dockerfile"

    def test_frontend_dockerfile_has_no_python_or_backend_tools(self):
        content = self.dockerfile_path.read_text(encoding="utf-8")
        assert not re.search(r"\b(python|pip|uv|uvx|torch|pytest)\b", content, re.IGNORECASE), "frontend/Dockerfile ne doit contenir aucun outil Python/backend"


class TestDockerignoreConfigurations:
    """Vérifications des fichiers .dockerignore."""

    def test_root_dockerignore_excludes_critical_patterns(self):
        root_ignore = get_repo_root() / ".dockerignore"
        assert root_ignore.is_file(), ".dockerignore racine doit exister"
        content = root_ignore.read_text(encoding="utf-8")
        lines = [line.strip() for line in content.splitlines() if line.strip() and not line.strip().startswith("#")]

        critical_patterns = [".env", ".venv", "node_modules", "__pycache__", ".git", ".pytest_cache"]
        for pattern in critical_patterns:
            assert any(pattern in line for line in lines), f".dockerignore racine doit exclure '{pattern}'"

    def test_backend_and_frontend_dockerignore_exist_and_exclude_secrets(self):
        backend_ignore = get_repo_root() / "backend" / ".dockerignore"
        frontend_ignore = get_repo_root() / "frontend" / ".dockerignore"

        assert backend_ignore.is_file(), "backend/.dockerignore doit exister"
        assert frontend_ignore.is_file(), "frontend/.dockerignore doit exister"

        for file_path in (backend_ignore, frontend_ignore):
            content = file_path.read_text(encoding="utf-8")
            assert ".env" in content, f"{file_path.name} doit exclure formellement .env"
            assert ".git" in content, f"{file_path.name} doit exclure .git"
