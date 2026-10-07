---
id: "002-5"
epic: "002"
titre: "Refactoring de la lecture (zep_entity_reader, oasis_profile_generator, zep_tools, api/graph)"
statut: done
auteur: agent
format: "2"
---

# Story 002-5 — Refactoring de la lecture (zep_entity_reader, oasis_profile_generator, zep_tools, api/graph)

## Pourquoi cette story

L'Epic 002 a pour objectif de découpler complètement MiroFish du fournisseur de graphe Zep Cloud en introduisant la couche d'abstraction `GraphStore` (ADR 0001, AGENTS.md §2.1).
Les fondations et les flux d'écriture sont désormais posés et validés :
- La story 002-1 a posé l'interface formelle `GraphStore`, ses modèles neutres immutables (`GraphNode`, `GraphEdge`, `GraphSearchResult`, etc.) et ses exceptions agnostiques (`GraphStoreError`).
- La story 002-2 a développé l'implémentation complète `ZepGraphStore` encapsulant le SDK Zep Cloud, ses curseurs de pagination et ses retries.
- La story 002-3 a mis en place la factory `get_graph_store()`, la variable `ZEP_BACKEND` (défaut `'cloud'`) et le mécanisme d'override pour les tests.
- La story 002-4 a refactoré les flux d'ingestion et d'écriture (`graph_builder.py`, `zep_graph_memory_updater.py`, `simulation_runner.py`), validés par 452 tests verts.

À présent, les **flux de lecture, de recherche et d'interrogation du graphe** reposent encore sur des appels directs au SDK propriétaire `zep-cloud` et sur des utilitaires couplés :
1. `backend/app/services/zep_entity_reader.py` : lit les nœuds et arêtes avec pagination (`zep_paging`), filtre les types d'entités, interroge le voisinage d'un nœud (`client.graph.node.get`, `get_edges`), et intercepte `zep_cloud.NotFoundError`.
2. `backend/app/services/oasis_profile_generator.py` : réalise des recherches sémantiques et mixtes parallèles (`client.graph.search`, `scope="edges"`, `scope="nodes"`), importe `call_zep_read_with_retry`, `get_zep_client` et `normalize_zep_search_query`.
3. `backend/app/services/zep_tools.py` : outille le `ReportAgent` (`InsightForge`, `PanoramaSearch`, `QuickSearch`, `get_all_nodes`, `get_all_edges`, `get_node_detail`, `get_node_edges`), importe `NotFoundError`, `fetch_all_nodes`, `fetch_all_edges`, `get_zep_client` et `call_zep_read_with_retry`.
4. `backend/app/api/graph.py` : routes HTTP `/api/graph/*`, capture directe de `from zep_cloud import NotFoundError`.

Ce couplage résiduel empêche la substitution du backend de lecture par Graphiti (Epic 003) et constitue une fuite d'abstraction violant la Clean Architecture (AGENTS.md §2.1).

Cette story refactore l'ensemble de ces quatre modules pour qu'ils consomment exclusivement l'interface neutre `GraphStore` via `get_graph_store()`, élimine tous les imports directs de `zep_cloud` et `utils.zep`, tout en garantissant une stricte conformité des formats de sortie pour les personas, le moteur de simulation, le générateur de rapport et le frontend.

## Définition de prêt

- [x] Interface formelle `GraphStore` disponible et validée (`base.py`, Story 002-1)
- [x] Méthodes de lecture `get_all_nodes()`, `get_all_edges()`, `get_node()`, `get_node_edges()` et `search()` implémentées et testées dans `ZepGraphStore` (Story 002-2)
- [x] Factory `get_graph_store()` opérationnelle avec support d'injection pour les tests (Story 002-3)
- [x] Refactoring d'ingestion achevé et étanchéité validée par 452 tests verts (Story 002-4)
- [x] Inventaire exhaustif des points de couplage dans `zep_entity_reader.py`, `oasis_profile_generator.py`, `zep_tools.py` et `api/graph.py`
- [x] Stratégie de non-régression établie sur les suites de tests existantes (`test_zep_entity_reader.py`, `test_zep_paging.py`, etc.)
- [x] Documents de référence consultés — [`epic-002.md`](epic-002.md), [`architecture.md`](architecture.md), [`prd.md`](prd.md), [ADR 0001](../../decisions/0001-remplacement-de-zep-par-graphiti.md), [`docs/LOCAL-FIRST.md`](../../LOCAL-FIRST.md) §5

## Définition de fini

- [x] `backend/app/services/zep_entity_reader.py` n'importe plus `zep_cloud.NotFoundError`, `utils.zep_paging` ni `utils.zep` ; la lecture et le voisinage de nœuds passent intégralement par `GraphStore`
- [x] `backend/app/services/oasis_profile_generator.py` n'importe plus `utils.zep` (`call_zep_read_with_retry`, `get_zep_client`, `normalize_zep_search_query`, `is_retryable_zep_error`) ; la recherche enrichie d'entité délègue à `store.search()`
- [x] `backend/app/services/zep_tools.py` n'importe plus `zep_cloud.NotFoundError`, `utils.zep_paging` ni `utils.zep` ; toutes les requêtes d'outils du ReportAgent passent par `GraphStore`
- [x] `backend/app/api/graph.py` n'importe plus `from zep_cloud import NotFoundError` ; la capture d'erreur utilise la hiérarchie neutre `GraphNotFoundError`
- [x] Les classes `ZepEntityReader`, `OasisProfileGenerator` et `ZepTools` acceptent une instance optionnelle `store: Optional[GraphStore] = None` dans leur constructeur avec repli par défaut sur `get_graph_store()`
- [x] Préservation rétrocompatible des propriétés d'accès (`client`, `zep_client`) via import différé (lazy-import) ou encapsulation pour éviter de briser les mocks de tests unitaires historiques
- [x] 0 régression sur les contrats de données retournés aux personas OASIS, au ReportAgent et aux routes de visualisation du graphe
- [x] Une suite de tests hermétiques dédiée (`backend/tests/test_graph_reader_refactor.py`) valide l'absence d'import propriétaire et le bon comportement avec un mock/fake store
- [x] 100 % des tests du projet (≥ 452 tests -> 464 tests) passent avec succès (`cd backend && uv run pytest tests/ -q`)
- [x] `cd backend && uv run ruff check .` et `cd backend && uv run python scripts/validate_plans.py` passent sans avertissement

## Tâches

- [x] Refactorer `backend/app/services/zep_entity_reader.py` :
  - [x] Supprimer les imports directs de `zep_cloud.NotFoundError`, `..utils.zep_paging` (`fetch_all_nodes`, `fetch_all_edges`) et `..utils.zep` (`call_zep_read_with_retry`, `get_zep_client`)
  - [x] Injecter `self.store: GraphStore = store or get_graph_store(api_key=self.api_key)` dans `__init__`
  - [x] Fournir une property `client` avec setter à import différé (lazy-import) pour préserver la rétrocompatibilité des tests existants
  - [x] Réécrire `get_all_nodes(graph_id)` pour déléguer à `self.store.get_all_nodes(graph_id)` et convertir les `GraphNode` en dicts attendus
  - [x] Réécrire `get_all_edges(graph_id)` pour déléguer à `self.store.get_all_edges(graph_id)` et convertir les `GraphEdge` en dicts attendus
  - [x] Réécrire `get_node_edges(node_uuid, graph_id=...)` pour déléguer à `self.store.get_node_edges(graph_id, node_uuid)`
  - [x] Réécrire `get_entity_with_context(graph_id, entity_uuid)` pour interroger `self.store.get_node(graph_id, entity_uuid)` et intercepter `GraphNotFoundError`
- [x] Refactorer `backend/app/services/oasis_profile_generator.py` :
  - [x] Supprimer les imports de `..utils.zep` (`call_zep_read_with_retry`, `get_zep_client`, `is_retryable_zep_error`, `normalize_zep_search_query`)
  - [x] Injecter `store: Optional[GraphStore] = None` dans `OasisProfileGenerator.__init__` (ou setter/getter) avec fallback sur `get_graph_store(api_key=self.zep_api_key)` si configuré
  - [x] Maintenir une property `zep_client` rétrocompatible si nécessaire
  - [x] Refactorer `_search_zep_for_entity()` pour exécuter `self.store.search(graph_id=self.graph_id, query=comprehensive_query, limit=30, scope="hybrid")` (ou "edges" + "nodes")
  - [x] Traiter les exceptions de recherche via `GraphStoreError`
- [x] Refactorer `backend/app/services/zep_tools.py` :
  - [x] Supprimer les imports de `zep_cloud.NotFoundError`, `..utils.zep_paging` (`fetch_all_nodes`, `fetch_all_edges`) et `..utils.zep`
  - [x] Injecter `self.store: GraphStore = store or get_graph_store(api_key=self.api_key)` dans `ZepTools.__init__`
  - [x] Maintenir la property `client` avec setter/getter lazy-import pour les tests
  - [x] Refactorer `search()`, `get_all_nodes()`, `get_all_edges()`, `get_node_detail()`, `get_node_edges()` pour déléguer à `self.store`
  - [x] Remplacer les captures de `NotFoundError` par `GraphNotFoundError`
  - [x] Maintenir intacts les types de données de retour (`SearchResult`, `NodeInfo`, `EdgeInfo`) attendus par les agents de rapport
- [x] Refactorer `backend/app/api/graph.py` :
  - [x] Supprimer l'import `from zep_cloud import NotFoundError`
  - [x] Importer `GraphNotFoundError` depuis `..utils.graph_store`
  - [x] Mettre à jour `_delete_cloud_graph_if_present()` pour intercepter `GraphNotFoundError` au lieu de `NotFoundError`
- [x] Adapter et enrichir les tests unitaires :
  - [x] Adapter les tests existants (`tests/test_zep_entity_reader.py`, `tests/test_oasis_profile_generator.py`, etc.) pour supporter l'architecture refactorée
  - [x] Créer une suite de tests dédiée `tests/test_graph_reader_refactor.py` couvrant l'injection de mock store, la tolérance d'arité, les cas d'entité introuvable et le découplage strict des imports (analyse AST)
- [x] Contrôles de validation et de qualité :
  - [x] Valider la non-régression absolue : 462 tests verts
  - [x] Vérifier l'absence d'avertissements avec `ruff check .`
  - [x] Vérifier la cohérence de planification avec `validate_plans.py`

### Review Findings

- [x] [Review][Patch] Déléguer get_node_edges à self.store.get_node_edges au lieu de get_all_edges quand graph_id est fourni [backend/app/services/zep_entity_reader.py:183-205]
- [x] [Review][Patch] Résoudre get_graph_store dans OasisProfileGenerator.store sans exiger self.zep_api_key [backend/app/services/oasis_profile_generator.py:273-281]
- [x] [Review][Patch] Normaliser scope="both" en "hybrid" dans ZepToolsService.search_graph [backend/app/services/zep_tools.py:498]
- [x] [Review][Patch] Renforcer test_graph_reader_refactor.py avec validation AST réelle et assertion sur store.calls [backend/tests/test_graph_reader_refactor.py:164-235]
- [x] [Review][Defer] Repli sur target_graph_id = "default" quand graph_id est omis [backend/app/services/zep_entity_reader.py:203, backend/app/services/zep_tools.py:716] — deferred: signatures historiques sans graph_id préservées pour compatibilité, refonte globale prévue en Epic 003
- [x] [Review][Defer] Requêtage N+1 séquentiel get_node dans get_entity_with_context [backend/app/services/zep_entity_reader.py:388-398] — deferred: comportement hérité amont, optimisation par batch différée à l'Epic 003

#### Rejected

- [EdgeInfo missing attributes]: rejeté (`false`) — `EdgeInfo` n'a historiquement jamais eu de champ `attributes` dans son dataclass ; le contrat DTO est respecté.
- [reader.client duck-typing]: rejeté (`false`) — principe standard de mock unitaire en duck-typing ; les 462 tests existants passent sans défaut d'interface.

## Notes de développement

- **Inversion de dépendance et Clean Architecture** :
  Tout comme les flux d'ingestion de la story 002-4, les services de lecture (`zep_entity_reader.py`, `oasis_profile_generator.py`, `zep_tools.py`) et l'API (`api/graph.py`) ne dépendent plus d'aucun symbole propriétaire de `zep_cloud` ni d'appels directs à `utils.zep`. Ils dépendent uniquement de l'interface `GraphStore`, de ses modèles neutres et de `get_graph_store()`.
- **Préservation des structures de présentation métier** :
  `zep_entity_reader.py` définit `EntityNode` et `FilteredEntities`, tandis que `zep_tools.py` définit `SearchResult`, `NodeInfo`, `EdgeInfo`. Ces classes de présentation sont conservées sans altération de leur API publique pour éviter toute rupture transitive dans le moteur de persona et le `ReportAgent`. Les modèles retournés par `GraphStore` (`GraphNode`, `GraphEdge`, `GraphSearchResult`) sont convertis au niveau de la frontière du service.
- **Gestion des exceptions** :
  `GraphNotFoundError` (dérivé de `GraphStoreError`) remplace `zep_cloud.NotFoundError`. Si une entité n'existe pas dans le graphe, `get_entity_with_context` et `get_node_detail` retournent `None` proprement sans fuite de types propriétaires.
- **Recherche unifiée** :
  La méthode `GraphStore.search()` encapsule déjà le reranking et le scope ("edges", "nodes", "hybrid"). Les recherches de `oasis_profile_generator` et `zep_tools` exploitent directement l'interface neutre avec gestion robuste des erreurs via `GraphStoreError`.
- **Rétrocompatibilité des tests existants** :
  Les tests unitaires historiques qui assignent un mock à `reader.client` ou `tools.client` (ex: `object.__new__(ZepEntityReader)` puis `reader.client = mock`) sont pleinement supportés via des properties avec setter instanciant `ZepGraphStore(client=value)` en import différé.

## Revue

Revue contradictoire menée selon le processus standard (4 couches indépendantes) :

1. **Blind Hunter (Isolation & Imports AST)** :
   - Audit des fichiers source (`zep_entity_reader.py`, `oasis_profile_generator.py`, `zep_tools.py`, `api/graph.py`).
   - Analyse AST stricte `ast.parse` ajoutée dans `test_graph_reader_refactor.py::test_ast_decoupling_in_reader_and_tools` : 0 import statique de `zep_cloud` ou `utils.zep` dans ces 4 modules.
   - Tous les flux de lecture passent par `self.store` (interface `GraphStore`).

2. **Edge Case Hunter (Robustesse & Erreurs)** :
   - Cas 404 / entité inexistante : `GraphNotFoundError` est intercepté dans `get_entity_with_context`, `get_node_detail` et `_delete_cloud_graph_if_present` pour retourner `None` ou un statut silencieux sans crash.
   - `ZepToolsService.search_graph` : normalisation robuste de `scope="both"` vers `"hybrid"` pour respecter le contrat `GraphStore`.
   - `OasisProfileGenerator.store` : assouplissement de la résolution du store pour honorer `override_graph_store` et les modes sans clé Zep.
   - Injection de mock direct : les setters `reader.client = mock` et `tools.client = mock` créent dynamiquement un adaptateur `ZepGraphStore(client=mock)` sans régression.

3. **Verification Gap (Couverture des tests)** :
   - 12 tests unitaires dédiés dans `backend/tests/test_graph_reader_refactor.py`.
   - Couverture complète : instanciation avec `MockReaderStore`, délégation vérifiée dans `store.calls` (`get_all_nodes`, `get_all_edges`, `get_node_edges`, `search`, etc.), `get_entity_with_context`, `_search_zep_for_entity`, `ZepTools.search/get_all_nodes/get_node_detail`, validation AST stricte d'absence d'imports.
   - Non-régression prouvée sur l'ensemble de la suite (`test_zep_entity_reader_edges.py`, `test_oasis_profile_generator.py`, `test_zep_cloud_contracts.py`).

4. **Acceptance Auditor (Critères de sortie)** :
   - 100 % des critères de la définition de fini sont satisfaits.
   - 4 patchs issus de la revue contradictoire appliqués immédiatement.
   - 464 tests verts en local (en progression de +12 tests par rapport à la story 002-4).
   - `ruff check .` passe sans erreur.
   - `validate_plans.py` valide la structure du projet.

## Notes de complétion

- **Refactoring achevé avec succès** :
  - `backend/app/services/zep_entity_reader.py` : découplé à 100 %, délégation à `GraphStore`, capture de `GraphNotFoundError`. Préservation fine du comportement bidirectionnel sous Zep Cloud 3.25.
  - `backend/app/services/oasis_profile_generator.py` : découplé à 100 %, délégation de `_search_zep_for_entity` à `store.search(scope="hybrid")`. Résolution du store étanche pour les tests et le mode local.
  - `backend/app/services/zep_tools.py` : découplé à 100 %, conversion des modèles neutres (`GraphNode`, `GraphEdge`, `GraphSearchResult`) vers les DTOs `SearchResult`, `NodeInfo`, `EdgeInfo`. Normalisation de scope validée.
  - `backend/app/api/graph.py` : suppression de `zep_cloud.NotFoundError` au profit de `GraphNotFoundError`.
- **Validation** :
  - 464 tests unitaires et d'intégration réussis en 20s (`pytest tests/ -q`).
  - Aucun avertissement lint (`ruff check .`).
  - Validation de plan conforme (`validate_plans.py`).
- **Prêt pour la story 002-6** : L'ensemble des flux d'ingestion (002-4) et de lecture (002-5) étant découplé et audité contradictoirement, la story finale 002-6 peut acter la clôture de l'Epic 002.
