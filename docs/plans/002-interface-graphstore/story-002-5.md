---
id: "002-5"
epic: "002"
titre: "Refactoring de la lecture (zep_entity_reader, oasis_profile_generator, zep_tools, api/graph)"
statut: in-progress
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

- [ ] `backend/app/services/zep_entity_reader.py` n'importe plus `zep_cloud.NotFoundError`, `utils.zep_paging` ni `utils.zep` ; la lecture et le voisinage de nœuds passent intégralement par `GraphStore`
- [ ] `backend/app/services/oasis_profile_generator.py` n'importe plus `utils.zep` (`call_zep_read_with_retry`, `get_zep_client`, `normalize_zep_search_query`, `is_retryable_zep_error`) ; la recherche enrichie d'entité délègue à `store.search()`
- [ ] `backend/app/services/zep_tools.py` n'importe plus `zep_cloud.NotFoundError`, `utils.zep_paging` ni `utils.zep` ; toutes les requêtes d'outils du ReportAgent passent par `GraphStore`
- [ ] `backend/app/api/graph.py` n'importe plus `from zep_cloud import NotFoundError` ; la capture d'erreur utilise la hiérarchie neutre `GraphNotFoundError`
- [ ] Les classes `ZepEntityReader`, `OasisProfileGenerator` et `ZepTools` acceptent une instance optionnelle `store: Optional[GraphStore] = None` dans leur constructeur avec repli par défaut sur `get_graph_store()`
- [ ] Préservation rétrocompatible des propriétés d'accès (`client`, `zep_client`) via import différé (lazy-import) ou encapsulation pour éviter de briser les mocks de tests unitaires historiques
- [ ] 0 régression sur les contrats de données retournés aux personas OASIS, au ReportAgent et aux routes de visualisation du graphe
- [ ] Une suite de tests hermétiques dédiée (`backend/tests/test_graph_reader_refactor.py`) valide l'absence d'import propriétaire et le bon comportement avec un mock/fake store
- [ ] 100 % des tests du projet (≥ 452 tests) passent avec succès (`cd backend && uv run pytest tests/ -q`)
- [ ] `cd backend && uv run ruff check .` et `cd backend && uv run python scripts/validate_plans.py` passent sans avertissement

## Tâches

- [ ] Refactorer `backend/app/services/zep_entity_reader.py` :
  - [ ] Supprimer les imports directs de `zep_cloud.NotFoundError`, `..utils.zep_paging` (`fetch_all_nodes`, `fetch_all_edges`) et `..utils.zep` (`call_zep_read_with_retry`, `get_zep_client`)
  - [ ] Injecter `self.store: GraphStore = store or get_graph_store(api_key=self.api_key)` dans `__init__`
  - [ ] Fournir une property `client` avec setter à import différé (lazy-import) pour préserver la rétrocompatibilité des tests existants
  - [ ] Réécrire `get_all_nodes(graph_id)` pour déléguer à `self.store.get_all_nodes(graph_id)` et convertir les `GraphNode` en dicts attendus
  - [ ] Réécrire `get_all_edges(graph_id)` pour déléguer à `self.store.get_all_edges(graph_id)` et convertir les `GraphEdge` en dicts attendus
  - [ ] Réécrire `get_node_edges(node_uuid, graph_id=...)` pour déléguer à `self.store.get_node_edges(graph_id, node_uuid)`
  - [ ] Réécrire `get_entity_with_context(graph_id, entity_uuid)` pour interroger `self.store.get_node(graph_id, entity_uuid)` et intercepter `GraphNotFoundError`
- [ ] Refactorer `backend/app/services/oasis_profile_generator.py` :
  - [ ] Supprimer les imports de `..utils.zep` (`call_zep_read_with_retry`, `get_zep_client`, `is_retryable_zep_error`, `normalize_zep_search_query`)
  - [ ] Injecter `store: Optional[GraphStore] = None` dans `OasisProfileGenerator.__init__` (ou setter/getter) avec fallback sur `get_graph_store(api_key=self.zep_api_key)` si configuré
  - [ ] Maintenir une property `zep_client` rétrocompatible si nécessaire
  - [ ] Refactorer `_search_zep_for_entity()` pour exécuter `self.store.search(graph_id=self.graph_id, query=comprehensive_query, limit=30, scope="hybrid")` (ou "edges" + "nodes")
  - [ ] Traiter les exceptions de recherche via `GraphStoreError`
- [ ] Refactorer `backend/app/services/zep_tools.py` :
  - [ ] Supprimer les imports de `zep_cloud.NotFoundError`, `..utils.zep_paging` (`fetch_all_nodes`, `fetch_all_edges`) et `..utils.zep`
  - [ ] Injecter `self.store: GraphStore = store or get_graph_store(api_key=self.api_key)` dans `ZepTools.__init__`
  - [ ] Maintenir la property `client` avec setter/getter lazy-import pour les tests
  - [ ] Refactorer `search()`, `get_all_nodes()`, `get_all_edges()`, `get_node_detail()`, `get_node_edges()` pour déléguer à `self.store`
  - [ ] Remplacer les captures de `NotFoundError` par `GraphNotFoundError`
  - [ ] Maintenir intacts les types de données de retour (`SearchResult`, `NodeInfo`, `EdgeInfo`) attendus par les agents de rapport
- [ ] Refactorer `backend/app/api/graph.py` :
  - [ ] Supprimer l'import `from zep_cloud import NotFoundError`
  - [ ] Importer `GraphNotFoundError` depuis `..utils.graph_store`
  - [ ] Mettre à jour `_delete_cloud_graph_if_present()` pour intercepter `GraphNotFoundError` au lieu de `NotFoundError`
- [ ] Adapter et enrichir les tests unitaires :
  - [ ] Adapter les tests existants (`tests/test_zep_entity_reader.py`, `tests/test_oasis_profile_generator.py`, etc.) pour supporter l'architecture refactorée
  - [ ] Créer une suite de tests dédiée `tests/test_graph_reader_refactor.py` couvrant l'injection de mock store, la tolérance d'arité, les cas d'entité introuvable et le découplage strict des imports (analyse AST)
- [ ] Contrôles de validation et de qualité :
  - [ ] Valider la non-régression absolue : 452 tests verts
  - [ ] Vérifier l'absence d'avertissements avec `ruff check .`
  - [ ] Vérifier la cohérence de planification avec `validate_plans.py`

## Notes de développement

- **Inversion de dépendance et Clean Architecture** :
  Tout comme les flux d'ingestion de la story 002-4, les services de lecture (`zep_entity_reader.py`, `oasis_profile_generator.py`, `zep_tools.py`) ne doivent plus importer aucun symbole de `zep_cloud` ni appeler directement `utils.zep`. Ils dépendent uniquement de l'interface `GraphStore` et de ses modèles neutres.
- **Préservation des structures de présentation métier** :
  `zep_entity_reader.py` définit `EntityNode` et `FilteredEntities`, tandis que `zep_tools.py` définit `SearchResult`, `NodeInfo`, `EdgeInfo`. Ces classes de présentation sont conservées sans altération de leur API publique pour éviter toute rupture transitive dans le moteur de persona et le `ReportAgent`. Les modèles retournés par `GraphStore` (`GraphNode`, `GraphEdge`, `GraphSearchResult`) sont convertis au niveau de la frontière du service.
- **Gestion des exceptions** :
  `GraphNotFoundError` (dérivé de `GraphStoreError`) remplace `zep_cloud.NotFoundError`. Si une entité n'existe pas dans le graphe, `get_entity_with_context` et `get_node_detail` retournent `None` proprement sans fuite de types propriétaires.
- **Recherche unifiée** :
  La méthode `GraphStore.search()` encapsule déjà le reranking et le scope ("edges", "nodes", "hybrid"). Les recherches parallèles ad-hoc de `oasis_profile_generator` et `zep_tools` peuvent exploiter directement `scope="hybrid"` ou combiner les résultats neutres retournés par le store.
- **Rétrocompatibilité des tests existants** :
  Certaines suites de tests existantes assignent directement un mock à `reader.client` ou `tools.client`. L'utilisation d'une property `client` avec setter instanciant un `ZepGraphStore(client=value)` en lazy-import garantit la non-régression des tests existants sans polluer les imports statiques du module.

## Revue

Revue contradictoire menée selon le processus standard (4 couches indépendantes : Blind Hunter, Edge Case Hunter, Verification Gap, Acceptance Auditor).
En attente de réalisation après implémentation.

## Notes de complétion

En cours de développement. Les notes détaillées seront rédigées à l'issue de l'implémentation et de la revue contradictoire.
