# 0012 — Contrat de provenance commun aux deux stores `GraphStore`

- **Statut** : accepté
- **Date** : 2026-10-11
- **Précise** : [ADR 0001](0001-remplacement-de-zep-par-graphiti.md) sur l'interface à deux implémentations
- **Préalable à** : [story 009-2](../plans/009-eligibilite-acteurs-et-sources/story-009-2.md)
- **Traite** : R03, R05, R08 de la [revue de reprise](../plans/009-eligibilite-acteurs-et-sources/revue-coherence-2026-10-10.md), A05 de la [matrice de couverture](../plans/009-eligibilite-acteurs-et-sources/couverture-rapport-audit.md)

## Contexte

Deux faits mesurés dans le code, tous deux vérifiables sur la branche
`local-first` au commit de ce 11 octobre 2026.

**`add_text_batch` ne connaît que des chaînes.** Le contrat est
`add_text_batch(graph_id, chunks: List[str], batch_size, progress_callback)`.
Un fragment ingéré ne porte donc aucune information sur le fichier d'où il
vient : `GraphitiGraphStore.add_text_batch` écrit `source_description=f"chunk_{idx}"`,
où `idx` est un rang dans la concaténation. Un fragment qui chevauche deux
fichiers n'est attribuable à aucun. C'est le constat R03.

**Graphiti valide des métadonnées puis les jette.** `add_episode` vérifie que
`metadata` est un dictionnaire, ne le transmet pas, et retourne un `EpisodeRecord`
dont l'UUID peut être un `uuid4()` fabriqué sur place si la réponse de Graphiti
n'en porte pas. `EpisodicNode` possède pourtant un champ `episode_metadata`, et
la requête de sauvegarde Neo4j de `graphiti-core 0.30.2` ne l'écrit pas — l'annotation
doit donc être posée par le store, en Cypher, sur l'UUID réellement persisté. C'est
le constat R05.

**Le contrat n'offre aucune lecture d'épisode.** `EpisodeRecord` porte `uuid`,
`graph_id`, `processed`, `created_at` — ni contenu, ni source. La requête de
citation proposée par l'[architecture](../plans/009-eligibilite-acteurs-et-sources/architecture.md)
§4 liait `r` sans le rattacher au graphe cible. C'est le constat R08.

Trois contraintes non négociables dans le cadre :

- **NFR-2** : les appels existants restent valides. `chunks: List[str]` doit
  continuer de fonctionner partout, y compris chez `zep_graph_memory_updater` et
  les scripts de simulation.
- **`AGENTS.md` §2.1** : une interface exige au moins deux implémentations
  réelles. L'extension est donc écrite dans **les deux** stores, testée dans les
  deux, et le Cypher reste dans le store comme aujourd'hui.
- **C3 est borné** aux nouvelles ingestions documentaires. Les graphes migrés
  par l'epic 006 n'ont pas d'épisode source, et l'activité simulée en a de
  Simulation. Aucun rétro-remplissage n'est permis.

## Décision

**On étend `GraphStore` par un paramètre facultatif de métadonnées alignées et
une méthode de lecture de provenance, sans casser un seul appel existant, et on
persiste réellement les métadonnées dans les deux stores.**

### 1. Écriture : `chunk_metadata` aligné

```python
def add_text_batch(
    self,
    graph_id: str,
    chunks: List[str],
    batch_size: int = 350,
    progress_callback: Optional[Callable[[str, int, int], None]] = None,
    chunk_metadata: Optional[List[Dict[str, Any]]] = None,
) -> BatchSubmissionRecord:
```

`chunk_metadata` est **après** `progress_callback` : les quatre premiers
paramètres gardent leur position, donc aucun appelant n'est cassé et aucun
paramètre ne devient positionnel par accident. `None` signifie « aucune
provenance demandée » et produit exactement le comportement d'aujourd'hui.

Quand il est fourni, c'est une liste **de même longueur que `chunks`**, dans le
même ordre, une entrée par fragment. La validation est **faite une fois, dans
`base.py`**, avant toute écriture — c'est la seule façon que les deux stores
refusent la même entrée pour la même raison :

| Champ | Type | Requis | Contrainte |
|---|---|---|---|
| `source_document_id` | `str` | oui | non vide |
| `source_filename` | `str` | oui | non vide |
| `chunk_index` | `int` | oui | ≥ 0, base 0 **local au document** |
| `char_start` | `int` | oui | ≥ 0 |
| `char_end` | `int` | oui | > `char_start` |
| `source_role` | `str` | oui | valeur de `DocumentRole` |
| `page` | `int` | non | jamais déduit d'un index |
| `section` | `str` | non | jamais déduit d'un index |

Un désalignement, un champ manquant, un type invalide ou une entrée non
dictionnaire lève `GraphValidationError` **avant** la première écriture. Il
n'existe aucun chemin produisant une ingestion partielle déclarée réussie.

**Identité d'opération.** Quand `chunk_metadata` est fourni, il entre dans le
`sha256` qui produit l'`operation_id`, à côté du texte. Deux textes identiques
issus de deux documents différents ont donc deux opérations différentes, ce qui
est la seule façon de réconcilier un lot Zep sans confusion. Quand il est absent,
le hachage est **inchangé** : un lot Zep déjà persisté et repris après
redémarrage reste reconnaissable.

### 2. Persistance : l'UUID réellement écrit, et une annotation vérifiée

`GraphitiGraphStore.add_episode` cesse de fabriquer un UUID :

1. il appelle `graphiti.add_episode(...)` et **lit l'UUID du résultat** ;
2. si le résultat n'en porte pas, il lève `GraphStoreError` — plus de repli
   silencieux sur `uuid4().hex`, qui aurait produit un UUID qui n'existe nulle
   part dans Neo4j ;
3. si `metadata` est fourni, il exécute ensuite un `SET` Cypher sur
   `(:Episodic {uuid, group_id})` et **vérifie qu'une ligne a été touchée** ;
   zéro ligne → `GraphStoreError`.

L'annotation est donc une opération dont l'échec est visible : une erreur de
métadonnées ne peut jamais produire un succès d'ingestion. `ZepGraphStore` n'a
rien à corriger de ce côté — `graph.add(metadata=...)` et `BatchAddItem.metadata`
portent déjà les valeurs ; l'extension consiste à y verser les champs de
provenance **et** à les exposer dans `source_description` de façon lisible.

### 3. Lecture : `get_edge_provenance`

```python
def get_edge_provenance(self, graph_id: str, edge_uuid: str) -> List[ProvenanceRecord]:
```

`ProvenanceRecord` est un DTO neutre, gelé, défini dans `base.py` :

| Champ | Sens |
|---|---|
| `episode_uuid` | la référence telle qu'écrite dans `r.episodes` |
| `resolved` | `False` si la référence ne pointe vers aucun épisode **de ce graphe** |
| `origin` | `document` · `simulation` · `legacy` · `unresolved` |
| `source_document_id`, `source_filename`, `source_role` | origine documentaire |
| `chunk_index`, `char_start`, `char_end` | position dans le texte normalisé du document |
| `page`, `section` | **seulement si l'extracteur les a fournis** |
| `content` | texte réellement ingéré |
| `simulation_id`, `platform` | origine simulée |
| `missing_reason` | exigence non satisfaite, quand `resolved` est `False` |

La méthode est **abstraite** : chaque store déclare son comportement. Une
référence non résolue n'est pas une exception — c'est un enregistrement avec
`resolved=False`, parce qu'une arête migrée est un fait normal, pas une panne.

Les quatre origines sont distinctes et jamais fusionnées :

| Origine | Condition de classement | Compté comme fait documentaire (C3) |
|---|---|---|
| `document` | épisode résolu portant `source_document_id` | oui |
| `simulation` | épisode résolu portant `simulation_id` | **non** |
| `legacy` | épisode résolu sans aucune métadonnée de provenance | non, signalé |
| `unresolved` | référence présente, épisode absent du graphe | non, signalé |

### 4. Isolation

Toute requête de lecture est bornée par `graph_id`. Côté Graphiti, la requête
part de l'arête **dans le graphe cible** et résout les épisodes par
`OPTIONAL MATCH`, de sorte qu'une référence non résolue reste visible au lieu de
disparaître. Côté Zep, la lecture de l'arête passe par
`graph.edge.get_by_graph_id(graph_id, filters=SearchFilters(edge_uuids=[...]))` :
l'API Zep n'offre pas de « get edge by uuid **dans** un graphe », et appeler
`graph.edge.get(uuid)` à l'aveugle ferait fuiter une arête d'un autre graphe.

### 5. Ce que « référence résolue » veut dire pour C3

Une référence est **résolue** si et seulement si les quatre conditions sont
simultanément vraies :

1. l'UUID figure dans `r.episodes` de l'arête ;
2. un nœud `:Episodic` portant cet UUID existe **avec `group_id = graph_id`** ;
3. ce nœud porte `source_document_id`, `source_filename`, `chunk_index`,
   `char_start`, `char_end` et `source_role` ;
4. `document_text[char_start:char_end] == content`, où `document_text` est le
   texte normalisé du document.

La condition 4 est vérifiable seulement si le texte normalisé est conservé : le
projet le persiste par document, ce qui est aussi ce qui permet de rejouer la
vérification plus tard. Un graphe migré de l'epic 006 ne satisfait aucune de ces
conditions ; ses références sont `legacy` ou `unresolved`, jamais réécrites.

## Conséquences

**Positives**

- Un fait du graphe devient rattachable à un fichier, un index et une plage de
  caractères, et cette attribution est vérifiable par une sonde réelle.
- `add_episode` ne peut plus rapporter un UUID qui n'existe pas : c'est une
  garantie, pas une convenance.
- Les appels existants — 14 méthodes du contrat, les scripts de simulation,
  l'updater d'activité simulée — sont intacts et le filet `GraphStore` reste
  vert.

**Négatives**

- `get_edge_provenance` est abstraite : les quatorze doublures de test qui
  héritent de `GraphStore` doivent l'implémenter, y compris celles qui ne servent
  qu'à un autre usage. Une doublure qui n'implémente pas cette méthode devient
  une erreur d'instanciation — c'est voulu, mais c'est du travail, et il est fait
  dans la même story.
- L'annotation Graphiti coûte une requête Cypher supplémentaire par épisode.
  Sur une ingestion de plusieurs centaines de fragments, c'est le poste de coût
  nouveau de cette story ; il est assumé, pas-optimisé.
- Zep n'ayant pas de lecture d'épisode par graphe, l'implémentation Zep fait une
  requête d'arête filtrée par graphe puis une lecture d'épisode par référence.
  C'est correct et plus lent que Graphiti.
- `page` et `section` restent `None` pour la quasi-totalité des extractions
  actuelles : `FileParser` ne produit pas de pagination. C'est honnête, et ce
  n'est pas corrigé par cette story.

## Alternatives rejetées

**Modifier `chunks` en `List[Chunk]` ou en tuples `(texte, métadonnées)`.**
Rupture de signature pour tous les appelants, y compris le script de mesure de
l'epic 001 et les probes déjà écrites. NFR-2 l'interdit.

**Ajouter `metadata` en position 5 de `add_text_batch`.**
Aucun appelant actuel ne passe cinq arguments, mais un paramètre inserted avant
`progress_callback` deviendrait positionnel pour quiconque l'ajoute, et
`build_operation_id` compare des hachages : le jour où une implémentation et un
test divergent d'un cran, le symptôme est un UUID d'épisode faux, pas une erreur
de signature.

**Écrire la provenance dans le `fact` de l'arête ou dans le `summary` du nœud.**
Le texte généré est le domaine du LLM ; yloguer de la structure le rend
inexploitable et le corrompt au premier réécriture. La provenance est une donnée
du store, pas du texte.

**Faire échouer `get_edge_provenance` sur une référence non résolue.**
Un graphe migré de l'epic 006 est un cas normal d'usage. Une exception
transformerait « cette arête vient d'une époque antérieure » en panne, et
l'appelant n'aurait aucun moyen de distinguer les deux.

**Laisser `add_episode` fabriquer un `uuid4()` quand Graphiti n'en renvoie pas.**
C'est le comportement actuel (R05). Il produit un `EpisodeRecord` qui prétend
avoir ingéré un épisode et renvoie une référence que rien ne résoudra jamais.

## Références

- [`story-009-2.md`](../plans/009-eligibilite-acteurs-et-sources/story-009-2.md) — la story qui implémente cet ADR
- [`architecture.md`](../plans/009-eligibilite-acteurs-et-sources/architecture.md) §4 — traçabilité Neo4j
- [revue de reprise](../plans/009-eligibilite-acteurs-et-sources/revue-coherence-2026-10-10.md) — R03, R05, R08
- [ADR 0001](0001-remplacement-de-zep-par-graphiti.md) — l'interface à deux implémentations
- `graphiti-core 0.30.2`, `EpisodicNode.episode_metadata` et `get_episode_node_save_query` — la preuve que l'annotation doit être posée par le store