---
id: "003-3"
epic: "003"
titre: "Lecture Cypher, parcours de voisinage et recherche hybride temporelle dans GraphitiGraphStore"
statut: in-progress
auteur: agent
format: "2"
---

# Story 003-3 — Lecture Cypher, parcours de voisinage et recherche hybride temporelle dans GraphitiGraphStore

## Pourquoi cette story

Les stories 003-1 et 003-2 ont posé le socle opérationnel et le pipeline d'écriture de `GraphitiGraphStore` : initialisation des dépendances locales, constructeur à injection, gestionnaire asynchrone `_run_async`, cycle de vie (`create_graph`, `delete_graph`, `set_ontology`) et ingestion d'épisodes (`add_episode`, `add_text_batch`, `wait_for_batch`, `wait_for_episodes`) avec partitionnement strict `group_id = graph_id` (521 tests verts).

Cependant, les méthodes de lecture, de parcours et de recherche lèvent actuellement une exception `NotImplementedError` :
- `get_all_nodes`
- `get_all_edges`
- `get_node`
- `get_node_edges`
- `get_graph_data`
- `get_graph_info`
- `search`

Pour permettre aux modules en aval de consommer la mémoire de simulation et d'exposer les données :
1. **Extraction ensembliste de nœuds et arêtes** :
   - `get_all_nodes(graph_id)` doit récupérer l'ensemble des entités rattachées au groupe via `MATCH (n:Entity {group_id: $group_id})` et les convertir en `GraphNode` agnostiques.
   - `get_all_edges(graph_id, include_temporal=True)` doit récupérer les relations entre entités du groupe via `MATCH (source:Entity)-[r]->(target:Entity) WHERE source.group_id = $group_id AND target.group_id = $group_id` et les convertir en `GraphEdge` neutres en préservant fidèlement les métadonnées temporelles (Critère C3, NFR-4).
2. **Parcours ponctuel et voisinage** :
   - `get_node(graph_id, node_uuid)` doit extraire un nœud unique vérifiant strictement le `group_id`.
   - `get_node_edges(graph_id, node_uuid)` doit collecter l'ensemble des arêtes incidentes (entrantes et sortantes) connectant le nœud à ses voisins du même groupe.
3. **Consolidation pour l'API et l'interface utilisateur** :
   - `get_graph_data(graph_id)` doit agréger nœuds et arêtes au format attendu par la visualisation du frontend (`/api/graph/*`) avec les propriétés de rétrocompatibilité (`graph_id`, `nodes`, `edges`, `node_count`, `edge_count`, `statistics`).
   - `get_graph_info(graph_id)` doit retourner un `GraphInfo` synthétique comportant les comptages et la liste des types d'entités présents.
4. **Recherche hybride temporelle** :
   - `search(graph_id, query, limit=10, scope="edges", reranker=None)` doit exploiter les capacités de recherche sémantique/hybride de `graphiti.search` ou des requêtes Cypher dédiées filtrées par `group_id`, et restituer un `GraphSearchResult` structuré (`facts`, `nodes`, `edges`, `query`, `total_count`).
5. **Étanchéité inter-graphes (Critère C2, NFR-3)** :
   - Chaque requête Cypher de lecture doit contraindre explicitement les nœuds et arêtes au `group_id = graph_id` cible pour garantir l'absence totale de fuite entre simulations distinctes hébergées dans la même base Neo4j.

Cette story livre l'ensemble des méthodes de lecture et de recherche de `GraphitiGraphStore` avec une suite de tests unitaires mockés hermétiques.

## Définition de prêt

- [x] Contrat d'interface et signatures des 7 méthodes de lecture et recherche définies dans [`base.py`](../../backend/app/utils/graph_store/base.py)
- [x] Modèles neutres `GraphNode`, `GraphEdge`, `GraphInfo`, `GraphSearchResult` disponibles dans `base.py`
- [x] Requêtes Cypher de lecture et voisinage spécifiées dans [`architecture.md §4`](architecture.md)
- [x] Socle `GraphitiGraphStore`, write pipeline et passerelle `_run_async` validés en stories 003-1 et 003-2 (521 tests verts)
- [x] Exigences de temporalité (C3, NFR-4 : `created_at`, `valid_at`, `invalid_at`, `expired_at`) documentées
- [x] Règle de partitionnement `group_id = graph_id` (PRD C2, NFR-3) documentée
- [x] Documents consultés : [`prd.md`](prd.md), [`architecture.md`](architecture.md), [`epic-003.md`](epic-003.md), [ADR 0001](../../decisions/0001-remplacement-de-zep-par-graphiti.md), [ADR 0003](../../decisions/0003-ontologie-differee-en-v2.md)

## Définition de fini

- [ ] `get_all_nodes(graph_id)` est implémenté, filtre par `group_id` et retourne une liste de `GraphNode` neutres
- [ ] `get_all_edges(graph_id, include_temporal=True)` est implémenté, extrait les arêtes avec leurs 4 horodatages temporels et retourne une liste de `GraphEdge` neutres
- [ ] `get_node(graph_id, node_uuid)` retourne le `GraphNode` ciblé ou `None` s'il n'existe pas ou appartient à un autre graphe
- [ ] `get_node_edges(graph_id, node_uuid)` extrait le voisinage complet (entrant et sortant) scopé au `group_id`
- [ ] `get_graph_data(graph_id)` retourne le dictionnaire complet conforme à l'API (`graph_id`, `nodes`, `edges`, `node_count`, `edge_count`, `statistics`)
- [ ] `get_graph_info(graph_id)` retourne un `GraphInfo` agrégé valide
- [ ] `search(graph_id, query, limit=10, scope="edges", reranker=None)` supporte les périmètres (`edges`, `nodes`, `hybrid`) et retourne un `GraphSearchResult` structuré
- [ ] Toutes les requêtes Cypher appliquent strictement le prédicat d'isolation `group_id = graph_id` (0 fuite inter-simulations)
- [ ] Toutes les exceptions levées lors des opérations de lecture sont traduites vers `GraphStoreError` via `_translate_errors`
- [ ] Une suite de tests unitaires hermétiques dans `backend/tests/test_graphiti_graph_store.py` couvre 100 % des flux de lecture, de voisinage et de recherche
- [ ] Les 521 tests existants restent 100 % au vert (`uv run pytest tests/ -q`)
- [ ] `uv run ruff check .` et `uv run python scripts/validate_plans.py` passent sans avertissement

## Tâches

- [ ] Implémenter les helpers de conversion Cypher -> DTO neutres (`_record_to_graph_node`, `_record_to_graph_edge`)
- [ ] Implémenter `get_all_nodes` avec requête Cypher paramétrée et filtrage `group_id`
- [ ] Implémenter `get_all_edges` avec gestion de l'option `include_temporal` et extraction de `valid_at`, `invalid_at`, `expired_at`, `created_at`
- [ ] Implémenter `get_node` avec gestion de la présence/absence du nœud
- [ ] Implémenter `get_node_edges` pour le parcours de voisinage direct
- [ ] Implémenter `get_graph_data` et `get_graph_info` avec agrégation des métriques
- [ ] Implémenter `search` avec délégation à `graphiti.search` ou requêtes Cypher selon le scope et conversion en `GraphSearchResult`
- [ ] Compléter `backend/tests/test_graphiti_graph_store.py` avec les tests unitaires de lecture, parcours et recherche
- [ ] Valider l'étanchéité du partitionnement `group_id` sur toutes les opérations de lecture
- [ ] Valider la non-régression globale sur l'ensemble de la suite de tests
- [ ] Exécuter `ruff check .` et `validate_plans.py`

## Notes de développement

- **Mapping des nœuds (`GraphNode`)** :
  Dans Neo4j, les entités Graphiti portent le label `:Entity` et des propriétés `uuid`, `name`, `summary`, `group_id`, `created_at`. Le convertisseur extrait ces champs et mappe l'ensemble des propriétés complémentaires dans `attributes`.
- **Mapping des relations temporelles (`GraphEdge`)** :
  Les arêtes créées par Graphiti portent le type `:RELATES_TO` (ou types dérivés), une propriété `fact`, `uuid`, `created_at`, `valid_at`, `invalid_at`, `expired_at`. Les nœuds source et destination doivent être identifiés par leurs UUIDs respectifs (`source_uuid`, `target_uuid`).
- **Structure de `get_graph_data`** :
  Pour garantir la compatibilité ascendante avec les routes `/api/graph/*` et le frontend Vue.js sans nécessiter de refonte d'interface, la structure retournée doit contenir :
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
  `graphiti.search(prompt=query, group_ids=[graph_id])` exécute la recherche sémantique combinée. Selon la valeur de `scope` (`edges`, `nodes`, `hybrid`), les résultats sont extraits et projetés dans `GraphSearchResult(facts=..., nodes=..., edges=..., query=..., total_count=...)`.
- **Isolation `group_id`** :
  Aucune requête de lecture ne doit interroger la base sans contraindre `group_id: $group_id` sur les nœuds source, cible ou intermédiaires.

## Revue

*(Section à compléter lors de la revue contradictoire BMad de la story 003-3)*

## Notes de complétion

*(Section à renseigner lors de la clôture de la story 003-3)*
