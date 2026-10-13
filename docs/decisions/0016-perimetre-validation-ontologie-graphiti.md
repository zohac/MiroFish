# 0016 — Périmètre de validation ontologique limité à Graphiti

- **Statut** : accepté
- **Date** : 2026-10-12
- **Complète** : [ADR 0015](0015-controle-ontologie-avant-persistance.md), sans le réécrire
- **Concerne** : [story 007-2](../plans/007-ontologie-dynamique/story-007-2.md)

## Contexte

L’ADR 0015 a établi que Graphiti possède une frontière de contrôle avant
persistance démontrable, tandis que le SDK Zep `3.25.0` permet seulement de
sérialiser `strict_ontology`. Zep extrait à distance et ne fournit pas, dans le
contrat observé, les candidats rejetés ni un diagnostic par type avant
persistance.

Le local-first du projet fait de Graphiti le moteur de référence. Attendre une
garantie distante Zep bloque la validation locale alors que son mécanisme
applicatif est démontré sur Graphiti.

## Décision

La garantie de validation avant persistance de la story 007-2 est portée par
`GraphitiGraphStore`, avec les chemins `add_episode` et `add_text_batch` utilisés
par MiroFish. Le contrôle est effectué avant la délégation de sauvegarde, en
mode permissif par rétrogradation vers `Entity` avec journalisation, et en mode
strict par `GraphValidationError`.

`ZepGraphStore` conserve son parcours historique et la pose d’ontologie de
007-1. Il n’est pas présenté comme conforme à la garantie de validation de
007-2. Une écriture Zep demandant explicitement la garantie stricte est refusée
avec une erreur de capacité ; aucune suppression compensatoire ni interprétation
optimiste du filtrage serveur n’est autorisée.

La politique `Project.strict_ontology`, le journal durable et les endpoints de
007-2 sont implémentés pour le backend Graphiti. La préférence est persistée
dans tout projet afin de survivre au rechargement et d’être appliquée lors de
la prochaine construction Graphiti.

## Conséquences

- Le périmètre de C2 et des AC1–AC3 est explicitement Graphiti ; la mesure
  réelle utilise Neo4j local et les lots applicatifs du store.
- Les parcours Zep historiques restent disponibles sans annoncer la garantie
  C2. Leur validation ontologique complète devient un travail séparé soumis à
  une nouvelle preuve du contrat distant.
- Le PRD, l’architecture, l’epic et la story 007-2 sont alignés sur ce
  périmètre avant le démarrage de l’implémentation.
- L’ADR 0015 reste la preuve de la limite Zep et n’est pas modifié.
