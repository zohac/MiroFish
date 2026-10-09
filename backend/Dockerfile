# ==============================================================================
# MiroFish Backend Dockerfile
# ==============================================================================
# Environnement d'exécution Python 3.11 autonome et optimisé pour MiroFish backend.
# Géré exclusivement avec uv sync --locked (ADR 0006, AGENTS.md §2.5).
# ==============================================================================

FROM python:3.11-slim

# Définition des variables d'environnement Python
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    FLASK_HOST=0.0.0.0 \
    FLASK_PORT=5001

# Outils de compilation nécessaires pour les dépendances avec extensions C (ex: psutil)
RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Copie de l'exécutable uv depuis l'image officielle Astral
COPY --from=ghcr.io/astral-sh/uv:0.9.26 /uv /uvx /bin/

WORKDIR /app

# Copie préalable des manifestes pour maximiser la réutilisation du cache Docker
COPY backend/pyproject.toml backend/uv.lock ./backend/

# Installation des dépendances verrouillées (--locked garantit la conformité stricte au lockfile)
RUN cd backend && uv sync --locked

# Copie du code source backend, des ressources partagées et des fichiers de documentation/gouvernance
COPY docs/ ./docs/
COPY locales/ ./locales/
COPY AGENTS.md .env.example docker-compose.yml docker-compose.neo4j.yml .dockerignore ./
COPY frontend/Dockerfile frontend/.dockerignore frontend/vite.config.js ./frontend/
COPY backend/ ./backend/

WORKDIR /app/backend

EXPOSE 5001

# Démarrage du serveur backend Flask
CMD ["uv", "run", "python", "run.py"]
