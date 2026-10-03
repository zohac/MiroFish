# 0002 — Ne pas adopter de fork communautaire : prendre la forme, pas le code

- **Statut** : accepté
- **Date** : 2026-10-03

## Contexte

Six forks communautaires ont été audités le 3 octobre 2026
(`docs/LOCAL-FIRST.md` §12). Deux sont « sérieux » : `tt-a1i/MiroFish-local`
(Graphiti + Neo4j derrière un adaptateur) et `nikmcfly/MiroFish-Offline`
(Neo4j + Ollama, ~2 570 ★).

Les deux sont **gelés depuis mars 2026** et **ne sont pas des forks GitHub de
l'amont** : aucun lien de synchronisation, `tt-a1i` n'a même pas de branche
`main`. Entre leur base et aujourd'hui, l'amont a gagné **+2 785 / −1 017
lignes sur les 14 fichiers** que `tt-a1i` a touchés.

Et le code lui-même ne va pas dans notre sens :

| Constat | Emplacement |
|---|---|
| Structured output jamais configuré (0 occurrence de `structured_output_mode`) | `zep_graphiti_impl.py` |
| Temporalité écrasée (`invalid_at`/`expired_at` forcés à `None`) | leur `graph_builder.py:489-490` |
| Patch figé sur la signature de `graphiti-core` 0.25.0 (actuel : 0.30.2), sans contrôle de version | leur `graphiti_patch.py` |
| `set_ontology()` = no-op ; `custom_entity_types=` jamais utilisé | leur `zep_graphiti_impl.py:363-389` |
| **Aucun test** — `backend/tests/` n'existe pas dans le fork | — |

Le point le plus grave n'est pas une limitation mais un **échec silencieux** :
`get_episode_status()` renvoie toujours `processed=True`, donc la
construction du graphe rapporte un succès complet même quand rien n'a été
extrait.

## Décision

**On n'adopte aucun fork.** On réutilise la *forme* et on réécrit le reste.

Concrètement, on garde comme références : l'ossature interface + deux
implémentations + factory, l'isolation par `group_id`, le
`docker-compose.local.yml` (Neo4j 5.26 + APOC + volumes), et le mapping
`OPENAI_* ← LLM_*`.

## Conséquences

**Positives**

- Maîtrise totale du code : pas de monkey-patch en amont, pas de surprise au
  changement de version de Graphiti.
- Le code reste aligné sur l'amont, qui avance vite (≈100 commits depuis mars).
- Nos tests couvrent la couche — c'est précisément leur absence qui rend les
  bugs ci-dessus invisibles.

**Négatives**

- L'estimation de 2 à 4 jours **n'est pas réduite** par l'existence des forks.
  Le gain réel est d'un demi-jour sur l'ossature d'adaptateur, pas sur les
  points durs.
- On réécrit ce que d'autres ont déjà écrit. C'est le prix de la maîtrise.

## Alternatives rejetées

- **Baser le projet sur `tt-a1i`** — 7 mois de retard, échecs silencieux,
  zéro test, patch cassant.
- **Baser le projet sur `nikmcfly`** — le plus prêt à l'emploi (2 570 ★,
  Ollama intégré), mais **sans Graphiti, donc sans temporalité** : on perd
  exactement ce qui fait la valeur du projet.
- **Rebaser leur branche sur l'amont** — 3 800 lignes de conflit sur 14
  fichiers, pour un résultat moins bon que du neuf.
- **PR #634 (JSON local)** — fermée non mergée, et régressive.