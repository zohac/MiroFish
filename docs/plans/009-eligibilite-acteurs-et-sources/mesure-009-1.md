# Mesure 009-1 — Classifieur d'éligibilité des acteurs

- **Mode** : real
- **Date** : 2026-10-10T17:45:38.449402+00:00
- **Commit** : `2ca4057` (arbre de travail, exécuté avant commit)
- **Politique** : 009-1-v1
- **Classifieur disponible** : True
- **Modèle** : space-bunny
- **Résultat global** : SUCCÈS

## Domaine `logiciel_gestion` — SUCCÈS

- Acteurs retenus : 8 / seuil 2
- Faux acteurs : 0 / seuil 0
- Compteurs : {'total': 23, 'eligible': 8, 'review': 3, 'ineligible': 12}

| Entité | Attendu | Obtenu | Correspond |
|---|---|---|---|
| Élodie Laurent | person/eligible | person/eligible | oui |
| Atelier Sillage | organization/eligible | organization/eligible | oui |
| Malik Benoît | person/eligible | person/eligible | oui |
| Association Abonnement Mensuel | organization/eligible | organization/eligible | oui |
| Sillage | product/ineligible | product/ineligible | oui |
| Assistance technique | service/ineligible | service/ineligible | oui |
| 29 €/mois | product/ineligible | product/ineligible | oui |
| https://sillage.example/aide | domain/ineligible | domain/ineligible | oui |
| portail.sillage.example | domain/ineligible | domain/ineligible | oui |
| Rue des Halles | place/ineligible | place/ineligible | oui |
| Lancement de Sillage | event/ineligible | event/ineligible | oui |
| Traçabilité | concept/ineligible | concept/ineligible | oui |
| Utilisateurs de Sillage | collective/review | collective/review | oui |
| Orion | unknown/review | unknown/review | oui |
| 2026-11-15 | event/ineligible | event/ineligible | oui |
| 3 mois | concept/ineligible | concept/ineligible | oui |
| Sillage Assistant | product/ineligible | product/ineligible | oui |
| Tableau de bord Sillage | product/ineligible | product/ineligible | oui |
| Association 3 mois | organization/eligible | organization/eligible | oui |
| (vide) | unknown/review | unknown/review | oui |
| Sillage | organization/eligible | organization/eligible | oui |
| Association 29 €/mois | organization/eligible | organization/eligible | oui |
| Association 2026-11-15 | organization/eligible | organization/eligible | oui |

## Domaine `evenement_culturel` — SUCCÈS

- Acteurs retenus : 8 / seuil 2
- Faux acteurs : 0 / seuil 0
- Compteurs : {'total': 23, 'eligible': 8, 'review': 3, 'ineligible': 12}

| Entité | Attendu | Obtenu | Correspond |
|---|---|---|---|
| Inès Morel | person/eligible | person/eligible | oui |
| Association des Lanternes | organization/eligible | organization/eligible | oui |
| Hugo Bernard | person/eligible | person/eligible | oui |
| Comité 2026 | organization/eligible | organization/eligible | oui |
| Lanterne | product/ineligible | product/ineligible | oui |
| Navette du festival | service/ineligible | service/ineligible | oui |
| 12 € | product/ineligible | product/ineligible | oui |
| https://lanternes.example/programme | domain/ineligible | domain/ineligible | oui |
| billets.lanternes.example | domain/ineligible | domain/ineligible | oui |
| Place des Tilleuls | place/ineligible | place/ineligible | oui |
| Ouverture du festival | event/ineligible | event/ineligible | oui |
| Accessibilité | concept/ineligible | concept/ineligible | oui |
| Habitants du quartier | collective/review | collective/review | oui |
| Aube | unknown/review | unknown/review | oui |
| 2026-12-01 | event/ineligible | event/ineligible | oui |
| 2 semaines | concept/ineligible | concept/ineligible | oui |
| Lampe Lanterne | product/ineligible | product/ineligible | oui |
| Plan du festival | product/ineligible | product/ineligible | oui |
| Association 2 semaines | organization/eligible | organization/eligible | oui |
| (vide) | unknown/review | unknown/review | oui |
| Lanterne | organization/eligible | organization/eligible | oui |
| Association 12 € | organization/eligible | organization/eligible | oui |
| Association 2026-12-01 | organization/eligible | organization/eligible | oui |

## Limites et écarts (revue de code du 11 octobre 2026)

- **Fixtures télégraphiées** : les résumés des cas composites (« Association
  Abonnement Mensuel », « Comité 2026 », « Association 29 €/mois »…) énoncent la
  conclusion attendue (« son nom ne désigne pas une formule tarifaire », « ce
  nom n'est pas une date pure »). La mesure démontre donc le comportement de
  bout en bout sur fixtures annotées — pas la généralisation sémantique à un
  résumé neutre. Renforcer avec des cas à résumé non concluant avant de
  revendiquer cette généralisation.
- **Rationales corrompus du fournisseur** : trois sorties mélangent d'autres
  scripts (Hugo Bernard : « …personne physique做题未被描述为组… » ; Navette du
  festival : « …personneSNS… » ; Ouverture du festival : « …organisation。即使… »).
  Les décisions role/status restent correctes et inchangées ; l'anomalie est
  consignée ici, elle était invisible dans la matrice.
- **Provenance du champ `commit`** : `git` est absent de l'environnement
  d'exécution, `_git_commit()` retournerait « inconnu » ; le champ a été
  renseigné à la main (`2ca4057`, arbre de travail). Le `.md` a été reformaté
  (le rendu de la sonde n'émet pas de backticks) — une réexécution de la sonde
  reproduira ci-dessus uniquement après régénération des deux fichiers.
- **Verdict renforcé après coup** : le critère de faux acteurs de la sonde
  compte désormais aussi les activations `review`→`eligible` (revue du
  11 octobre 2026). La matrice enregistrée reste valide (toutes les lignes
  correspondent), et les seuils n'auraient pas changé sous le nouveau critère.
