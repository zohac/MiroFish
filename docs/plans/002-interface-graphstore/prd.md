# Epic 002 — Interface GraphStore

- **Statut** : `in-progress` · **Dépend de** : 001 · **Bloque** : 003, 004
- **Suivi** : [`sprint-status.yaml`](../../sprint-status.yaml)

> L'épreuve Graphiti local (Epic 001) a prouvé avec succès (Verdict GO, 96.7 % d'extraction sans cloud à 0 € marginal)
> que notre LLM gratuit et son embedder local extraient des entités et relations exploitables.
> Cet Epic 002 pose l'interface d'abstraction `GraphStore` qui rend le remplacement de Zep par Graphiti modulaire,
> réversible et sans régression sur le comportement applicatif existant.

---

## 1. Le problème

Actuellement, l'accès au graphe de connaissances est directement couplé au SDK propriétaire
Zep Cloud (`zep-cloud==3.25.0`) à travers **10 fichiers** du backend MiroFish (identifiés dans
AGENTS.md §5 et `docs/LOCAL-FIRST.md` §5) :

1. [`backend/app/services/graph_builder.py`](../../backend/app/services/graph_builder.py) : création,
   suppression, ajout par lots (`add_batch`), attente d'ingestion (`get_batch_summary`),
   ontologie (`set_ontology`), extraction globale de données de visualisation (`get_graph_data`).
2. [`backend/app/services/zep_entity_reader.py`](../../backend/app/services/zep_entity_reader.py) : lecture
   paginée des nœuds (`get_all_nodes`), des arêtes (`get_all_edges`), extraction du voisinage d'un nœud
   (`get_node_edges`), filtrage des entités par ontologie et enrichissement de contexte.
3. [`backend/app/services/zep_graph_memory_updater.py`](../../backend/app/services/zep_graph_memory_updater.py) :
   ingestion continue des actions de simulation par épisodes textuels (`add`), suivi d'état des épisodes (`episode.get`).
4. [`backend/app/services/oasis_profile_generator.py`](../../backend/app/services/oasis_profile_generator.py) :
   recherche sémantique (`search`), enrichissement des profils d'agents avec des faits et résumés de nœuds.
5. [`backend/app/services/zep_tools.py`](../../backend/app/services/zep_tools.py) : outils d'interrogation
   pour le `ReportAgent` (`search`, `get_all_nodes`, `get_all_edges`, `get_node_detail`, `get_node_edges`, statistiques).
6. [`backend/app/api/graph.py`](../../backend/app/api/graph.py) : routes HTTP de lecture (`get_graph_data`),
   de suppression (`delete_graph`) et capture directe de `zep_cloud.NotFoundError`.
7. [`backend/app/services/simulation_runner.py`](../../backend/app/services/simulation_runner.py) :
   timeouts d'ingestion Zep et coordination du cycle de vie de la mémoire de simulation.
8. [`backend/app/utils/zep.py`](../../backend/app/utils/zep.py) : client Zep Cloud partagé, politique
   de retries (`call_zep_read_with_retry`) et normalisation des requêtes.
9. [`backend/app/utils/zep_paging.py`](../../backend/app/utils/zep_paging.py) : pagination par curseur opaque
   (`fetch_all_nodes`, `fetch_all_edges`).
10. [`backend/scripts/validate_zep_cloud_integration.py`](../../backend/scripts/validate_zep_cloud_integration.py) :
    banc de validation autonome contre l'API Zep Cloud.

Brancher Graphiti directement dans les services métiers introduirait des bifurcations conditionnelles
(`if zep else graphiti`) disséminées dans tout le code, ce qui constitue une violation grave des
principes de Clean Architecture et de conception logicielle (AGENTS.md §2.1 : *« Un `if zep else graphiti`
dans un service est un bug de conception »*).

Pour préserver la stabilité du produit, permettre une réversibilité immédiate et préparer l'implémentation
de `GraphitiGraphStore` (Epic 003), nous devons découpler le domaine applicatif du fournisseur de graphe.

## 2. L'objectif

Concevoir et implémenter une couche d'abstraction unifiée pour les magasins de graphe de connaissances temporels :
1. Définir une interface abstraite formelle `GraphStore` et des modèles de données neutres (`GraphNode`,
   `GraphEdge`, `GraphSearchResult`, `EpisodeRecord`, `BatchSubmissionRecord`).
2. Définir une hiérarchie d'exceptions agnostiques (`GraphStoreError`, `GraphNotFoundError`, `GraphConnectionError`).
3. Encapsuler l'intégralité du comportement Zep Cloud existant dans une classe `ZepGraphStore` conforme
   à l'interface, logée dans `backend/app/utils/graph_store/`.
4. Poser une factory `get_graph_store()` sélectionnant l'implémentation via la variable `ZEP_BACKEND`
   (`cloud` par défaut, `graphiti` réservé pour l'Epic 003).
5. Migrer l'ensemble des consommateurs métier du backend pour qu'ils n'interagissent qu'avec `GraphStore`.
6. Valider la non-régression absolue sur la suite de tests existante (333 tests verts), complétée par les
   tests d'isolation et de contrat du nouveau composant.

## 3. Ce que cet epic n'est pas

| Hors périmètre | Pourquoi |
|---|---|
| L'implémentation concrète de `GraphitiGraphStore` | Fait l'objet exclusif de l'Epic 003 (écriture et chemin de lecture) |
| L'exécution sans clé Zep configurée | Fait l'objet de l'Epic 004 (exige `GraphitiGraphStore` opérationnel de bout en bout) |
| L'environnement Docker unifié | Fait l'objet de l'Epic 005 |
| La migration des données Zep historiques | Fait l'objet de l'Epic 006 |
| L'ontologie dynamique custom en v1 | Reportée en v2 par l'ADR 0003 |

## 4. Critères de sortie — chiffrés

| # | Critère | Seuil | Sinon |
|---|---|---|---|
| **C1** | Définition formelle de l'interface `GraphStore` | 1 classe abstraite / `Protocol` couvrant 100 % des opérations réelles du moteur (cycle de vie, batch, ontologie, lecture, recherche, temporalité) | Échec de cadrage |
| **C2** | Implémentation complète de `ZepGraphStore` | 1 classe concrète encapsulant le SDK Zep, sa pagination et ses retries sans fuite de types propriétaires | Rejet de l'abstraction |
| **C3** | Factory `get_graph_store()` pilotée par `ZEP_BACKEND` | 1 fonction factory opérationnelle, défaut strict à `'cloud'`, rejet explicite des backends non supportés, support d'override pour tests | Régression de configuration |
| **C4** | Élimination des imports directs du SDK Zep dans les services | **0** occurrence de `from zep_cloud` et de `from ..utils.zep import get_zep_client` dans `services/` et `api/` | Fuite d'abstraction |
| **C5** | Absence de branchements conditionnels sur le backend | **0** bifurcation `if zep else graphiti` dans le code métier ou les routes API | Bug de conception (AGENTS.md §2.1) |
| **C6** | Non-régression sur le filet de tests existant | **100 % des 333 tests** restent verts, augmentés des tests d'interface et d'isolation | Régression bloquante |

## 5. Recensement des opérations du graphe

L'analyse minutieuse du code source existant identifie l'ensemble exact des capacités requises par MiroFish :

1. **Cycle de vie du graphe** :
   - `create_graph(name: str, graph_id: str | None = None) -> str`
   - `delete_graph(graph_id: str) -> None`
   - `get_graph_data(graph_id: str) -> Dict[str, Any]` (nœuds, arêtes, métadonnées, statistiques pour l'API et le frontend)
   - `get_graph_info(graph_id: str) -> GraphInfo` (nombre de nœuds, d'arêtes, types d'entités)

2. **Ontologie** :
   - `set_ontology(graph_id: str, ontology: Dict[str, Any]) -> None` (nécessaire à `graph_builder.py` et testé par `test_ontology_attributes.py`)

3. **Ingestion et épisodes** :
   - `add_episode(graph_id: str, text: str, source_description: str = "", metadata: dict | None = None, created_at: str | None = None) -> EpisodeRecord`
   - `add_text_batch(graph_id: str, chunks: List[str], batch_size: int = 350, progress_callback: Callable | None = None) -> BatchSubmissionRecord` (ingestion par lots pour documents longs)
   - `wait_for_batch(batch: BatchSubmissionRecord, progress_callback: Callable | None = None, timeout: float = 600.0) -> bool` (suivi de traitement par lots)
   - `wait_for_episodes(graph_id: str, episode_uuids: List[str], timeout: float = 600.0) -> bool` (suivi de traitement d'épisodes unitaires)

4. **Interrogation et recherche** :
   - `get_all_nodes(graph_id: str) -> List[GraphNode]`
   - `get_all_edges(graph_id: str, include_temporal: bool = True) -> List[GraphEdge]`
   - `get_node(graph_id: str, node_uuid: str) -> GraphNode | None`
   - `get_node_edges(graph_id: str, node_uuid: str) -> List[GraphEdge]`
   - `search(graph_id: str, query: str, limit: int = 10, scope: str = "edges") -> GraphSearchResult`

5. **Temporalité et métadonnées** :
   - Préservation systématique des champs temporels sur les nœuds et arêtes (`created_at`, `valid_at`, `invalid_at`, `expired_at`).

## 6. Risques et parades

| Risque | Signal | Parade |
|---|---|---|
| Fuite de types Zep (`EntityNode`, `ZepEdge`, `ApiError`, `NotFoundError`) dans les appelants | `import zep_cloud` persistant dans `services/` | Définir des dataclasses neutres et une hiérarchie d'exceptions agnostique (`GraphStoreError`, etc.) dans `app/utils/graph_store/` |
| Rupture des comportements asynchrones ou de polling de Zep Cloud | Échec des tests de `GraphBuilderService` ou `ZepGraphMemoryUpdater` | `ZepGraphStore` intègre la gestion des batchs, la pagination par curseurs et les retries de façon totalement transparente |
| Régression des tests existants utilisant des mocks Zep spécifiques (`test_zep_*.py`) | Tests pytest existants échouant | Conserver `utils/zep.py` et `utils/zep_paging.py` comme briques internes consommées par `ZepGraphStore`, ou adapter les fixtures sans altérer les assertions de contrat |
| Régression silencieuse par couplage résiduel dans un script ou service | Import direct non détecté en CI | Ajouter un test statique d'isolation d'imports (`test_graph_store_isolation.py`) contrôlant l'absence de `zep_cloud` dans `app/services/` et `app/api/` |

