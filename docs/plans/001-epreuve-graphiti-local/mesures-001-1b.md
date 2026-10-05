# Preuves de rejouabilité — story 001-1b (4 octobre 2026)

Ces deux fichiers sont les sorties brutes du protocole
[`mesurer-001-1.sh`](mesurer-001-1.sh), lancées sur les **deux** arbres entre
lesquels la story fait la transition. Ils sont la preuve versionnée de ce que la
story affirme dans ses notes de complétion.

`mesure-001-1.txt` n'est **pas** remplacé : c'est la sortie du 3 octobre 2026,
sur un arbre sans override, la preuve historique du conflit. Ses `192 passed`
sont ceux de ce jour-là, et le dire est plus utile que de le rafraîchir.

| Fichier | Arbre de départ | État annoncé | Filet de tests sur l'arbre **mesuré** |
|---|---|---|---|
| [`mesure-001-1b-avant-override.txt`](mesure-001-1b-avant-override.txt) | `uv.lock` au sha `1b41b865…`, `neo4j 5.23.0`, pas de `graphiti_core` | `AVANT la 001-1b` | **204 passed** |
| [`mesure-001-1b-apres-override.txt`](mesure-001-1b-apres-override.txt) | `neo4j 5.28.6`, `graphiti_core` présent | `APRÈS la 001-1b` | **234 passed** |

## Pourquoi deux sorties, et pas une

Le protocole ne suppose plus l'état de l'arbre : il **normalise**
`backend/pyproject.toml` dans l'état qu'il veut mesurer, mesure, puis restaure
l'octet initial. C'est ce qui le rend rejouable sur les deux arbres — poser
l'override rendait la version précédente inutilisable, parce qu'elle exigeait
`graphiti-core` absent et ajoutait une seconde table `[tool.uv]` que TOML refuse.

Les deux fichiers ont la **même mécanique** et le même couple de versions
mesuré. Ce qui diffère, c'est l'état de départ et le compte de tests — et
l'écart est instructif : sur l'arbre d'avant le geste, les 30 tests ajoutés par
la story 001-1b ne sont pas encore satisfaits, parce qu'ils lisent le dépôt réel
et y attendent la declaration posée. C'est le comportement correct d'un garde-fou,
et c'est la preuve qu'ils ne passent pas par hasard.

## Ce que chaque sortie prouve

Les deux, à chaque fois :

- le **refus du résolveur** est reproduit à l'étape 1 — le conflit est réel,
  il n'est pas hérité d'un lock fabriqué ;
- l'override de l'ADR 0010 résout à l'étape 2, et la version résolue est
  consignée **à côté** de la borne dans l'arbre mesuré ;
- `oasis`, `neo4j 5.28.6`, `graphiti_core` s'importent dans cet ordre ;
- la **restauration est complète** : mêmes sha pour `pyproject.toml` et
  `uv.lock`, et le venv au même couple de versions qu'au départ.

La sortie « après » porte en plus `neo4j 5.28.6` à l'étape 3, lisible dans les
`METADATA` installés aux côtés des exigences de `camel-oasis` (`==5.23.0`) et de
`camel-ai` (`>=5.18.0,<6`) : les trois exigences, et celle qui gagne.

## Ce que ces fichiers ne prouvent pas

Rien à l'exécution. Aucune connexion n'a été ouverte sous cet override. C'est la
story 001-2, et c'est elle qui tranche l'ADR 0010 — par supersession s'il casse.