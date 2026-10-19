---
id: "013-4"
epic: "013"
titre: "Télémétrie d'usage, mesure des temps et plafonds budgétaires"
statut: review
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

- [x] Modèle `backend/app/models/report_usage.py` créé avec `ReportUsageMetrics`, `CallUsageRecord` et `PricingTable`.
- [x] Service de suivi `ReportUsageTracker` implémenté et intégré dans `ReportAgent` pour enregistrer l'usage à chaque appel LLM.
- [x] Garde-fous budgétaires et temporels (`max_total_cost_usd`, `max_wall_seconds`) actifs dans `ReportAgent` avec interruption contrôlée.
- [x] Persistance atomique de `reports/<report_id>/usage.json` et enrichissement de `run_manifest.json` et `report_history.json`.
- [x] Endpoint REST `GET /api/report/<report_id>/usage` implémenté dans `backend/app/api/report.py`.
- [x] Suite de tests unitaires et d'intégration hermétiques dédiée dans `backend/tests/test_report_usage_telemetry.py`.
- [x] Filet global de tests maintenu au vert ($\ge 1 881$ tests hôte + 9 tests Node frontend).

---

## Tâches

- [x] 1. Définir le modèle de métriques `ReportUsageMetrics`, `CallUsageRecord` et la table tarifaire `PricingTable` dans `backend/app/models/report_usage.py`.
- [x] 2. Implémenter le traqueur d'usage `ReportUsageTracker` (`backend/app/services/report_usage_tracker.py`) capturant les métriques à chaque appel `LLMClient`.
- [x] 3. Intégrer les garde-fous budgétaires (`max_total_cost_usd`) et temporels (`max_wall_seconds`) avec arrêts contrôlés `ReportBudgetExceededError` et `ReportTimeoutError`.
- [x] 4. Intégrer `ReportUsageTracker` dans `ReportAgent._generate_report_internal` et persister `reports/<report_id>/usage.json`.
- [x] 5. Mettre à jour `SimulationAuditService.gather_audit_files` et `ReportManager._append_to_history` pour inclure la télémétrie.
- [x] 6. Exposer l'endpoint REST `GET /api/report/<report_id>/usage` dans `backend/app/api/report.py`.
- [x] 7. Écrire la suite de tests unitaires et d'intégration hermétiques dans `backend/tests/test_report_usage_telemetry.py`.
- [x] 8. Vérifier la non-régression complète (`uv run pytest tests/` et `validate_plans.py`).
- [x] 9. Exécuter la revue de code contradictoire BMAD 4 couches et consigner les conclusions.

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

### Notes d'implémentation (19 octobre 2026)

- **Politique de gratuité explicite** : `PricingTable` distingue les passerelles locales (`antigravity-local`, `codex-local`, `local`, `ollama`), les modèles explicitement gratuits (`-free`, `:free`) et un champ `billing_mode` (`auto`, `free`, `metered`) ajouté à `ReportLLMProfile`. Un modèle gratuit reste à `0.00 $` même hors grille tarifaire, tout en conservant un `theoretical_cost_usd` informatif.
- **Table tarifaire datée** : `PRICING_TABLE_VERSION = "2026-10-19"` ; les tarifs sont indicatifs et jamais présentés comme une facture. `estimated_cost_usd` vaut `None` dès qu'un appel n'a pas d'`usage` exploitable.
- **Tokens de réflexion** : extraction défensive depuis `completion_tokens_details.reasoning_tokens`, puis `reasoning_tokens` et `output_tokens_details`. Ils sont considérés comme un sous-ensemble de `completion_tokens` ; un tarif séparé n'est appliqué que si `thinking_billed_separately` est vrai.
- **Durées** : `duration_seconds` est la somme des temps d'inférence mesurés par appel ; `wall_seconds` conserve le temps mural du job (outils, E/S, audits compris).
- **Couverture des outils** : `ReportAgent` injecte son client LLM profilé dans `ZepToolsService` (`llm_client=self.llm`) et bascule en phase `interviews` autour de l'outil d'interview. Les appels d'outils sont donc mesurés et soumis au même garde-fou.
- **Garde-fou à deux niveaux** : contrôle aux frontières (planification, sections, outils, audit) et `pre_request_callback` dans `LLMClient`, qui bloque chaque tentative HTTP, y compris les relances JSON et les reprises anti-troncature. Le temps restant est transmis comme `timeout` de la requête OpenAI-compatible.
- **Fail-Closed tarifaire** : un modèle facturable absent de la grille déclenche `ReportBudgetExceededError` plutôt que de traiter « inconnu » comme gratuit. Une erreur `usage` manquante, elle, reste marquée inconnue sans fabriquer de coût (AT-12).
- **Persistance** : `usage.json` est écrit atomiquement avant le scellement du ZIP d'audit ; il est ensuite inclus dans `checksums.sha256`. Une fois scellé, il n'est plus réécrit (le ZIP et le fichier disque restent identiques). Le résumé est repris dans `meta.json`, `run_manifest.json` et `report_history.json` (avec rétro-remplissage des entrées historiques).
- **API** : `GET /api/report/<report_id>/usage` reconstruit la réponse depuis `ReportUsageMetrics` (liste blanche de champs) ; un fichier absent renvoie 404, un fichier corrompu 500 sans traceback serveur.
- **Secrets** : `sanitize_usage_payload` filtre récursivement les clés sensibles en normalisant casse, tirets et underscores (`api_key`, `baseUrl`, `access-token`, `prompt_messages`, etc.). `run_manifest.json` n'expose plus `LLM_BASE_URL`, seulement `base_url_configured`.

---

## Revue

**Revue contradictoire BMAD 4 couches — 19 octobre 2026.**

Quatre relectures indépendantes (correction fonctionnelle, preuve par les tests, sécurité/robustesse, intégration/non-régression) ont examiné le diff, puis les correctifs ont été réappliqués et revérifiés.

### Findings retenus et corrigés

1. **Gratuité inversée / coûts fictifs** — `opencode-go` et les modèles locaux hors grille pouvaient produire un coût non nul, et un modèle local inconnu retournait `None`. Correctifs : `billing_mode` explicite sur `ReportLLMProfile`, court-circuit de gratuité avant résolution tarifaire, marqueurs `-free`/`:free`, coût théorique conservé.
2. **Appels LLM des outils non mesurés** — `ZepToolsService` créait son propre client, échappant au traqueur et au budget. Correctif : injection de `llm_client=self.llm`, phase `interviews` autour des entretiens et contrôle budgétaire avant chaque outil.
3. **Premier contrôle budgétaire hors du `try`** — un budget nul levait hors de `generate_report`, sans `usage.json` ni historique. Correctif : `begin()` et le contrôle `planning` déplacés dans le bloc protégé ; un arrêt contrôlé produit désormais un rapport `FAILED` persisté.
4. **Garde-fou inerte sans profil** — le parcours API sans `profile_id` n'avait aucun plafond. Correctif : repli sur `ReportLLMProfile.default_from_env()` (2,0 $ / 900 s), tout en conservant le modèle du client.
5. **Durée murale au lieu du temps d'inférence** — `duration_seconds` incluait les outils et les E/S. Correctif : `duration_seconds` = somme des temps d'appel, `wall_seconds` = temps mural.
6. **Requêtes possibles après le plafond** — les relances internes de `chat_json` et les reprises anti-troncature échappaient au contrôle. Correctif : `pre_request_callback` dans `LLMClient` et `timeout` par requête égal au temps restant.
7. **Projection budgétaire trop agressive** — la moyenne globale pouvait couper avant la moindre section. Correctif : projection sur le coût du dernier appel.
8. **Modèle facturable non tarifé** — le plafond devenait silencieusement inerte. Correctif : Fail-Closed tarifaire (`pricing_unavailable`) plutôt que « inconnu = gratuit ».
9. **Fuite potentielle de `LLM_BASE_URL`** dans `run_manifest.json`. Correctif : `base_url_configured` booléen ; bloc `llm` aligné sur le profil du job (`model`, `provider`, effort).
10. **Endpoint `/usage` trop permissif** — lecture brute et traceback serveur. Correctif : reconstruction via `ReportUsageMetrics` (liste blanche), 404 si absent, 500 explicite sans traceback si corrompu.
11. **`usage.json` copié brut dans l'archive d'audit** — risque de secrets hérités. Correctif : re-sérialisation sanitizée, fichier omis si absent plutôt que faux négatif.
12. **Callbacks écrasés sur client partagé** — chaînage du callback précédent et détachement en `finally`.
13. **`usage=object()` considéré disponible** — détection stricte de champs numériques réels ; coût `None` sinon.
14. **Historique legacy sans `usage_summary`** — rétro-remplissage depuis `usage.json`/`meta.json`.
15. **Divers robustesse** : `OverflowError` sur JSON corrompu, `UnicodeDecodeError`, noms de champs sensibles normalisés (`baseUrl`, `access-token`), idempotence de la persistance après scellement.

### Points confirmés conformes

- Extraction défensive des tokens et absence de double comptage par défaut.
- Écriture atomique (`tmp` + `fsync` + `os.replace`) et inclusion dans `checksums.sha256`.
- Aucun prompt, message ou clé d'API dans `usage.json` ni dans la réponse REST.
- Isolation par `report_id` et compatibilité des appels LLM existants (Graphiti, OASIS, autres services) préservée.

### Verdict

**Conforme aux AC1–AC6 après correctifs.** Filet complet : **1 920 tests hôte verts** (dont 40 tests hermétiques dédiés à la story) + 9 tests Node frontend. `ruff check` et `validate_plans.py` au vert.

---

## Notes de complétion

- **Divergences assumées par rapport au plan initial** :
  - Le champ `billing_mode` a été ajouté à `ReportLLMProfile` pour rendre la gratuité explicite plutôt que déduite du seul `provider_id`. Cela évite de facturer à tort un run gratuit et de déclarer gratuit un modèle payant.
  - `duration_seconds` désigne désormais le temps d'inférence cumulé ; le temps mural est conservé dans `wall_seconds`. Le critère AC1 reste satisfait et AC2 devient mesurable sans biais.
  - `usage.json` n'est pas réécrit après le scellement de l'archive d'audit : l'idempotence prime sur l'actualisation tardive d'une durée.
  - Un modèle facturable absent de la grille tarifaire provoque un arrêt Fail-Closed (`pricing_unavailable`) au lieu d'un plafond silencieusement inopérant.
- **Limite connue** : le plafond temporel est vérifié avant chaque tentative HTTP et borné par le `timeout` transmis au SDK ; il ne peut pas interrompre de force une requête déjà bloquée côté fournisseur au-delà de ce timeout.
- **Validation** : `uv run pytest tests/ -q` → **1 920 passed** ; `uv run ruff check .` → propre ; `uv run python scripts/validate_plans.py` → structure valide. Les nouveaux tests couvrent les coûts, la gratuité locale, l'usage manquant, les cumuls par phase, les arrêts budget/timeout, l'API, les secrets et l'archive d'audit.
