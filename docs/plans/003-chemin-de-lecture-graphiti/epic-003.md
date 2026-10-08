# Epic 003 — GraphitiGraphStore : écriture et chemin de lecture (ADR 0003)

- **Statut** : `in-progress` · **Dépend de** : 001, 002 · **Bloque** : 004, 005
- **Suivi** : [`sprint-status.yaml`](../../sprint-status.yaml)

> L'Epic 001 a prouvé que la chaîne locale Graphiti + Neo4j 5.26 + OpenCode Go fonctionne sans frais.
> L'Epic 002 a isolé MiroFish derrière l'interface `GraphStore` (470 tests verts).
> Cet Epic 003 concrétise le backend local `GraphitiGraphStore` et débloque le chemin de lecture.
>
> Le plan complet du projet est dans [`docs/LOCAL-FIRST.md`](../../LOCAL-FIRST.md) et la cible d'architecture dans
> [`docs/architecture/cible-graphstore.md`](../../architecture/cible-graphstore.md).

**Artefacts de ce dossier** — [`prd.md`](prd.md) (quoi, pourquoi, critères chiffrés) ·
[`architecture.md`](architecture.md) (comment, modèles et schémas) · ce fichier (le contrat
d'ingénierie) · `story-003-<n>.md` (une story démarrée = un fichier markdown).

---

## Le problème en une phrase

Seul le backend Zep Cloud est actuellement implémenté derrière l'interface `GraphStore` ; pour faire fonctionner
MiroFish en local-first sans cloud ni crédits, il faut implémenter `GraphitiGraphStore` sur Neo4j et adapter
le chemin de lecture d'entités pour qu'il ne dépende pas d'une ontologie custom (ADR 0003).

## Objectif

Implémenter la classe `GraphitiGraphStore` dans `backend/app/utils/graph_store/graphiti_store.py`, connecter
Graphiti au driver Neo4j local, au client LLM avec gestion de session OpenCode Go et à l'embedder local,
assurer l'isolation stricte par `group_id`, implémenter les requêtes de lecture et recherche temporelle Cypher,
adapter `zep_entity_reader.py` pour exploiter les entités sans label custom, et activer `ZEP_BACKEND='graphiti'`
dans la factory sans aucune régression sur le filet de tests existant (470 tests).

## Exigences fonctionnelles

| # | Exigence |
|---|---|
| FR-1 | Créer `GraphitiGraphStore` héritant de `GraphStore`, initialiser le moteur Graphiti avec le driver Neo4j, `GraphitiOpenAIClient` et `SentenceTransformersEmbedder` local |
| FR-2 | Activer la résolution de `ZEP_BACKEND='graphiti'` dans la factory `get_graph_store()` à partir des variables d'environnement (`NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`) |
| FR-3 | Implémenter l'écriture et le cycle de vie du graphe (`create_graph`, `delete_graph`, `add_episode`, `add_text_batch`, `set_ontology` no-op) avec partitionnement strict par `group_id = graph_id` |
| FR-4 | Implémenter la lecture par requêtes Cypher optimisées (`get_all_nodes`, `get_all_edges`, `get_node`, `get_node_edges`, `get_graph_data`, `get_graph_info`) en préservant 100 % des métadonnées temporelles |
| FR-5 | Implémenter la recherche hybride (vectorielle + sémantique / BM25) via `search()` mappée sur les structures neutres `GraphSearchResult` |
| FR-6 | Adapter le chemin de lecture dans `zep_entity_reader.py` pour accepter et typer les entités Graphiti portant le label générique `:Entity` sans exiger de custom labels Zep |
| FR-7 | Fournir une suite de tests unitaires mockés hermétiques et des tests d'intégration réels contre l'instance Neo4j locale (`docker-compose.neo4j.yml`) |

## Exigences non fonctionnelles

| # | Exigence | Pourquoi |
|---|---|---|
| NFR-1 | Zéro régression : les 470 tests existants restent verts | La livraison du second backend ne doit altérer aucun comportement existant |
| NFR-2 | Clean Architecture : dépendances vers l'intérieur | `services` → `GraphStore`, aucun import direct de `graphiti_core` ni de `neo4j` dans les services ou l'API (AGENTS.md §2.1) |
| NFR-3 | Isolation inter-simulations absolue | `group_id = graph_id` présent sur tous les nœuds, arêtes et filtres Cypher (0 fuite inter-graphes) |
| NFR-4 | Préservation de la sémantique temporelle | `valid_at`, `invalid_at`, `expired_at`, `created_at` fidèlement restitués pour les personas et rapports |
| NFR-5 | Tests unitaires hermétiques par défaut | Pas de dépendance obligatoire à un Neo4j en ligne ou à des appels réseau pour exécuter la suite de tests standard |

## UX requirements

Cet epic est un chantier d'infrastructure backend. Les contrats JSON des routes HTTP `/api/graph/*` et le
comportement pour le frontend restent strictement identiques, que le backend soit Zep ou Graphiti.

## Index des stories

| Story | Titre | Statut | Fichier |
|---|---|---|---|
| 003-1 | Squelette de `GraphitiGraphStore`, initialisation des dépendances et activation dans la factory | `done` | [`story-003-1.md`](story-003-1.md) |
| 003-2 | Implémentation du cycle de vie et de l'ingestion d'épisodes avec partitionnement `group_id` | `in-progress` | [`story-003-2.md`](story-003-2.md) |
| 003-3 | Implémentation de la lecture Cypher, des parcours de voisinage et de la recherche hybride temporelle | `backlog` | — |
| 003-4 | Adaptation du chemin de lecture (`zep_entity_reader.py`) pour les entités génériques Graphiti | `backlog` | — |
| 003-5 | Tests d'intégration réels avec Neo4j local, validation des critères C1-C6 et clôture de l'Epic 003 | `backlog` | — |

| Story | Critères d'acceptation (résumé) |
|---|---|
| 003-1 | Given la classe `GraphitiGraphStore`, when elle est instanciée, then elle initialise le driver Neo4j, `GraphitiOpenAIClient` (OpenCode Go avec en-têtes de session et `json_object`) et `SentenceTransformersEmbedder` local ; la factory `get_graph_store(backend="graphiti")` retourne l'instance sans lever `NotImplementedError` ; des tests unitaires mockés valident l'instanciation |
| 003-2 | Given `GraphitiGraphStore`, when `add_episode` ou `add_text_batch` est appelé, then les épisodes sont persistés via Graphiti avec `group_id = graph_id` ; `delete_graph` supprime l'ensemble des nœuds et relations rattachés au groupe ; `set_ontology` est un no-op gracieux |
| 003-3 | Given un graphe Graphiti peuplé, when `get_all_nodes`, `get_all_edges`, `get_node_edges` et `search` sont appelés, then les requêtes Cypher filtrent par `group_id` et retournent les modèles neutres `GraphNode` et `GraphEdge` avec leurs 4 timestamps temporels ; `search` retourne un `GraphSearchResult` complet |
| 003-4 | Given un graphe contenant des nœuds avec le label unique `:Entity`, when `zep_entity_reader.py` analyse le graphe, then les nœuds ne sont plus ignorés silencieusement ; `get_entity_nodes` et `get_entity_with_context` retournent des entités exploitables pour la configuration de simulation |
| 003-5 | Given l'environnement Neo4j de l'épreuve (`docker-compose.neo4j.yml`), when les tests d'intégration sont exécutés, then l'ingestion d'un document, la lecture et la recherche fonctionnent de bout en bout ; 100 % des 470 tests existants restent verts ; les critères C1 à C6 du PRD sont satisfaits ; la documentation est synchronisée |

## Documents à consulter

| Document | Ce qu'on y prend |
|---|---|
| [`prd.md`](prd.md) | Objectifs et critères chiffrés C1 à C6 de l'Epic 003 |
| [`architecture.md`](architecture.md) | Schémas de composants, requêtes Cypher et flux de données |
| [ADR 0001](../../decisions/0001-remplacement-de-zep-par-graphiti.md) | Choix de Graphiti + Neo4j derrière l'interface unifiée |
| [ADR 0003](../../decisions/0003-ontologie-differee-en-v2.md) | Décision de différer l'ontologie dynamique en v2 et prioriser le chemin de lecture |
| [ADR 0010](../../decisions/0010-override-driver-neo4j.md) | Arbitrage du driver Neo4j 5.26 |
| [`docs/LOCAL-FIRST.md` §12](../../LOCAL-FIRST.md) | Audit des pièges du fork `tt-a1i` et points de rupture Graphiti |
| `backend/app/utils/graph_store/base.py` | Contrat formel de l'interface `GraphStore` et DTOs neutres |
| `backend/app/utils/graph_store/factory.py` | Factory `get_graph_store()` |
| `backend/app/utils/graph_store/graphiti_store.py` | Implémentation `GraphitiGraphStore` et `LocalPassthroughCrossEncoder` |
| `backend/app/utils/graphiti_llm_client.py` | Client LLM avec compatibilité session OpenCode Go |
| `backend/app/utils/graphiti_embedder.py` | Embedder local SentenceTransformers |

## Décisions liées

- **ADR 0001** — Remplacement de Zep par Graphiti + Neo4j derrière une interface
- **ADR 0003** — Ontologie dynamique différée en v2 : le chemin de lecture d'abord
- **ADR 0004** — Endpoint LLM gratuit OpenCode Go avec session
- **ADR 0007** — Une story = un fichier markdown
- **ADR 0010** — Override du driver Neo4j 5.26 pour résoudre le conflit avec Oasis
- **ADR 0011** — Format 2 des stories et sections obligatoires en français

## L'epic est terminé quand

- [x] `GraphitiGraphStore` est initialisé avec driver Neo4j, LLM session et embedder local (Story 003-1)
- [ ] Le cycle de vie et l'ingestion d'épisodes sont implémentés avec isolation par `group_id` (Story 003-2)
- [ ] La lecture Cypher, les requêtes de voisinage et la recherche hybride temporelle sont opérationnelles (Story 003-3)
- [ ] Le chemin de lecture (`zep_entity_reader.py`) traite avec succès les entités Graphiti (Story 003-4)
- [ ] Les tests d'intégration réels sur Neo4j local passent et les 470 tests existants restent verts (Story 003-5)
