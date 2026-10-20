---
id: "013-4"
epic: "013"
titre: "Télémétrie d'usage, mesure des temps et plafonds budgétaires"
statut: done
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

1. **Table de tarification standard (`PricingTable`)** — valeurs reprises de la table de référence du PRD source (§6, captures du 19 octobre 2026) :
   ```python
   DEFAULT_PRICING = {
       "gemini-3.8-flash": {
           "input_cost_per_million": 1.50,
           "output_cost_per_million": 7.50,
           "currency": "USD",
       },
       "deepseek-v4-pro": {
           "input_cost_per_million": 1.74,
           "output_cost_per_million": 3.84,
           "currency": "USD",
       },
       "gpt-6.1-sol": {
           "input_cost_per_million": 2.00,
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

- **Politique de gratuité explicite** : `PricingTable` distingue les passerelles locales (`antigravity-local`, `codex-local`, `local`, `ollama`) et les modèles explicitement gratuits (`-free`, `:free`, `free-`). Le champ `billing_mode` (`auto`, `free`, `metered`) de `ReportLLMProfile` rend la gratuité déclarative : `free` n'est honoré que si la grille ne prouve pas le modèle facturable, et `metered` arme le Fail-Closed. Un modèle gratuit reste à `0.00 $` même hors grille tarifaire, tout en conservant un `theoretical_cost_usd` informatif (ou `None` s'il n'est pas calculable).
- **Table tarifaire datée** : `PRICING_TABLE_VERSION = "2026-10-19"` ; les tarifs sont indicatifs et jamais présentés comme une facture. `estimated_cost_usd` vaut `None` dès qu'un appel n'a pas d'`usage` exploitable.
- **Tokens de réflexion** : extraction défensive depuis `completion_tokens_details.reasoning_tokens`, puis `reasoning_tokens` et `output_tokens_details`. Ils sont considérés comme un sous-ensemble de `completion_tokens` ; un tarif séparé n'est appliqué que si `thinking_billed_separately` est vrai.
- **Durées** : `duration_seconds` est la somme des temps d'inférence mesurés par appel ; `wall_seconds` conserve le temps mural du job (outils, E/S, audits compris).
- **Couverture des outils** : `ReportAgent` injecte son client LLM profilé dans `ZepToolsService` (`llm_client=self.llm`) et bascule en phase `interviews` autour de l'outil d'interview. Les appels d'outils sont donc mesurés et soumis au même garde-fou.
- **Garde-fou à deux niveaux** : contrôle aux frontières (planification, sections, outils, audit) et `pre_request_callback` dans `LLMClient`, qui bloque chaque tentative HTTP, y compris les relances JSON et les reprises anti-troncature. Le temps restant est transmis comme `timeout` de la requête OpenAI-compatible.
- **Fail-Closed tarifaire** : un modèle facturable absent de la grille déclenche `ReportBudgetExceededError` plutôt que de traiter « inconnu » comme gratuit — mais seulement sur un profil `billing_mode="metered"`, pour qu'un run gratuit ou non tarifé ne soit jamais interrompu. Une erreur `usage` manquante, elle, reste marquée inconnue sans fabriquer de coût (AT-12).
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

**Conforme aux AC1–AC6 après correctifs.** Deuxième passe de revue contradictoire (19-20 octobre 2026) : 14 findings corrigés, dont quatre arbitrages tranchés (périmètre du Fail-Closed, sémantique de `billing_mode`, preuve de l'effort effectif, source des prix alignée sur le PRD source). Filet complet : **1 939 tests hôte verts** (dont 59 tests hermétiques dédiés à la story) + 9 tests Node frontend. `ruff check` et `validate_plans.py` au vert.

### Review Findings

Revue contradictoire BMAD à quatre couches (`blind-hunter`, `edge-case-hunter`, `verification-gap`, `acceptance-auditor`) menée le 19 octobre 2026 sur le commit `9659397`, puis vérification de chaque finding contre le code réel. Filet mesuré : `pytest --collect-only` → **1 920 tests collectés**, dont **40** dans `test_report_usage_telemetry.py`.

- [x] [Review][Patch] **Source des prix : grille alignée sur la table du PRD source** — `DEFAULT_PRICING` (`backend/app/models/report_usage.py:36-57`) fixe `gemini-3.8-flash` à `0,15 / 0,60 $` et `deepseek-v4-pro` à `0,27 / 1,10 $`, alors que la table de référence du PRD source (§6, lignes 149-153, captures du 19 octobre 2026) indique `1,50 / 7,50 $` et `1,74 / 3,84 $` ; `gpt-6.1-sol` est à `2,50 $` en entrée contre `2,00 $`. Pour 1 M tokens entrée + 1 M sortie, le coût estimé est 12× trop bas sur Flash et 4× sur DeepSeek : le plafond `max_total_cost_usd` peut donc être franchi d'un ordre de grandeur avant l'arrêt, et la comparaison de coûts du benchmark est faussée. La story elle-même reprend les valeurs du code dans ses Notes de développement (§1). **Décision de revue (20 oct. 2026) : aligner la grille sur la table du PRD source.** `DEFAULT_PRICING` porte désormais 1,50 / 7,50 (Flash), 1,74 / 3,84 (DeepSeek) et 2,00 / 10,00 (gpt-6.1-sol), avec la référence de la table en commentaire. Le plafond budgétaire redevient significatif et les tests de coût suivent.

- [x] [Review][Patch] **Périmètre du Fail-Closed tarifaire** [backend/app/services/report_usage_tracker.py:665] — `FREE_PROVIDER_IDS` (`backend/app/models/report_usage.py:61`) ignore `opencode-go`, et `_infer_provider_id` (`report_usage_tracker.py:206-231`) ne reconnaît que les ports `18081`/`18080`. Les modèles réellement configurés hors des 4 entrées de `DEFAULT_PRICING` — `gpt-4o-mini` (défaut de `Config`, `backend/app/config.py:30`), `qwen-plus` (`.env.example`), `space-bunny` (OpenCode Go, §2.9 de la constitution) — ne sont ni tarifés ni gratuits : `record_call` incrémente `unpriced_model_calls`, puis `BudgetGuard.check` lève `ReportBudgetExceededError` au contrôle de section suivant ; le rapport part en `FAILED` après la seule planification. Le même garde-fou est branché sur `POST /api/report/chat` (`backend/app/api/report.py:703`), qui renvoie alors un **500 avec traceback** (`:718-723`). **Décision de revue (19 oct. 2026) : orienter le Fail-Closed sur `billing_mode="metered"`.** Le refus de démarrer ne s'applique qu'à un profil explicitement payant ; les profils `flash-medium`/`flash-high` du catalogue passent en `metered`, un run gratuit ou non tarifé n'échoue plus, et le chat n'est plus exposé au plafond d'un profil qu'il n'a pas demandé.
- [x] [Review][Patch] **Sémantique de `billing_mode`** [backend/app/services/report_usage_tracker.py:329,524] — `"metered"` est déclaré par le catalogue (`backend/app/models/report_llm_profile.py:137,146,155`) mais n'est jamais lu (seul `== "free"` est testé). À l'inverse, un `"billing_mode": "free"` fourni par le client force `cost = 0.0` sur un modèle facturable et neutralise le plafond (mesuré : `deepseek-v4-pro`, 1 M entrée + 1 M sortie → `0.0` au lieu de 1,37 $ estimés). `default_from_env` teste de plus la sous-chaîne nue `"free"` (`:92`) alors que `FREE_MODEL_MARKERS` impose `-free`/`:free`/`free-`. **Décision de revue : valider `free` contre la grille.** `free` n'est honoré (coût `0.0`) que si le modèle est réellement gratuit — passerelle locale ou marqueur de la grille — sinon repli sur `auto` ; `metered` force le coût théorique même sur une passerelle gratuite.
- [x] [Review][Patch] **`reasoning_effort_effective` sur Antigravity** [backend/app/services/report_agent.py:1293-1312] — l'effort demandé est marqué **effectif** avant tout appel LLM (`:2407`), sans confirmation issue de la réponse. AC3 exige `"unknown"` quand le provider ne renvoie pas d'`usage` : un run Antigravity sans `usage` produit `usage_available=False`, `estimated_cost_usd=None` **et** `reasoning_effort_effective="high"`. **Décision de revue : exiger une preuve par réponse.** L'effort effectif n'est renseigné qu'à partir d'une réponse porteuse d'`usage` ; sinon il reste `"unknown"`.

- [x] [Review][Patch] Arrêt contrôlé sans corps de rapport ni manifeste d'audit [backend/app/services/report_agent.py:2709-2760] — `markdown_content` n'est assemblé qu'à `:2556`, donc un arrêt budget/timeout laisse `full_report.md` absent (garde `if report.markdown_content`, `:4306`) alors que la Définition de prêt promet une « sauvegarde partielle » ; aucun `run_manifest.json`/ZIP n'est produit (le handler retourne avant `build_audit_package`) ; le statut écrit est `publication_status: "failed_validation"` sans qu'aucun `ReportQualityGate` n'ait tourné, et `update_progress(..., -1, ...)` n'a pas de contrat côté API/IHM.
- [x] [Review][Patch] Cycle de vie des callbacks sur client partagé [backend/app/services/report_usage_tracker.py:437] — `detach` compare `getattr(...) is self.handle_llm_usage` : chaque accès recrée un objet *bound method*, donc l'identité est toujours fausse et le callback précédent n'est **jamais** restauré. S'y ajoutent : `pre_request_callback` écrasé sans chaînage ni restauration (`report_agent.py:1338`, `:2835-2839` inversement au finding #12 de la revue initiale), `request_timeout` laissé à sa dernière valeur (`:1333`), et aucun ré-attachement au second `generate_report` sur la même instance (`attach_to` n'est appelé qu'en `__init__`, `:1163`) alors que `_usage_persisted` est remis à `False` à chaque génération.
- [x] [Review][Patch] Couverture de vérification de bout en bout [backend/tests/test_report_usage_telemetry.py] — six garanties ne sont pas protégées : (1) le branchement `pre_request_callback` → `_create_completion` (`llm_client.py:162-164`) n'est jamais exercé (les deux tests appellent la closure directement, `:661-677`) ; (2) le `timeout` transmis au SDK (`openai_chat_compat.py:65-67`) n'est asserté nulle part ; (3) l'effort effectif Antigravity n'est pas observé sur `generate_report` ; (4) le rétro-remplissage `usage_summary` des rapports legacy/historique n'est pas testé ; (5) `billing_mode` n'est pas couvert à `from_dict`/`to_dict` ; (6) le contrôle budgétaire d'entrée de `_execute_tool` (`report_agent.py:1466-1469`) n'est pas testé au-delà du plafond. Enfin `test_usage_endpoint_reports_corrupt_file_without_traceback` teste l'absence d'une *clé*, pas du corps sérialisé.
- [x] [Review][Patch] Résolution tarifaire approximative [backend/app/models/report_usage.py:247] — le repli `lowered.startswith(key_lower) or key_lower in lowered` fait hériter à `gemini-3.8-flash-pro` ou `qwen3.8-max-plus` le tarif du modèle de base (coût sous-estimé, plafond contourné, Fail-Closed jamais déclenché) ; le paramètre `provider_id` de `get_pricing` est accepté mais jamais lu.
- [x] [Review][Patch] Télémétrie trompeuse pour les modèles hors grille [backend/app/services/report_usage_tracker.py:375-379] — l'avertissement « coût laissé inconnu » est émis à chaque appel même quand le run est gratuit et que le coût vaut bien `0.0` (cas nominal des passerelles locales) ; et `build_metrics` agrège `theoretical_cost(...) or 0.0` (`:527-535`), ce qui publie `theoretical_cost_usd=0.0` et `pricing_available=True` pour un modèle absent de la grille — un coût théorique fabriqué, contraire à AT-12.
- [x] [Review][Patch] Contrat de `usage.json` absent ou illisible [backend/app/api/report.py:1530-1546] — la docstring promet une « liste blanche de champs », mais la branche de repli renvoie le dictionnaire hérité de `meta.json` filtré par une *blocklist* (`sanitize_usage_payload`) ; côté audit, `usage.json` n'est ajouté que s'il se charge (`simulation_audit_service.py:326-340`) — une archive scellée peut donc l'omettre en silence, alors que l'en-tête du service annonce un décompte d'artefacts qui ne correspond plus.
- [x] [Review][Patch] Télémétrie complète exposée par les endpoints de rapport [backend/app/services/report_agent.py:505] — `Report.to_dict()` embarque désormais `usage_metrics` (avec la liste `calls`), donc `GET /api/report/<id>`, `/by-simulation/<id>` et surtout `/list?limit=50` (`api/report.py:518`) restituent la télémétrie brute de chaque rapport, sans passer par la liste blanche réservée à `/usage` (volume multiplié sur la liste, aucune couverture de test).
- [x] [Review][Patch] Manifeste d'audit : version et provenance [backend/app/services/simulation_audit_service.py:149-166] — le schéma de `run_manifest.json` change (`base_url` remplacé par `base_url_configured`, ajout de `usage` et de deux champs d'effort) sans incrément de `version` (toujours `"1.0.0"`), et deux runs ciblant des passerelles différentes (18080, 18081, OpenCode Go) deviennent indistinguables — alors que la reproductibilité est l'objet de l'epic.
- [x] [Review][Patch] Validation d'entrée du profil à la frontière API [backend/app/models/report_llm_profile.py:74-82] — `"billing_mode": null` devient la chaîne `"None"` puis un 400 ; `max_total_cost_usd`/`max_wall_seconds` négatifs sont acceptés et produisent un arrêt immédiat avec un message « plafond atteint » au lieu d'une erreur explicite ; une valeur non finie retombe silencieusement à `None` dans `BudgetGuard.from_profile` (`report_usage_tracker.py:87-101`) et **désactive** le plafond.
- [x] [Review][Patch] Extrait de `architecture.md` non exécutable [docs/plans/013-benchmark-llm-report-replay/architecture.md:116-136] — `phase_totals` et `calls` sont déclarés sans valeur par défaut après des champs qui en ont une : le dataclass lèverait au chargement. Le contrat publié ne correspond pas à `report_usage.py`.

- [x] [Review][Defer] `AGENTS.md` contredit ses propres chiffres [AGENTS.md:§2.2, §3, §11] — deferred: le diff met à jour le tableau d'axes et « la tâche du moment » à 1 920 tests, mais §2.2 s'arrête à `post-011-4 : 1719`, §3 annonce « 1431 tests collectés » et §11 « 333 passed ». Fichier de contexte agent : correction hors périmètre de patch automatique.
- [x] [Review][Defer] Écart de référence du filet (1 881 → 1 920, +39 pour 40 tests) [docs/plans/013-benchmark-llm-report-replay/story-013-4.md] — deferred: `pytest --collect-only` mesure 1 920 tests et 40 dans le nouveau fichier ; la base antérieure réellement collectée était donc 1 880, non 1 881. Dérive de reporting antérieure, sans effet sur le code.
- [x] [Review][Defer] ADR manquant sur tarification, budget et accès à l'`usage` brut — deferred: exigé par le PRD source §12.4 et AGENTS.md §2.3, mais l'ADR dépend de l'arbitrage des trois décisions ci-dessus (source des prix, sémantique de `billing_mode`, périmètre du Fail-Closed).
- [x] [Review][Defer] Télémétrie du cache, des erreurs et des reprises [backend/app/models/report_usage.py:311-327] — deferred: le PRD source §6.3/§6.6 demande de comptabiliser séparément entrée, sortie, **cache** et raisonnement, et de conserver erreurs/reprises par appel ; ni `cached_tokens` ni `finish_reason` n'existent. Hors AC1–AC6 de la story, à traiter avec le banc 013-6.
- [x] [Review][Defer] `dry_run` de FR-08 (PRD source) absent — deferred: l'epic 013 (FR-07) cadre la story sur la télémétrie et les plafonds ; l'estimation sans appel LLM reste à couvrir en 013-5/013-6.
- [x] [Review][Defer] Amplification des reprises du SDK au-delà du plafond temporel [backend/app/utils/llm_client.py:133-137] — deferred: `OpenAI(...)` conserve `max_retries=2` par défaut, donc un `timeout` de temps restant peut être rejoué jusqu'à trois fois ; borner le plafond mural suppose de changer la construction du client (impact global), hors du correctif direct.

**Rejetés (avec réfutation)**

- `false` — `_persist_usage_metrics` fabriquerait `usage_available=True` pour zéro appel : la branche `tracker is None` est inatteignable, `usage_tracker` étant toujours instancié dans `ReportAgent.__init__` (`:1154`) ; le chemin réel `build_metrics()` renvoie bien `False` sans appel (`bool(self._calls)`).
- `false` — `call_index` dupliqué après fusion manuelle de `usage.json` : aucune voie du programme ne recharge puis réenregistre des appels ; `from_dict` ne fait que restaurer un état déjà écrit par `record_call`.
- `false` — hermeticité incomplète de `test_default_agent_falls_back_to_env_profile_guard` : le test n'assert que `profile_id` et les plafonds ; ni `provider_id` ni `reasoning_effort` n'entrent dans ses assertions, donc `Config.LLM_BASE_URL`/`LLM_REASONING_EFFORT` ne peuvent pas le faire varier.
- `false` — absence de mesure réelle (`mesure-013-4.md`) : aucun AC de la story ne l'exige ; l'épreuve empirique A/B est le livrable de la story 013-6.
- `low` → rejeté — `NaN` dans `usage.json`, ou plafond `NaN` : aucun producteur interne n'écrit de non-fini ; le seul chemin est un fichier ou un corps JSON forgé à la main, et la correction ajouterait de la validation pour un cas non atteint.
- `low` → rejeté — `datetime.utcnow()` (naïf/déprécié), absence de `fsync` de répertoire, import local de `sanitize_usage_payload`, usage de `ReportManager._get_usage_path` depuis l'API : cosmétique ou encapsulation, sans consommateur qui en diverge aujourd'hui.
- `low` → rejeté — `getattr(self.zep_tools, "llm", None)` instancie un `LLMClient` par effet de bord d'une propriété paresseuse (`zep_tools.py:518-522`) : le client créé est précisément celui que les outils utiliseront, donc l'instrumenter est correct ; le coût est une construction d'objet OpenAI sans appel réseau.
- `low` → rejeté — `ReportUsageMetrics.summary()` sans `profile_id` : `meta.json`, `report_history.json` et le bloc `llm` du manifeste portent déjà le profil, le modèle, le provider et l'effort ; aucune jointure n'est perdue.

---

## Notes de complétion

- **Divergences assumées par rapport au plan initial** :
  - Le champ `billing_mode` a été ajouté à `ReportLLMProfile` pour rendre la gratuité explicite plutôt que déduite du seul `provider_id`. `free` reste validé contre la grille (un modèle prouvé facturable n'est pas mis à 0 $), et `metered` arme le Fail-Closed.
  - `duration_seconds` désigne désormais le temps d'inférence cumulé ; le temps mural est conservé dans `wall_seconds`. Le critère AC1 reste satisfait et AC2 devient mesurable sans biais.
  - `usage.json` n'est pas réécrit après le scellement de l'archive d'audit : l'idempotence prime sur l'actualisation tardive d'une durée.
  - Un modèle facturable absent de la grille provoque un arrêt Fail-Closed (`pricing_unavailable`) sur un profil déclaré `metered`, au lieu d'un plafond silencieusement inopérant.
- **Limite connue** : le plafond temporel est vérifié avant chaque tentative HTTP et borné par le `timeout` transmis au SDK ; il ne peut pas interrompre de force une requête déjà bloquée côté fournisseur au-delà de ce timeout.
- **Validations et divergences de la seconde passe** :
  - **Fail-Closed tarifaire orienté `metered`** : le refus de démarrer ne s'applique plus qu'à un profil explicitement payant. Les profils `flash-medium`/`flash-high` du catalogue passent en `metered` ; un run gratuit ou non tarifé (gpt-4o-mini, qwen-plus, space-bunny) ne casse plus, et le chat n'est plus exposé au plafond.
  - **`billing_mode` effectif** : `free` n'est honoré que si la grille ne prouve pas le modèle facturable (sinon repli sur le tarif réel) ; `metered` force le calcul théorique hors passerelle gratuite. `default_from_env` réutilise `PricingTable.is_free_model` au lieu d'une sous-chaîne nue.
  - **Effort effectif prouvé** : `reasoning_effort_effective` n'est renseigné qu'à partir d'une réponse porteuse d'`usage` sur la passerelle Antigravity ; sinon `"unknown"` (AC3 à la lettre).
  - **Arrêt contrôlé réellement partiel** : la section en cours est écrite avant l'arrêt, le markdown partiel est assemblé, et le manifeste + ZIP d'audit sont produits pour un run interrompu. Le statut de progression reste `"failed"` (plus de statut `budget_exceeded` sans contrat).
  - **Cycle de vie des callbacks** : `detach` compare une référence stable (un *bound method* est recréé à chaque accès), le callback pré-requête est chaîné puis restauré avec son `request_timeout`, et la télémétrie est rebranchée au démarrage de chaque génération.
  - **Honnêteté de la télémétrie** : plus d'avertissement « coût inconnu » sur un run gratuit, plus de `theoretical_cost_usd` fabriqué à `0.0` pour un modèle hors grille, et `usage.json` toujours présent dans l'archive avec `usage_available: false` s'il manque.
  - **Manifeste d'audit en version 1.1.0** avec alias de passerelle (`antigravity-local`, `codex-local`, `external`) : deux runs de gateways différentes restent distinguables sans exposer l'URL.
  - **Grille tarifaire alignée sur le PRD source** : Flash 1,50 / 7,50, DeepSeek 1,74 / 3,84, gpt-6.1-sol 2,00 / 10,00, avec la référence datée en commentaire (l'ADR 0018 reste à écrire).
  - **Validation d'entrée du profil** : `billing_mode: null` retombe sur `auto`, les plafonds négatifs ou non finis sont refusés.
  - **Validation** : `uv run pytest tests/` → **1 939 passed** ; `uv run ruff check .` → propre ; `uv run python scripts/validate_plans.py` → structure valide. Les six garanties auparavant non couvertes (callback pré-requête, `timeout` SDK, effort effectif, rétro-remplissage legacy, `billing_mode`, contrôle d'outil) sont désormais testées.
