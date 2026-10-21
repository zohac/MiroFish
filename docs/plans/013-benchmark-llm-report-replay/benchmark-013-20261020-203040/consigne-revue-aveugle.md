# Consigne d'évaluation — revue aveugle de la campagne `benchmark-013-20261020-203040`

Ce document est la procédure à suivre pour faire la **revue aveugle** de la
campagne. Elle est la seule chose que le banc n'a pas faite, et c'est
délibéré : un agent ne peut pas être son propre juge aveugle.

> **Rappel de la règle du dépôt** (PRD source §8 et §12.5) : l'expérience doit
> publier séparément le score **brut** des composants existants — c'est fait,
> voir `rapport-qualification-epic-013.md` — **et** une revue manuelle, avant
> d'attribuer le résultat au LLM. Cette revue est donc **préalable à toute
> décision de changement de modèle**.

---

## 1. Ce que l'évaluateur reçoit

**Uniquement ces deux fichiers :**

- `variante-A.md`
- `variante-B.md`

**Et rien d'autre.** En particulier, ne transmettez pas :

- `correspondance.json` (la clé : variante ↔ profil),
- `mesure-benchmark-013.json` (la charge utile : elle contient la clé),
- `rapport-qualification-epic-013.md` (il nomme les profils et les écarts).

Si l'évaluateur lit l'un de ces trois fichiers, l'aveuglement est rompu : il
faut recommencer avec un autre évaluateur.

## 2. La consigne à transmettre

Copiez-collez le bloc ci-dessous dans un **contexte neuf**, en joignant
`variante-A.md` et `variante-B.md` (et rien d'autre).

```text
Tu es un évaluateur indépendant. Deux rapports annotés t'ont été fournis :
« variante-A.md » et « variante-B.md ». Ils ont été produits sur le même jeu
de preuves par deux configurations d'un même modèle, et tu ne sais pas
laquelle correspond à laquelle. Tu ne peux pas et ne dois pas deviner.

Remplis la grille suivante, sur l'échelle 0 à 5 (0 = absent, 5 = excellent),
et remplis la colonne « Commentaire » avec une justification factuelle
(appuyer sur des passages précis du rapport, ne pas généraliser) :

| # | Critère | Échelle | Note A | Note B | Commentaire |
|---|---|---|---|---|---|
| 1 | Exactitude factuelle vérifiable | 0 à 5 | | | |
| 2 | Couverture de la cohorte | 0 à 5 | | | |
| 3 | Explicitation des limites et des objections | 0 à 5 | | | |
| 4 | Lisibilité et structure du rapport | 0 à 5 | | | |
| 5 | Respect des contraintes de publication | 0 à 5 | | | |

Règles de lecture :
- Un rapport qui affirme une action, un paiement, une adoption ou une
  citation sans trace observable est une **erreur matérielle** : compte-la et
  signale-la.
- Une section obligatoire manquante (objections, limites, contradictions) est
  un défaut de publication, pas un simple détail de style.
- Distingue « le rapport dit qu'il n'a pas pu établir » (honnêteté) de « le
  rapport affirme sans preuve » (erreur).
- N'optimise pas le style, la longueur ou l'assurance du rapport.
- Si un critère te semble impossible à noter, dis-le au lieu de deviner.

Termine par :
1. la liste des erreurs matérielles repérées dans chaque variante, avec citation
   du passage concerné ;
2. les points où l'un des rapports est manifestement plus faible que l'autre,
   sans en tirer de conclusion générale sur la configuration ;
3. ce que tu n'as pas pu vérifier.
```

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

- **Le budget n'est pas le même.** Le rapport formel mesure, pour cette
  campagne : `high` consomme **~13 % de tokens de plus** et **~12 % de coût
  théorique de plus** que `medium` (0,9119 $ → 1,0251 $). Sur une passerelle
  locale facturée au coût nul, cela ne se voit pas ; ailleurs, c'est le poste
  principal.
- **Une seule génération par variante.** L'écart observé entre `medium` et
  `high` (159 → 178 affirmations ; 0 → 1 assertion d'action vérifiée) peut
  être dû à l'effort **ou** à la variabilité stochastique du modèle. Pour
  trancher, il faut `--repetitions > 1` : le banc l'expose, la campagne de
  référence ne l'a pas fait.
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
