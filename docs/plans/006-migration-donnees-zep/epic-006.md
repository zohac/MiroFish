# Epic 006 — Migrer un graphe Zep existant — ou acter qu'on jette

- **Statut** : `backlog` · **Dépend de** : 003, 004, 005 · **Bloque** : aucun
- **Suivi** : [`sprint-status.yaml`](../../sprint-status.yaml)
- **PRD** : [`prd.md`](prd.md) · **Architecture** : [`architecture.md`](architecture.md)

> Les Epics 001 à 005 ont délivré une pile locale-first complète (Graphiti, Neo4j, Docker de référence, 711 tests verts).  
> **L'Epic 006 apporte la réponse définitive à la gestion des données historiques Zep Cloud** : un outillage d'audit pour recenser ce qui existe, un arbre de décision formalisé (« Migrer ou Jeter »), un pipeline ETL pour rapatrier directement les graphes vers Neo4j local sans coût LLM, et un outil de purge sécurisé.

---

## 1. Exigences fonctionnelles (FR)

| Réf. | Intitulé | Description |
|---|---|---|
| **FR-1** | Audit et inventaire d'un compte Zep | `auditer_graphes_zep.py` liste l'ensemble des graphes d'un compte avec comptage de nœuds, arêtes, épisodes et dates. |
| **FR-2** | Extraction paginée sans perte | Récupération intégrale des nœuds et arêtes via le SDK Zep et pagination par curseurs. |
| **FR-3** | Mapping et transformation de schéma | Traduction vers le modèle Graphiti Neo4j (`:Entity`, `group_id = target_graph_id`, attributs, métadonnées temporelles). |
| **FR-4** | Injection Cypher transactionnelle par lots | Chargement direct dans Neo4j local sans sollicitation de modèles LLM. |
| **FR-5** | Relecture applicative validée | Les graphes importés sont relus sans erreur par `GraphitiGraphStore` et exploités par `ZepEntityReader`. |
| **FR-6** | Purge distante contrôlée | Script autonome `purger_graphes_zep.py` avec confirmation explicite pour clore les graphes sur Zep Cloud. |

---

## 2. Exigences non fonctionnelles (NFR)

| Réf. | Intitulé | Description |
|---|---|---|
| **NFR-1** | Coût marginal nul (0 €) | Rapatriement direct structurel sans ré-extraction ni appels API payants. |
| **NFR-2** | Idempotence et étanchéité | Ré-exécution sûre sans duplication ni fuite inter-graphes. |
| **NFR-3** | Préservation temporelle | Horodatages `valid_at`, `invalid_at`, `expired_at` rigoureusement conservés. |
| **NFR-4** | Hermétisme des tests | 100 % des tests CI mockent Zep Cloud et Neo4j, 0 dépendance réseau externe. |

---

## 3. UX requirements

- L'utilisateur peut auditer son compte Zep Cloud avec une commande unique et obtenir un récapitulatif clair.
- L'arbre d'arbitrage fournit une recommandation objective entre ré-ingestion locale et migration ETL directe.
- Le rapatriement affiche une barre de progression claire par lots et valide l'intégrité à l'arrivée.
- La purge exige une double confirmation afin d'éviter toute suppression accidentelle.

---

## 4. Index des stories

| Story | Titre | Statut | Fichier |
|---|---|---|---|
| 006-1 | Outil d'audit et d'inventaire d'un compte Zep Cloud (`auditer_graphes_zep.py`) | `backlog` | `story-006-1.md` |
| 006-2 | Pipeline ETL de transformation et injection directe Cypher dans Neo4j (`migrer_zep_vers_graphiti.py`) | `backlog` | `story-006-2.md` |
| 006-3 | Validation de relecture GraphStore, personas OASIS et outil de purge Zep Cloud (`purger_graphes_zep.py`) | `backlog` | `story-006-3.md` |

| Story | Critères d'acceptation (résumé) |
|---|---|
| 006-1 | Given une clé `ZEP_API_KEY` valide, when `auditer_graphes_zep.py` est lancé, then l'ensemble des graphes distants est inspecté et restitué sous forme de tableau et fichier JSON avec nombre d'entités, arêtes et épisodes ; tests unitaires avec mocks hermétiques passants. |
| 006-2 | Given un `graph_id` distant sous Zep Cloud, when `migrer_zep_vers_graphiti.py` est exécuté, then 100 % des nœuds et arêtes sont extraits, transformés et insérés dans Neo4j local sous `group_id = graph_id` avec leurs métadonnées temporelles ; tests unitaires et d'insertion Cypher passants. |
| 006-3 | Given un graphe migré dans Neo4j local, when `GraphitiGraphStore` et `ZepEntityReader` s'exécutent, then les entités sont lues avec succès et permettent la génération de personas ; `purger_graphes_zep.py` permet la suppression sécurisée et confirmée des données sur Zep Cloud. |

---

## 5. Documents à consulter

| Document | Ce qu'on y prend |
|---|---|
| [`docs/LOCAL-FIRST.md`](../../LOCAL-FIRST.md) | §11 point 3 : question ouverte de la migration des données Zep. |
| [`docs/decisions/0001-remplacement-de-zep-par-graphiti.md`](../../decisions/0001-remplacement-de-zep-par-graphiti.md) | Principes d'isolation et remplacement de Zep. |
| [`backend/app/utils/graph_store/zep_store.py`](../../backend/app/utils/graph_store/zep_store.py) | Structures `GraphNode`, `GraphEdge` et accès Zep Cloud. |
| [`backend/app/utils/graph_store/graphiti_store.py`](../../backend/app/utils/graph_store/graphiti_store.py) | Modèle de données Neo4j Graphiti (`:Entity`, partitionnement `group_id`). |
| [`backend/app/services/zep_entity_reader.py`](../../backend/app/services/zep_entity_reader.py) | Contrat de lecture des entités et typage. |
| [`AGENTS.md`](../../AGENTS.md) | Constitution du dépôt (§2.8, §2.10). |
