---
id: "011-5"
epic: "011"
titre: "Barrière de publication ReportQualityGate, anti-troncature de section et dossier d'audit exportable (simulation_audit/)"
statut: done
auteur: "Antigravity & Équipe MiroFish"
format: "2"
---

# Story 011-5 — Barrière de publication ReportQualityGate, anti-troncature de section et dossier d'audit exportable (simulation_audit/)

Lot C, priorité **P0**. En tant qu'analyste, auditeur et décideur s'appuyant sur les synthèses de simulation de MiroFish, je veux qu'une barrière de publication serveur stricte (`ReportQualityGate`) vérifie systématiquement l'intégrité structurelle du rapport, l'absence absolue de sections tronquées ou de phrases coupées en fin de génération via une procédure de reprise ciblée (`SectionCompletionGuard`), la conformité linguistique intégrale avec la locale active (`fr`), la présence de la section obligatoire d'objections et limites en cas de refus dans la cohorte, et la validation des affirmations clés sans tolérer de faux statut d'achèvement (bascule honnête et explicite en `ReportStatus.FAILED_VALIDATION` si un défaut critique persiste) ; et je veux pouvoir exporter en un clic un dossier d'audit autonome et complet (`simulation_audit.zip`) réunissant l'ensemble des 8 artefacts de preuve canoniques de la simulation pour vérification indépendante hors-ligne.

Cette story répond directement aux exigences fonctionnelles **FR-09** (Barrière de publication `ReportQualityGate` & `SectionCompletionGuard`), **FR-10** (Dossier d'audit exportable `simulation_audit/`) et **FR-11** (Conformité linguistique native) de l'Epic 011. Elle concourt aux critères de sortie chiffrés **C9** (0 section publiée tronquée ou sans ponctuation terminale, bascule en `FAILED_VALIDATION` si non résolu) et **C10** (Export du dossier d'audit complet avec les 8 artefacts requis, vérifiable hors-ligne), tout en garantissant la souveraineté locale-first (**NFR-01**), la non-régression absolue (**NFR-02**), la résilience face aux défaillances de génération (**NFR-04**) et l'étanchéité des prompts (**NFR-05**).

---

## Définition de prêt

- [x] **Objectif compris et cadré** :
  1. Définir le modèle de données structuré `QualityCheckItem`, `QualityCategory`, `QualityStatus` et le conteneur `QualityGateResult` dans `backend/app/models/report_quality.py`.
  2. Étendre l'énumération `ReportStatus` dans `backend/app/services/report_agent.py` avec le statut terminal explicite `FAILED_VALIDATION = "failed_validation"`.
  3. Concevoir et implémenter le composant anti-troncature `SectionCompletionGuard` : détection fine de phrases coupées (absence de ponctuation terminale `.`, `!`, `?`, `»`, `"` ou de clôture markdown valide ```` `) ou arrêt prématuré par quota de tokens (`finish_reason == "length"`), et déclenchement d'une continuation ciblée réassemblant le texte sans duplication (max 2 tentatives par section).
  4. Concevoir et implémenter la barrière de publication `ReportQualityGate` dans `backend/app/services/report_quality_gate.py` appliquant les 5 vérifications canoniques préalables à la publication :
     - *Contrôle 1 (Intégrité structurelle)* : 100 % des sections prévues dans l'outline sont présentes et non vides (> 50 caractères).
     - *Contrôle 2 (Anti-troncature)* : Aucune section ne se termine sur une phrase coupée ou un bloc markdown ouvert.
     - *Contrôle 3 (Conformité linguistique FR)* : Respect strict de la langue demandée (`locale == 'fr'`) sur les titres, sous-titres et synthèses.
     - *Contrôle 4 (Section d'objections et limites)* : Présence obligatoire de la section d'objections si `CohortCoverageTable` signale des réticences ou refus.
     - *Contrôle 5 (Vérification des claims)* : Absence d'affirmation événementielle critique en statut `CONTRADICTED` ou `UNSUPPORTED` sans limitation signalée.
  5. Implémenter la machine d'états stricte : si tous les contrôles passent (ou si les avertissements sont mineurs) $\rightarrow$ `ReportStatus.COMPLETED` ; si un échec bloquant persiste après reprise $\rightarrow$ bascule immédiate en `ReportStatus.FAILED_VALIDATION` avec journal d'audit `quality_checks.json` explicite.
  6. Concevoir et implémenter le service d'audit exportable `SimulationAuditService` dans `backend/app/services/simulation_audit_service.py` assemblant à la volée une archive ZIP canonique (`simulation_audit_<sim_id>.zip`) réunissant les 8 artefacts de preuve indispensables :
     - `run_manifest.json` : métadonnées d'exécution, modèle, provider, locale, git commit, horodatages ISO 8601.
     - `simulation_brief.json` : brief scénario, hypothèses, règles et horizon temporel (`time_horizon`).
     - `actors.json` : sélection des acteurs, rôles de scénario et empreinte SHA-256.
     - `source_manifest.json` : inventaire des documents sources avec typage épistémique (`EpistemicSourceKind`) et statuts de validation.
     - `observed_events.jsonl` : traces réelles normalisées des actions sociales avec `event_id` déterministes.
     - `cohort_coverage.json` : tableau de couverture de cohorte, répartition des décisions et marquage des silencieux.
     - `report_claims.json` : registre des affirmations structurées (`ReportClaim`), preuves associées et statuts de vérification.
     - `quality_checks.json` : rapport d'évaluation du `ReportQualityGate`.
     - `report.md` : texte final intégral du rapport publié.
  7. Exposer les endpoints API REST dans `backend/app/api/report.py` :
     - `GET /api/report/<report_id>/quality` : consultation du statut et des détails du `QualityGateResult`.
     - `GET /api/report/<report_id>/audit/download` : téléchargement direct en streaming de l'archive ZIP d'audit.
     - `GET /api/simulation/<simulation_id>/audit/download` : téléchargement direct par identifiant de simulation.
  8. Adapter l'interface Vue 3 pour restituer visuellement l'état du Quality Gate (badges couleur : Vert « Validé », Orange « Validé avec réserves », Rouge « Échec validation ») et intégrer le bouton d'export du dossier d'audit (.zip).
- [x] **Documents consultés** :
  - [PRD Epic 011](prd.md) : §2 (objectifs 6 et 7), §3 (FR-09, FR-10, FR-11), §4 (NFR-01, NFR-02, NFR-04, NFR-05), §5 (C9, C10).
  - [Architecture Epic 011](architecture.md) : §2.9 (barrière de publication `ReportQualityGate` & `SectionCompletionGuard`), §2.10 (dossier d'audit téléchargeable `SimulationAuditService`), §2.11 (interface utilisateur).
  - [Hub Epic 011](epic-011.md) : critères de sortie C9 et C10, découpage des stories.
  - [Proposition amont Keova](rapport-chatgpt.md) : constat des coupures de sections en fin de prompt, absence de traçabilité des vérifications, besoin d'un paquet d'audit autonome pour les comités de direction.
  - `backend/app/services/report_agent.py` : boucle ReACT, assemblage des sections, `ReportStatus`, `ReportOutline`, `ReportSection`.
  - `backend/app/services/simulation_action_verifier.py` : règles de vérification de claims, anti-affabulation et détection d'objections.
  - `backend/app/models/report_claim.py` : `ReportClaim`, `ReportClaimRegistry`.
  - `backend/app/models/cohort_coverage.py` : `CohortCoverageTable`, `DecisionStatus`.
  - `backend/app/api/report.py` : endpoints existants de rapport, gestion des téléchargements de fichiers (`send_file`).
  - `AGENTS.md` : §2.1 (Clean Architecture, pas de dépendance circulaire), §2.2 (tests hermétiques et non-régression).
- [x] **Dépendances résolues** :
  - Story 011-1 close (`done`) : maintien en vie interactif OASIS, interviews directes et clôture différée.
  - Story 011-2 close (`done`) : registre d'événements observés (`OasisLogReaderService`, `EvidencePack`) et bouclier `ToolShield`.
  - Story 011-3 close (`done`) : contrat structuré `ReportClaim`, typage épistémique et contrôle anti-affabulation.
  - Story 011-4 close (`done`) : tableau de couverture de cohorte, section limites et respect du temps simulé.
  - Filet global : **1 719 tests collectés et réussis sur l'hôte** (+ 9 tests frontend Node), 0 échec.
- [x] **Décisions d'ingénierie arrêtées avant code** :
  1. **Modèle `QualityGateResult` et typage strict** : Créer `backend/app/models/report_quality.py` contenant `QualityCheckItem` (catégorie, description, statut `PASSED` / `WARNING` / `FAILED`, détails), `QualityCategory` (`STRUCTURAL_INTEGRITY`, `COMPLETION_GUARD`, `LANGUAGE_COMPLIANCE`, `LIMITATIONS_SECTION`, `CLAIM_VERIFICATION`) et `QualityGateResult` (booléen `is_publishable`, statut global, liste des vérifications, horodatage, métadonnées).
  2. **Extension de `ReportStatus`** : Ajouter la valeur `FAILED_VALIDATION = "failed_validation"` dans `ReportStatus` (enum string). Un rapport dont les contrôles critiques ont échoué ne passe jamais en `COMPLETED`.
  3. **Heuristique fine d'anti-troncature (`SectionCompletionGuard`)** :
     - Vérifier la queue du texte de section après élimination des espaces finaux.
     - Sont considérés comme non tronqués : les textes se terminant par une ponctuation finale canonique (`.`, `!`, `?`, `...`, `»`, `"`, `')` ou une fin de bloc markdown valide (```` ``` ````, `|` pour un tableau achevé, `*` pour une puce complète).
     - En cas de fin suspecte (phrase coupée en plein mot ou sans ponctuation) : formulation d'un prompt de continuation court demandant au LLM de poursuivre exactement la phrase commencée.
     - Raccordement intelligent sans doublon des premiers mots renvoyés.
     - Limite de sécurité fixée à 2 tentatives de relance maximum par section pour éviter toute boucle infinie.
  4. **Cinq contrôles impératifs de la barrière `ReportQualityGate`** :
     - *Check 1 : Intégrité* : Toutes les sections de l'outline sont générées avec un contenu non vide.
     - *Check 2 : Troncature* : 100 % des sections passent le filtre de fin de phrase.
     - *Check 3 : Langue* : Vérification que les titres et contenus principaux sont rédigés dans la langue attendue (ex: absence de sections complètes basculées en anglais par hallucination LLM si locale `fr`).
     - *Check 4 : Limites & objections* : Si des refus figurent dans `CohortCoverageTable`, vérification de la présence effective de la section d'objections non levées.
     - *Check 5 : Claims vérifiées* : Aucune affirmation de type `OBSERVED_SOCIAL_ACTION` en statut `CONTRADICTED`.
  5. **Composition du dossier d'audit (`SimulationAuditService`)** :
     - Créer l'archive zip en mémoire via `io.BytesIO` et `zipfile.ZipFile` (ou sur disque dans un sous-dossier `simulation_audit/`).
     - Vérifier l'existence et l'intégrité de chacun des 8 fichiers sources indispensables. Si un fichier intermédiaire optionnel manque, le service génère un manifeste minimal avec notification d'absence plutôt que de crasher.
     - Calcul d'un fichier `checksums.sha256` intégré à la racine du zip pour sceller l'authenticité de l'archive.
  6. **Gestion des endpoints HTTP** :
     - Endpoint `/api/report/<report_id>/quality` renvoyant le JSON de `quality_checks.json`.
     - Endpoint `/api/report/<report_id>/audit/download` utilisant `send_file` de Flask avec `as_attachment=True` et `download_name=f"simulation_audit_{simulation_id}.zip"`.
  7. **Résilience et non-blocage de l'IHM** :
     - Si le rapport bascule en `FAILED_VALIDATION`, l'utilisateur n'est pas bloqué : le texte généré reste consultable dans l'IHM avec un bandeau explicatif et les diagnostics détaillés, permettant à l'utilisateur de comprendre pourquoi la barrière a refusé la publication automatique.
- [x] **Stratégie de tests identifiée** :
  - Créer `backend/tests/test_report_quality_gate_audit.py`.
  - Tests unitaires de `QualityGateResult` et sérialisation JSON de `quality_checks.json`.
  - Tests unitaires de `SectionCompletionGuard` : détection de texte tronqué vs texte complet, prompts de reprise, fusion sans doublon, et plafond de 2 relances.
  - Tests de la barrière `ReportQualityGate` : scénario nominal (tous checks au vert $\rightarrow$ `COMPLETED`), scénario d'objection manquante, scénario d'affirmation contredite, et scénario de bascule en `FAILED_VALIDATION`.
  - Tests de `SimulationAuditService` : création de l'archive ZIP, présence exacte des 8 artefacts canoniques (+ `checksums.sha256`), extraction et relecture hors-ligne.
  - Tests d'intégration API Flask des routes `/quality` et `/audit/download` (codes 200, 404, en-têtes HTTP corrects).
  - Filet global maintenu à $\ge 1 719$ tests au vert sur l'hôte.

---

## Définition de fini

- [x] Critères d'acceptation **AC1 à AC8** satisfaits et vérifiés par des tests automatisés passants.
- [x] Modèle `QualityCheckItem`, `QualityCategory`, `QualityStatus` et `QualityGateResult` créés dans `backend/app/models/report_quality.py`.
- [x] Extension de `ReportStatus` avec la valeur `FAILED_VALIDATION = "failed_validation"` dans `backend/app/services/report_agent.py`.
- [x] Composant anti-troncature `SectionCompletionGuard` opérationnel avec détection fine et reprise ciblée en max 2 passes.
- [x] Service de barrière de publication `ReportQualityGate` implémenté avec les 5 contrôles préalables et sérialisation `quality_checks.json`.
- [x] Intégration dans le cycle de vie du `ReportAgent` : publication en `COMPLETED` si succès, ou bascule en `FAILED_VALIDATION` avec motif clair si défaut persistant (Critère C9).
- [x] Service `SimulationAuditService` créant l'archive ZIP exportable contenant les 8 artefacts de preuve canoniques et leurs empreintes SHA-256 (Critère C10).
- [x] Endpoints API REST `/api/report/<report_id>/quality` et `/api/report/<report_id>/audit/download` opérationnels dans `backend/app/api/report.py`.
- [x] IHM frontend adaptée pour afficher les badges d'état qualité et le bouton d'exportation du dossier d'audit ZIP.
- [x] Suite de tests hermétiques dédiée créée dans `backend/tests/test_report_quality_gate_audit.py` (15 tests au vert).
- [x] Filet global de tests maintenu (1 734 tests réussis sur l'hôte, +15 tests) et parité frontend (9 tests Node).
- [x] `python backend/scripts/validate_plans.py` validé sans anomalie.
- [x] Revue contradictoire BMAD à 4 couches réalisée avec findings consignés et résolus.
- [x] Synchronisation des documents de suivi (`epic-011.md`, `sprint-status.yaml`, `STATUS.md`, `AGENTS.md`).

---

## Tâches

- [x] **T1 — Modèle structuré de qualité `report_quality.py` et extension de `ReportStatus`** :
  - Créer `backend/app/models/report_quality.py`.
  - Définir `QualityCategory` (`STRUCTURAL_INTEGRITY`, `COMPLETION_GUARD`, `LANGUAGE_COMPLIANCE`, `LIMITATIONS_SECTION`, `CLAIM_VERIFICATION`).
  - Définir `QualityStatus` (`PASSED`, `WARNING`, `FAILED`).
  - Définir la dataclass `QualityCheckItem` (catégorie, titre, statut, message, détails).
  - Définir la dataclass `QualityGateResult` avec `is_publishable`, `final_status`, `checks`, `summary`, `evaluated_at` et méthodes `to_dict`, `from_dict`, `to_json`, `save_to_file`.
  - Ajouter `FAILED_VALIDATION = "failed_validation"` à `ReportStatus` dans `backend/app/services/report_agent.py`.
- [x] **T2 — Détecteur de troncature et reprise ciblée `SectionCompletionGuard`** :
  - Implémenter le vérificateur de terminaison textuelle (`is_text_truncated(text: str) -> bool`) détectant les phrases interrompues et balises non fermées.
  - Implémenter `SectionCompletionGuard.complete_section(llm_client, section_title, current_content, locale)` déclenchant un prompt ciblé de prolongation.
  - Réassembler sans couture le prolongement avec le contenu existant (détection et suppression des répétitions de raccord).
  - Verrouiller le nombre de relances à 2 maximum par section.
- [x] **T3 — Service de barrière de publication `ReportQualityGate`** :
  - Créer `backend/app/services/report_quality_gate.py`.
  - Implémenter `evaluate_report(outline, report_md, cohort_table, claims_registry, brief, locale) -> QualityGateResult`.
  - Exécuter les 5 contrôles :
    1. *Structure* : Sections prévues présentes et non vides.
    2. *Troncature* : Absence de phrase coupée ou bloc markdown pendant.
    3. *Langue* : Titres et corps respectant la locale demandée (`fr`).
    4. *Limites* : Présence obligatoire de la section d'objections si refus constatés.
    5. *Claims* : Ratio de vérification et absence de contradiction flagrante sur les faits d'actions simulées.
  - Sauvegarder automatiquement `quality_checks.json` dans le répertoire du rapport et de la simulation.
- [x] **T4 — Intégration dans `ReportAgent` et gestion de la machine d'états (Critère C9)** :
  - Dans `ReportAgent._generate_report_internal`, invoquer le `ReportQualityGate` une fois les sections assemblées.
  - Si `result.is_publishable` est vrai : bascule vers `ReportStatus.COMPLETED`.
  - Si `result.is_publishable` est faux : bascule vers `ReportStatus.FAILED_VALIDATION` (aucun faux `COMPLETED`).
  - Persister l'état dans `report_state.json` avec les détails de validation.
- [x] **T5 — Service d'audit et archive ZIP autonome `SimulationAuditService` (Critère C10)** :
  - Créer `backend/app/services/simulation_audit_service.py`.
  - Implémenter `build_audit_package(simulation_id, report_id) -> bytes`.
  - Réunir les 8 artefacts canoniques :
    1. `run_manifest.json` (versions, git sha, modèle, locale, dates).
    2. `simulation_brief.json`.
    3. `actors.json`.
    4. `source_manifest.json` (documents avec `EpistemicSourceKind`).
    5. `observed_events.jsonl` (traces OASIS avec `event_id`).
    6. `cohort_coverage.json`.
    7. `report_claims.json`.
    8. `quality_checks.json`.
    9. `report.md`.
  - Ajouter `checksums.sha256` listant les condensats de tous les fichiers inclus.
  - Sauvegarder l'archive sous `simulations/<sim_id>/simulation_audit_<sim_id>.zip`.
- [x] **T6 — Endpoints d'API REST dans `backend/app/api/report.py`** :
  - Ajouter `GET /api/report/<report_id>/quality` renvoyant le JSON du `QualityGateResult`.
  - Ajouter `GET /api/report/<report_id>/audit/download` envoyant l'archive ZIP générée avec le Content-Disposition adéquat.
  - Ajouter `GET /api/report/simulation/<simulation_id>/audit/download` pour téléchargement direct depuis l'identifiant de simulation.
  - Gérer les erreurs (404 si simulation ou rapport introuvable, 409 si génération en cours).
- [x] **T7 — Adaptation de l'interface utilisateur frontend (Vue 3)** :
  - Dans le composant de vue de rapport (`Step4Report.vue`) :
    - Ajouter le badge de statut qualité : Vert (`Validé`), Orange (`Validé avec réserves`), Rouge (`Échec validation`).
    - Afficher une carte/accordéon dépliant les points de contrôle de `quality_checks.json`.
    - Ajouter le bouton « Télécharger le dossier d'audit (.zip) » branché sur l'API de téléchargement.
- [x] **T8 — Suite hermétique de tests `test_report_quality_gate_audit.py` et validation globale** :
  - Créer `backend/tests/test_report_quality_gate_audit.py`.
  - Couvrir les cas nominaux et d'échec : détection de troncature, relance de `SectionCompletionGuard`, évaluation des 5 checks du Quality Gate, génération de l'archive ZIP d'audit (validation de son contenu et de ses checksums), et appels d'API Flask.
  - Valider l'intégralité du filet de tests (1 734 tests hôte) et les 9 tests Node frontend.
  - Exécuter la revue de code BMAD à 4 couches.

---

## Notes de développement

### 1. Analyse des défaillances de troncature et d'auditabilité (Runs Keova R1 à R5)

L'audit approfondi des cinq runs Keova a révélé deux lacunes méthodologiques majeures :
1. **La troncature invisible des sections stratégiques** :
   - Dans le run R3 et R4, la section « Analyse financière et viabilité économique » s'est interrompue abruptement sur la phrase : « Pour les indépendants générant moins de 30 k€, le surcoût de l'accompagnement personnalisé représente un frein majeur car ».
   - Le système a néanmoins marqué le rapport comme `COMPLETED`, délivrant un document inachevé au décideur.
   - **Correction Story 011-5 :** `SectionCompletionGuard` détecte la phrase non close (« car » sans ponctuation terminale) et déclenche une continuation ciblée. Si la troncature ne peut être résolue, le rapport est déclassé en `FAILED_VALIDATION`.
2. **L'opacité des vérifications en comité de direction (Absence de pack d'audit)** :
   - Lorsqu'un rapport est présenté, les décideurs et auditeurs demandent : « Quels posts précis prouvent le rejet de Florence ? », « Quel brief exact a été injecté ? », « Quels documents étaient considérés comme faits réels ? ».
   - Auparavant, ces informations étaient éparpillées entre des fichiers JSONL, une base SQLite interne et des logs temporaires non exportables.
   - **Correction Story 011-5 :** L'export d'audit `simulation_audit.zip` rassemble en un seul clic les 8 artefacts de preuve vérifiables hors-ligne par un tiers avec leurs empreintes cryptographiques SHA-256.

---

### 2. Schéma de données de `quality_checks.json`

```json
{
  "simulation_id": "sim_20261016_keova",
  "report_id": "rep_20261016_184500",
  "evaluated_at": "2026-10-16T19:30:00Z",
  "is_publishable": true,
  "final_status": "completed",
  "summary": "5 vérifications sur 5 réussies. 0 phrase tronquée détectée.",
  "checks": [
    {
      "category": "structural_integrity",
      "title": "Intégrité des sections",
      "status": "passed",
      "message": "8 sections prévues, 8 sections générées avec succès (> 50 caractères).",
      "details": {"total_sections": 8, "empty_sections": 0}
    },
    {
      "category": "completion_guard",
      "title": "Anti-troncature de fin de section",
      "status": "passed",
      "message": "100 % des sections se terminent par une ponctuation terminale valide.",
      "details": {"retries_applied": 1, "resolved_sections": ["Analyse financière"]}
    },
    {
      "category": "language_compliance",
      "title": "Conformité linguistique",
      "status": "passed",
      "message": "Texte et titres conformes à la locale 'fr'.",
      "details": {"locale": "fr", "foreign_blocks_detected": 0}
    },
    {
      "category": "limitations_section",
      "title": "Section d'objections et limites",
      "status": "passed",
      "message": "Section 'Objections non levées, contradictions et limites' présente et détaillée.",
      "details": {"objections_count": 3}
    },
    {
      "category": "claim_verification",
      "title": "Intégrité des affirmations d'actions simulées",
      "status": "passed",
      "message": "0 contradiction critique détectée sur les actions de la cohorte.",
      "details": {"total_claims": 24, "verified": 22, "unsupported": 2, "contradicted": 0}
    }
  ]
}
```

---

### 3. Matrice des 8 artefacts du dossier d'audit exportable (`simulation_audit.zip`)

| Fichier dans l'archive | Description & Rôle probatoire | Source interne |
|---|---|---|
| `run_manifest.json` | Métadonnées d'exécution : version MiroFish, git commit, modèle LLM, provider, locale, température, horodatages ISO 8601 | Configuration d'exécution & runtime |
| `simulation_brief.json` | Brief officiel soumis à la simulation : scénario, hypothèses, règles d'interaction, horizon temporel | `simulations/<sim_id>/simulation_brief.json` |
| `actors.json` | Sélection formelle des personas, attribution des rôles (`ScenarioRole`) et empreinte SHA-256 | `simulations/<sim_id>/actors.json` |
| `source_manifest.json` | Inventaire complet des documents sources injectés avec typage épistémique (`EpistemicSourceKind`) | Documents du projet & `source_documents.json` |
| `observed_events.jsonl` | Traces chronologiques des actions réelles observées sur les plateformes avec `event_id` déterministes | `OasisLogReaderService` (`actions.jsonl` & SQLite) |
| `cohort_coverage.json` | Tableau de couverture de cohorte, engagement individuel, objections et silencieux (`present_no_action`) | `simulations/<sim_id>/cohort_coverage.json` |
| `report_claims.json` | Registre structuré des assertions du rapport avec leurs statuts (`VERIFIED`, `UNSUPPORTED`) et preuves | `simulations/<sim_id>/report_claims.json` |
| `quality_checks.json` | Journal d'audit de la barrière `ReportQualityGate` attestant de la complétude et de l'intégrité | `reports/<rep_id>/quality_checks.json` |
| `report.md` | Texte intégral définitif du rapport d'analyse sociale | `reports/<rep_id>/report.md` |
| `checksums.sha256` | Empreintes cryptographiques SHA-256 de chacun des 9 fichiers ci-dessus pour scellement hors-ligne | Calculé à la volée lors de la compression |

---

## Revue

### Review Findings (Revue contradictoire BMAD à 4 couches du 16 octobre 2026)

- [x] [Review][Patch] Correction de l'import manquant json et utilisation du helper canonique get_report_by_simulation dans download_simulation_audit [`backend/app/api/report.py:1264`]
- [x] [Review][Patch] Élimination des faux positifs de troncature dans SectionCompletionGuard.is_text_truncated pour les phrases interrogatives et citations se terminant par une ponctuation canonique valide ('?', '!', '»', '"') [`backend/app/services/report_quality_gate.py:1278-1282`]
- [x] [Review][Patch] Correction de l'espacement typographique dans SectionCompletionGuard.assemble_continuation évitant un espace parasite avant une ponctuation intermédiaire ou finale [`backend/app/services/report_quality_gate.py:1324-1333`]
- [x] [Review][Patch] Insensibilité à la casse sur l'intitulé de la section d'objections et limites dans le Contrôle 4 du ReportQualityGate [`backend/app/services/report_quality_gate.py:1584-1589`]
- [x] [Review][Patch] Garde anti-collision 409 Conflict lors du téléchargement d'audit pendant une génération de rapport en cours [`backend/app/api/report.py:1148-1280`]
- [x] [Review][Patch] Résilience de typage dans build_source_manifest supportant à la fois les instances SourceDocument et les dictionnaires [`backend/app/services/simulation_audit_service.py:1834-1838`]
- [x] [Review][Patch] Repli sur simulationId dans l'IHM Step4Report.vue lors du téléchargement du package d'audit [`frontend/src/components/Step4Report.vue:755-759`]
- [x] [Review][Patch] Enrichissement de la suite hermétique de tests couvrant la non-régression de l'espacement, les questions interrogatives et le conflit 409 [`backend/tests/test_report_quality_gate_audit.py`]

#### Rejected findings
*(Aucun finding rejeté — 10 points bruts de la revue à 4 couches consolidés en 8 patches appliqués et testés)*

---

## Notes de complétion

La story 011-5 a été complétée avec succès le 16 octobre 2026 :

1. **Modèle de qualité et extension d'état (`backend/app/models/report_quality.py` & `report_agent.py`)** :
   - Énumérations `QualityCategory` (5 catégories) et `QualityStatus` (`passed`, `warning`, `failed`).
   - Dataclasses `QualityCheckItem` et `QualityGateResult` avec sérialisation JSON déterministe et persistance atomique `save_to_file`.
   - Extension de `ReportStatus` avec la valeur canonique `FAILED_VALIDATION = "failed_validation"`.

2. **Garde anti-troncature de section `SectionCompletionGuard` (`backend/app/services/report_quality_gate.py`)** :
   - Détection fine de troncature (`is_text_truncated`) : ponctuation terminale canonique (`_CANONICAL_TERMINAL_PUNCTUATION`), détection des blocs de code markdown non fermés (nombre impair de triples backticks), titres orphelins terminaux, et mots de liaison/conjonctions suspensives (`_SUSPICIOUS_TRAILING_WORDS` FR/EN) sans faux positif sur les phrases interrogatives closes.
   - Prolongation ciblée par LLM (`complete_section`) avec contexte glissant de queue (500 caractères) et limite stricte de 2 relances par section.
   - Réassemblage sans couture (`assemble_continuation`) avec suppression des préfixes LLM, respect strict de la typographie de ponctuation et détection de chevauchement sur les derniers mots.

3. **Barrière de publication `ReportQualityGate` (`backend/app/services/report_quality_gate.py`)** :
   - Exécution des 5 contrôles préalables :
     1. Intégrité structurelle des sections de l'outline (> 50 caractères).
     2. Anti-troncature et clôture du texte.
     3. Conformité linguistique (`fr`).
     4. Présence obligatoire de la section d'objections et limites si des refus/réticences existent dans `CohortCoverageTable` (insensible à la casse).
     5. Intégrité des assertions sans affabulation critique (`CONTRADICTED` sur `OBSERVED_SOCIAL_ACTION`).
   - Persistance automatique de `quality_checks.json` dans le dossier du rapport et de la simulation.

4. **Intégration dans le cycle de vie du `ReportAgent` (Critère C9)** :
   - Évaluation de la barrière avant la finalisation de l'état.
   - Transition automatique vers `ReportStatus.COMPLETED` si publiable, ou `ReportStatus.FAILED_VALIDATION` si un contrôle bloquant échoue, empêchant la livraison d'un rapport défaillant.

5. **Dossier d'audit exportable `SimulationAuditService` (Critère C10)** :
   - Rassemblement des 8 artefacts de preuve canoniques (`run_manifest.json`, `simulation_brief.json`, `actors.json`, `source_manifest.json`, `observed_events.jsonl`, `cohort_coverage.json`, `report_claims.json`, `quality_checks.json`, `report.md`).
   - Scellement cryptographique `checksums.sha256` calculé à la volée.
   - Génération et mise en cache du package ZIP sous `simulations/<sim_id>/simulation_audit_<sim_id>.zip` avec support de `force_rebuild`.

6. **Endpoints REST et interface utilisateur Vue 3 (Critères C9, C10)** :
   - Endpoints Flask : `GET /api/report/<report_id>/quality`, `GET /api/report/<report_id>/audit/download`, `GET /api/report/simulation/<sim_id>/audit/download` avec garde 409 Conflict en cours d'exécution.
   - IHM `Step4Report.vue` : Badges d'état qualité, carte dépliable des vérifications de qualité, bouton de téléchargement de l'archive ZIP d'audit avec repli sur `simulationId`.

7. **Qualité et tests hermétiques** :
   - 20 tests unitaires hermétiques dédiés dans `backend/tests/test_report_quality_gate_audit.py`.
   - Filet global porté à **1 739 tests réussis sur l'hôte** (0 échec, +20 tests).
   - 9 tests Node frontend réussis et build Vite vérifié.
   - Revue de code BMAD à 4 couches validée avec 8 patches appliqués.
