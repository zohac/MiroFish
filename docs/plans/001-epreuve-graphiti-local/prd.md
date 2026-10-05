# Epic 001 — Épreuve Graphiti local

- **Statut** : `in-progress` · **Dépend de** : rien · **Bloque** : 002, 003
- **Suivi** : [`sprint-status.yaml`](../../../docs/sprint-status.yaml)

> On mesure avant de construire. Le plan complet du projet est dans
> [`docs/LOCAL-FIRST.md`](../../LOCAL-FIRST.md) ; cet epic est le **test qui
> rend le reste décideable**.

---

## Le problème

Le remplacement de Zep par Graphiti n'a de sens que si l'extraction
d'entités fonctionne avec notre LLM gratuit. Or un modèle gratuit et
« stealth » ne garantit rien sur le structured output, dont Graphiti dépend
(comportement documenté : les petits modèles produisent souvent un JSON qui ne
correspond pas au schéma).

Tant que ce n'est pas mesuré, tout le reste est spéculatif — y compris
l'estimation de 2 à 4 jours.

## L'hypothèse testée

> `space-bunny-free`, appelé via Graphiti avec l'en-tête de session et le mode
> `json_object`, extrait des entités et des relations exploitables sur un
> document réel, sans intervention manuelle.

## L'objectif

**Mesurer.** Produire un verdict go / no-go documenté, reproductible, avec des
chiffres — pas une impression.

## Ce que cet epic n'est pas

| Hors périmètre | Pourquoi |
|---|---|
| L'interface `GraphStore` | epic 002 |
| Le chemin de lecture (ADR 0003) | epic 003 |
| L'ontologie dynamique | v2, ADR 0003 |
| Docker | epic 005 |
| Modifier le code de production | on mesure dans un script, pas dans les services |

## Critères de sortie — chiffrés

| # | Critère | Seuil | Sinon |
|---|---|---|---|
| C1 | Épisodes extraits sans erreur | **≥ 27 / 30** chunks (90 %) | no-go |
| C2 | Échecs d'authentification (`MissingSessionID`) | **0** | no-go (bug de plumbing, à corriger puis re-mesurer) |
| C3 | Graphe non vide **et relisible après redémarrage de Neo4j** | ≥ 1 entité, ≥ 1 relation | no-go |
| C4 | Temporalité : `valid_at` renseigné sur une arête | ≥ 1 arête | signal d'alerte, pas bloquant |
| C5 | Rapport de mesure versionné | 1 fichier | l'épreuve n'a pas eu lieu |

Échantillon : **les 30 premiers chunks** du rapport n° 2506 décrit plus bas —
borné, reproductible, et assez large pour qu'un « ça marche » ait un sens.

**Règle de décision** : si C1 ou C2 échoue, on s'arrête. Pas de migration
partielle au-dessus d'une extraction qui ne fonctionne pas.

## Le document retenu

**Rapport d'information n° 2506** — « La territorialisation et le portage des
politiques publiques en termes d'aménagement du territoire et de transition
énergétique et écologique », commission du développement durable et de
l'aménagement du territoire, 17ᵉ législature. Déposé le 18 février 2026.

| | |
|---|---|
| Source | `https://www.assemblee-nationale.fr/dyn/17/rapports/cion-dvp/l17b2506_rapport-information.pdf` |
| Format | PDF 1.5, 80 pages, 3,1 Mo — format accepté (`config.py:54`) |
| sha256 | `4281a931545537f56625c3f4d0907fc6…` |
| Texte extrait | **26 168 mots**, 189 503 caractères |
| Entités | sigles et institutions (CRTE, PETR, EPCI, SGPE, PCAET, ANCT), personnes nommées (Dominique Faure, Boris Ravignon, Éric Woerth, Élisabeth Borne) |
| Temporalité | 28 années distinctes citées (2019 → 2030), 18 marqueurs explicites (« depuis », « à partir de »…) |

Le sujet est débat et choral — territorialisation, transition énergétique,
portage par les collectivités : exactement le type de document pour lequel
MiroFish est utile. Il y a des acteurs qui se contredisent, des décisions
datées, des positions à essaimer.

Le fichier n'est **pas** versionné : l'URL et le sha256 ci-dessus suffisent à
le retrouver à l'identique. Il est téléchargé dans
`backend/uploads/documents/` (répertoire gitignoré).

### Découverte en préparant l'entrée — `chunk_size` est en caractères

`split_text_into_chunks(text, chunk_size, overlap)` découpe en **caractères**
(`file_parser.py:161`, docstring « 每块的字符数 »), pas en mots. Le défaut est
500 caractères, recouvrement 50 (`config.py:41`).

Conséquence mesurée sur ce document : **562 chunks**, soit ~385 caractères et
~54 mots par chunk.

Donc « 5 000 mots pour 10 chunks » était faux d'un facteur ~12 : 5 000 mots
donneraient environ 1 400 chunks, donc 1 400 appels d'extraction. L'épreuve
est bornée à un **échantillon des 30 premiers chunks** (~1 600 mots).

Deux choses en découlent :

- `chunk_size` est un **réglable**, pas une constante : surchargé par requête
  (`api/graph.py:587`) et par projet (`project.chunk_size`). On pourra donc le
  mesurer plus tard.
- 500 caractères ≈ 54 mots, c'est petit : une relation qui s'étale sur
  plusieurs phrases sera coupée. La qualité du graphe dépendra autant du
  réglage que du modèle. **Question ouverte pour l'epic 003**, pas pour cette
  épreuve.

## Ce qu'on mesure au-delà des seuils

- nombre d'appels LLM pour 10 chunks (l'extraction coûte plusieurs appels)
- latence par chunk
- retries et timeouts
- **schémas refusés** (erreur de validation) vs échecs réseau — ils se
  ressemblent mais n'appellent pas les mêmes parades
- dimensions d'embedding retenues (pour le reranker)

## Risques

| Risque | Signal | Parade |
|---|---|---|
| Conflit `graphiti-core` / `camel-oasis` sur le driver Neo4j | erreur d'import ou version incompatibe | forcer le driver par `override-dependencies` — acté par l'ADR 0010, précisé par l'ADR 0011, posé par la story 001-1b |
| Structured output non honoré | erreur de validation JSON | mode `json_object`, puis modèle payant |
| `MissingSessionID` | HTTP 400 | sous-classe du client LLM |
| Reranker incompatible | erreur de logprobs | repli RRF |
| Politique d'usage de l'endpoint | throttling, 429 | `SEMAPHORE_LIMIT` bas, extraction en série |

## Décision attendue à la fin

Un **go / no-go écrit dans [`docs/STATUS.md`](../../STATUS.md)** :

- **go** → on enchaîne sur l'epic 002 (interface `GraphStore`)
- **no-go** → on bascule l'extraction sur un modèle payant ponctuel, qui reste
  moins cher que des crédits Zep, et on documenterait la décision dans un ADR