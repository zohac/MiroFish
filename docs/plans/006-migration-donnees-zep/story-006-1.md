---
id: "006-1"
epic: "006"
titre: "Outil d'audit et d'inventaire d'un compte Zep Cloud (auditer_graphes_zep.py)"
statut: in-progress
auteur: agent
format: "2"
---

# Story 006-1 — Outil d'audit et d'inventaire d'un compte Zep Cloud (auditer_graphes_zep.py)

## Définition de prêt

- [x] Objectif compris : concevoir et implémenter un outil autonome d'audit et d'inventaire d'un compte Zep Cloud (`backend/scripts/auditer_graphes_zep.py`), capable de recenser l'ensemble des graphes de connaissances distants (`graph_id`), d'en dénombrer les entités, relations et épisodes, d'analyser la présence des documents sources locaux et de produire une synthèse décisionnelle (console, JSON, Markdown) pour guider l'arbitrage « Migrer ou Jeter » (PRD Epic 006, Critère C1, FR-1).
- [x] Documents consultés : [PRD Epic 006](prd.md) (§1, §2, §4, §5 C1), [Architecture Epic 006](architecture.md) (§1, §2, §3, §4), [Epic 006 Hub](epic-006.md), [`backend/app/utils/zep.py`](../../backend/app/utils/zep.py), [`backend/app/utils/zep_paging.py`](../../backend/app/utils/zep_paging.py), [`backend/app/utils/graph_store/zep_store.py`](../../backend/app/utils/graph_store/zep_store.py), [AGENTS.md](../../AGENTS.md) (§2.1, §2.2, §2.4, §2.8).
- [x] Prérequis techniques vérifiés : client `zep_cloud` et helpers de pagination (`fetch_all_nodes`, `fetch_all_edges`) opérationnels dans `backend/app/utils/`, gestion des erreurs `GraphStoreError` posée lors de l'Epic 002.
- [x] Stratégie de test identifiée : création d'une suite de tests unitaires hermétiques (`backend/tests/test_auditer_graphes_zep.py`) avec mocks du client Zep Cloud (`unittest.mock`), tests de validation des arguments CLI, de parsing JSON, de diagnostic de clé manquante et de génération des recommandations d'arbitrage sans aucun appel réseau réel en CI.

## Définition de fini

- [ ] Script d'audit autonome `backend/scripts/auditer_graphes_zep.py` implémenté avec support CLI complet (`--api-key`, `--output-json`, `--output-report`, `--mock`, `--quiet`).
- [ ] Extraction exhaustive des métriques par graphe : identifiant (`graph_id` / `group_id`), nombre d'entités, nombre de relations, nombre d'épisodes, date de création/mise à jour et détection de documents sources locaux associés dans `backend/uploads/documents/`.
- [ ] Module de recommandation d'arbitrage intégré appliquant l'arbre de décision de l'Epic 006 (« Migrer » si données orphelines, « Jeter / Re-ingérer local » si documents présents, « Purger » si graphes de tests éphémères).
- [ ] Export des résultats sous format JSON normalisé et sous forme de tableau Markdown récapitulatif.
- [ ] Suite de tests unitaires hermétiques (`backend/tests/test_auditer_graphes_zep.py`) couvrant 100 % des branches (mode mock, erreurs d'authentification 401, rate limiting 429, erreurs d'arguments et génération de rapports).
- [ ] Conformité de l'outillage (`ruff check .`, `validate_plans.py`) et préservation du filet de tests ($\ge 711$ tests verts).
- [ ] Revue contradictoire BMad (4 couches) réalisée et consignée.

## Tâches

- [ ] Concevoir l'architecture de la sonde d'audit `backend/scripts/auditer_graphes_zep.py` avec dataclasses typées (`GraphSummary`, `AuditReport`).
- [ ] Implémenter l'extraction des graphes distants via le SDK Zep Cloud et les fonctions de pagination (`fetch_all_nodes`, `fetch_all_edges`, consultation des groupes).
- [ ] Implémenter le mode `--mock` pour simuler des graphes réalistes sans nécessiter de compte Zep Cloud actif.
- [ ] Développer la logique d'analyse heuristique et de recommandation d'arbitrage (« Migrer vs Jeter ») selon la présence des fichiers sources dans `uploads/`.
- [ ] Développer les formateurs de sortie console, JSON et Markdown.
- [ ] Écrire la suite de tests unitaires hermétiques `backend/tests/test_auditer_graphes_zep.py`.
- [ ] Exécuter la suite de tests et vérifier le linting `ruff`.
- [ ] Réaliser la revue contradictoire BMad et appliquer les correctifs nécessaires.
- [ ] Mettre à jour l'état de la story et synchroniser les référentiels.

## Notes de développement

La Story 006-1 concrétise la première étape indispensable du PRD de l'Epic 006 : l'observabilité et le diagnostic d'un compte Zep Cloud existant.
Afin d'éviter tout appel réseau en CI et d'offrir une expérience reproductible sur n'importe quel poste de travail, la sonde `auditer_graphes_zep.py` intègre nativement un mode `--mock` fournissant un jeu de données de test représentatif (graphe avec documents locaux correspondants, graphe orphelin avec documents disparus, et graphe de test éphémère).
La sonde n'affiche jamais la clé API dans ses logs ou sorties console (respect de la règle d'or AGENTS.md §2.4).
L'arbitrage intègre la détection automatique des documents dans `backend/uploads/documents/` : si un document de même nom ou hash est présent localement, la ré-ingestion locale propre (0 € via `space-bunny-free`) est recommandée en priorité plutôt qu'un ETL complexe.

## Revue

La revue contradictoire BMad sera consignée ici à l'issue de l'implémentation :
- **Couche Contrat & Architecture** : vérification de la conformité au PRD Epic 006 et de l'intégration Clean Architecture.
- **Couche Hermétisme & Sécurité** : vérification de l'absence totale de fuite de secrets (`ZEP_API_KEY`) et de l'étanchéité des tests sans réseau.
- **Couche Tests & Qualité** : vérification de la couverture des tests unitaires et de la robustesse face aux erreurs API (401, 404, 429).
- **Couche Robustesse & CI** : validation des codes retour CLI (0 en succès, 1 sur erreur) et conformité `ruff`.

## Notes de complétion

À renseigner lors de la clôture de la story après implémentation, passage des tests et revue BMad.
