# Epic 004 — Construire un graphe en local sans clé Zep

- **Statut** : `in-progress` · **Dépend de** : 001, 002, 003 · **Bloque** : 005, 006, 007
- **Suivi** : [`sprint-status.yaml`](../../sprint-status.yaml)

> L'Epic 001 a prouvé la faisabilité de la chaîne Graphiti + Neo4j 5.26 + OpenCode Go à coût marginal nul.
> L'Epic 002 a isolé MiroFish derrière l'interface `GraphStore` (470 tests verts).
> L'Epic 003 a concrétisé le backend local `GraphitiGraphStore`, validé le chemin de lecture et réussi l'épreuve d'intégration réelle Neo4j (562 tests verts).
>
> **Cet Epic 004 franchit le pas de la bascule local-first complète** : il supprime tout blocage lié à la clé Zep Cloud
> dans l'application, rend la configuration du LLM universellement paramétrable via `.env`, et démontre l'ingestion,
> la construction de graphe, la génération de personas et la simulation en 100 % local sans aucune dépendance cloud Zep.

**Artefacts de ce dossier** — [`prd.md`](prd.md) (quoi, pourquoi, critères chiffrés) ·
[`architecture.md`](architecture.md) (comment, modèles et flux de données) · ce fichier (le contrat
d'ingénierie) · `story-004-<n>.md` (une story démarrée = un fichier markdown).

---

## Le problème en une phrase

L'application MiroFish bloque encore l'utilisateur si `ZEP_API_KEY` est absente de l'environnement (gardes HTTP 400 dans l'API et instanciations en dur) et le choix du LLM doit être totalement paramétrable via `.env` (endpoint, modèle, clé, effort de raisonnement) pour fonctionner avec n'importe quel fournisseur compatible OpenAI sans couplage rigide.

---

## Objectif

1. Rendre `ZEP_API_KEY` strictement facultative dans `backend/app/config.py` et dans 100 % des routes de `backend/app/api/` (`graph.py`, `simulation.py`) dès lors que `ZEP_BACKEND='graphiti'` est configuré.
2. Centraliser et homogénéiser la paramétrabilité universelle du LLM via `.env` (`LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL_NAME`, `LLM_REASONING_EFFORT`), en garantissant la neutralité pour les fournisseurs tiers et l'injection transparente des en-têtes OpenCode Go (`x-opencode-session`) uniquement lorsque l'hôte est `opencode.ai`.
3. Valider la construction de graphe de bout en bout depuis un document réel (`GraphBuilderService` → `GraphitiGraphStore` → Neo4j local) avec suivi asynchrone par `TaskManager`.
4. Valider l'extraction d'entités et la génération de personas OASIS et de configuration de simulation sans appel ni clé Zep.
5. Démontrer la non-régression absolue sur l'ensemble du filet de tests existant (562 tests verts).

---

## Exigences fonctionnelles

| # | Exigence |
|---|---|
| FR-1 | Paramétrabilité universelle du LLM : support complet et cohérent de `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL_NAME` et `LLM_REASONING_EFFORT` dans `Config`, `LLMClient` et `MiroFishLLMClient`. |
| FR-2 | Conditionnement strict de l'adaptateur de session dans `llm_compat.py` : injection de `x-opencode-session` et `User-Agent` uniquement pour l'hôte `opencode.ai`, neutralité stricte pour les autres hôtes. |
| FR-3 | Levée des gardes bloquants `400 ZEP_API_KEY not configured` dans `backend/app/api/graph.py` et `backend/app/api/simulation.py` lorsque `ZEP_BACKEND == 'graphiti'`. |
| FR-4 | Adaptation des services métiers (`GraphBuilderService`, `ZepEntityReader`, `OasisProfileGenerator`, `ZepGraphMemoryManager`, `zep_tools`) pour accepter `api_key=None` et déléguer proprement à la factory `get_graph_store()`. |
| FR-5 | Ingestion et construction de graphe locale de bout en bout : découpage en chunks, persistance Graphiti dans Neo4j local via `add_text_batch` et progression de la tâche jusqu'à `COMPLETED`. |
| FR-6 | Extraction d'entités et enrichissement des personas sans Zep : `simulation_config_generator.py` et `oasis_profile_generator.py` opérationnels sur le graphe local via `ZepEntityReader`. |
| FR-7 | Banc de qualification local-first autonome démontrant le cycle complet documents → graphe → personas sans aucune clé Zep. |

---

## Exigences non fonctionnelles

| # | Exigence | Pourquoi |
|---|---|---|
| NFR-1 | Zéro régression Zep Cloud | Si un utilisateur configure explicitement `ZEP_BACKEND='cloud'` avec `ZEP_API_KEY`, le comportement hérité reste 100 % opérationnel. |
| NFR-2 | Clean Architecture & DRY | Aucune bifurcation conditionnelle `if zep else graphiti` dans les services métiers. Toute l'abstraction passe par `GraphStore`. |
| NFR-3 | Hermétisme des tests | Les tests unitaires mockent l'environnement et n'exigent ni connexion réseau sortante ni instance active par défaut. |
| NFR-4 | Coût marginal nul en environnement de test | Le banc d'épreuve et les tests de référence s'exécutent avec OpenCode Go (`space-bunny-free`) et Neo4j local à 0 € de frais API. |
| NFR-5 | Robustesse face aux pannes | En cas d'indisponibilité de Neo4j ou du LLM, remonter des erreurs explicites dans les tâches plutôt que des plantages silencieux. |

---

## UX requirements

- Pour le frontend Vue, les contrats d'API JSON (`/api/graph/*`, `/api/simulation/*`) demeurent rigoureusement identiques.
- L'interface ne doit plus forcer la saisie d'une clé Zep Cloud pour créer un projet ou démarrer une simulation dès que le backend opère en local (`graphiti`).

---

## Index des stories

| Story | Titre | Statut | Fichier |
|---|---|---|---|
| 004-1 | Paramétrabilité universelle du LLM et consolidation de `llm_compat.py` | `done` | [`story-004-1.md`](story-004-1.md) |
| 004-2 | Levée des gardes `ZEP_API_KEY` dans les routes API et les services métiers | `done` | [`story-004-2.md`](story-004-2.md) |
| 004-3 | Ingestion et construction de graphe de bout en bout avec `GraphitiGraphStore` | `done` | [`story-004-3.md`](story-004-3.md) |
| 004-4 | Extraction d'entités, génération de personas et configuration de simulation sans Zep | `done` | [`story-004-4.md`](story-004-4.md) |
| 004-5 | Banc de test de qualification local-first et clôture de l'Epic 004 | `backlog` | [`story-004-5.md`](story-004-5.md) |

| Story | Critères d'acceptation (résumé) |
|---|---|
| 004-1 | Given la configuration dans `.env`, when `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL_NAME` et `LLM_REASONING_EFFORT` sont définis, then `llm_client.py` et `graphiti_llm_client.py` les consomment de manière uniforme ; when l'hôte n'est pas `opencode.ai`, then aucun en-tête `x-opencode-session` n'est envoyé ; des tests unitaires valident l'isolation des en-têtes et le passage de l'effort de raisonnement. |
| 004-2 | Given `ZEP_BACKEND='graphiti'`, when `ZEP_API_KEY` est absente de l'environnement, then `Config.validate()` ne signale aucune erreur ; les routes `/api/graph/build`, `/api/graph/<id>/data`, `/api/graph/<id>` (DELETE) et `/api/simulation/create` s'exécutent sans renvoyer d'erreur 400 de clé manquante ; `GraphBuilderService` s'instancie sans exiger de clé. |
| 004-3 | Given un document textuel soumis à `/api/graph/build` avec `ZEP_BACKEND='graphiti'`, when la tâche d'ingestion s'exécute, then elle découpe le texte, soumet les lots à `GraphitiGraphStore`, attend la persistance dans Neo4j et termine avec le statut `COMPLETED` ; les nœuds et arêtes sont consultables via `/api/graph/<id>/data`. |
| 004-4 | Given un graphe Graphiti local peuplé, when `/api/simulation/create` est appelé, then `ZepEntityReader` extrait les entités génériques sans filtrage indu ; `simulation_config_generator.py` génère les configurations de simulation et `oasis_profile_generator.py` crée les profils de personas exploitables sans aucune clé Zep. |
| 004-5 | Given l'environnement Neo4j local et OpenCode Go, when le script de qualification autonome est lancé, then le scénario complet documents → graphe → personas → simulation se déroule avec succès à 100 % en local ; les critères C1 à C5 du PRD sont satisfaits et l'Epic 004 est formellement clos. |

---

## Documents à consulter

| Document | Ce qu'on y prend |
|---|---|
| [`prd.md`](prd.md) | Objectifs et critères chiffrés C1 à C5 de l'Epic 004 |
| [`architecture.md`](architecture.md) | Cartographie des flux, résolutions LLM et diagrammes de séquence |
| [ADR 0001](../../decisions/0001-remplacement-de-zep-par-graphiti.md) | Remplacement de Zep par Graphiti + Neo4j derrière GraphStore |
| [ADR 0004](../../decisions/0004-llm-opencode-go.md) | Endpoint LLM OpenCode Go et adaptateur d'en-têtes de session |
| [ADR 0007](../../decisions/0007-une-story-un-fichier.md) | Règle une story = un fichier markdown |
| [ADR 0011](../../decisions/0011-format-2-et-sections-francais.md) | Titres de sections en français et format 2 |
| [`backend/app/config.py`](file:///Users/simon/dev/MiroFish/backend/app/config.py) | Configuration globale et validation `Config.validate()` |
| [`backend/app/utils/llm_compat.py`](file:///Users/simon/dev/MiroFish/backend/app/utils/llm_compat.py) | Adaptateur de session conditionnel et kwargs de complétion |
| [`backend/app/utils/llm_client.py`](file:///Users/simon/dev/MiroFish/backend/app/utils/llm_client.py) | Client LLM OpenAI MiroFish |
| [`backend/app/utils/graphiti_llm_client.py`](file:///Users/simon/dev/MiroFish/backend/app/utils/graphiti_llm_client.py) | Client LLM Graphiti |
| [`backend/app/services/graph_builder.py`](file:///Users/simon/dev/MiroFish/backend/app/services/graph_builder.py) | Service d'ingestion et de construction de graphe |
| [`backend/app/api/graph.py`](file:///Users/simon/dev/MiroFish/backend/app/api/graph.py) | Routes HTTP du graphe de connaissances |
| [`backend/app/api/simulation.py`](file:///Users/simon/dev/MiroFish/backend/app/api/simulation.py) | Routes HTTP de simulation et personas |

---

## Décisions liées

- **ADR 0001** — Remplacement de Zep par Graphiti + Neo4j derrière une interface unifiée
- **ADR 0003** — Ontologie dynamique différée en v2 : le chemin de lecture d'abord
- **ADR 0004** — LLM sur endpoint OpenCode Go avec session, étendu à la paramétrabilité universelle
- **ADR 0005** — Licence AGPL et distribution locale
- **ADR 0007** — Une story = un fichier markdown
- **ADR 0011** — Format 2 et sections obligatoires en français
