# PRD — Epic 005 : Environnement Docker de référence — Docker-first (ADR 0006)

- **Statut** : `in-progress` · **Dépend de** : 001, 002, 003, 004 · **Bloque** : 006, 007
- **Suivi** : [`sprint-status.yaml`](../../sprint-status.yaml)

> L'Epic 001 a prouvé la viabilité de la chaîne Graphiti + Neo4j 5.26 + OpenCode Go en conteneur isolé.  
> L'Epic 002 a posé l'interface neutre `GraphStore` et garanti l'isolation architecturale (0 import Zep direct).  
> L'Epic 003 a implémenté `GraphitiGraphStore`, la persistance partitionnée et la lecture d'entités sans ontologie rigide.  
> L'Epic 004 a levé 100 % des verrous `ZEP_API_KEY`, instauré le LLM universel et validé le pipeline complet de bout en bout (632 tests verts, Verdict GO).  
>
> **L'Epic 005 concrétise l'ADR 0006 (« Docker d'abord : un seul environnement de référence »)** : il unifie l'application complète (Neo4j, Backend Flask, Frontend Vue) au sein d'une configuration `docker-compose.yml` reproductible, autonome, prête pour la production et pour le développement.

---

## 1. Le problème

### 1.1 Contexte et état des lieux

Jusqu'à la clôture de l'Epic 004, l'ensemble du développement s'est déroulé en environnement hôte local (`backend/.venv` avec Python 3.11 + `pnpm` sur l'hôte), avec une exception assumée : l'instance de base de données Neo4j s'exécutant dans un conteneur dédié via `docker-compose.neo4j.yml` (story 001-2).

Cet état temporaire a permis d'avancer rapidement sur les briques applicatives, mais présente les défauts majeurs identifiés dans l'**ADR 0006** :
1. **L'image et le compose actuels pointent sur l'amont** :
   - `docker-compose.yml` pointe sur `image: ghcr.io/666ghj/mirofish:latest`. Cette image amont ne contient **aucune** de nos modifications (ni `GraphStore`, ni `GraphitiGraphStore`, ni `graphiti-core`, ni la paramétrabilité universelle LLM, ni la levée des gardes `ZEP_API_KEY`).
   - Le conteneur s'appelle `mirofish` en un bloc monolithique, au lieu de découper proprement les services `backend`, `frontend` et `neo4j`.
   - Neo4j n'est pas présent dans ce compose : lancer `docker compose up` démarre une image obsolète incapable de fonctionner sans Zep Cloud.
2. **Dualité d'environnements et risque de divergence** :
   - Travailler en local tout en livrant sous Docker crée deux environnements qui finissent inévitablement par diverger : versions système de bibliothèques C, gestionnaires de paquets, variables d'environnement, résolutions réseau.
   - Les commandes mentionnées dans la constitution ([`AGENTS.md`](file:///Users/simon/dev/MiroFish/AGENTS.md) §3) pour Docker (`docker compose run --rm backend uv run pytest tests/ -q`) ne peuvent pas s'exécuter tant que le service `backend` n'est pas défini et construit depuis nos sources.
3. **Disparité réseau et résolution d'hôtes** :
   - En local, l'hôte contacte Neo4j sur `bolt://localhost:7687`.
   - Au sein d'un réseau Docker Compose, le backend doit contacter Neo4j via le nom de service interne `bolt://neo4j:7687`.
   - La configuration doit être fluide et ne nécessiter aucune modification manuelle de code pour basculer entre conteneurs et accès externe.

---

## 2. L'objectif

Faire de Docker l'**environnement de référence absolu** du projet MiroFish (ADR 0006), tel que stipulé dans la constitution ([`AGENTS.md`](file:///Users/simon/dev/MiroFish/AGENTS.md) §2.9) :

1. **Unification des services sous `docker compose`** :
   - Un `docker-compose.yml` de référence décrivant les 3 services essentiels :
     - `neo4j` : instance Neo4j 5.26 Community (absorbant `docker-compose.neo4j.yml`), avec volume persistant nommé `neo4j_data` et healthcheck Bolt.
     - `backend` : service API Flask + Graphiti + moteurs de simulation, basé sur Python 3.11, géré par `uv sync --locked`.
     - `frontend` : service Vue 3 + Vite, géré par `pnpm` (ADR 0008), avec proxy `/api` vers `backend:5001`.
2. **Construction locale (`build: .`) reproductible** :
   - Remplacer l'image amont par des directives de construction explicites s'appuyant sur notre fork `local-first`.
   - Garantir un cache de couches Docker optimal (`COPY pyproject.toml uv.lock` puis `uv sync`, `COPY package.json pnpm-lock.yaml` puis `pnpm install`).
3. **Exécution du filet de tests sous Docker** :
   - Permettre l'exécution immédiate de la suite complète de 632 tests :
     ```bash
     docker compose run --rm backend uv run pytest tests/ -q
     ```
   - 100 % des tests doivent être verts dans le conteneur Linux Python 3.11 de référence.
4. **Persistance et cycle de vie des données** :
   - Les données du graphe Neo4j doivent être conservées dans un volume nommé (`neo4j_data`).
   - `docker compose stop && docker compose start` ou `docker compose down && docker compose up` (sans `-v`) préservent intégralement les graphes et simulations.
   - Les artefacts uploadés et simulations sont montés dans des volumes persistants (`uploads`, `simulations`).
5. **Gestion stricte des secrets et ports sans collision** :
   - Aucun secret en dur ni dans les Dockerfiles ni dans les images : injection exclusive par `env_file: .env`.
   - Paramétrabilité des ports exposés sur l'hôte via variables d'environnement (`FLASK_PORT=5001`, `FRONTEND_PORT=3000` avec repli 3002 si 3000/3001 occupés par d'autres projets sur la machine).

---

## 3. Ce que cet epic n'est pas

| Hors périmètre | Pourquoi |
|---|---|
| Déploiement Kubernetes ou orchestration multi-nœuds | MiroFish est conçu pour une exécution locale ou mono-serveur simple. Docker Compose est la cible adéquate. |
| Migration des données Zep Cloud existantes | Fait l'objet de l'Epic 006 (si nécessaire). |
| Refonte graphique ou fonctionnelle du frontend | Le frontend reste servi avec ses fonctionnalités actuelles ; seul son build/serveur Docker est adressé. |
| Remplacement de Neo4j Community par Enterprise | NFR-1 exige 0 € de coût récurrent et conformité avec les licences libres. |

---

## 4. Topologie cible des services Docker

```
                    ┌────────────────────────────────────────┐
                    │            Machine Hôte                │
                    │                                        │
                    │   Navigateur : http://localhost:3000   │
                    │   API Flask  : http://localhost:5001   │
                    │   Neo4j Bolt : bolt://localhost:7687   │
                    │   Neo4j Web  : http://localhost:7474   │
                    └───────────────────┬────────────────────┘
                                        │ ports exposés
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                       Réseau Docker : mirofish_network                      │
│                                                                             │
│  ┌──────────────────────┐   proxy /api    ┌──────────────────────────────┐  │
│  │       frontend       │ ──────────────> │           backend            │  │
│  │   (Vue 3 / Vite)     │                 │   (Flask / Graphiti / OASIS) │  │
│  │   Port interne 3000  │                 │   Port interne 5001          │  │
│  └──────────────────────┘                 └──────────────┬───────────────┘  │
│                                                          │                  │
│                                                          │ bolt://neo4j:7687│
│                                                          ▼                  │
│                                           ┌──────────────────────────────┐  │
│                                           │            neo4j             │  │
│                                           │  (Neo4j 5.26.31-community)   │  │
│                                           │  Bolt 7687 / HTTP 7474       │  │
│                                           └──────────────┬───────────────┘  │
└──────────────────────────────────────────────────────────┼──────────────────┘
                                                           │
                                                           ▼
                                               [ Volume nommé : neo4j_data ]
```

---

## 5. Configuration et Variables d'Environnement

Le fichier `.env` de l'hôte reste la source unique de vérité. Docker Compose y puise les variables pour l'interpolation et l'injection :

```ini
# --- Backend & LLM ---
ZEP_BACKEND=graphiti
FLASK_PORT=5001
FRONTEND_PORT=3000
LLM_BASE_URL=https://opencode.ai/zen/go/v1
LLM_API_KEY=votre_cle_llm
LLM_MODEL_NAME=space-bunny-free
LLM_REASONING_EFFORT=medium
GRAPHITI_TELEMETRY_ENABLED=false

# --- Base de données Neo4j ---
# Pour l'hôte (tests locaux) :
NEO4J_URI=bolt://localhost:7687
# Pour les conteneurs (override automatique dans docker-compose) :
# NEO4J_URI_DOCKER=bolt://neo4j:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=votre_mot_de_passe_securise
```

---

## 6. Exigences fonctionnelles (FR)

- **FR-1 (Compose unifié multi-services)** : `docker-compose.yml` définit les 3 services interconnectés : `neo4j`, `backend`, `frontend`, partageant un réseau dédié (`mirofish-network`).
- **FR-2 (Absorption de `docker-compose.neo4j.yml`)** : Le service `neo4j` reprend exactement la configuration prouvée lors de la story 001-2 (`neo4j:5.26.31-community`, healthcheck Bolt sur `cypher-shell`, volume persistant nommé `neo4j_data`, mot de passe depuis `.env`).
- **FR-3 (Construction locale des images)** : Le backend et le frontend sont construits depuis le code source du dépôt (`Dockerfile` multi-stage ou Dockerfiles dédiés `backend/Dockerfile` et `frontend/Dockerfile`).
- **FR-4 (Dépendances verrouillées et cache optimal)** :
  - Python : `uv sync --locked` (garantit le respect strict de `uv.lock`).
  - Node : `pnpm install --frozen-lockfile` (garantit le respect de `pnpm-lock.yaml`, ADR 0008).
- **FR-5 (Ordonnancement et Healthchecks)** :
  - Le `backend` attend que `neo4j` soit dans un état `healthy` avant de démarrer (`depends_on: { neo4j: { condition: service_healthy } }`).
  - Le `frontend` démarre et proxyfie les requêtes `/api/*` vers le `backend`.
- **FR-6 (Support de l'outillage de test et CLI)** :
  - Possibilité d'exécuter `docker compose run --rm backend uv run pytest tests/ -q`.
  - Possibilité d'exécuter les scripts de vérification dans le conteneur (`verifier_qualification_local_first.py`).

---

## 7. Exigences non fonctionnelles (NFR)

- **NFR-1 (Sécurité & Secrets)** : Aucun mot de passe ni token dans les Dockerfiles ni dans les couches d'images. `.env` n'est jamais copié (`COPY .env` interdit).
- **NFR-2 (Reproductibilité)** : Aucun tag flottant (`latest` banni pour les bases de données, versions fixées pour Python 3.11, Node, pnpm et Neo4j 5.26.31).
- **NFR-3 (Persistance des données)** : Les graphes et historiques survivent aux arrêts et redémarrages de conteneurs (`docker compose down` sans `-v` ne perd aucune donnée).
- **NFR-4 (Compatibilité des ports)** : Les ports sont configurables pour éviter les conflits avec des services existants sur l'hôte (ports 3000/3001).
- **NFR-5 (Performance de démarrage)** : Démarrage complet de la stack (`docker compose up -d --wait`) en moins de 60 secondes sur une machine standard.

---

## 8. Critères de sortie — chiffrés

| # | Critère | Seuil exigé | Risque si non atteint |
|---|---|---|---|
| **C1** | **Démarrage unifié sans erreur** | `docker compose up -d` démarre les 3 services (`neo4j`, `backend`, `frontend`) avec statut `healthy`/`running` en **$\le 60$ secondes**. | Déploiement cassé ou instable |
| **C2** | **Filet global de tests vert sous Docker** | `docker compose run --rm backend uv run pytest tests/ -q` valide **100 % des 632 tests existants** au vert dans le conteneur. | Dérive environnementale local/Docker |
| **C3** | **Persistance des données Neo4j** | Un graphe créé dans Neo4j est **100 % intact** après un cycle `docker compose down && docker compose up -d` (sans flag `-v`). | Perte de données utilisateur |
| **C4** | **Pipeline complet e2e dans Docker** | Le banc de qualification globale (`verifier_qualification_local_first.py`) s'exécute avec succès (`code retour 0`) à l'intérieur du conteneur `backend` connecté à `neo4j`. | Incompatibilité réseau inter-conteneurs |
| **C5** | **0 secret dans les images et validation CI** | L'inspection `docker history` confirme **0 token ou mot de passe** dans les couches d'images. Le linter `ruff check` et `validate_plans.py` passent sans avertissement. | Fuite de sécurité / non-conformité |
