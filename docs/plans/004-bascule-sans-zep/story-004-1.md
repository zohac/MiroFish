---
id: "004-1"
epic: "004"
titre: "Paramétrabilité universelle du LLM et consolidation de llm_compat.py"
statut: done
auteur: agent
format: "2"
---

# Story 004-1 — Paramétrabilité universelle du LLM et consolidation de `llm_compat.py`

## Définition de prêt

- [x] Objectif compris : rendre la configuration LLM universelle et 100 % pilotée par `.env` (compatible OpenAI, gratuit ou payant), avec OpenCode Go `space-bunny-free` comme référence de test sans régression.
- [x] Documents consultés : [PRD](prd.md), [Architecture](architecture.md), [Epic 004](epic-004.md), [`backend/app/config.py`](file:///Users/simon/dev/MiroFish/backend/app/config.py), [`backend/app/utils/llm_compat.py`](file:///Users/simon/dev/MiroFish/backend/app/utils/llm_compat.py), [`backend/app/utils/llm_client.py`](file:///Users/simon/dev/MiroFish/backend/app/utils/llm_client.py), [`backend/app/utils/graphiti_llm_client.py`](file:///Users/simon/dev/MiroFish/backend/app/utils/graphiti_llm_client.py), [`backend/app/utils/openai_chat_compat.py`](file:///Users/simon/dev/MiroFish/backend/app/utils/openai_chat_compat.py).
- [x] Neutralité vérifiée : `x-opencode-session` ne doit être émis que vers `opencode.ai` ou ses sous-domaines. Aucun en-tête propriétaire pour les autres fournisseurs (OpenAI, DeepSeek, Groq, Ollama, etc.).
- [x] Stratégie de test identifiée : tests unitaires hermétiques validant la lecture des variables `.env`, l'exposition dans `Config`, le comportement de `llm_compat.py` et l'absence de fuite d'en-têtes sur endpoints tiers.

## Définition de fini

- [x] `Config` expose formellement `LLM_REASONING_EFFORT` chargé depuis `.env` / environnement.
- [x] `llm_compat.py` garantit une isolation stricte : injection de `x-opencode-session` uniquement pour `opencode.ai` et ses sous-domaines, en-têtes neutres (`User-Agent`) pour tout autre hôte.
- [x] `llm_client.py` et `graphiti_llm_client.py` consomment de manière uniforme les variables `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL_NAME`, `LLM_REASONING_EFFORT`.
- [x] Les tests unitaires couvrent la configuration `.env`, les différents types de fournisseurs (OpenCode, OpenAI direct, hôte local Ollama/vLLM, passerelle tierce) et la transmission de l'effort de raisonnement.
- [x] Tous les tests existants et nouveaux restent verts (filet ≥ 562 tests, atteint : 571 tests).
- [x] Linter `ruff check .` sans avertissement ni erreur.

## Tâches

- [x] Exposer `LLM_REASONING_EFFORT` dans `Config` (`backend/app/config.py`).
- [x] Consolider `backend/app/utils/llm_compat.py` pour unifier l'accès à `Config.LLM_REASONING_EFFORT` avec repli propre sur `os.environ`.
- [x] Vérifier la cohérence de transmission de `reasoning_effort` dans `backend/app/utils/openai_chat_compat.py` et `backend/app/utils/graphiti_llm_client.py`.
- [x] Écrire et enrichir la suite de tests unitaires dans `backend/tests/test_llm_compat.py` pour valider l'universalité et la neutralité des fournisseurs tiers (DeepSeek, Groq, Ollama local, OpenAI officiel).
- [x] Valider l'exécution des tests (`uv run pytest tests/ -q`) et le lint (`uv run ruff check .`).

## Notes de développement

La paramétrabilité universelle du LLM est un pilier de l'indépendance de MiroFish.
L'utilisateur doit pouvoir utiliser :
1. Soit l'endpoint de référence gratuit OpenCode Go (`https://opencode.ai/zen/go/v1`, modèle `space-bunny-free`) qui nécessite la session `x-opencode-session` et supporte `reasoning_effort` ;
2. Soit tout endpoint payant ou local compatible OpenAI (`https://api.openai.com/v1`, `https://api.deepseek.com/v1`, `https://api.groq.com/openai/v1`, `http://localhost:11434/v1`) avec n'importe quelle clé et modèle, sans subir l'injection d'en-têtes inattendus.

`Config` centralise la lecture de ces variables depuis `.env`. `llm_compat.py` applique la logique d'aiguillage sur l'URL de base.
La résolution des paramètres d'initialisation dans `LLMClient` a été alignée sur celle de `MiroFishLLMClient` pour lire de façon consistante `os.environ` puis `Config`.

## Revue

- **Couche Contrat & Architecture** :
  - `Config.LLM_REASONING_EFFORT` est déclaré et documenté.
  - La neutralité d'hôte est prouvée : `_requires_session_header` n'est actif que sur `opencode.ai` ou ses sous-domaines (gestion robuste des URLs avec ou sans scheme `https://`).
  - Aucun en-tête `x-opencode-session` n'est envoyé vers OpenAI, DeepSeek, Groq, Mistral ou des endpoints locaux (Ollama, vLLM).
- **Couche Hermétisme & Sécurité** :
  - Aucun secret en dur.
  - Les tests sont isolés et utilisent des mocks ou `monkeypatch` pour garantir l'indépendance de l'environnement de la machine.
- **Couche Tests & Qualité** :
  - 22 tests unitaires dédiés dans `test_llm_compat.py` et `test_llm_client.py`.
  - 16 tests unitaires pour `MiroFishLLMClient` (`test_graphiti_llm_client.py`).
  - Filet global de tests porté à 571 tests verts (+9).
  - `ruff check .` impeccable.

## Notes de complétion

La Story 004-1 a atteint l'ensemble de ses objectifs :
1. **Paramétrabilité universelle** :
   - `Config.LLM_REASONING_EFFORT` a été formellement intégré et typé dans `backend/app/config.py`.
   - `LLMClient` (`backend/app/utils/llm_client.py`) et `MiroFishLLMClient` (`backend/app/utils/graphiti_llm_client.py`) résolvent désormais de façon parfaitement homogène les paramètres LLM (`api_key`, `base_url`, `model`, `reasoning_effort`) depuis l'environnement ou `Config`.
2. **Neutralité stricte des tiers** :
   - `_requires_session_header` dans `backend/app/utils/llm_compat.py` n'active l'en-tête `x-opencode-session` QUE pour `opencode.ai` et ses sous-domaines, avec support robuste des URLs sans scheme (`https://`).
   - Pour tout fournisseur tiers (OpenAI officiel, DeepSeek, Groq, Mistral, Ollama/vLLM locaux), seul l'en-tête neutre `User-Agent: mirofish/0.1.0` est envoyé.
3. **Transmission de l'effort de raisonnement** :
   - `llm_completion_kwargs()` accepte un effort explicite optionnel ou résout `LLM_REASONING_EFFORT` dynamiquement sans fuite d'état ni rupture d'hermétisme des tests.
4. **Validation et filets de test** :
   - 22 tests unitaires dédiés (`test_llm_compat.py` et `test_llm_client.py`).
   - Filet global de tests porté de 562 à **571 tests 100 % verts**.
   - Lint `ruff check .` impeccable.
   - Aucun secret ni token dans le code.
