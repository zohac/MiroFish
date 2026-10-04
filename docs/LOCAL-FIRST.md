# MiroFish — Installation locale, LLM OpenCode Go, et plan de remplacement de Zep

> Document de travail écrit après l'installation et l'analyse du projet.
> Les versions et chiffres ont été vérifiés sur la machine de développement
> (macOS arm64, 3 octobre 2026).

---

## 1. État de l'installation

### Ce qui est installé

| Composant | Version | Note |
|---|---|---|
| Node.js | 24.15.0 | requis >= 18 |
| Python | **3.11.15** (géré par `uv`) | voir ci-dessous |
| camel-ai | 0.2.78 | moteur de simulation OASIS |
| zep-cloud | 3.25.0 | SDK Zep Cloud |
| flask | 3.1.2 | backend |

### Piège : Python système incompatible

`backend/pyproject.toml` impose `requires-python = ">=3.11,<3.13"`.
Le Python système est **3.14.6** — hors plage.

`uv` a donc provisionné un **CPython 3.11.15** managé dans `.venv/`.
Aucun conflit avec le Python système, aucun impact sur le reste de la machine.

> Si un jour on veut `graphiti-core[falkordblite]` (FalkorDB embarqué),
> il faut passer sur **Python 3.12** — autorisé par la contrainte `>=3.11,<3.13`.
> Voir section 6.

### Ports

| Service | URL | Statut |
|---|---|---|
| Backend | http://localhost:5001 | OK |
| Frontend | http://localhost:3002 | ⚠️ pas 3000 |

Le frontend est sur **3002** parce que les ports 3000 et 3001 sont occupés par
des conteneurs Docker d'un **autre projet** (`lyvia-boostrap-web-1`,
`lyvia-boostrap-api-1`). Rien à voir avec MiroFish.

Pour libérer les ports :

```bash
docker stop lyvia-boostrap-web-1 lyvia-boostrap-api-1
```

Le CORS est en `origins: "*"` (`backend/app/__init__.py:43`), donc le port de
fallback ne pose aucun problème.

### Tests

```
144 passed in 3.87s     # à l'installation
154 passed in 3.89s     # après le travail LLM du §2 (+10 tests)
```

---

## 2. LLM branché sur OpenCode Go (Space Bunny Free)

### Configuration

Dans `.env` (gitignoré — **ne jamais versionner ce fichier**) :

```env
LLM_BASE_URL=https://opencode.ai/zen/go/v1
LLM_API_KEY=<clé opencode-go>
LLM_MODEL_NAME=space-bunny-free
LLM_REASONING_EFFORT=high
```

La clé est celle du provider `opencode-go` dans
`~/.local/share/opencode/auth.json`.

`Space Bunny Free` est **gratuit et illimité** sur Go, avec **0 jour de
rétention** et aucun entraînement sur les données.

### Le piège : `MissingSessionID`

Le premier test a échoué en HTTP 400 :

```
MissingSessionID — Request is missing x-opencode-session and cannot be
routed efficiently.
```

La [passerelle Go](https://opencode.ai/docs/go/#where-can-i-use-it) impose trois
choses que MiroFish ne faisait pas :

1. envoyer un **identifiant de session stable** (`x-opencode-session`) par
   conversation ;
2. **s'identifier** avec son propre user-agent, pas un nom de SDK générique ;
3. envoyer un trafic « typique d'un agent de code ».

Le point 3 est une question de politique d'usage, pas de technique — voir
section 7.

### Le correctif : `backend/app/utils/llm_compat.py`

Nouveau module exposant :

- `llm_request_headers(base_url)` → `default_headers` (`x-opencode-session`
  + `User-Agent: mirofish/0.1.0`) — **uniquement** si l'hôte est
  `opencode.ai`, donc sans effet sur les autres fournisseurs ;
- `llm_completion_kwargs()` → `{"reasoning_effort": "high"}` si
  `LLM_REASONING_EFFORT` est défini, sinon `{}`.

Variable optionnelle : `OPENCODE_SESSION_ID` (par défaut, un UUID stable
pour toute la durée du process — une exécution = une session).

### Sites câblés (6)

| Fichier | Nature |
|---|---|
| `app/utils/llm_client.py` | `OpenAI(...)` + `create_chat_completion` |
| `app/services/simulation_config_generator.py` | `OpenAI(...)` |
| `app/services/oasis_profile_generator.py` | `OpenAI(...)` |
| `scripts/run_parallel_simulation.py` | `ModelFactory.create(...)` |
| `scripts/run_twitter_simulation.py` | `ModelFactory.create(...)` |
| `scripts/run_reddit_simulation.py` | `ModelFactory.create(...)` |

`reasoning_effort` transite par `create_chat_completion()`
(`app/utils/openai_chat_compat.py`), point central qui couvre les 3 services
`app/`. Côté camel-ai, il passe par `model_config_dict`.

Vérifié : `ChatGPTConfig().as_dict()` renvoie `{}`, donc l'ajout est neutre
pour le comportement par défaut.

`effort high` est **réellement honoré** par le endpoint (14 reasoning tokens
constatés contre 0 pour `low`).

### Tests

`backend/tests/test_llm_compat.py` (nouveau) couvre les en-têtes et l'effort.

Deux tests existants dans `test_openai_chat_compat.py` échouaient : ils
assertaient la forme exacte de la requête, et le `.env` local injectait
`reasoning_effort`. Ils ont été rendus **hermétiques**
(`monkeypatch.delenv("LLM_REASONING_EFFORT")`) plutôt que de figer `'high'`
dans leurs attentes — sinon la garantie « forme par défaut préservée » aurait
cessé d'être testée.

---

## 3. À quoi sert Zep

**Zep est le graphe de connaissances temporel du monde simulé** — l'état
partagé que les agents et le rapporteur interrogent, en dehors des prompts.

L'architecture de MiroFish crée un problème que le LLM seul ne résout pas :
faire évoluer des milliers d'agents en parallèle. La mémoire ne peut pas vivre
dans les prompts — il faudrait réinjecter tout l'historique dans chaque fenêtre
de contexte, à chaque tour. Zep sort l'état des prompts.

### Les 5 rôles

1. **Extraction du graphe de départ** — `app/services/graph_builder.py`
   Documents → chunks → `graph.add`. Zep extrait entités et relations avec
   une ontologie sur mesure (`set_ontology`, 10 types max).

2. **Décider de quoi parle la simulation** — `app/services/zep_entity_reader.py`
   → `simulation_config_generator.py`. Nodes + arêtes filtrés par type en
   `EntityNode`. Détermine le nombre d'agents et le sujet.

3. **Enrichir les personas** — `app/services/oasis_profile_generator.py:385-409`
   `graph.search` sur les arêtes (limit 30) + les nœuds (limit 20), reranker RRF.

4. **Écrire l'historique de la simulation** —
   `app/services/zep_graph_memory_updater.py:494`
   Activities par tour réinjectées via `graph.add` avec `created_at` et
   métadonnées (simulation_id, plateforme, plage de rounds, agent_ids).

5. **Outils du ReportAgent** — `app/services/zep_tools.py`
   `search_graph`, `panorama_search`, `insight_forge`,
   `get_simulation_context`, `get_graph_statistics`, `interview_agents`…

### Le volet temporel (le vrai différenciant)

`EdgeInfo` (`app/services/zep_tools.py:97-100`) porte quatre champs :

```
created_at    quand le fait a été observé
valid_at      à partir de quand il est vrai
invalid_at    à partir de quand il devient faux
expired_at    quand Zep l'a invalidated
```

Plus la distinction `is_expired` / `is_invalid`. Sur une simulation
d'actualité politique ou de finance, « qui était PDG, et jusqu'à quand » est
la question centrale. Un graphe sans temporalité ne peut pas y répondre.

### Nuance importante

**Pendant les tours de simulation, les agents ne lisent pas Zep.** Les scripts
de simulation n'y touchent pas — le memory updater fait uniquement des
*écritures*.

Zep se lit **avant** (construction + personas) et **après** (rapport), et
s'écrit **pendant**. L'état n'est donc pas réinjecté en temps réel dans le
raisonnement des agents.

### Ce n'est pas un Obsidian

L'analogie est seductive mais diverge sur trois points :

| | Obsidian | Zep |
|---|---|---|
| Qui écrit le graphe | **toi**, à la main (`[[wikilinks]]`) | le **LLM**, automatiquement |
| Temporalité | notes atemporelles | fenêtres de validité natives |
| Destinataire | la lecture humaine | la récupération machine (RRF, scopes) |

Analogie plus juste : **un mur d'enquête de journaliste, où les liens à
ficelle sont tracés tout seuls et où les épingles expirent.**

---

## 4. Couplage Zep — ce qu'il faudrait remplacer

Inventaire mesuré :

- **10 fichiers** couplés (`app/api/graph.py`, `graph_builder.py`,
  `oasis_profile_generator.py`, `ontology_generator.py`,
  `zep_entity_reader.py`, `zep_graph_memory_updater.py`, `zep_tools.py`,
  `app/utils/zep.py`, `app/utils/zep_paging.py`,
  `scripts/validate_zep_cloud_integration.py`)
- **~16 endpoints Zep distincts**
- Une couture **partielle** existe déjà : `app/utils/zep.py`
  (`get_zep_client`, `call_zep_read_with_retry`, `is_retryable_zep_error`)

### Table de correspondance

| Zep utilisé | Graphiti | Difficulté |
|---|---|---|
| `graph.create` / `graph.delete` | instance / `group_id` | facile |
| `graph.add` (épisodes texte) | `add_episode()` | facile |
| `graph.node.get`, `get_edges` | Cypher | facile |
| `graph.search` (edges/nodes, RRF) | `search()` hybride | moyen |
| `graph.episode.get` | récupération d'épisode | facile |
| `batch.*` (6 endpoints) | **inutile** — synchrone | supprime de la complexité |
| `graph.set_ontology` | `custom_entity_types` (Pydantic) | **dur** |

---

## 5. Pourquoi pas Zep OSS

**Zep Community Edition (auto-hébergé) a été déprécié en avril 2025.**
Le repo `getzep/zep` est archivé dans `legacy/`.

Le chemin OSS est **Graphiti** — **Apache-2.0**, ~31k étoiles — et c'est
**le moteur qui fait tourner Zep Cloud**. On ne réécrit pas la sémantique
temporelle : on utilise le même graphe, en local.

### Contraintes Graphiti

- Python >= 3.10
- Base : **Neo4j 5.26** / FalkorDB 1.1.2 / Amazon Neptune.
  **Kuzu est déprécié** par Graphiti — ne pas partir là-dessus.
- LLM + embedder + cross-encoder (reranking) à fournir
- Supporte tout endpoint OpenAI-compatible via `OpenAIGenericClient`
  (Ollama, vLLM, LM Studio, ou ton endpoint OpenCode Go)
- `structured_output_mode` : `"json_schema"` (défaut) ou `"json_object"`
  (schéma injecté dans le prompt — pour les fournisseurs peu fiables)
- `SEMAPHORE_LIMIT` (défaut 10) pour éviter les 429
- Télémétrie **opt-out** : `GRAPHITI_TELEMETRY_ENABLED=false`

### Le cas de l'embedder : « déjà installé » ne veut pas dire « installable »

`sentence-transformers==3.0.0` et `torch==2.9.1` sont **bien** dans le venv.
Mais ce n'est pas `camel-ai` qui les y met, c'est `camel-oasis`, qui **épingle**
`sentence-transformers==3.0.0`. L'extra `graphiti-core[sentence-transformers]`
exige `>=3.2.1` : même forme de conflit que sur le driver `neo4j`, et l'extra
est donc **ininstallable** sans arbitrage.

> ⚠️ **Corrigé le 3 octobre 2026** (story 001-1, [ADR 0011](../../decisions/0011-inventaire-driver-et-format-de-story.md)).
> Ce paragraphe disait « dépendance de camel-ai » et en concluait que
> l'embedder local était gratuit. C'est vrai du venv, faux de l'installation :
> c'est le conflit qu'il faut voir, pas la version installée. **La story 001-4
> est bloquée** et devra trancher — avec son propre `override-dependencies`, ou en
> acceptant un embedder moins récent. Un saut `sentence-transformers` 3.0 → 3.2
> est un changement de modèle et de `torch` : il ne se décide pas par analogie
> avec un driver. Mesuré et consigné dans
> [`story-001-1.md`](plans/001-epreuve-graphiti-local/story-001-1.md).
>
> **Confirmé le 4 octobre 2026** (story 001-1b) : l'override posé pour le driver
> porte sur **`neo4j` seul** — `sentence-transformers` 3.0.0 et `torch` 2.9.1 sont
> restés intacts dans le lock, et `graphiti-core` est déclaré **sans extra**.
> `backend/tests/test_pyproject_override.py` refuse qu'on élargisse cet override :
> le passage à 3.2 reste une décision de la 001-4, pas un effet de bord.

---

## 6. Les 3 obstacles réels

### 6.1 L'ontologie générée à l'exécution — le point dur

`app/services/ontology_generator.py` génère du **code Python** de modèles
d'entités/relations via le LLM, **à l'exécution**. Graphiti attend des
**classes Pydantic**. Créer dynamiquement des classes et réindexer constitue
le vrai travail. C'est ~80% de l'effort.

### 6.2 L'isolation multi-graphes

MiroFish crée un graphe Zep **par simulation/projet** (`graph.create` →
`graph_id`, `delete_graph`). Zep Cloud gère ça nativement ; Graphiti est conçu
pour des graphes individuels.

Il faut trancher : une base Neo4j par simulation, ou partitionner par
`group_id`. Mais `app/utils/zep_paging.py` suppose qu'un graphe = une
simulation.

### 6.3 La fiabilité du structured output

Graphiti *dépend* du structured output JSON pour extraire. Or
`space-bunny-free` est un *stealth model* gratuit : **rien ne garantit qu'il
honore `json_schema`**.

Le README de Graphiti avertit que les petits modèles « émettent fréquemment du
JSON qui ne correspond pas au schéma », ce qui se manifeste par des échecs
d'extraction.

Mitigation : `structured_output_mode="json_object"`.

---

## 7. Arbitrage économique (et ce que « local » ne résout pas)

Motivation : **économiser des crédits**, pas la confidentialité.

| | Zep Cloud | Graphiti local |
|---|---|---|
| Crédits | par épisode | **0** |
| Appels LLM d'extraction | inclus dans Zep | **à ta charge** |
| Embeddings + reranker | inclus | CPU local |
| RAM | — | Neo4j : **2-4 Go** |

**Les crédits ne disparaissent pas : ils se convertissent en appels LLM.**

Avec `Space Bunny Free` (gratuit, illimité), le coût marginal tombe réellement
à zéro. Mais on paie en **latence** et en **fiabilité de sortie structurée** —
précisément le maillon faible d'un modèle gratuit.

Autrement dit : on échange de la monnaie (crédits Zep) contre de la monnaie
(compute + risque qualité). Pour le coût, c'est souvent gagnant. Pour la
prévisibilité, moins.

### ⚠️ Risque de politique d'usage

La doc Go précise que le service est conçu pour des agents de code, que le
trafic est **surveillé**, et que les clients validés sont Hermes, Claude Code,
Codex, ZCode, Pi, jcode, Kilo Code CLI.

MiroFish est un moteur de simulation sociale — trafic massif, parallèle, non
coder. Même sur un modèle illimité, ce profil d'usage est hors du cas d'usage
déclaré. **À garder en tête si l'on bascule la production dessus.**

---

## 8. Licence — AGPL-3.0

`LICENSE` = **GNU Affero General Public License v3**
(confirmé par `pyproject.toml` : `license = { text = "AGPL-3.0" }`).

### Ce qu'on peut faire

- Utiliser, modifier, forker, pour son usage personnel local — **aucune
  obligation**.
- Graphiti est **Apache-2.0** (permissif) : aucune incompatibilité.

### La condition à surveiller — section 13 de l'AGPL

> Exécuter une version **modifiée** en **mode réseau** et laisser **d'autres
> utilisateurs** interagir avec elle oblige à mettre le code source complet à
> leur disposition.

Trois conditions **cumulatives** : *modifié* + *réseau* + *autres utilisateurs*.
En local seul, la clause ne se déclenche jamais.

**Le piège** : MiroFish est un moteur de prédiction d'opinion — le genre
d'outil qu'on a envie d'exposer en démo. Le jour où c'est fait sur un VPS ou
un LAN, la source doit être offerte.

Un fork reste **obligatoirement AGPL** : impossible de le repasser en MIT ou de
le fermer.

Note : l'image officielle `ghcr.io/666ghj/mirofish:latest` est utilisée non
modifiée → code déjà public → conforme. Seules les modifications créent
l'obligation.

*(Analyse technique de licence, pas un avis juridique.)*

---

## 9. Docker — le delta réel

L'image existe déjà (`Dockerfile`) : base `python:3.11`, `uv` pour le backend,
`npm ci` pour le frontend, un seul conteneur lançant les deux via
`npm run dev`. Le `docker-compose.yml` n'a qu'un service.

### Ce qu'il reste à faire

1. Ajouter un service `neo4j` dans le compose — **avec un volume**, sinon le
   graphe est perdu à chaque recréation.
2. ~~Ajouter `graphiti-core` aux dépendances backend.~~ → **fait** le
   4 octobre 2026 (story 001-1b), avec `override-dependencies` pour le driver.
3. Faire pointer MiroFish vers `neo4j:7687` sur le réseau compose.

### ⚠️ Piège de build

Le Dockerfile utilise **`uv sync --frozen`**. `--frozen` échoue si `uv.lock`
n'est pas cohérent avec `pyproject.toml`.

Ajouter `graphiti-core` impose de **régénérer le lock (`uv lock`) avant de
builder**, sinon l'image ne se construit pas. **C'est fait** — le lock est
régénéré et commité avec la déclaration, et la CI échoue sur la même
désynchronisation (`uv sync --frozen`) : le piège est désormais surveillé, pas
évité.

### Limite de l'image actuelle

`CMD ["npm", "run", "dev"]` → l'image est en **mode dev** : pas de build
frontend, pas de minification. Correct pour un usage local, mais les
modifications frontend ne sont pas rebuildées proprement. À corriger si
l'on veut une image de production.

---

## 10. Plan d'attaque recommandé

Approche : une interface `GraphStore` avec deux implémentations
(`ZepGraphStore` qui continue de fonctionner, `GraphitiGraphStore` en local).
On garde le chemin Zep opérationnel le temps de valider le local, et les
154 tests servent de filet. La forme est validée par l'audit du §12 : c'est
exactement l'ossature `interface + ZepCloudStore/GraphitiStore + factory` que
`tt-a1i` a écrite — utile comme modèle, pas comme code.

### Ordre

| Étape | Contenu | Verdict |
|---|---|---|
| **1** | Neo4j + Graphiti sur un document de test ; **mesurer** si `space-bunny-free` tient la sortie structurée — avec les 4 portails du §12.6 | **décisif** |
| 2 | Si l'extraction tient → chemin de lecture (§12.6), puis ontologie dynamique en v2 | — |
| 3 | Si elle ne tient pas → extraction sur un modèle payant ponctuel (moins cher que des crédits Zep) | — |

**L'étape 1 est rapide et élimine le seul vrai point de rupture du projet.**
Le volume de code n'est pas le risque ; l'ontologie dynamique et la fiabilité
du structured output le sont.

Estimation : **2 à 4 jours** de travail concentré, dont l'ontologie dynamique.
Pas un rewrite — `zep_tools.py` est le plus gros morceau mais ses outils se
mappent presque 1:1.

> Cette estimation **n'est pas réduite** par l'existence des forks (§12.4) :
> aucun ne résout le §6.1 ni le §6.3. Le gain possible est d'un demi-jour sur
> l'ossature d'adaptateur, pas sur les deux points durs.

---

## 11. Points ouverts

1. **Pourquoi le local ?** Crédit ou confidentialité ? Si c'est le budget, une
   autre piste existe : le quota gratuit Zep peut suffire pour quelques
   simulations, et l'effort serait disproportionné. → *partiellement tranché* :
   la motivation est bien le coût (le LLM est gratuit, donc les crédits Zep sont le
   seul poste payant), et la communauté a convergé sur Graphiti comme seule
   voie OSS. Mais l'audit (§12) montre que personne n'a livré d'implémentation
   robuste : la question n'est plus « quel fork adopter » mais « le budget
   jours-homme vaut-il face au quota Zep ».
2. **Document de test** — manque un PDF/texte pour l'étape 1. **Bloquant.**
3. **Migration des données existantes** — le graphe Zep actuel contient-il
   quelque chose à conserver ? Si oui, il faut prévoir une migration, ce qui
   change le périmètre.
4. ~~**Conflit de driver Neo4j**~~ → **tranché par la story 001-1, 3 octobre
   2026 : le conflit est réel et structurel.** `camel-oasis==0.2.5` épingle
   `neo4j==5.23.0` (exact, sur ses 9 versions publiées) ; `graphiti-core`
   exige `neo4j>=5.26.0` (depuis la 0.12.0). Aucune combinaison ne résout —
   ce n'est donc pas notre lock, c'est une contrainte de l'amont. Un second
   conflit de la même forme attend la story 001-4 :
   `sentence-transformers==3.0.0` vs `>=3.2.1`. Contre-mesure mesurée et
   rejouable (`mesurer-001-1.sh`) : `override-dependencies` côté `uv` — un seul
   environnement, tests verts, imports dans l'ordre. Pas de second venv, pas de
   sous-processus. La décision est **actée par l'ADR 0010**, précisée par l'ADR
   0011, et **appliquée par la story 001-1b le 4 octobre 2026** :
   `override-dependencies = ["neo4j>=5.26.0,<6.0.0"]` est dans
   `backend/pyproject.toml`, avec `neo4j 5.28.6` en commentaire à côté de la
   borne, et 204 tests verts. Le détail est dans
   [`story-001-1.md`](plans/001-epreuve-graphiti-local/story-001-1.md) et
   [`story-001-1b.md`](plans/001-epreuve-graphiti-local/story-001-1b.md).

---

## 12. Audit des forks communautaires (3 octobre 2026)

Vérification faite après coup : API GitHub (étoiles, dernière poussée, état
des PR), clones peu profonds de `tt-a1i` et `Well-Go-USA`, puis diff du fork
`tt-a1i` contre **sa propre base** (`985f89f`, 6 mars 2026) — indispensable
pour isoler leur travail de la dérive upstream.

### 12.1 Cartographie

| Repo | ★ | Dernière poussée | Nature | Verdict |
|---|---|---|---|---|
| `666ghj/MiroFish` | 75 661 | 1er oct. | amont, Zep requis | référence |
| `nikmcfly/MiroFish-Offline` | 2 570 | 24 mars | Neo4j CE 5.15 + Ollama, `GraphStorage` maison, **sans Graphiti** | jouable, mais sans temporalité |
| `tt-a1i/MiroFish-local` | 155 | 17 mars | adaptateur Zep/Graphiti + Neo4j 5.26 | **référence, pas socle** |
| `Well-Go-USA/mirofish-graphiti` | 0 | 15 juin | Graphiti + Neo4j, 3 jours de commits | mort-né |
| `dimatolsto/MiroFish-Offline-Kuzu` | 0 | 27 mars | Kuzu embarqué, 1 jour | mort-né |
| `cdavsnail/MiroFish-LocOllama` | 0 | 8 juil. | fork amont, 61 issues ouvertes | à éviter |
| `SCTY-Inc/mirofish-cli` | 311 | 30 sept. | réécriture CLI (claude/codex CLI) | hors sujet Zep |
| PR #634 (Zep → JSON) | — | fermée | non mergée, +927/−1418 | régression (keyword search) |

Deux détails de méthode qui changent la lecture :

- **Aucun des deux forks sérieux n'est un fork GitHub de l'amont** → pas de
  synchro automatique, la réintégration serait manuelle.
- `tt-a1i` n'a **pas de branche `main`** : sa branche par défaut est
  `feat/zep-localization-mvp`, et sa base est du **6 mars** (pas du 17).

### 12.2 Ce que `tt-a1i` a réellement fait

| | Fichiers | Détail |
|---|---|---|
| Nouveau | 5 fichiers, ~1 690 lignes | `zep_adapter.py` (279), `zep_graphiti_impl.py` (904), `zep_cloud_impl.py` (223), `zep_factory.py` (136), `graphiti_patch.py` (148) |
| Modifié | 13 fichiers | `api/{graph,simulation}.py`, `config.py`, 7 services Zep, `utils/{file_parser,llm_client}.py` |
| Supprimé | `utils/zep_paging.py` | jugé inutile dans leur architecture |
| Tests | **aucun** | `backend/tests/` n'existe pas dans le fork |

Le découpage est bon : une interface, deux implémentations, une factory.
C'est exactement la forme du §10.

### 12.3 Cinq raisons de ne pas le reprendre tel quel

1. **Le graphe revient vide, silencieusement.**
   `zep_entity_reader.py:265-269` ignore les nœuds dont les labels sont ⊆
   `{Entity, Node}`. Les nœuds Graphiti sont **toujours** `[:Entity]` → *toute
   entité est droppée*, et personas comme configuration de simulation voient un
   graphe vide. Aucun warning. C'est le bug le plus grave, et il n'apparaît
   dans aucun de leurs docs.

2. **La temporalité est écrasée.** `graph_builder.py:489-490` force
   `"invalid_at": None, "expired_at": None  # 适配器暂不支持`, alors que le
   Cypher (`zep_graphiti_impl.py:636-638`) récupère bien `valid_at` /
   `invalid_at` / `expired_at` de Graphiti. Ils jettent exactement le
   différenciant décrit au §3. `get_all_edges` rate en plus les arêtes
   `EPISODIC`, et `get_node` / `get_node_edges` ne filtrent pas par `group_id`
   (fuite entre simulations).

3. **Structured output jamais configuré** — zéro occurrence de
   `structured_output_mode`, `SEMAPHORE_LIMIT` ou `max_retries`. Le défaut
   `json_schema` reste actif : le §6.3 est donc *non traité*. Pire,
   `get_episode_status()` renvoie toujours `processed=True` et
   `wait_for_episode()` toujours `True` → le builder rapporte un succès
   complet même si rien n'a été extrait.

4. **Le patch est dépendant d'une version précise.** `graphiti_patch.py`
   reproduit la signature positionnelle de `add_nodes_and_edges_bulk_tx` de
   **graphiti-core 0.25.0**, pinné `>=0.25.0,<0.26.0`. La dernière version est
   **0.30.2**. Au-delà : soit un `TypeError` au premier épisode, soit — pire —
   `apply_patch()` avale l'échec, log un warning, et Neo4j refuse l'écriture
   sans signal. Aucun contrôle de version, aucun switch de désactivation.

5. **Ontologie hors périmètre, explicitement.** `set_ontology()` est un no-op
   qui écrit dans un cache jamais relu (`zep_graphiti_impl.py:363-389`),
   `custom_entity_types=` n'apparaît nulle part, et `graph_builder.py:219-226`
   passe des listes JSON là où Zep attend `{name: Class}`. Ils conservent même
   l'`ontology_generator.py` d'avant les correctifs de juillet.

À quoi s'ajoutent des incompatibilités avec notre base actuelle : leur ajout
d'épisodes passe par le chemin **legacy** (`batch_size=3` + `sleep(1)`) au lieu
de l'API Batch d'upstream, et il leur manque `utils/zep_paging.py`,
`is_retryable_zep_error`, `normalize_ontology_attributes`, `utils/locale.py`.

### 12.4 Coût du portage

Le portage par merge est hors de prix : entre le 6 mars et aujourd'hui,
upstream a bougé **+2 785 / −1 017 lignes sur les 14 fichiers que le fork a
touchés** (`api/graph.py` +600, `simulation_runner.py` +648,
`graph_builder.py` +563, `api/simulation.py` +421,
`zep_graph_memory_updater.py` +399, `llm_client.py` +253). Et leur `config.py`
**régresserait** trois correctifs upstream récents (`load_dotenv(override=True)`,
rejet de `ZEP_API_URL`, avertissement DEBUG).

Conclusion : **prendre la forme, pas le code**. Les ~900 lignes de
`zep_graphiti_impl.py` méritent d'être réécrites ; l'ossature d'adaptateur, le
mapping `OPENAI_* ← LLM_*`, le compose et les clés `.env` sont réutilisables.

### 12.5 Ce qui est réutilisable

- L'ossature interface + deux impls + factory (`zep_adapter.py`).
- L'isolation par `group_id` : `add_episode(group_id=graph_id)` et toutes les
  lectures Cypher filtrées — c'est la bonne réponse au §6.2.
- Le mapping `OPENAI_API_KEY` / `OPENAI_BASE_URL` depuis `LLM_*`
  (`config.py`, 4 lignes) : c'est ce qui fait pointer les appels internes de
  Graphiti sur notre endpoint.
- La dégradation automatique en **RRF** quand l'API ne gère pas les logprobs
  (`GRAPHITI_FORCE_CROSS_ENCODER`).
- `docker-compose.local.yml` : Neo4j 5.26 + APOC + volumes nommés +
  healthcheck. Copiable tel quel (retirer le `version:` obsolète et le mot de
  passe en dur).

### 12.6 Conséquences sur le plan

**L'étape 1 doit avoir quatre portails** — exactement ceux que le fork a ratés :

1. **En-tête de session dans le client Graphiti.** `OpenAIGenericClient`
   n'expose pas de paramètre d'en-têtes documenté → sous-classer et overrider
   `acompletion` pour injecter `x-opencode-session` et le User-Agent. Sinon on
   n'obtiendra pas un verdict sur le modèle, mais un `MissingSessionID` dès la
   première extraction.
2. `structured_output_mode="json_object"` explicite, plus retries et
   `SEMAPHORE_LIMIT`.
3. **Embedder local `sentence-transformers`** — zéro appel API, pas de collision
   de dimension, pas de chunking. ⚠️ **bloqué** : l'extra exige `>=3.2.1` et
   `camel-oasis` épingle `3.0.0` (voir « Le cas de l'embedder » plus haut, et
   l'ADR 0011). Story 001-4, arbitrage propre.
4. **Conflit de driver Neo4j** (`camel-oasis` vs `graphiti-core`) : **tranché**
   par l'ADR 0010, précisé par l'ADR 0011. Override à poser par la story
   001-1b ; comportement à prouver par la story 001-2.

**Sur l'ontologie, la décision est plus simple qu'il n'y paraît** : le chemin de
lecture (labels, `summary`, `fact`, `valid_at`) est identique avec ou sans
ontologie custom. Donc **faire le chemin de lecture une fois, et démarrer sans
ontologie custom** ; l'ontologie générée devient une v2. Cela recale le §6.1 :
c'est désormais une *v2*, plus le gros de l'effort initial.

**Règle de travail** : tout ce qu'on écrira côté graphe doit avoir des tests.
L'absence de `backend/tests/` chez eux est précisément la raison pour laquelle
ces bugs sont invisibles.

*(Audit technique, pas un jugement sur les personnes : le travail est sérieux et
bien documenté, il est simplement arrêté à un MVP et non vérifié.)*

---

## Annexe — commandes utiles

```bash
# Installation complète
npm run setup:all

# Lancer les deux services
npm run dev

# Tests
cd backend && uv run pytest tests/ -q

# Test de l'endpoint LLM
cd backend && uv run python -c "
from app.utils.llm_client import LLMClient
print(LLMClient().chat(messages=[{'role':'user','content':'ping'}], max_tokens=10))"
```

Pour rebuilt après un changement de dépendance :

```bash
cd backend && uv lock && uv sync
```

### Audit des forks

```bash
# État réel d'un fork (étoiles / dernière poussée)
gh api repos/tt-a1i/MiroFish-local \
  --jq '{stars: .stargazers_count, pushed: .pushed_at, default: .default_branch}'

gh api repos/666ghj/MiroFish/pulls/634 \
  --jq '{state, merged, changed_files, title}'

# Identifier la base d'un fork (indispensable : les forks ne suivent pas l'amont)
git clone --depth 1 https://github.com/tt-a1i/MiroFish-local.git
SHA=$(git -C MiroFish rev-list -1 --before=2026-03-17 upstream/main)
git -C MiroFish log -1 --format='base: %h %ad %s' --date=short $SHA
git -C MiroFish archive $SHA backend/app | tar -x -C "$TMPDIR/march"

# Empreinte réelle du fork (et non la dérive upstream)
diff -rq "$TMPDIR/march/backend/app" tt-a1i/backend/app

# Mesurer la dérive upstream sur les fichiers que le fork a touchés
git diff --stat $SHA HEAD -- backend/app/api/graph.py backend/app/services/zep_tools.py
```
