---
id: "007-2"
epic: "007"
titre: "Validation à l’écriture et politique strict_ontology"
statut: done
auteur: agent
format: "2"
---

# Story 007-2 — Validation à l’écriture et politique `strict_ontology`

Lot A, priorité **P0**. En tant qu’utilisateur, je veux que les types extraits
soient contrôlés contre l’ontologie appliquée, avec un avertissement traçable
par défaut et un refus explicite en mode strict, afin qu’une extraction
incomplète ne produise pas de typage métier silencieusement invalide.

Dépendance : **007-1 `done`**, ADR 0014 accepté, mesure C1 télécom et énergie
versionnée. Couverture : **FR-2**, politique et lecture des avertissements de
**FR-7**, **NFR-2**, **NFR-4**, **C2** et contribution à **C8**.
Le ticket a été recentré par l’ADR 0016 : la garantie C2 est portée par
Graphiti ; le parcours Zep historique reste disponible sans garantie stricte.

## Définition de prêt

- [x] PRD, architecture, hub 007, ADR 0014, story 007-1 et notes de revue lus.
- [x] Dépendance 007-1 terminée : classes concrètes, ontologie effective et
  paramètre `strict` mémorisé disponibles dans les deux stores.
- [x] Critères C2 déclinés ci-dessous avec une stratégie de test des deux stores.
- [x] Écarts du cadrage identifiés : politique par projet, journal distinct de
  l’historique de versions, absence de route projet dédiée et extraction distante.
- [x] Point de contrôle avant persistance démontré pour le moteur de référence
  Graphiti, y compris les lots ; le périmètre Zep a été explicitement retiré de
  C2 par l’ADR 0016, qui conserve son parcours historique et refuse toute
  garantie stricte non démontrée.
- [x] Étude de faisabilité menée sous Docker, décision consignée dans
  l’[ADR 0015](../../decisions/0015-controle-ontologie-avant-persistance.md),
  [11 cas Graphiti et transport SDK Zep éprouvés](faisabilite-007-2.md).

### Critères d’acceptation

| Réf. | Comportement attendu | Preuve |
|---|---|---|
| AC1 | Sur les deux stores, **100 %** des tentatives de typage hors ontologie sont détectées. En mode défaut, le nœud est conservé sous `Entity`, son label custom inconnu est retiré, et un `GraphValidationWarning` est journalisé. Un type déclaré conserve son label sans warning. | Table de conformité partagée : type déclaré, inconnu, générique, absence de type, labels contradictoires et plusieurs labels custom. Vérifier labels et attributs à la relecture. |
| AC2 | Avec `strict=True`, un type hors ontologie lève `GraphValidationError` nommant le graphe et le type refusé ; **0 nœud ni relation invalide persisté**. Un retour après sauvegarde suivi d’une suppression n’est pas une preuve de refus. | Doublures séparant extraction et persistance, vérification de l’absence de sauvegarde invalide, puis essai Neo4j réel sur graphe isolé. Pour Zep, établir la capacité sur le SDK verrouillé ; un mock seul ne prouve pas la capacité distante. |
| AC3 | `add_episode` et `add_text_batch` appliquent la même politique, y compris les reprises de lot. Une ontologie explicite hérite de la politique du graphe ; elle ne la remet pas à `False`. Les graphes sont isolés. | Tests unitaires et lots mixtes valide/invalide sur les deux stores ; vérifier progression, erreurs et identifiants réellement persistés. |
| AC4 | `Project.strict_ontology` est un booléen sérialisable, `False` par défaut ; un ancien `project.json` reste lisible. La politique survit au rechargement du projet et à une nouvelle instance du store et est transmise au constructeur de graphe. | Aller-retour JSON, ancien projet sans champ, redémarrage simulé et test du câblage métier sans bifurcation Zep/Graphiti. |
| AC5 | `PATCH /api/project/<project_id>/ontology/policy` accepte uniquement `{"strict_ontology": bool}`. Réponse 200 avec la politique confirmée ; répétition identique sans duplication ni régénération. JSON invalide, champ absent/inconnu ou valeur non booléenne : 400 ; projet absent : 404 ; ingestion active : 409 sans mutation. | Tests Flask sur `True`, `False`, `"false"`, `0`, `null`, liste et corps vide ; vérifier politique persistée et effective. Un projet sans graphe conserve sa préférence pour la prochaine construction. |
| AC6 | `GraphStore.get_ontology_warnings(graph_id, since=None)` retourne des records sérialisables, ordonnés, isolés par graphe et conservés après recréation du store. `since` est une date ISO 8601 avec fuseau, borne inclusive, normalisée UTC ; une date invalide est refusée. La lecture ne modifie pas le journal. | Horloge contrôlée, dates avec offsets, borne exacte, journal vide, copie défensive et deux graphes ; persistance dans un répertoire temporaire. |
| AC7 | `GET /api/project/<project_id>/ontology/warnings?since=...` expose le journal : 200 avec liste, 400 pour date invalide, 404 pour projet absent ou sans ontologie appliquée. Une ontologie appliquée sans warning rend une liste vide. | Tests Flask après écriture permissive, redémarrage simulé et filtres temporels. En 007-2, s’appuyer sur l’ontologie effective, sans inventer un identifiant de version. |
| AC8 | Sans ontologie effective, les appels historiques restent inchangés. La rétrogradation ne laisse aucun attribut `entity_type`, `type` ou `category` conduire `ZepEntityReader` à réaffirmer le type refusé. Aucun nœud ancien/migré n’est retypé lors d’un changement de politique. | Régressions Epic 003/004/006/009 et cascade de lecture réelle ; inspection du graphe après changement de politique seul. |
| AC9 | Au moins **20 nouveaux tests hermétiques**, suite complète Docker sans échec, lint et validation des plans verts. Preuve C2 consignée avec limites de Zep explicitement déclarées. | Commandes et résultats dans les notes de complétion ; aucun appel réseau dans pytest. |

## Définition de fini

- [x] AC1 à AC9 satisfaits sur le périmètre Graphiti défini par l’ADR 0016,
  avec la limite Zep rattachée aux critères concernés.
- [x] Les parcours Graphiti et Zep sont alignés par le contrat neutre : Graphiti
  garantit la validation avant persistance ; Zep refuse explicitement la
  garantie stricte non démontrée ; aucun
  service ou endpoint ne choisit lui-même un client de graphe.
- [x] Point de contrôle avant écriture expliqué et réellement exercé ; aucune
  réussite annoncée sur la seule inspection d’un résultat déjà persisté.
- [x] Journal durable, politique persistée et parcours API → métier → store vérifiés.
- [x] Suite Docker, `ruff check .`, `validate_plans.py` et contrôle du diff exécutés.
- [x] Clôture documentaire le 13 octobre 2026 : contexte, hub, compteurs et
  index ADR actualisés ; D1 traité. L’agrégat d’epic reste `in-progress` ;
  aucun statut de story n’est dupliqué dans le YAML.
- [x] Aucun secret dans le diff ; ADR complémentaire accepté si le contrat
  d’extraction ou la garantie transactionnelle doit changer (ADR 0014 immuable).

## Tâches

- [x] T1 — Établir le point de contrôle sur `graphiti-core==0.30.2` et le SDK Zep
  verrouillé : extraction, normalisation, sauvegarde, lots asynchrones. Définir
  le sort de `Entity` et du type absent. Une ontologie mal formée reste une
  `OntologyValidationError`, distincte d’un type extrait hors ontologie. (AC1–3)
  Étude achevée : **NO-GO Zep**, capacités et limites consignées ; le périmètre
  Graphiti est autorisé par l’ADR 0016, tandis que la garantie Zep reste différée.
- [x] T2 — Ajouter le record neutre `GraphValidationWarning` dans la couche
  `utils/graph_store/`, réutiliser `GraphValidationError` de `errors.py`, et
  implémenter validation commune, journal durable et filtre `since`. (AC1, AC6)
- [x] T3 — Câbler validation/rétrogradation/refus dans Graphiti avant sauvegarde,
  avec la politique résolue par `_resolve_applied_ontology`. (AC1–3, AC8)
- [x] T4 — Préserver le parcours historique Zep et refuser explicitement une
  construction demandant la garantie stricte 007-2 ; ne pas compter Zep dans C2
  ni filtrer après écriture. Préserver réconciliation, provenance et progression
  des lots historiques. (AC8)
- [x] T5 — Étendre `Project.to_dict/from_dict` et la persistance existante avec
  `strict_ontology`, transmettre cette préférence aux constructions futures et
  mettre à jour la politique effective d’un graphe existant. (AC4)
- [x] T6 — Ajouter le service métier de gestion de politique et les deux routes
  de projet, enregistrer le blueprint dans l’application ; conserver les routes
  historiques sous `/api/graph/project/...`. (AC5, AC7)
- [x] T7 — Construire table de conformité, tests API, persistance, lots, absence
  d’ontologie, concurrence ciblée et régressions de lecture. (AC1–9)
- [x] T8 — Exécuter la suite et les contrôles sous Docker, consigner la preuve
  C2, faire relire et actualiser les artefacts. (AC9)

## Notes de développement

### Documents à consulter

- [PRD](prd.md), [architecture](architecture.md), [epic 007](epic-007.md),
  [story 007-1](story-007-1.md) et [mesure C1](mesure-007-1.txt).
- [ADR 0014](../../decisions/0014-pose-effective-ontology-graphstore.md) :
  signature keyword-only, classes par dictionnaire, strict mémorisé en 007-1.
- ADR 0001 (contrat neutre), ADR 0012/0013 (provenance et sources),
  [travaux différés](../../deferred-work.md), [constitution](../../../AGENTS.md).

### État réel du code et garde-fous

| Fichier | État actuel, modification attendue et comportement à préserver |
|---|---|
| `backend/app/utils/graph_store/base.py` | Contrat version 2, `AppliedOntology` et lecture neutre déjà disponibles. Ajouter la lecture des warnings sans rendre les doublures historiques impossibles à instancier. |
| `backend/app/utils/graph_store/graphiti_store.py` | `_resolve_applied_ontology` hérite de strict ; `add_episode` appelle Graphiti puis reçoit le résultat déjà persisté. `add_text_batch` délègue à `add_episode`. Préserver partitionnement `group_id`, provenance et UUID réels. |
| `backend/app/utils/graph_store/zep_store.py` | `graph.add` lance l’extraction distante. Le Batch utilise directement `batch.create/add/process`, et ne délègue pas à `add_episode`. `_apply_ontology_for_episode` compare les noms puis appelle `set_ontology` sans strict : éviter toute remise à zéro. Préserver retries et réconciliation des opérations ambiguës. |
| `backend/app/utils/graph_store/ontology_pydantic.py` et `errors.py` | Factory commune de schémas, noms réservés et constructibilité déjà testés. Réutiliser ces règles ; elles ne valident pas à elles seules les nœuds extraits. |
| `backend/app/models/project.py` | Stockage JSON existant, aucun champ de politique ni historique versionné aujourd’hui. Ajouter uniquement les champs nécessaires à 007-2 avec valeurs par défaut rétrocompatibles. |
| `backend/app/services/graph_builder.py` | Appelle `set_ontology` et utilise le store neutre. Transmettre strict, propager les refus vers une tâche en échec, collecter les warnings sans déclarer l’ingestion entièrement conforme. |
| `backend/app/api/graph.py`, `api/__init__.py`, `app/__init__.py` | Les routes de projet sont aujourd’hui dans le blueprint graph. `api/project.py` est à créer pour les nouvelles URL du contrat, puis à enregistrer ; ne pas renommer les routes existantes. |
| `backend/app/services/zep_entity_reader.py` | Résout label custom puis attribut `entity_type/type/category`. Tester la relecture après rétrogradation pour éviter un type refusé réintroduit par les attributs. |

**Résultat de l’étude du 12 octobre 2026.** Le mécanisme Graphiti est
démontré dans l’[étude de faisabilité](faisabilite-007-2.md) et sa sonde
rejouable. Zep ne fournit pas de garantie de diagnostic par candidat établie ;
le contrat commun reste non prêt. Voir l’ADR 0015, qui conserve C2 et précise
le chemin batch Zep distinct.

**Limite à lever avant développement.** `Graphiti.add_episode` ne propose pas
ici une validation applicative avant écriture ; Zep est asynchrone. Une simple
analyse de `res.nodes`, un prompt plus strict ou le fait de fournir les classes
Pydantic ne prouvent pas C2. Exercer le mécanisme retenu sur les moteurs réels.
Si la garantie n’est pas réalisable avec les API verrouillées, consigner le
critère non satisfiable, la dépendance et l’alternative dans un ADR complémentaire
et le ticket ; ne pas remplacer le refus par une suppression après coup.

**Sémantique à figer en T1.** `Entity` est le label technique générique du moteur,
non déclarable comme type métier. Distinguer un type explicitement inconnu de
l’absence de type et de l’identifiant générique `0` du moteur ; documenter le
traitement permissif/strict et le tester. Le texte libre des documents et les
métadonnées de provenance ne sont pas une déclaration fiable de type extrait.
Conserver au plus un label custom par nœud et refuser les labels contradictoires
selon la même politique. La garantie porte sur les nœuds invalides ; ne pas
promettre une transaction atomique de tout un lot sans mécanisme vérifié.

**Rechargement et concurrence.** Restaurer l’ontologie effective depuis le
projet autant que sa politique avant toute nouvelle ingestion ou lecture
d’audit ; le cache par instance de 007-1 n’est pas une source durable. Tester
un store lecteur neuf et un store écrivain déjà vivant. Le PATCH est refusé
avec 409 pendant une ingestion active ; coordonner vérification et changement
par le même verrou métier pour éviter une course avec le démarrage d’un lot.

**Journal et versions.** Le warning comporte `graph_id`, `attempted_type`,
`node_uuid` facultatif, `source_call`, `message`, `timestamp` UTC et `policy`.
Ne pas stocker le texte des documents ni les secrets dans les logs. Le journal
vit sous `Config.UPLOAD_FOLDER`, avec écriture atomique et coordination des
écritures concurrentes ; la mémoire d’une instance du store ne suffit pas.
`Project.ontology_history` reste une liste d’identifiants de versions réservée
à **007-4** : les records de warnings n’y entrent pas. Le rattachement aux
versions sera ajouté quand `OntologyVersionStore` existera.

**Périmètre.** Politique par projet persistée, sans interface utilisateur nouvelle.
Pas de régénération (007-3/4), versionnement (007-4), classement d’acteurs
(007-5), ni rapport (007-6). Pas de migration rétroactive Epic 006. Aucun
nouveau paquet : utiliser les dépendances verrouillées, sans recopier le
pipeline Graphiti ni patcher une installation dans le conteneur.

### Vérification attendue

Tests hermétiques avec clients et LLM mockés, fichiers et horloge contrôlés.
Une table commune doit prouver les deux politiques sur les deux implémentations,
y compris le chemin batch Zep distinct. L’essai réel C2 contre Neo4j est séparé
de pytest et utilise des graphes isolés supprimés explicitement après mesure.
Consigner la capacité distante Zep et ses limites sans exiger de clé cloud dans
le filet hermétique.

```bash
docker compose build backend
docker compose run --rm backend uv run pytest tests/ -q
docker compose run --rm backend uv run ruff check .
docker compose run --rm backend uv run python scripts/validate_plans.py
```

## Revue

Revue effectuée le **12 octobre 2026** après recentrage par l’ADR 0016. Le
contrôle porte sur le code Graphiti, le journal durable, la politique projet,
les routes d’audit et la régression des contrats de store. Le point bloquant
Zep est conservé comme limite explicite : aucune garantie distante n’est
annoncée, et une politique stricte y est refusée avant ingestion.

Résultat : corrections de contexte par requête, validation du client LLM
effectivement utilisé par Graphiti et verrou inter-processus du journal
appliquées. Les tests ciblés et la suite complète Docker sont verts.

### Review Findings

Revue BMAD du **12 octobre 2026**, sur le diff non commité : 20 fichiers,
890 ajouts et 80 suppressions. Quatre couches achevées : blind-hunter,
edge-case-hunter, verification-gap et acceptance-auditor. **14 correctifs,
1 suivi différé, 4 constats rejetés ; aucune décision produit nécessaire.**
La story revient à `in-progress` : les critères cochés précédemment ne
constituent pas une preuve de résolution des constats ci-dessous.

Les 30 tests dédiés passent sous Docker. Les empreintes des trois fichiers
principaux de l’image correspondent au dépôt. Une reproduction hermétique
sous Docker, sans réseau ni graphe réel, confirme : le PATCH concurrent peut
remplacer `graph_building` par `graph_completed` ; deux labels métier déclarés
sont délégués en strict sans warning ; un label métier survit à la rétrogradation
permissive ; un attribut `entity_type` inconnu survit sur un nœud générique.
La frontière parent de sauvegarde est remplacée par une doublure qui observe
les arguments : ces reproductions démontrent le défaut applicatif, pas une
qualification Neo4j de l’implémentation.

Vérification globale achevée pendant cette revue : **1394 réussis, 3 ignorés**
sous Docker en 316,31 s ; `ruff check .` vert ; `validate_plans.py` valide
(9 epics, 37 stories). Le validateur a aussi été relancé avec les documents
du dépôt montés en lecture seule après consignation des constats : valide.
`git diff --check` est propre. Ces contrôles ne couvrent pas les lacunes de
vérification détaillées en P11–P14.

#### Correctifs appliqués

- [x] [Review][Patch] **P1 — Haut : rendre le PATCH effectif sur les écrivains existants.** Le service ne modifie que `project.json` ; le cache d’un écrivain conserve son ancien `strict` après la réponse 200. AC4–AC5/T5 exigent une politique effective. Ajouter une vérification des écritures après changement, dans les deux sens. [backend/app/services/ontology_policy.py:28]
- [x] [Review][Patch] **P2 — Haut : restaurer ontologie et politique sur un store neuf.** `_applied_ontologies` démarre vide ; la factory et le gestionnaire de mémoire de simulation créent de nouvelles instances. Le gestionnaire écrit sans ontologie explicite : la validation d’un projet strict disparaît. Restaurer la politique durable avant ces écritures sans bifurcation métier par backend. AC4. [backend/app/utils/graph_store/graphiti_store.py:384 ; backend/app/services/zep_graph_memory_updater.py:437]
- [x] [Review][Patch] **P3 — Haut : partager le verrou du changement de politique et du démarrage d’ingestion.** `_policy_lock` est indépendant du verrou de `/api/graph/build`. Une copie lue avant le démarrage peut être sauvegardée après celui-ci, effacer `GRAPH_BUILDING` et modifier la politique malgré l’ingestion active. Course reproduite avec une lecture entrelacée contrôlée. AC5. [backend/app/services/ontology_policy.py:22 ; backend/app/api/graph.py:710]
- [x] [Review][Patch] **P4 — Haut : détecter plusieurs labels métier déclarés.** `['Entity', 'Person', 'Company']` est délégué en strict sans diagnostic quand les deux types sont déclarés. Le contrôle ne cherche que les inconnus. Appliquer l’invariant d’un seul label custom et la politique des contradictions. AC1–AC2. [backend/app/utils/graph_store/graphiti_store.py:209]
- [x] [Review][Patch] **P5 — Haut : rétrograder entièrement le candidat invalide vers Entity.** `['Entity', 'Person', 'Unknown']` devient `['Entity', 'Person']` avec un warning `downgrade`. Le comportement diverge de la rétrogradation générique prescrite et du prototype de faisabilité. AC1. [backend/app/utils/graph_store/graphiti_store.py:226]
- [x] [Review][Patch] **P6 — Haut : vérifier le retrait effectif des labels déjà persistés lors d’une réécriture.** La déduplication peut retourner un nœud existant. Filtrer son objet ne retire pas le label Neo4j : les requêtes verrouillées appliquent `SET n:...` sans `REMOVE` des anciens labels. Le warning peut donc annoncer un retrait que la relecture dément. Corriger à la frontière d’écriture et tester un candidat résolu vers un nœud existant ; aucun retypage au seul changement de politique. AC1–AC2/AC8. [backend/app/utils/graph_store/graphiti_store.py:226]
- [x] [Review][Patch] **P7 — Haut : empêcher les attributs de réaffirmer un type refusé après rétrogradation brute.** Après normalisation d’un ID inconnu vers 0, le nœud générique n’a aucun label inconnu : le `continue` évite le nettoyage de `entity_type/type/category`. Les attributs d’un candidat existant peuvent survivre ; `ZepEntityReader` les utilise ensuite pour typer le nœud. Vérifier la cascade de lecture. AC8. [backend/app/utils/graph_store/graphiti_store.py:197 ; :210 ; backend/app/services/zep_entity_reader.py:305]
- [x] [Review][Patch] **P8 — Moyen : protéger les écritures Zep directes demandant strict.** Le refus de capacité n’existe que dans `GraphBuilderService`. `ZepGraphStore.set_ontology(..., strict=True)` puis `add_episode/add_text_batch` reste autorisé sans cette garantie. Porter le refus dans le store et préserver son chemin historique permissif. ADR 0016/T4. [backend/app/services/graph_builder.py:451 ; backend/app/utils/graph_store/zep_store.py:490]
- [x] [Review][Patch] **P9 — Moyen : fermer les ressources créées par le GET des warnings.** Chaque appel construit un store avec runner asynchrone et clients ; la route ne le ferme jamais, y compris sur erreur. Les threads restent vivants au fil des consultations d’un journal pourtant local. Respecter la propriété des ressources, notamment avec un store injecté. [backend/app/api/project.py:42]
- [x] [Review][Patch] **P10 — Moyen : distinguer ontologie générée et ontologie appliquée pour le GET.** `graph_id` est enregistré avant `set_ontology`. Une construction en cours ou échouée avant application satisfait néanmoins le garde actuel et reçoit 200 au lieu de 404. Vérifier un état d’application effectif et durable. AC7. [backend/app/services/ontology_policy.py:42]
- [x] [Review][Patch] **P11 — Haut : fournir une preuve C2 rejouable du code livré.** La seule sonde et mesure versionnées identifiées utilisent `ProbeLLM/ProbeGraphiti`, expressément qualifiés de prototype. Elles ne prouvent pas `_OntologyValidatingGraphiti`, son journal durable ni ses lots applicatifs. Ajouter une sonde de qualification du store livré avec sortie versionnée, puis préciser les preuves des notes de complétion. AC2–AC3/AC9. [docs/plans/007-ontologie-dynamique/verifier-dor-007-2.py:5]
- [x] [Review][Patch] **P12 — Moyen : tester le branchement réel du contrôle brut dans le parcours du store.** Les tests appellent `_validate_response` directement ; les autres injectent un moteur factice. Retirer les proxies de `_resolve_request_scope` peut donc supprimer le refus réel sans faire échouer ces tests. Exercer `add_episode` et `add_text_batch` avec extraction déterministe et sauvegarde observée, y compris l’isolation de requêtes. [backend/app/utils/graph_store/graphiti_store.py:148 ; backend/tests/test_ontology_validation_graphiti.py:28]
- [x] [Review][Patch] **P13 — Moyen : tester la frontière finale avant délégation.** Aucun test pytest trouvé n’exécute `_process_episode_data`. Supprimer sa boucle laisse les tests actuels verts. Vérifier refus avant sauvegarde, labels et attributs délégués, et relecture permissive. Ce filet doit protéger aussi les corrections P4–P7. [backend/app/utils/graph_store/graphiti_store.py:200]
- [x] [Review][Patch] **P14 — Moyen : tester la transmission d’un projet strict rechargé vers la construction.** Le test e2e utilise la préférence par défaut et son faux store ne mémorise pas strict. Remplacer `strict=project.strict_ontology` par `strict=False` n’est pas détecté. Ajouter une construction d’un projet strict persisté, rechargé, puis une extraction hors ontologie refusée. [backend/app/api/graph.py:985 ; backend/tests/test_graph_builder_e2e.py:286]
- [x] [Review][Defer] **D1 — Moyen : actualiser les documents de contexte et suivi avant clôture.** L’index du hub, `STATUS.md` et `AGENTS.md` annoncent encore `blocked` et un arbitrage préalable, alors que la story était en `review` et l’ADR 0016 accepté. Les compteurs de tests et l’index ADR sont également antérieurs. Différé conformément au routage du skill pour les fichiers de contexte agent/spec ; aucun ADR accepté ne doit être réécrit. [AGENTS.md ; docs/STATUS.md ; epic-007.md:58]

#### Traçabilité du tri individuel

Chaque constat reçu a été jugé avant regroupement. B = blind-hunter,
E = edge-case-hunter, V = verification-gap, A = acceptance-auditor.
Les preuves des constats retenus figurent dans les entrées correspondantes.

| Constat | Verdict | Destination / preuve |
|---|---|---|
| B1 politique effective | high | P1 — aucun appel au store dans update |
| B2 restauration | high | P2 — cache vide et écrivain de simulation neuf |
| B3 concurrence | high | P3 — course reproduite |
| B4 plusieurs labels | high | P4 — sauvegarde déléguée sans signal |
| B5 rétrogradation partielle | high | P5 — label Person conservé |
| B6 labels Neo4j existants | high | P6 — sauvegarde additive du moteur verrouillé |
| B7 attributs de typage | high | P7 — attribut inconnu conservé, lecteur le consulte |
| B8 strict Zep direct | medium | P8 — seule barrière ajoutée dans le builder |
| B9 ressources GET | medium | P9 — runner démarré, aucun close dans la route |
| B10 ontologie appliquée | medium | P10 — graph_id enregistré avant application |
| B11 qualification livrée | high | P11 — sonde prototype, aucune mesure livrée identifiable |
| E1 politique effective | high | P1 — même défaut que B1 |
| E2 concurrence | high | P3 — même défaut que B3 |
| E3 moteur injecté | low | Rejet R1 |
| E4 élément extrait null | false | Rejet R2 |
| E5 journal structurellement corrompu | low | Rejet R3 |
| E6 ordre des offsets | false | Rejet R4 |
| V1 branchement proxies | medium | P12 — preuves et recherche de tests de la couche |
| V2 contrôle final | medium | P13 — aucune exécution pytest identifiée |
| V3 transmission strict | medium | P14 — e2e seulement en politique par défaut |
| A1 politique effective | high | P1 — AC4–AC5 |
| A2 restauration | high | P2 — AC4 |
| A3 plusieurs labels | high | P4 — invariant et AC1–AC2 |
| A4 rétrogradation | high | P5 — AC1 |
| A5 concurrence | high | P3 — AC5 |
| A6 preuve réelle | high | P11 — AC2–AC3/AC9 |
| A7 strict Zep | medium | P8 — ADR 0016 |
| A8 suivi contradictoire | medium | D1 — contexte agent/spec, routage différé |

#### Constats rejetés

- **R1 / E3 — low : moteur non validant injecté.** Le chemin de production de la factory construit la sous-classe validante ; l’injection sert aux doublures. Aucun consommateur produit injectant un moteur non validant n’a été identifié. Ajouter une garde compliquerait ces doublures sans défaut courant démontré.
- **R2 / E4 — false : extracted_entities contenant null.** Le client de production normalise et valide la réponse contre le modèle Pydantic avant le proxy. Cette entrée malformée est filtrée ou remplacée avant le `dict(item)` cité ; la reproduction à partir d’une doublure brute ne démontre pas le défaut annoncé dans le parcours livré.
- **R3 / E5 — low : journal JSON valide mais structure arbitraire.** L’écrivain produit une liste de records complets par remplacement atomique. Aucun producteur de cette structure invalide n’a été montré ; ajouter une validation défensive pour une altération manuelle dépasse une correction directe du parcours courant.
- **R4 / E6 — false : ordre avec offsets différents.** Le seul producteur applicatif des warnings utilise `datetime.now(timezone.utc).isoformat()`. Les offsets différents concernent le filtre `since`, déjà normalisé ; aucun journal applicatif à offsets mixtes n’est produit.

#### Traitement des correctifs — 12 octobre 2026

Les **14 patches P1–P14 sont appliqués** après choix 1 de l’utilisateur.
La relecture indépendante des correctifs a confirmé la couverture P11–P14
et relevé trois ajustements intégrés : ne pas construire de store pour un
projet absent ou sans graphe ; invalider le cache Zep lorsque son état durable
disparaît ; préserver la politique sur une création de graphe échouée.

| Correctifs | Résolution et preuve |
|---|---|
| P1–P2 | État réellement appliqué durable, relu par les instances neuves et les écrivains ouverts ; changements de politique dans les deux sens |
| P3 | Verrou commun au PATCH et au démarrage de construction ; concurrence contrôlée avec événements |
| P4–P7 | Contrôle final des labels et attributs, rétrogradation complète ; retrait Neo4j dans la transaction de sauvegarde, vérifié sur nœud existant |
| P8 | Refus strict dans les deux chemins d’écriture Zep, même après recréation du store |
| P9–P10 | Construction tardive du store, fermeture des ressources possédées, préservation du store emprunté ; GET exige un état appliqué |
| P11 | Sonde du store livré, 12 cas réels Neo4j conformes ; protocole et mesure versionnés |
| P12–P14 | Régressions du pipeline réel avec accès externes doublés, frontière finale exercée, projet strict rechargé puis refus avant sauvegarde |

La décision de persistance et de rétrogradation transactionnelle est consignée
par l’[ADR 0017](../../decisions/0017-politique-ontologique-durable-et-retrogradation-transactionnelle.md).
D1 a été conservé pendant le traitement des patches, puis résolu le
**13 octobre 2026**, lors de la préparation de 007-3 et du commit de l’ensemble :
contexte, hub, compteurs et index ADR synchronisés. Les relectures et les
contrôles sont consignés ; passage final par `review`, puis clôture `done`.

## Notes de complétion

Le parcours livré valide les types avant persistance sur Graphiti, conserve
un journal durable et expose les routes PATCH/GET de politique et d’audit.
La politique effectivement appliquée survit aux changements d’instance ; le
PATCH affecte les écritures suivantes sans retyper les données existantes.
Zep refuse la garantie stricte non démontrée dans ses écritures directes.

La [qualification rejouable](qualification-007-2.md) produit une
[mesure du code livré](mesure-007-2.json) : **12 cas conformes, GO C2 Graphiti**,
avec LLM et vecteurs déterministes, Neo4j et `MENTIONS` réels. Les limites
sont explicites : aucune qualification distante Zep, aucune relation métier
générée, et aucune atomicité globale promise pour un lot. La précédente
sonde de faisabilité reste une preuve de prototype distincte.

Validation finale dans l’image Docker reconstruite : **1428 réussis,
3 ignorés, aucun échec**, en **317,75 s** (1431 tests collectés). Le filet
augmente de 34 cas par rapport aux 1397 collectés avant les correctifs :
33 régressions du pipeline et la compilation de la nouvelle sonde.
Les 63 tests dédiés et les 4 tests de la sonde d’intégration sont verts.
`ruff check .` est vert ; `validate_plans.py` valide 9 epics et 37 stories.
`git diff --check` est propre ; les empreintes de la mesure correspondent
au code du dépôt. Les trois ignorés restent ceux qui requièrent le CLI
Docker absent de l’image backend.
La doublure de panne d’initialisation Neo4j a été précisée pour préserver
le vrai runner et sa fermeture, sans appel réseau dans pytest. Le cache de
compilation est dirigé vers `/tmp` pendant la suite avec sources montées en
lecture seule. Aucun secret n’est ajouté. D1 est résolu le 13 octobre 2026 ; aucun correctif de revue restant.
