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

**Notre travail : faire tourner tout ça sans cloud.**

| Axe | État |
|---|---|
| LLM branché sur l'endpoint gratuit (OpenCode Go) | ✅ fait, testé |
| Graphe de connaissances local (Graphiti + Neo4j) à la place de Zep Cloud | ❌ à faire |
| Image Docker de production | ❌ à faire |

- Amont : `666ghj/MiroFish` — AGPL-3.0, ~75 000 ★, très actif
- Fork de travail : `zohac/MiroFish`, branche `local-first`
- Contexte technique détaillé : [`docs/LOCAL-FIRST.md`](docs/LOCAL-FIRST.md)

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
**154 tests** — il doit grossir, jamais rétrécir.

```bash
cd backend && uv run pytest tests/ -q     # obligatoire avant chaque commit
```

Règles de qualité des tests :

- **Hermétiques** : jamais de dépendance à `.env` ni à l'ordre d'exécution.
  Si un test casse selon la machine, mocker l'environnement
  (`monkeypatch.delenv(...)`) plutôt que figer une valeur.
- **Pas de réseau réel** : les clients HTTP/LLM sont mockés. Un test qui
  appelle l'API ne teste pas notre code.
- **Un test = une intention.** Si le nom du test contient un « et », il
  faut deux tests.
- Les tests qui touchent un contrat Zep existant sont notre filet de
  sécurité pendant la migration : ils doivent rester verts **avant et après**
  chaque refactor.

### 2.3 Docs et décisions dans `/docs`

- **Contexte technique** → `docs/LOCAL-FIRST.md`
- **Décision d'architecture** → un ADR dans `docs/decisions/NNNN-titre.md`
- **Schéma** → `docs/architecture/`, diagrammes Mermaid
- `AGENTS.md` = constitution + index. Il est mis à jour en fin de session
  dès que le cadre change.

Un ADR est **immuable** une fois accepté. Pour le changer, on écrit un
nouvel ADR qui le supersède — on ne réécrit pas l'histoire.

### 2.4 Secrets

`.env` est gitignoré et **ne doit jamais être commité**. La clé OpenCode Go
vit dans `~/.local/share/opencode/auth.json`. Avant chaque commit, vérifier
qu'aucun token n'apparaît dans le diff.

### 2.5 Dépendances

`backend/pyproject.toml` est la **source unique** (`requirements.txt` est un
artefact amont, ne pas y ajouter de dépendance). Toute nouvelle dépendance
doit être justifiée, et `uv lock` régénéré : le Dockerfile utilise
`uv sync --frozen` et échoue si le lock est désynchronisé.

Dépendance prévue : `graphiti-core` (Apache-2.0). Aucune autre.

### 2.6 Git

- Branche de travail : **`local-first`**. `origin` = `zohac/MiroFish`,
  `upstream` = `666ghj/MiroFish`.
- **Ne jamais pousser sur `upstream`.**
- Message de commit = *ce qui* + *pourquoi*. Pas de « fix » nu.
- Jalon important → tag de sauvegarde (ex. `local-first-2026-10-03`).

### 2.7 Licence

AGPL-3.0. Exécuter une version modifiée en mode réseau avec d'autres
utilisateurs impose de publier les sources. Voir l'ADR 0005.

---

## 3. Commandes

```bash
# Installation complète (le Python système est ignoré : uv gère le 3.11)
npm run setup:all

# Backend :5001 + frontend :3000 (proxy /api → 5001)
npm run dev

# Tests
cd backend && uv run pytest tests/ -q

# Dépendances : lock DANS le backend, sinon le build Docker casse
cd backend && uv lock && uv sync
```

Variables d'environnement utiles :

| Variable | Rôle |
|---|---|
| `FLASK_PORT` | port backend (défaut 5001) |
| `LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL_NAME` | endpoint LLM |
| `LLM_REASONING_EFFORT` | effort de raisonnement (OpenCode Go) |
| `ZEP_API_KEY` | requis uniquement si le backend graphe = Zep |
| `NEO4J_URI` / `NEO4J_USER` / `NEO4J_PASSWORD` | cible Graphiti (à venir) |

---

## 4. Carte du dépôt

| Zone | Chemin | Rôle |
|---|---|---|
| Routes HTTP | `backend/app/api/` | `graph.py`, `simulation.py`, `report.py` |
| Métier | `backend/app/services/` | construction graphe, personas, simulation, rapport |
| Clients & helpers | `backend/app/utils/` | `zep.py`, `zep_paging.py`, `llm_client.py`, `llm_compat.py`, `ontology.py`, `locale.py` |
| Modèles | `backend/app/models/` | `project.py`, `task.py` |
| Config | `backend/app/config.py` + `.env` | variables d'env |
| Tests | `backend/tests/` | pytest — 154 tests |
| Simulations | `backend/scripts/` | `run_{parallel,twitter,reddit}_simulation.py` |
| Frontend | `frontend/` | Vue + Vite, proxy `/api` vers 5001 |
| Docker | `Dockerfile`, `docker-compose.yml` | 1 service, **mode dev** |

---

## 5. Le graphe : rayon d'impact

Le graphe de connaissances est le point le plus couplé du code. 18 fichiers
contiennent une référence à Zep ; le noyau qui utilise réellement le client
est :

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
| Python système hors plage (`>=3.11,<3.13`) | `uv` refuse de synchroniser | utiliser `backend/.venv` (3.11 géré par uv) |
| `uv sync --frozen` échoue au build | lock désynchronisé | `uv lock` puis `uv sync`, **avant** de builder |
| Ports 3000/3001 occupés | le frontend démarre sur 3002 | normal ; CORS est en `*`. Libérer les ports si besoin |
| Dockerfile `CMD npm run dev` | image en mode dev, pas de build front | à corriger seulement si on vise la production |
| OpenCode Go exige un identifiant de session | HTTP 400 `MissingSessionID` | en-têtes via `utils/llm_compat.py` — **Graphiti n'est pas couvert** |
| Structured output non honoré | échec d'extraction | `structured_output_mode="json_object"` explicite |
| `camel-oasis` vs `graphiti-core` | conflit de version du driver Neo4j | vérifier **avant** d'ajouter la dépendance |

---

## 7. Definition of Done

- [ ] `cd backend && uv run pytest tests/ -q` → tout vert
- [ ] Aucun secret dans le diff
- [ ] Doc mise à jour si le comportement ou une décision a changé
- [ ] ADR écrit si une décision d'architecture a été prise
- [ ] Message de commit qui explique le **pourquoi**
- [ ] `AGENTS.md` touché si le cadre lui-même a changé

---

## 8. Hors périmètre (pour l'instant)

- Ré-auditer les forks communautaires → fait, ADR 0002
- Ontologie dynamique → reportée en v2, ADR 0003
- Moderniser le frontend ou l'i18n
- Exposer l'application en réseau sans lire l'ADR 0005

---

## 9. Index des documents

| Doc | Contenu |
|---|---|
| [`docs/LOCAL-FIRST.md`](docs/LOCAL-FIRST.md) | Installation, rôle de Zep, inventaire du couplage, obstacles, plan, audit des forks |
| [`docs/README.md`](docs/README.md) | Conventions et index de la documentation |
| [`docs/architecture/cible-graphstore.md`](docs/architecture/cible-graphstore.md) | Schémas de l'architecture cible |
| [`docs/decisions/`](docs/decisions/) | ADR — décisions d'architecture, figées |

### Décisions figées

| ADR | Décision |
|---|---|
| 0001 | Remplacer Zep par Graphiti + Neo4j, derrière une interface à deux implémentations |
| 0002 | Ne pas adopter de fork communautaire : prendre la forme, pas le code |
| 0003 | L'ontologie dynamique est une **v2** ; le chemin de lecture d'abord |
| 0004 | LLM : endpoint gratuit OpenCode Go, avec compat session |
| 0005 | Licence : rester local ; si exposition réseau, publier les sources |

---

## 10. Contrat de session

**Au début** — lire ce fichier, puis `docs/README.md`, puis l'ADR concerné.

**À la fin** — tests verts, commit explicatif, docs et ADR à jour,
`AGENTS.md` régénéré si le cadre a bougé, tag si jalon.

Ne pas laisser dans le working tree du travail non commité : c'est la
première cause de perte de travail sur ce dépôt.