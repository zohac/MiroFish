# Mesure réelle — Provenance documentaire (story 009-2, critère C3)

- **Date** : 2026-10-11T16:01:38.782908+00:00
- **Statut** : **SUCCES**
- **Environnement** : `GraphitiGraphStore` contre Neo4j local, hors pytest et CI.

## Critères de sortie

| Critère | Résultat |
|---|---|
| `C3_deux_documents_ingerees` | ✅ VALIDÉ |
| `C3_deux_fragments_par_document` | ✅ VALIDÉ |
| `C3_positions_exactes` | ✅ VALIDÉ |
| `C3_references_resolues` | ✅ VALIDÉ |
| `C3_origines_signalees` | ✅ VALIDÉ |
| `C3_isolation_par_graphe` | ✅ VALIDÉ |
| `C3_nettoyage_propre` | ✅ VALIDÉ |

## Décomptes du filet hermétique

- 1110 réussis sur l'hôte ; 1107 réussis + 3 ignorés sous Docker, sur le code courant de la story 009-2

> Les trois contrôles ignorés sous Docker nécessitent la CLI Docker.
> Aucune nouvelle exception n'est introduite par la story 009-2.

## Détails

- **Fragments par document** : `{'doc_73a9b40401fd': 2, 'doc_9a44b6503670': 2}`
- **Références totales** : `8`
- **Documentaires résolues** : `8`
- **Positions exactes** : `8`
- **Origines** : `{'document': 8}`
- **Références non résolues** : `[]`

## Documents ingérés

| Nom | Rôle | Priorité | Statut de validation |
|---|---|---|---|
| `alpha.txt` | `facts` | 1 | `unvalidated` |
| `beta.txt` | `hypotheses` | 1 | `unvalidated` |

## Empreintes des textes normalisés

- `alpha` : `53f4cf977ddd90676d64d4cbf67ae0ea6742944d054219874ac6958b6dbd902f`
- `beta` : `9958d0f8f434b48b9bc335752ef0d4f40782d9b0b117502b7c5251a4a10197ee`

## Portée

Cette sonde prouve le chemin **documentaire** de bout en bout contre un Neo4j
réel : résolution des références, positions exactes, isolation par graphe et
nettoyage. La classification des quatre origines (`document`, `simulation`,
`legacy`, `unresolved`) est prouvée par les tests hermétiques
(`tests/test_provenance_store_contract.py`), qui exercent les quatre cas sans
dépendance à Neo4j.

> Sortie sans secret : aucun identifiant, mot de passe ni clé n'est consigné.
