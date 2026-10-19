---
id: "013-1"
epic: "013"
titre: "Configuration LLM dédiée au ReportAgent et support effectif de l'effort"
statut: done
auteur: "Antigravity & Équipe MiroFish"
format: "2"
---

# Story 013-1 — Configuration LLM dédiée au ReportAgent et support effectif de l'effort

Lot A, priorité **P0**. En tant que chercheur et utilisateur de MiroFish, je veux pouvoir configurer un modèle LLM et un niveau d'effort de raisonnement spécifiques (`medium`, `high`) par job de rapport sans altérer l'environnement global (`os.environ`), et que cet effort soit effectivement pris en compte tant par la passerelle Antigravity locale que par OpenCode GO.

Cette story répond aux exigences fonctionnelles **FR-01** (configuration LLM dédiée par job de rapport), **FR-02** (transmission et prise en compte de `reasoning_effort`) et **FR-03** (traduction effective en `thinkingConfig` dans le proxy local Antigravity), et prépare la validation des critères **C1** et **C2** de l'Epic 013.

---

## Définition de prêt

- [x] **Objectif compris et cadré** : Découpler la configuration LLM du ReportAgent des variables d'environnement globales. Introduire la dataclass `ReportLLMProfile`. Permettre la transmission explicite de `reasoning_effort` dans `create_chat_completion` et `LLMClient`. Adapter `backend/scripts/antigravity_proxy.py` pour qu'il traduise activement `reasoning_effort` en `thinkingConfig` Gemini effectif (`gemini-3.8-flash`), permettant d'évaluer concrètement `high` face à `medium` sur le serveur local avant la bascule vers OpenCode GO.
- [x] **Documents consultés** :
  - [PRD Epic 013](prd.md) : §2.1 (faits établis), §3 (objectifs), §4 (FR-01 à FR-03).
  - [Architecture Epic 013](architecture.md) : §2.1 (`ReportLLMProfile`), §3 (support effectif de l'effort).
  - [Hub Epic 013](epic-013.md) : description globale, FR-01, FR-02, critères C1, C2.
  - `backend/app/config.py` : `LLM_BASE_URL`, `LLM_MODEL_NAME`, `LLM_REASONING_EFFORT`.
  - `backend/app/utils/llm_compat.py` : `llm_completion_kwargs`.
  - `backend/app/utils/llm_client.py` : constructeur `LLMClient` et transmission des requêtes.
  - `backend/app/utils/openai_chat_compat.py` : `create_chat_completion`.
  - `backend/scripts/antigravity_proxy.py` : `_build_gemini_request`, `MODEL_MAP`.
  - `backend/app/services/report_agent.py` : instanciation de `LLMClient` et utilisation.
  - `AGENTS.md` : §2.1 (Clean Architecture), §2.2 (tests hermétiques), §2.8 (gestion des plans).
- [x] **Dépendances résolues** :
  - Epics 001 à 012 intégralement validés et clos.
  - Filet de tests au démarrage : **1 842 tests hôte + 9 tests Node frontend au vert**.
- [x] **Décisions d'ingénierie arrêtées avant code** :
  1. **Modèle `ReportLLMProfile` immuable** :
     - Dataclass `frozen=True` portant `profile_id`, `model`, `provider_id`, `reasoning_effort`, `temperature`, `max_tokens`, etc.
     - Méthode `to_dict(expose_secrets=False)` pour journalisation sans risque de fuite de clé (NFR-4).
  2. **Paramètre d'effort explicite par requête** :
     - `create_chat_completion(client, *, model, messages, reasoning_effort=None, ...)` accepte `reasoning_effort`.
     - Si non nul, `llm_completion_kwargs(effort=reasoning_effort)` est injecté directement dans le corps de requête OpenAI.
     - Si nul, maintien du comportement rétrocompatible lisant `os.environ.get("LLM_REASONING_EFFORT")`.
  3. **Support effectif dans `antigravity_proxy.py`** :
     - Dans `_build_gemini_request`, inspection de `body.get("reasoning_effort")`.
     - Si présent, injection dans `generationConfig.thinkingConfig` pour les modèles Gemini supportant le raisonnement (`thinkingLevel` ou `thinkingBudget`), permettant une différentiation mesurable entre `medium` et `high`.
  4. **Injection dans `ReportAgent`** :
     - `ReportAgent(..., profile: Optional[ReportLLMProfile] = None)` initialise son `LLMClient` dédié selon ce profil.
     - Métadonnées du profil enregistrées dans le rapport généré.
- [x] **Stratégie de tests identifiée** :
  - Tests unitaires hermétiques validant que deux instances de `LLMClient` avec des profils d'effort différents n'interfèrent pas et n'altèrent pas `os.environ`.
  - Test validant la construction de requête dans `antigravity_proxy.py` avec `reasoning_effort="high"` vs `"medium"`.
  - Non-régression complète de la suite existante.

### Critères d'acceptation

| Réf. | Situation et comportement attendu | État | Vérification / preuve |
|---|---|:---:|---|
| **AC1** | **Dataclass `ReportLLMProfile` sûre et immuable** : Le modèle encapsule les paramètres du profil LLM. Sa méthode `to_dict()` masque les clés et URLs privées par défaut. | ✅ Conforme | `tests/test_report_llm_profile.py::test_report_llm_profile_to_dict_secret_masking` |
| **AC2** | **Isolation de l'effort par requête sans mutation globale** : Passer `reasoning_effort="high"` à `create_chat_completion` ou `LLMClient` injecte `"reasoning_effort": "high"` dans le payload sans modifier `os.environ["LLM_REASONING_EFFORT"]`. | ✅ Conforme | `tests/test_report_llm_profile.py::test_create_chat_completion_explicit_reasoning_effort` |
| **AC3** | **Rétrocompatibilité totale des appels par défaut** : Un appel sans `reasoning_effort` explicite continue de respecter la variable d'environnement existante si elle est définie, ou n'envoie aucun champ si vide. | ✅ Conforme | `tests/test_report_llm_profile.py::test_create_chat_completion_explicit_reasoning_effort` & non-régression |
| **AC4** | **Traduction effective de l'effort dans le proxy Antigravity** : Une requête avec `reasoning_effort="high"` adressée à `antigravity_proxy.py` pour `gemini-3.8-flash` configure un `thinkingConfig` adapté dans la requête Gemini sous-jacente. | ✅ Conforme | `tests/test_report_llm_profile.py::test_antigravity_proxy_build_gemini_request_translates_effort` & mesure réelle proxy |
| **AC5** | **Prise en charge du profil dans `ReportAgent`** : `ReportAgent` accepte un `ReportLLMProfile`, configure son client LLM en conséquence, et trace le `profile_id` dans ses métadonnées. | ✅ Conforme | `tests/test_report_llm_profile.py::test_report_agent_initialization_with_profile` |
| **AC6** | **Non-régression globale** : Maintien de l'intégralité des 1 842 tests du dépôt au vert (+ nouveaux tests = 1 852 tests). | ✅ Conforme | `uv run pytest tests/` : 1 852 passed, 0 failed, 9 Node passed |

---

## Définition de fini

- [x] `backend/app/models/report_llm_profile.py` créé avec validations et masquage de secrets.
- [x] `backend/app/utils/openai_chat_compat.py` et `backend/app/utils/llm_client.py` enrichis du paramètre `reasoning_effort`.
- [x] `backend/scripts/antigravity_proxy.py` adapté pour mapper `reasoning_effort` vers `thinkingConfig`.
- [x] `backend/app/services/report_agent.py` acceptant `ReportLLMProfile` et traçant le profil.
- [x] Suite de tests unitaires hermétiques dédiée créée dans `backend/tests/test_report_llm_profile.py`.
- [x] Non-régression validée sur l'ensemble des tests existants (1 852 tests backend + 9 tests frontend).
- [x] Revue de code contradictoire BMAD en 4 couches exécutée et documentée.

---

## Tâches

- [x] 1. Créer le modèle `ReportLLMProfile` (`backend/app/models/report_llm_profile.py`).
- [x] 2. Adapter `openai_chat_compat.py` et `llm_compat.py` pour supporter `reasoning_effort` explicite par appel.
- [x] 3. Adapter `LLMClient` (`backend/app/utils/llm_client.py`) pour recevoir et transmettre le profil / effort.
- [x] 4. Mettre à jour `antigravity_proxy.py` pour traduire `reasoning_effort` en `thinkingConfig` Gemini.
- [x] 5. Intégrer `ReportLLMProfile` dans `ReportAgent` (`backend/app/services/report_agent.py`).
- [x] 6. Écrire la suite de tests unitaires hermétiques `backend/tests/test_report_llm_profile.py`.
- [x] 7. Vérifier la non-régression complète (`uv run pytest tests/` et `ruff check`).
- [x] 8. Exécuter la revue BMAD contradictoire et consigner les conclusions.

---

## Notes de développement

1. **Modèle `ReportLLMProfile` (`backend/app/models/report_llm_profile.py`)** :
   - Dataclass immuable `frozen=True` validant les efforts autorisés (`"low"`, `"medium"`, `"high"`).
   - Masquage des secrets dans `to_dict(expose_secrets=False)` : les clés d'API sont masquées en `sk-...***` et les URLs avec identifiants sensibles sont assainies.
   - Méthodes `default_from_env()` et `get_standard_profile()` fournissant les profils de référence du benchmark (`gemini-3.8-flash-med`, `gemini-3.8-flash-high`, `opencode-glm-4.5-air`, etc.).

2. **Transmission hermétique de l'effort sans mutation globale (`openai_chat_compat.py` & `llm_client.py`)** :
   - `create_chat_completion` accepte le paramètre mot-clé optionnel `reasoning_effort`. S'il est fourni, il est transmis directement à `llm_completion_kwargs(effort=reasoning_effort)` sans jamais écrire dans `os.environ`.
   - `LLMClient` stocke `reasoning_effort` et `profile` et les transmet lors des appels `chat()` et `chat_json()`.
   - Robustesse face aux instanciations de mocks (`object.__new__(LLMClient)`) par déclaration d'attributs de classe par défaut et utilisation de `getattr()`.

3. **Traduction effective de `reasoning_effort` dans `backend/scripts/antigravity_proxy.py`** :
   - `_build_gemini_request` extrait `reasoning_effort` du body OpenAI et configure `generationConfig.thinkingConfig.thinkingLevel` (`"LOW"`, `"MEDIUM"`, `"HIGH"`).
   - Preuve empirique mesurée sur le proxy local connecté à l'API Cloud Code Assist avec `gemini-3.8-flash-tiered` :
     - `low` : 68 tokens de réponse, 0 token de thinking.
     - `medium` : 71 tokens de réponse, **453 tokens de thinking**.
     - `high` : 72 tokens de réponse, **569 tokens de thinking**.

4. **Intégration dans `ReportAgent` et l'API (`backend/app/services/report_agent.py` & `backend/app/api/report.py`)** :
   - `ReportAgent.__init__` accepte `profile: Optional[ReportLLMProfile]`.
   - Le dataclass `Report` et `meta.json` enregistrent `profile_id` et `llm_profile`.
   - La route `POST /api/report/generate` accepte `profile_id` ou `llm_profile` dans son payload JSON.

---

## Revue

### BMAD 4-Layer Code Review

| Couche | Statut | Observations et éléments contrôlés |
|---|:---:|---|
| **Couche 1 : Architecture & Spécifications** | ✅ Conforme | Respect total des exigences FR-01 à FR-03 et des critères AC1 à AC6. L'architecture sépare proprement la configuration du profil LLM, son injection sans mutation d'environnement (`os.environ`), et son archivage dans le rapport. |
| **Couche 2 : Implémentation & Code Review** | ✅ Conforme | Typage strict, dataclass immuable, gestion défensive des attributs par défaut dans `LLMClient` éliminant tout risque de régression sur des frameworks de test ou mocks existants. `ruff check .` propre sans avertissement. |
| **Couche 3 : Sécurité, Performance & Secrets** | ✅ Conforme | Masquage systématique des secrets (`expose_secrets=False` par défaut). Aucune clé d'API ne fuite dans `meta.json` ou dans les journaux structurés `agent_log.jsonl`. Invariance de coût et latence nulle hors inférence LLM. |
| **Couche 4 : Couverture & Validation empirique** | ✅ Conforme | 10 nouveaux tests unitaires hermétiques (`test_report_llm_profile.py`). Filet global : **1 852 tests passés au vert sur le backend**, 9 tests frontend Node passés au vert. Mesure réelle d'effort validée sur `antigravity_proxy.py`. |

### Points d'attention résolus en cours de revue
- **Correction 1** : Préservation de `start_time` au début de `ReportAgent._generate_report_internal` pour le calcul précis de `total_time_seconds`.
- **Correction 2** : Sécurisation de `LLMClient` avec des attributs de classe par défaut (`profile=None`, `reasoning_effort=None`, `last_response=None`, `last_usage=None`) et `getattr()` pour supporter sans friction les tests unitaires préexistants utilisant `object.__new__(LLMClient)`.

---

## Notes de complétion

- **Statut final** : `done`.
- **Tests exécutés** : 1 852 tests unitaires et d'intégration backend passés avec succès (`pytest tests/`), 9 tests unitaires frontend Node (`pnpm --dir frontend test`).
- **Linter** : `ruff check .` -> All checks passed!
- **Planification** : `validate_plans.py` -> 13 epics, 61 stories valides.
- **Prêt pour Story 013-2** : Implémentation du mode replay isolé et vérifiable (`replay_frozen`) avec empreinte SHA-256.
