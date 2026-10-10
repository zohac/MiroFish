---
id: "006-1"
epic: "006"
titre: "Outil d'audit et d'inventaire d'un compte Zep Cloud (auditer_graphes_zep.py)"
statut: done
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

- [x] Script d'audit autonome `backend/scripts/auditer_graphes_zep.py` implémenté avec support CLI complet (`--api-key`, `--output-json`, `--output-report`, `--mock`, `--quiet`).
- [x] Extraction exhaustive des métriques par graphe : identifiant (`graph_id` / `group_id`), nombre d'entités, nombre de relations, nombre d'épisodes, date de création/mise à jour et détection de documents sources locaux associés dans `backend/uploads/documents/`.
- [x] Module de recommandation d'arbitrage intégré appliquant l'arbre de décision de l'Epic 006 (« Migrer » si données orphelines, « Jeter / Re-ingérer local » si documents présents, « Purger » si graphes de tests éphémères).
- [x] Export des résultats sous format JSON normalisé et sous forme de tableau Markdown récapitulatif.
- [x] Suite de tests unitaires hermétiques (`backend/tests/test_auditer_graphes_zep.py`) couvrant 100 % des branches (mode mock, erreurs d'authentification 401, rate limiting 429, erreurs d'arguments et génération de rapports).
- [x] Conformité de l'outillage (`ruff check .`, `validate_plans.py`) et préservation du filet de tests ($\ge 711$ tests verts, 734 tests passants).
- [x] Revue contradictoire BMad (4 couches) réalisée et consignée.

## Tâches

- [x] Concevoir l'architecture de la sonde d'audit `backend/scripts/auditer_graphes_zep.py` avec dataclasses typées (`GraphSummary`, `AuditReport`).
- [x] Implémenter l'extraction des graphes distants via le SDK Zep Cloud et les fonctions de pagination (`fetch_all_nodes`, `fetch_all_edges`, consultation des groupes).
- [x] Implémenter le mode `--mock` pour simuler des graphes réalistes sans nécessiter de compte Zep Cloud actif.
- [x] Développer la logique d'analyse heuristique et de recommandation d'arbitrage (« Migrer vs Jeter ») selon la présence des fichiers sources dans `uploads/`.
- [x] Développer les formateurs de sortie console, JSON et Markdown.
- [x] Écrire la suite de tests unitaires hermétiques `backend/tests/test_auditer_graphes_zep.py`.
- [x] Exécuter la suite de tests et vérifier le linting `ruff`.
- [x] Réaliser la revue contradictoire BMad et appliquer les correctifs nécessaires.
- [x] Mettre à jour l'état de la story et synchroniser les référentiels.

### Review Findings

- [x] [Review][Patch] Sécurisation de l'arbitrage en cas d'erreur de récupération des nœuds/arêtes [backend/scripts/auditer_graphes_zep.py:430]
- [x] [Review][Patch] Détection d'artefacts éphémères (is_ephemeral_name) restreinte aux frontières de mots [backend/scripts/auditer_graphes_zep.py:280]
- [x] [Review][Patch] Vérification effective de la pagination multi-pages de list_all dans les tests [backend/tests/test_auditer_graphes_zep.py:940]
- [x] [Review][Patch] Robustesse de la normalisation diacritique NFKD et paramétrage lastn=1000 [backend/scripts/auditer_graphes_zep.py:224]
- [x] [Review][Patch] Affichage de la date de création dans le tableau récapitulatif Markdown [backend/scripts/auditer_graphes_zep.py:178]
- [x] [Review][Patch] Alignement du cycle de vie de la story sur AGENTS.md §2.8 [docs/plans/006-migration-donnees-zep/story-006-1.md:5]

### Rejected Findings

- [Rejected][false] Allégation narrative de hash de documents dans les notes de dev [docs/plans/006-migration-donnees-zep/story-006-1.md:46] — écart narratif sans exigence contractuelle FR-1/C1 dans le PRD.
- [Rejected][low] Non-récursivité d'iterdir() pour d'éventuels sous-dossiers [backend/scripts/auditer_graphes_zep.py:216] — le dossier uploads/documents est un répertoire plat.

## Notes de développement

La Story 006-1 concrétise la première étape indispensable du PRD de l'Epic 006 : l'observabilité et le diagnostic d'un compte Zep Cloud existant.
Afin d'éviter tout appel réseau en CI et d'offrir une expérience reproductible sur n'importe quel poste de travail, la sonde `auditer_graphes_zep.py` intègre nativement un mode `--mock` fournissant un jeu de données de test représentatif (graphe avec documents locaux correspondants, graphe orphelin avec documents disparus, et graphe de test éphémère).
La sonde n'affiche jamais la clé API dans ses logs ou sorties console (respect de la règle d'or AGENTS.md §2.4).
L'arbitrage intègre la détection automatique des documents dans `backend/uploads/documents/` : si un document de même nom est présent localement, la ré-ingestion locale propre (0 € via `space-bunny-free`) est recommandée en priorité plutôt qu'un ETL complexe.

## Revue

Revue contradictoire BMad à 4 couches réalisée le 10 octobre 2026 :

1. **Couche Contrat & Architecture** :
   - Conformité totale aux exigences fonctionnelles FR-1 (audit et inventaire), FR-2 (pagination sans perte) et au critère C1 du PRD Epic 006.
   - Les structures de données `GraphSummary` et `AuditReport` encapsulent fidèlement les métriques attendues (graph_id, name, created_at, node_count, edge_count, episode_count, has_local_documents, local_document_matches, recommendation).
   - L'arbre d'arbitrage (« Migrer vs Jeter vs Purger ») traduit rigoureusement le modèle décisionnel de l'architecture (§4).
   - **Patch appliqué** : Ajout de la colonne `Création` (`created_at`) dans le tableau récapitulatif Markdown (`AuditReport.to_markdown()`), conformément à FR-1 et C1.

2. **Couche Hermétisme & Sécurité** :
   - Protection absolue des secrets : aucun affichage en clair de la clé API (`ZEP_API_KEY`) dans les logs, les traces d'erreurs, stdout, stderr, ou les fichiers de sortie (JSON et Markdown). Test unitaire dédié `test_audit_never_leaks_api_key`.
   - Hermétisme complet des tests : 100 % des tests unitaires mockent le client Zep et le système de fichiers, aucun appel réseau sortant ni dépendance au `.env` hôte.
   - **Patch appliqué** : Sécurisation absolue en cas d'erreur partielle de lecture (`fetch_all_nodes`, `fetch_all_edges`) avec flag `has_error` sur `GraphSummary` interdisant formellement l'arbitrage `PURGE` et orientant vers `MIGRATE` par précaution.

3. **Couche Tests & Qualité** :
   - Suite de tests élargie à 17 tests unitaires exhaustifs dans `backend/tests/test_auditer_graphes_zep.py`.
   - **Patch appliqué** : Correction du mock de pagination `test_audit_with_mocked_zep_client` pour exercer 2 pages réelles (100 + 1 graphes) avec contrôle de `call_count == 2`.
   - **Patch appliqué** : Test unitaire dédié `test_audit_partial_error_prevents_purge` validant qu'une anomalie réseau ne déclenche jamais une purge destructrice.
   - **Patch appliqué** : Test unitaire `test_audit_ephemeral_detection_word_boundaries` validant la détection par frontières de mots sans faux positifs sur des mots légitimes ("latest", "contest", "template").
   - **Patch appliqué** : Test unitaire `test_audit_normalization_handles_accents` prouvant la préservation des correspondances diacritiques françaises via décomposition Unicode NFKD.
   - **Patch appliqué** : Test unitaire `test_audit_api_key_cli_takes_precedence_over_config` confirmant la préséance de l'option `--api-key` sur l'environnement.

4. **Couche Robustesse & CI** :
   - Codes retours normalisés : `0` en succès, `1` en cas d'erreur bloquante (clé manquante sans mock, erreur API non gérée).
   - Traitement élégant des cas limites (compte sans graphes, dossiers de documents inexistants).
   - Paramétrage `lastn=1000` lors de la récupération des épisodes pour maximiser la couverture sans coupure prématurée.
   - Linting `ruff check .` impeccable et validation de la structure de plan via `validate_plans.py` conforme.
   - Filet global porté de 716 à **734 tests passants** (100 % vert).

## Notes de complétion

Implémentation complète, auditée contradictoirement et validée de la sonde d'audit `backend/scripts/auditer_graphes_zep.py` et de sa suite de tests `backend/tests/test_auditer_graphes_zep.py`.
- Le mode `--mock` fournit une démonstration reproductible et déterministe avec les 3 cas types (Rebuild local 0 €, Migration ETL, Purge).
- Les formats d'export JSON normalisé et rapport Markdown synthétique sont opérationnels avec horodatages complets.
- L'arbre de décision protège les données existantes contre toute purge accidentelle en cas d'erreur de lecture.
- 6 patches de revue BMad appliqués (sécurisation purge, délimiteurs regex éphémères, pagination 2 pages, accents NFKD, colonne Markdown, cycle de vie).
- 17 tests unitaires au vert (+4 tests de revue), portant le filet global de 716 à 734 tests verts sans aucune régression.
