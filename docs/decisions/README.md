# ADR — décisions d'architecture

Un ADR (*Architecture Decision Record*) capture **une** décision : son
contexte, la décision elle-même, ses conséquences, et les alternatives
rejetées. Il existe pour qu'une conversation difficile ne se recommence pas
dans six mois.

---

## Format

```markdown
# NNNN — Titre de la décision

- **Statut** : proposé | accepté | supersédé par ADR-NNNN
- **Date** : AAAA-MM-JJ

## Contexte
Ce qui force la décision. Faits, avec sources.

## Décision
Une phrase, à l'impératif. « On… »

## Conséquences
Ce que ça oblige à faire. Positive ET négative.

## Alternatives rejetées
Ce qu'on a écarté, et pourquoi. C'est la section la plus utile six mois plus tard.
```

## Index

| ADR | Décision | Statut |
|---|---|---|
| [0001](0001-remplacement-de-zep-par-graphiti.md) | Remplacer Zep par Graphiti + Neo4j derrière une interface | accepté — 2026-10-03 |
| [0002](0002-forks-adoption-refusee.md) | Ne pas adopter de fork communautaire | accepté — 2026-10-03 |
| [0003](0003-ontologie-differee-en-v2.md) | Ontologie dynamique reportée en v2 | accepté — 2026-10-03 |
| [0004](0004-llm-opencode-go.md) | LLM sur endpoint gratuit OpenCode Go | accepté — 2026-10-03 |
| [0005](0005-licence-agpl.md) | Rester local ; exposer en réseau ⇒ sources publiées | accepté — 2026-10-03 |
| [0006](0006-docker-first.md) | Docker d'abord : un seul environnement de référence | accepté — 2026-10-03 |
| [0007](0007-une-story-un-fichier.md) | Une story = un fichier, l'état vit avec la story | accepté — 2026-10-03 |
| [0008](0008-pnpm.md) | pnpm comme gestionnaire de paquets Node | accepté — 2026-10-03 |
| [0009](0009-format-des-stories.md) | Fichiers de story en markdown, pas en YAML | accepté — 2026-10-03 |
| [0010](0010-override-driver-neo4j.md) | Forcer le driver `neo4j` par `override-dependencies` — un seul environnement | accepté — 2026-10-03 |
| [0011](0011-inventaire-driver-et-format-de-story.md) | Relevé réel de la surface `neo4j`, version résolue consignée, marqueur de format de story | accepté — 2026-10-03 |

## Règles

- **Un ADR = une décision.** Si deux décisions doivent être prises ensemble,
  c'est deux ADR.
- **Écrit après la décision**, pas avant — pour qu'il reste court et vrai.
- **Immuable une fois accepté.** Une décision qui ne tient plus ne se
  réécrit pas : elle se supersède.
- **Une décision sans alternative rejetée est incomplète** : on doit pouvoir
  lire pourquoi on n'a pas choisi l'autre chemin.