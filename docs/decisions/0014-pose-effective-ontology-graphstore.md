# 0014 — Pose effective de l'ontologie par `GraphStore.set_ontology`

- **Statut** : accepté
- **Date** : 2026-10-12
- **Complète** : [ADR 0003](0003-ontologie-differee-en-v2.md), qui différait l'ontologie dynamique en v2 et posait le no-op comme attitude v1 assumée
- **Préalable à** : [story 007-1](../plans/007-ontologie-dynamique/story-007-1.md)
- **Traite** : FR-1 et NFR-2 de l'[epic 007](../plans/007-ontologie-dynamique/epic-007.md), H2 et R1 du [PRD](../plans/007-ontologie-dynamique/prd.md) §5

## Contexte

`OntologyGenerator` (`backend/app/services/ontology_generator.py`) produit depuis
l'Epic 001 un dictionnaire d'ontologie de dix types d'entité et de relations,
appel LLM oblige. Ce dictionnaire est remis à `GraphBuilderService`, qui le passe
à `GraphStore.set_ontology(graph_id, ontology)`.

Ce qui se passait ensuite dépendait de l'implémentation, et **les deux
implémentations ne faisaient rien de visible** :

- `GraphitiGraphStore.set_ontology` validait son entrée, journalisait en `debug`
  et sortait. Le commentaire portait : « no-op en v1 conformément à l'ADR 0003 ».
- `ZepGraphStore.set_ontology` construisait bien des classes Pydantic, mais
  seulement si `entity_types` ou `edge_types` était non vide, et aucun test
  d'intégration ne l'exerçait.

Mesuré dans le graphe réel (Epic 003-5, Epic 004-3, Epic 005-4) : **tous** les
nœuds portent `:Entity`. `EntityNode.get_entity_type()` ne peut donc pas
atteindre sa première branche (label non `Entity`), et retombe sur la cascade
d'attributs, puis sur la chaîne littérale `"Entity"`. Les types métier produits à
coût LLM — `PersonEntity`, `MediaOrganization`, `RegulatoryDecision` — sont
perdus au moment précis où ils sont calculés.

L'ADR 0003 avait rendu ce no-op **assumé** : l'ontologie dynamique était une v2,
le chemin de lecture d'abord. L'Epic 009 a clos le verrou d'éligibilité des
acteurs et aiguisé le besoin : `ActorClassifierService` qualifie chaque entité
sans dépendre du label Graphiti, donc la qualification est refaite par LLM alors
que le type est déjà connu.

Trois faits mesurés contraignent la décision :

- `Graphiti.add_episode` accepte `entity_types: dict[str, type[BaseModel]]` et
  `edge_types: dict[str, type[BaseModel]]` — un **dictionnaire**, pas une liste.
  `node_operations.py` en dérive le label du nœud par
  `labels = list({'Entity', str(entity_type_name)})` : la clé du dictionnaire
  **est** le label Cypher.
- `graphiti_core.validate_entity_types` refuse une classe dont un champ entre en
  collision avec `EntityNode.model_fields` (`attributes`, `created_at`,
  `group_id`, `labels`, `name`, `name_embedding`, `summary`, `uuid`). Le nom de
  classe devient aussi un label Cypher : un nom non identifiant produit une
  erreur de syntaxe **en aval**, loin de la cause.
- Zep Cloud applique l'ontologie **côté serveur**, via
  `client.graph.set_ontology(graph_ids=[...])`. Il n'existe pas de paramètre
  d'ontologie par épisode : la seule façon d'en consommer une à l'écriture est
  de l'appliquer au graphe avant d'ajouter l'épisode.

## Décision

**On rompt le no-op : l'ontologie est une propriété du graphe, posée par
`set_ontology` et consommée par les écritures suivantes. Les deux stores
l'acceptent, et les signatures sont étendues sans casser aucun appel existant.**

### 1. `set_ontology` devient effectif, et versionné

```python
def set_ontology(
    self,
    graph_id: str,
    ontology: Dict[str, Any],
    *,
    strict: bool = False,
) -> None: ...
```

L'appel positionnel historique `set_ontology(graph_id, ontology)` reste valable :
`strict` est **keyword-only** et vaut `False` par défaut. La validation est
inchangée pour ce qui existait déjà (`graph_id` non vide, `ontology` dictionnaire)
et s'y ajoute un refus explicite de toute ontologie inexploitable, levé **avant**
toute mutation d'état.

`GraphStore` porte désormais un attribut de classe :

```python
class GraphStore(ABC):
    version: int = 2
```

`version = 1` désigne l'historique : `set_ontology` no-op, `add_episode` sans
paramètre d'ontologie. Un appelant qui a besoin de la pose effective — la sonde
C1, la régénération de la 007-4 — lit `store.version >= 2` au lieu de supposer.

`version` est **déclaré, pas imposé**. Un `__init_subclass__` qui refuserait une
sous-classe non versionnée casserait une quinzaine de doublures de test qui
héritent de `GraphStore` sans redéclarer l'attribut : le filet de régression des
epics 002 à 009 tomberait pour un gain nul. Une version se **lit** ; elle ne
s'**impose** pas à une classe qui ne consomme pas la fonctionnalité.

### 2. L'ontologie appliquée est mémorisée par `graph_id`

Chaque store concret conserve, pour la durée de vie de l'instance, l'ontologie
appliquée par `graph_id` : pour `GraphitiGraphStore`, le dictionnaire
`{nom: classe Pydantic}` traduit ; pour `ZepGraphStore`, le dictionnaire brut
déjà transmis à Zep.

`add_episode` résout alors, dans cet ordre :

1. l'ontologie passée explicitement (`ontology=...`) ;
2. l'ontologie mémorisée pour ce `graph_id` ;
3. rien — comportement historique, label `:Entity` seul.

C'est **une seule** mécanique pour les deux stores, et elle couvre `add_text_batch`
sans ajouter de paramètre : `add_text_batch` délègue à `add_episode`.

### 3. `add_episode` accepte une ontologie facultative

```python
def add_episode(
    self,
    graph_id: str,
    text: str,
    source_description: str = "",
    metadata: Optional[Dict[str, Any]] = None,
    created_at: Optional[str] = None,
    *,
    ontology: Optional[Dict[str, Any]] = None,
) -> EpisodeRecord: ...
```

Keyword-only, `None` par défaut. **Sans ontologie, l'appel construit exactement
la même requête qu'avant** : les clés `entity_types` et `edge_types` ne sont pas
ajoutées à l'appel Graphiti. C'est ce qui rend la rétrocompatibilité Epic 003-2
vérifiable plutôt que déclarative.

### 4. La traduction Pydantic est validée en deux temps

`OntologyToPydantic.from_dict` refuse une ontologie en deux temps, et **dans cet
ordre** :

1. **schéma** — chaque type a un nom identifiant (`^[A-Za-z_][A-Za-z0-9_]*$`,
   parce que ce nom devient un label Cypher), au plus
   `MAX_ONTOLOGY_TYPES` types, chaque attribut porte un nom identifiant et un type
   soit primitif (`str`, `int`, `float`, `bool`, `List[str]`, et leurs alias
   textuels), soit une **référence** à un `entity_type` déclaré ;
2. **constructibilité** — un stub de chaque classe est instancié, et l'éventuelle
   `pydantic.ValidationError` est convertie en refus.

Un attribut dont le nom entre en collision avec un champ de `EntityNode` est
**renommé** avec le préfixe `entity_`, pas refusé : c'est le comportement que
`ZepGraphStore` applique déjà, et refuser tuerait une construction de graphe
entière pour un nom d'attribut résiduel. Une **référence circulaire** entre types
d'entité est refusée : elle n'a aucun sens aplati et signale une ontologie
incohérente.

Un cycle de références est détecté par un parcours en profondeur de graphe
orienté ; le refus nomme le cycle.

### 5. Ce que la décision ne règle pas

`strict` est **accepté et mémorisé, jamais appliqué par `set_ontology`**. Le refus
d'un nœud dont le type n'est pas dans l'ontologie est l'objet de la story 007-2 :
il suppose un modèle de `GraphValidationWarning`, une politique sérialisable dans
`Project` et une méthode `get_ontology_warnings`. Un paramètre promis et non
appliqué serait un mensonge de contrat ; il est donc déclaré ici, testé comme
défaut, et branché en 007-2.

## Conséquences

**Positives**

- Les nœuds ingested portent le label déclaré. `EntityNode.get_entity_type()`
  atteint sa première branche sans être modifié (Epic 003-4 reste valable), et
  `ActorClassifierService` (009-1) reçoit un signal primaire sans être touché.
- Le partitionnement par `group_id` est orthogonal : `set_ontology` n'écrit rien
  dans Neo4j et ne touche pas au `group_id`. Le critère C2 de l'Epic 003 et le
  C5 de l'Epic 009 tiennent sans un test de plus.
- Un graphe migré depuis Zep (Epic 006) reste sur `:Entity` : il n'a jamais eu
  d'ontologie appliquée, donc aucune règle ne le rétrograde.

**Négatives, assumées**

- L'ontologie mémorisée est **par instance de store**. `get_graph_store()`
  construisant une instance par résolution, une ingestion doit partager son store
  avec le `set_ontology` qui la précède. `GraphBuilderService` le garantit par
  construction (un seul `self.store` pour les deux appels), et l'invariant est
  écrit ici pour être vérifiable, pas pour être découvert.
- `set_ontology` devient un point de refus : une ontologie mal formée échoue le
  build au lieu d'être ignorée. C'est le but, mais cela déplace un échec du
  moment de l'extraction vers le moment de la pose.
- La version `2` est déclarée sans outillage de migration : une implémentation
  tierce de `GraphStore` reste acceptée. Le garde-fou est la lecture de
  `version`, pas l'interdiction.

## Alternatives rejetées

**Garder le no-op et ajouter un second store typé.** Rejeté : deux chemins
d'écriture pour le même graphe, donc deux réponses au même problème et le retour
exact du défaut que cette décision supprime — le typage présent mais non
appliqué.

**Traduire en Pydantic à chaque ingestion.** Rejeté : la traduction serait
rejouée par fragment, donc par unité de travail, et une ontologie invalide
échouerait au milieu d'un lot après des écritures réussies. Traduire une fois, à
la pose, est déterministe et échoue avant la première écriture.

**Rendre `ontology` positionnel sur `add_episode`.** Rejeté : un paramètre
positionnel s'insère dans l'existant et le rend ambigu ; `created_at` et
`ontology` se confondraient pour tout appelant positionnel. Keyword-only rend
l'ajout impossible à rater.

**Exiger `version` dans `__init_subclass__`.** Rejeté : quinze doublures de test
héritant de `GraphStore` cesseraient d'être instanciables, pour une protection
contre une sous-classe qui, en pratique, n'est jamais instanciée en production.

**Refuser les attributs dont le nom entre en collision avec `EntityNode`.**
Rejeté : le préfixage `entity_` existe déjà côté Zep, le refuser côté Graphiti
donnerait deux comportements pour un même dict d'ontologie, et un nom
d'attribut résiduel ne doit pas faire échouer tout un graphe.