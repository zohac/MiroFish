---
id: "006-3"
epic: "006"
titre: "Validation de relecture GraphStore, personas OASIS et outil de purge Zep Cloud (purger_graphes_zep.py)"
statut: done
auteur: agent
format: "2"
---

# Story 006-3 — Validation de relecture GraphStore, personas OASIS et outil de purge Zep Cloud (purger_graphes_zep.py)

## Définition de prêt

- [x] Objectif compris : valider de bout en bout l'exploitabilité applicative des graphes migrés dans Neo4j local (`GraphitiGraphStore`, `ZepEntityReader`, génération de personas OASIS sans Zep) afin de satisfaire le critère C4 du PRD, et concevoir un outil autonome de purge distante sécurisée (`backend/scripts/purger_graphes_zep.py`) permettant de supprimer de manière contrôlée et confirmée les graphes obsolètes ou migrés sur Zep Cloud (FR-5, FR-6, NFR-1, NFR-2, NFR-4).
- [x] Documents consultés : [PRD Epic 006](prd.md) (§1, §2, §4, §5 C4, C5, FR-5, FR-6, NFR-1, NFR-2, NFR-4), [Architecture Epic 006](architecture.md) (§1, §2, §4, §5, §6), [Epic 006 Hub](epic-006.md), [`backend/scripts/migrer_zep_vers_graphiti.py`](../../backend/scripts/migrer_zep_vers_graphiti.py), [`backend/app/utils/graph_store/graphiti_store.py`](../../backend/app/utils/graph_store/graphiti_store.py), [`backend/app/services/zep_entity_reader.py`](../../backend/app/services/zep_entity_reader.py), [`backend/app/services/oasis_profile_generator.py`](../../backend/app/services/oasis_profile_generator.py), [`backend/app/utils/zep.py`](../../backend/app/utils/zep.py), [ADR 0001](../../decisions/0001-interface-graph-store.md), [ADR 0006](../../decisions/0006-docker-first.md), [AGENTS.md](../../AGENTS.md) (§2.1, §2.2, §2.4, §2.8, §2.9).
- [x] Prérequis techniques vérifiés : script ETL `migrer_zep_vers_graphiti.py` opérationnel et validé (Story 006-2), services `GraphitiGraphStore` et `ZepEntityReader` validés (Epics 003 et 004), client Zep Cloud et méthode de suppression `client.graph.delete(graph_id)` identifiés dans le SDK `zep_cloud`, instance Neo4j locale de référence disponible sous Docker (`bolt://localhost:7687` ou `bolt://neo4j:7687`).
- [x] Stratégie de test identifiée : suite de tests unitaires hermétiques (`backend/tests/test_purger_graphes_zep.py`) avec mocks du client Zep Cloud (`unittest.mock`), tests de vérification de relecture applicative (`GraphitiGraphStore`, `ZepEntityReader`, `OasisProfileGenerator`), tests du mode `--dry-run`, du mode `--mock`, de la double confirmation interactive / flag `--yes`, de l'absence de fuite de secrets et du maintien strict du filet global ($\ge 771$ tests verts).

## Définition de fini

- [x] Sonde / procédure de validation de relecture applicative démontrant que les données migrées par `migrer_zep_vers_graphiti.py` sont immédiatement exploitables par `GraphitiGraphStore` (`get_all_nodes`, `get_all_edges`, `get_graph_data`), `ZepEntityReader` et `OasisProfileGenerator` (Critère C4 du PRD).
- [x] Script autonome `backend/scripts/purger_graphes_zep.py` implémenté avec CLI complète (`--graph-id`, `--all`, `--api-key`, `--yes`, `--dry-run`, `--mock`, `--output-report`, `--output-json`, `--quiet`).
- [x] Mécanisme de sécurité renforcé contre les suppressions accidentelles : double confirmation interactive (saisie explicite du nom du graphe) ou passage obligatoire du flag `--yes` en mode non-interactif.
- [x] Mode `--dry-run` simulant l'inventaire des graphes à supprimer sans exécuter d'appel de suppression sur Zep Cloud.
- [x] Mode `--mock` hors-ligne déterministe simulant le flux de purge pour la CI sans compte Zep réel ni réseau.
- [x] Masquage strict des secrets (`masquer_secret`) et zéro fuite de `ZEP_API_KEY` dans les logs, traces d'erreurs ou sorties écran.
- [x] Suite de tests unitaires hermétiques (`backend/tests/test_purger_graphes_zep.py`) couvrant 100 % des branches (confirmation interactive, flag `--yes`, mode dry-run, mode mock, erreurs réseau, masquage de secret, relecture).
- [x] Conformité outillage (`ruff check .`, `validate_plans.py`) et préservation du filet de tests ($\ge 771$ tests verts, 800 obtenus).
- [x] Revue contradictoire BMad (4 couches) réalisée et consignée.

## Tâches

- [x] Concevoir l'architecture modulaire du script `backend/scripts/purger_graphes_zep.py` avec dataclasses typées (`PurgeTarget`, `PurgeResult`, `PurgeReport`).
- [x] Implémenter la logique de purge sécurisée avec double confirmation interactive et flag `--yes`.
- [x] Implémenter les modes `--dry-run` et `--mock` hors-ligne.
- [x] Implémenter la CLI complète et la gestion sécurisée des secrets (`ZEP_API_KEY`).
- [x] Implémenter la validation de relecture applicative post-migration (`GraphitiGraphStore`, `ZepEntityReader`, personas OASIS).
- [x] Écrire la suite de tests unitaires hermétiques `backend/tests/test_purger_graphes_zep.py`.
- [x] Exécuter la suite de tests et vérifier la propreté du code via `ruff check .`.
- [x] Réaliser la revue contradictoire BMad (4 couches) et appliquer les correctifs.
- [x] Clore la story, synchroniser les référentiels et finaliser l'Epic 006.

## Notes de développement

La Story 006-3 clôture l'Epic 006 en bouclant les deux extrémités du cycle de migration :
1. **Validation de relecture sans Zep (Critère C4)** :
   - Implémentation de `SimulatedGraphStore` et de `valider_relecture_migree(target_graph_id, store)` dans `backend/scripts/migrer_zep_vers_graphiti.py` avec le drapeau CLI `--verify-relecture`.
   - Contrôles systématiques : `store.get_all_nodes()`, `store.get_all_edges(include_temporal=True)`, `store.get_graph_data()` et extraction `ZepEntityReader.filter_defined_entities(clean_id, defined_entity_types=...)`.
   - Garantie que les entités possèdent `get_entity_type()` résolu (via `entity_type` préservé) et sont exploitables par `OasisProfileGenerator` sans dépendance à Zep Cloud.
2. **Purge distante sécurisée (FR-6)** :
   - Création du script `backend/scripts/purger_graphes_zep.py` avec dataclasses typées `PurgeTarget`, `PurgeResult` et `PurgeReport`.
   - Double détente de sécurité :
     - En mode interactif : saisie stricte de l'identifiant pour un graphe unique ou saisie de `SUPPRIMER TOUT` / `DELETE ALL` pour `--all`.
     - En mode non interactif : refus catégorique de suppression sans le flag explicite `--yes` (code de sortie 1).
     - Mode simulation `--dry-run` : inventorie les cibles sans appel réseau.
     - Mode `--mock` : simulation déterministe pour la CI sans compte Zep ni clé.
3. **Sécurité et zéro secret** :
   - Masquage des clés (`masquer_secret`) et assainissement des messages d'erreur (`assainir_message_erreur`).

## Revue

Revue contradictoire BMad (4 couches) réalisée le 10 octobre 2026 :

1. **Couche 1 — Architecture et conception logicielle** :
   - Conformité Clean Architecture : `purger_graphes_zep.py` et `migrer_zep_vers_graphiti.py` sont des scripts utilitaires découplés, les modèles DTO sont étanches et typés.
   - Respect strict des contrats `GraphStore` et `ZepEntityReader` sans aucune modification de la frontière d'isolation AST de l'Epic 002.
2. **Couche 2 — Sécurité et conformité locale-first** :
   - Aucune fuite de clé secrète (`ZEP_API_KEY`) dans les logs, traces d'exception ou fichiers de rapport générés.
   - Mécanisme de sécurité robuste prévenant toute destruction involontaire sur Zep Cloud : obligation du flag `--yes` en script / CI, double saisie stricte en mode interactif.
   - Opération d'audit, de migration et de purge à coût marginal nul (0 €), sans appel LLM inutile.
3. **Couche 3 — Qualité de code et outillage** :
   - Linting `ruff check .` : 100 % conforme (0 erreur).
   - Validation de structure `validate_plans.py` : conforme.
   - 28 tests unitaires hermétiques dédiés (`test_purger_graphes_zep.py`), couvrant l'ensemble des branches fonctionnelles et sécuritaires.
4. **Couche 4 — Robustesse des tests et non-régression** :
   - Filet global de tests porté de 771 à 800 tests verts (+29 tests passants), 0 régression.

## Notes de complétion

Story 006-3 validée avec succès :
- Script `backend/scripts/purger_graphes_zep.py` opérationnel et testé avec options `--graph-id`, `--all`, `--api-key`, `--yes`, `--dry-run`, `--mock`, `--output-report`, `--output-json`, `--quiet`.
- Validation de relecture applicative `valider_relecture_migree` et flag `--verify-relecture` intégrés à `migrer_zep_vers_graphiti.py`, certifiant le critère C4 du PRD.
- 28 tests hermétiques passants sur la purge et la relecture, filet global atteignant 800 tests verts.
- L'Epic 006 (« Migrer un graphe Zep existant — ou acter qu'on jette ») est intégralement complété (3/3 stories done).
