# Epic 001 — Épreuve Graphiti local

- **Statut** : `in-progress` · **Dépend de** : rien · **Bloque** : 002, 003
- **Suivi** : [`sprint-status.yaml`](../../../sprint-status.yaml)

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

## Critères de succès — chiffrés

| # | Critère | Seuil | Sinon |
|---|---|---|---|
| C1 | Épisodes extraits sans erreur | **≥ 9 / 10** chunks | no-go |
| C2 | Échecs d'authentification (`MissingSessionID`) | **0** | no-go (bug de plumbing, à corriger puis re-mesurer) |
| C3 | Graphe non vide **et relisible après redémarrage de Neo4j** | ≥ 1 entité, ≥ 1 relation | no-go |
| C4 | Temporality : `valid_at` renseigné sur une arête | ≥ 1 arête | signal d'alerte, pas bloquant |
| C5 | Rapport de mesure versionné | 1 fichier | l'épreuve n'a pas eu lieu |

**Règle de décision** : si C1 ou C2 échoue, on s'arrête. Pas de migration
partielle au-dessus d'une extraction qui ne fonctionne pas.

## Entrée nécessaire — bloquante

Un **document réel d'au moins 5 000 mots** (10 chunks de 500), PDF, MD ou
TXT. Sans lui, l'épreuve ne peut pas produire de chiffre. C'est le seul
élément bloquant côté entrée.

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
| Conflit `graphiti-core` / `camel-oasis` sur le driver Neo4j | erreur d'import ou version incompatibe | venv séparé pour le graphe |
| Structured output non honoré | erreur de validation JSON | mode `json_object`, puis modèle payant |
| `MissingSessionID` | HTTP 400 | sous-classe du client LLM |
| Reranker incompatible | erreur de logprobs | repli RRF |
| Politique d'usage de l'endpoint | throttling, 429 | `SEMAPHORE_LIMIT` bas, extraction en série |

## Décision attendue à la fin

Un **go / no-go écrit dans [`docs/STATUS.md`](../../STATUS.md)** :

- **go** → on enchaîne sur l'epic 002 (interface `GraphStore`)
- **no-go** → on bascule l'extraction sur un modèle payant ponctuel, qui reste
  moins cher que des crédits Zep, et on documenterait la décision dans un ADR