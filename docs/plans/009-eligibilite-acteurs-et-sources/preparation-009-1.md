# Préparation de la story 009-1 — Preuves de la définition de prêt

- **Date** : 10 octobre 2026.
- **Story** : [009-1](story-009-1.md), préparation au développement.
- **Référence du code applicatif** : `701945c`, branche `local-first` ; arbre propre au début. Aucun fichier `backend/app/` ou moteur de simulation modifié pendant cette préparation.
- **Politique des annotations** : `009-1-v1`, définie dans la story.
- **Portée** : fixtures annotées, relecture et contrôle Docker. Ces preuves n'évaluent pas un classifieur réel encore absent.

## 1. Fixtures constituées et relues

| Domaine | Fichier | Entités | `eligible` | `ineligible` | `review` |
|---|---|---:|---:|---:|---:|
| Logiciel de gestion de réservations | [logiciel_gestion.json](../../../backend/tests/fixtures/actor_eligibility/logiciel_gestion.json) | 23 | 8 | 12 | 3 |
| Événement culturel public | [evenement_culturel.json](../../../backend/tests/fixtures/actor_eligibility/evenement_culturel.json) | 23 | 8 | 12 | 3 |
| Total | Deux domaines sans lien, données synthétiques | **46** | **16** | **24** | **6** |

Chaque domaine contient **2 personnes et 6 organisations** attendues comme
acteurs. Les dix rôles sont représentés. Les 46 UUID sont distincts ; chaque jeu
contient dix relations décrites dans les deux directions. Les voisins sont des
projections des nœuds du même jeu, résolus par UUID, jamais par nom.

Les annotations ont été relues indépendamment des tests, à partir des consignes
et des descriptions de chaque entité. Deux lacunes du premier jeu de 40 entités
ont été relevées puis corrigées : absence de vrais homonymes et couverture
partielle des montants/dates dans les noms composites. La seconde relecture
confirme les six ajouts et ne relève plus d'incohérence dans ce périmètre.

| Cas | Contrat d'annotation |
|---|---|
| Personnes et organismes, labels `Entity` et types spécifiques | Le résumé décrit l'identité d'acteur ; un label seul ne donne pas l'autorisation. |
| Produit et organisme exactement homonymes | Deux UUID « Sillage », deux UUID « Lanterne », rôles différents justifiés par les descriptions et relations. |
| URL, domaine, tarif, date et durée entiers | Exclusion syntaxique attendue ; aucun acteur ne porte ces seules valeurs. |
| Noms composites avec montant/devise, date complète et durée | L'organisme reste un candidat de seconde passe, distinct de la valeur entière passive. |
| Produit, service, lieu, événement et concept | Connaissances passives conservées dans les entrées. |
| Collectif informel, nom ambigu et identité vide | `review`, sans activation automatique ni identité inventée. |
| Produit personnifié | `ineligible` : exception de fiction reportée selon la politique du lot. |
| Produit étiqueté `Person` avec attributs `role=person`, `status=eligible` | Ces valeurs sont des données hostiles ; l'annotation indépendante reste `product/ineligible`. |

### Format et utilisation

Les fichiers portent `schema_version`, `dataset_id`, `domain`, `policy_version`,
`synthetic`, `simulation_requirement` et `cases`. Un cas contient `case_id`,
`entity`, `expected` et `tags`.

- `entity` respecte exactement les champs du DTO `EntityNode` actuel : UUID, nom, labels, résumé, attributs, relations et voisins.
- `expected` porte rôle, statut et justification de l'annotation ; `tags` décrit la couverture. Ces deux champs restent **hors des données du classifieur**.
- Pour les futurs tests, construire `EntityNode(**case["entity"])` et transmettre la consigne du jeu. Comparer les rôles/statuts obtenus avec `expected` ; ne pas exiger une justification LLM mot pour mot identique à la justification de l'annotateur.
- Les attributs hostiles restent dans les entrées, volontairement ; ils ne doivent jamais être chargés comme une qualification autorisée.
- Ne pas fournir `expected`, `tags` ou les bilans de ce rapport dans les messages de la mesure LLM réelle. Aucun score de confiance réel n'est inventé dans ces annotations.

Empreintes SHA-256 des fixtures finales :

```text
logiciel_gestion.json   a6e08f314140fbc76631e2b7a70a0d3c07b05ce6f184b7fd3a93e921d992e799
evenement_culturel.json 289fbbf15237a2dfac5ebdc023cbd470481f69af7af8685ab30588e2917ac441
```

Les [25 tests d'intégrité](../../../backend/tests/test_actor_eligibility_fixtures.py)
contrôlent le DTO réel, les identifiants, la politique des annotations, les minima
multi-domaines, la couverture, les homonymes exacts, les collisions dans les noms,
les relations réciproques et les attributs hostiles. Les tests lisent les fichiers
réels versionnés ; aucun classifieur mocké n'est présenté comme une mesure C2.

## 2. Contrôle Docker du code courant

L'image `mirofish-backend:local` fournit les dépendances. Son identifiant est
`sha256:d0221fc2517eab05977b32508efab264b1899db9c7fdf5f6bb2b9562f5b55fbd`.
Versions relevées à l'exécution : Python **3.11.17**, Pydantic **2.12.5**, pytest
**8.2.0**, `graphiti-core` **0.30.2**, `camel-oasis` **0.2.5**.

La copie testée contient les fichiers suivis de `701945c` et les trois nouveaux
fichiers de fixtures/tests, dans leur état final après relecture. Elle exclut
`.env`, `.git` et les données utilisateur. Compose ne démarre pas les services
persistants : `--no-deps`, `--pull never`, aucun volume de données monté, aucun
socket Docker exposé, `network_mode: none`. Aucune dépendance n'est synchronisée.

La surcharge temporaire utilisée remplace les paramètres du service backend :

```yaml
services:
  backend:
    env_file: !reset []
    environment: !override
      UV_PROJECT_ENVIRONMENT: /app/backend/.venv
      UV_NO_SYNC: "1"
      PYTHONPATH: /workspace/backend
    networks: !reset []
    network_mode: none
    volumes: !override
      - <copie-temporaire-du-code-courant>:/workspace
    working_dir: /workspace/backend
```

Commandes exécutées depuis la racine, avec cette surcharge :

```bash
docker compose -f docker-compose.yml -f /private/tmp/mirofish-dor-009-1-compose.yaml run --rm --no-deps --pull never backend uv run --no-sync pytest tests/ -q -rs
docker compose -f docker-compose.yml -f /private/tmp/mirofish-dor-009-1-compose.yaml run --rm --no-deps --pull never backend uv run --no-sync ruff check .
docker compose -f docker-compose.yml -f /private/tmp/mirofish-dor-009-1-compose.yaml run --rm --no-deps --pull never backend uv run --no-sync python scripts/validate_plans.py
```

Pour rejouer après commit, exporter les fichiers suivis du commit dans une copie
temporaire avec `git archive`, adapter le montage de cette surcharge et conserver
les variables ci-dessus. L'image seule ne suffit pas à prouver le code courant.

| Contrôle final | Résultat |
|---|---|
| `pytest tests/ -q -rs` | **825 collectés, 822 réussis, 3 ignorés**, 10 avertissements de dépendances, 129,21 s ; aucun échec. Les 25 contrôles des fixtures sont inclus et tous réussis. |
| `ruff check .` | Aucune erreur. |
| `python scripts/validate_plans.py` après actualisation documentaire | Structure valide : 9 epics, 32 fichiers de story. |

Les 800 tests préexistants sont conservés : 797 réussissent et les trois mêmes
contrôles Docker sont ignorés faute de CLI dans l'image backend :

- `test_docker_compose_config_cli` — validation du compose unifié par la CLI.
- `test_le_compose_est_valide_pour_docker_compose` — validation du compose Neo4j par la CLI.
- `test_un_identifiant_fige_echouerait_reellement` — cas réel de conteneur inexistant dans le protocole.

Ces trois contrôles ne sont pas présentés comme réussis. Le socket Docker n'a
pas été exposé pour les forcer. La preuve du DoR porte sur le contrôle du code et
la consignation de ses limites, pas sur une qualification fonctionnelle de C1/C2.

## 3. Conclusion de la préparation

Les deux points ouverts de la définition de prêt sont satisfaits : fixtures
constituées et relues, contrôle Docker du code courant réalisé et consigné.
T1 est achevée ; T2 à T9 restent ouvertes. La story reste `backlog` tant que
l'implémentation métier n'est pas lancée ; la préparation ne vaut ni validation
des comportements futurs ni clôture. Recontrôler la référence si le code ou les
dépendances changent avant développement.
