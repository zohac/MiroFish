---
id: "012-4"
epic: "012"
titre: "Barrière de publication « Fail-Closed » et états de certification du rapport"
statut: backlog
auteur: "Antigravity & Équipe MiroFish"
format: "2"
---

# Story 012-4 — Barrière de publication « Fail-Closed » et états de certification du rapport

Lot D, priorité **P0**. En tant qu'analyste et décideur s'appuyant sur les simulations MiroFish, je veux que la barrière de publication `ReportQualityGate` applique un contrôle strict en mode « Fail-Closed » distinguant quatre états de certification explicites (`draft`, `needs_review`, `verified_publishable`, `failed_validation`), afin qu'aucun rapport alléguant des actions simulées ne puisse être certifié ou qualifié de publiable si aucune preuve authentique n'est établie dans les traces d'exécution (éliminant l'anomalie R6 où 0 claim vérifié sur 258 recevait un verdict `is_publishable=true`).

Cette story répond directement à l'exigence fonctionnelle **FR-05** (barrière de publication stricte « Fail-Closed ») et valide le critère de sortie **C5** (zéro rapport certifié « vérifié » avec 0 claim vérifié) de l'Epic 012, ainsi que les exigences de l'audit réel R6 (QA-08 et QA-09).

---

## Définition de prêt

- [ ] **Objectif compris et cadré** :
  - Mettre fin au comportement permissif (« Fail-Open ») de `ReportQualityGate` qui accordait `is_publishable=True` et `final_status=warning` même en présence de 0 % d'assertions vérifiées ou lors de l'absence de registre d'audit.
  - Définir le modèle formel `PublicationStatus` (`draft`, `needs_review`, `verified_publishable`, `failed_validation`).
  - Conditionner strictement `is_publishable = True` à l'état `verified_publishable` (avec option de consultation sous réserve pour `needs_review`, et interdiction formelle de certification pour `failed_validation`).
  - Imposer un seuil minimal de vérification ($\ge 80\ %$ de claims d'actions observées vérifiés dans l'`EvidencePack`) pour l'état `verified_publishable`.
  - Rejeter en `failed_validation` tout rapport affirmant des actions sans aucune preuve (`verified_claims == 0`), comportant des conversions commerciales fictives (`ADOPTED_VERIFIED` non sourcé) ou des contradictions critiques d'exécution.
  - Traiter avec nuance les rapports exploratoires/théoriques sans assertions d'actions simulées (bascule en `needs_review` sans échec artificiel).
  - Exposer ces états et diagnostics détaillés dans l'API Flask et l'interface utilisateur Vue 3 (`Step4Report.vue`).
- [ ] **Documents consultés** :
  - [PRD Epic 012](prd.md) : §2 (C5), §3 (FR-05), §4 (NFR-1, NFR-2, NFR-3).
  - [Architecture Epic 012](architecture.md) : §1 (diagramme de flux), §2.4 (barrière de publication Fail-Closed), §3 (rétrocompatibilité `QualityGateResult`).
  - [Hub Epic 012](epic-012.md) : description globale, FR-05, critère C5.
  - [Audit R6](../../retour-essai-6/PRD-MiroFish-correctifs-audit-reel-R6-2026-10-17.md) : anomalie P0 / Story 012-4 (§ P0, QA-08, QA-09).
  - `backend/app/models/report_quality.py` : dataclass `QualityGateResult`, `QualityStatus`, `_recompute_status`.
  - `backend/app/services/report_quality_gate.py` : classe `ReportQualityGate`, méthode `evaluate_report`.
  - `backend/app/api/report.py` : endpoint `GET /<report_id>/quality`.
  - `frontend/src/components/Step4Report.vue` : badges qualité et diagnostics d'audit.
  - `frontend/locales/fr.json` et `frontend/locales/en.json` : libellés d'internationalisation.
  - `AGENTS.md` : §2.1 (Clean Architecture), §2.2 (qualité et herméticité des tests), §2.8 (gestion des plans).
- [ ] **Dépendances résolues** :
  - Stories 012-1 (résolution d'identités sans collision), 012-2 (rôles et décisions déterministes) et 012-3 (réconciliation déterministe claims $\leftrightarrow$ EvidencePack) sont closes avec succès.
  - Filet global actuel : **1 800 tests réussis sur l'hôte**, 9 tests frontend Node passants, 0 échec.
- [ ] **Décisions d'ingénierie arrêtées avant code** :
  1. **Modèle `PublicationStatus`** :
     - Énumération string canonique :
       - `draft` : rapport en cours de génération ou non encore soumis aux contrôles qualité.
       - `needs_review` : rapport exploratoire/théorique sans prétention d'actions simulées, ou rapport empirique avec preuves partielles (entre 50 % et 80 % de claims vérifiés) ou avertissements mineurs ; consultable avec bandeau d'avertissement explicite.
       - `verified_publishable` : rapport dont $\ge 80\ %$ des claims d'actions observées sont attestés par des `event_id` d'`EvidencePack` authentiques, sans affabulation ni contradiction critique ; certifié publiable.
       - `failed_validation` : certification refusée en raison d'un manque total de preuves (0 action vérifiée alors que des actions sont alléguées), de contradictions avérées ou de conversions d'adoption infondées. Le rapport reste conservé à titre de trace d'audit mais ne peut être diffusé comme validé.
  2. **Garantie Fail-Closed sur `is_publishable`** :
     - Le booléen `is_publishable` vaut `True` **uniquement** si `publication_status == PublicationStatus.VERIFIED_PUBLISHABLE`.
     - Dans tous les autres cas (`draft`, `needs_review`, `failed_validation`), `is_publishable = False`.
  3. **Règles d'arbitrage de la barrière de claims (`QualityCategory.CLAIM_VERIFICATION`)** :
     - **Cas A : Absence de registre** : Si aucun registre `ReportClaimRegistry` n'est fourni ou s'il est vide :
       - Si le corps du rapport contient des mentions d'actions simulées ou de rounds, verdict `FAILED` -> `FAILED_VALIDATION`.
       - Si le corps du rapport ne mentionne aucune action simulée (synthèse théorique), verdict `WARNING` -> `NEEDS_REVIEW`.
     - **Cas B : Zéro claim vérifié avec actions alléguées (anomalie R6)** : Si `claims_registry` comporte des claims d'actions simulées mais `verified_claims == 0`, verdict immédiat `FAILED` -> `FAILED_VALIDATION` (élimination formelle de QA-08).
     - **Cas C : Contradictions d'actions simulées** : Toute assertion contredite (`VerificationStatus.CONTRADICTED`) entraîne un verdict `FAILED` -> `FAILED_VALIDATION`.
     - **Cas D : Taux de vérification suffisant** : Si le ratio de vérification des claims d'actions observées est $\ge 80\ %$, verdict `PASSED` -> éligible à `VERIFIED_PUBLISHABLE`.
     - **Cas E : Taux intermédiaire** : Si le ratio est compris entre 50 % et 80 % sans contradiction critique, verdict `WARNING` -> `NEEDS_REVIEW`.
  4. **Contrôle d'absence d'affabulation commerciale** :
     - Si le rapport affiche un taux d'adoption non nul ou des statuts `ADOPTED_VERIFIED` alors qu'aucune preuve d'action probante n'est liée à l'adoption dans le registre de claims, rejet immédiat en `FAILED_VALIDATION`.
  5. **Compatibilité IHM et bilinguisme** :
     - Intégration de 4 badges distincts dans `Step4Report.vue` avec styles et infobulles adaptés.
     - Clés i18n dans `fr.json` et `en.json` pour chaque statut de certification et chaque motif de refus.
- [ ] **Stratégie de tests identifiée** :
  - Test de régression directe sur le cas R6 : 258 claims, 0 vérifié $\rightarrow$ doit retourner `publication_status == 'failed_validation'` et `is_publishable == False`.
  - Test sur un cas nominal prouvé : 10 claims d'actions, 9 vérifiés ($90\ \%$) $\rightarrow$ `verified_publishable` et `is_publishable == True`.
  - Test sur un cas exploratoire sans registre $\rightarrow$ `needs_review` et `is_publishable == False`.
  - Test sur un cas avec conversion fictive non étayée $\rightarrow$ `failed_validation`.
  - Test sur la désérialisation d'anciens fichiers `quality_checks.json` ne comportant pas `publication_status` (rétrocompatibilité descendante).

### Critères d'acceptation

| Réf. | Situation et comportement attendu | Vérification / preuve |
|---|---|---|
| **AC1** | **Typologie formelle `PublicationStatus`** : Le modèle `report_quality.py` définit `PublicationStatus` avec les valeurs `draft`, `needs_review`, `verified_publishable`, `failed_validation`. `QualityGateResult` expose le champ `publication_status` et assure une sérialisation/désérialisation bidirectionnelle exacte. | Test unitaire de validation de l'énumération, roundtrip JSON et rétrocompatibilité avec les anciens exports. |
| **AC2** | **Règle Fail-Closed sur absence de preuves (Anomalie R6 / QA-08)** : Lorsqu'un rapport comporte des affirmations d'actions simulées mais qu'aucune n'est vérifiée par l'`EvidencePack` (`verified_claims == 0`), `ReportQualityGate` attribue impérativement `QualityStatus.FAILED`, `publication_status = PublicationStatus.FAILED_VALIDATION` et `is_publishable = False`. | Test unitaire reproduisant fidèlement les statistiques R6 (0 vérifié sur 258 claims) et validant le rejet strict. |
| **AC3** | **Règle Fail-Closed sur absence de registre (QA-09)** : Si aucun registre de claims n'est disponible ou si la collecte d'événements a échoué, le contrôle ne conclut jamais par un succès silencieux. Il bascule en `failed_validation` (si des actions sont rédigées) ou en `needs_review` (rapport théorique). | Test unitaire validant le comportement avec `claims_registry = None` sur texte avec actions vs texte purement théorique. |
| **AC4** | **Seuil d'exigence pour `verified_publishable`** : La certification `verified_publishable` avec `is_publishable = True` est accordée si et seulement si tous les contrôles préalables sont au vert (`PASSED`), 0 contradiction critique n'est relevée, et au moins 80 % des claims d'actions observées sont étayés par des preuves valides. | Test unitaire comparant un rapport à 85 % de preuves (reçu en `verified_publishable`) et un rapport à 75 % (rétrogradé en `needs_review`). |
| **AC5** | **Interdiction d'affabulation commerciale** : Si le rapport revendique des adoptions (`ADOPTED_VERIFIED`) sans qu'aucun événement de conversion probant ne soit vérifié dans les claims d'actions, la barrière de publication refuse la certification et bascule en `failed_validation`. | Test unitaire injectant un tableau de cohorte avec adoptions sans actions vérifiées correspondantes. |
| **AC6** | **Exposition API et affichage IHM bilingue** : L'API `/api/report/<id>/quality` renvoie `publication_status` et les diagnostics. `Step4Report.vue` affiche les 4 états avec badges, couleurs contrastées et messages d'aide en français et anglais. | Tests d'intégration API Flask, validation du build frontend Vite et test unitaire de parité i18n (`test_i18n_parity.py`). |
| **AC7** | **Non-régression globale** : Maintien de l'intégralité des 1 800 tests existants au vert sur l'hôte, et intégration d'une suite hermétique complète pour la barrière fail-closed. | Exécution complète de `pytest` sans échec (filet $\ge 1810$ tests verts). |

---

## Définition de fini

- [ ] Énumération `PublicationStatus` et champ `publication_status` implémentés dans `backend/app/models/report_quality.py`.
- [ ] Logique d'évaluation Fail-Closed implémentée dans `backend/app/services/report_quality_gate.py`.
- [ ] Zéro rapport certifié sans preuve (QA-08) et gestion stricte de l'absence de registre (QA-09).
- [ ] Rétrocompatibilité transparente assurée sur les anciens fichiers `quality_checks.json`.
- [ ] Endpoint API `GET /api/report/<report_id>/quality` enrichi et validé.
- [ ] Composant Vue 3 `Step4Report.vue` adapté avec les 4 états de publication et styles associés.
- [ ] Dictionnaires `locales/fr.json` et `locales/en.json` synchronisés à 100 % de parité.
- [ ] Suite de tests hermétiques dédiée créée dans `backend/tests/test_report_quality_gate_audit.py` (ou suite équivalente).
- [ ] 1 800+ tests backend au vert sur l'hôte et 9 tests frontend Node passants.
- [ ] `validate_plans.py` et `ruff check` validés sans erreur.
- [ ] Revue contradictoire BMAD à 4 couches réalisée, findings résolus.
- [ ] Documentation et suivi de sprint mis à jour (`epic-012.md`, `sprint-status.yaml`, `STATUS.md`, `AGENTS.md`).

---

## Tâches

- [ ] **T1 — Modélisation de `PublicationStatus` et enrichissement de `QualityGateResult`** :
  - Définir `PublicationStatus` dans `backend/app/models/report_quality.py`.
  - Mettre à jour `QualityGateResult` pour intégrer `publication_status`, les statistiques détaillées et le recalcul fail-closed de `is_publishable`.
  - Assurer la rétrocompatibilité sur `from_dict` pour les anciens exports dépourvus de `publication_status`.
- [ ] **T2 — Implémentation des règles Fail-Closed dans `ReportQualityGate`** :
  - Mettre à jour `ReportQualityGate.evaluate_report` pour appliquer les seuils de preuve ($\ge 80\ %$ pour `verified_publishable`, 50–80 % pour `needs_review`, $< 50\ %$ ou 0 vérifié pour `failed_validation`).
  - Gérer l'absence de registre selon la nature du texte (QA-09).
  - Bloquer les conversions commerciales fictives non sourcées.
  - Définir les messages diagnostics explicites pour chaque catégorie de défaillance.
- [ ] **T3 — Intégration API et sérialisation serveur** :
  - Mettre à jour l'API `backend/app/api/report.py` pour remonter `publication_status` et les nouveaux diagnostics d'intégrité.
  - Vérifier la persistance atomique de `quality_checks.json` dans `reports/<id>/` et `simulations/<id>/`.
- [ ] **T4 — Interface utilisateur Vue 3 et localisation bilingue** :
  - Mettre à jour `frontend/src/components/Step4Report.vue` pour restituer les badges `draft`, `needs_review`, `verified_publishable`, `failed_validation`.
  - Ajouter les clés de traduction nécessaires dans `frontend/locales/fr.json` et `frontend/locales/en.json`.
  - Tester le rendu visuel et la non-régression des tests Node (`pnpm --dir frontend test`).
- [ ] **T5 — Suite de tests hermétiques dédiée et validation de non-régression** :
  - Rédiger les tests unitaires couvrant les AC1 à AC7 dans `backend/tests/test_report_quality_gate_audit.py`.
  - Valider l'invalidation propre de la fixture d'audit R6.
  - Exécuter la suite complète `pytest` et `validate_plans.py`.
- [ ] **T6 — Revue contradictoire BMAD à 4 couches et finalisation** :
  - Lancer `/bmad-code-review`, appliquer les correctifs et mettre à jour le statut.

---

## Notes de développement

### Diagnostic de l'anomalie R6 sur la barrière de publication
Dans le run réel Keova R6 (`sim_ea4f3cfe1028`, rapport `report_77d96ea4c1c9`), le fichier `quality_checks.json` généré concluait :
```json
{
  "is_publishable": true,
  "final_status": "warning",
  "summary": "Validé avec réserves : 4 réussis, 1 avertissement(s).",
  "checks": [
    {
      "category": "claim_verification",
      "title": "Intégrité des affirmations d'actions simulées",
      "status": "warning",
      "message": "17 affirmation(s) contredite(s) ou divergente(s) répertoriée(s) dans le registre d'audit.",
      "details": {
        "total_claims": 258,
        "contradicted": 17,
        "verification_ratio": 0.0
      }
    }
  ]
}
```

Ce diagnostic illustre la faille fondamentale :
1. Sur 258 assertions, **0 claim n'a été vérifié** (`verification_ratio = 0.0`).
2. 17 claims étaient explicitement contredits.
3. Pourtant, parce qu'aucun claim n'était marqué d'une catégorie bloquante (`OBSERVED_SOCIAL_ACTION` contredite en dur), la barrière n'émettait qu'un simple `WARNING`.
4. Le calcul de clôture `_recompute_status` stipulait que tout `WARNING` reste `is_publishable = True`.
5. Le rapport était donc certifié publiable par le système alors qu'aucune de ses affirmations de faits simulés n'était reliée à la moindre trace d'exécution !

La Story 012-4 remplace ce comportement par un automate d'états strict :
```
                    ┌─────────────────────────┐
                    │       Evaluating        │
                    └────────────┬────────────┘
                                 │
         ┌───────────────────────┼───────────────────────┐
         │                       │                       │
         ▼                       ▼                       ▼
  [verified_publishable]   [needs_review]       [failed_validation]
  - Claims vérifiés >= 80% - Synthèse théorique - 0 claim vérifié
  - 0 contradiction        - Preuves 50-80%     - Contradiction avérée
  - is_publishable = True  - is_pub = False     - Conversions fictives
                                                - is_publishable = False
```

---

## Revue

### Review Findings

*(À renseigner lors de la revue contradictoire BMAD)*

---

## Notes de complétion

*(À renseigner lors de la clôture de la story)*
