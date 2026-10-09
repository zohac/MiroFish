---
id: "005-1"
epic: "005"
titre: "Dockerfiles dédiés backend et frontend construits depuis les sources locales"
statut: backlog
auteur: agent
format: "2"
---

# Story 005-1 — Dockerfiles dédiés backend et frontend construits depuis les sources locales

## Définition de prêt

- [ ] Objectif compris : concevoir les Dockerfiles dédiés pour le backend (`backend/Dockerfile`) et le frontend (`frontend/Dockerfile`), assurant une construction autonome et reproductible depuis les sources locales de notre fork `local-first`, avec cache optimal des dépendances (`uv.lock` et `pnpm-lock.yaml`) et 0 secret dans les images.
- [ ] Documents consultés : [PRD](prd.md) (notamment critères C1, C2 et C5), [Architecture](architecture.md), [Epic 005](epic-005.md), [`Dockerfile`](file:///Users/simon/dev/MiroFish/Dockerfile), [ADR 0006](../../decisions/0006-docker-first.md), [ADR 0008](../../decisions/0008-pnpm-seul.md), [AGENTS.md](file:///Users/simon/dev/MiroFish/AGENTS.md) (§2.4, §2.5, §2.9).
- [ ] Prérequis vérifiés : Codebase locale fonctionnelle (632 tests verts), `backend/uv.lock` synchronisé avec `backend/pyproject.toml`, `pnpm-lock.yaml` synchronisé avec `package.json`, `.dockerignore` prêt à exclure `.env` et les dossiers temporaires.
- [ ] Stratégie de test identifiée : validation de la constructibilité des images via `docker build`, vérification du cache de couches, suite de tests unitaires hermétiques validant la structure des Dockerfiles et l'absence d'exposition de secrets, contrôle d'inspection d'image.

## Définition de fini

- [ ] `backend/Dockerfile` autonome basé sur `python:3.11-slim`, copiant `uv` depuis `ghcr.io/astral-sh/uv:0.9.26`, installant les dépendances Python via `uv sync --locked`, sans Node.js ni dépendances frontend superflues.
- [ ] `frontend/Dockerfile` autonome basé sur `node:20-slim`, avec `pnpm` activé via corepack conformément à l'ADR 0008, installant les dépendances via `pnpm install --frozen-lockfile`, sans dépendances Python ni PyTorch.
- [ ] Cache de couches Docker optimal : les manifestes de dépendances (`uv.lock`, `pyproject.toml`, `package.json`, `pnpm-lock.yaml`) sont copiés et installés avant la copie du code source applicatif pour accélérer les reconstructions.
- [ ] Fichiers `.dockerignore` configurés pour exclure formellement `.env`, `.venv`, `node_modules`, `__pycache__`, `.git`, `.pytest_cache` et tout fichier temporaire (AGENTS.md §2.4).
- [ ] 0 secret présent dans les images construites (vérifié par inspection `docker history` ou analyse statique).
- [ ] Tests de non-régression et de structure de plan (`validate_plans.py`, `ruff check`) passants sans avertissement.

## Tâches

- [ ] Concevoir le `backend/Dockerfile` spécialisé avec `python:3.11-slim` et `uv sync --locked`.
- [ ] Concevoir le `frontend/Dockerfile` spécialisé avec `node:20-slim` et `pnpm install --frozen-lockfile`.
- [ ] Mettre en place et consolider les fichiers `.dockerignore` (racine, backend, frontend) pour interdire toute inclusion de secrets ou d'environnements hôtes.
- [ ] Valider la construction locale des images `mirofish-backend:local` et `mirofish-frontend:local`.
- [ ] Développer une suite de tests unitaires hermétiques validant la conformité des directives Dockerfiles et des fichiers `.dockerignore` (`backend/tests/test_docker_build_config.py`).
- [ ] Réaliser la revue contradictoire BMad (4 couches) et consigner les résultats.
- [ ] Mettre à jour l'index des stories et l'état d'avancement dans la documentation de suivi.

## Notes de développement

Dans le dépôt amont, un unique `Dockerfile` à la racine regroupait Python 3.11 et Node.js dans un même conteneur, démarrant le backend et le frontend via `CMD ["pnpm", "run", "dev"]`.

Cette approche présentait de sérieux inconvénients :
1. **Poids et temps de build excessifs** : le conteneur mélangeait le runtime Python (incluant PyTorch, sentence-transformers, graphiti-core) et l'environnement Node/npm complet.
2. **Couplage de cycle de vie** : impossible de redémarrer le backend sans couper le frontend, et impossible de lancer un conteneur dédié uniquement aux tests unitaires backend sans instancier tout l'écosystème Node.
3. **Divergence avec la cible Docker-first** : l'ADR 0006 et la constitution exigent que Docker Compose orchestre des services bien distincts (`backend`, `frontend`, `neo4j`) permettant d'exécuter `docker compose run --rm backend uv run pytest tests/ -q`.

La Story 005-1 pose la première pierre fondamentale de l'Epic 005 en créant les Dockerfiles spécialisés pour chaque tiers applicatif, avec un respect rigoureux des locks figés (`uv sync --locked` et `pnpm install --frozen-lockfile`) et de la sécurité des secrets.

## Revue

- **Couche Contrat & Architecture** : À compléter lors de la revue BMad.
- **Couche Hermétisme & Sécurité** : À compléter lors de la revue BMad.
- **Couche Tests & Qualité** : À compléter lors de la revue BMad.

## Notes de complétion

À rédiger à l'achèvement de la story.
