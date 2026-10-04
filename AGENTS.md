# AGENTS.md — MiroFish local-first

Constitution du dépôt. Elle vaut pour toute contribution, humaine ou agent.
En cas de conflit entre ce fichier et une demande ponctuelle : **ce fichier
gagne**, et on le corrige explicitement dans un commit dédié.

> Révision : 3 octobre 2026 · branche `local-first` · fork `zohac/MiroFish`

---

## 1. Le projet en une minute

MiroFish est un **moteur de simulation sociale**. À partir de documents, il
construit un graphe de connaissances, en déduit une configuration de
simulation, génère des personas, fait vivre des agents (Twitter, Reddit,
parallèle) via `camel-oasis`, puis rédige un rapport.

**Notre travail : faire tourner tout ça sans cloud, dans un environnement
reproductible.**

| Axe | État |
|---|---|
| LLM branché sur l'endpoint gratuit (OpenCode Go) | ✅ fait, testé |
| Cadre de travail : constitution, ADR, CI, suivi | ✅ fait |
| Planification migrée vers `epic-XXX.md` + `story-XXX.md` (ADR 0009) | ✅ fait |
| Graphe de connaissances local (Graphiti + Neo4j) à la place de Zep Cloud | ❌ à faire |
| Environnement Docker de référence (Docker-first) | ❌ à faire — epic 005 |

- Amont : `666ghj/MiroFish` — AGPL-3.0, ~75 000 ★, très actif
- Fork de travail : `zohac/MiroFish`, branche `local-first`
- État du projet : [`docs/STATUS.md`](docs/STATUS.md)
- Contexte technique détaillé : [`docs/LOCAL-FIRST.md`](docs/LOCAL-FIRST.md)

### La tâche du moment

**La story 001-1b** — poser l'`override-dependencies` du driver `neo4j`, décidé
par l'ADR 0010 et précisé par l'ADR 0011. Fichier prêt :
[`story-001-1b.md`](docs/plans/001-epreuve-graphiti-local/story-001-1b.md).
Deux lignes de déclaration, un lock régénéré, et une promesse à tenir : le
protocole de mesure de la 001-1 doit **rester rejouable** sur l'arbre qui en
résulte — sans quoi poser l'override ferait perdre la mesure.

> **La story 001-1 est `done`.** Son conflit est **réel et structurel**, la
> parade est mesurée et rejouable
> ([`mesurer-001-1.sh`](docs/plans/001-epreuve-graphiti-local/mesurer-001-1.sh)),
> et la décision est **actée** dans l'ADR 0010 puis précisée par l'ADR 0011.
> Cinq points de sa revue sont restés différés, dans
> [`deferred-work.md`](deferred-work.md).
>
> **Puis 001-2** — Neo4j 5.26 + APOC en local, avec volumes nommés. C'est le
> **premier test comportemental** du driver forcé : personne n'a encore ouvert
> de connexion sous cet override. C'est là, pas dans 001-1, qu'un problème de
> driver se verrait — et si elle casse, l'ADR 0010 est supersédé, pas réécrit.

---

## 2. Règles

### 2.1 Clean architecture, SOLID, KISS, DRY

Les dépendances pointent **vers l'intérieur**, jamais l'inverse :

```
api/  →  services/  →  utils/
(HTTP)   (métier)     (clients, helpers purs)
```

- `api` connaît `services`. `services` connaît `utils`. **Jamais l'inverse.**
- Aucune dépendance circulaire. `utils` ne connaît aucun service métier.
- **Une interface exige ≥ 2 implémentations réelles.** Avant d'en créer une,
  vérifier qu'il y a bien deux cas concurrents (Zep **et** Graphiti).
- **DRY sur le graphe** : la connaissance « comment dialoguer avec le store »
  vit dans l'implémentation, **jamais** dans les appelants. Un `if zep else
  graphiti` dans un service est un bug de conception.
- **KISS** : pas de couche d'abstraction spéculative, pas de configuration
  dynamique si un booléen suffit.

### 2.2 Tout code produit est testé

Une fonctionnalité sans test **n'est pas terminée**. Le filet actuel est de
**192 tests** — il doit grossir, jamais rétrécir.

Règles de qualité des tests :

- **Hermétiques** : jamais de dépendance à `.env` ni à l'ordre d'exécution.
  Si un test casse selon la machine, mocker l'environnement
  (`monkeypatch.delenv(...)`) plutôt que figer une valeur.
- **Pas de réseau réel** : les clients HTTP et LLM sont mockés. Un test qui
  appelle l'API ne teste pas notre code.
- **Un test = une intention.** Si le nom du test contient un « et », il faut
  deux tests.
- **Vérifier qu'un test teste vraiment.** Une fixture dont la mutation ne
  correspond pas au fichier réel fait passer un test sans rien vérifier — pire
  que pas de test. Quand un test échoue, vérifier d'abord qu'il reproduit le
  défaut qu'il prétend couvrir.
- Les tests qui touchent un contrat Zep existant sont notre filet de sécurité
  pendant la migration : ils doivent rester verts **avant et après** chaque
  refactor.

### 2.3 Docs et décisions dans `/docs`

- **Contexte technique** → `docs/LOCAL-FIRST.md`
- **État du projet** → `docs/STATUS.md`
- **Décision d'architecture** → un ADR dans `docs/decisions/NNNN-titre.md`
- **Planification** → `docs/plans/<NNN>-<slug>/`
- **Schéma** → `docs/architecture/`, diagrammes Mermaid
- `AGENTS.md` = constitution + index, mis à jour en fin de session dès que le
  cadre change.

Un ADR est **immuable** une fois accepté. Pour le changer, on écrit un nouvel
ADR qui le précise ou le supersède — on ne réécrit pas l'histoire.

### 2.4 Secrets

`.env` est gitignoré et **ne doit jamais être commité** — ni dans le dépôt, ni
dans une image Docker. La clé OpenCode Go vit dans
`~/.local/share/opencode/auth.json`. Avant chaque commit, vérifier qu'aucun
token n'apparaît dans le diff.

Sous Docker, les secrets passent par `env_file: .env`, jamais par `COPY`.

### 2.5 Dépendances

**Python** — `backend/pyproject.toml` est la source unique (`requirements.txt`
est un artefact amont, ne pas y ajouter de dépendance). Toute nouvelle
dépendance doit être justifiée, déclarée dans le groupe `dev` si c'est un
outillage, et le lock régénéré : l'image utilise `uv sync --frozen` et échoue
si le lock est désynchronisé.

**Node** — **pnpm uniquement** (ADR 0008). La version est écrite **une seule
fois**, dans le champ `packageManager` de `package.json`. Installations et
builds en `--frozen-lockfile`. Il ne doit plus rester un seul appel à `npm`
dans le dépôt, et un `package-lock.json` qui réapparaît se **supprime** : c'est
une dérive, pas un conflit à réconcilier.

Dépendance prévue côté produit : `graphiti-core` (Apache-2.0). Aucune autre.

### 2.6 Git

- Branche de travail : **`local-first`**. `origin` = `zohac/MiroFish`,
  `upstream` = `666ghj/MiroFish`.
- **Ne jamais pousser sur `upstream`.**
- Message de commit = *ce qui* + *le pourquoi*. Pas de « fix » nu.
- Jalon important → tag de sauvegarde (ex. `local-first-2026-10-03`).
- L'amont avance vite (~100 commits depuis mars). Pour le réintégrer :
  `git fetch upstream && git rebase upstream/main`, **puis** relancer les
  192 tests — ses correctifs d'ontologie et de Zep ne sont pas chez nous.

### 2.7 Licence

AGPL-3.0. Exécuter une version modifiée en mode réseau avec d'autres
utilisateurs impose de publier les sources. Voir l'ADR 0005.

### 2.8 Aucune feature sans plan

On n'attaque pas une fonctionnalité sans ses artefacts. La valeur est dans
les artefacts : une liste de tâches sans PRD ni architecture ne sert qu'à
mesurer un effort, pas à décider quoi construire.

| Artefact | Emplacement | Répond à |
|---|---|---|
| PRD | `docs/plans/<NNN>-<slug>/prd.md` | quoi, pourquoi, **critères de sortie chiffrés** |
| Architecture | `docs/plans/<NNN>-<slug>/architecture.md` | comment, avec schémas Mermaid |
| Epic | `docs/plans/<NNN>-<slug>/epic-<NNN>.md` | le contrat d'ingénierie : FR, NFR, UX, index des stories, **documents à consulter** |
| Story | `docs/plans/<NNN>-<slug>/story-<epic>-<n>[-<suffixe>].md` | une story = un fichier markdown : en-tête minimal, puis les six sections en français (voir §2.10) |
| Suivi | `sprint-status.yaml` (racine) | **l'agrégat par epic** |

Règles :

- Un PRD sans critère chiffré est une liste de courses : on ne sait pas quand
  c'est fini.
- **Une story = un fichier markdown** (ADR 0007, forme précisée par l'ADR
  0009). Un petit en-tête `---` machine-readable (`id`, `epic`, `titre`,
  `statut`, `auteur`, `format`), puis de la prose : c'est une note, pas une
  donnée. L'état d'une story vit dans son fichier ; `sprint-status.yaml` ne
  porte que l'agrégat d'epic. Deux endroits pour le même état, et l'état ment.
- L'`id` suit `<epic>-<n>`, avec un **suffixe alphabétique facultatif** pour une
  story dérivée — celle qui naît d'un critère qu'une story précédente n'a pas
  pu tenir (`001-1b` est le geste que la 001-1 n'appliquait pas). Le suffixe se
  valide : `validate_plans.py` refuse un `id` mal formé.
- `format: "2"` dans l'en-tête, et les six sections en français. Le marqueur
  rend la rupture diagnosticable : un fichier au format 1 est refusé avec un
  message qui nomme le format attendu, au lieu de sept « section absente »
  identiques (ADR 0011).
- Une story passe `backlog → in-progress → review → done`, jamais de saut.
  `blocked` quand une dépendance externe nous arrête. **Ne pas passer
  directement à `done`** : un `done` sans passer par `review` n'a pas été
  relu. *Cette règle n'est outillée par rien* : `validate_plans.py` lit des
  fichiers, pas un historique, et ne contrôle que l'appartenance de l'état à la
  liste des cinq autorisés.
- **Un fichier par story réellement démarrée**, pas imaginée — sinon la
  formalisation devient du bruit. Une story en `backlog` peut n'exister que
  dans l'index de `epic-<NNN>.md`, avec ses critères résumés.
- **Définition de prêt** satisfaite avant de commencer : critères
  mesurables, dépendances résolues, stratégie de test identifiée, documents
  lus.
- **Définition de fini** cochée avant de finir, et **notes de complétion**
  écrites : ce qui a divergé du plan, et pourquoi. Un critère **non satisfiable**
  se barre et se date, il ne se supprime pas : le voir échouer est l'intérêt.
- La structure est **validée par un script**
  (`backend/scripts/validate_plans.py`, PyYAML dans le groupe `dev`) lancé en
  CI. Voici ce qu'il impose, et rien de plus :
  1. un epic `in-progress` ou au-delà a un dossier de plan complet
     (`prd.md`, `architecture.md`, `epic-<NNN>.md`) ;
  2. une story `in-progress` ou au-delà a un fichier **et** est citée dans le
     hub — citation cherchée par frontières de mot, pas par sous-chaîne, sinon
     `001-1b` tiendrait lieu de `001-1` ; et une ligne de hub passée
     `in-progress` a un fichier derrière ;
  3. états et `id` sont valides, `format` est bon, les six sections obligatoires
     sont présentes, et une story en `review` ou `done` n'a plus aucune case
     ouverte — ni dans `Tâches`, ni dans les deux définitions ;
  4. une story `done` dont les notes de complétion sont encore au gabarit est
     refusée.
- `docs/STATUS.md` est la vue humaine, alimentée du YAML. Pas de second
  saisie.

### 2.9 Docker d'abord — mais pas encore exécutable

**Docker est l'environnement de référence cible** (ADR 0006). Un seul
environnement reproductible, pas deux qui divergent.

> ⚠️ **L'epic 005 n'est pas fait.** Aujourd'hui, le `docker-compose.yml`
> pointe l'image **amont** `ghcr.io/666ghj/mirofish:latest` — sans aucune de
> nos modifications — ne contient pas Neo4j, et son service s'appelle
> `mirofish`, pas `backend`. Les commandes Docker de la §3 sont écrites pour
> après l'epic 005 : lancées maintenant, elles échouent ou font tourner le
> code amont. **Tant que l'epic 005 n'est pas fait, on travaille en local,
> et c'est un choix assumé.**

Ce qui restera vrai quand Docker sera prêt :

- Toute commande passe par `docker compose`. Un `uv run` ou un `pnpm run` en
  local crée un **second** environnement, qui divergera.
- Le mode sans Docker reste un **secours explicite**. On ne mélange pas les
  deux dans une même session.
- Le code est **monté en volume** en développement ; l'image reste la
  référence des dépendances.
- Les données persistantes vivent dans des **volumes nommés** (Neo4j), jamais
  dans le cycle de vie d'un conteneur.
- `docker compose down` **sans** `-v` conserve les données. `down -v` détruit
  le graphe : ne le lancer que sciemment.
- Aucune modification manuelle d'un conteneur ou d'une image. Tout passe par
  les fichiers du dépôt.
- Les ports sont exposés **explicitement** dans le compose. Sur cette machine,
  3000 et 3001 sont déjà pris par les conteneurs d'un autre projet.

### 2.10 Langue

**Français, partout, sans exception.** Cette constitution, les ADR, les PRD,
les epics, les stories, le `STATUS.md`, les messages de commit, les
commentaires de pull request, et les échanges avec l'utilisateur comme entre
agents.

Restent en anglais, et uniquement là :

- le code et les identifiants — `chunk_size`, `GraphStore`, `zep_entity_reader` ;
- les valeurs de statut et les clés d'en-tête des stories — `backlog`,
  `in-progress`, `review`, `done`, `blocked`, `definition_of_ready` : ce sont
  des identifiants lus par `validate_plans.py` ;
- un terme technique établi où la traduction serait moins claire — `pipeline`,
  `commit`, `endpoint`, `healthcheck`.

Les six sections d'une story sont donc en français : **Définition de prêt**,
**Définition de fini**, **Tâches**, **Notes de développement**, **Revue**,
**Notes de complétion**. L'illustration donnée dans l'ADR 0009 montre les
noms anglais d'origine : cet ADR est immuable, on ne l'a pas retouché, et son
illustration est **caduque** sur ce point. L'ADR 0011 explique pourquoi le
validateur exige désormais les titres français. **Ne pas la recopier.**

> Cette règle est outillée par `validate_plans.py`, qui refuse un fichier sans
> `format: "2"` ou dont les sections portent les titres anglais (ADR 0011). Elle
> reste une règle de constitution sur *le reste* des documents : un PRD, une
> architecture ou un ADR écrits en anglais ne sont détectés par rien. Un
> document en anglais n'est pas détecté, il est en faute.

---

## 3. Commandes

### Aujourd'hui — local (l'epic 005 n'est pas fait)

```bash
# Bootstrap, une fois par poste
cd backend && uv sync && cd ..
pnpm install && pnpm --dir frontend install

# Avant chaque commit
cd backend && uv run pytest tests/ -q                  # 192 tests
cd backend && uv run ruff check .                     # lint
cd backend && uv run python scripts/validate_plans.py # structure de plan

# Application
pnpm dev                                              # backend :5001, frontend :3000
pnpm build                                            # build frontend
```

Le document de test de l'épreuve est dans `backend/uploads/documents/`, qui est
**gitignoré** : sur un autre poste il est absent. Le retélécharger depuis
l'URL et le vérifier au sha256 donnés dans le PRD de l'epic 001.

### Après l'epic 005 — Docker

```bash
docker compose up -d                      # backend, frontend, Neo4j
docker compose ps                         # état + healthchecks
docker compose logs -f backend            # logs
docker compose run --rm backend uv run pytest tests/ -q
docker compose run --rm backend bash
```

Ports : backend `5001` · frontend `3000` (3001, 3002 si occupés) · Neo4j
`7474` (browser) et `7687` (bolt).

Variables d'environnement utiles :

| Variable | Rôle |
|---|---|
| `FLASK_PORT` | port backend (défaut 5001) |
| `LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL_NAME` | endpoint LLM |
| `LLM_REASONING_EFFORT` | effort de raisonnement (OpenCode Go) |
| `ZEP_API_KEY` | requis uniquement si le backend graphe = Zep |
| `NEO4J_URI` / `NEO4J_USER` / `NEO4J_PASSWORD` | cible Graphiti |

---

## 4. Carte du dépôt

| Zone | Chemin | Rôle |
|---|---|---|
| Routes HTTP | `backend/app/api/` | `graph.py`, `simulation.py`, `report.py` |
| Métier | `backend/app/services/` | construction graphe, personas, simulation, rapport |
| Clients & helpers | `backend/app/utils/` | `zep.py`, `zep_paging.py`, `llm_client.py`, `llm_compat.py`, `ontology.py`, `locale.py` |
| Modèles | `backend/app/models/` | `project.py`, `task.py` |
| Config | `backend/app/config.py` + `.env` | variables d'env |
| Tests | `backend/tests/` | pytest — 192 tests |
| Simulations | `backend/scripts/` | `run_{parallel,twitter,reddit}_simulation.py` |
| Outillage | `backend/scripts/validate_plans.py` | validation de la structure de planification |
| Frontend | `frontend/` | Vue + Vite, proxy `/api` vers 5001 |
| Locks | `pnpm-lock.yaml`, `frontend/pnpm-lock.yaml`, `backend/uv.lock` | versions figées — ne jamais en réécrire un à la main |
| Planification | `docs/plans/`, `sprint-status.yaml` | PRD, architecture, epic, stories, suivi |
| Données d'entrée | `backend/uploads/documents/` | rapport AN n° 2506 — **gitignoré** |
| Docker | `Dockerfile`, `docker-compose.yml` | image amont, 1 service — **à étendre** (epic 005) |

---

## 5. Le graphe : rayon d'impact

Le graphe de connaissances est le point le plus couplé du code. **Dix
fichiers utilisent réellement le client Zep** — le noyau :

```
backend/app/api/graph.py
backend/app/services/graph_builder.py            # extraction depuis les documents
backend/app/services/ontology_generator.py       # ontologie générée à l'exécution
backend/app/services/oasis_profile_generator.py  # enrichment des personas
backend/app/services/zep_entity_reader.py        # lecture → config de simulation
backend/app/services/zep_graph_memory_updater.py # écriture pendant les tours
backend/app/services/zep_tools.py                # outils du ReportAgent
backend/app/utils/zep.py                         # client + retry
backend/app/utils/zep_paging.py                  # pagination
backend/scripts/validate_zep_cloud_integration.py
```

**Tout nouveau code qui touche au graphe passe par l'interface du store
(ADR 0001), jamais par le client Zep directement.** C'est cette discipline qui
permettra de basculer `ZEP_BACKEND` sans réécrire les services.

---

## 6. Pièges connus

| Piège | Symptôme | Réflexe |
|---|---|---|
| **Commandes Docker lancées trop tôt** | le conteneur tourne le code amont, ou `no such service: backend` | epic 005 (§2.9) : travailler en local d'ici là |
| Python système hors plage (`>=3.11,<3.13`) | `uv` refuse de synchroniser | utiliser `backend/.venv`, ou Docker (3.11) |
| `uv sync --frozen` échoue au build | lock désynchronisé | `uv lock` puis `uv sync`, **avant** de construire l'image |
| **Dérive Docker / local** | les tests passent en local, pas dans le conteneur | un seul environnement de référence |
| **npm et pnpm mélangés** | un `package-lock.json` réapparaît, `node_modules` divergent | pnpm uniquement ; le lock npm se supprime (ADR 0008) |
| `pnpm install` sans `--frozen-lockfile` | le lock est réécrit sans bruit | `--frozen-lockfile` par défaut, partout |
| `docker compose down -v` | le graphe Neo4j disparaît | ne l'utiliser que pour repartir de zéro, sciemment |
| Ports 3000/3001 occupés | le frontend démarre sur 3002 | exposer des ports explicites dans le compose |
| `CMD pnpm run dev` | image en mode dev, pas de build front | à corriger pour une image de production |
| `.env` copié dans l'image | secret dans l'historique Docker | `env_file`, jamais `COPY` |
| OpenCode Go exige un identifiant de session | HTTP 400 `MissingSessionID` | en-têtes via `utils/llm_compat.py` — **Graphiti n'est pas couvert** |
| Structured output non honoré | échec d'extraction | `response_format={"type": "json_object"}` côté MiroFish (`llm_client.py:183`), mode `json_object` explicite côté Graphiti |
| `camel-oasis` vs `graphiti-core` | `neo4j==5.23.0` (pin exact) vs `neo4j>=5.26.0` (plancher) — **conflit structurel, vérifié** | story 001-1 : aucune combinaison publiée ne résout. Parade mesurée et rejouable : `override-dependencies`. **Un second conflit identique** (`sentence-transformers==3.0.0` vs `>=3.2.1`) bloque la story 001-4 |

---

## 7. Définition de « fini »

- [ ] Tests verts — en local aujourd'hui, sous Docker après l'epic 005
- [ ] `ruff check` → rien
- [ ] `validate_plans.py` → rien à signaler
- [ ] Aucun secret dans le diff ni dans l'image
- [ ] Artefacts de plan à jour (PRD, architecture, epic, story, `sprint-status.yaml`)
- [ ] Doc mise à jour si le comportement a changé
- [ ] ADR écrit si une décision d'architecture a été prise
- [ ] Message de commit qui explique le **pourquoi**
- [ ] `AGENTS.md` touché si le cadre lui-même a changé

---

## 8. Hors périmètre (pour l'instant)

- Ré-auditer les forks communautaires → fait, ADR 0002
- Ontologie dynamique → reportée en v2, ADR 0003
- Moderniser le frontend ou l'i18n
- Exposer l'application en réseau sans lire l'ADR 0005
- GitHub Projects : uniquement comme vue générée, et seulement quand
  plusieurs epics seront en cours

---

## 9. Index des documents

| Doc | Contenu |
|---|---|
| [`docs/STATUS.md`](docs/STATUS.md) | fait / en cours / à faire / prochain pas |
| [`sprint-status.yaml`](sprint-status.yaml) | agrégat machine-readable par epic |
| [`docs/plans/001-epreuve-graphiti-local/`](docs/plans/001-epreuve-graphiti-local/epic-001.md) | l'epic en cours : PRD, architecture, epic, stories |
| [`docs/LOCAL-FIRST.md`](docs/LOCAL-FIRST.md) | installation, rôle de Zep, couplage, obstacles, plan, audit des forks |
| [`docs/README.md`](docs/README.md) | conventions et index de la documentation |
| [`deferred-work.md`](deferred-work.md) | travail réel différé, avec ce qui le déclencherait |
| [`docs/architecture/cible-graphstore.md`](docs/architecture/cible-graphstore.md) | schémas de l'architecture cible |
| [`docs/decisions/`](docs/decisions/) | ADR — décisions d'architecture, figées |

### Décisions figées

| ADR | Décision |
|---|---|
| 0001 | Remplacer Zep par Graphiti + Neo4j, derrière une interface à deux implémentations |
| 0002 | Ne pas adopter de fork communautaire : prendre la forme, pas le code |
| 0003 | L'ontologie dynamique est une **v2** ; le chemin de lecture d'abord |
| 0004 | LLM : endpoint gratuit OpenCode Go, avec compat session |
| 0005 | Licence : rester local ; si exposition réseau, publier les sources |
| 0006 | **Docker d'abord** : un seul environnement de référence |
| 0007 | **Une story = un fichier**, l'état vit avec la story |
| 0008 | **pnpm** pour Node : version figée dans `packageManager`, lock strict |
| 0009 | **Fichiers de story en markdown**, pas en YAML |
| 0010 | Forcer `neo4j` par `override-dependencies` : un seul environnement, on contourne le pin de l'amont |
| 0011 | Relevé réel de la surface `neo4j` (pas de `neo4j.Version`), version résolue consignée, marqueur de format de story |

---

## 10. Ce qui est déjà réglé — ne pas re-dériver

Ces faits ont été vérifiés et coûtent du temps à retrouver. Les redériver, c'est
du gaspillage ; les refaire sans leurs conditions, c'est reproduire leurs bugs.

| Fait vérifié | Où c'est écrit |
|---|---|
| Zep Community Edition est déprécié ; Graphiti est la voie OSS | ADR 0001 |
| Aucun fork communautaire n'est adoptable : bugs silencieux, zéro test, gelés depuis mars | ADR 0002, `LOCAL-FIRST.md` §12 |
| L'ontologie custom est une v2, **pas** le premier chantier | ADR 0003 |
| `zep_entity_reader.py:262` filtre les nœuds sans label d'ontologie → **le graphe revient vide en silence** | ADR 0003 |
| L'endpoint gratuit exige un en-tête de session, et **le client de Graphiti n'en envoie pas** | ADR 0004 |
| `chunk_size` compte des **caractères** (500), pas des mots → ~54 mots par chunk | PRD de l'epic 001 |
| Le patch du fork de référence est figé sur `graphiti-core` 0.25 (actuel 0.30) | `LOCAL-FIRST.md` §12.3 |
| **`camel-oasis` et `graphiti-core` ne coexistent pas** : `neo4j==5.23.0` est un pin exact qu'aucune version ne desserre, `graphiti-core` exige un plancher `>=5.26.0` — aucune combinaison publiée ne résout | ADR 0010, ADR 0011, story 001-1 · `LOCAL-FIRST.md` §11.4 |
| **Un `override` est un pari sur le comportement, pas sur le lock** : la surface du driver est relevée (`neo4j.Version` n'est utilisée nulle part), l'exécution ne l'est pas — la 001-2 tranche | ADR 0011 |
| **La mesure de la 001-1 est rejouable** : `mesurer-001-1.sh` remet `pyproject.toml`, `uv.lock` et le venv à leur état initial, et sa sortie est versionnée dans `mesure-001-1.txt` | story 001-1 |
| **`architecture.md` §3 se trompe sur l'embedder** : `sentence-transformers` 3.0.0 est bien là, mais l'extra de Graphiti exige `>=3.2.1` — même conflit que `neo4j` | story 001-1 |
| Le `docker-compose.yml` pointe l'image amont, pas la nôtre | ADR 0006 |
| Les tests passent sans `.env` — ils sont hermétiques | `LOCAL-FIRST.md` §2 |

---

## 11. Contrat de session

**Au début, dans cet ordre** — c'est ce qu'il faut lire pour reprendre le
travail sans mémoire :

1. ce fichier,
2. [`docs/STATUS.md`](docs/STATUS.md) — où on en est, questions ouvertes,
3. [`docs/plans/001-epreuve-graphiti-local/epic-001.md`](docs/plans/001-epreuve-graphiti-local/epic-001.md) — le contrat de l'epic en cours, et ses 11 documents de référence,
4. le fichier de story de la tâche du moment,
5. l'ADR concerné (§9).

**Environnement** — avant de modifier quoi que ce soit :
`cd backend && uv run pytest tests/ -q` doit afficher 192 passed. Sinon, on
corrige avant de commencer, pas après.

**À la fin** — tests verts, lint vert, structure validée, commit explicatif,
doc et ADR à jour, `sprint-status.yaml` à jour, story passée en `review` (pas
en `done` directement), `AGENTS.md` régénéré si le cadre a bougé, tag si
jalon.

Ne pas laisser dans l'arbre de travail du travail non commité : c'est la
première cause de perte de travail sur ce dépôt.
