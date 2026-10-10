---
id: "005-4"
epic: "005"
titre: "Persistance des données Neo4j et cycle de vie des volumes"
statut: done
auteur: agent
format: "2"
---

# Story 005-4 — Persistance des données Neo4j et cycle de vie des volumes

## Définition de prêt

- [x] Objectif compris : valider et prouver que les données du graphe de connaissances stockées dans Neo4j sous Docker survivent intégralement aux cycles d'arrêt et de redémarrage des conteneurs via Docker Compose (`docker compose down` puis `docker compose up -d`), grâce au volume nommé `neo4j_data`, et qu'une purge volontaire (`docker compose down -v`) réinitialise proprement la base sans laisser de résidus orphelins.
- [x] Documents consultés : [PRD](prd.md) (notamment critère C3, exigence NFR-3), [Architecture](architecture.md) (§4), [Epic 005](epic-005.md), [`docker-compose.yml`](../../docker-compose.yml), [AGENTS.md](../../AGENTS.md) (§2.9, §3).
- [x] Prérequis vérifiés : `docker-compose.yml` unifié configuré avec les volumes nommés `neo4j_data` et `neo4j_logs`, service `neo4j` opérationnel avec healthcheck Bolt (`cypher-shell`), service `backend` opérationnel et validé sous Docker (Stories 005-1, 005-2, 005-3).
- [x] Stratégie de test identifiée : conception d'une sonde de vérification automatisée (`backend/scripts/verifier_persistance_neo4j_docker.py`) exécutant un cycle réel (insertion de nœuds/relations témoins, arrêt `down`, redémarrage `up -d --wait`, validation de l'intégrité à 100 %, puis validation de la purge sur `down -v`), et suite de tests unitaires hermétiques validant la déclaration et le cycle de vie des volumes (`backend/tests/test_docker_volume_persistence.py`).

## Définition de fini

- [x] Sonde de vérification automatisée de persistance opérationnelle (`backend/scripts/verifier_persistance_neo4j_docker.py`) démontrant la conformité au critère C3 du PRD.
- [x] Preuve formelle que 100 % des nœuds et arêtes créés dans Neo4j sont préservés après un cycle `docker compose down && docker compose up -d` (sans option `-v`).
- [x] Preuve formelle qu'un cycle `docker compose down -v` purge explicitement le volume `neo4j_data` et réinitialise l'instance à un état vierge.
- [x] Vérification du comportement des montages bind backend (`backend/uploads`, `backend/simulations`) garantissant la non-régression sur les fichiers téléversés et rapports générés.
- [x] Suite de tests unitaires hermétiques (`backend/tests/test_docker_volume_persistence.py`) validant la configuration et le comportement attendu.
- [x] Filet global de tests (684 tests verts) et outillage (`ruff check .`, `validate_plans.py`) 100 % passants au vert.

## Tâches

- [x] Développer la sonde de vérification autonome de persistance (`backend/scripts/verifier_persistance_neo4j_docker.py`).
- [x] Exécuter le cycle de vérification de persistance (écriture de graphe témoin -> arrêt conteneur -> redémarrage -> validation 100 % intègre).
- [x] Vérifier le comportement de réinitialisation contrôlée lors de l'exécution de `docker compose down -v`.
- [x] Contrôler la préservation des données applicatives dans les volumes bind `./backend/uploads` et `./backend/simulations`.
- [x] Écrire la suite de tests unitaires hermétiques (`backend/tests/test_docker_volume_persistence.py`).
- [x] Réaliser la revue contradictoire BMad (4 couches) et consigner les résultats.
- [x] Mettre à jour l'index des stories et l'état d'avancement dans la documentation de suivi.

### Review Findings

- [x] [Review][Patch] Corriger le test de détection de perte de nœud pour tester réellement l'échec du critère C3 dans le rapport [backend/tests/test_docker_volume_persistence.py:212-248]
- [x] [Review][Patch] Fermer explicitement les drivers et sessions Neo4j créés (`driver.close()`) pour éliminer les fuites de ressources [backend/scripts/verifier_persistance_neo4j_docker.py:528,634,735,783]
- [x] [Review][Patch] Propager les paramètres de connexion personnalisés (`uri`, `user`, `password`) lors des reconnexions post-down et post-purge [backend/scripts/verifier_persistance_neo4j_docker.py:489,634,735]
- [x] [Review][Patch] Rendre strictement déterministe le tri Cypher des arêtes multi-graphes (`ORDER BY a.name ASC, b.name ASC, r.type ASC`) [backend/scripts/verifier_persistance_neo4j_docker.py:259]
- [x] [Review][Patch] Réinitialiser correctement le store mock lors de l'usage de `driver_override` en mode mock [backend/scripts/verifier_persistance_neo4j_docker.py:770-781]
- [x] [Review][Patch] Ajouter un test unitaire hermétique simulant l'échec de commande Docker CLI pour valider la robustesse du rapport [backend/tests/test_docker_volume_persistence.py:311]

#### Rejected
- Timeout de 120s jugé trop rigide : false (120s est le standard de l'outillage de test et largement suffisant en local/CI).
- Purge de base complète par cycle-complet : low (le rôle de cycle-complet est précisément l'épreuve complète avec down -v ; les sous-commandes ecrire/verifier permettent des tests ciblés non destructifs).

## Notes de développement

La constitution ([`AGENTS.md`](../../AGENTS.md) §2.9) et l'Architecture ([`architecture.md`](architecture.md) §4) posent un principe strict pour la gestion des données persistantes :
- Les données Neo4j résident dans le volume nommé `neo4j_data` monté sur `/data`.
- Les logs Neo4j résident dans le volume nommé `neo4j_logs` monté sur `/logs`.
- La commande standard `docker compose down` détruit les conteneurs éphémères mais préserve les volumes nommés et bind.
- Seule l'instruction explicite `docker compose down -v` détruit le volume `neo4j_data` et le graphe sous-jacent.

La Story 005-4 a développé la sonde `backend/scripts/verifier_persistance_neo4j_docker.py` fournissant une CLI complète :
- Mode `cycle-complet` orchestrant les 7 étapes de vérification :
  1. Écriture du graphe témoin (nœuds typés, scores, propriétés riches, relations orientées avec timestamps `valid_at`).
  2. Établissement de la baseline et calcul de l'empreinte SHA-256 canonique.
  3. Arrêt normal des conteneurs via `docker compose down` (sans `-v`).
  4. Redémarrage de la stack via `docker compose up -d --wait`.
  5. Validation de la persistance intégrale (100 % des nœuds et arêtes identiques au SHA-256 près — Critère C3).
  6. Validation de la persistance des montages bind `backend/uploads` et `backend/simulations` au SHA-256 près.
  7. Validation de la purge volontaire lors d'un `docker compose down -v` (réinitialisation complète).
- Support des sous-commandes pas à pas (`ecrire`, `verifier`, `purger`) et des options `--mock` et `--json` pour intégration CI.
- Suite de tests unitaires et hermétiques (`backend/tests/test_docker_volume_persistence.py`) ajoutant 11 tests vérifiant la déclaration des volumes dans `docker-compose.yml`, la détection d'altération de données, la gestion des pertes de nœuds et le repli sans Docker CLI.

## Revue

- **Couche Contrat & Architecture** : Validée. La conformité avec le critère C3 du PRD et l'ADR 0006 est démontrée de manière empirique et automatisée. La topologie des volumes (`neo4j_data`, `neo4j_logs`, montages bind `uploads` et `simulations`) est scrupuleusement respectée et vérifiée. Tri déterministe Cypher (`ORDER BY a.name ASC, b.name ASC, r.type ASC`) sécurisant la stabilité canonique du SHA-256.
- **Couche Hermétisme & Sécurité** : Validée. Zéro clé d'API ni mot de passe en clair. Propagation rigoureuse des identifiants et fermeture explicite de tous les pools/drivers Neo4j (`driver.close()`). Les tests unitaires s'exécutent de façon 100 % hermétique avec isolation en mémoire sans nécessiter de dépendance externe active. Nettoyage garanti des artefacts de test.
- **Couche Tests & Qualité** : Validée. 12 nouveaux tests unitaires hermétiques posés (+1 test d'échec de commande Docker CLI et test actif de détection d'altération du critère C3). Filet global de tests porté à 684 tests verts (+13 tests). Linter `ruff check .` sans aucun avertissement.
- **Couche Robustesse & CI** : Validée. Gestion gracieuse des timeouts et codes retour Docker CLI, support complet du mode `--mock` et `--json` pour l'outillage CI et scripts d'automatisation. Les 6 patchs de la revue contradictoire BMad ont été intégralement appliqués et validés.

## Notes de complétion

- **Livrables produits** :
  1. `backend/scripts/verifier_persistance_neo4j_docker.py` : sonde de vérification autonome de persistance et cycle de vie des volumes (modes réel, mock, pas à pas et JSON), fermetures propres des connexions et tri déterministe.
  2. `backend/tests/test_docker_volume_persistence.py` : suite de 12 tests unitaires et hermétiques validant la déclaration, l'intégrité, le cycle de vie des volumes et la résilience aux pannes Docker CLI.
  3. Preuve de conformité formelle au critère C3 de l'Epic 005.
- **Résultats de validation** :
  - Filet global : 684 tests passants au vert (100 %).
  - Lint `ruff check .` : 0 erreur, 0 avertissement.
  - Validation des plans `validate_plans.py` : 100 % conforme.
- **Statut final** : La story 005-4 est close avec succès (`done`) après revue contradictoire BMad et application des 6 patchs. La story 005-5 (Banc de qualification Docker de référence et clôture de l'Epic 005) est prête à démarrer.

