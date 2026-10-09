---
id: "005-3"
epic: "005"
titre: "Validation du filet global de tests (664 tests) et outillage sous Docker"
statut: backlog
auteur: agent
format: "2"
---

# Story 005-3 — Validation du filet global de tests (664 tests) et outillage sous Docker

## Définition de prêt

- [ ] Objectif compris : valider que l'environnement de référence Docker (`docker compose run --rm backend`) exécute 100 % de l'outillage et du filet de tests (664 tests unitaires pytest, `ruff check .`, `validate_plans.py`) de manière reproductible et isolée, sans dépendance vis-à-vis des outils installés sur la machine hôte.
- [ ] Documents consultés : [PRD](prd.md) (notamment critères C2 et C5, exigences FR-6, NFR-2), [Architecture](architecture.md) (§6), [Epic 005](epic-005.md), [`docker-compose.yml`](../../docker-compose.yml), [ADR 0006](../../decisions/0006-docker-first.md), [AGENTS.md](../../AGENTS.md) (§2.2, §2.9, §3).
- [ ] Prérequis vérifiés : `backend/Dockerfile` construit et opérationnel (`mirofish-backend:local`), `docker-compose.yml` unifié configuré avec les services `neo4j`, `backend`, `frontend` sur le réseau `mirofish_network`, suite de 664 tests unitaires passants au vert sur l'hôte.
- [ ] Stratégie de test identifiée : exécution de `docker compose run --rm backend uv run pytest tests/ -q` dans le conteneur, vérification de l'hermétisme sans `.env`, exécution du linter `ruff check .` et de `validate_plans.py` dans le conteneur, création d'une suite de tests automatisée ou script de vérification validant la parité d'exécution hôte/Docker.

## Définition de fini

- [ ] Exécution réussie de `docker compose run --rm backend uv run pytest tests/ -q` validant 100 % des tests (664 tests) au vert dans le conteneur.
- [ ] Exécution réussie de `docker compose run --rm backend uv run ruff check .` avec 0 erreur.
- [ ] Exécution réussie de `docker compose run --rm backend uv run python scripts/validate_plans.py` validant la structure de planification dans le conteneur.
- [ ] Vérification du comportement des volumes montés (`uploads`, `simulations`) et des permissions de fichiers créés lors de l'exécution des tests.
- [ ] Documentation ou script d'aide facilitant l'exécution des tests conteneurisés pour les développeurs et la CI.
- [ ] Tests de non-régression et de structure de plan (`validate_plans.py`, `ruff check`) passants sans avertissement.

## Tâches

- [ ] Vérifier la configuration du conteneur `backend` pour l'exécution de commandes éphémères (`docker compose run --rm backend`).
- [ ] Exécuter la suite complète des 664 tests pytest dans le conteneur `backend` sous Docker.
- [ ] Identifier et corriger d'éventuels écarts environnementaux entre l'hôte et le conteneur (chemins, dépendances verrouillées, variables d'environnement).
- [ ] Exécuter le linter `ruff check .` et le validateur de plans `scripts/validate_plans.py` dans le conteneur.
- [ ] Écrire une suite de tests unitaires ou un script de test validant le comportement de l'outillage Docker.
- [ ] Réaliser la revue contradictoire BMad (4 couches) et consigner les résultats.
- [ ] Mettre à jour l'index des stories et l'état d'avancement dans la documentation de suivi.

## Notes de développement

L'ADR 0006 et la constitution ([`AGENTS.md`](../../AGENTS.md) §2.9) posent Docker comme l'environnement de référence cible unique pour éviter toute dérive entre les postes de développement.

La Story 005-3 valide concrètement cette promesse :
- Le conteneur `backend` doit pouvoir exécuter l'ensemble de la chaîne de qualité (`pytest`, `ruff`, `validate_plans.py`) sans nécessiter d'environnement Python local sur l'hôte.
- Les 664 tests du filet de sécurité doivent être 100 % verts dans le conteneur Debian `python:3.11-slim`, garantissant que toutes les dépendances C (`gcc`, `python3-dev`, `psutil`) et Python (`uv.lock`) sont parfaitement fonctionnelles dans l'image.

## Revue

À compléter lors de la revue BMad.

## Notes de complétion

À rédiger à l'achèvement de la story.
