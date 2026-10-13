# Qualification 007-2 — validation ontologique livrée

Mesure du 12 octobre 2026 : **12 cas conformes, GO C2 Graphiti**.
La sortie machine est [mesure-007-2.json](mesure-007-2.json).

## Protocole rejouable

Depuis la racine du dépôt, avec Neo4j sain et l’image backend construite :

```bash
docker compose build backend
docker compose run --rm --no-deps backend uv run python scripts/verifier_ontology_validation.py > /tmp/mesure-007-2.json
```

La sonde emploie `GraphitiGraphStore` et `_OntologyValidatingGraphiti` livrés.
Neo4j, ses transactions, les épisodes et les relations `MENTIONS` sont réels.
Seuls le LLM et les vecteurs sont déterministes. Les candidats fautifs de la
frontière finale sont injectés avant son validateur, jamais après celui-ci.
Les empreintes SHA-256 du store et de la sonde figurent dans la sortie.

Pour mesurer le dépôt avant reconstruction de l’image, monter explicitement
`backend/app` et `backend/scripts` aux emplacements `/app/backend/app` et
`/app/backend/scripts`, en lecture seule. Ce mode a servi à la présente mesure,
avec les dépendances verrouillées de l’image Docker de référence.

## Cas et observations

| Cas | Observation requise |
|---|---|
| Type déclaré | Label `Person` conservé, aucun warning |
| ID 999 strict | Refus avant persistance, aucun épisode ni nœud |
| ID 0 strict | Même refus du type générique hors ontologie |
| ID 999 permissif | Nœud `Entity`, warning durable |
| Label final inconnu strict | Refus avant sauvegarde |
| Labels déclaré et inconnu permissifs | Seulement `Entity` persisté |
| Deux labels métier stricts | Contradiction refusée |
| Deux labels métier permissifs | Rétrogradation complète vers `Entity` |
| Attribut de type sur candidat générique | Attribut retiré, diagnostics conservés |
| Lot mixte strict | Épisode valide conservé ; épisode invalide refusé |
| Lot mixte permissif | Deux épisodes, candidat invalide rétrogradé |
| Nœud existant avec labels antérieurs | Relecture Neo4j : seulement `Entity` |

Chaque cas relit aussi la politique et le journal depuis une nouvelle instance.
Les graphes temporaires portent le préfixe `qualification0072_` et un UUID.
Ils sont supprimés dans un `finally`, puis leur absence est vérifiée. La sonde
ne détruit aucun volume et ne supprime aucun graphe extérieur à ses cas.

## Limites

Cette preuve valide le comportement du pipeline face aux candidats imposés ;
elle ne mesure pas la qualité d’extraction d’un LLM distant. Aucune relation
métier n’est générée par la doublure. Le refus strict précède néanmoins toute
délégation de sauvegarde de l’épisode concerné. La garantie stricte Zep demeure
non démontrée et ses écritures strictes sont refusées conformément à l’ADR 0016.
Un lot strict peut conserver ses épisodes valides déjà écrits : la garantie
porte sur l’absence de persistance du candidat invalide, pas sur une transaction
globale du lot.
