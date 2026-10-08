# Epic 003 — GraphitiGraphStore : écriture et chemin de lecture (ADR 0003)

- **Statut** : `in-progress` · **Dépend de** : 001, 002 · **Bloque** : 004, 005
- **Suivi** : [`sprint-status.yaml`](../../sprint-status.yaml)

> L'épreuve technique de l'Epic 001 a prouvé avec succès (Verdict GO validé) que Graphiti, Neo4j 5.26,
> l'embedder local `all-MiniLM-L6-v2` et le LLM gratuit OpenCode Go permettent d'extraire des entités et relations
> exploitables à coût marginal nul.
> L'Epic 002 a ensuite posé l'interface neutre `GraphStore`, encapsulé l'implémentation existante `ZepGraphStore`
> et prouvé par analyse AST l'étanchéité totale du code métier vis-à-vis des SDK tiers (470 tests verts).
>
> L'**Epic 003** constitue le tournant opérationnel local-first : il implémente la seconde classe concrète
> `GraphitiGraphStore`, connecte Graphiti et Neo4j en local, et résout le défi structurel du chemin de lecture
> sans dépendre de l'ontologie dynamique (ADR 0003).

---

## 1. Le problème

### 1.1 Contexte et état des lieux

MiroFish consomme désormais le graphe de connaissances exclusivement à travers l'interface formelle
`GraphStore` et sa factory `get_graph_store()`. Cependant, à ce jour, seule l'implémentation `ZepGraphStore`
est opérationnelle. La factory lève une exception explicite `NotImplementedError` lorsque `ZEP_BACKEND='graphiti'`
est demandé.

Pour que MiroFish fonctionne de manière autonome en local et sans dépendance au cloud Zep, il est nécessaire
d'implémenter `GraphitiGraphStore` dans `backend/app/utils/graph_store/graphiti_store.py`.

### 1.2 Les pièges constatés et le problème du chemin de lecture

L'audit détaillé des forks communautaires (`docs/LOCAL-FIRST.md` §12) et l'analyse de l'ADR 0003 ont mis en
lumière les causes fondamentales d'échec des tentatives précédentes de portage de Graphiti sur MiroFish :

1. **Le piège du graphe vide en lecture (ADR 0003, LOCAL-FIRST.md §12.3)** :
   Dans le code amont hérité de Zep, `backend/app/services/zep_entity_reader.py` filtre les entités selon :
   ```python
   custom_labels = [l for l in labels if l not in ["Entity", "Node"]]
   if not custom_labels:
       # Nœud ignoré !
   ```
   Or Graphiti, lorsqu'il est exécuté sans ontologie Pydantic custom générée dynamiquement, appose
   systématiquement le label unique `:Entity`. Sans adaptation, **100 % des nœuds sont silencieusement ignorés**,
   et les générateurs de personas et de simulation opèrent sur un graphe vide.
2. **L'écrasement de la temporalité** :
   Les timestamps et fenêtres de validité temporelle (`created_at`, `valid_at`, `invalid_at`, `expired_at`),
   qui constituent le cœur de la mémoire du monde simulé, ont souvent été écrasés ou mis à `None` par les
   implémentations naïves.
3. **Le défaut d'isolation inter-graphes** :
   Dans Zep Cloud, chaque simulation possède un `graph_id` étanche. Dans Neo4j partagé, sans isolation stricte
   par `group_id = graph_id` sur chaque nœud, arête et requête Cypher, les données de différentes simulations
   se mélangent.
4. **Structured output et compatibilité d'endpoint** :
   Graphiti s'appuie sur la génération JSON structurée. Sans le paramètre `structured_output_mode="json_object"`,
   les retries appropriés et l'injection des en-têtes de session (`x-opencode-session`), les extractions
   échouent fréquemment (portails validés lors de l'Epic 001).

L'**ADR 0003** a acté la décision clé : **l'ontologie dynamique est différée en v2 (Epic 007)**.
L'effort doit porter en priorité sur **le chemin de lecture**, afin de rendre les entités et faits extraits par
Graphiti directement exploitables par le moteur de personas et de rapport.

---

## 2. L'objectif

Concevoir, implémenter et valider l'implémentation concrète `GraphitiGraphStore` :
1. Implémenter l'intégralité des 14 méthodes de l'interface `GraphStore` dans `backend/app/utils/graph_store/graphiti_store.py`.
2. Connecter le moteur `graphiti-core` au driver Neo4j 5.26 (avec override), au client LLM avec gestion de session
   (`GraphitiOpenAIClient`) et à l'embedder local `SentenceTransformersEmbedder` (`all-MiniLM-L6-v2`).
3. Assurer une étanchéité absolue des données entre graphes au moyen du partitionnement systématique par `group_id = graph_id`.
4. Restituer fidèlement les données temporelles (`valid_at`, `invalid_at`, `expired_at`, `created_at`) via des requêtes Cypher optimisées.
5. Adapter le chemin de lecture (`zep_entity_reader.py`) pour consommer les entités extraites par Graphiti sans exiger
   de labels d'ontologie custom.
6. Activer le support de `ZEP_BACKEND='graphiti'` dans la factory `get_graph_store()`.
7. Démontrer la fiabilité par des tests unitaires hermétiques mockés et des tests d'intégration réels sur l'instance
   Neo4j locale (`docker-compose.neo4j.yml`), sans aucune régression sur le filet existant (470 tests verts).

---

## 3. Ce que cet epic n'est pas

| Hors périmètre | Pourquoi |
|---|---|
| L'ontologie dynamique générée par LLM à l'exécution | Différée en v2 par l'ADR 0003 (Epic 007) |
| L'exécution de bout en bout de l'application sans clé Zep dans l'UI | Fait l'objet de l'Epic 004 (bascule globale et suppression de la clé Zep) |
| L'environnement Docker unifié pour toute l'application | Fait l'objet de l'Epic 005 (Docker-first) |
| La migration de données depuis un compte Zep Cloud existant | Fait l'objet de l'Epic 006 |

---

## 4. Critères de sortie — chiffrés

| # | Critère | Seuil | Sinon |
|---|---|---|---|
| **C1** | Implémentation complète de l'interface `GraphStore` | **100 %** des 14 méthodes abstraites implémentées par `GraphitiGraphStore`, sans fuite de types propriétaires | Rejet du composant |
| **C2** | Partitionnement et isolation stricte par `group_id` | **0** fuite de nœuds ou d'arêtes entre deux `graph_id` distincts hébergés dans la même base Neo4j | Risque d'intégrité critique |
| **C3** | Préservation des métadonnées temporelles | **100 %** des arêtes temporelles retournées portent `created_at`, `valid_at`, `invalid_at`, `expired_at` (ou `None` explicite si indéterminé) | Rupture de temporalité |
| **C4** | Chemin de lecture opérationnel sans ontologie custom | Sur un graphe Graphiti, `get_all_nodes()` et `zep_entity_reader.py` retournent un nombre **> 0** d'entités exploitables (0 nœud filtré à tort) | Graphe vide en simulation |
| **C5** | Activation transparente via factory `ZEP_BACKEND` | `get_graph_store(backend="graphiti")` retourne une instance opérationnelle de `GraphitiGraphStore` | Erreur d'instanciation |
| **C6** | Filet de tests et non-régression | **100 % des 470 tests existants** restent verts, enrichis de tests unitaires et d'intégration dédiés (≥ 15 nouveaux tests) | Régression bloquante |

---

## 5. Recensement des opérations de `GraphitiGraphStore`

L'implémentation doit satisfaire le contrat d'interface `GraphStore` (défini dans `backend/app/utils/graph_store/base.py`) :

1. **Cycle de vie du graphe** :
   - `create_graph(name: str, graph_id: str | None = None) -> str` : Enregistrement de l'identifiant logique (`group_id`).
   - `delete_graph(graph_id: str) -> None` : Suppression Cypher ciblée de tous les nœuds, arêtes et épisodes associés au `group_id`.
   - `get_graph_data(graph_id: str) -> Dict[str, Any]` : Extraction des nœuds et arêtes au format attendu par la visualisation frontend.
   - `get_graph_info(graph_id: str) -> GraphInfo` : Métriques consolidées (nombre de nœuds, d'arêtes, types d'entités).

2. **Ontologie (v1)** :
   - `set_ontology(graph_id: str, ontology: Dict[str, Any]) -> None` : No-op gracieux avec enregistrement des métadonnées (conformément à l'ADR 0003).

3. **Ingestion et épisodes** :
   - `add_episode(graph_id: str, text: str, source_description: str = "", metadata: dict | None = None, created_at: str | None = None) -> EpisodeRecord` : Ingestion via `graphiti.add_episode(group_id=graph_id)`.
   - `add_text_batch(graph_id: str, chunks: List[str], batch_size: int = 350, progress_callback: Callable | None = None) -> BatchSubmissionRecord` : Traitement séquentiel ou parallèle par lots via Graphiti.
   - `wait_for_batch(batch: BatchSubmissionRecord, progress_callback: Callable | None = None, timeout: float = 600.0) -> bool` : Synchronisation (Graphiti traitant les épisodes de manière synchrone, retourne `True` après écriture).
   - `wait_for_episodes(graph_id: str, episode_uuids: List[str], timeout: float = 600.0) -> bool` : Vérification de persistance dans Neo4j.

4. **Interrogation et parcours (Cypher)** :
   - `get_all_nodes(graph_id: str) -> List[GraphNode]` : Requête Cypher `MATCH (n:Entity {group_id: $group_id}) RETURN n`.
   - `get_all_edges(graph_id: str, include_temporal: bool = True) -> List[GraphEdge]` : Requête Cypher sur les relations du groupe.
   - `get_node(graph_id: str, node_uuid: str) -> GraphNode | None` : Récupération d'un nœud spécifique avec contrôle de `group_id`.
   - `get_node_edges(graph_id: str, node_uuid: str) -> List[GraphEdge]` : Voisinage immédiat (arêtes entrantes et sortantes).

5. **Recherche sémantique et hybride** :
   - `search(graph_id: str, query: str, limit: int = 10, scope: str = "edges", reranker: str | None = None) -> GraphSearchResult` : Recherche hybride (vectorielle + fulltext/BM25) via `graphiti.search(group_ids=[graph_id])` avec mapping vers les modèles neutres.

---

## 6. Risques et parades

| Risque | Signal | Parade |
|---|---|---|
| Filtre trop restrictif dans `zep_entity_reader.py` excluant les nœuds Graphiti | `get_entity_nodes()` retourne une liste vide sur un graphe peuplé | Normaliser le filtre de lecture : si aucun custom label n'est présent, accepter le label générique `:Entity` et déduire le type à partir des attributs ou du nom |
| Injection de données inter-graphes dans Neo4j | Données d'une ancienne simulation apparaissant dans une nouvelle | Appliquer systématiquement le prédicat `WHERE n.group_id = $group_id` sur 100 % des requêtes Cypher de lecture et d'écriture |
| Conflit de versions de dépendances (`sentence-transformers`, `neo4j`) | Erreur d'import ou de synchronisation `uv sync` | Exploiter les modules dédiés éprouvés lors de l'Epic 001 (`graphiti_embedder.py`, `verifier_driver_neo4j.py`) |
| Erreurs HTTP 400 `MissingSessionID` lors de l'extraction Graphiti | Échec de l'appel LLM dans `graphiti.add_episode` | Utiliser `GraphitiOpenAIClient` qui surcharge `acompletion` pour injecter automatiquement `x-opencode-session` |
| Échecs de parsing JSON sur OpenCode Go | Erreur `OutputParsingException` dans Graphiti | Configurer explicitement `structured_output_mode="json_object"` sur le client Graphiti |
