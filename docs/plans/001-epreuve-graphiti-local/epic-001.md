# Epic 001 — Épreuve Graphiti local

- **Statut** : `in-progress` · **Dépend de** : rien · **Bloque** : 002, 003
- **Suivi** : [`sprint-status.yaml`](../../../docs/sprint-status.yaml)

> On mesure avant de construire. Le plan complet du projet est dans
> [`docs/LOCAL-FIRST.md`](../../LOCAL-FIRST.md).

**Artefacts de ce dossier** — [`prd.md`](prd.md) (quoi, pourquoi, critères
chiffrés) · [`architecture.md`](architecture.md) (comment) · ce fichier (le
contrat d'ingénierie) · `story-001-<n>.md` (une story démarrée = un fichier
markdown).

---

## Le problème en une phrase

Le remplacement de Zep par Graphiti n'a de sens que si l'extraction d'entités
fonctionne avec notre LLM gratuit — et personne n'a mesuré si un modèle gratuit
et « stealth » tient le structured output dont Graphiti dépend.

## Objectif

**Mesurer**, produire un verdict go / no-go chiffré et reproductible, puis
sortir de l'ambiguïté. Pas de code de production touché : tout vit dans un
script.

## Exigences fonctionnelles

| # | Exigence |
|---|---|
| FR-1 | Extraire le texte du rapport n° 2506 avec le parseur du projet (`FileParser`), pas avec un autre outil |
| FR-2 | Découper selon le découpage réel du projet (500 caractères / recouvrement 50) et ne traiter que les **30 premiers** chunks |
| FR-3 | Configurer Graphiti avec l'endpoint LLM du projet et un embedder local |
| FR-4 | Faire porter l'en-tête de session par le client LLM **de Graphiti**, qui ne voit pas notre module de compatibilité |
| FR-5 | Écrire chaque chunk comme épisode, en mesurant succès, échec, latence et type d'erreur |
| FR-6 | Relire le graphe après **redémarrage** de Neo4j : nœuds, arêtes, dates |
| FR-7 | Produire un rapport de mesure versionné |

## Exigences non fonctionnelles

| # | Exigence | Pourquoi |
|---|---|---|
| NFR-1 | Coût total **0 €** | c'est la raison d'être du local-first |
| NFR-2 | Aucun secret dans le rapport, le script ou l'image | `.env` n'est jamais versionné, le rapport est versionné |
| NFR-3 | Script **rejouable à l'identique** : pas d'état caché, sortie capturée dans un fichier | une mesure non rejouable ne vaut pas une mesure |
| NFR-4 | Le rapport se lit en **2 minutes** : verdict en tête, chiffres ensuite | c'est l'UX de cet epic (voir plus bas) |
| NFR-5 | Les tests existants restent verts — **234** (183 à l'écriture de cet epic ; +9 de revue le 3 octobre, +12 par la 001-1b, +30 par la revue de la 001-1b) | le filet de sécurité ne doit pas bouger |
| NFR-6 | L'épreuve tourne sous Docker dès que l'epic 005 est fait ; **en attendant, en local** — et c'est dit | ADR 0006 n'est pas encore exécutable |

## UX requirements

Cet epic n'a **pas d'interface** : c'est un script et un rapport. L'UX est
donc le document lui-même, et elle a une exigence : **le verdict go / no-go
en tête du rapport**, pas en annexe. Quelqu'un doit pouvoir ouvrir
`rapport.md` et savoir en dix secondes si on continue.

## Index des stories

| Story | Titre | Statut | Fichier |
|---|---|---|---|
| 001-1 | Vérifier le conflit `graphiti-core` vs `camel-oasis` | `done` | [`story-001-1.md`](story-001-1.md) |
| 001-1b | Poser l'`override-dependencies` — **décidé par l'ADR 0010, précisé par l'ADR 0011** | `done` | [`story-001-1b.md`](story-001-1b.md) |
| 001-2 | Neo4j 5.26 + APOC en local, avec volumes nommés — **premier test comportemental du driver forcé** | `backlog` | [`story-001-2.md`](story-001-2.md) |
| 001-3 | Client LLM Graphiti portant l'en-tête de session | `backlog` | — |
| 001-4 | Embedder local `sentence-transformers` | `backlog` | — |
| 001-5 | Script de mesure reproductible + rapport versionné | `backlog` | — |
| 001-6 | Verdict go / no-go documenté | `backlog` | — |

> **Pourquoi 001-3 et 001-4 n'ont pas de contenu détaillé ici** : leurs
> critères Given/When/Then sont dans le tableau ci-dessous. Le fichier
> `story-<n>.md` sera créé au moment où la story démarre — c'est la règle :
> un fichier par story **réellement démarrée**, pas imaginée. Le script de
> validation impose l'inverse, lui : une story `in-progress` ou au-delà **doit**
> avoir un fichier et être citée dans ce document.
>
> `001-2` a son fichier alors qu'elle est `backlog` : c'est le premier test
> comportemental du driver forcé, et ses choix — version du serveur figée,
> compose séparé, surface à exercer — méritaient d'être écrits **avant** de la
> démarrer, pas pendant. C'est une exception assumée : le fichier est là pour
> fixer le périmètre, pas pour prétendre que le travail a commencé.

| Story | Critères d'acceptation (résumé) |
|---|---|
| 001-1 | Given `graphiti-core` ajouté, when `uv sync` tourne, then **aucune erreur de résolution** — ⚠️ **échec mesuré et rejouable** (`mesurer-001-1.sh`, sortie dans `mesure-001-1.txt`) : `neo4j==5.23.0` est un pin exact que `graphiti-core` ne peut pas satisfaire (plancher `>=5.26.0`), et l'inverse vaut aussi · sous l'`override` de l'ADR 0010, `camel-oasis`, `neo4j` et `graphiti_core` s'importent dans cet ordre et les tests restent verts |
| 001-1b | Given l'ADR 0010 et l'ADR 0011, when on ajoute `override-dependencies = ["neo4j>=5.26.0,<6.0.0"]` dans `backend/pyproject.toml`, then `uv lock` résout · `uv sync --frozen` réussit · `oasis`, `neo4j` et `graphiti_core` s'importent dans cet ordre · les tests passent · **le geste est réversible** : retirer l'override puis `git checkout backend/pyproject.toml backend/uv.lock` ramène l'arbre à l'état initial, et `uv lock` **échoue à nouveau** sans l'override — c'est bien la preuve du conflit, pas une restauration du lock · *mesuré, en revue* : `neo4j 5.28.6` lockée, lock revenu au sha `1b41b865…` après `git checkout`, `mesurer-001-1.sh` rejoué sur **les deux** arbres, les deux sorties versionnées dans [`mesures-001-1b.md`](mesures-001-1b.md) |
| 001-2 | Given un `docker-compose.neo4j.yml` séparé et un serveur **figé** sur `neo4j:5.26.31-community`, when il démarre, then le healthcheck Bolt passe au vert · une écriture puis une relecture passent par `neo4j 5.28.6` sous le pin `camel-oasis`, sans workaround · un nœud survit à l'arrêt puis au redémarrage · les quatre symboles de la surface de l'ADR 0011 sont **exercés**, dont la hiérarchie d'exceptions prouvé par un `ClientError` réel · le verdict est écrit et l'écart driver/serveur consigné — **premier test comportemental du driver forcé** ; s'il casse, l'ADR 0010 est supersédé |
| 001-3 | Given un appel d'extraction, when l'hôte est `opencode.ai`, then aucun `MissingSessionID` · given un autre endpoint, then aucun en-tête ajouté |
| 001-4 | Given l'embedder local, when un texte est encodé, then les dimensions sont stables · l'extraction fonctionne sans API d'embeddings — ⚠️ **bloquée par le même conflit que `neo4j`** (`sentence-transformers==3.0.0` vs `>=3.2.1`) : arbitrage propre à faire, l'ADR 0010 ne la couvre pas |
| 001-5 | Given le rapport AN n° 2506, when le script est lancé, then 30 chunks sont traités · le rapport contient appels, latences, retries, erreurs exactes · il est commité |
| 001-6 | Given C1 à C5, when le verdict est écrit, then il est dans `docs/STATUS.md` · un no-go déclenche un ADR · un go fait passer 002 en `in-progress` |

## Documents à consulter

| Document | Ce qu'on y prend |
|---|---|
| [`prd.md`](prd.md) | l'hypothèse testée et les seuils |
| [`architecture.md`](architecture.md) | le squelette Graphiti, et les points marqués « à confirmer » |
| [`docs/LOCAL-FIRST.md` §6.3](../../LOCAL-FIRST.md) | pourquoi le structured output est le point de rupture |
| [`docs/LOCAL-FIRST.md` §12.6](../../LOCAL-FIRST.md) | les quatre points de rupture au même endroit |
| [`docs/architecture/cible-graphstore.md`](../../architecture/cible-graphstore.md) | la séquence de construction et ses quatre risques |
| [ADR 0003](../../decisions/0003-ontologie-differee-en-v2.md) | pourquoi l'ontologie est hors de cette épreuve |
| [ADR 0004](../../decisions/0004-llm-opencode-go.md) | la compat session, et le fait que Graphiti n'est pas couvert |
| [ADR 0006](../../decisions/0006-docker-first.md) | NFR-6 |
| [ADR 0010](../../decisions/0010-override-driver-neo4j.md) | pourquoi on force le driver plutôt que de séparer les environnements |
| [ADR 0011](../../decisions/0011-inventaire-driver-et-format-de-story.md) | la surface réelle du driver, la version résolue, le format de story |
| `backend/app/config.py:41` | `DEFAULT_CHUNK_SIZE` = 500 **caractères** |
| `backend/app/utils/file_parser.py:161` | le découpage et ses limites |
| `backend/app/api/graph.py:587` | `chunk_size` est surchargeable par requête et par projet |

## Décisions liées

- **ADR 0001** — Graphiti + Neo4j derrière une interface (le but de l'épreuve)
- **ADR 0003** — pas d'ontologie custom en v1 (donc pas ici)
- **ADR 0004** — endpoint gratuit, compat session centralisée
- **ADR 0006** — Docker d'abord, quand l'epic 005 aura rendu la chose possible

## L'epic est terminé quand

- [ ] C1 à C5 evaluated et consignés dans [`rapport.md`](rapport.md)
- [ ] Verdict go / no-go écrit dans [`docs/STATUS.md`](../../STATUS.md)
- [ ] Un no-go a produit un ADR ; un go a fait passer l'epic 002 en `in-progress`
- [ ] `rapport.md` est versionné, le script est rejouable, aucune histoire en suspens
- [ ] Les tests existants restent verts — **234** (183 à l'écriture de l'epic, +9 de revue, +12 par la 001-1b, +30 par sa revue)