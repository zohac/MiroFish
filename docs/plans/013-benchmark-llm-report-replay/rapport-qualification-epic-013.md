# Rapport de qualification — banc de benchmark A/B du ReportAgent

> Généré par `backend/scripts/verifier_benchmark_epic_013.py` le 2026-10-20 19:16:45 UTC.
> Grille de score : version `1.1.0` (34 métriques, grille fermée).
> Simulation : `sim_80a54d7bbd7b` · mode de rejeu : `replay_frozen` · répétitions par variante : 1.
> Dossier de campagne : `benchmark-013-20261020-203040`.

## 1. Verdict de la campagne

**comparaison contrôlée**

Motif : Les deux variantes reposent sur le même jeu de preuves figées (empreinte SHA-256 identique).

Ce verdict porte sur le **contrôle de la comparaison** (même jeu de preuves, même code vérificateur). Il ne conclut rien sur la qualité rédactionnelle d'une variante : cette appréciation appartient à la revue aveugle outillée par ce banc.

## 2. Protocole appliqué

- **Preuves figées** : empreinte SHA-256 `26cf493ea7bbd579be7162c0eec3ee7074f905f0e5532a3c004cb9c017989f56` (737 événements observés, 41 acteurs, archives d'entretiens présentes : non).
- **Rejeu** : `replay_frozen` — les interactions OASIS live sont neutralisées, le paquet de preuves est celui scellé par l'empreinte.
- **Profils** : issus du catalogue fermé des profils LLM de rapport (`flash-medium`, `flash-high`). Aucun profil n'est écrit en dur dans le banc.
- **Répétitions par variante** : 1.
- **Tentatives par variante** : 1 au maximum. Une génération qui **lève** (erreur d'infrastructure : réponse amont coupée, 502, timeout réseau) est relancée une fois, avec le même profil et le même jeu de preuves : une panne réseau n'est pas un résultat. Les relances sont consignées variante par variante.
- **Grille de score** : version `1.1.0`, fermée et purement mécanique. Elle ne contient aucun champ interprétatif et ne classe pas les variantes.
- **Code vérificateur** : inchangé pendant toute la campagne. Toute modification entre deux variantes annulerait la comparaison.

## 3. Contrôle d'environnement

- **Backend de graphe résolu** : `graphiti` (attendu : `graphiti`). Les outils graphe du `ReportAgent` interrogent donc le Neo4j local, et non une passerelle distante.
- **État du graphe au pré-contrôle** : 42 nœuds, 163 arêtes.
- **État du graphe à la fin de la campagne** : identique au pré-contrôle, mesuré sur 2 variante(s).
- **Rappel de protocole** : le graphe n'est **pas** scellé par l'empreinte des preuves. `replay_frozen` ne gèle que les interactions OASIS live ; les outils graphe interrogent toujours Neo4j. C'est le principal biais résiduel du protocole, et c'est la raison de ce garde-fou.

## 4. Métriques par variante

| Métrique | A | B |
|---|---|--- | ---|
| `claims_total` | 159 | 178 |
| `claims_verified` | 0 | 1 |
| `claims_unsupported` | 152 | 169 |
| `claims_contradicted` | 7 | 8 |
| `claims_verification_ratio` | 0 | 0.0056 |
| `claims_action_total` | 0 | 1 |
| `claims_action_verified` | 0 | 1 |
| `claims_action_verification_rate` | indisponible | 1 |
| `quality_total_checks` | 5 | 5 |
| `quality_passed_checks` | 4 | 4 |
| `quality_warning_checks` | 1 | 1 |
| `quality_failed_checks` | 0 | 0 |
| `quality_publication_status` | needs_review | needs_review |
| `quality_is_publishable` | non | non |
| `cohort_total_members` | 18 | 18 |
| `cohort_active_members` | 17 | 17 |
| `cohort_silent_members` | 1 | 1 |
| `cohort_adoption_denominator` | 12 | 12 |
| `cohort_adoption_rate` | 0 | 0 |
| `usage_calls_count` | 58 | 50 |
| `usage_prompt_tokens` | 452161 | 521268 |
| `usage_completion_tokens` | 31159 | 32428 |
| `usage_thinking_tokens` | 0 | 0 |
| `usage_cached_tokens` | 0 | 0 |
| `usage_total_tokens` | 517143 | 582629 |
| `usage_duration_seconds` | 2195.4498 | 1885.2271 |
| `usage_wall_seconds` | 2214.2056 | 2220.1092 |
| `usage_estimated_cost_usd` | 0 | 0 |
| `usage_theoretical_cost_usd` | 0.9119 | 1.0251 |
| `usage_stop_reason` | indisponible | indisponible |
| `usage_stop_message` | indisponible | indisponible |
| `usage_finish_reasons` | stop, length | stop, length |
| `report_characters` | 47202 | 49468 |
| `report_sections` | 13 | 13 |

**Écarts bruts**

| Métrique | Écart brut (B − A) |
|---|---|
| `claims_total` | 19.0 |
| `claims_verified` | 1.0 |
| `claims_unsupported` | 17.0 |
| `claims_contradicted` | 1.0 |
| `claims_verification_ratio` | 0.0056 |
| `claims_action_total` | 1.0 |
| `claims_action_verified` | 1.0 |
| `quality_total_checks` | 0.0 |
| `quality_passed_checks` | 0.0 |
| `quality_warning_checks` | 0.0 |
| `quality_failed_checks` | 0.0 |
| `cohort_total_members` | 0.0 |
| `cohort_active_members` | 0.0 |
| `cohort_silent_members` | 0.0 |
| `cohort_adoption_denominator` | 0.0 |
| `cohort_adoption_rate` | 0.0 |
| `usage_calls_count` | -8.0 |
| `usage_prompt_tokens` | 69107.0 |
| `usage_completion_tokens` | 1269.0 |
| `usage_thinking_tokens` | 0.0 |
| `usage_cached_tokens` | 0.0 |
| `usage_total_tokens` | 65486.0 |
| `usage_duration_seconds` | -310.2227 |
| `usage_wall_seconds` | 5.9036 |
| `usage_estimated_cost_usd` | 0.0 |
| `usage_theoretical_cost_usd` | 0.113178 |
| `report_characters` | 2266.0 |
| `report_sections` | 0.0 |

Statut de couverture : variante A : échec de couverture ; variante B : mesurée

Un taux dont le dénominateur est connu et vaut zéro ne s'affiche pas : il est marqué « échec de couverture ». Il ne vaut jamais 100 %. Une métrique absente des artefacts s'affiche « indisponible », jamais 0.

**Certification demandée par la barrière de publication**

- Variante A : certification `needs_review` — 0 contrôle(s) en échec, 1 avertissement(s).
- Variante B : certification `needs_review` — 0 contrôle(s) en échec, 1 avertissement(s).

## 5. Comparabilité

- **Règle appliquée** : empreinte SHA-256 des preuves figées en priorité, identifiant d'instantané en repli.
- **Verdict** : comparaison contrôlée.
- **Motif** : Les deux variantes reposent sur le même jeu de preuves figées (empreinte SHA-256 identique).
- **Preuve d'identité** : `sha256`.

## 6. Coût, durée et budget

- **Coût facturable estimé** : 0.0 $ (estimation, grille tarifaire version `2026-10-19` — jamais une facture).
- **Coût théorique** : somme des `usage_theoretical_cost_usd` publiés dans le tableau §4 (mêmes tokens valorisés au tarif du fournisseur, hors gratuité de la passerelle locale). C'est le montant qu'une campagne comparable coûterait sur une passerelle facturée.
- **Durée murale de campagne** : 4434.964 s.
- Variante A (`flash-medium`, répétition 1) : statut `completed`, durée 2214.372 s, coût facturable estimé 0.0 $.
- Variante B (`flash-high`, répétition 1) : statut `completed`, durée 2220.283 s, coût facturable estimé 0.0 $.
- **Plafonds** : chaque variante applique les plafonds de son profil (`max_total_cost_usd`, `max_wall_seconds`). Un plafond atteint produit un arrêt contrôlé, avec son code et son message ; le banc ne bascule jamais d'un modèle vers un autre et n'escalade jamais un effort.

## 7. Biais résiduels et limites

- **Le graphe n'est pas figé** : le jeu de preuves est scellé, le graphe ne l'est pas. Le garde-fou de cohérence le vérifie avant et après chaque variante, mais il ne peut pas exclure une variation minime et invisible du graphe.
- **Une seule génération par variante** : une génération isolée ne permet pas de distinguer l'effet de l'effort de raisonnement de la variabilité stochastique du modèle. Les répétitions commandées par `--repetitions` sont le moyen de réduire cette variance ; leur nombre est indiqué ci-dessus.
- **Effort effectif déclaré par le fournisseur** : l'effort retenu n'est déclaré effectif que si la réponse porte un objet d'usage. Sinon la valeur reste « inconnue ».
- **Arbitrage qualitatif hors du banc** : la grille mesure des décomptes et des taux. Elle n'évalue pas la qualité rédactionnelle, qui relève de la revue aveugle.

## 8. Domaines couverts et non couverts

**Couverts par cette campagne**

- Le rejeu à preuves figées sur une simulation existante, sans relance d'OASIS ni reconstruction de graphe.
- La consommation de tokens (entrée, sortie, réflexion, cache), la durée d'inférence et le coût estimé.
- L'intégrité du registre des affirmations et la barrière de publication, lus dans les artefacts produits.
- La couverture de cohorte et les statuts de décision.

**Non couverts par cette campagne**

- La qualité rédactionnelle elle-même : elle est mesurée par la revue aveugle, dont le matériel est fourni à côté de ce rapport.
- Les autres simulations, les autres domaines et les autres modèles : une campagne porte sur un seul jeu de preuves.
- Le coût réel d'une facturation : les montants publiés sont des estimations issues de la grille tarifaire du dépôt.
- La robustesse du rejeu face à une dérive du graphe : le banc la détecte et écarte la variante, il ne la répare pas.

## 9. Matériel de revue aveugle

Le dossier de campagne `benchmark-013-20261020-203040` contient :

- `variante-A.md` et `variante-B.md` : la paire anonymisée.
- `grille-aveugle.md` : la grille à remplir.
- `correspondance.json` : l'association variante ↔ profil, dans un **fichier distinct**.

Règle de procédure : la correspondance ne s'ouvre qu'après remplissage complet de la grille. Le banc n'exécute pas cette revue : un agent ne peut pas être son propre juge aveugle.
