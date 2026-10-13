# 0017 — Politique ontologique durable et rétrogradation transactionnelle

- **Statut** : accepté
- **Date** : 2026-10-12
- **Complète** : [ADR 0014](0014-pose-effective-ontology-graphstore.md) et [ADR 0016](0016-perimetre-validation-ontologie-graphiti.md)
- **Concerne** : story 007-2, correctifs de revue P1–P10

## Contexte

Les stores sont recréés entre les requêtes HTTP et les écritures de simulation.
Une politique conservée seulement en mémoire laisse donc un nouvel écrivain
sans contrôle. La sauvegarde Graphiti ajoute les labels aux nœuds existants :
modifier uniquement le candidat en mémoire ne retire pas leurs anciens labels.

## Décision

Chaque store publie l’ontologie effectivement appliquée et sa politique dans
`UPLOAD_FOLDER/applied-ontologies/<backend>/<sha256(graph_id)>.json`. Le fichier
est remplacé atomiquement sous verrou de fichier. Les écritures relisent cet
état ; un changement de politique ne modifie aucune donnée du graphe.
L’effacement accompagne une création ou suppression réussie ; une création
échouée préserve la politique antérieure. Le namespace sépare Zep et Graphiti.

Le PATCH de politique partage le verrou de projet du démarrage de construction.
Ce verrou est local au processus Flask, comme celui du parcours de construction
existant ; il ne constitue pas une exclusion entre plusieurs workers Flask.

Sur Graphiti, un candidat final invalide devient exclusivement `Entity` en mode
permissif et perd ses attributs `entity_type`, `type` et `category`. Lors de sa
réécriture, les labels Neo4j antérieurs sont retirés dans la même transaction
que la sauvegarde Graphiti. Le refus strict intervient avant cette transaction.
Un changement de politique seul ne déclenche aucune rétrogradation.

Les écritures Zep directes refusent aussi une politique stricte, conformément
à la limite de capacité de l’ADR 0016. Les ressources créées pour une requête
d’audit sont fermées ; un store injecté reste sous la responsabilité de son
propriétaire.

## Conséquences

Les instances neuves et les écrivains déjà ouverts appliquent la politique
durable à leurs prochaines écritures. Une requête déjà commencée conserve son
instantané de politique. Le stockage local partagé doit être conservé avec
les données applicatives ; il ne prétend pas découvrir une ontologie appliquée
hors MiroFish. La qualification réelle et les tests hermétiques exercent le
pipeline livré, y compris la réécriture d’un nœud déjà labellisé.
