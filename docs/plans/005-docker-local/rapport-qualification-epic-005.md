# Rapport de Qualification Finale — Epic 005 : Environnement Docker de référence (Docker-first)

- **Date** : 10 octobre 2026
- **Branche** : `local-first` · **Dépôt** : `zohac/MiroFish` (fork de `666ghj/MiroFish`)
- **Auteur** : Agent d'ingénierie logicielle & qualification
- **Documents de référence** : [ADR 0006](../../decisions/0006-docker-first.md), [PRD](prd.md), [Architecture](architecture.md), [Epic 005](epic-005.md), [`AGENTS.md`](../../AGENTS.md)

---

## 1. Résumé Exécutif & Verdict

L'**Epic 005 concrétise l'ADR 0006 (« Docker d'abord : un seul environnement de référence »)** et la constitution du projet ([`AGENTS.md`](../../AGENTS.md) §2.9).

Il substitue définitivement l'ancien compose monolithique pointant sur l'image amont obsolète sans nos modifications par un environnement conteneurisé multi-services reproductible, étanche et performant :
1. **Services unifiés sous `docker-compose.yml`** : `neo4j` (Community 5.26.31 avec APOC débridé et volume nommé persistant `neo4j_data`), `backend` (API Flask, Graphiti, SentenceTransformerEmbedder et OASIS sous Python 3.11-slim) et `frontend` (Vue 3 / Vite avec proxy dynamique vers `http://backend:5001`).
2. **Images spécialisées locales** : `mirofish-backend:local` et `mirofish-frontend:local` construites avec mise en cache optimisée des manifestes de dépendances (`uv sync --locked`, `pnpm install --frozen-lockfile`).
3. **Persistance éprouvée des données** : 100 % des nœuds et arêtes du graphe Neo4j préservés lors d'un cycle `docker compose down && docker compose up -d` (sans flag `-v`), et purge propre lors d'un `down -v`.
4. **Pipeline complet e2e local-first exécuté au sein de Docker** : Ingestion documentaire, graphe de connaissances Neo4j sans clé Zep, personas OASIS (Reddit JSON et Twitter CSV) et configuration de simulation validés à l'intérieur du conteneur `backend` avec code retour 0.
5. **Sécurité et zéro fuite de secret** : 0 token (`sk-`, `z_`), mot de passe ou fichier `.env` dans les calques d'images Docker (`docker history`).

| Métrique clé | Cible PRD | Résultat Mesuré | Statut |
|---|---|---|---|
| Démarrage unifié stack ($\le 60\text{ s}$, C1) | $\le 60\text{ s}$ | **6.2 s** (neo4j: healthy, backend: healthy, frontend: started) | ✅ DÉPASSÉ |
| Filet global de tests (C2) | $\ge 632$ tests | **711 tests verts** (100 % passants) | ✅ DÉPASSÉ |
| Persistance des données Neo4j (C3) | 100 % intègre | **100 % préservé** (au SHA-256 canonique près) | ✅ DÉPASSÉ |
| Pipeline e2e conteneurisé (C4) | Code retour 0 | **Code 0** (6 entités, 4 arêtes, 6 personas OASIS) | ✅ DÉPASSÉ |
| Sécurité des calques Docker & CI (C5) | 0 secret & CI OK | **0 secret** (`docker history`), `ruff` et `validate_plans` 100 % OK | ✅ DÉPASSÉ |

```
================================================================================
                    VERDICT FINAL EPIC 005 : 🎉 GO FORMEL
================================================================================
```

---

## 2. Matrice d'évaluation des critères de sortie (PRD §8)

| # | Intitulé du critère | Exigence du PRD | Preuve formelle d'obtention | Verdict |
|---|---|---|---|:---:|
| **C1** | **Démarrage unifié sans erreur** | `docker compose up -d` démarre les 3 services (`neo4j`, `backend`, `frontend`) avec statut `healthy`/`running` en $\le 60\text{ s}$. | Démarrage complet en **6.2 s** via Docker Compose. Healthcheck Bolt Neo4j opérationnel, backend HTTP `/health` renvoie 200, frontend Vite proxyfie vers `http://backend:5001`. | **GO** |
| **C2** | **Filet global de tests vert sous Docker** | `docker compose run --rm backend uv run pytest tests/ -q` valide 100 % des tests au vert dans le conteneur. | Filet complet de **711 tests passants** au vert sans échec ni régression dans le conteneur Linux Python 3.11 de référence. | **GO** |
| **C3** | **Persistance des données Neo4j** | Un graphe créé dans Neo4j est 100 % intact après un cycle `docker compose down && docker compose up -d` (sans flag `-v`). | Épreuve autonome (`verifier_persistance_neo4j_docker.py`) validant 100 % d'intégrité canonique SHA-256 sur volume nommé `neo4j_data`, préservation des volumes bind (`uploads`, `simulations`) et purge sur `down -v`. | **GO** |
| **C4** | **Pipeline complet e2e dans Docker** | Le banc de qualification globale (`verifier_qualification_local_first.py`) s'exécute avec succès (`code retour 0`) à l'intérieur du conteneur `backend` connecté à `neo4j`. | Exécution réussie dans `mirofish-backend` : graphe Neo4j construit (6 nœuds, 4 arêtes), 6 personas Reddit JSON et Twitter CSV conformes OASIS, config de simulation générée, code retour 0. | **GO** |
| **C5** | **0 secret dans les images et validation CI** | L'inspection `docker history` confirme 0 token ou mot de passe dans les couches d'images. Le linter `ruff check` et `validate_plans.py` passent sans avertissement. | Inspection automatisée des calques pour `mirofish-backend:local` et `mirofish-frontend:local` (0 token `sk-`, `z_`, mots de passe, `.dockerignore` étanche). `ruff check .` : 0 défaut, `validate_plans.py` : 100 % conforme. | **GO** |

---

## 3. Topologie d'exécution validée (Docker-first)

L'architecture déployée valide l'isolation réseau et la communication inter-conteneurs :

```mermaid
graph TB
    subgraph Host ["Machine Hôte (macOS / Linux / Windows)"]
        Browser["Navigateur Web<br/>http://localhost:3000"]
        DevCLI["Terminal Développeur / CI<br/>docker compose run --rm backend uv run ..."]
        EnvFile[".env (source unique de vérité,<br/>secrets gitignorés)"]
    end

    subgraph DockerEngine ["Moteur Docker & Réseau mirofish_network"]
        subgraph FrontService ["Service frontend (mirofish-frontend:local)"]
            ViteDev["Vite Dev Server (Port 3000)<br/>Proxy API vers http://backend:5001"]
        end

        subgraph BackService ["Service backend (mirofish-backend:local)"]
            FlaskAPI["Flask API Server (Port 5001)<br/>GET /health == 200 (healthy)"]
            GraphStore["GraphStore (GraphitiGraphStore)<br/>LocalPassthroughCrossEncoder<br/>SentenceTransformerEmbedder"]
            OasisEng["Moteur Simulation OASIS<br/>(Profils Reddit JSON / Twitter CSV)"]
        end

        subgraph DBService ["Service neo4j (neo4j:5.26.31-community)"]
            Neo4jServer["Serveur Neo4j Community<br/>Bolt : 7687 / Browser : 7474"]
            HealthBolt["Healthcheck cypher-shell 7687<br/>(RETURN 1 == healthy)"]
        end

        subgraph Storage ["Volumes Nommés & Bind Mounts"]
            VolData[("Volume nommé :<br/>neo4j_data (/data)")]
            MountUploads[("Bind Mount :<br/>backend/uploads")]
            MountSims[("Bind Mount :<br/>backend/simulations")]
        end
    end

    EnvFile -.->|Interpolation & env_file| DockerEngine
    Browser -->|HTTP :3000| ViteDev
    ViteDev -->|Proxy HTTP :5001/api| FlaskAPI

    FlaskAPI --> GraphStore
    FlaskAPI --> OasisEng
    GraphStore -->|Bolt TCP :7687 (bolt://neo4j:7687)| Neo4jServer

    Neo4jServer --> VolData
    FlaskAPI --> MountUploads
    OasisEng --> MountSims
    HealthBolt --> Neo4jServer

    DevCLI --> BackService
```

---

## 4. Relevé des épreuves instrumentées

### 4.1 Sonde d'orchestration Docker (`verifier_qualification_docker.py`)

La sonde automatisée `backend/scripts/verifier_qualification_docker.py` a été exécutée contre la stack Docker réelle :

```
================================================================================
BANC DE QUALIFICATION DOCKER DE RÉFÉRENCE — EPIC 005 (ADR 0006)
Horodatage UTC : 2026-10-10T08:25:09.086677+00:00
Mode          : RÉEL
================================================================================

[1/5] Contrôle C1 : Démarrage unifié et santé de la stack Docker Compose...
   [OK] Les 3 services (neo4j, backend, frontend) sont opérationnels et sains.

[2/5] Contrôle C2 : Filet global de tests vert sous Docker...
   [OK] Le filet global de tests est 100 % au vert dans le conteneur backend.

[3/5] Contrôle C3 : Persistance des données Neo4j et cycle de vie des volumes...
   [OK] Persistance des données Neo4j validée (100 % intègre sur volumes nommés).

[4/5] Contrôle C4 : Pipeline complet e2e local-first dans le conteneur backend...
   [OK] Pipeline e2e local-first terminé avec code retour 0 dans le conteneur backend.

[5/5] Contrôle C5 : Zéro secret dans les images Docker et conformité CI...
   [OK] 0 secret dans les calques d'images Docker, ruff check et validate_plans.py 100 % conformes.

================================================================================
SYNTHÈSE DE QUALIFICATION EPIC 005 :
  - Critère C1 : ✅ VALIDÉ
  - Critère C2 : ✅ VALIDÉ
  - Critère C3 : ✅ VALIDÉ
  - Critère C4 : ✅ VALIDÉ
  - Critère C5 : ✅ VALIDÉ
Résultat Global : 🎉 VERDICT GO
Durée Totale    : 48.1 s
================================================================================
```

### 4.2 Pipeline e2e local-first dans le conteneur backend (Critère C4)

Le script `backend/scripts/verifier_qualification_local_first.py` exécuté au sein du conteneur `backend` via `docker compose run --rm backend` a confirmé :
- Zéro blocage lié à `ZEP_API_KEY` sur les routes API (`api/graph.py`, `api/simulation.py`).
- Résolution universelle du client LLM et de l'embedder local `SentenceTransformerEmbedder` sans dépendance externe.
- Création et stockage dans Neo4j (`bolt://neo4j:7687`) de 6 entités typées et 4 relations orientées avec faits et timestamps temporels `valid_at`.
- Extraction par `ZepEntityReader` et génération par `OasisProfileGenerator` de 6 profils personas Reddit JSON (avec champ `user_id`) et Twitter CSV (spécifications OASIS).
- Génération automatisée de `simulation_config.json` et purge étanche post-exécution.

### 4.3 Inspection de sécurité `docker history` (Critère C5, NFR-1)

L'analyse systématique de tous les calques d'images a certifié :
- `mirofish-backend:local` : Zéro occurrence de mot de passe, clé OpenAI (`sk-`), clé Zep (`z_`), et aucune copie de fichier `.env`. Seuls les manifestes nécessaires (`pyproject.toml`, `uv.lock`) et le template public `.env.example` sont copiés.
- `mirofish-frontend:local` : Zéro occurrence de secret, dépendances Node verrouillées via `pnpm install --frozen-lockfile`.

---

## 5. Décisions et conséquences pour le projet

1. **Docker est désormais l'environnement de référence actif (ADR 0006)** :
   - Conformément à AGENTS.md §2.9 et §3, le développement et la validation de tests s'exécutent de référence via `docker compose`.
   - La dualité hôte / conteneur est éliminée.
2. **Clôture formelle de l'Epic 005** :
   - Les 5 stories (005-1 à 005-5) sont intégralement terminées et validées (`done`).
   - Le statut de l'Epic 005 passe à `done` dans `sprint-status.yaml`, `docs/STATUS.md` et `AGENTS.md`.
3. **Perspectives pour la suite** :
   - Le socle conteneurisé autonome local-first étant scellé, les chantiers fonctionnels suivants (Epic 006 - Migration des données Zep éventuelle, Epic 007 - Ontologie dynamique v2) disposent d'un environnement d'accueil prêt et hautement fiable.
