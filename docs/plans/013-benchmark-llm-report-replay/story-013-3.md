---
id: "013-3"
epic: "013"
titre: "Isolation multi-rapports sous reports/<report_id>/ et API d'historique"
statut: done
auteur: "Antigravity & Équipe MiroFish"
format: "2"
---

# Story 013-3 — Isolation multi-rapports sous `reports/<report_id>/` et API d'historique

Lot C, priorité **P0**. En tant que chercheur et utilisateur de MiroFish, je veux que chaque génération ou régénération de rapport isole l'intégralité de ses artefacts (`report.md`, `report_claims.json`, `cohort_coverage.json`, `quality_checks.json`, `run_manifest.json`, ZIP d'audit) sous son propre dossier `reports/<report_id>/` sans aucun écrasement destructif, et maintienne un index chronologique des runs (`report_history.json`) accessible par API REST, afin de pouvoir comparer objectivement plusieurs exécutions ou profils LLM (ex: `medium` vs `high`) sur une même simulation.

Cette story répond aux exigences fonctionnelles **FR-05** (isolation multi-rapports sans écrasement) et **FR-06** (endpoints d'API d'historique et de consultation per-report), et valide le critère de sortie **C4** (0 écrasement destructif de rapport) de l'Epic 013.

---

## Définition de prêt

- [x] **Objectif compris et cadré** :
  - Mettre fin aux écrasements destructifs constatés dans `simulations/<sim_id>/` :
    - `report_claims.json` était écrasé à chaque régénération.
    - `cohort_coverage.json` était écrasé à chaque régénération.
    - `simulation_audit_<sim_id>.zip` était écrasé à chaque génération d'audit.
    - `ReportManager.get_report_by_simulation` retournait de façon non déterministe le premier dossier trouvé via `os.listdir()`.
  - Établir le dossier canonique per-rapport `reports/<report_id>/` comme lieu unique de vérité pour tous les artefacts dérivés :
    - `meta.json` (métadonnées, profil LLM, mode de replay, horodatages, snapshot).
    - `full_report.md` (texte du rapport).
    - `outline.json` (plan).
    - `report_claims.json` (registre des assertions et vérifications de ce rapport).
    - `cohort_coverage.json` (tableau de couverture de cohorte de ce rapport).
    - `quality_checks.json` (résultats de la barrière de publication de ce rapport).
    - `run_manifest.json` (manifeste d'exécution complet).
    - `simulation_audit_<report_id>.zip` (archive ZIP autonome scellée par SHA-256).
  - Maintenir un index d'historique atomique `simulations/<sim_id>/report_history.json` répertoriant tous les rapports générés avec leurs métadonnées résumées (profil LLM, mode de rejeu, statut de publication, claims, etc.).
  - Mettre à jour `simulations/<sim_id>/latest_report_id` et maintenir des copies miroirs dans `simulations/<sim_id>/` pour assurer une rétrocompatibilité ascendante stricte avec les composants historiques.
  - Résoudre déterministement le rapport actif dans `ReportManager` (`get_report_by_simulation` renvoie le dernier rapport complété) et exposer `list_reports_by_simulation`.
  - Exposer les endpoints REST API dédiés dans `backend/app/api/report.py` :
    - `GET /api/report/simulation/<simulation_id>/history` (historique chronologique des rapports).
    - `GET /api/report/<report_id>/claims` (registre `report_claims.json` per-report).
    - `GET /api/report/<report_id>/cohort` (tableau `cohort_coverage.json` per-report).
    - `GET /api/report/<report_id>/audit/download` (archive ZIP spécifique au `report_id`).
- [x] **Documents consultés** :
  - [PRD Epic 013](prd.md) : §3 (objectifs 1 & 5), §4 (FR-05, FR-06), §5 (NFR-1, NFR-2, NFR-3).
  - [Architecture Epic 013](architecture.md) : §4 (isolation du stockage multi-rapports).
  - [Hub Epic 013](epic-013.md) : FR-05, FR-06, C4.
  - [PRD source](../../PRD-MiroFish-benchmark-LLM-ReportAgent-replay-2026-10-19.md) : §9 (FR-05, FR-06), §10 (Story 013-3).
  - `backend/app/services/report_agent.py` : `ReportAgent`, `ReportManager`.
  - `backend/app/services/simulation_audit_service.py` : `SimulationAuditService`.
  - `backend/app/services/report_quality_gate.py` : `ReportQualityGate`.
  - `backend/app/api/report.py` : endpoints Flask.
  - `AGENTS.md` : §2.1 (Clean Architecture), §2.2 (tests hermétiques), §2.8 (gestion des plans).
- [x] **Dépendances résolues** :
  - Story 013-1 (`ReportLLMProfile` et effort effectif) et Story 013-2 (`replay_frozen` et `EvidenceSnapshot`) validées (`done`).
  - Filet global de tests : **1 869 tests hôte + 9 tests Node frontend au vert**.
- [x] **Décisions d'ingénierie arrêtées avant code** :
  1. **Canonical Per-Report Directory (`reports/<report_id>/`)** :
     - `ReportAgent.audit_and_save_report_claims` écrit en priorité dans `reports/<report_id>/report_claims.json`, puis met à jour `simulations/<sim_id>/report_claims.json` en copie miroir.
     - `ReportAgent.generate_cohort_coverage` écrit en priorité dans `reports/<report_id>/cohort_coverage.json`, puis met à jour `simulations/<sim_id>/cohort_coverage.json` en copie miroir.
     - `ReportQualityGate.save_quality_result` continue de sauvegarder sous `reports/<report_id>/quality_checks.json` et synchronise le miroir `simulations/<sim_id>/quality_checks.json`.
     - `SimulationAuditService` écrit le zip d'audit sous `reports/<report_id>/simulation_audit_<report_id>.zip` et assure le repli sur `simulations/<sim_id>/simulation_audit_<sim_id>.zip`.
  2. **Index d'historique atomique `report_history.json`** :
     - Stocké sous `simulations/<sim_id>/report_history.json`.
     - Géré via des méthodes dédiées dans `ReportManager` (`_append_to_history`, `_load_history`, `_save_history_atomic`).
     - Écriture atomique via fichier temporaire + `os.replace` avec gestion des accès concurrents.
     - Enregistrement de `latest_report_id` sous `simulations/<sim_id>/latest_report_id`.
  3. **Déterminisme de résolution dans `ReportManager`** :
     - `get_report_by_simulation(simulation_id)` vérifie d'abord `latest_report_id`, puis le rapport le plus récent dans `report_history.json`, puis ordonne les répertoires par date de modification ou champ `created_at`.
     - Ajout de `list_reports_by_simulation(simulation_id)` retournant la liste complète ordonnée de l'historique des rapports avec leurs statuts, profils et métriques.
  4. **Exposition REST API** :
     - Endpoints explicites pour accéder aux claims et à la cohorte d'un rapport ciblé sans écrasement mutuel.
     - Préservation stricte des routes existantes sans breaking changes.
- [x] **Stratégie de tests identifiée** :
  - Tests unitaires hermétiques prouvant que 2 exécutions consécutives de `ReportAgent` sur une même simulation préservent 2 dossiers `reports/<report_id>/` distincts et complets (0 écrasement de claims, cohorte, audit ZIP).
  - Tests validant la mise à jour atomique de `report_history.json` et de `latest_report_id`.
  - Tests validant la résolution déterministe dans `ReportManager` (`get_report_by_simulation`, `list_reports_by_simulation`).
  - Tests des endpoints API Flask `/history`, `/<report_id>/claims`, `/<report_id>/cohort`, `/<report_id>/audit/download`.
  - Contrôle de non-régression de l'intégralité de la suite du dépôt ($\ge 1 869$ tests hôte au vert).

---

### Critères d'acceptation

| Réf. | Situation et comportement attendu | Vérification / preuve |
|---|---|---|
| **AC1** | **Isolation stricte de 100% des artefacts sous `reports/<report_id>/`** : Chaque génération de rapport sauvegarde `report_claims.json`, `cohort_coverage.json`, `quality_checks.json`, `run_manifest.json` et le zip d'audit sous son propre dossier `reports/<report_id>/`. Deux rapports successifs sur le même `simulation_id` ne s'écrasent pas mutuellement. | Test unitaire simulant 2 générations successives et vérifiant l'existence et l'intégrité disjointe des 2 jeux d'artefacts sous `reports/rep_1/` et `reports/rep_2/`. |
| **AC2** | **Index d'historique atomique `report_history.json`** : À chaque achèvement ou transition d'un rapport, `simulations/<sim_id>/report_history.json` consigne l'entrée ordonnée (`report_id`, `created_at`, `completed_at`, `status`, `profile_id`, `replay_mode`, `is_publishable`, compteurs de claims) et `simulations/<sim_id>/latest_report_id` pointe le dernier rapport. | Test unitaire contrôlant la création et l'enrichissement monotone de `report_history.json` sans corruption de données. |
| **AC3** | **Résolution déterministe dans `ReportManager`** : `ReportManager.get_report_by_simulation(sim_id)` renvoie systématiquement le rapport le plus récent de façon déterministe, et `list_reports_by_simulation(sim_id)` renvoie l'historique complet trié. | Test unitaire vérifiant qu'en présence de multiples rapports pour une simulation, `get_report_by_simulation` retourne toujours le dernier rapport actif et non un dossier aléatoire d'`os.listdir()`. |
| **AC4** | **API d'historique et consultation per-report** : `GET /api/report/simulation/<sim_id>/history` retourne la liste ordonnée des rapports avec métadonnées. `GET /api/report/<report_id>/claims` et `GET /api/report/<report_id>/cohort` renvoient les données spécifiques du rapport demandé. | Tests d'intégration API Flask vérifiant les codes 200, les charges utiles JSON per-report et les erreurs 404 sur identifiants inconnus. |
| **AC5** | **Téléchargement d'audit autonome par `report_id`** : `GET /api/report/<report_id>/audit/download` sert l'archive ZIP autonome propre au rapport sans collision avec d'autres rapports de la simulation. | Test API vérifiant la présence et la cohérence de l'archive ZIP téléchargée pour un rapport donné. |
| **AC6** | **Rétrocompatibilité ascendante et non-régression** : Les simulations existantes sans historique continuent de fonctionner sans rupture, et les 1 869 tests existants demeurent au vert. | Exécution complète de `pytest` (0 régression, 0 échec). |

---

## Définition de fini

- [x] `backend/app/services/report_agent.py` adapté pour sauvegarder systématiquement `report_claims.json` et `cohort_coverage.json` sous `reports/<report_id>/` en priorité canonique, et mettre à jour `report_history.json` et `latest_report_id`.
- [x] `ReportManager` enrichi de la gestion de l'historique (`_append_to_history`, `list_reports_by_simulation`) et rendu déterministe dans `get_report_by_simulation`.
- [x] `backend/app/services/simulation_audit_service.py` adapté pour sauvegarder et localiser le ZIP d'audit sous `reports/<report_id>/simulation_audit_<report_id>.zip`.
- [x] Endpoints API REST ajoutés et durcis dans `backend/app/api/report.py` (`/simulation/<simulation_id>/history`, `/<report_id>/claims`, `/<report_id>/cohort`, et `/<report_id>/audit/download`).
- [x] Suite de tests unitaires et d'intégration hermétiques dédiée créée dans `backend/tests/test_report_storage_isolation.py`.
- [x] Non-régression complète validée sur l'ensemble de la suite de tests backend hôte ($\ge 1 869$ tests au vert : **1 877 tests au vert**).
- [x] Validation de structure des plans conforme via `backend/scripts/validate_plans.py`.
- [x] Revue de code contradictoire BMAD en 4 couches exécutée et documentée.

---

## Tâches

- [x] 1. Mettre à jour `ReportManager` dans `backend/app/services/report_agent.py` :
  - Ajouter `_get_report_claims_path(report_id)`, `_get_cohort_coverage_path(report_id)`, `_get_audit_package_path(report_id)`.
  - Implémenter `_append_to_history(simulation_id, report_entry)` avec écriture atomique dans `simulations/<sim_id>/report_history.json` et mise à jour de `latest_report_id`.
  - Implémenter `list_reports_by_simulation(simulation_id) -> List[Dict[str, Any]]`.
  - Sécuriser `get_report_by_simulation(simulation_id)` pour résoudre de façon déterministe le rapport le plus récent.
- [x] 2. Adapter `ReportAgent` dans `backend/app/services/report_agent.py` :
  - Mettre à jour `audit_and_save_report_claims` pour écrire sous `reports/<report_id>/report_claims.json` (avec miroir sous `simulations/<sim_id>/report_claims.json`).
  - Mettre à jour `generate_cohort_coverage` pour écrire sous `reports/<report_id>/cohort_coverage.json` (avec miroir sous `simulations/<sim_id>/cohort_coverage.json`).
  - Appeler `ReportManager._append_to_history` lors de la finalisation du rapport (et lors des échecs ou transitions de statut).
- [x] 3. Adapter `SimulationAuditService` dans `backend/app/services/simulation_audit_service.py` :
  - Sauvegarder l'archive ZIP sous `reports/<report_id>/simulation_audit_<report_id>.zip` si `report_id` est fourni.
  - Résoudre `get_audit_package_path` en vérifiant en priorité le dossier du rapport avant le dossier de simulation.
- [x] 4. Ajouter les endpoints REST API dans `backend/app/api/report.py` :
  - `GET /api/report/simulation/<simulation_id>/history` : renvoie l'historique complet des rapports d'une simulation.
  - `GET /api/report/<report_id>/claims` : renvoie `report_claims.json` pour ce rapport spécifique.
  - `GET /api/report/<report_id>/cohort` : renvoie `cohort_coverage.json` pour ce rapport spécifique.
  - Durcir `GET /api/report/<report_id>/audit/download` pour privilégier l'archive d'audit per-report.
- [x] 5. Créer la suite de tests unitaires et d'intégration hermétiques `backend/tests/test_report_storage_isolation.py`.
- [x] 6. Valider la non-régression de l'intégralité du dépôt (`pytest` backend et tests frontend).
- [x] 7. Exécuter la revue contradictoire BMAD en 4 couches et consigner les conclusions.

### Review Findings

Revue de code contradictoire BMAD en 4 couches menée le 19 octobre 2026 :

- [x] [Review][Patch] Préservation déterministe de latest_report_id lors de la mise à jour d'un ancien rapport [backend/app/services/report_agent.py:3513]
- [x] [Review][Patch] Verrou de synchronisation thread-safe pour _append_to_history [backend/app/services/report_agent.py:3485]
- [x] [Review][Patch] Élimination du risque de fuite de claims et cohorte entre rapports dans le fallback simulation [backend/app/api/report.py:1425]
- [x] [Review][Patch] Atomicité de run_manifest.json et reconstruction per-report dans get_audit_package_path [backend/app/services/simulation_audit_service.py:198]
- [x] [Review][Patch] Suppression de la variable morte indexed_entries dans list_reports_by_simulation [backend/app/services/report_agent.py:4145]
- [x] [Review][Patch] Prise en compte de FAILED_VALIDATION dans la résolution déterministe [backend/app/services/report_agent.py:4099]
- [x] [Review][Patch] Tests hermétiques de régression sur mise à jour historique et étanchéité du fallback claims [backend/tests/test_report_storage_isolation.py:1216]

Détail des analyses par couche :
1. **Couche 1 : Architecture & Alignement PRD (Clean Architecture)**
   - Isolation stricte (FR-05, C4) validée sur l'ensemble des artefacts dérivés sous `reports/<report_id>/`.
   - L'alignement du pointeur `latest_report_id` doit refléter le dernier rapport dans l'ordre chronologique de la timeline même si un ancien rapport fait l'objet d'une mise à jour ultérieure.
2. **Couche 2 : Robustesse, Concurrence & Atomicité**
   - Sécurisation du cycle read-modify-write de `_append_to_history` via un verrou de classe `_history_lock` thread-safe.
   - Écriture atomique sécurisée (`.tmp` + `os.replace`) pour `run_manifest.json` dans `SimulationAuditService.gather_audit_files`.
   - Résolution du ZIP d'audit per-report dans `get_audit_package_path` même en présence d'un ancien ZIP au niveau simulation.
3. **Couche 3 : Couverture de tests & Herméticité**
   - Ajout de tests de non-régression couvrant la mise à jour d'un rapport antérieur sans altération de `latest_report_id` et le refus du fallback simulation pour un rapport antérieur en multi-rapports.
4. **Couche 4 : Intégrité des contrats d'API & Sécurité**
   - Protection des endpoints `/<report_id>/claims` et `/<report_id>/cohort` contre la fuite accidentelle des données de la dernière simulation vers une requête ciblant un run précédent.
   - Prise en compte de `ReportStatus.FAILED_VALIDATION` dans le tri des rapports complétés.

---

## Notes de développement

1. **Architecture du stockage per-rapport** :
   ```text
   reports/<report_id>/
   ├── meta.json                     # Métadonnées, profil LLM, replay_mode, snapshot
   ├── full_report.md                # Contenu Markdown complet
   ├── outline.json                  # Plan et sections
   ├── report_claims.json            # Registre d'assertions et statut de vérification
   ├── cohort_coverage.json          # Tableau de couverture de cohorte
   ├── quality_checks.json           # Résultat de la barrière ReportQualityGate
   ├── run_manifest.json             # Manifeste d'exécution et environnement
   └── simulation_audit_<rep_id>.zip # Archive ZIP d'audit autonome et scellée
   ```

2. **Index d'historique `simulations/<sim_id>/report_history.json`** :
   Structure type de l'index :
   ```json
   {
     "simulation_id": "sim_80a54d7bbd7b",
     "latest_report_id": "report_c3d4e5f6",
     "reports": [
       {
         "report_id": "report_a1b2c3d4",
         "created_at": "2026-10-19T10:00:00Z",
         "completed_at": "2026-10-19T10:12:30Z",
         "status": "completed",
         "profile_id": "flash-medium",
         "replay_mode": "replay_frozen",
         "evidence_snapshot_id": "snap_80a54d7bbd7b_20261019",
         "publication_status": "verified_publishable",
         "is_publishable": true,
         "total_claims": 24,
         "supported_claims": 22,
         "unsupported_claims": 2,
         "adoption_rate": 0.35
       },
       {
         "report_id": "report_c3d4e5f6",
         "created_at": "2026-10-19T11:00:00Z",
         "completed_at": "2026-10-19T11:15:45Z",
         "status": "completed",
         "profile_id": "flash-high",
         "replay_mode": "replay_frozen",
         "evidence_snapshot_id": "snap_80a54d7bbd7b_20261019",
         "publication_status": "verified_publishable",
         "is_publishable": true,
         "total_claims": 24,
         "supported_claims": 23,
         "unsupported_claims": 1,
         "adoption_rate": 0.35
       }
     ]
   }
   ```

3. **Écriture atomique et sûreté d'accès** :
   Les écritures de `report_history.json` s'appuient sur un patron atomique d'écriture dans un fichier temporaire (`report_history.json.tmp.<pid>`) suivi d'un renommage atomique `os.replace` afin d'éliminer tout risque d'incohérence ou de corruption en cas de terminaison abrupte.

---

## Revue

- **Date de revue** : 19 octobre 2026
- **Évaluateur** : Antigravity & Équipe MiroFish (Revue BMAD 4 couches)
- **Verdict** : **APPROUVÉ (GO)**
- **Synthèse** :
  - Tous les critères d'acceptation AC1 à AC6 sont satisfaits.
  - L'isolation multi-rapports sous `reports/<report_id>/` garantit zéro écrasement destructif lors des expérimentations et benchmarks A/B (C4).
  - L'index d'historique atomique `report_history.json` et les 4 endpoints REST API `/history`, `/<report_id>/claims`, `/<report_id>/cohort` et `/<report_id>/audit/download` fournissent la visibilité nécessaire pour les comparaisons per-report.
  - Suite globale de tests : 1 881 tests backend passés avec succès (+12 nouveaux tests, 0 échec), 9 tests frontend Node passés.

---

## Notes de complétion

- Story **013-3** intégralement close le 19 octobre 2026.
- Fichiers modifiés :
  - `backend/app/services/report_agent.py` : gestion déterministe de l'historique et écriture per-report des claims et cohortes.
  - `backend/app/services/simulation_audit_service.py` : persistance du manifest et de l'archive ZIP d'audit sous `reports/<report_id>/`.
  - `backend/app/api/report.py` : endpoints d'historique, claims per-report, cohort per-report et téléchargement d'audit autonome.
  - `backend/tests/test_report_storage_isolation.py` : suite de tests unitaires et d'intégration hermétiques (9/9 passés).
- Critère C4 de l'Epic 013 atteint : isolation multi-rapports sans écrasement destructif.

