# Consigne d'évaluation — revue aveugle de la campagne `benchmark-013-20261020-203040`

Ce document est la procédure à suivre pour faire la **revue aveugle** de la
campagne. Le banc l'a outillée mais ne l'a pas exécutée : un agent ne peut
pas être son propre juge aveugle.

> **Rappel de la règle du dépôt** (PRD source §8 et §12.5) : l'expérience doit
> publier séparément le score **brut** des composants existants — c'est fait,
> voir `rapport-qualification-epic-013.md` — **et** une revue manuelle, avant
> d'attribuer le résultat au LLM. Cette revue est donc **préalable à toute
> décision de changement de modèle**.

---

## 1. Ce que l'évaluateur reçoit

### Contrôle préalable — obligatoire

Une première tentative a échoué : les pièces de preuve jointes étaient celles
d'une **autre simulation** (`sim_ea4f3cfe1028`, 258 affirmations — l'exécution
R6, encore présente dans `backend/uploads/reports/report_77d96ea4c1c9/` et
dans `backend/tests/fixtures/qualification_epic_012/r6_bundle/`). L'évaluateur
l'a détecté, et ses notes des critères 1 et 5 sont devenues provisoires.

**Avant d'envoyer quoi que ce soit, vérifiez** que chaque pièce de preuve
jointe est la bonne. Le contrôle tient en une ligne :

```bash
cd /chemin/vers/le/dépôt
for f in A-report_claims.json B-report_claims.json; do
  python3 -c "import json,sys;d=json.load(open(sys.argv[1]));print(sys.argv[1], d.get('simulation_id'), d.get('total_claims'))" "$f"
done
```

La sortie attendue est **exactement** :

```
A-report_claims.json sim_80a54d7bbd7b 159
B-report_claims.json sim_80a54d7bbd7b 178
```

Un autre `simulation_id`, un autre nombre d'affirmations : **n'envoyez pas**,
reprenez la liste de fichiers ci-dessous. Le dossier `backend/uploads/reports/`
contient plus de trente rapports anciens : c'est la source d'erreur la plus
probable.

### Les deux rapports à juger

- `variante-A.md`
- `variante-B.md`

### Les preuves, si l'on veut juger l'exactitude factuelle

Les preuves **ne divulguent pas** l'identité technique des variantes (ni le
modèle, ni l'effort, ni le `report_id` de correspondance) : les transmettre ne
rompt donc pas l'aveuglement. Sans elles, le critère « exactitude factuelle
vérifiable » n'est pas **mesurable**,
seulement appréciable.

Pour chaque variante, trois fichiers suffisent. Les chemins complets, à
prendre **tels quels** :

| Variante | Fichier | Ce qu'il permet de vérifier |
|---|---|---|
| A | `backend/uploads/reports/report_108186c7524b/report_claims.json` | statut de chaque affirmation (`VERIFIED` / `UNSUPPORTED` / `CONTRADICTED`), `claim_id`, champ `limitations`, `evidence_refs` (vide = non rattaché à un événement) |
| A | `backend/uploads/reports/report_108186c7524b/quality_checks.json` | les 5 contrôles de publication et leur verdict |
| A | `backend/uploads/reports/report_108186c7524b/cohort_coverage.json` | les 18 membres, rôles, statuts de décision, comptes d'actions, membres silencieux |
| B | `backend/uploads/reports/report_ccf28321dcb8/report_claims.json` | idem |
| B | `backend/uploads/reports/report_ccf28321dcb8/quality_checks.json` | idem |
| B | `backend/uploads/reports/report_ccf28321dcb8/cohort_coverage.json` | idem |

À quoi s'ajoutent, communs aux deux variantes :
`backend/uploads/simulations/sim_80a54d7bbd7b/actors.json` (les personas) et
`backend/uploads/simulations/sim_80a54d7bbd7b/simulation_config.json` (le brief
et ses règles).

**Prudence de nommage** : les fichiers de preuve portent le même nom pour les
deux variantes. Renommez-les en les transmettant (`A-report_claims.json`,
`B-report_claims.json`, …) pour que l'évaluateur ne les confonde pas — et
appliquez le contrôle préalable ci-dessus **après** renommage.

### Ce que l'évaluateur ne doit **pas** recevoir

| Fichier | Pourquoi |
|---|---|
| `correspondance.json` | c'est **la clé** : variante ↔ profil, effort, `report_id` |
| `mesure-benchmark-013.json` | la charge utile porte la même clé, plus les écarts chiffrés entre les deux variantes |
| `rapport-qualification-epic-013.md` | il nomme les profils, et affiche déjà les écarts bruts |

Si l'un de ces trois fichiers est lu, l'aveuglement est rompu : il faut
recommencer avec un autre évaluateur.

## 2. La consigne à transmettre

Copiez-collez le bloc ci-dessous dans un **contexte neuf**, en joignant les
deux rapports (et, si vous le souhaitez, les preuves de la section 1).

```text
Tu es un évaluateur indépendant. Deux rapports t'ont été fournis :
« variante-A.md » et « variante-B.md ». Ils ont été produits sur le même jeu
de preuves figées par deux configurations d'un même modèle, et tu ne sais pas
laquelle correspond à laquelle. Tu ne peux pas et ne dois pas deviner.

Des fichiers de preuve accompagne éventuellement chaque rapport :
<variante>-report_claims.json (statut de chaque affirmation : VERIFIED,
UNSUPPORTED ou CONTRADICTED, avec son claim_id et ses limitations),
<variante>-quality_checks.json (contrôles de publication),
<variante>-cohort_coverage.json (membres de la cohorte, rôles, statuts de
décision, comptes d'actions, membres silencieux).

Remplis la grille suivante, sur l'échelle 0 à 5 (0 = absent, 5 = excellent),
et remplis la colonne « Commentaire » avec une justification factuelle
(appuyer sur des passages précis, ne pas généraliser) :

| # | Critère | Échelle | Note A | Note B | Commentaire |
|---|---|---|---|---|---|
| 1 | Exactitude factuelle vérifiable | 0 à 5 | | | |
| 2 | Couverture de la cohorte | 0 à 5 | | | |
| 3 | Explicitation des limites et des objections | 0 à 5 | | | |
| 4 | Lisibilité et structure du rapport | 0 à 5 | | | |
| 5 | Respect des contraintes de publication | 0 à 5 | | | |

Pour le critère 1, vérifie point par point :
- Chaque citation entre guillemets est-elle **verbatim** d'un événement
  observé, ou une reformulation présentée comme telle ?
- Chaque affirmation attribuée à un persona est-elle **soutenue** par une
  action observée de ce persona ? Un persona avec 0 action ne peut se voir
  attribuer ni parole, ni refus, ni décision.
- Le rapport affirme-t-il une adoption, une souscription ou un paiement que son
  propre tableau de cohorte contredit ?
- La section « Sources & Provenance » certifie-t-elle une traçabilité que le
  registre d'affirmations du même rapport nie ?
- Y a-t-il des chiffres, des dates, des durées ou des formulations qui
  n'apparaissent nulle part dans les preuves ?

Pour le critère 2 : le rapport mentionne-t-il les personas qui ont agi ? Omet-il
un persona très actif ? Mentionne-t-il un persona sans aucune action ?

Pour le critère 3 : la section « Objections non levées, contradictions et
limites » est-elle présente ? Contient-elle des objections **réelles** (vérifiables
dans les preuves) ou seulement des généralités ? Le rapport dit-il la limite la
plus grave qu'il constate sur lui-même ?

Pour le critère 5 : le respect des 72 h, des rôles réels et pilotes, de la
distinction Essentiel / Premium, de l'absence de promesse inventée, et de la
séparation des origines d'information.

Règles de lecture :
- Une affirmation d'action, de paiement ou d'adoption sans trace observable
  est une **erreur matérielle** : compte-la et signale-la, avec le claim_id.
- Un rapport qui dit « je n'ai pas pu établir » fait preuve d'honnêteté ; un
  rapport qui affirme sans preuve est une erreur.
- N'optimise pas le style, la longueur ou l'assurance du rapport.
- Si un critère te semble impossible à noter, dis-le au lieu de deviner.

Termine par :
1. la liste des erreurs matérielles de chaque variante, avec la citation du
   passage, le claim_id si elle existe, et la preuve qui la contredit (ou
   l'absence de preuve) ;
2. les points où l'un des rapports est manifestement plus faible que l'autre,
   sans en tirer de conclusion générale sur la configuration ;
3. ce que tu n'as pas pu vérifier.
```

## 2 bis. La grille de cette campagne a déjà été remplie

Une première version de la grille a été remplie (voir `grille-aveugle.md`),
puis confirmée par une **revue indépendante** (voir
`revue-aveugle-independante.md`). La campagne est donc **documentée** ; la
procédure ci-dessus reste la référence pour une **contre-évaluation** ou pour
un nouvel arrivant.

Rappel de la conclusion, pour ne pas la réinterpréter : les deux variantes
sont notées **2/5**, les erreurs matérielles majeures sont **communes**, et la
variante `high` n'apporte **aucune réduction claire** des erreurs pour ~13 % de
tokens de plus. **La configuration par défaut reste `medium`.**

## 3. Après la grille remplie

1. **Remplir** `grille-aveugle.md` (le fichier de ce dossier) avec les notes
   obtenues, et **le dater**.
2. **Ouvrir alors seulement** `correspondance.json` : il dit quelle variante
   est `medium` et laquelle est `high`.
3. **Interpréter** : maintenant seulement, on sait quelle note appartient à
   quelle configuration.

## 4. La décision — et ses limites

Le critère de décision du PRD source (§8) :

> Choisir `high` si la revue aveugle montre une **réduction claire des erreurs
> matérielles et des citations non fondées**, sans dépassement du budget ni
> baisse de couverture. Sinon conserver `medium` ou tester une alternative.

Trois garde-fous à ne pas oublier :

- **Le budget n'est pas le même.** La campagne de référence mesure : `high`
  consomme **~13 % de tokens de plus** et **~12 % de coût théorique de plus**
  que `medium` (0,9119 $ → 1,0251 $). Sur une passerelle locale facturée au
  coût nul, cela ne se voit pas ; ailleurs, c'est le poste principal.
- **Une seule génération par variante.** L'écart observé entre `medium` et
  `high` peut être dû à l'effort **ou** à la variabilité stochastique du
  modèle. Pour trancher, il faut `--repetitions > 1` : le banc l'expose, la
  campagne de référence ne l'a pas fait.
- **La couverture n'est pas comparable.** Côté `medium`, le taux de
  vérification des actions est **indéfinible** (dénominateur nul → échec de
  couverture) ; côté `high`, il est mesurable. Ce n'est pas un « meilleur
  taux », c'est un dénominateur qui existe.

## 5. Ce qu'il ne faut pas faire

- **Ne pas** ouvrir `correspondance.json` avant d'avoir rempli et daté la
  grille.
- **Ne pas** conclure à partir d'une seule génération : la variance du modèle
  n'est pas isolée.
- **Ne pas** remplacer la revue par la lecture du rapport formel : le rapport
  nomme les profils, il n'est donc pas aveugle.
- **Ne pas** corriger le code entre les deux variantes : cela annulerait la
  comparaison. Le code vérificateur est resté inchangé pendant toute la
  campagne.
