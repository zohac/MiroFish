# 0003 — L'ontologie dynamique est une v2 : le chemin de lecture d'abord

- **Statut** : accepté
- **Date** : 2026-10-03

## Contexte

`backend/app/services/ontology_generator.py` génère, **à l'exécution**, des
classes Python d'entités et de relations via le LLM : Zep reçoit une ontologie
sur mesure pour contraindre l'extraction. Graphiti attend l'équivalent sous
forme de classes Pydantic (`custom_entity_types`). C'était identifié comme **le
point dur** du projet — ~80 % de l'effort estimé.

L'audit du fork de référence (`docs/LOCAL-FIRST.md` §12.3) montre qu'ils ont
laissé `set_ontology()` en no-op… et que le graphe obtenu est vide. La cause
est dans **notre** code amont :

```
backend/app/services/zep_entity_reader.py:262
  custom_labels = [l for l in labels if l not in ["Entity", "Node"]]
  if not custom_labels:  →  nœud ignoré
```

Le lecteur ne retient que les nœuds portant un label d'ontologie **au-delà** de
`{Entity, Node}`. Or Graphiti, sans `custom_entity_types`, n'attribue que
`Entity` : **tout est filtré**, silencieusement. Ce n'est donc pas un bug de
leur fork, c'est un point de friction structurel entre Zep et Graphiti.

## Décision

**v1 sans ontologie custom.** On livre d'abord le chemin de lecture complet
(labels, `summary`, `fact`, `valid_at`/`invalid_at`/`expired_at`, isolation
par `group_id`), avec ses tests. L'ontologie dynamique devient une **v2**,
optionnelle.

## Conséquences

**Positives**

- Le chemin de lecture est **identique avec ou sans ontologie** : on ne le
  fait qu'une fois, et on valide la boucle complète beaucoup plus tôt.
- Le §6.1 de `docs/LOCAL-FIRST.md` est requalifié : ce n'est plus le gros de
  l'effort initial, c'est une extension.
- Le filtre de `zep_entity_reader.py` doit être rendu explicite : la question
  « qu'est-ce qu'une entité exploitable ici ? » devient un choix de l'interface
  du store, pas une hypothèse cachée dans un service.

**Négatives**

- En v1, les entités extraites portent les types génériques de Graphiti, pas
  les types métier générés. La configuration de simulation s'appuie sur les
  types d'entités : il faut vérifier qu'elle reste pertinente (à confirmer).
- La v2 demande plus : fabriquer des classes Pydantic à l'exécution, gérer la
  réindexation quand l'ontologie change, et invalider les données extraites
  avec l'ancienne ontologie. C'est un vrai sujet, à son heure.

## Alternatives rejetées

- **Ontologie en premier** — c'était le plan initial. On attaquerait le point
  le plus difficile avant d'avoir validé que la boucle fonctionne, sur un
  modèle dont la qualité d'extraction n'est pas encore mesurée.
- **Ontologie figée en dur dans le code** — contredit la génération à
  l'exécution, et figerait le domaine d'usage dans le dépôt.
- **Mapper quand même les entités génériques sur l'ontologie Zep** — mappings
  fragiles, sans bénéfice tant que la v2 n'est pas décidée.