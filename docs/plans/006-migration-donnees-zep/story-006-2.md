---
id: "006-2"
epic: "006"
titre: "Pipeline ETL de transformation et injection directe Cypher dans Neo4j (migrer_zep_vers_graphiti.py)"
statut: in-progress
auteur: agent
format: "2"
---

# Story 006-2 — Pipeline ETL de transformation et injection directe Cypher dans Neo4j (migrer_zep_vers_graphiti.py)

## Définition de prêt

- [x] Objectif compris : concevoir et implémenter un pipeline ETL autonome de migration de données (`backend/scripts/migrer_zep_vers_graphiti.py`), capable d'extraire l'intégralité des nœuds et arêtes d'un graphe distant hébergé sur Zep Cloud (`graph_id`), de les transformer fidèlement vers le schéma Neo4j compatible Graphiti (:Entity, group_id = graph_id, préservation des labels, attributs et horodatages temporels ISO 8601 UTC) et de les injecter directement dans la base Neo4j locale par requêtes Cypher transactionnelles par lots (UNWIND), sans aucun appel LLM ni coût marginal (0 €) (PRD Epic 006, Critères C2, C3, FR-2, FR-3, FR-4, NFR-1, NFR-2, NFR-3).
- [x] Documents consultés : [PRD Epic 006](prd.md) (§1, §2, §4, §5 C2, C3), [Architecture Epic 006](architecture.md) (§1, §2, §3, §3.1, §4, §5, §6), [Epic 006 Hub](epic-006.md), [`backend/app/utils/zep.py`](../../backend/app/utils/zep.py), [`backend/app/utils/zep_paging.py`](../../backend/app/utils/zep_paging.py), [`backend/app/utils/graph_store/graphiti_store.py`](../../backend/app/utils/graph_store/graphiti_store.py), [ADR 0001](../../decisions/0001-interface-graph-store.md), [ADR 0006](../../decisions/0006-docker-first.md), [AGENTS.md](../../AGENTS.md) (§2.1, §2.2, §2.4, §2.8, §2.9).
- [x] Prérequis techniques vérifiés : client `zep_cloud` et pagination par curseurs (`fetch_all_nodes`, `fetch_all_edges`) opérationnels dans `backend/app/utils/zep_paging.py`, driver `neo4j` Python opérationnel et testé (Epic 001, ADR 0010), instance Neo4j locale de référence disponible sous Docker (`bolt://neo4j:7687` ou `bolt://localhost:7687`), schéma `:Entity {uuid, group_id}` validé lors des Epics 003, 004 et 005.
- [x] Stratégie de test identifiée : création d'une suite de tests unitaires hermétiques (`backend/tests/test_migrer_zep_vers_graphiti.py`) avec mocks du client Zep Cloud et du driver Neo4j (`unittest.mock`), tests de validation du mapping de schéma, de la normalisation temporelle ISO 8601 UTC, des requêtes Cypher `UNWIND`, du découpage par lots, de l'idempotence, des erreurs de connexion, de l'absence de fuite de secrets et du mode `--mock` sans dépendance réseau en CI.

## Définition de fini

- [ ] Script ETL autonome `backend/scripts/migrer_zep_vers_graphiti.py` implémenté avec CLI complète (`--graph-id`, `--api-key`, `--neo4j-uri`, `--neo4j-user`, `--neo4j-password`, `--batch-size`, `--mock`, `--output-report`, `--quiet`).
- [ ] Module de transformation (`ZepToGraphitiTransformer`) assurant la conversion sans perte des structures Zep vers les dictionnaires Cypher Neo4j :
  - Nœuds : label `:Entity`, propriété `group_id = target_graph_id`, conservation de `uuid`, `name`, `summary`, `created_at`, et injection des attributs avec préservation de `entity_type`.
  - Relations : type `RELATES_TO`, conservation de `uuid`, `source_node_uuid`, `target_node_uuid`, `name`, `fact`, `fact_type`, `created_at`, et injection des attributs.
- [ ] Préservation rigoureuse de la temporalité : normalisation et validation des champs `valid_at`, `invalid_at`, `expired_at` au format ISO 8601 UTC (`YYYY-MM-DDTHH:MM:SSZ`), satisfaisant à 100 % le critère C3 du PRD.
- [ ] Module d'injection transactionnelle directe dans Neo4j (`Neo4jDirectLoader`) exécutant des requêtes Cypher `UNWIND` par lots paramétrables (`--batch-size`, défaut 100) sous isolation étanche `group_id = target_graph_id` garantissant l'idempotence (`MERGE`) (critère C2, NFR-2).
- [ ] Opération d'ETL à coût marginal nul (0 €) : 0 requête LLM, 0 appel à un embedder distant ou local pendant toute la migration (NFR-1).
- [ ] Mode `--mock` hors-ligne déterministe simulant l'extraction et l'injection d'un graphe représentatif sans nécessiter de compte Zep actif ni d'instance Neo4j en ligne.
- [ ] Émission d'un compte-rendu de migration structuré (nombre de nœuds extraits/injectés, nombre d'arêtes extraites/injectées, durée, taux de fidélité, export optionnel JSON/Markdown).
- [ ] Suite de tests unitaires hermétiques (`backend/tests/test_migrer_zep_vers_graphiti.py`) couvrant 100 % des branches (mode mock, mapping nœuds/arêtes, normalisation temporelle, requêtes Cypher `UNWIND`, erreurs réseau, CLI).
- [ ] Conformité de l'outillage (`ruff check .`, `validate_plans.py`) et préservation du filet de tests ($\ge 734$ tests verts).
- [ ] Revue contradictoire BMad (4 couches) réalisée et consignée.

## Tâches

- [ ] Concevoir l'architecture modulaire du script `backend/scripts/migrer_zep_vers_graphiti.py` avec dataclasses typées (`ZepNodeDTO`, `ZepEdgeDTO`, `MigrationResult`, `MigrationReport`).
- [ ] Implémenter le module de transformation `ZepToGraphitiTransformer` (mapping schéma Graphiti, conversion de types, normalisation ISO 8601 UTC des timestamps).
- [ ] Implémenter le chargeur direct Neo4j `Neo4jDirectLoader` exécutant les requêtes Cypher transactionnelles `UNWIND` par lots de nœuds et d'arêtes.
- [ ] Implémenter le mode `--mock` hors-ligne générant un jeu de test complet et validant le flux ETL sans dépendance externe.
- [ ] Implémenter la CLI complète avec gestion des arguments, lecture sécurisée des variables d'environnement (`ZEP_API_KEY`, `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`) et reporting d'exécution.
- [ ] Écrire la suite de tests unitaires hermétiques `backend/tests/test_migrer_zep_vers_graphiti.py`.
- [ ] Exécuter la suite de tests et vérifier la propreté du code via `ruff check .`.
- [ ] Réaliser la revue contradictoire BMad (4 couches) et appliquer les correctifs.
- [ ] Mettre à jour l'état de la story et synchroniser les référentiels.

## Notes de développement

La Story 006-2 constitue le cœur technique de l'Epic 006 : le rapatriement structurel (ETL direct) des données hébergées sur Zep Cloud vers l'instance locale Neo4j, sans nécessiter de ré-ingestion coûteuse par LLM.
Points d'attention d'architecture et de conception :
1. **Coût marginal nul (0 €)** : Le pipeline n'appelle ni OpenAI, ni OpenCode Go, ni SentenceTransformerEmbedder. Il transfère les faits sémantiques et entités déjà extraits dans Zep directement sous forme de nœuds et relations Neo4j.
2. **Compatibilité GraphitiGraphStore** : Pour que le graphe migré soit immédiatement interrogeable par l'application locale (Story 006-3), les nœuds doivent porter le label `:Entity` et la propriété `group_id = target_graph_id`, et les arêtes le type `RELATES_TO` avec la propriété `fact`.
3. **Temporalité native** : Zep stocke `valid_at` et `invalid_at`. La transformation doit rigoureusement normaliser ces dates en chaînes ISO 8601 UTC afin que les filtres temporels de `GraphitiGraphStore` continuent de fonctionner à l'identique.
4. **Idempotence Cypher** : L'utilisation de `MERGE (n:Entity {uuid: row.uuid, group_id: $group_id})` et `MERGE (source)-[r:RELATES_TO {uuid: row.uuid}]->(target)` garantit qu'une migration interrompue ou rejouée ne crée aucun doublon.
5. **Hermétisme et sécurité** : Aucun secret (`ZEP_API_KEY`, `NEO4J_PASSWORD`) ne doit fuiter dans les logs, traces d'erreurs ou sorties écran. Le mode `--mock` permet à la CI et aux développeurs hors-ligne d'exécuter et vérifier le pipeline sans infrastructure tierce.

## Revue

La revue contradictoire BMad sera consignée ici à l'issue de l'implémentation :
- **Couche Contrat & Architecture** : vérification de la conformité aux exigences fonctionnelles FR-2, FR-3, FR-4 et aux critères C2 et C3 du PRD Epic 006.
- **Couche Hermétisme & Sécurité** : vérification de l'étanchéité des tests sans appel réseau ni Neo4j réel, et absence de fuite de mots de passe ou clés API.
- **Couche Tests & Qualité** : vérification de la couverture unitaire des branches de transformation, des cas limites (timestamps nuls, attributs vides) et du chargeur transactionnel.
- **Couche Robustesse & CI** : validation des codes retours (0 en succès, 1 sur erreur), du partitionnement multi-tenant et de la conformité `ruff`.

## Notes de complétion

À renseigner lors de la clôture de la story après implémentation, passage des tests et revue BMad.
