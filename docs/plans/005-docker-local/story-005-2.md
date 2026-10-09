---
id: "005-2"
epic: "005"
titre: "docker-compose.yml unifié avec Neo4j, Backend, Frontend et Healthchecks"
statut: backlog
auteur: agent
format: "2"
---

# Story 005-2 — docker-compose.yml unifié avec Neo4j, Backend, Frontend et Healthchecks

## Définition de prêt

- [ ] Objectif compris : concevoir le fichier `docker-compose.yml` unifié de référence pour MiroFish, orchestrant les trois services essentiels (`neo4j`, `backend`, `frontend`) sur un réseau dédié `mirofish_network`, avec ordonnancement strict par healthchecks (`condition: service_healthy`), volumes persistants et injection étanche des secrets via `env_file`.
- [ ] Documents consultés : [PRD](prd.md) (notamment critères C1, C3 et C5, exigences FR-1, FR-2, FR-5), [Architecture](architecture.md) (§1, §3, §4, §5), [Epic 005](epic-005.md), [`docker-compose.neo4j.yml`](../../docker-compose.neo4j.yml), [`docker-compose.yml`](../../docker-compose.yml), [ADR 0006](../../decisions/0006-docker-first.md), [ADR 0008](../../decisions/0008-pnpm-seul.md), [AGENTS.md](../../AGENTS.md) (§2.4, §2.9, §3).
- [ ] Prérequis vérifiés : `backend/Dockerfile` et `frontend/Dockerfile` créés et construits avec succès (Story 005-1), configuration prouvée de Neo4j 5.26.31-community avec APOC et healthcheck Bolt disponible dans `docker-compose.neo4j.yml` (Story 001-2).
- [ ] Stratégie de test identifiée : validation de la configuration Compose via `docker compose config`, suite de tests unitaires hermétiques validant la syntaxe YAML, la déclaration des trois services, les règles de dépendances conditionnelles, les volumes nommés et l'absence de fuite de secrets (`backend/tests/test_docker_compose_config.py`).

## Définition de fini

- [ ] `docker-compose.yml` unifié à la racine du dépôt définissant les 3 services `neo4j`, `backend` et `frontend`.
- [ ] Service `neo4j` absorbant fidèlement la configuration de `docker-compose.neo4j.yml` : image `neo4j:5.26.31-community`, plugins APOC débridés (`apoc.meta.data,apoc.merge.*,apoc.create.*`), heap mémoire borné (512m initial, 1G max), volume nommé `neo4j_data` pour `/data`, volume `neo4j_logs` pour `/logs`, ports hôtes 7474 et 7687, healthcheck Bolt Cypher (`cypher-shell RETURN 1`).
- [ ] Service `backend` construit depuis `./backend/Dockerfile` (contexte racine `.`), configuré avec `NEO4J_URI=bolt://neo4j:7687`, `depends_on: { neo4j: { condition: service_healthy } }`, volumes montés pour `./backend/uploads` et `./backend/simulations`, port hôte `${FLASK_PORT:-5001}:5001`, `env_file: .env` et healthcheck HTTP sur `/health`.
- [ ] Service `frontend` construit depuis `./frontend/Dockerfile` (contexte racine `.`), configuré avec port hôte `${FRONTEND_PORT:-3000}:3000`, `depends_on: { backend: { condition: service_healthy } }`.
- [ ] Réseau bridge dédié `mirofish_network` interconnectant les conteneurs avec résolution DNS interne (`neo4j`, `backend`, `frontend`).
- [ ] Volumes nommés déclarés (`neo4j_data`, `neo4j_logs`) assurant que `docker compose down` sans `-v` préserve intégralement les données du graphe.
- [ ] Validation de la configuration via `docker compose config` sans erreur.
- [ ] Suite de tests unitaires hermétiques validant la conformité du compose (`backend/tests/test_docker_compose_config.py`).
- [ ] Tests de non-régression et de structure de plan (`validate_plans.py`, `ruff check`) passants sans avertissement.

## Tâches

- [ ] Concevoir le `docker-compose.yml` unifié intégrant les services `neo4j`, `backend` et `frontend`.
- [ ] Intégrer la configuration prouvée de `docker-compose.neo4j.yml` dans le service `neo4j` (image, APOC, heap, healthcheck Bolt, volumes nommés).
- [ ] Configurer le service `backend` (build context, directives réseau, volumes uploads/simulations, dépendance Neo4j healthy, healthcheck `/health`).
- [ ] Configurer le service `frontend` (build context, exposition de port paramétrable, dépendance backend healthy).
- [ ] Déclarer le réseau `mirofish_network` et les volumes `neo4j_data` et `neo4j_logs`.
- [ ] Adapter la configuration proxy Vite (`frontend/vite.config.js`) pour supporter dynamiquement le nom d'hôte interne du backend sous Docker tout en préservant l'accès local.
- [ ] Écrire la suite de tests unitaires hermétiques (`backend/tests/test_docker_compose_config.py`).
- [ ] Valider la syntaxe avec `docker compose config`.
- [ ] Réaliser la revue contradictoire BMad (4 couches) et consigner les résultats.
- [ ] Mettre à jour l'index des stories et l'état d'avancement dans la documentation de suivi.

## Notes de développement

L'ancien `docker-compose.yml` hérité du dépôt amont présentait trois limitations critiques :
1. Il pointait une image monolithique précompilée (`ghcr.io/666ghj/mirofish:latest`) sans accès à notre code ni aux adaptations local-first.
2. Il ne contenait aucun service `neo4j`, obligeant à recourir à un compose séparé (`docker-compose.neo4j.yml`) utilisé uniquement pendant les phases de prototypage.
3. Il ne comportait aucun mécanisme de healthcheck ni de coordination de démarrage, entraînant des erreurs de connexion transitoires au lancement.

La Story 005-2 unifie l'architecture sous un compose unique de référence :
- **Ordonnancement robuste** : Neo4j vérifie sa réactivité Bolt via `cypher-shell` avant que le Backend ne démarre ; le Backend vérifie la route `/health` de Flask avant que le Frontend n'ouvre son proxy.
- **Topologie réseau claire** : les conteneurs communiquent par leurs noms d'hôtes internes sur le réseau bridge `mirofish_network` (`bolt://neo4j:7687`, `http://backend:5001`), éliminant toute ambiguïté liée à `localhost`.
- **Zéro fuite de secret** : les variables sensibles transitent via `env_file: .env` et l'interpolation Compose (`${NEO4J_PASSWORD}`), sans jamais figer de clé dans le fichier de définition.

## Revue

- **Couche Contrat & Architecture** : À compléter lors de la revue BMad.
- **Couche Hermétisme & Sécurité** : À compléter lors de la revue BMad.
- **Couche Tests & Qualité** : À compléter lors de la revue BMad.

## Notes de complétion

À rédiger à l'achèvement de la story.
