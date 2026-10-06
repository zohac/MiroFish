---
id: "001-3"
epic: "001"
titre: "Client LLM Graphiti portant l'en-tête de session"
statut: done
auteur: agent
format: "2"
---

# Story 001-3 — Client LLM Graphiti portant l'en-tête de session

## Pourquoi cette story

L'épreuve Graphiti local a un objectif unique : mesurer si le modèle LLM gratuit
(`space-bunny-free` sur l'endpoint OpenCode Go `https://opencode.ai/zen/go/v1`)
est capable d'extraire des entités et relations exploitables sur le document de
référence. Cette gratuité est la condition sine qua non de la rentabilité du
local-first (ADR 0004 et NFR-1 : coût marginal de 0 €).

Mais la passerelle OpenCode Go impose deux contraintes strictes :
1. Un identifiant de session stable via l'en-tête `x-opencode-session` ;
2. Un User-Agent identifiant le client (`mirofish/0.1.0`).

En l'absence de l'en-tête `x-opencode-session`, la passerelle répond
immédiatement un code d'erreur `HTTP 400 MissingSessionID`.

Dans le reste de l'application, ces exigences sont satisfaites par
`backend/app/utils/llm_compat.py` via `llm_request_headers(base_url)`.
Cependant, `graphiti-core` est une bibliothèque tierce autonome : elle utilise son
propre client LLM interne (`OpenAIGenericClient`), qui instancie directement
`AsyncOpenAI` du SDK officiel sans passer par notre couche de compatibilité.

Sans adaptation, dès le premier appel d'extraction d'un épisode par Graphiti, la
requête échouera en `MissingSessionID`. Ce serait un échec de plomberie (plumbing
bug), pas un verdict sur la capacité du modèle — or le critère de sortie **C2 du
PRD** impose strictement **0 échec d'authentification (`MissingSessionID`)**.

Cette story répond à une question unique :
> Comment fournir à `graphiti-core` un client LLM compatible qui injecte
> automatiquement les en-têtes de session requis pour OpenCode Go, demeure
> strictement neutre pour les autres fournisseurs, supporte le mode de sortie
> structurée `json_object` et relaie l'effort de raisonnement configuré ?

Elle ne mesure pas l'extraction complète (story 001-5) et ne touche pas à
l'embedder local (story 001-4). Elle lève le risque d'authentification LLM de
l'épreuve.

## Définition de prêt

- [x] Critères Given/When/Then écrits et mesurables
- [x] Aucune dépendance externe non résolue — `graphiti-core==0.30.2` est installée dans l'arbre (story 001-1b)
- [x] Stratégie de test identifiée (tests unitaires hermétiques avec mocks + sonde de vérification réelle isolée)
- [x] Documents à consulter lus — [`epic-001.md`](epic-001.md),
      [`prd.md`](prd.md) (critère C2),
      [`architecture.md`](architecture.md) §1 et §2,
      [ADR 0004](../../decisions/0004-llm-opencode-go.md),
      [`docs/LOCAL-FIRST.md` §6.3 et §12.6](../../LOCAL-FIRST.md),
      `backend/app/utils/llm_compat.py`,
      `backend/app/utils/llm_client.py`,
      `backend/app/config.py`

## Définition de fini

- [x] Un client LLM compatible Graphiti (`MiroFishLLMClient`, sous-classe de `OpenAIGenericClient`) est créé dans `backend/app/utils/graphiti_llm_client.py` et instanciable directement par `Graphiti(llm_client=...)`
- [x] L'en-tête `x-opencode-session` et le `User-Agent: mirofish/0.1.0` sont injectés automatiquement pour tout appel vers un hôte `opencode.ai` ou ses sous-domaines via `llm_request_headers(base_url)`
- [x] L'en-tête de session n'est jamais ajouté pour d'autres fournisseurs (OpenAI standard, Ollama local, vLLM), préservant la neutralité de l'adaptateur
- [x] La session honore `OPENCODE_SESSION_ID` si définie, et utilise sinon un identifiant de processus stable `_PROCESS_SESSION_ID` de manière reproductible
- [x] Le mode de sortie structurée est positionné sur `structured_output_mode="json_object"` par défaut, injectant le schéma dans le prompt pour les modèles ne supportant pas les contraintes strictes de `json_schema`
- [x] L'effort de raisonnement (`LLM_REASONING_EFFORT`, extrait par `llm_completion_kwargs()`) est transmis via `extra_body` lors des appels de complétion si configuré
- [x] Une sonde réutilisable (`backend/scripts/verifier_llm_graphiti.py`) permet d'exercer un appel réel ou simulé via le client Graphiti et de constater l'absence de `MissingSessionID` (critère C2)
- [x] Une suite de tests unitaires hermétiques (`backend/tests/test_graphiti_llm_client.py`) couvre tous les cas d'usage avec mocks, sans appel réseau ni clé en CI
- [x] Les 279 tests existants restent verts, aucun test ne régresse (total porté à 293 tests)
- [x] `ruff check .` et `scripts/validate_plans.py` passent sans avertissement ni erreur
- [x] Aucun secret (clé API ou session) n'est commité dans le dépôt

## Tâches

- [x] 1. Confirmer l'interface de `graphiti-core 0.30.2` : `OpenAIGenericClient`, `LLMConfig`, `AsyncOpenAI`, et `structured_output_mode`
- [x] 2. Écrire `backend/app/utils/graphiti_llm_client.py` implémentant `MiroFishLLMClient(OpenAIGenericClient)` avec injection de `default_headers` et transmission de `extra_body`
- [x] 3. Écrire le script de vérification `backend/scripts/verifier_llm_graphiti.py` exerçant le client avec rapport clair du résultat HTTP et détection de `MissingSessionID`
- [x] 4. Écrire les tests unitaires dans `backend/tests/test_graphiti_llm_client.py` (isolation par `monkeypatch`, mock des requêtes `chat.completions.create`, vérification des en-têtes et du payload)
- [x] 5. Vérifier la suite complète de tests (279 existants + nouveaux tests) et le lint `ruff`
- [x] 6. Exécuter la sonde de vérification en local avec les variables d'environnement actives pour prouver l'absence d'erreur `MissingSessionID`
- [x] 7. Mettre à jour la documentation et consigner les résultats dans les notes de complétion

## Notes de développement

**Ce que cette story ne doit pas faire.** Elle ne doit pas brancher l'embedder local
ni tenter de résoudre le conflit de version `sentence-transformers` (c'est l'objet
exclusif de la story **001-4**). Elle ne doit pas exécuter l'extraction des 30
chunks du document ni rédiger le rapport de mesure (c'est la story **001-5**). Elle
ne doit toucher à aucun service métier de production dans `backend/app/services/`
(l'interface `GraphStore` relève de l'epic **002**). Son rayon d'action est
strictement délimité : rendre le client LLM de Graphiti compatible avec la
passerelle OpenCode Go sans régression.

**Rectification des hypothèses de départ (`architecture.md` §1 et ADR 0004).**
Au moment de la rédaction de l'ADR 0004 et de `architecture.md` §1, la signature
exacte de `graphiti-core` n'avait pas encore été inspectée. L'ADR 0004 anticipait de
« surcharger `acompletion` », et `architecture.md` proposait un squelette avec
`async def _llm_request(...)`.
L'inspection du code de `graphiti-core==0.30.2` (installé au cours de la story 001-1b)
révèle la structure réelle :
1. `graphiti_core.llm_client.openai_generic_client.OpenAIGenericClient` hérite de
   `LLMClient`.
2. Son constructeur accepte :
   ```python
   def __init__(
       self,
       config: LLMConfig | None = None,
       cache: bool = False,
       client: typing.Any = None,
       max_tokens: int = 16384,
       structured_output_mode: StructuredOutputMode = 'json_schema',
   )
   ```
3. Si `client is None`, il fait :
   ```python
   self.client = AsyncOpenAI(api_key=config.api_key, base_url=config.base_url)
   ```
   sans injecter de `default_headers`. C'est là que réside l'omission des en-têtes.
4. Les appels de génération passent par `generate_response(...)` ->
   `_generate_response_with_retry(...)` -> `_generate_response(...)`.
5. Dans `_generate_response(...)`, l'appel au client est :
   ```python
   response = await self.client.chat.completions.create(
       model=self.model or DEFAULT_MODEL,
       messages=openai_messages,
       temperature=self.temperature,
       max_tokens=max_tokens,
       response_format=self._build_response_format(response_model),
   )
   ```

**Mécanisme d'injection des en-têtes via `default_headers`.**
Le client `AsyncOpenAI` accepte un argument `default_headers` lors de son
instanciation. En fournissant les en-têtes construits par
`llm_request_headers(base_url)` (`backend/app/utils/llm_compat.py`), tous les appels
asynchrones de complétion émis par Graphiti porteront systématiquement
`x-opencode-session` et `User-Agent: mirofish/0.1.0`. Cette approche évite de
monkey-patcher les couches de transport HTTP et respecte les interfaces officielles
du SDK OpenAI et de Graphiti.

**Support du mode `json_object` pour `space-bunny-free`.**
`OpenAIGenericClient` supporte déjà nativement
`structured_output_mode="json_object"`. Dans ce mode :
- `_build_response_format` produit `{"type": "json_object"}` au lieu d'un schéma JSON
  strict (`json_schema`) que les modèles gratuits ou passerelles compatibles
  OpenAI rejettent fréquemment ;
- `LLMClient.generate_response` injecte automatiquement le schéma Pydantic
  sérialisé dans le prompt du dernier message utilisateur.
`MiroFishLLMClient` doit donc configurer ce mode par défaut pour OpenCode Go, tout
en laissant la possibilité de spécifier `json_schema` pour les fournisseurs qui le
supportent strictement.

**Transmission de l'effort de raisonnement (`reasoning_effort`).**
Lorsque `LLM_REASONING_EFFORT` est positionné (ex: `high`), `llm_completion_kwargs()`
fournit `{"reasoning_effort": effort}`. Pour que ce paramètre soit pris en compte
par OpenCode Go, `_generate_response` dans `MiroFishLLMClient` doit relayer ces
arguments via `extra_body` lors de l'appel à `self.client.chat.completions.create(...)`.

**Stratégie de test : étanchéité absolue en CI.**
Conformément à AGENTS.md §2.2 :
- Aucun test automatisé ne doit appeler l'API réseau d'OpenCode Go ni dépendre de
  secrets locaux (`auth.json` ou `.env`).
- Les tests unitaires doivent simuler le comportement du SDK OpenAI à l'aide de
  mocks et vérifier que les en-têtes transmis à `AsyncOpenAI` et les arguments passés
  à `chat.completions.create` sont conformes aux attentes selon les URLs et les
  variables d'environnement.
- L'exercice d'un appel réel fait l'objet d'un script de vérification séparé
  (`verifier_llm_graphiti.py`), exécutable manuellement lorsque les clés sont
  présentes.

## Revue

Revue contradictoire menée par 4 couches indépendantes (blind-hunter, edge-case-hunter, verification-gap, acceptance-auditor).
Bilan du triage : 0 decision-needed, 6 patch, 0 defer, 5 rejetés.

### Constats de revue retenus (Patch)

- [x] [Review][Patch] Filtrage des balises `<think>` pour les modèles de raisonnement (`backend/app/utils/graphiti_llm_client.py:128`)
- [x] [Review][Patch] Fiabilisation de la sonde mockée pour tester la vraie injection de headers (`backend/scripts/verifier_llm_graphiti.py:64-77`)
- [x] [Review][Patch] Alignement du statut de la story en `review` pendant le cycle de revue (AGENTS.md §2.8)
- [x] [Review][Patch] Neutralité stricte si `config.base_url=None` (`backend/app/utils/graphiti_llm_client.py:73`)
- [x] [Review][Patch] Protection contre `choices=[]` via `EmptyResponseError` (`backend/app/utils/graphiti_llm_client.py:125`)
- [x] [Review][Patch] Exercice de la méthode publique `generate_response` dans les tests de raisonnement (`backend/tests/test_graphiti_llm_client.py:143`)

### Rejets documentés

- `extra_body` vs kwargs directs (`graphiti_llm_client.py:122`) : faux positif, `extra_body` est le mécanisme standard et sûr du SDK OpenAI pour transmettre des champs de requête non typés.
- Mutation des objets `Message.content` (`graphiti_llm_client.py:103`) : faux positif, opération de nettoyage utf-8 idempotente conforme à l'implémentation amont de Graphiti.
- Rôles de messages autres que user/system/assistant (`graphiti_llm_client.py:104-109`) : faux positif, Graphiti n'utilise aucun rôle d'outil/fonction.
- Message avec `content=None` (`graphiti_llm_client.py:103`) : faux positif, le modèle Pydantic `Message` rejette `None` dès l'instanciation.
- Export dans `app/utils/__init__.py` : rejeté (faible impact), les imports se font par chemin direct de module.

## Notes de complétion

La story 001-3 est terminée avec succès et validée par revue de code (4 couches contradictoires, 6 correctifs appliqués) :
- `backend/app/utils/graphiti_llm_client.py` : implémentation de `MiroFishLLMClient(OpenAIGenericClient)` avec injection des en-têtes `default_headers` via `llm_request_headers()`, neutralité garantie avec `config.base_url=None`, mode `json_object` par défaut, relai de `LLM_REASONING_EFFORT` via `extra_body`, nettoyage des balises `<think>` et sécurisation contre les listes `choices` vides.
- `backend/scripts/verifier_llm_graphiti.py` : script de vérification réutilisable et autonome dont le mode `--mock` exerce réellement le constructeur de `MiroFishLLMClient` et valide la présence de `x-opencode-session`.
- Preuve négative et positive du critère C2 :
  - Sans `x-opencode-session` : OpenCode Go répond immédiatement `HTTP 400 MissingSessionID` (`Request is missing x-opencode-session`).
  - Avec `MiroFishLLMClient` : `x-opencode-session` est transmis et accepté par la passerelle OpenCode Go (0 échec `MissingSessionID`).
- `backend/tests/test_graphiti_llm_client.py` : 16 tests unitaires hermétiques (+1 test d'exécution de sonde mockée), portant le total de la suite de tests de 279 à 296 tests (100% verts).
- Linter `ruff` et validateur de structure `validate_plans.py` passent sans avertissement.

