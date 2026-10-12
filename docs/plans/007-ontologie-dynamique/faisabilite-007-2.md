# Faisabilité du contrôle avant persistance — 007-2

- **Date** : 12 octobre 2026
- **Décision** : [ADR 0015](../../decisions/0015-controle-ontologie-avant-persistance.md)
- **Verdict du DoR actuel** : **NO-GO**. Graphiti démontré ; C2 Zep non démontré.
- **Preuves** : [sonde rejouable](verifier-dor-007-2.py), [mesure JSON](mesure-dor-007-2.json).

## Versions et protocole

Exécution Docker contre le Neo4j local du compose : `graphiti-core==0.30.2`,
`zep-cloud==3.25.0`, driver `neo4j==5.28.6`, serveur déclaré
`neo4j:5.26.31-community`. Versions installées vérifiées à l’exécution ;
empreintes SHA-256 des sources effectivement exercées dans la mesure JSON.

```bash
docker compose run --rm \
  -v "$PWD/docs:/app/docs:ro" \
  backend uv run python /app/docs/plans/007-ontologie-dynamique/verifier-dor-007-2.py \
  > docs/plans/007-ontologie-dynamique/mesure-dor-007-2.json
```

Le LLM et l’embedder sont déterministes et locaux ; aucun appel LLM ni HTTP
Zep réel. Le pipeline Graphiti, le store applicatif et Neo4j sont réels.
Chaque cas utilise un `group_id` aléatoire `dor0072_*`, supprimé dans un
`finally`, puis vérifié vide. Aucun volume ni autre graphe n’est effacé.
Code retour 0 : l’étude et ses assertions passent ; cela n’inverse pas le
verdict NO-GO sur le contrat commun. Cette sonde est un prototype documentaire,
sans modification des services de production.

## Graphiti : deux contrôles nécessaires

La lecture des sources verrouillées et l’exécution établissent cet ordre :

1. `add_episode` extrait les types via le client LLM ;
2. `_create_entity_nodes` convertit l’identifiant en label ;
3. déduplication, résolution des relations et hydratation des attributs ;
4. `_process_episode_data` délègue la sauvegarde à `add_nodes_and_edges_bulk` ;
5. le résultat revient au store après persistance.

Un ID hors plage, par exemple **999**, est transformé en `Entity` en étape 2,
sans warning. Le contrôle final des labels ne peut plus distinguer cet ID du
choix générique **0**. Le cas témoin le démontre : un nœud générique persiste,
sans signal. Vérifier seulement `res.nodes` est trop tard.

Le mécanisme démontré combine donc :

- un contrôle de la réponse d’extraction `ExtractedEntities` avant cette
  conversion, qui conserve l’ID tenté et le schéma associé ;
- une sous-classe locale de `Graphiti` qui contrôle les nœuds hydratés dans
  `_process_episode_data` **avant** d’appeler `super()`. Le pipeline amont
  n’est pas recopié et aucun module installé n’est modifié.

La sonde fournit des réponses LLM adversariales. La faute finale est injectée
explicitement à l’entrée du contrôle : elle éprouve la frontière de sauvegarde,
sans prétendre qu’un LLM produit naturellement ce label à ce stade.

| Cas | Nœuds / épisodes / relations persistés | Résultat |
|---|---|---|
| Type déclaré | 1 / 1 / 1 | Sauvegarde et relecture réussies |
| ID 999, témoin sans contrôle brut | 1 / 1 / 1 | Repli générique silencieux confirmé |
| ID 999 strict | 0 / 0 / 0 | `GraphValidationError`, aucune délégation de sauvegarde |
| ID 0 strict | 0 / 0 / 0 | Même refus avant sauvegarde |
| ID 999 permissif | 1 / 1 / 1 | `Entity` et un signal enregistré par le prototype |
| Label inconnu final strict | 0 / 0 / 0 | Refus à la frontière de sauvegarde |
| Label inconnu final permissif | 1 / 1 / 1 | `Entity`, signal et suppression de l’attribut de type refusé |
| Lot valide puis ID 999 strict | 1 / 1 / 1 | Premier fragment conservé, second refusé avant sauvegarde |
| Même lot permissif | 2 / 2 / 2 | Deux fragments conservés, un signal |
| Lot avec faute finale strict | 0 / 0 / 0 | Premier fragment refusé, lot interrompu |
| Même lot permissif | 2 / 2 / 2 | Deux rétrogradations signalées |

Les relations de cette preuve sont les `MENTIONS` réelles créées par Graphiti.
La sonde ne génère pas de relations métier `RELATES_TO` : elle démontre le
point de contrôle, pas toute la qualification C2 de l’implémentation future.
Les warnings du prototype sont des signaux en mémoire ; leur journal durable
reste à implémenter en 007-2.

### Lots, sémantique et limites

`GraphitiGraphStore.add_text_batch` appelle séquentiellement `add_episode` :
les deux contrôles couvrent donc **le chemin batch applicatif**, réellement
exercé. Le lot n’est pas atomique : les fragments valides précédents restent
persistés si un fragment suivant est refusé.

Le `Graphiti.add_episode_bulk` natif est différent : il sauvegarde les épisodes
avant l’extraction et appelle directement la sauvegarde bulk, sans passer par
`_process_episode_data`. Il n’est pas utilisé par notre store et ne bénéficie
pas du mécanisme démontré. Le substituer au chemin actuel exigerait une nouvelle
preuve, pas une optimisation transparente.

Avec une ontologie de types d’entité effective, **0** est un choix hors types
métier : warning en permissif, refus en strict. Un ID hors plage conserve son
identifiant dans le diagnostic ; aucun nom de type n’est inventé. Un champ
`entity_type_id` absent ou non entier est une réponse structurée invalide,
distincte du choix générique : refus de validation, pas succès silencieux.
Sans ontologie de types d’entité, ces règles ne s’activent pas.

`_process_episode_data` est une méthode privée, disponible dans la version
verrouillée : l’implémentation devra garder un test de signature et de chemin.
Le prototype utilise une instance par cas. L’intégration future devra porter
un snapshot par requête, sans mutation de politique globale du client LLM,
et tester la concurrence. Les graphes hérités et la déduplication avec leurs
labels devront être qualifiés séparément ; aucune rétrogradation rétroactive
n’est autorisée par cette étude.

## Zep : transport possible, garantie C2 absente

Le transport HTTP de la sonde intercepte les requêtes du **vrai SDK 3.25.0** :

| Chemin | Capacité réellement constatée |
|---|---|
| `graph.add` | Paramètre typé `strict_ontology`, présent dans le JSON envoyé |
| `batch.create` | Aucun paramètre typé `strict_ontology` ; appel avec ce mot-clé refusé par Python |
| `batch.create` avec `request_options.additional_body_parameters` | `strict_ontology: true` effectivement présent dans le JSON envoyé |
| `Episode` et `BatchSummary` | Aucun champ déclaré de détail des entités rejetées ni de warning ontologique |

L’absence de paramètre batch typé **n’est donc pas** le blocage principal. Les
paramètres additionnels permettent sa sérialisation, mais ne prouvent pas son
traitement par un serveur distant.

La [documentation officielle actuelle de Zep](https://help.getzep.com/customizing-graph-structure)
décrit un mode permissif qui conserve les entités sans type spécifique et un
mode strict qui exclut de l’extraction les entités hors types configurés. Elle
décrit aussi son application aux lots. Ce filtrage ne promet pas un diagnostic
par entité ni une exception nommant chaque type refusé. La configuration des
types par défaut modifie aussi le schéma effectivement autorisé côté serveur.

Cette documentation est celle du service courant, pas une preuve versionnée
du serveur derrière SDK 3.25.0. Aucun appel cloud n’a été fait : ni le refus
ni la rétrogradation serveur ne sont qualifiés ici. Les modèles autorisent des
champs additionnels ; l’absence de champ déclaré ne prouve pas qu’un serveur
n’en retournera jamais. Elle ne fournit toutefois aucun contrat exploitable
garantissant les signaux C2.

L’application n’a pas accès aux candidats extraits avant persistance distante.
`get_nodes`, la fin d’un batch et une suppression compensatoire sont des
contrôles après écriture ; les candidats filtrés ne sont pas reconstructibles
à partir du graphe final. Transformer le filtrage silencieux en
`GraphValidationError` pour chaque type hors ontologie n’est donc **pas
démontré réalisable avec le contrat public inspecté**.

## Décision et effet sur la story

**L’étude demandée est terminée ; le DoR commun n’est pas satisfait.** La story
est `blocked` par la capacité distante non démontrée, avant implémentation.
C2 et AC1–AC3 sont conservés ; aucun affaiblissement du contrat n’est adopté.
L’ADR 0015 consigne ce NO-GO et les points démontrés.

Deux sorties sont identifiées, à arbitrer avant de reprendre :

1. restreindre explicitement C2 à Graphiti, avec refus préalable des écritures
   ontologiques Zep qui demandent cette garantie ; conserver le chemin Zep
   historique sans ontologie. Ce serait une modification de périmètre à
   reporter dans PRD, architecture et story ;
2. conserver C2 sur les deux moteurs et obtenir une API Zep de préparation /
   validation avant commit, ou concevoir une extraction applicative contrôlée
   et une ingestion structurée. C’est une nouvelle architecture, à éprouver.

Un appel cloud supplémentaire peut préciser le filtrage natif, mais un test
heureux ne crée pas le contrat de diagnostic par candidat qui manque.


## Contrôles de clôture de l’étude

- Sonde finale : code retour **0**, **11 cas Graphiti conformes** et assertions
  de sérialisation Zep conformes ; nettoyage de chaque graphe vérifié.
- `ruff check` sur la sonde sous Docker : `All checks passed!`.
- `validate_plans.py` sous Docker : structure valide, **9 epics, 37 stories**.
- `git diff --check` : propre.
- Aucune modification du code produit ; suite globale non rejouée pour cette
  étude. Sa dernière référence reste 1364 réussis et 3 ignorés sous Docker.
