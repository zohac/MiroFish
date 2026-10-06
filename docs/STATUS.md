# État du projet

Une page, mise à jour à chaque changement d'epic. La source de vérité est
[`sprint-status.yaml`](sprint-status.yaml) — ce fichier en est la **vue
humaine**, pas un second saisie.

> Dernière mise à jour : **6 octobre 2026** · branche `local-first`

---

## Où on en est

Le **cadrage est terminé** : constitution du projet (`AGENTS.md`), audit des
forks communautaires, cinq décisions d'architecture figées, CI qui lance les
tests et le lint. Le **prochain jalon est l'épreuve Graphiti** — mesurer si
le modèle gratuit tient l'extraction structurée, avant d'investir deux à
quatre jours de migration.

## Fait

| Livrable | Où |
|---|---|
| LLM branché sur l'endpoint gratuit, en-têtes de session compris | commit `28c61d0` |
| Travail sécurisé : branche `local-first`, tag de sauvegarde, fork `zohac/MiroFish` | commits `28c61d0`, `50e9826` |
| Analyse Zep : rôle, rayon d'impact, obstacles | `docs/LOCAL-FIRST.md` §3–§6 |
| Audit des 6 forks communautaires | `docs/LOCAL-FIRST.md` §12 |
| 5 ADR — Graphiti, forks, ontologie, LLM, licence | `docs/decisions/` |
| 7 ADR — + Docker-first, structure par story | `docs/decisions/0006`, `0007` |
| 8 ADR — + pnpm (Node), version figée dans `packageManager` | `docs/decisions/0008` |
| Constitution, suivi, CI + lint ruff | `AGENTS.md`, `docs/sprint-status.yaml`, `.github/workflows/ci.yml` |

## En cours

**Epic 001 — Épreuve Graphiti local** (le seul point de rupture du projet).
Plan : [`docs/plans/001-epreuve-graphiti-local/`](plans/001-epreuve-graphiti-local/prd.md)

La story **001-1 est `done`** : le conflit `graphiti-core` / `camel-oasis` est
réel et structurel, la parade est mesurée et rejouable
([`mesurer-001-1.sh`](plans/001-epreuve-graphiti-local/mesurer-001-1.sh)), la
décision est actée par l'ADR 0010 et précisée par l'ADR 0011. Cinq points de sa
revue de la 001-1 sont dans [`deferred-work.md`](deferred-work.md).

La story **001-1b est `done`** : l'`override-dependencies` du driver est posé
dans `backend/pyproject.toml`, avec `graphiti-core==0.30.2` **sans extra**, et le
lock est régénéré et commité. `neo4j 5.28.6` résolue — la version que l'ADR 0011
avait consignée, sans écart.

### La story 001-2 est `done` — le driver forcé **tient**

> C'est la réponse que l'ADR 0010 attendait et qu'il ne pouvait pas avoir : est-ce
> que `neo4j 5.28.6`, forcé contre le pin `==5.23.0` de `camel-oasis`, tient
> contact avec un vrai serveur ? **Oui.** 17 contrôles, deux fois, sur deux
> configurations de serveur. **L'ADR 0010 n'est pas supersédé.**
>
> La story est passée par **une revue de code à quatre couches** avant d'être
> close, et cette revue a trouvé mieux que des coquilles : **six garde-fous qui ne
> pouvaient pas échouer** — le secret, la dérogation APOC, le healthcheck, deux
> sur l'identifiant de conteneur — et un **critère C3 qui ne tenait que par
> coïncidence** de forme du graphe de vérification. Les 28 correctifs sont
> appliqués, **six vérifiés par mutation** sur le vrai fichier puis restauration à
> l'octet initial, et **les deux mesures ont été rejouées** sur le code corrigé.
> Cinq des « mutants vérifiés » que la story annonçait ne l'avaient pas été : le
> tri de la revue l'a montré, la correction l'a fait.

Premier contact avec un vrai serveur, donc premières mesures :

| Mesuré | Valeur |
|---|---|
| Driver | `neo4j 5.28.6` — lockée par `backend/uv.lock` |
| Serveur | `Neo4j 5.26.31` `community` — lue de `CALL dbms.components()`, pas du tag |
| Surface de l'ADR 0011 | 17/17 : `GraphDatabase.driver`, transactions, `Query`, 4 exceptions |
| Hiérarchie d'exceptions | tient — mais `Neo4jError` et `DriverError` sont **sœurs** sous `GqlError` |
| Volume nommé | le nœud survit à `stop` puis `start`, `valid_at` compris (**C3**) |
| Écart driver / serveur | 5.28.6 / 5.26.31 — mesuré, gardé par un test |

Le compose d'épreuve est **séparé** — [`docker-compose.neo4j.yml`](../../docker-compose.neo4j.yml)
— parce que `docker-compose.yml` pointe l'image amont (AGENTS.md §2.9). L'epic
005 l'absorbera quand l'environnement de référence existera.

Deux mesures, parce qu'**APOC a deux réponses et non une** :

- `graphiti-core==0.30.2` **s'en passe** — zéro occurrence de `apoc` dans le
  paquet, et ses 31 requêtes d'indexation plus ses deux procédures vectorielles
  passent sur un serveur sans plugin ;
- **`camel-oasis` en a besoin** — `Neo4jGraph.__init__` lance `refresh_schema()`,
  qui exécute `CALL apoc.meta.data()`, et `add_nodes_from_df` utilise
  `apoc.merge.node`. Sans plugin, son chemin Neo4j casse dès le premier appel.

Le plugin reste donc dans le compose, mais pour une raison que
`architecture.md` §4 ne donnait pas — il y prescrivait APOC « repris du fork de
référence ». **Cette phrase est désormais fausse** : le fork avait APOC parce
que `camel` en a besoin, et c'est mesuré.

Trois découvertes que personne n'avait faites, toutes dans
[`story-001-2.md`](plans/001-epreuve-graphiti-local/story-001-2.md) § Notes de
complétion : la hiérarchie d'exceptions n'est pas une chaîne ; `graphiti-core`
appelle `CALL db.indexes()`, qui **n'existe pas** sur un 5.x (hors chemin
d'écriture, mais la 001-5 doit le savoir) ; et `apoc.merge.*` est refusé par
défaut même plugin installé — sans quoi `camel` accuse une installation
manquante qui est présente.

Fichiers : [`story-001-2.md`](plans/001-epreuve-graphiti-local/story-001-2.md),
[`verifier-001-2.sh`](plans/001-epreuve-graphiti-local/verifier-001-2.sh),
[`mesure-001-2-compose.txt`](plans/001-epreuve-graphiti-local/mesure-001-2-compose.txt),
[`mesure-001-2-sans-apoc.txt`](plans/001-epreuve-graphiti-local/mesure-001-2-sans-apoc.txt).

### La story 001-3 est `done` — Client LLM Graphiti avec en-tête de session (C2 validé et relu)

> `MiroFishLLMClient` hérite de `OpenAIGenericClient` dans `backend/app/utils/graphiti_llm_client.py`.
> Les `default_headers` injectent automatiquement `x-opencode-session` et `User-Agent: mirofish/0.1.0`
> vers OpenCode Go sans polluer les autres fournisseurs (neutralité préservée même si `base_url=None`),
> le mode `json_object` est actif par défaut, les balises `<think>` des modèles de raisonnement
> sont nettoyées et `LLM_REASONING_EFFORT` est relayé via `extra_body`.
> Sonde de vérification fiabilisée (`backend/scripts/verifier_llm_graphiti.py`) et critère C2 prouvé
> (0 échec `MissingSessionID`). Revue de code contradictoire passée (4 couches, 6 correctifs appliqués).
> Fichier : [`story-001-3.md`](plans/001-epreuve-graphiti-local/story-001-3.md).

### La story 001-4 est `done` — Embedder local Sentence-Transformers pour Graphiti

> `SentenceTransformerEmbedder` sous-classe `EmbedderClient` dans `backend/app/utils/graphiti_embedder.py`.
> L'investigation a levé la fausse hypothèse de blocage : `graphiti-core` n'embarquant aucun embedder
> interne, aucun extra n'est nécessaire et `sentence-transformers==3.0.0` (fourni par `camel-oasis`)
> opère déjà localement.
> Modèle par défaut : `all-MiniLM-L6-v2` (384 dimensions, coût marginal de 0 €), chargement paresseux
> (*lazy-loading*) thread-safe, encodage asynchrone non-bloquant via `asyncio.to_thread` et conversion
> en flottants natifs Python.
> Sonde de vérification validée (`backend/scripts/verifier_embedder_graphiti.py`) : inférence ~7 ms à chaud,
> lot de 8 entités en ~50 ms (~6 ms/entité), mode `--mock` autonome et instanciation conjointe avec `Graphiti`
> sans clé OpenAI. Revue de code contradictoire passée (4 couches, 6 correctifs appliqués).
> 18 tests unitaires hermétiques dans `backend/tests/test_graphiti_embedder.py`. Fichier : [`story-001-4.md`](plans/001-epreuve-graphiti-local/story-001-4.md).

### La story 001-5 est `done` — Épreuve sur 30 chunks exécutée et rapport versionné (Verdict GO)

> Le banc de mesure autonome `backend/scripts/mesurer_extraction_graphiti.py` a exécuté
> l'épreuve complète en conditions réelles sur les 30 premiers chunks du document parlementaire
> (rapport AN n° 2506) avec `space-bunny`, l'embedder local `all-MiniLM-L6-v2` et Neo4j 5.26 :
> - **C1 (Épisodes sans erreur)** : **29/30 (96.7 %)** (seuil ≥ 90 % / 27/30). 1 seule anomalie isolée sur le chunk 22.
> - **C2 (Authentification / session)** : **0 échec `MissingSessionID`**.
> - **C3 (Persistance graphe Neo4j)** : **49 nœuds et 45 relations** persistés et relus.
> - **C4 (Temporalité `valid_at`)** : **11 arêtes temporelles** renseignées (corrigé en revue BMad 4 couches).
> - **C5 (Rapport versionné)** : [`rapport.md`](plans/001-epreuve-graphiti-local/rapport.md) généré avec **Verdict GO** en tête.
> Revue de code contradictoire passée (4 couches, 8 patchs appliqués, 1 rejeté documenté).
> 17 tests unitaires hermétiques dans `backend/tests/test_mesure_extraction_graphiti.py`. Fichier : [`story-001-5.md`](plans/001-epreuve-graphiti-local/story-001-5.md).

**333 tests verts**, 315 + 18 (tests unitaires hermétiques et sonde mockée).

**`graphiti-core` envoie une télémétrie par défaut — elle est coupée.**
`posthog 7.62.1` entre dans le lock avec `graphiti-core`, et la bibliothèque
écrit une télémétrie d'initialisation vers `us.i.posthog.com` depuis
`Graphiti.__init__`, **activée par défaut** (`telemetry.py:36`, défaut `'true'`).
Un projet dont la thèse est le local-first ne peut pas laisser sortir de la
machine sans l'avoir demandé : `app/config.py` pose
`GRAPHITI_TELEMETRY_ENABLED=false` par défaut **et** pousse la variable dans
l'environnement, parce que c'est là que la bibliothèque la lit. Six tests, dont un
qui prouve que la bibliothèque aurait été active de sa propre initiative.

L'override, dans la forme exacte que l'ADR 0011 impose :

```toml
[tool.uv]
override-dependencies = ["neo4j>=5.26.0,<6.0.0"]
# version effectivement résolue au lock du 2026-10-03 : neo4j 5.28.6
```

Le point difficile n'était pas la déclaration : c'est que poser l'override
**cascait le protocole de mesure de la 001-1**. Il ne casse plus — il **normalise**
`pyproject.toml` dans l'état qu'il veut mesurer, puis restaure l'octet initial,
et **refuse** un arbre ambigu au lieu de le deviner. Rejoué sur les deux arbres,
204 tests verts sur l'arbre d'avant, 234 sur celui d'après — les deux sorties
sont versionnées dans [`mesures-001-1b.md`](plans/001-epreuve-graphiti-local/mesures-001-1b.md).
[`story-001-1b.md`](plans/001-epreuve-graphiti-local/story-001-1b.md).

## À faire

| Epic | Titre | Dépend de |
|---|---|---|
| 002 | Interface `GraphStore` + `ZepGraphStore` + factory | 001 |
| 003 | `GraphitiGraphStore` : écriture et chemin de lecture | 001, 002 |
| 004 | Construire un graphe sans clé Zep — la preuve finale | 003 |
| 005 | Docker local : Neo4j dans le compose — **le compose d'épreuve existe déjà**, il s'y substituera | 003 |
| 006 | Migrer le graphe Zep existant — ou acter qu'on jette | 003 |
| 007 | Ontologie dynamique (v2) | 003 |

---

## Critères de succès de l'épreuve — chiffrés, sinon « ça tient » ne veut rien dire

| # | Critère | Seuil |
|---|---|---|
| C1 | Épisodes extraits sans erreur | **≥ 27 sur 30** chunks (90 %) |
| C2 | Échecs d'authentification (`MissingSessionID`) | **0** |
| C3 | Graphe non vide **et relisible après redémarrage de Neo4j** | ≥ 1 entité, ≥ 1 relation persistées |
| C4 | Temporalité : `valid_at` renseigné | ≥ 1 arête |
| C5 | Rapport de mesure versionné dans le dépôt | 1 fichier |

Échantillon : les 30 premiers chunks du rapport n° 2506 de l'Assemblée
nationale (URL et sha256 dans le PRD de l'epic 001).

**Règle de décision** : si C1 ou C2 échoue, on s'arrête là. Pas de migration
partielle sur une extraction qui ne fonctionne pas. Le repli est alors
l'extraction sur un modèle payant ponctuel, moins cher que des crédits Zep.

## Prochain pas

1. **Produire le verdict go / no-go** (story 001-6) et clore l'epic 001.
2. Démarrer l'epic 002 (interface `GraphStore` et factory).

## Questions ouvertes

| Question | Effet si la réponse change |
|---|---|
| Le graphe Zep actuel contient-il quelque chose à garder ? | Epic 006 : migration possible ou non |
| ~~`camel-oasis` et `graphiti-core` sont-ils compatibles dans un venv ?~~ | **répondu non** (story 001-1) — parade mesurée et rejouable : override du driver, **actée par l'ADR 0010**, précisée par l'ADR 0011 |
| Le driver `neo4j` forcé à **5.28.6** tient-il **à l'exécution** ? | 001-2 est le premier test ; s'il casse, l'ADR 0010 est supersédé et on bascule sur un venv séparé. La version est lockée et **consignée dans `pyproject.toml`**, donc 001-2 teste bien celle qui sera déployée |
| ~~`sentence-transformers` : même conflit que `neo4j` ?~~ | **fausse hypothèse levée** (story 001-4) : `graphiti-core` ne fournit pas d'embedder, l'interface `EmbedderClient` est abstraite et `sentence-transformers==3.0.0` opère déjà sans extra ni override |
| ~~La politique d'usage de l'endpoint gratuit tient-elle à ce volume ?~~ | **Validé (story 001-5)** : 29/30 chunks extraits sans saturation ni blocage réseau sous rate limiting (délai 1s) |
| Le reranker supporte-t-il cet endpoint (logprobs) ? | repli RRF / pass-through local validé sans clé OpenAI (NFR-1) |

## Chiffres de référence

| | |
|---|---|
| Tests | **327**, tous verts, **sans `.env`** (+12 par la 001-5 ; 315 avant) |
| Lint | ruff, règles volontairement étroites (amont) |
| Amont | `666ghj/MiroFish` — AGPL-3.0, très actif |
| ADR | 11 acceptés, 0 supersédé |
| Node | pnpm 10.23.0, version figée dans `packageManager`, `package-lock.json` supprimés |
| Environnement de référence | Docker dès que l'epic 005 est fait (ADR 0006) — en attendant, on travaille en local, et c'est dit |
| Fork audités | 6 — 0 adopté |