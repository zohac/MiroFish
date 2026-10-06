---
id: "002-4"
epic: "002"
titre: "Refactoring de l'ingestion (graph_builder, zep_graph_memory_updater, simulation_runner)"
statut: done
auteur: agent
format: "2"
---

# Story 002-4 — Refactoring de l'ingestion (graph_builder, zep_graph_memory_updater, simulation_runner)

## Pourquoi cette story

L'Epic 002 a pour objectif de découpler MiroFish du fournisseur de graphe de connaissances Zep Cloud (ADR 0001, AGENTS.md §2.1).
Les stories précédentes ont préparé le terrain :
- La story 002-1 a défini l'interface neutre `GraphStore`, ses modèles de données et ses exceptions.
- La story 002-2 a implémenté `ZepGraphStore`, encapsulant l'accès au SDK Zep Cloud, les retries et la pagination.
- La story 002-3 a mis en place la factory centralisée `get_graph_store()`, pilotée par `ZEP_BACKEND` (défaut `'cloud'`), avec gestion d'override (`override_graph_store`).

L'étape suivante consiste à **refactorer les flux d'ingestion et d'écriture** de l'application :
1. `backend/app/services/graph_builder.py` : construction initiale du graphe à partir des documents sources.
2. `backend/app/services/zep_graph_memory_updater.py` : injection asynchrone des souvenirs et activités des agents au fil des tours de simulation.
3. `backend/app/services/simulation_runner.py` : orchestration des barrières de synchronisation d'ingestion.

Aujourd'hui, ces modules importaient directement `zep_cloud` et les fonctions bas niveau de `utils.zep` (`get_zep_client`, `call_zep_read_with_retry`, `is_retryable_zep_error`) ainsi que `zep_paging.py`.
Ce couplage direct empêchait l'aiguillage transparent vers Graphiti (Epic 003).

Cette story refactore ces trois composants pour qu'ils s'appuient exclusivement sur l'interface `GraphStore` obtenue via `get_graph_store()`, sans aucun appel direct au client Zep propriétaire, tout en maintenant 100 % de compatibilité comportementale et la totalité des tests existants au vert.

## Définition de prêt

- [x] Interface `GraphStore` posée et testée dans `backend/app/utils/graph_store/base.py` (Story 002-1)
- [x] Implémentation `ZepGraphStore` opérationnelle et testée dans `backend/app/utils/graph_store/zep_store.py` (Story 002-2)
- [x] Factory `get_graph_store()` et mécanisme d'injection `override_graph_store` validés et testés (Story 002-3)
- [x] Points de couplage Zep identifiés dans `graph_builder.py`, `zep_graph_memory_updater.py` et `simulation_runner.py`
- [x] Stratégie de non-régression établie sur les suites de tests existantes (`test_zep_graph_memory_updater.py`, `test_zep_simulation_barrier.py`, `test_simulation_prepare_failure.py`, `test_ontology_attributes.py`)
- [x] Documents à consulter lus — [`epic-002.md`](epic-002.md), [`architecture.md`](architecture.md), [`prd.md`](prd.md), [ADR 0001](../../decisions/0001-remplacement-de-zep-par-graphiti.md), [`docs/LOCAL-FIRST.md`](../../LOCAL-FIRST.md) §5

## Définition de fini

- [x] `backend/app/services/graph_builder.py` n'importe plus `zep_cloud`, `utils.zep` ni `utils.zep_paging` ; toutes ses opérations de création, ontologie, batch et lecture passent par `GraphStore`
- [x] `backend/app/services/zep_graph_memory_updater.py` n'importe plus `utils.zep.get_zep_client` ni `call_zep_read_with_retry` ; les ajouts d'épisodes et l'attente de traitement passent par `GraphStore`
- [x] `backend/app/services/simulation_runner.py` n'importe plus de constantes propriétaires depuis `utils.zep`
- [x] L'instanciation du store dans les services accepte une instance optionnelle `store: Optional[GraphStore] = None` et recourt à `get_graph_store(api_key=...)` par défaut
- [x] 0 régression sur l'ensemble des fonctionnalités d'ingestion et de simulation
- [x] Les tests existants associés restent 100 % au vert et sont adaptés pour utiliser `FakeGraphStore` ou le mock de store sans dépendance réseau
- [x] 100 % des tests du projet (≥ 442 tests) passent avec succès (`uv run pytest tests/ -q` → 452 tests verts)
- [x] `uv run ruff check .` et `uv run python scripts/validate_plans.py` passent sans avertissement

## Tâches

- [x] Refactorer `backend/app/services/graph_builder.py` :
  - [x] Supprimer les imports directs de `zep_cloud` (`BatchAddItem`, `EntityEdgeSourceTarget`, `NotFoundError`, `EntityModel`, `EdgeModel`, etc.)
  - [x] Supprimer les imports de `..utils.zep` (`get_zep_client`, `call_zep_read_with_retry`, `is_retryable_zep_error`) et `..utils.zep_paging`
  - [x] Injecter `self.store: GraphStore = store or get_graph_store(api_key=self.api_key)` dans `GraphBuilderService.__init__`
  - [x] Déléguer `create_graph()` à `self.store.create_graph()`
  - [x] Déléguer `set_ontology()` à `self.store.set_ontology()`
  - [x] Déléguer l'ingestion par lots et le découpage à `self.store.add_text_batch()`
  - [x] Déléguer l'attente du lot asynchrone à `self.store.wait_for_batch()` avec transmission du callback de progression
  - [x] Déléguer `get_graph_data()` et `get_graph_info()` à `self.store`
  - [x] Traduire les exceptions capturées vers la hiérarchie `GraphStoreError`
- [x] Refactorer `backend/app/services/zep_graph_memory_updater.py` :
  - [x] Supprimer les imports de `..utils.zep` (`get_zep_client`, `call_zep_read_with_retry`)
  - [x] Injecter `self.store: GraphStore = store or get_graph_store(api_key=self.api_key)` dans `ZepGraphMemoryUpdater.__init__`
  - [x] Déléguer l'ajout d'épisode dans `_send_batch_activities()` à `self.store.add_episode()`
  - [x] Déléguer le polling de complétion dans `_wait_for_pending_episodes()` à `self.store.wait_for_episodes()`
  - [x] Maintenir la rétrocompatibilité des classes et alias publics (`ZepGraphMemoryUpdater`, `ZepGraphMemoryManager`)
- [x] Nettoyer `backend/app/services/simulation_runner.py` :
  - [x] Remplacer les imports de `ZEP_HTTP_REQUEST_TIMEOUT_SECONDS` et `ZEP_INGESTION_WAIT_TIMEOUT_SECONDS` depuis `..utils.zep` par des constantes locales décorrélées du SDK
- [x] Adapter et enrichir les tests unitaires :
  - [x] Adapter `tests/test_zep_graph_memory_updater.py` et `tests/test_zep_cloud_contracts.py` pour fonctionner avec injection de store
  - [x] Créer la suite de tests dédiée `tests/test_graph_builder_refactor.py` couvrant l'injection de `MockIngestionStore`
- [x] Valider la non-régression globale (`uv run pytest tests/ -q` → 452 tests)
- [x] Contrôler `ruff check .` et `validate_plans.py`

## Notes de développement

- **Inversion de dépendance (Clean Architecture)** :
  `services/graph_builder.py` et `services/zep_graph_memory_updater.py` dépendent désormais uniquement de l'abstraction `utils/graph_store`.
  Ils ne connaissent ni `zep_cloud` ni les particularités du SDK sous-jacent.
- **Rétrocompatibilité des signatures et accès clients** :
  `GraphBuilderService` et `ZepGraphMemoryUpdater` conservent leur paramètre `api_key: Optional[str] = None` et ajoutent `store: Optional[GraphStore] = None`. Une property `client` avec setter crée dynamiquement un `ZepGraphStore(client=...)` si un mock de client historique est assigné.
- **Gestion des exceptions** :
  `GraphStoreError` hérite de `RuntimeError` et `GraphTimeoutError` hérite de `(GraphStoreError, TimeoutError)`, assurant une parfaite interopérabilité avec les gestionnaires d'erreurs standards de Python et de MiroFish.
- **Découplage de simulation_runner** :
  `simulation_runner.py` ne dépend plus d'aucun symbole de `utils.zep`. Les timeouts de barrière sont pilotés par des constantes découplées `GRAPH_INGESTION_WAIT_TIMEOUT_SECONDS` et `GRAPH_HTTP_REQUEST_TIMEOUT_SECONDS`.

## Revue

Revue contradictoire menée par 4 couches indépendantes (*Blind Hunter*, *Edge Case Hunter*, *Verification Gap*, *Acceptance Auditor*).
Bilan du triage : 0 `decision-needed`, 8 `patch`, 0 `defer`, 0 rejeté.

### Constats de revue retenus (Patch)

- [x] [Review][Patch] Import différé (lazy-import) de `ZepGraphStore` dans `GraphBuilderService.client.setter` et `ZepGraphMemoryUpdater.client.setter` pour garantir l'absence totale de chargement de `zep_cloud` à l'import de module [`backend/app/services/graph_builder.py:24`, `backend/app/services/zep_graph_memory_updater.py:20`]
- [x] [Review][Patch] Adaptateur de callback de progression dans `add_text_batches` pour supporter les signatures à 2 arguments `(msg, prog)` et à 3 arguments `(status, current, total)` sans `TypeError` [`backend/app/services/graph_builder.py:238-266`]
- [x] [Review][Patch] Correction des échelles de calcul de progression dans `_build_graph_worker` (`progress=20 + int(prog * 40)` pour 20-60% et `progress=60 + int(prog * 30)` pour 60-90%) [`backend/app/services/graph_builder.py:168,183`]
- [x] [Review][Patch] Levée immédiate de `GraphTimeoutError` si `deadline` est déjà échue dans `_wait_for_pending_episodes` pour éviter un faux `GraphValidationError` sur timeout <= 0 [`backend/app/services/zep_graph_memory_updater.py:535-540`]
- [x] [Review][Patch] Renforcement strict du test de découplage `test_graph_builder_imports_are_decoupled_from_zep_cloud` sans disjonction tautologique `or` [`backend/tests/test_graph_builder_refactor.py:2440`]
- [x] [Review][Patch] Ajout d'un test unitaire d'intégration couvrant l'exécution complète de `_build_graph_worker` avec suivi de progression et `TaskManager` [`backend/tests/test_graph_builder_refactor.py`]
- [x] [Review][Patch] Remplacement du littéral magique `600.0` par la constante de module `DEFAULT_INGESTION_WAIT_TIMEOUT_SECONDS` dans `graph_builder.py` [`backend/app/services/graph_builder.py:289,310`]
- [x] [Review][Patch] Prise en charge des instances de `GraphStore` dans `client.setter` (`if isinstance(value, GraphStore): self.store = value`) [`backend/app/services/graph_builder.py:56`, `backend/app/services/zep_graph_memory_updater.py:1441`]

## Notes de complétion

Implémentation complète du refactoring de l'ingestion :
- Découplage intégral de `GraphBuilderService`, `ZepGraphMemoryUpdater`, `ZepGraphMemoryManager` et `SimulationRunner`.
- Aucun import direct de `zep_cloud` ni de `utils.zep` dans la couche de services d'ingestion.
- Revue contradictoire BMad 4 couches validée : 8 patchs appliqués (import différé de `ZepGraphStore`, adaptation d'arité de callback, redressement des échelles de progression, gestion stricte du deadline expiré, constantes partagées, et extension des tests).
- Création et enrichissement de la suite `tests/test_graph_builder_refactor.py` (10 tests unitaires hermétiques avec store factice `MockIngestionStore`).
- Filet de sécurité étendu à 452 tests (100 % passants).
- Vérifications de style `ruff check` et de conformité de planification `validate_plans.py` validées à 100 %.
