# 0011 — Inventaire réel du driver `neo4j`, version résolue, et format de story

- **Statut** : accepté
- **Date** : 2026-10-03
- **Précise** : [ADR 0010](0010-override-driver-neo4j.md) sur son inventaire d'API, et [ADR 0009](0009-format-des-stories.md) sur les titres de sections
- **Ne remplace pas** : l'override `neo4j` reste celui de l'ADR 0010

## Contexte

Deuxfaits sont acquis le 3 octobre 2026, tous deux vérifiés dans
`backend/.venv` et rejouables par
[`mesurer-001-1.sh`](../plans/001-epreuve-graphiti-local/mesurer-001-1.sh).

**L'inventaire d'API de l'ADR 0010 est faux.** Il fonde le seul argument donné
pour que l'override soit tenable :

> C'est vérifié au niveau de l'API (son usage du driver se limite à
> `GraphDatabase.driver()` et `neo4j.Version`).

Deux erreurs. `neo4j.Version` n'est référencé **nulle part** dans `camel/` ni
dans `oasis/` — l'API citée n'existe pas. Et la surface réellement atteinte est
plus large que celle retenue, en particulier sur ce qui bouge le plus entre
5.23 et 5.28 : les transactions gérées et la hiérarchie d'exceptions.

**La borne de l'override n'épingle rien.** `neo4j>=5.26.0,<6.0.0` se résout
sur la dernière 5.x disponible au jour du lock. L'ADR 0010 le reconnaît
lui-même (« plus large que nécessaire ») mais se déclare supersédé si la story
001-2 casse : **001-2 risquerait donc de ne pas tester la version déployée.**

**Le renommage des sections n'a rien laissé derrière lui.** Le passage des six
titres à l'anglais (`## Tasks`, `## Completion notes`) est un changement
cassent : tout fichier de story écrit avant cette décision produit six « section
obligatoire absente » sans qu'aucun message n'explique pourquoi. Le dépôt a
déjà changé de format une fois (YAML → markdown, ADR 0009), sans marqueur.

## Décision

**1. L'inventaire de l'ADR 0010 est remplacé par celui-ci.** La surface que
`camel-oasis` atteint à travers le driver, relevée telle quelle :

| Symbole | Fichiers | Où |
|---|---|---|
| `neo4j.GraphDatabase.driver` / `GraphDatabase.driver` | 2 | `camel/.../neo4j_graph.py:103`, `oasis/social_agent/agent_graph.py:28` |
| `from neo4j import Query` | 1 | `camel/.../neo4j_graph.py:229` |
| `neo4j.exceptions.{ServiceUnavailable, AuthError, ClientError, CypherSyntaxError}` | 1 | `neo4j_graph.py:115, 120, 128, 230, 254, 627, 696` |
| `neo4j.Version` | **0** | — |

`neo4j.Version` est retiré de l'inventaire : il n'a jamais été utilisé. La
surface se limite à la création de driver, aux sessions et transactions
gérées, à `Query`, et à la hiérarchie d'exceptions — cette dernière étant ce qui
a le plus de chances de bouger entre deux versions majeures du driver. **C'est
la story 001-2, avec un vrai Neo4j, qui tranche le comportement** ; l'ADR 0010
avait raison de le dire et tort de le dire sur cette base.

**2. La version résolue est consignée à côté de la borne.** L'override reste
une plage — l'épingler à l'exact imposerait de réévaluer chaque release du
driver — mais la version qu'il a résolue le 3 octobre 2026 est écrite dans l'ADR
et reprise dans toute implémentation :

```toml
[tool.uv]
override-dependencies = ["neo4j>=5.26.0,<6.0.0"]
# version effectivement résolue au lock du 2026-10-03 : neo4j 5.28.6
```

`docs/STATUS.md` et `story-001-1.md` reprennent **cette écriture exacte**. Une
implémentation qui recopie une forme différente de la borne n'implémente pas
cet ADR.

**3. Le format de story porte un marqueur de version.** Un fichier de story
declare `format: "2"` dans son en-tête. Un fichier au format 1 — titres anglais
— est refusé avec **un seul** message nommant le format attendu, la raison du
changement et le moyen de le corriger, au lieu de sept messages identiques qui ne
disent rien.

`validate_plans.py` contrôle désormais, en plus de ce qu'il contrôlait :

- la présence de `format` et sa valeur, avec sortie anticipée avant les sections ;
- la forme de l'`id` : `<epic>-<n>` suivi d'un suffixe alphabétique facultatif
  (`001-1b` est une story dérivée, `AGENTS.md` §2.8) ;
- la citation dans le hub par **frontières de mot**, plus par sous-chaîne —
  `001-1` est sous-chaîne de `001-1b`, et une story en revue dont la ligne a
  disparu du hub ne doit pas passer sur celle de sa voisine ;
- l'existence du fichier derrière une ligne de hub passée `in-progress` ou
  au-delà ;
- les cases à cocher des `Définition de prêt` et `Définition de fini`, au même
  titre que celles de `Tâches`, pour une story en `review` ou `done`.

**4. Ce qui n'est pas contrôlé est écrit.** Ni l'ADR 0010 ni ce document ne
promettent que `validate_plans.py` contrôle l'**ordre** des états. « Jamais de
saut » (`AGENTS.md` §2.8) reste une convention : un validateur qui lit des
fichiers n'a pas d'historique. Le dire vaut mieux que le laisser croire.

## Conséquences

**Positives**

- L'ADR 0010 repose sur un relevé au lieu d'une supposition, et la version que
  la story 001-2 teste est celle qui sera déployée.
- Le renommage de sections n'est plus un piège silencieux : le diagnostic dit
  pourquoi, et quoi faire.
- `AGENTS.md` §2.8 énumère des invariants que `validate_plans.py` applique
  vraiment ; il n'y a plus d'écart entre ce qui est promis et ce qui est vérifié.

**Négatives**

- Un fichier de story antérieur doit être repris : `format: "2"` et titres
  français. Aujourd'hui il n'y en a qu'un, déjà repris ; une branche antérieure
  en contient.
- La citation dans le hub devient une correspondance de token, pas une
  recherche libre : un hub qui cite `001-1` au milieu d'une prose sans
  délimiteur n'est plus accepté. C'est le prix du correctif sur `001-1b`.
- L'inventaire du point 1 est un relevé ponctuel, pas un contrat : une
  version plus récente de `camel-oasis` peut appeler une API de plus. Rien ne
  surveille ça — c'est la story 001-2, et derrière elle le réintégrage de
  l'amont (`AGENTS.md` §2.6).

## Références

- [`story-001-1.md`](../plans/001-epreuve-graphiti-local/story-001-1.md) — la mesure
- [`mesurer-001-1.sh`](../plans/001-epreuve-graphiti-local/mesurer-001-1.sh) et
  [`mesure-001-1.txt`](../plans/001-epreuve-graphiti-local/mesure-001-1.txt) — la sortie capturée
- [ADR 0009](0009-format-des-stories.md) — les story files sont du markdown
- [ADR 0010](0010-override-driver-neo4j.md) — la décision que cet ADR précise
