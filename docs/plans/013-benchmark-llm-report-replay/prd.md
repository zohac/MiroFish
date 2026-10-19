# PRD — Epic 013 : Benchmark LLM du ReportAgent et régénération non destructive sur simulation existante

> **Projet** : MiroFish, branche `local-first`  
> **Statut** : Cadrage validé / En cours d'implémentation  
> **Date** : 19 octobre 2026  
> **Base de code consultée** : `zohac/MiroFish`, commit `b0c668d`  
> **Planification** : Epic 013 (`docs/plans/013-benchmark-llm-report-replay/`)  
> **Périmètre** : backend de rapports, configuration LLM, API, écran de génération de rapport, audits et tests.  
> **Hors périmètre initial** : relancer OASIS, refaire les graphes et modifier les règles métier Keova.

---

## 1. Résumé de décision

**Problème à résoudre.** Les simulations MiroFish sont orchestrées de bout en bout. Le modèle déclaré pour les derniers essais Keova est `gemini-3.8-flash`, utilisé avec un effort de raisonnement `medium` selon la configuration de l'utilisateur. Le septième essai (R7) produit une analyse riche, mais son audit ne vérifie aucune des 167 affirmations extraites et refuse la publication automatique (`needs_review` via la barrière Fail-Closed de l'Epic 012). Nous ignorons quelle part de ces erreurs vient du raisonnement du LLM et quelle part du pipeline de récupération, de rédaction et de vérification.

**Décision expérimentale.** Ne pas lancer immédiatement une huitième simulation complète. Ajouter la possibilité de **régénérer seulement le rapport à partir d'un même run**, avec une **configuration LLM par rapport** et une comparaison reproductible. Commencer par **`gemini-3.8-flash` en `high`**, face à la référence `medium` (sur le serveur Antigravity local actuel). Puis seulement, couper le serveur Antigravity pour basculer sur l'API OpenCode GO si l'on souhaite tester d'autres modèles du catalogue (`deepseek-v4-pro`, `qwen3.8-max`, `gpt-6.1-sol`, etc.). Garder un modèle Codex coûteux comme arbitre ponctuel, non comme modèle par défaut.

**Bénéfice** : isoler et mesurer la contribution du modèle, éliminer le coût et le temps des 72h de simulation OASIS.  
**Coût** : développement du mode replay, isolation multi-rapports sans écrasement, métriques de consommation et sélecteur UI.  
**Risque principal** : comparer des rapports ne disposant pas exactement des mêmes preuves, ou attribuer au modèle un échec du vérificateur.  

---

## 2. Contexte vérifié et hypothèses

### 2.1 Faits établis dans `local-first`

| Point | Constat dans `local-first` |
|---|---|
| Configuration LLM actuelle | `backend/app/config.py` expose `LLM_BASE_URL`, `LLM_MODEL_NAME`, `LLM_REASONING_EFFORT` globaux. |
| Effort de raisonnement | `backend/app/utils/llm_compat.py` transmet `reasoning_effort` s'il est configuré dans l'environnement. |
| Client partagé | `backend/app/utils/llm_client.py` accepte `api_key`, `base_url`, `model`, mais pas de paramètre d'effort propre à une instance. |
| Compatibilité des requêtes | `backend/app/utils/openai_chat_compat.py` appelle `llm_completion_kwargs()` sans paramètre, lisant `os.environ`. |
| Serveur Antigravity local | `backend/scripts/antigravity_proxy.py` écoute sur le port 18081 et relaie vers Google Cloud Code Assist, mais n'extrait pas `reasoning_effort` du body OpenAI. |
| ReportAgent | `backend/app/services/report_agent.py` reçoit un `llm_client` optionnel et utilise `LLMClient()` par défaut. Il planifie, rédige, vérifie et persiste l'audit. |
| Remplacement destructif (R4) | `ReportAgent` persiste `report_claims.json`, `cohort_coverage.json` et `quality_checks.json` directement sous `simulations/<sim_id>/`, écrasant les runs précédents d'un même simulateur. |
| Clôture OASIS | La génération ferme l'environnement OASIS dans `finally`. Une régénération ultérieure ne dispose plus des interviews live. |
| Situation observée en R7 | `report_claims.json` : 167 affirmations, 0 vérifiée. `quality_checks.json` : `needs_review` / `is_publishable=false`. |

---

## 3. Objectifs et non-objectifs

### Objectifs

1. Générer **N versions de rapport distinctes pour un unique `simulation_id`**, chacune avec un profil LLM explicitement enregistré (`ReportLLMProfile`).
2. Permettre une comparaison `medium` vs `high` **sans recalcul d'ontologie, de profils, de graphe, de rounds OASIS ni de nouveaux posts**.
3. **Figer et rendre reproductibles les entrées consultées par le ReportAgent** via le mode `replay_frozen` (empreinte SHA-256).
4. Assurer la prise en compte réelle de `reasoning_effort` tant sur le proxy local Antigravity que sur OpenCode GO.
5. Conserver l'ancien rapport et son dossier d'audit complet sans écrasement destructif sous `reports/<report_id>/`.
6. Maintenir les barrières `fail-closed` et la séparation épistémique des sources (Epics 011/012).

### Non-objectifs (V1)

- Relancer des rounds OASIS pour le benchmark de rapport.
- Basculer aveuglément vers des modèles payants sans budget explicite.
- Altérer les barrières de qualité pour forcer un passage artificiel en `verified_publishable`.

---

## 4. Exigences Fonctionnelles (FR)

- **FR-01** : Configuration LLM dédiée par job de rapport (`ReportLLMProfile`), défaut rétrocompatible.
- **FR-02** : Transmission explicite de `reasoning_effort` (`low`, `medium`, `high`) sans altérer `os.environ`.
- **FR-03** : Traduction effective de `reasoning_effort` en `thinkingConfig` dans le proxy local Antigravity pour `gemini-3.8-flash`.
- **FR-04** : Régénération d'un rapport sur un run existant sans relancer OASIS (mode `replay_frozen`).
- **FR-05** : Empreinte cryptographique (hash SHA-256) du jeu de preuves figé garantissant la stricte parité A/B.
- **FR-06** : Isolation étanche des rapports, claims, cohortes et audits sous `reports/<report_id>/` (0 écrasement).
- **FR-07** : Endpoints API REST étendus : historique des rapports par simulation, déclenchement avec profil et mode de rejeu.
- **FR-08** : Télémétrie d'usage, mesure de durée et estimation de coût par génération.
- **FR-09** : Interface utilisateur Vue 3 (Step4) intégrant le sélecteur de rapport, bouton de régénération avec profil et diff de statut qualité.
- **FR-10** : Banc d'orchestration global A/B évaluant formellement la campagne de qualification de l'Epic 013.

---

## 5. Exigences Non Fonctionnelles (NFR)

- **NFR-1 : Généricité absolue** : Aucune logique codée en dur pour Keova ; modèles et profils configurables.
- **NFR-2 : Non-régression totale** : Préservation des 1 842 tests hôte + 9 tests frontend existants.
- **NFR-3 : Sûreté et concurrence** : Deux jobs simultanés sur des profils distincts ne doivent jamais contaminer leurs paramètres respectifs.
- **NFR-4 : Zéro fuite de secrets** : Les clés API et tokens ne doivent jamais apparaître dans les logs de télémétrie ou les manifestes.
