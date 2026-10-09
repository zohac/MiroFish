---
id: "005-2"
epic: "005"
titre: "docker-compose.yml unifié avec Neo4j, Backend, Frontend et Healthchecks"
statut: done
auteur: agent
format: "2"
---

# Story 005-2 — docker-compose.yml unifié avec Neo4j, Backend, Frontend et Healthchecks

## Définition de prêt

- [x] Objectif compris : concevoir le fichier `docker-compose.yml` unifié de référence pour MiroFish, orchestrant les trois services essentiels (`neo4j`, `backend`, `frontend`) sur un réseau dédié `mirofish_network`, avec ordonnancement strict par healthchecks (`condition: service_healthy`), volumes persistants et injection étanche des secrets via `env_file`.
- [x] Documents consultés : [PRD](prd.md) (notamment critères C1, C3 et C5, exigences FR-1, FR-2, FR-5), [Architecture](architecture.md) (§1, §3, §4, §5), [Epic 005](epic-005.md), [`docker-compose.neo4j.yml`](../../docker-compose.neo4j.yml), [`docker-compose.yml`](../../docker-compose.yml), [ADR 0006](../../decisions/0006-docker-first.md), [ADR 0008](../../decisions/0008-pnpm-seul.md), [AGENTS.md](../../AGENTS.md) (§2.4, §2.9, §3).
- [x] Prérequis vérifiés : `backend/Dockerfile` et `frontend/Dockerfile` créés et construits avec succès (Story 005-1), configuration prouvée de Neo4j 5.26.31-community avec APOC et healthcheck Bolt disponible dans `docker-compose.neo4j.yml` (Story 001-2).
- [x] Stratégie de test identifiée : validation de la configuration Compose via `docker compose config`, suite de tests unitaires hermétiques validant la syntaxe YAML, la déclaration des trois services, les règles de dépendances conditionnelles, les volumes nommés et l'absence de fuite de secrets (`backend/tests/test_docker_compose_config.py`).

## Définition de fini

- [x] `docker-compose.yml` unifié à la racine du dépôt définissant les 3 services `neo4j`, `backend` et `frontend`.
- [x] Service `neo4j` absorbant fidèlement la configuration de `docker-compose.neo4j.yml` : image `neo4j:5.26.31-community`, plugins APOC débridés (`apoc.meta.data,apoc.merge.*,apoc.create.*`), heap mémoire borné (512m initial, 1G max), volume nommé `neo4j_data` pour `/data`, volume `neo4j_logs` pour `/logs`, ports hôtes 7474 et 7687, healthcheck Bolt Cypher (`cypher-shell RETURN 1`).
- [x] Service `backend` construit depuis `./backend/Dockerfile` (contexte racine `.`), configuré avec `NEO4J_URI=bolt://neo4j:7687`, `depends_on: { neo4j: { condition: service_healthy } }`, volumes montés pour `./backend/uploads` et `./backend/simulations`, port hôte `${FLASK_PORT:-5001}:5001`, `env_file: .env` et healthcheck HTTP sur `/health`.
- [x] Service `frontend` construit depuis `./frontend/Dockerfile` (contexte racine `.`), configuré avec port hôte `${FRONTEND_PORT:-3000}:3000`, `depends_on: { backend: { condition: service_healthy } }`.
- [x] Réseau bridge dédié `mirofish_network` interconnectant les conteneurs avec résolution DNS interne (`neo4j`, `backend`, `frontend`).
- [x] Volumes nommés déclarés (`neo4j_data`, `neo4j_logs`) assurant que `docker compose down` sans `-v` préserve intégralement les données du graphe.
- [x] Validation de la configuration via `docker compose config` sans erreur.
- [x] Suite de tests unitaires hermétiques validant la conformité du compose (`backend/tests/test_docker_compose_config.py`).
- [x] Tests de non-régression et de structure de plan (`validate_plans.py`, `ruff check`) passants sans avertissement.

## Tâches

- [x] Concevoir le `docker-compose.yml` unifié intégrant les services `neo4j`, `backend` et `frontend`.
- [x] Intégrer la configuration prouvée de `docker-compose.neo4j.yml` dans le service `neo4j` (image, APOC, heap, healthcheck Bolt, volumes nommés).
- [x] Configurer le service `backend` (build context, directives réseau, volumes uploads/simulations, dépendance Neo4j healthy, healthcheck `/health`).
- [x] Configurer le service `frontend` (build context, exposition de port paramétrable, dépendance backend healthy).
- [x] Déclarer le réseau `mirofish_network` et les volumes `neo4j_data` et `neo4j_logs`.
- [x] Adapter la configuration proxy Vite (`frontend/vite.config.js`) pour supporter dynamiquement le nom d'hôte interne du backend sous Docker tout en préservant l'accès local.
- [x] Écrire la suite de tests unitaires hermétiques (`backend/tests/test_docker_compose_config.py`).
- [x] Valider la syntaxe avec `docker compose config`.
- [x] Réaliser la revue contradictoire BMad (4 couches) et consigner les résultats.
- [x] Mettre à jour l'index des stories et l'état d'avancement dans la documentation de suivi.

### Review Findings

- [x] [Review][Patch] Rendre `env_file: .env` optionnel avec `required: false` et adapter la validation de tests unitaires pour garantir l'hermétisme CI [docker-compose.yml:96-98, backend/tests/test_docker_compose_config.py:491-496]
- [x] [Review][Patch] Protéger le port interne du conteneur backend (`FLASK_PORT: 5001`) contre les surcharges dans `.env` [docker-compose.yml:98-100]
- [x] [Review][Patch] Paramétrer les ports hôtes de Neo4j (`${NEO4J_HTTP_PORT:-7474}` et `${NEO4J_BOLT_PORT:-7687}`) et fallback mot de passe [docker-compose.yml:60-64]
- [x] [Review][Patch] Aligner le cycle de vie de la Story 005-2 en formalisant la phase de revue avant clôture [docs/plans/005-docker-local/story-005-2.md:5]
- [x] [Review][Defer] Dépendance du client Axios frontend à `http://localhost:5001` contournant le proxy interne Vite [frontend/src/api/index.js:6] — deferred: préexistant (hérité de l'amont), à consolider lors de la qualification e2e de l'Epic 005 (Story 005-5).

#### Rejected
- Healthcheck cypher-shell extraction password: low (fonctionnement identique à l'existant prouvé dans docker-compose.neo4j.yml).
- Healthcheck sur frontend: low (complexité non justifiée pour un conteneur feuille).
- Assertion statique test_vite_config_proxy_support: low/false (test statique standard dans une suite pytest sans runtime Node).

## Notes de développement

L'ancien `docker-compose.yml` hérité du dépôt amont présentait trois limitations critiques :
1. Il pointait une image monolithique précompilée (`ghcr.io/666ghj/mirofish:latest`) sans accès à notre code ni aux adaptations local-first.
2. Il ne contenait aucun service `neo4j`, obligeant à recourir à un compose séparé (`docker-compose.neo4j.yml`) utilisé uniquement pendant les phases de prototypage.
3. Il ne comportait aucun mécanisme de healthcheck ni de coordination de démarrage, entraînant des erreurs de connexion transitoires au lancement.

La Story 005-2 unifie l'architecture sous un compose unique de référence :
- **Ordonnancement robuste** : Neo4j vérifie sa réactivité Bolt via `cypher-shell` (`RETURN 1`) avant que le Backend ne démarre ; le Backend vérifie la route `/health` de Flask avant que le Frontend n'ouvre son proxy.
- **Topologie réseau claire** : les conteneurs communiquent par leurs noms d'hôtes internes sur le réseau bridge `mirofish_network` (`bolt://neo4j:7687`, `http://backend:5001`), éliminant toute ambiguïté liée à `localhost`.
- **Zéro fuite de secret** : les variables sensibles transitent via `env_file: .env` et l'interpolation Compose (`${NEO4J_PASSWORD}`), sans jamais figer de clé dans le fichier de définition ni injecter `env_file` dans Neo4j.
- **Proxy Vite dynamique** : `frontend/vite.config.js` résout `process.env.BACKEND_URL || 'http://localhost:5001'`, assurant une compatibilité transparente entre l'exécution Docker (`http://backend:5001`) et le développement local sur machine hôte.

## Revue

- **Couche Contrat & Architecture** : Le fichier `docker-compose.yml` unifié formalise l'environnement multi-services complet conformément à l'ADR 0006 et aux spécifications de l'Architecture (§1 à §5). Les trois services (`neo4j`, `backend`, `frontend`) sont isolés et interopérables. L'ordonnancement conditionnel (`service_healthy`) garantit une séquence d'initialisation déterministe (Neo4j -> Backend -> Frontend).
- **Couche Hermétisme & Sécurité** : `env_file: .env` est strictement restreint au service `backend`. `neo4j` reçoit uniquement `NEO4J_AUTH: neo4j/${NEO4J_PASSWORD}` par interpolation. Aucun secret n'est hardcodé. Le réseau `mirofish_network` assure l'étanchéité des communications internes.
- **Couche Tests & Qualité** : 13 tests unitaires dédiés créés dans `backend/tests/test_docker_compose_config.py` couvrant la structure globale, la déclaration des volumes nommés, les configurations spécifiques à chaque service, les healthchecks, le support de `BACKEND_URL` dans Vite et des cas de tests négatifs. La suite complète compte désormais 664 tests passants avec succès.
- **Couche Robustesse & CI** : La commande `docker compose config` valide la cohérence sémantique du fichier sans avertissement. Le script `validate_plans.py` et le linter `ruff` s'exécutent avec un résultat parfait.

## Notes de complétion

La Story 005-2 est intégralement menée à bien et validée :
- `docker-compose.yml` unifié créé avec les 3 services `neo4j`, `backend`, `frontend`, le réseau `mirofish_network` et les volumes nommés `neo4j_data` et `neo4j_logs`.
- `frontend/vite.config.js` adapté pour le proxy dynamique vers le backend sous Docker tout en conservant le fallback hôte.
- Garde-fous `test_neo4j_serveur_epreuve.py` actualisés pour acter l'absorption de Neo4j sous l'Epic 005.
- Nouvelle suite de tests `backend/tests/test_docker_compose_config.py` ajoutée (13 tests hermétiques).
- Validation complète : 664 tests unitaires pytest au vert, 0 warning linter, validation des plans OK.
