# PRD — Epic 006 : Migrer un graphe Zep existant — ou acter qu'on jette (ADR 0001, ADR 0006)

- **Statut** : `backlog` · **Dépend de** : 003, 004, 005 · **Bloque** : aucun
- **Suivi** : [`sprint-status.yaml`](../../sprint-status.yaml)

> Les Epics 001 à 005 ont totalement affranchi MiroFish de la dépendance à Zep Cloud pour les nouvelles exécutions :
> - Graphiti + Neo4j en local assurent la construction du graphe temporel sans aucun crédit Zep (Epic 003).
> - L'application fonctionne de bout en bout en local sans clé `ZEP_API_KEY` (Epic 004).
> - La stack complète (Neo4j, backend, frontend) s'exécute dans un environnement Docker de référence avec volumes persistants (Epic 005).
>
> **L'Epic 006 résout la question des données historiques** (`LOCAL-FIRST.md` §11, point 3) :
> Que fait-on des graphes de connaissances créés sous Zep Cloud lors des utilisations antérieures du projet ?
> Faut-il les rapatrier en local, les archiver, ou acter formellement qu'on les jette au profit d'une ré-ingestion depuis les documents d'origine ?

---

## 1. Le problème

### 1.1 Contexte et état des lieux

Avant la mise en place de la pile locale, toute construction de graphe par MiroFish reposait exclusivement sur le service SaaS Zep Cloud. Les utilisateurs ou équipes ayant déjà exploité MiroFish disposent potentiellement sur leur compte Zep Cloud de graphes partitionnés par `group_id = graph_id` contenant :
- des entités nommées et résumées (`GraphNode`) avec attributs typés (`entity_type`) ;
- des relations sémantiques et faits temporels (`GraphEdge`) horodatés (`valid_at`, `invalid_at`, `expired_at`) ;
- des épisodes textuels sources (`EpisodeRecord`) issus des découpages documentaires.

### 1.2 La rupture et les alternatives

Face à ces données existantes hébergées chez un tiers propriétaire, trois écueils se présentent :

1. **Opacité et absence de diagnostic** :
   - L'utilisateur ignore le volume exact de données hébergées sur son compte Zep Cloud (nombre de graphes orphelins, volume d'entités, arêtes et épisodes).
   - Aucun outil dans le dépôt ne permet d'auditer l'état d'un compte Zep Cloud sans lancer manuellement des scripts complexes ou consommer l'interface web Zep.
2. **Le coût d'une ré-extraction aveugle** :
   - Si un utilisateur a investi du temps et des crédits pour construire un graphe riche et complexe sur Zep Cloud, devoir ré-extraire l'intégralité des documents en local consomme du temps de calcul CPU/GPU et des appels LLM inutiles.
   - Dans le cas où les documents sources d'origine ne sont plus disponibles localement, la perte du graphe Zep Cloud équivaut à la perte définitive des connaissances extraites.
3. **Le coût de conservation inutile sur le cloud** :
   - Si les graphes distants ne sont que des artefacts de test éphémères ou obsolètes, conserver un compte Zep Cloud actif ou risquer de dépasser des quotas gratuits n'a aucun sens économique.
   - En l'absence de script de purge sécurisé, les données restent dormantes sur les serveurs d'un tiers.

---

## 2. L'objectif

Offrir aux utilisateurs une **stratégie outillée, déterministe et mesurée** pour gérer leurs données historiques Zep Cloud :

1. **Outil d'audit et inventaire (`auditer_graphes_zep.py`)** :
   - Inspecter un compte Zep Cloud à partir de `ZEP_API_KEY`.
   - Produire un inventaire consolidé (JSON et tableau Markdown) listant chaque graphe (`graph_id`), son nombre d'entités, d'arêtes, d'épisodes, et sa date de création.
   - Fournir des indicateurs d'aide à la décision (taille, valeur sémantique, présomption de redondance avec les documents locaux).
2. **Arbre de décision formel « Migrer ou Jeter »** :
   - Formaliser un guide d'arbitrage :
     - *Cas 1 (Documents sources présents & modèle local disponible)* : Recommander la ré-ingestion locale propre (0 coût avec `space-bunny-free`).
     - *Cas 2 (Documents sources absents ou graphe validé manuellement)* : Enclencher la migration structurelle directe Zep → Neo4j local.
     - *Cas 3 (Données obsolètes / de test)* : Purger le compte Zep Cloud.
3. **Module de migration ETL direct (`migrer_zep_vers_graphiti.py`)** :
   - Extraire les nœuds et arêtes d'un graphe distant via le SDK Zep (`fetch_all_nodes`, `fetch_all_edges`).
   - Mapper fidèlement les entités et relations vers le schéma de graphe Graphiti / Neo4j (`:Entity`, `group_id = graph_id`, types relationnels, labels et champs temporels).
   - Injecter les données directement dans Neo4j par requêtes Cypher transactionnelles par lots, **sans aucun appel LLM de ré-extraction** (coût marginal = 0 €).
4. **Validation de relecture sans couture** :
   - Garantir que le graphe migré est immédiatement interrogeable par `GraphitiGraphStore` (`get_all_nodes`, `get_all_edges`, `get_graph_data`).
   - S'assurer que `ZepEntityReader` lit les entités migrées et permet à `oasis_profile_generator.py` de générer des personas conformes.
5. **Outil de purge optionnel et sécurisé (`purger_graphes_zep.py`)** :
   - Permettre la suppression explicite et confirmée des graphes migrés ou obsolètes sur Zep Cloud pour clore proprement le compte tiers.

---

## 3. Ce que cet epic n'est pas

| Hors périmètre | Pourquoi |
|---|---|
| Migration inverse (Neo4j local vers Zep Cloud) | MiroFish est désormais local-first ; le cloud n'est pas une cible de destination. |
| Ré-extraction LLM des documents | La migration est un ETL structurel 1:1, elle ne rejoue pas l'extraction de texte. |
| Synchronisation bidirectionnelle temps réel | Le store local remplace définitivement Zep, il n'y a pas de mode hybride synchronisé. |
| Ontologie dynamique v2 | Fait l'objet de l'Epic 007. |

---

## 4. Exigences détaillées

### 4.1 Exigences fonctionnelles (FR)

| Réf. | Intitulé | Description |
|---|---|---|
| **FR-1** | Audit et inventaire Zep Cloud | Un script autonome `auditer_graphes_zep.py` inspecte le compte Zep Cloud et produit un rapport détaillé (graph_id, nœuds, arêtes, épisodes, horodatages). |
| **FR-2** | Extraction paginée résiliente | Extraction de 100 % des entités et relations d'un graphe distant via curseurs de pagination et gestion des retries réseau. |
| **FR-3** | Mapping et transformation neutre | Conversion sans perte des structures Zep (`EntityNode`, `EntityEdge`) vers le modèle Graphiti Neo4j (`:Entity`, labels, propriétés, métadonnées temporelles). |
| **FR-4** | Injection Cypher transactionnelle | Insertion directe dans Neo4j local par lots paramétrables sous isolation étanche `group_id = target_graph_id`. |
| **FR-5** | Relecture applicative immédiate | Le graphe importé est lisible par `GraphitiGraphStore`, `zep_entity_reader.py` et les générateurs de simulation. |
| **FR-6** | Purge distante contrôlée | Un script `purger_graphes_zep.py` avec confirmation interactive ou flag `--yes` supprime les graphes cibles sur Zep Cloud. |

### 4.2 Exigences non fonctionnelles (NFR)

| Réf. | Intitulé | Description |
|---|---|---|
| **NFR-1** | Coût marginal nul (0 €) | Aucune invocation de LLM ni d'embedder externe pendant la migration ; opération purement structurelle (ETL). |
| **NFR-2** | Idempotence et étanchéité | La ré-exécution de la migration sur un même `graph_id` remplace ou fusionne proprement sans doublons ni interférence avec d'autres graphes. |
| **NFR-3** | Préservation intégrale de la temporalité | Les horodatages `valid_at`, `invalid_at`, `expired_at` et `created_at` sont rigoureusement préservés au format ISO 8601 UTC. |
| **NFR-4** | Tests hermétiques | Les outils d'audit et de migration sont testés avec des mocks de Zep Cloud et Neo4j, sans dépendance à une clé ou à une connexion externe en CI. |

---

## 5. Critères de sortie chiffrés (C1 à C5)

| # | Critère | Seuil de succès |
|---|---|---|
| **C1** | Inventaire Zep Cloud fonctionnel | `auditer_graphes_zep.py` extrait l'inventaire complet avec 100 % des métriques requises (JSON et Markdown). |
| **C2** | Fidélité de migration à 100 % | 100 % des nœuds et arêtes d'un graphe Zep source sont restitués dans Neo4j local (0 entité ni relation perdue). |
| **C3** | Préservation de la temporalité | 100 % des arêtes possédant un champ temporel (`valid_at`, `invalid_at`) conservent leur valeur dans Neo4j. |
| **C4** | Intégration métier validée | `GraphitiGraphStore.get_all_nodes(graph_id)` et `zep_entity_reader.py` lisent le graphe migré et produisent les profils OASIS attendus. |
| **C5** | Filet de tests au vert | $\ge 711$ tests existants passants + suite de tests unitaires et d'intégration ETL dédiée (100 % vert). |
