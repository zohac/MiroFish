# 0010 — Forcer le driver `neo4j` pour que Graphiti et `camel-oasis` coexistent

- **Statut** : accepté
- **Date** : 2026-10-03

## Contexte

Pour remplacer Zep (ADR 0001), il faut pouvoir faire tourner `graphiti-core` et
`camel-oasis` — le moteur de simulation — **dans le même environnement**. La
story [`001-1`](../plans/001-epreuve-graphiti-local/story-001-1.md) a mesuré
que c'est impossible tel quel :

| Paquet | Exigence | Depuis |
|---|---|---|
| `camel-oasis==0.2.5` | `neo4j==5.23.0` (pin **exact**) | ses 9 versions publiées, de 0.0.1 à 0.2.5 |
| `graphiti-core` | `neo4j>=5.26.0` | la 0.12.0 (juin 2025) |

Ce sont deux épinglages exacts sur des versions qui ne se recouvrent pas : le
résolveur refuse, et **aucune combinaison des paquets publiés ne résout**. Ce
n'est donc pas un lock à refaire ni un fork mal fiché — c'est une contrainte
structurelle de l'amont, présente chez le fork de référence `tt-a1i`, qui a dû
contourner par un second venv *et* un sous-processus
(`simulation_runner._get_simulation_python`).

`camel-ai` lui-même accepte large (`neo4j>=5.18,<6`) : c'est `oasis` qui
resserre à l'exact, pour son stockage graphe interne.

L'alternative naturelle — forcer le driver via
`[tool.uv] override-dependencies` — a été **essayée et mesurée**, pas supposée
fiable : le lock résout, `oasis`, `neo4j` et `graphiti_core` s'importent dans
l'ordre, et les 183 tests restent verts.

## Décision

**On force le driver `neo4j` par `override-dependencies` côté `uv`, et on
n'introduit pas de second environnement.**

```toml
[tool.uv]
override-dependencies = ["neo4j>=5.26.0,<6.0.0"]
```

Cette décision **tranche l'architecture, elle n'applique rien**. L'override
n'est pas dans `pyproject.toml` à la date de cet ADR : il sera posé par une
story dédiée, après revalidation. Un ADR écrit avant l'exécution décrit
l'intention ; celui-ci décrit un geste déjà essayé et mesuré, avec sa limite
assumée.

Deux règles encadrent la mise en œuvre.

1. **Le périmètre de l'override est `neo4j` seul.** Le conflit
   `sentence-transformers==3.0.0` (camel-oasis) contre `>=3.2.1` (extra Graphiti)
   est **de même nature mais n'est pas tranché ici** : story 001-4, à revalider
   séparément. Un saut de `sentence-transformers` 3.0 → 3.2 est un changement
   de modèle et de `torch`, il ne se décide pas par analogie avec un driver.
2. **Un `override` est une promesse faite au résolveur, pas au projet.** On
   promet que le code de `camel-oasis` fonctionne avec un driver qu'il déclare
   incompatible. C'est vérifié au niveau de l'API (son usage du driver se
   limite à `GraphDatabase.driver()` et `neo4j.Version`), **pas à l'exécution**.
   Si la story 001-2 révèle un comportement cassé, cet ADR est supersédé —
   il ne sera pas réécrit.

## Conséquences

**Positives**

- **Un seul environnement** (ADR 0006 respecté) : pas de second venv, pas de
  sous-processus, pas de versions qui divergent en silence.
- Le lock reste **reproductible et vérifiable** : `uv sync --frozen` continue de
  fonctionner dans l'image, et `uv tree --invert --package neo4j` documente
  immédiatement qui tire quoi.
- Aucun changement de code : le geste est dans la déclaration de dépendances.

**Négatives**

- On **contourne délibérément** une contrainte déclarée par l'amont. Le jour où
  `camel-oasis` utilise une API du driver retirée en 5.26+, on ne le saura pas
  à la résolution : l'override aura produit un lock valide et un runtime cassé.
- Le garde-fou est faible : c'est `uv lock` qui échouerait, et seulement si
  quelqu'un le relance. Rien ne surveille la dérive en continu.
- Le saut 5.23 → 5.28 est **plus large que nécessaire** : Graphiti demande
  `>=5.26`, on atterrit sur la dernière 5.x disponible au moment du lock. Le
  verrouiller plus bas est possible, mais cela exige d'être revalidé à chaque
  release du driver.
- **Le comportement réel n'est pas encore prouvé** : aucun test de la story
  001-1 n'ouvre de connexion. C'est la story 001-2 qui tranche, et donc
  Indirectement cet ADR.

## Alternatives rejetées

- **Un second venv pour Graphiti** (ce qu'a fait `tt-a1i`) — fonctionne, mais
  c'est exactement les deux environnements que l'ADR 0006 interdit, plus un
  sous-processus à maintenir pour un problème d'une ligne. Coût permanent,
  bénéfice nul.
- **Rétrograder `graphiti-core` à une version compatible avec `neo4j==5.23.0`**
  — techniquement possible : les versions jusqu'à **0.11.6** (mai 2025)
  acceptaient `neo4j>=5.23.0`. Rejeté quand même : cela fait passer Graphiti de
  la 0.30 visée à une version de **dix-sept mois**, antérieure au travail sur
  l'APOC et au Cypher de 5.26, et antérieure à notre propre compréhension du
  produit. On migrerait vers une bibliothèque qu'on n'a pas encore apprise à
  utiliser pour résoudre un problème de dépendance — c'est le coût que l'ADR
  0002 a déjà refusé de payer avec les forks.
- **Patcher `camel-oasis`** (fork ou `sitecustomize` pour desserrer le pin) —
  crée une divergence avec l'amont pour un besoin ponctuel. Le réintégrage de
  l'amont, déjà coûteux (ADR 0002, §12.4 de `LOCAL-FIRST.md`), le deviendrait
  davantage.
- **Attendre un desserrage amont du pin** — aucune version de `camel-oasis`
  postérieure à 0.2.5 n'existe (dernière publication : décembre 2025). On ne
  peut pas attendre et voir sur un mouvement qui n'est pas annoncé.

## Références

- [`story-001-1.md`](../plans/001-epreuve-graphiti-local/story-001-1.md) — la
  mesure, ses chiffres, et la limite assumée
- [ADR 0001](0001-remplacement-de-zep-par-graphiti.md) — pourquoi Graphiti
- [ADR 0006](0006-docker-first.md) — pourquoi un seul environnement
- [`docs/LOCAL-FIRST.md` §11](../LOCAL-FIRST.md) — le point ouvert, désormais
  tranché