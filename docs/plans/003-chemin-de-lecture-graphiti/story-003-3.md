---
id: "003-3"
epic: "003"
titre: "Lecture Cypher, parcours de voisinage et recherche hybride temporelle dans GraphitiGraphStore"
statut: done
auteur: agent
format: "2"
---

# Story 003-3 — Lecture Cypher, parcours de voisinage et recherche hybride temporelle dans GraphitiGraphStore

## Pourquoi cette story

Les stories 003-1 et 003-2 ont posé le socle opérationnel et le pipeline d'écriture de `GraphitiGraphStore` : initialisation des dépendances locales, constructeur à injection, gestionnaire asynchrone `_run_async`, cycle de vie (`create_graph`, `delete_graph`, `set_ontology`) et ingestion d'épisodes (`add_episode`, `add_text_batch`, `wait_for_batch`, `wait_for_episodes`) avec partitionnement strict `group_id = graph_id` (521 tests verts).

Cependant, les méthodes de lecture, de parcours et de recherche levaient jusqu'alors une exception `NotImplementedError` :
- `get_all_nodes`
- `get_all_edges`
- `get_node`
- `get_node_edges`
- `get_graph_data`
- `get_graph_info`
- `search`

Pour permettre aux modules en aval de consommer la mémoire de simulation et d'exposer les données :
1. **Extraction ensembliste de nœuds et arêtes** :
   - `get_all_nodes(graph_id)` récupère l'ensemble des entités rattachées au groupe via `MATCH (n:Entity) WHERE n.group_id = $group_id` et les convertit en `GraphNode` agnostiques.
   - `get_all_edges(graph_id, include_temporal=True)` récupère les relations entre entités du groupe via `MATCH (source:Entity)-[r]->(target:Entity) WHERE source.group_id = $group_id AND target.group_id = $group_id` et les convertit en `GraphEdge` neutres en préservant fidèlement les métadonnées temporelles (Critère C3, NFR-4).
2. **Parcours ponctuel et voisinage** :
   - `get_node(graph_id, node_uuid)` extrait un nœud unique vérifiant strictement le `group_id` et enrichit ses arêtes connectées.
   - `get_node_edges(graph_id, node_uuid)` collecte l'ensemble des arêtes incidentes (entrantes et sortantes via `-[r]-`) connectant le nœud à ses voisins du même groupe.
3. **Consolidation pour l'API et l'interface utilisateur** :
   - `get_graph_data(graph_id)` agrège nœuds et arêtes au format attendu par la visualisation du frontend (`/api/graph/*`) avec les propriétés de rétrocompatibilité (`graph_id`, `nodes`, `edges`, `node_count`, `edge_count`, `statistics`).
   - `get_graph_info(graph_id)` retourne un `GraphInfo` synthétique comportant les comptages et la liste des types d'entités présents (hors labels génériques `Entity` et `Node`).
4. **Recherche hybride temporelle** :
   - `search(graph_id, query, limit=10, scope="edges", reranker=None)` exploite les capacités de recherche sémantique/hybride de `graphiti.search` et des requêtes Cypher dédiées filtrées par `group_id`, résout les noms de nœuds connectés, et restitue un `GraphSearchResult` structuré (`facts`, `nodes`, `edges`, `query`, `total_count`).
5. **Étanchéité inter-graphes (Critère C2, NFR-3)** :
   - Chaque requête Cypher de lecture contraint explicitement les nœuds et arêtes au `group_id = graph_id` cible pour garantir l'absence totale de fuite entre simulations distinctes hébergées dans la même base Neo4j.

Cette story livre l'ensemble des méthodes de lecture et de recherche de `GraphitiGraphStore` avec une suite de tests unitaires mockés hermétiques (540 tests verts).

## Définition de prêt

- [x] Contrat d'interface et signatures des 7 méthodes de lecture et recherche définies dans [`base.py`](../../backend/app/utils/graph_store/base.py)
- [x] Modèles neutres `GraphNode`, `GraphEdge`, `GraphInfo`, `GraphSearchResult` disponibles dans `base.py`
- [x] Requêtes Cypher de lecture et voisinage spécifiées dans [`architecture.md §4`](architecture.md)
- [x] Socle `GraphitiGraphStore`, write pipeline et passerelle `_run_async` validés en stories 003-1 et 003-2 (521 tests verts)
- [x] Exigences de temporalité (C3, NFR-4 : `created_at`, `valid_at`, `invalid_at`, `expired_at`) documentées
- [x] Règle de partitionnement `group_id = graph_id` (PRD C2, NFR-3) documentée
- [x] Documents consultés : [`prd.md`](prd.md), [`architecture.md`](architecture.md), [`epic-003.md`](epic-003.md), [ADR 0001](../../decisions/0001-remplacement-de-zep-par-graphiti.md), [ADR 0003](../../decisions/0003-ontologie-differee-en-v2.md)

## Définition de fini

- [x] `get_all_nodes(graph_id)` est implémenté, filtre par `group_id` et retourne une liste de `GraphNode` neutres
- [x] `get_all_edges(graph_id, include_temporal=True)` est implémenté, extrait les arêtes avec leurs 4 horodatages temporels et retourne une liste de `GraphEdge` neutres
- [x] `get_node(graph_id, node_uuid)` retourne le `GraphNode` ciblé ou `None` s'il n'existe pas ou appartient à un autre graphe
- [x] `get_node_edges(graph_id, node_uuid)` extrait le voisinage complet (entrant et sortant) scopé au `group_id`
- [x] `get_graph_data(graph_id)` retourne le dictionnaire complet conforme à l'API (`graph_id`, `nodes`, `edges`, `node_count`, `edge_count`, `statistics`)
- [x] `get_graph_info(graph_id)` retourne un `GraphInfo` agrégé valide
- [x] `search(graph_id, query, limit=10, scope="edges", reranker=None)` supporte les périmètres (`edges`, `nodes`, `hybrid`) et retourne un `GraphSearchResult` structuré
- [x] Toutes les requêtes Cypher appliquent strictement le prédicat d'isolation `group_id = graph_id` (0 fuite inter-simulations)
- [x] Toutes les exceptions levées lors des opérations de lecture sont traduites vers `GraphStoreError` via `_translate_errors`
- [x] Une suite de tests unitaires hermétiques dans `backend/tests/test_graphiti_graph_store.py` couvre 100 % des flux de lecture, de voisinage et de recherche
- [x] Les 521 tests existants restent 100 % au vert (`uv run pytest tests/ -q` -> 540 passés)
- [x] `uv run ruff check .` et `uv run python scripts/validate_plans.py` passent sans avertissement

## Tâches

- [x] Implémenter les helpers de conversion Cypher -> DTO neutres (`_record_to_graph_node`, `_record_to_graph_edge`)
- [x] Implémenter `get_all_nodes` avec requête Cypher paramétrée et filtrage `group_id`
- [x] Implémenter `get_all_edges` avec gestion de l'option `include_temporal` et extraction de `valid_at`, `invalid_at`, `expired_at`, `created_at`
- [x] Implémenter `get_node` avec gestion de la présence/absence du nœud
- [x] Implémenter `get_node_edges` pour le parcours de voisinage direct
- [x] Implémenter `get_graph_data` et `get_graph_info` avec agrégation des métriques
- [x] Implémenter `search` avec délégation à `graphiti.search` ou requêtes Cypher selon le scope et conversion en `GraphSearchResult`
- [x] Compléter `backend/tests/test_graphiti_graph_store.py` avec les tests unitaires de lecture, parcours et recherche
- [x] Valider l'étanchéité du partitionnement `group_id` sur toutes les opérations de lecture
- [x] Valider la non-régression globale sur l'ensemble de la suite de tests
- [x] Exécuter `ruff check .` et `validate_plans.py`

### Review Findings

- [x] [Review][Patch] Filtrage des embeddings vectoriels internes (name_embedding, fact_embedding) et propriétés système dans attributes [backend/app/utils/graph_store/graphiti_store.py:640, 680]
- [x] [Review][Patch] Prise en charge des collections (tuple, set) pour episodes dans _record_to_graph_edge [backend/app/utils/graph_store/graphiti_store.py:672]
- [x] [Review][Patch] Sécurisation null-safe avec coalesce sur n.name et n.summary dans la recherche de nœuds Cypher [backend/app/utils/graph_store/graphiti_store.py:935]
- [x] [Review][Patch] Rejet strict des booléens (limit=True) pour le paramètre limit dans search [backend/app/utils/graph_store/graphiti_store.py:885]
- [x] [Review][Patch] Mise à jour de la docstring d'en-tête de test_graphiti_graph_store.py pour inclure la Story 003-3 [backend/tests/test_graphiti_graph_store.py:1]
- [x] [Review][Patch] Tests unitaires hermétiques couvrant le filtrage des embeddings, la désérialisation de tuple d'épisodes et le rejet de limit=True [backend/tests/test_graphiti_graph_store.py]

#### Rejected

- [Ignorer le paramètre reranker dans search] : rejeté (`false`) — Le contrat d'interface GraphStore rend reranker optionnel (Optional[str] = None). Graphiti utilise un calcul de similarité vectoriel natif pour la recherche sémantique sans exiger de reranker externe en local (ADR 0001, ADR 0003).
- [Calcul de total_count par len(facts) + len(nodes) dans search] : rejeté (`false`) — Parité exacte avec l'implémentation de référence ZepGraphStore.search (lignes 1000-1008 de zep_store.py).
- [Validation explicite de isinstance(include_temporal, bool)] : rejeté (`low`) — Valeur par défaut True, comportement booléen standard en Python sans ambiguïté.

## Notes de développement

- **Mapping des nœuds (`GraphNode`)** :
  Dans Neo4j, les entités Graphiti portent le label `:Entity` et des propriétés `uuid`, `name`, `summary`, `group_id`, `created_at`. Le convertisseur `_record_to_graph_node` extrait ces champs et mappe l'ensemble des propriétés complémentaires dans `attributes`.
- **Mapping des relations temporelles (`GraphEdge`)** :
  Les arêtes créées par Graphiti portent le type `:RELATES_TO` (ou types dérivés), une propriété `fact`, `uuid`, `created_at`, `valid_at`, `invalid_at`, `expired_at`. Les nœuds source et destination sont identifiés par leurs UUIDs respectifs (`source_node_uuid`, `target_node_uuid`) et enrichis de leurs libellés nominatifs (`source_node_name`, `target_node_name`).
- **Structure de `get_graph_data`** :
  Pour garantir la compatibilité ascendante avec les routes `/api/graph/*` et le frontend Vue.js sans nécessiter de refonte d'interface, la structure retournée contient :
  ```python
  {
      "graph_id": graph_id,
      "nodes": [n.to_dict() for n in nodes],
      "edges": [e.to_dict(include_temporal=True) for e in edges],
      "node_count": len(nodes),
      "edge_count": len(edges),
      "statistics": {
          "node_count": len(nodes),
          "edge_count": len(edges),
      },
  }
  ```
- **Recherche hybride (`search`)** :
  `graphiti.search(query=query, group_ids=[graph_id], num_results=...)` exécute la recherche sémantique combinée. Selon la valeur de `scope` (`edges`, `nodes`, `hybrid`), les résultats sont extraits et projetés dans `GraphSearchResult(facts=..., nodes=..., edges=..., query=..., total_count=...)`.
- **Isolation `group_id`** :
  Aucune requête de lecture n'interroge la base sans contraindre `group_id: $group_id` sur les nœuds source, cible ou intermédiaires.

## Revue

- **Revue contradictoire BMad (8 octobre 2026)** :
  1. *Conformité au contrat GraphStore (Critère C1, NFR-1)* : Les 14 méthodes de l'interface `GraphStore` sont intégralement implémentées dans `GraphitiGraphStore`, sans aucun stub résiduel `NotImplementedError`.
  2. *Isolation étanche (Critère C2, NFR-3)* : L'ensemble des 5 requêtes Cypher (`get_all_nodes`, `get_all_edges`, `get_node`, `get_node_edges`, `search`) et les appels `graphiti.search(..., group_ids=[target_graph_id])` filtrent explicitement sur `group_id = graph_id`. Des tests dédiés (`TestGraphitiStrictPartitioningIsolation`) valident l'absence de fuite.
  3. *Temporalité (Critère C3, NFR-4)* : Les métadonnées temporelles (`created_at`, `valid_at`, `invalid_at`, `expired_at`) sont correctement extraites et projetées vers `GraphEdge`, avec respect du flag `include_temporal`.
  4. *Rétrocompatibilité API / Frontend (Critère C4, NFR-5)* : `get_graph_data` produit exactement la structure dictionnaire attendue par `/api/graph/*` et le frontend Vue.js.
  5. *Traduction des erreurs* : L'ensemble des méthodes est enveloppé dans `with self._translate_errors(...)`, traduisant les exceptions Neo4j et Graphiti vers `GraphStoreError`.
  6. *Application des 6 patchs de revue* : Filtrage des vecteurs d'embeddings (`name_embedding`, `fact_embedding`) dans `attributes`, désérialisation flexible de `episodes` (tuple/set), `coalesce` défensif en Cypher, rejet strict de `limit=True`, synchronisation docstring et nouveaux tests unitaires dédiés (`TestGraphitiReviewPatchesStory003_3`).
  7. *Couverture de tests et non-régression* : 74 tests unitaires dédiés dans `test_graphiti_graph_store.py` (couvrant 100 % des flux), **545 tests globaux au vert** sur l'ensemble du projet (+24 tests). `ruff check .` et `validate_plans.py` passent sans avertissement.

## Notes de complétion

- **Date de complétion** : 8 octobre 2026.
- **Bilan d'implémentation** :
  - Implémentation des convertisseurs `_record_to_graph_node` et `_record_to_graph_edge` dans `GraphitiGraphStore`.
  - Implémentation complète de `get_all_nodes`, `get_all_edges`, `get_node`, `get_node_edges`, `get_graph_data`, `get_graph_info` et `search`.
  - Résolution des noms d'entités associés lors des recherches sémantiques `search` avec `scope='edges'` ou `scope='hybrid'`.
  - Intégration et validation des 6 patchs de la revue contradictoire BMad.
  - Enrichissement de `test_graphiti_graph_store.py` avec 24 nouveaux tests unitaires hermétiques validant la lecture, le voisinage, la temporalité, l'agrégation, la recherche hybride et les cas limites de revue (74 tests sur le module).
  - Filet de sécurité étendu à **545 tests unitaires verts** (+24 tests).
  - Statut : **VALIDÉ / DONE**.

