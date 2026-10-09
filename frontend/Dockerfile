# ==============================================================================
# MiroFish Frontend Dockerfile
# ==============================================================================
# Environnement d'exécution Node.js 20 autonome pour le frontend Vue 3 / Vite.
# Géré exclusivement avec pnpm via Corepack (ADR 0008, AGENTS.md §2.5).
# ==============================================================================

FROM node:20-slim

# Activation de pnpm via Corepack avec la version exacte fixée dans package.json
RUN corepack enable && corepack prepare pnpm@10.23.0 --activate

WORKDIR /app

# Copie préalable des manifestes pour maximiser la réutilisation du cache Docker
COPY package.json pnpm-lock.yaml ./
COPY frontend/package.json frontend/pnpm-lock.yaml ./frontend/

# Installation des dépendances avec verrouillage strict du lockfile
RUN pnpm --dir frontend install --frozen-lockfile

# Copie du code source du frontend et des ressources de localisation partagées
COPY frontend/ ./frontend/
COPY locales/ ./locales/

WORKDIR /app/frontend

EXPOSE 3000

# Démarrage du serveur de développement Vite avec écoute sur 0.0.0.0 (--host)
CMD ["pnpm", "run", "dev"]
