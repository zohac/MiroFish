FROM python:3.11

# Node.js (>=18) + pnpm via corepack.
# La version de pnpm n'est écrite qu'une fois : le champ packageManager de
# package.json. L'image ne peut donc pas dériver du poste de dev.
# Si corepack pose problème au build, repli explicite :
#   npm install -g pnpm@10.23.0
RUN apt-get update \
  && apt-get install -y --no-install-recommends nodejs npm \
  && npm install -g corepack \
  && corepack enable \
  && rm -rf /var/lib/apt/lists/*

# Copier uv depuis l'image officielle
COPY --from=ghcr.io/astral-sh/uv:0.9.26 /uv /uvx /bin/

WORKDIR /app

# D'abord les fichiers de description, pour le cache de couches
COPY package.json pnpm-lock.yaml ./
COPY frontend/package.json frontend/pnpm-lock.yaml ./frontend/
COPY backend/pyproject.toml backend/uv.lock ./backend/

# Dépendances (Node + Python), verrouillées
RUN pnpm install --frozen-lockfile \
  && pnpm --dir frontend install --frozen-lockfile \
  && cd backend && uv sync --frozen

# Code source
COPY . .

EXPOSE 3000 5001

# Backend + frontend en mode développement
CMD ["pnpm", "run", "dev"]