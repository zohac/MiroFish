---
id: "002-4"
epic: "002"
titre: "Refactoring de l'ingestion (graph_builder, zep_graph_memory_updater, simulation_runner)"
statut: in-progress
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

Aujourd'hui, ces modules importent directement `zep_cloud` et les fonctions bas niveau de `utils.zep` (`get_zep_client`, `call_zep_read_with_retry`, `is_retryable_zep_error`) ainsi que `zep_paging.py`.
Ce couplage direct empêche l'aiguillage transparent vers Graphiti (Epic 003).

Cette story refactore ces trois composants pour qu'ils s'appuient exclusivement sur l'interface `GraphStore` obtenue via `get_graph_store()`, sans aucun appel direct au client Zep propriétaire, tout en maintenant 100 % de compatibilité comportementale et la totalité des tests existants au vert.

## Définition de prêt

- [x] Interface `GraphStore` posée et testée dans `backend/app/utils/graph_store/base.py` (Story 002-1)
- [x] Implémentation `ZepGraphStore` opérationnelle et testée dans `backend/app/utils/graph_store/zep_store.py` (Story 002-2)
- [x] Factory `get_graph_store()` et mécanisme d'injection `override_graph_store` validés et testés (Story 002-3)
- [x] Points de couplage Zep identifiés dans `graph_builder.py`, `zep_graph_memory_updater.py` et `simulation_runner.py`
- [x] Stratégie de non-régression établie sur les suites de tests existantes (`test_zep_graph_memory_updater.py`, `test_zep_simulation_barrier.py`, `test_simulation_prepare_failure.py`, `test_ontology_attributes.py`)
- [x] Documents à consulter lus — [`epic-002.md`](epic-002.md), [`architecture.md`](architecture.md), [`prd.md`](prd.md), [ADR 0001](../../decisions/0001-remplacement-de-zep-par-graphiti.md), [`docs/LOCAL-FIRST.md`](../../LOCAL-FIRST.md) §5

## Définition de fini

- [ ] `backend/app/services/graph_builder.py` n'importe plus `zep_cloud`, `utils.zep` ni `utils.zep_paging` ; toutes ses opérations de création, ontologie, batch et lecture passent par `GraphStore`
- [ ] `backend/app/services/zep_graph_memory_updater.py` n'importe plus `utils.zep.get_zep_client` ni `call_zep_read_with_retry` ; les ajouts d'épisodes et l'attente de traitement passent par `GraphStore`
- [ ] `backend/app/services/simulation_runner.py` n'importe plus de constantes propriétaires depuis `utils.zep`
- [ ] L'instanciation du store dans les services accepte une instance optionnelle `store: Optional[GraphStore] = None` et recourt à `get_graph_store(api_key=...)` par défaut
- [ ] 0 régression sur l'ensemble des fonctionnalités d'ingestion et de simulation
- [ ] Les tests existants associés restent 100 % au vert et sont adaptés pour utiliser `FakeGraphStore` ou le mock de store sans dépendance réseau
- [ ] 100 % des tests du projet (≥ 442 tests) passent avec succès (`uv run pytest tests/ -q`)
- [ ] `uv run ruff check .` et `uv run python scripts/validate_plans.py` passent sans avertissement

## Tâches

- [ ] Refactorer `backend/app/services/graph_builder.py` :
  - [ ] Supprimer les imports directs de `zep_cloud` (`BatchAddItem`, `EntityEdgeSourceTarget`, `NotFoundError`, `EntityModel`, `EdgeModel`, etc.)
  - [ ] Supprimer les imports de `..utils.zep` (`get_zep_client`, `call_zep_read_with_retry`, `is_retryable_zep_error`) et `..utils.zep_paging`
  - [ ] Injecter `self.store: GraphStore = store or get_graph_store(api_key=self.api_key)` dans `GraphBuilderService.__init__`
  - [ ] Déléguer `_create_graph()` à `self.store.create_graph()`
  - [ ] Déléguer `_set_ontology()` à `self.store.set_ontology()`
  - [ ] Déléguer l'ingestion par lots et le découpage à `self.store.add_text_batch()`
  - [ ] Déléguer l'attente du lot asynchrone à `self.store.wait_for_batch()` avec transmission du callback de progression
  - [ ] Déléguer `_get_graph_data()` à `self.store.get_graph_data()`
  - [ ] Traduire les exceptions capturées vers la hiérarchie `GraphStoreError`
- [ ] Refactorer `backend/app/services/zep_graph_memory_updater.py` :
  - [ ] Supprimer les imports de `..utils.zep` (`get_zep_client`, `call_zep_read_with_retry`)
  - [ ] Injecter `self.store: GraphStore = store or get_graph_store(api_key=self.api_key)` dans `ZepGraphMemoryUpdater.__init__`
  - [ ] Déléguer l'ajout d'épisode dans `_add_memory_episode()` à `self.store.add_episode()`
  - [ ] Déléguer le polling de complétion dans `_wait_for_episodes()` à `self.store.wait_for_episodes()`
  - [ ] Maintenir la rétrocompatibilité des classes et alias publics (`ZepGraphMemoryUpdater`, `ZepGraphMemoryManager`)
- [ ] Nettoyer `backend/app/services/simulation_runner.py` :
  - [ ] Remplacer les imports de `ZEP_HTTP_REQUEST_TIMEOUT_SECONDS` et `ZEP_INGESTION_WAIT_TIMEOUT_SECONDS` depuis `..utils.zep` par des constantes locales ou issues de `config.py`
- [ ] Adapter et enrichir les tests unitaires :
  - [ ] Adapter `tests/test_zep_graph_memory_updater.py` et `tests/test_zep_simulation_barrier.py` pour fonctionner avec des mocks de `GraphStore` / `FakeGraphStore`
  - [ ] Créer ou adapter les tests de `graph_builder.py` avec injection de store factice sans réseau
- [ ] Valider la non-régression globale (`uv run pytest tests/ -q`)
- [ ] Contrôler `ruff check .` et `validate_plans.py`

## Notes de développement

- **Inversion de dépendance (Clean Architecture)** :
  `services/graph_builder.py` et `services/zep_graph_memory_updater.py` dépendent désormais uniquement de l'abstraction `utils/graph_store`.
  Ils ne connaissent ni `zep_cloud` ni les particularités du SDK sous-jacent.
- **Rétrocompatibilité des signatures** :
  `GraphBuilderService` et `ZepGraphMemoryUpdater` conservent leur paramètre `api_key: Optional[str] = None` pour ne pas casser les appelants actuels (`api/graph.py`, scripts de simulation), mais ajoutent un paramètre optionnel `store: Optional[GraphStore] = None` permettant l'injection directe en test unitaire.
- **Gestion des exceptions** :
  Toutes les erreurs levées par `GraphStore` appartiennent à la hiérarchie agnostique `GraphStoreError` (`GraphNotFoundError`, `GraphConnectionError`, `GraphTimeoutError`, `GraphValidationError`). Les blocs `except` dans les services doivent désormais intercepter ces exceptions plutôt que les erreurs SDK propriétaires.
- **Découplage de simulation_runner** :
  `simulation_runner.py` ne doit plus porter de référence directe aux spécificités de Zep. Les délais d'attente d'ingestion sont des paramètres d'orchestration temporelle neutres.

## Revue

*(Section réservée à la revue de code contradictoire post-implémentation)*

## Notes de complétion

*(Section complétée à l'issue de l'implémentation et de la revue contradictoire)*
