---
id: "002-2"
epic: "002"
titre: "Implémentation de ZepGraphStore et encapsulation du SDK Zep"
statut: done
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

- [x] La classe `ZepGraphStore(GraphStore)` est implémentée dans `backend/app/utils/graph_store/zep_store.py`
- [x] Les 14 méthodes abstraites de `GraphStore` sont implémentées et typées sans fuite de types Zep
- [x] La pagination par curseurs est intégrée de façon transparente pour `get_all_nodes`, `get_all_edges` et `get_graph_data`
- [x] La politique de retry et de réconciliation de création est encapsulée dans `create_graph` et les lectures
- [x] Toutes les erreurs du SDK Zep et de `httpx` sont traduites en exceptions de la hiérarchie `GraphStoreError`
- [x] `add_text_batch` et `wait_for_batch` gèrent la soumission par lots et le suivi asynchrone
- [x] `add_episode` et `wait_for_episodes` gèrent l'ingestion unitaire et le polling avec gestion de timeout
- [x] `search` prend en charge les périmètres (`edges`, `nodes`, `hybrid`) et le paramètre optionnel `reranker`
- [x] `backend/app/utils/graph_store/__init__.py` exporte `ZepGraphStore`
- [x] Une suite de tests unitaires complète et hermétique `backend/tests/test_zep_graph_store.py` teste chaque méthode avec mocks SDK
- [x] 100 % des tests existants (341 tests) restent au vert (`uv run pytest tests/ -q`)
- [x] `uv run ruff check .` et `uv run python scripts/validate_plans.py` passent sans avertissement

## Tâches

- [x] Créer `backend/app/utils/graph_store/zep_store.py` avec `ZepGraphStore(GraphStore)`
  - [x] Gestion du client Zep (`get_zep_client`) et injection de client pour les tests
  - [x] Helper interne de traduction des exceptions Zep / httpx vers `GraphStoreError`
  - [x] Implémentation du cycle de vie (`create_graph` avec réconciliation, `delete_graph`, `get_graph_data`, `get_graph_info`)
  - [x] Implémentation de l'ontologie (`set_ontology`)
  - [x] Implémentation de l'ingestion par lots (`add_text_batch`, `wait_for_batch`)
  - [x] Implémentation de l'ingestion unitaire (`add_episode`, `wait_for_episodes`)
  - [x] Implémentation des lectures paginées et parcours (`get_all_nodes`, `get_all_edges`, `get_node`, `get_node_edges`)
  - [x] Implémentation de la recherche sémantique (`search` avec support de `reranker` et scopes)
- [x] Exposer `ZepGraphStore` dans `backend/app/utils/graph_store/__init__.py`
- [x] Créer la suite de tests `backend/tests/test_zep_graph_store.py`
  - [x] Test d'initialisation et configuration de clé API
  - [x] Tests du cycle de vie (`create_graph`, `delete_graph`, `get_graph_data`, `get_graph_info`)
  - [x] Tests de traduction des exceptions (404 -> `GraphNotFoundError`, 502/503 -> `GraphConnectionError`, timeout -> `GraphTimeoutError`)
  - [x] Tests d'ingestion par lots (`add_text_batch`, `wait_for_batch`)
  - [x] Tests d'ingestion d'épisodes (`add_episode`, `wait_for_episodes`)
  - [x] Tests de lecture (`get_all_nodes`, `get_all_edges`, `get_node`, `get_node_edges`)
  - [x] Tests de recherche avec conversion en `GraphSearchResult` et gestion du `reranker`
- [x] Valider la non-régression globale (`uv run pytest tests/ -q`)
- [x] Contrôler `ruff check .` et `validate_plans.py`

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
- **Gestion des hiérarchies d'exceptions Python** :
  En Python 3, `TimeoutError` hérite de `OSError`. Dans le helper `_translate_error`, la détection de
  `(httpx.TimeoutException, TimeoutError)` doit impérativement précéder celle de `(ConnectError, NetworkError, OSError)`,
  faute de quoi les délais dépassés se traduisaient indûment en `GraphConnectionError`.

## Revue

Revue contradictoire menée par 4 couches indépendantes (*Blind Hunter*, *Edge Case Hunter*, *Verification Gap*, *Acceptance Auditor*).
Bilan du triage : 0 `decision-needed`, 6 `patch`, 0 `defer`, 1 rejeté.

### Constats de revue retenus (Patch)

- [x] [Review][Patch] Préservation des métadonnées temporelles et des épisodes dans `search()` : extraire `valid_at`, `invalid_at`, `expired_at`, `created_at` et `episodes` lors de la construction des `GraphEdge` et `created_at` pour les `GraphNode` [`backend/app/utils/graph_store/zep_store.py:912-940`]
- [x] [Review][Patch] Support des types d'entités sous forme de chaînes et garde contre dictionnaires incomplets dans `set_ontology()` : supporter la syntaxe `{"entity_types": ["Person", "Org"]}` et vérifier la présence de `"name"` [`backend/app/utils/graph_store/zep_store.py:308-335`]
- [x] [Review][Patch] Validation défensive des paramètres dans `wait_for_episodes()` et `wait_for_batch()` : valider `graph_id` non vide dans `wait_for_episodes()`, rejeter les `batch` invalides (`None` ou sans `batch_id`), et exiger un `timeout > 0` [`backend/app/utils/graph_store/zep_store.py:628`, `L670`]
- [x] [Review][Patch] Traduction de `TypeError` en `GraphValidationError` dans `_translate_error()` : capturer `(ValueError, TypeError)` pour éviter qu'un type de paramètre incorrect ne soit qualifié à tort d'"Erreur inattendue" [`backend/app/utils/graph_store/zep_store.py:121`]
- [x] [Review][Patch] Validation stricte des identifiants contre les chaînes constituées uniquement d'espaces : utiliser `if not graph_id or not graph_id.strip():` sur l'ensemble des méthodes publiques de `ZepGraphStore` [`backend/app/utils/graph_store/zep_store.py:180-874`]
- [x] [Review][Patch] Extension des tests unitaires hermétiques pour couvrir les nouveaux cas de garde : ajouter les tests pour la préservation temporelle dans `search()`, l'ontologie compacte, la validation de `wait_for_episodes()` / `wait_for_batch()`, et le chemin nominal de `get_node_edges()` [`backend/tests/test_zep_graph_store.py`]

### Rejets documentés

- `[Review][Reject] get_node initialise related_nodes à []` : Rejeté car conforme au contrat `GraphStore` et nécessaire pour éviter N requêtes HTTP consécutives sur Zep Cloud (délégation volontaire de l'assemblage de voisinage aux appelants comme `zep_entity_reader.py`).

## Notes de complétion

- `ZepGraphStore` est implémenté dans `backend/app/utils/graph_store/zep_store.py` et exporté dans `backend/app/utils/graph_store/__init__.py`.
- Les 14 méthodes du contrat `GraphStore` encapsulent l'intégralité des opérations Zep (création avec réconciliation, suppression, ontologie dynamique Pydantic, ingestion unitaire et par lots, polling asynchrone, parcours paginé par curseurs et recherche sémantique/hybride avec reranker).
- 68 tests unitaires hermétiques mockant le SDK Zep Cloud ont été écrits dans `backend/tests/test_zep_graph_store.py`.
- La revue contradictoire BMad (4 couches) a permis d'identifier et d'appliquer 6 patchs de robustesse (préservation temporelle dans `search`, ontologie compacte avec fallback `source_targets`, validation des identifiants et délais, capture de `TypeError`).
- Le filet de tests global passe de 341 à 409 tests, tous au vert (`uv run pytest tests/ -q`). Aucun avertissement lint (`ruff check`), structure de planification validée par script.
