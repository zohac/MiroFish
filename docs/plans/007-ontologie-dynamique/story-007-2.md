---
id: "007-2"
epic: "007"
titre: "Validation à l’écriture et politique strict_ontology"
statut: blocked
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
Le ticket est `blocked` après étude de faisabilité du 12 octobre 2026 ;
le développement n’est pas commencé (ADR 0015).

## Définition de prêt

- [x] PRD, architecture, hub 007, ADR 0014, story 007-1 et notes de revue lus.
- [x] Dépendance 007-1 terminée : classes concrètes, ontologie effective et
  paramètre `strict` mémorisé disponibles dans les deux stores.
- [x] Critères C2 déclinés ci-dessous avec une stratégie de test des deux stores.
- [x] Écarts du cadrage identifiés : politique par projet, journal distinct de
  l’historique de versions, absence de route projet dédiée et extraction distante.
- [ ] Point de contrôle avant persistance démontré pour chaque moteur, y compris
  les lots ; faisabilité du refus et de la rétrogradation établie sur les versions
  verrouillées. Consigner la décision avant de démarrer l’implémentation.
  **Non satisfait au 12 octobre 2026** : Graphiti démontré ; C2 Zep non démontré.
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

- [ ] AC1 à AC9 satisfaits, preuves et limites rattachées à chaque critère.
- [ ] Deux implémentations alignées par la même table de conformité ; aucun
  service ou endpoint ne choisit lui-même un client de graphe.
- [ ] Point de contrôle avant écriture expliqué et réellement exercé ; aucune
  réussite annoncée sur la seule inspection d’un résultat déjà persisté.
- [ ] Journal durable, politique persistée et parcours API → métier → store vérifiés.
- [ ] Suite Docker, `ruff check .`, `validate_plans.py` et contrôle du diff exécutés.
- [ ] Revue réalisée, corrections traitées, passage `in-progress → review → done`
  respecté ; notes de complétion, hub et agrégat actualisés.
- [ ] Aucun secret dans le diff ; ADR complémentaire accepté si le contrat
  d’extraction ou la garantie transactionnelle doit changer (ADR 0014 immuable).

## Tâches

- [x] T1 — Établir le point de contrôle sur `graphiti-core==0.30.2` et le SDK Zep
  verrouillé : extraction, normalisation, sauvegarde, lots asynchrones. Définir
  le sort de `Entity` et du type absent. Une ontologie mal formée reste une
  `OntologyValidationError`, distincte d’un type extrait hors ontologie. (AC1–3)
  Étude achevée : **NO-GO commun**, capacités et limites consignées ;
  AC1–AC3 restent à satisfaire, aucun développement autorisé par cette case.
- [ ] T2 — Ajouter le record neutre `GraphValidationWarning` dans la couche
  `utils/graph_store/`, réutiliser `GraphValidationError` de `errors.py`, et
  implémenter validation commune, journal durable et filtre `since`. (AC1, AC6)
- [ ] T3 — Câbler validation/rétrogradation/refus dans Graphiti avant sauvegarde,
  avec la politique résolue par `_resolve_applied_ontology`. (AC1–3, AC8)
- [ ] T4 — Câbler les mêmes garanties dans Zep, y compris le chemin Batch et
  `wait_for_batch`, sans perdre la politique lors d’une ontologie explicite.
  Préserver réconciliation, provenance et progression des lots. (AC1–3, AC8)
- [ ] T5 — Étendre `Project.to_dict/from_dict` et la persistance existante avec
  `strict_ontology`, transmettre cette préférence aux constructions futures et
  mettre à jour la politique effective d’un graphe existant. (AC4)
- [ ] T6 — Ajouter le service métier de gestion de politique et les deux routes
  de projet, enregistrer le blueprint dans l’application ; conserver les routes
  historiques sous `/api/graph/project/...`. (AC5, AC7)
- [ ] T7 — Construire table de conformité, tests API, persistance, lots, absence
  d’ontologie, concurrence ciblée et régressions de lecture. (AC1–9)
- [ ] T8 — Exécuter la suite et les contrôles sous Docker, consigner la preuve
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

Ticket préparé le **12 octobre 2026**, après clôture de 007-1. Analyse du PRD,
de l’architecture et des chemins des deux stores ; écarts relevés intégrés au
cadrage. Revue de l’implémentation à effectuer après développement.

## Notes de complétion

Rédaction du ticket terminée ; aucune implémentation de 007-2 effectuée.
L’étude demandée est terminée : **Graphiti démontré, C2 Zep non démontré**.
Le prérequis commun reste ouvert et la story passe en `blocked` avant
implémentation. Aucun critère d’acceptation n’a été affaibli.
Décision et voies de sortie : ADR 0015 et `faisabilite-007-2.md`.
Les résultats de C2, les commandes exécutées et les divergences du plan seront
consignés ici à la clôture, après revue.
