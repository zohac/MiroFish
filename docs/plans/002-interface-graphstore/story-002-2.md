---
id: "002-2"
epic: "002"
titre: "Implémentation de ZepGraphStore et encapsulation du SDK Zep"
statut: in-progress
auteur: agent
format: "2"
---

# Story 002-2 — Implémentation de ZepGraphStore et encapsulation du SDK Zep

## Pourquoi cette story

L'Epic 002 a pour mission d'abstraire l'accès au graphe de connaissances (ADR 0001, AGENTS.md §2.1).
La story 002-1 a posé les fondations : l'interface abstraite `GraphStore`, les modèles de données neutres
et la hiérarchie d'exceptions agnostiques dans `backend/app/utils/graph_store/`.

La deuxième étape indispensable est de concrétiser la première implémentation de cette interface : `ZepGraphStore`.
Aujourd'hui, 10 composants métier de MiroFish appellent directement le SDK `zep-cloud==3.25.0`
et manipulent des types propriétaires ou des dictionnaires hétérogènes.
Pour permettre le refactoring ultérieur de ces 10 composants (stories 002-4 et 002-5) sans régression :
1. `ZepGraphStore` doit implémenter les 14 méthodes de l'interface `GraphStore` en déléguant au client Zep Cloud.
2. La pagination (`fetch_all_nodes`, `fetch_all_edges` de `zep_paging.py`) et la politique de retries
   (`call_zep_read_with_retry` de `zep.py`) doivent être encapsulées à l'intérieur de `ZepGraphStore`.
3. Les exceptions propriétaires (`zep_cloud.NotFoundError`, `ApiError`, `httpx.TimeoutException`, etc.)
   doivent être systématiquement interceptées et traduites dans la hiérarchie agnostique `GraphStoreError`
   (`GraphNotFoundError`, `GraphConnectionError`, `GraphTimeoutError`, `GraphValidationError`).
4. Les sorties du SDK doivent être rigoureusement converties vers les dataclasses neutres (`GraphNode`,
   `GraphEdge`, `GraphSearchResult`, `EpisodeRecord`, `BatchSubmissionRecord`, `GraphInfo`), sans aucune
   fuite de types `zep_cloud` vers les appelants.
5. Une suite de tests unitaires hermétiques mockant le SDK Zep doit valider la conformité de chaque méthode
   et la bonne traduction des erreurs.

Cette story crée `backend/app/utils/graph_store/zep_store.py` et la suite de tests
`backend/tests/test_zep_graph_store.py`.

## Définition de prêt

- [x] Contrat d'interface `GraphStore` posé et validé par la story 002-1 dans `backend/app/utils/graph_store/base.py`
- [x] Table de correspondance des exceptions documentée dans `architecture.md` §4
- [x] Logique existante de pagination (`zep_paging.py`) et retries (`zep.py`) analysée et opérationnelle
- [x] Signatures des 14 méthodes et modèles neutres conformes aux correctifs de la revue de la story 002-1
- [x] Stratégie de test unitaire hermétique (mocking du SDK `zep-cloud`, zéro appel réseau) définie
- [x] Documents à consulter lus — [`epic-002.md`](epic-002.md), [`architecture.md`](architecture.md), [`prd.md`](prd.md), [ADR 0001](../../decisions/0001-remplacement-de-zep-par-graphiti.md)

## Définition de fini

- [ ] La classe `ZepGraphStore(GraphStore)` est implémentée dans `backend/app/utils/graph_store/zep_store.py`
- [ ] Les 14 méthodes abstraites de `GraphStore` sont implémentées et typées sans fuite de types Zep
- [ ] La pagination par curseurs est intégrée de façon transparente pour `get_all_nodes`, `get_all_edges` et `get_graph_data`
- [ ] La politique de retry et de réconciliation de création est encapsulée dans `create_graph` et les lectures
- [ ] Toutes les erreurs du SDK Zep et de `httpx` sont traduites en exceptions de la hiérarchie `GraphStoreError`
- [ ] `add_text_batch` et `wait_for_batch` gèrent la soumission par lots et le suivi asynchrone
- [ ] `add_episode` et `wait_for_episodes` gèrent l'ingestion unitaire et le polling avec gestion de timeout
- [ ] `search` prend en charge les périmètres (`edges`, `nodes`, `hybrid`) et le paramètre optionnel `reranker`
- [ ] `backend/app/utils/graph_store/__init__.py` exporte `ZepGraphStore`
- [ ] Une suite de tests unitaires complète et hermétique `backend/tests/test_zep_graph_store.py` teste chaque méthode avec mocks SDK
- [ ] 100 % des tests existants (341 tests) restent au vert (`uv run pytest tests/ -q`)
- [ ] `uv run ruff check .` et `uv run python scripts/validate_plans.py` passent sans avertissement

## Tâches

- [ ] Créer `backend/app/utils/graph_store/zep_store.py` avec `ZepGraphStore(GraphStore)`
  - [ ] Gestion du client Zep (`get_zep_client`) et injection de client pour les tests
  - [ ] Helper interne de traduction des exceptions Zep / httpx vers `GraphStoreError`
  - [ ] Implémentation du cycle de vie (`create_graph` avec réconciliation, `delete_graph`, `get_graph_data`, `get_graph_info`)
  - [ ] Implémentation de l'ontologie (`set_ontology`)
  - [ ] Implémentation de l'ingestion par lots (`add_text_batch`, `wait_for_batch`)
  - [ ] Implémentation de l'ingestion unitaire (`add_episode`, `wait_for_episodes`)
  - [ ] Implémentation des lectures paginées et parcours (`get_all_nodes`, `get_all_edges`, `get_node`, `get_node_edges`)
  - [ ] Implémentation de la recherche sémantique (`search` avec support de `reranker` et scopes)
- [ ] Exposer `ZepGraphStore` dans `backend/app/utils/graph_store/__init__.py`
- [ ] Créer la suite de tests `backend/tests/test_zep_graph_store.py`
  - [ ] Test d'initialisation et configuration de clé API
  - [ ] Tests du cycle de vie (`create_graph`, `delete_graph`, `get_graph_data`, `get_graph_info`)
  - [ ] Tests de traduction des exceptions (404 -> `GraphNotFoundError`, 502/503 -> `GraphConnectionError`, timeout -> `GraphTimeoutError`)
  - [ ] Tests d'ingestion par lots (`add_text_batch`, `wait_for_batch`)
  - [ ] Tests d'ingestion d'épisodes (`add_episode`, `wait_for_episodes`)
  - [ ] Tests de lecture (`get_all_nodes`, `get_all_edges`, `get_node`, `get_node_edges`)
  - [ ] Tests de recherche avec conversion en `GraphSearchResult` et gestion du `reranker`
- [ ] Valider la non-régression globale (`uv run pytest tests/ -q`)
- [ ] Contrôler `ruff check .` et `validate_plans.py`

## Notes de développement

- **Réutilisation des composants éprouvés** :
  `ZepGraphStore` s'appuie sur `app.utils.zep` (`get_zep_client`, `call_zep_read_with_retry`, `is_retryable_zep_error`)
  et `app.utils.zep_paging` (`fetch_all_nodes`, `fetch_all_edges`). Cela capitalise sur les 9 suites de tests
  de contrat Zep existantes tout en les encapsulant derrière l'interface unifiée.
- **Isolation des types propriétaires** :
  Aucun type propriétaire (`EntityNode`, `ZepEdge`, `BatchAddItem`, etc.) ne franchit la frontière de `zep_store.py`.
  Toutes les valeurs retournées sont des instances des modèles neutres définis dans `base.py`.
- **Rétrocompatibilité du format de données de l'API** :
  `get_graph_data` garantit la présence de `graph_id`, `node_count`, `edge_count` au premier niveau ainsi que
  `statistics`, répondant aux besoins conjoints de `api/graph.py` et du frontend Vue.

## Revue

Revue contradictoire planifiée sur les 4 couches BMad (*Blind Hunter*, *Edge Case Hunter*, *Verification Gap*, *Acceptance Auditor*) :
1. Couverture exhaustive des 14 méthodes de l'interface `GraphStore` ;
2. Traduction rigoureuse de toutes les erreurs du SDK et de HTTPX vers la hiérarchie `GraphStoreError` ;
3. Absence totale de fuite de types Zep dans les signatures et retours publics ;
4. Herméticité absolue des tests unitaires (aucun appel réseau externe, mocks complets) ;
5. Non-régression totale sur le filet existant (341 tests verts).

## Notes de complétion

Cette section sera complétée à l'issue de l'implémentation et de la revue contradictoire.
