---
id: "013-4"
epic: "013"
titre: "Télémétrie d'usage, mesure des temps et plafonds budgétaires"
statut: backlog
auteur: "Antigravity & Équipe MiroFish"
format: "2"
---

# Story 013-4 — Télémétrie d'usage, mesure des temps et plafonds budgétaires

Lot D, priorité **P0/P1**. En tant qu'analyste et expérimentateur MiroFish, je veux mesurer avec précision l'utilisation des ressources LLM (tokens de prompt, de complétion et de réflexion, nombre d'appels, temps d'inférence réel et coût estimé) pour chaque génération de rapport, et imposer des plafonds budgétaires et temporels stricts par profil sans escalade automatique vers des modèles payants, afin de comparer le coût-efficacité des configurations LLM (ex. `gemini-3.8-flash` en `medium` vs `high`) et d'éviter les dérives de consommation.

Cette story répond à l'exigence fonctionnelle **FR-08** (télémétrie d'usage, mesure de durée et estimation de coût par génération) et valide le critère de sortie **C5** (traçabilité des coûts et consommation) de l'Epic 013.

---

## Définition de prêt

- [x] **Objectif compris et cadré** :
  - Capturer systématiquement les métriques d'usage des appels LLM effectués par `ReportAgent` (phases d'outline, de rédaction de sections, d'interviews et d'audit de claims).
  - Fournir une table de tarification explicite, datée et extensible (`PricingTable`), calculant le coût estimatif en USD à partir des tarifs par million de tokens (prompt, complétion, réflexion) pour chaque modèle supporté.
  - Différencier rigoureusement les modèles gratuits (ex. serveur Antigravity local, OpenCode Go gratuit : 0.00 $) des modèles facturables.
  - Gérer honnêtement l'indisponibilité des métriques fournisseur (`usage_available = False`, `reasoning_effort_effective = "unknown"`) sans jamais fabriquer de fausses données de facturation (AT-12).
  - Imposer des plafonds stricts configurés dans `ReportLLMProfile` :
    - `max_total_cost_usd` (ex. 2.0 $) : interruption propre avant engagement de requêtes additionnelles en cas de dépassement prévisible (AT-11).
    - `max_wall_seconds` (ex. 900 s) : interruption propre en cas de dépassement de la durée limite d'exécution.
    - **Règle absolue d'étanchéité** : aucune bascule automatique vers un modèle payant ou un fournisseur externe non configuré.
  - Persister l'objet de métriques dans `reports/<report_id>/usage.json`, l'intégrer dans `run_manifest.json`, `meta.json` et `report_history.json`.
  - Exposer les métriques via un endpoint REST `GET /api/report/<report_id>/usage` et enrichir l'historique `GET /api/report/simulation/<sim_id>/history`.
  - Garantir l'étanchéité des secrets (NFR-4) : aucune clé API, token ou prompt personnel brut dans les logs ou exports de métriques.
- [x] **Documents consultés** :
  - [PRD Epic 013](prd.md) : §3 (objectifs 1 & 5), §4 (FR-08), §5 (NFR-1, NFR-2, NFR-4).
  - [Architecture Epic 013](architecture.md) : §2.3 (`ReportUsageMetrics`), §3 (`reasoning_effort`).
  - [Hub Epic 013](epic-013.md) : C5, C8.
  - [PRD source](../../PRD-MiroFish-benchmark-LLM-ReportAgent-replay-2026-10-19.md) : §9 (FR-08), §10 (Story 013-4), §11 (AT-11, AT-12, AT-13).
  - `backend/app/models/report_llm_profile.py` : `ReportLLMProfile` (`max_total_cost_usd`, `max_wall_seconds`).
  - `backend/app/utils/llm_client.py` : `LLMClient.last_usage`, `LLMClient._create_completion`.
  - `backend/app/services/report_agent.py` : boucle de génération `_generate_report_internal`.
  - `backend/app/services/simulation_audit_service.py` : intégration dans `run_manifest.json`.
- [x] **Dépendances résolues** :
  - Story 013-1 (`ReportLLMProfile`), Story 013-2 (`replay_frozen`) et Story 013-3 (isolation `reports/<report_id>/`) validées (`done`).
  - Filet global de tests : **1 881 tests hôte + 9 tests Node frontend au vert**.
- [x] **Décisions d'ingénierie arrêtées avant code** :
  1. **Modèle `ReportUsageMetrics` et `PricingTable`** :
     - Implémenté dans `backend/app/models/report_usage.py`.
     - Table de tarification référençant `gemini-3.8-flash`, `deepseek-v4-pro`, `qwen3.8-max`, `gpt-6.1-sol` avec distinction claire des coûts input / output et support des environnements locaux à coût marginal nul.
     - Prise en compte explicite des `thinking_tokens` (reasoning tokens) lorsque fournis par le proxy local ou le provider (`completion_tokens_details.reasoning_tokens`).
  2. **Traqueur de session `ReportUsageTracker`** :
     - Instancié par `ReportAgent` au début de la génération.
     - Capture l'usage de chaque appel `chat()` et `chat_json()` via un mécanisme d'écoute propre ou collecte synchrone après chaque phase.
     - Enregistrement par phase (`planning`, `sections`, `claims_reconciliation`, `interviews`).
  3. **Garde-fous budgétaires et temporels (`BudgetGuard`)** :
     - Vérification avant chaque itération d'écriture de section ou d'outil ReACT :
       - Si `current_cost >= max_total_cost_usd` : déclenchement de `ReportBudgetExceededError`, enregistrement du statut d'arrêt contrôlé, sauvegarde partielle et zéro requête LLM ultérieure.
       - Si `elapsed_seconds >= max_wall_seconds` : déclenchement de `ReportTimeoutError`, enregistrement propre du statut.
     - Interdiction stricte de bascule automatique vers un autre modèle (Fail-Safe).
  4. **Persistance et exposition REST** :
     - Sauvegarde atomique sous `reports/<report_id>/usage.json`.
     - Inclusion dans `run_manifest.json` via `SimulationAuditService.gather_audit_files`.
     - Ajout de la route `GET /api/report/<report_id>/usage` dans `backend/app/api/report.py`.
- [x] **Stratégie de tests identifiée** :
  - Tests unitaires de `PricingTable` : calcul exact des coûts, gestion des modèles inconnus, gratuité des modèles locaux.
  - Tests unitaires de `ReportUsageTracker` : cumul des tokens, gestion des réponses sans usage (`usage_available = False`), extraction des thinking tokens.
  - Tests du garde-fou budgétaire : déclenchement de `ReportBudgetExceededError` dès que le plafond est atteint, absence d'appels subséquents.
  - Tests du garde-fou temporel : arrêt propre sur dépassement de `max_wall_seconds`.
  - Tests d'intégration API Flask pour `GET /api/report/<report_id>/usage`.
  - Contrôle de non-régression globale ($\ge 1 881$ tests hôte au vert).

---

### Critères d'acceptation

| Réf. | Situation et comportement attendu | Vérification / preuve |
|---|---|---|
| **AC1** | **Modèle de métriques et table de tarification explicite** : `ReportUsageMetrics` capture `prompt_tokens`, `completion_tokens`, `thinking_tokens`, `total_tokens`, `duration_seconds`, `calls_count` et `estimated_cost_usd`. `PricingTable` calcule le coût estimatif à partir d'une table datée sans ambiguïté. | Tests unitaires validant la sérialisation, désérialisation et le calcul de coût pour différents modèles. |
| **AC2** | **Traçabilité par phase et cumul par job** : `ReportAgent` cumule fidèlement l'usage de chaque appel LLM (outline, sections, claims, interviews) et calcule la durée totale d'inférence. | Test simulant plusieurs appels LLM et contrôlant l'exactitude du cumul dans `ReportUsageTracker`. |
| **AC3** | **Gestion explicite des métriques manquantes** : Si le provider ne renvoie pas d'objet `usage`, les métriques sont marquées `usage_available = False`, `estimated_cost_usd = None`, et `reasoning_effort_effective = "unknown"`. Zéro coût fictif inventé. | Test unitaire simulant une réponse brute sans usage et vérifiant les valeurs nulles et drapeaux explicites. |
| **AC4** | **Plafond budgétaire et temporel Fail-Safe** : Si le coût estimé cumulé dépasse `max_total_cost_usd` ou si le temps dépasse `max_wall_seconds`, le job s'interrompt avec une erreur claire et prévisible (`ReportBudgetExceededError`). Zéro bascule automatique vers un modèle payant. | Test unitaire configurant un budget minime (ex. 0.0001 $) et vérifiant l'interruption immédiate avant la section suivante. |
| **AC5** | **Persistance per-rapport et synchronisation d'audit** : Les métriques sont persistées atomiquement dans `reports/<report_id>/usage.json`, incluses dans `run_manifest.json` et résumées dans `report_history.json`. | Test unitaire vérifiant la présence et la complétude des métriques dans les fichiers dérivés sur disque. |
| **AC6** | **API REST et sécurité des secrets** : `GET /api/report/<report_id>/usage` restitue les métriques d'usage complètes. Aucune clé API, token ou prompt brut ne figure dans la réponse ou les logs (NFR-4). | Tests API vérifiant le code 200, la structure JSON et l'absence totale de secrets. |

---

## Définition de fini

- [ ] Modèle `backend/app/models/report_usage.py` créé avec `ReportUsageMetrics`, `CallUsageRecord` et `PricingTable`.
- [ ] Service de suivi `ReportUsageTracker` implémenté et intégré dans `ReportAgent` pour enregistrer l'usage à chaque appel LLM.
- [ ] Garde-fous budgétaires et temporels (`max_total_cost_usd`, `max_wall_seconds`) actifs dans `ReportAgent` avec interruption contrôlée.
- [ ] Persistance atomique de `reports/<report_id>/usage.json` et enrichissement de `run_manifest.json` et `report_history.json`.
- [ ] Endpoint REST `GET /api/report/<report_id>/usage` implémenté dans `backend/app/api/report.py`.
- [ ] Suite de tests unitaires et d'intégration hermétiques dédiée dans `backend/tests/test_report_usage_telemetry.py`.
- [ ] Filet global de tests maintenu au vert ($\ge 1 881$ tests hôte + 9 tests Node frontend).

---

## Tâches

- [ ] 1. Définir le modèle de métriques `ReportUsageMetrics`, `CallUsageRecord` et la table tarifaire `PricingTable` dans `backend/app/models/report_usage.py`.
- [ ] 2. Implémenter le traqueur d'usage `ReportUsageTracker` (`backend/app/services/report_usage_tracker.py`) capturant les métriques à chaque appel `LLMClient`.
- [ ] 3. Intégrer les garde-fous budgétaires (`max_total_cost_usd`) et temporels (`max_wall_seconds`) avec arrêts contrôlés `ReportBudgetExceededError` et `ReportTimeoutError`.
- [ ] 4. Intégrer `ReportUsageTracker` dans `ReportAgent._generate_report_internal` et persister `reports/<report_id>/usage.json`.
- [ ] 5. Mettre à jour `SimulationAuditService.gather_audit_files` et `ReportManager._append_to_history` pour inclure la télémétrie.
- [ ] 6. Exposer l'endpoint REST `GET /api/report/<report_id>/usage` dans `backend/app/api/report.py`.
- [ ] 7. Écrire la suite de tests unitaires et d'intégration hermétiques dans `backend/tests/test_report_usage_telemetry.py`.
- [ ] 8. Vérifier la non-régression complète (`uv run pytest tests/` et `validate_plans.py`).
- [ ] 9. Exécuter la revue de code contradictoire BMAD 4 couches et consigner les conclusions.

---

## Notes de développement

1. **Table de tarification standard (`PricingTable`)** :
   ```python
   DEFAULT_PRICING = {
       "gemini-3.8-flash": {
           "input_cost_per_million": 0.15,
           "output_cost_per_million": 0.60,
           "currency": "USD",
       },
       "deepseek-v4-pro": {
           "input_cost_per_million": 0.27,
           "output_cost_per_million": 1.10,
           "currency": "USD",
       },
       "gpt-6.1-sol": {
           "input_cost_per_million": 2.50,
           "output_cost_per_million": 10.00,
           "currency": "USD",
       },
   }
   ```
   Pour les modèles hébergés sur le proxy local Antigravity (`provider_id == "antigravity-local"`), le coût facturable réel est de `0.00 $`, mais le coût estimé théorique peut être calculé à titre informatif.

2. **Extraction des thinking tokens** :
   Dans les réponses compatibles OpenAI, les tokens de raisonnement peuvent être localisés sous :
   `usage.completion_tokens_details.reasoning_tokens` ou `usage.reasoning_tokens`. Le traqueur doit extraire cette valeur de façon défensive sans lever d'`AttributeError`.

3. **Protection anti-escalade** :
   Le garde-fou budgétaire ne doit jamais tenter de basculer automatiquement vers un autre modèle en cas de dépassement. Le job s'arrête proprement et expose le motif du refus.

---

## Revue

*En attente de réalisation du ticket.*

---

## Notes de complétion

*En attente de réalisation du ticket.*
