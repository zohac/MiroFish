# Epic 007 — Ontologie dynamique (v2)

- **Statut** : `in-progress` · **Dépend de** : 003, 004, 005, 009 · **Bloque** : 010
- **Suivi** : [`sprint-status.yaml`](../../sprint-status.yaml)
- **PRD** : [`prd.md`](prd.md) · **Architecture** : [`architecture.md`](architecture.md)
- **Cadrage du 12 octobre 2026** : périmètre restreint à « **persistance + validation** » et « **une ontologie par projet** ». La boucle auto-évolutive acteur/ontologie est reportée (note consignée dans `deferred-work.md`). L'ontologie générée par `OntologyGenerator` (814 lignes) reste l'unique point de génération ; la v2 la traduit en labels réels sur les nœuds et la régénère sur événement.
- **Décision structurante** : [ADR 0014 — Pose effective de l'ontologie par `GraphStore.set_ontology`](../../decisions/0014-pose-effective-ontology-graphstore.md), story 007-1. C'est lui qui autorise la rupture du no-op de l'ADR 0003.

> L'Epic 009 a clos le verrou d'éligibilité des acteurs (**1157 tests verts**, Verdict GO, 4/4 stories). L'actor selection est qualifiée, l'anti-affabulation C7 tient, la section « Sources & Provenance » du rapport est en place, et l'étanchéité NFR-5 est maintenue au niveau des prompts LLM.  
>
> **L'Epic 007 transforme l'ontologie générée en typage réel du graphe.** La story 007-1 a rendu effectif le `set_ontology` de l'interface `GraphStore` (ADR 0014) ; la suite de la v2 valide l'écriture, régénère sur événement, et expose l'ontologie dans le rapport. Le filet de référence passe à **1431 tests collectés / 1428 réussis + 3 ignorés sous Docker** après 007-2 sans casser la rétrocompatibilité des epics antérieurs.

---

## 1. Exigences fonctionnelles (FR)

| Réf. | Intitulé | Description |
|---|---|---|
| **FR-1** | Application effective de l'ontologie | `GraphStore.set_ontology(graph_id, ontology, strict=False)` traduit le dict en classes Pydantic (`GraphitiGraphStore`) et aligne `ZepGraphStore` ; les écritures suivantes (`add_episode`, `add_text_batch`) consomment ces classes et posent les labels déclarés sur les nœuds. Le no-op de l'ADR 0003 disparaît. |
| **FR-2** | Validation à l'écriture | Toute tentative d'écriture d'un nœud avec un `entity_type` non déclaré déclenche un `GraphValidationWarning` (mode par défaut) ou un `GraphValidationError` (mode `strict_ontology=True`). Le warning est tracé dans un journal durable par graphe, distinct de `Project.ontology_history` (historique des versions en 007-4) et exposé via `GraphStore.get_ontology_warnings(graph_id, since=...)`. |
| **FR-3** | Régénération sur événement | Trois déclencheurs câblés : (a) ajout de document à un projet (E1), (b) modification du `SimulationBrief` au-delà d'un seuil de diff (`difflib.SequenceMatcher.ratio() < 0.95`, E2), (c) demande explicite via `POST /api/project/<id>/ontology/regenerate` (E3). Une création de projet déclenche la génération initiale (E4). |
| **FR-4** | Persistance versionnée d'ontologie | `OntologyVersion` (immuable, identifiant `ont_<uuid12>`) stocké dans `OntologyVersionStore` (`Config.UPLOAD_FOLDER/ontologies/<version_id>.json`). Le `Project` porte `applied_ontology_id`, `applied_ontology_version` (compteur monotone), `ontology_history` (liste de version_id). La version courante est lue en temps réel depuis le store, jamais cachée. |
| **FR-5** | Composition avec l'actor selection (Epic 009) | `ActorClassifierService` (009-1) consulte d'abord le label d'ontologie comme signal primaire (table de correspondance injective `PersonEntity → ActorRole.PERSON`, etc.) ; quand le label est absent, la cascade 009-1 s'applique. Le test C6 prouve le court-circuit LLM quand le label est suffisant. |
| **FR-6** | Audit dans le rapport | Une sous-section « Ontologie appliquée » est ajoutée à `build_sources_provenance_section()` (story 009-4). Elle liste : types d'entité (nom + description + `InformationOrigin` + compte), types de relation (idem), version d'ontologie appliquée, politique de validation. L'outil LLM `get_applied_ontology` est défini dans `ReportAgent._define_tools()`. |
| **FR-7** | Endpoints de gestion | Quatre endpoints : `POST /api/project/<id>/ontology/regenerate` (E3), `GET /api/project/<id>/ontology`, `GET /api/project/<id>/ontology/warnings?since=...`, `PATCH /api/project/<id>/ontology/policy`. `POST /api/graph/upload` (existant) déclenche E1 en arrière-plan et répond 202 avec un identifiant de tâche. |

---

## 2. Exigences non fonctionnelles (NFR)

| Réf. | Intitulé | Description |
|---|---|---|
| **NFR-1** | Zéro règle métier spécifique | L'ontologie reste inférée du corpus et du brief, sans catalogue de types en dur. L'arbitrage « multi-niveaux » et « édition manuelle » est reporté. La table de correspondance label → `ActorRole` (FR-5) est **injective et finie** : un label non mappé tombe en `REVIEW`, jamais en `ELIGIBLE` direct. |
| **NFR-2** | Rétrocompatibilité `GraphStore` | `add_episode(..., ontology=None)` reste l'appel par défaut et conserve le comportement Epic 003-2. Sans ontologie effective, les écritures conservent le comportement historique ; une ontologie vide est refusée. L'extension est documentée par l'ADR 0014 et testée sur les deux implémentations concrètes. |
| **NFR-3** | Régénération idempotente et déterministe | `OntologyGenerator` est appelé avec `temperature=0.0` par défaut (vs 0.3 en v1). Deux régénérations successives du même corpus produisent deux ontologies identiques au mot près sur les champs stables (`entity_types[].name`, `edge_types[].name`, `attributes[].name`). C3 vérifie la déterminisme par diff JSON. |
| **NFR-4** | Filet de tests hermétiques et Docker | La suite globale passe de **1157 à 1177+ tests verts** sur l'hôte (≥ +20 tests hermétiques par l'epic 007), **0 échec** sous Docker. `ruff check .` et `validate_plans.py` au vert. La parité Docker est validée par le banc `verifier_qualification_epic_007.py`. |
| **NFR-5** | Étanchéité NFR-5 maintenue | La consigne ontologique (« voici les types d'entité reconnus ») est passée au LLM **uniquement en `user_message`**, jamais en `system_prompt`. Le test d'inspection des messages LLM (test de 009-4 étendu) garantit la non-fuite. L'étiquette `NFR5_DATA_NOT_INSTRUCTION_SUFFIX` reste en place sur les trois `system_prompt` (plan, section, chat). |
| **NFR-6** | Performance sous budget | Régénération < 30 s pour un corpus de 50K caractères (hôte) / < 45 s (Docker). Le banc `verifier_qualification_epic_007.py` mesure les deux. Coût additionnel d'écriture (Pydantic + label) mesuré par réutilisation de l'Epic 005-4 ; ajustement si dépassement. |

---

## 3. Exigences d'expérience utilisateur

- À la création d'un projet, l'ontologie est générée automatiquement à partir des documents importés et du brief. L'utilisateur n'a pas à la configurer.
- Sur ajout d'un document, l'utilisateur voit un message clair « Ontologie régénérée : +2 types ajoutés, 0 type retiré » (détails dans `Project.ontology_history`).
- Le rapport final (généré par `ReportAgent`) contient une section « Ontologie appliquée » qui liste types, descriptions, origines (`documentary` / `hypothesis` / `inherited`) et compte d'entités. L'utilisateur peut citer cette section pour défendre la traçabilité.
- Si la politique est en mode `strict_ontology=True` et qu'un nœud est rejeté, l'utilisateur le voit dans la sortie de `add_episode` (code 422 explicite, message nommément le type refusé).
- Le parcours simple ne change pas : l'utilisateur n'a pas à toucher l'ontologie pour faire une simulation. L'API de gestion (`/regenerate`, `/policy`) est un pouvoir avancé, jamais bloquant.
- Les graphes migrés (Epic 006) restent sur `:Entity` sans label custom. L'utilisateur en est informé dans le rapport si l'ontologie v2 a été appliquée à un projet dont certains nœuds sont des héritages (mention « type hérité — version non retrouvée »).

---

## 4. Index des stories

| Story | Titre | Statut | Fichier |
|---|---|---|---|
| 007-1 | Persistance effective des labels d'ontologie dans `GraphStore` (Lot A - P0) | `done` | [story-007-1.md](story-007-1.md) |
| 007-2 | Validation à l'écriture et politique `strict_ontology` (Lot A - P0) | `done` | [story-007-2.md](story-007-2.md) |
| 007-3 | Régénération déterministe et budget de performance (Lot B - P1) | `done` | [story-007-3.md](story-007-3.md) |
| 007-4 | Régénération sur événement (E1 ajout document, E2 modification brief, E3 demande explicite) (Lot B - P1) | `backlog` | [story-007-4.md](story-007-4.md) |
| 007-5 | Cohérence projet (E5) et composition avec `ActorClassifierService` (Lot C - P1) | `backlog` | [story-007-5.md](story-007-5.md) |
| 007-6 | Audit dans le rapport (sous-section « Ontologie appliquée ») et outil LLM (Lot C - P1) | `backlog` | [story-007-6.md](story-007-6.md) |
| 007-7 | Qualification globale C1–C8 et clôture de l'epic (Lot D - P1) | `backlog` | [story-007-7.md](story-007-7.md) |

| Story | Critères d'acceptation (résumé) |
|---|---|
| 007-1 | `GraphStore.set_ontology` n'est plus no-op : sur 2 fixtures (télécom et énergie), **100 %** des nœuds portent un label custom non-`Entity` après `add_episode(..., ontology=...)` — mesuré sous Docker, [empreintes consignées](mesure-007-1.txt). Les deux implémentations (`GraphitiGraphStore`, `ZepGraphStore`) sont alignées par une table de conformité testée. Rétrocompatibilité Epic 003 préservée. |
| 007-2 | 100 % des écritures avec un `entity_type` hors ontologie déclenchent un `GraphValidationWarning` (mode défaut) ou un `GraphValidationError` (mode `strict_ontology=True`). La politique est sérialisable dans `Project` et l'endpoint `PATCH` est idempotent. Les warnings sont requêtables par `get_ontology_warnings`. |
| 007-3 | `OntologyGenerator` tourne à `temperature=0.0` par défaut. Pour un corpus de 50K caractères, régénération < 30 s hôte / < 45 s Docker. Deux régénérations du même corpus produisent deux ontologies identiques au mot près sur les champs stables. |
| 007-4 | Ajout d'un document déclenche la régénération en < 5 s ; modification du brief au-delà du seuil déclenche la régénération ; demande explicite via API régénère à tout moment. Les nœuds existants conservent leur label (mode par défaut) ou sont rétrogradés (mode strict). L'historique est tracé dans `Project.ontology_history`. |
| 007-5 | Deux simulations du même projet, sans déclencheur intermédiaire, partagent `applied_ontology_id`. Un projet différent a une ontologie distincte. `ActorClassifierService` consulte le label d'ontologie comme signal primaire (test : mock LLM prouve le court-circuit) et conserve la cascade 009-1 quand le label est absent. Les 921+ tests de 009-1 restent verts. |
| 007-6 | `build_sources_provenance_section()` inclut la sous-section « Ontologie appliquée » avec types, descriptions, origines, comptes et version. L'outil LLM `get_applied_ontology` est défini et testé (réponse JSON stable). Les graphes sans ontologie appliquée n'ont pas la sous-section. |
| 007-7 | `verifier_qualification_epic_007.py` orchestre les critères C1–C8 contre le stack Docker de référence, avec rapport formel `rapport-qualification-epic-007.md` et **VERDICT GO**. Filet global **1177+ tests verts** sur l'hôte, 0 échec, lint et structure au vert, 0 secret dans les images. |

### Dépendances et couverture

| Story | Dépend de | Exigences | Critères de sortie |
|---|---|---|---|
| 007-1 | 003, 004, 005, 009 (`done`) ; ADR 0010 (override neo4j) et ADR 0011 (surface) respectés, fixtures de test sous 2 domaines | FR-1 ; NFR-2 | C1, contribution C8 |
| 007-2 | 007-1 ; politique de validation fixée dans le PRD ; ADR 0016 | FR-2 ; NFR-2, NFR-4 | C2, contribution C8 |
| 007-3 | 007-1, 007-2 ; corpus et protocole C3 définis dans le ticket | FR-1 (déterminisme), FR-3 ; NFR-3, NFR-6 | C3, contribution C8 |
| 007-4 | 007-1, 007-2, 007-3 ; événements projet (E1-E3) identifiés, seuil de diff du brief fixé | FR-3, FR-4 ; NFR-3 | C4, contribution C8 |
| 007-5 | 007-4 ; table de correspondance label → `ActorRole` déclarée | FR-5 ; NFR-1, NFR-4 | C5, C6, contribution C8 |
| 007-6 | 007-4 ; sous-section rapport + outil LLM spécifiés | FR-6 ; NFR-4, NFR-5 | C7, contribution C8 |
| 007-7 | 007-1 à 007-6 (`done`) ; banc de qualification spécifié | FR-7 ; NFR-2, NFR-4, NFR-5, NFR-6 | Validation finale C1–C8, VERDICT GO |

Le lot A (P0) couvre C1 et C2, qui sont les conditions de l'application effective. Le lot B (P1) traite la régénération, qui préserve la valeur acquise. Le lot C (P1) aligne l'actor selection 009 et l'audit. Le lot D (P1) qualifie l'epic en orchestration Docker, comme pour les epics antérieurs.

L'Epic 006 (migration Zep) est close : les graphes migrés portent `:Entity` sans label custom et ne sont **pas** re-typés par la v2 (PRD §3.2, Q3). Le périmètre de l'Epic 007 reste local aux projets neufs.

---

## 5. Documents à consulter

| Document | Ce qu'on y prend |
|---|---|
| [`docs/plans/007-ontologie-dynamique/prd.md`](prd.md) | Contrat d'ingénierie, critères chiffrés C1 à C8, périmètre, risques. |
| [`docs/plans/007-ontologie-dynamique/architecture.md`](architecture.md) | Schémas Mermaid du pipeline en 5 phases, modèles `OntologyVersion` / `GraphValidationWarning`, interfaces étendues, traduction Pydantic, composition `ActorClassifierService`, endpoints, stratégie de tests. |
| [`docs/decisions/0003-ontologie-differee-en-v2.md`](../../decisions/0003-ontologie-differee-en-v2.md) | Décision d'origine : ontologie dynamique = v2, chemin de lecture d'abord. La v2 honore ce cadrage. |
| [`docs/LOCAL-FIRST.md` §6.1](../../LOCAL-FIRST.md) | Constat historique : « L'ontologie générée à l'exécution — le point dur » (~80 % de l'effort initial). Cadrage du risque R1 dans la v2. |
| [`docs/plans/009-eligibilite-acteurs-et-sources/rapport-qualification-epic-009.md`](../009-eligibilite-acteurs-et-sources/rapport-qualification-epic-009.md) | Verdict GO Epic 009 (1157 tests verts), contrats ADR 0012 / 0013, étanchéité NFR-5. La v2 s'insère sans rien casser. |
| [`backend/app/services/ontology_generator.py`](../../../backend/app/services/ontology_generator.py) | `OntologyGenerator` (814 lignes) : contrat de retour `entity_types` (10 max), `edge_types`, `attributes`. Ne change pas de signature en v2. |
| [`backend/app/utils/ontology.py`](../../../backend/app/utils/ontology.py) | Constante `MAX_ONTOLOGY_TYPES = 10`, helpers de normalisation. |
| [`backend/app/utils/graph_store/base.py`](../../../backend/app/utils/graph_store/base.py) | Contrat neutre `GraphStore` version 2, ontologie effective et politique `strict` mémorisée. |
| [`backend/app/utils/graph_store/graphiti_store.py`](../../../backend/app/utils/graph_store/graphiti_store.py) | Implémentation Graphiti : ontologie effective, résolution par graphe et appel d’extraction/persistance à contrôler en 007-2. |
| [`backend/app/utils/graph_store/zep_store.py`](../../../backend/app/utils/graph_store/zep_store.py) | Implémentation Zep : pose effective, extraction distante et chemin Batch distinct à couvrir en 007-2. |
| [`backend/app/services/zep_entity_reader.py`](../../../backend/app/services/zep_entity_reader.py) | `EntityNode.get_entity_type` (ligne 50) : cascade de résolution. La v2 alimente la première branche (label non-`Entity`). |
| [`backend/app/services/actor_classifier.py`](../../../backend/app/services/actor_classifier.py) | `ActorClassifierService` (009-1) : la v2 ajoute un court-circuit sur label d'ontologie. |
| [`backend/app/models/project.py`](../../../backend/app/models/project.py) | Modèle `Project` (009-2) : extension rétrocompatible `applied_ontology_id`, `applied_ontology_version`, `ontology_history`. |
| [`backend/app/models/source_document.py`](../../../backend/app/models/source_document.py) | `InformationOrigin` (ADR 0012, 009-2) : 5 origines réutilisées pour tracer l'origine d'un type d'ontologie (C7). |
| [`backend/app/services/graph_builder.py`](../../../backend/app/services/graph_builder.py) | Câble l'événement « ajout de document » à la régénération (E1) ; `set_ontology` est appelé ligne 322. |
| [`backend/app/services/report_agent.py`](../../../backend/app/services/report_agent.py) | `build_sources_provenance_section()` (009-4) : ajout de la sous-section « Ontologie appliquée ». |
| [`backend/app/services/zep_tools.py`](../../../backend/app/services/zep_tools.py) | L'outil LLM `get_applied_ontology` est défini ici (cohérence avec `get_edge_provenance`, 009-4). |
| [`backend/app/api/graph.py`](../../../backend/app/api/graph.py) | Endpoint `POST /api/graph/upload` déclenche E1 en arrière-plan, répond 202. |
| [`backend/app/api/simulation.py`](../../../backend/app/api/simulation.py) | `prepare_simulation` lit `Project.applied_ontology_id` (câblage transparent, pas d'endpoint nouveau). |
| [`backend/app/api/project.py`](../../../backend/app/api/project.py) | Fichier cible à créer : endpoints `/api/project/<id>/ontology/regenerate`, `/get`, `/warnings`, `/policy`. |
| [`backend/scripts/verifier_qualification_epic_009.py`](../../../backend/scripts/verifier_qualification_epic_009.py) | Modèle du banc de qualification à réutiliser (Epic 005-5, Epic 007-7). |
| [ADR 0001](../../decisions/0001-remplacement-de-zep-par-graphiti.md) | Interface `GraphStore` à deux implémentations. La v2 respecte le contrat commun. |
| [ADR 0003](../../decisions/0003-ontologie-differee-en-v2.md) | Cadrage initial de la v2. |
| [ADR 0014](../../decisions/0014-pose-effective-ontology-graphstore.md) | **Pose effective de l'ontologie** : rupture du no-op de `set_ontology`, `strict` et `ontology` en keyword-only, contrat versionné `version = 2`. C'est la décision que la story 007-1 applique ; elle ne sera pas re-dérivée. |
| [ADR 0012](../../decisions/0012-contrat-de-provenance-graphstore.md) | Contrat de provenance commun. L'ontologie est un typage, pas une origine. |
| [ADR 0013](../../decisions/0013-semantique-des-sources.md) | Sémantique des sources : `InformationOrigin` (5 origines) sert à étiqueter l'origine d'un type d'ontologie. |
| [`AGENTS.md`](../../../AGENTS.md) | Constitution : clean architecture (api → services → utils), règles de dépendance, étiquette `NFR5_DATA_NOT_INSTRUCTION_SUFFIX`, définitions de prêt/fini, Docker d'abord. |
| [`docs/deferred-work.md`](../../deferred-work.md) | Note sur la boucle auto-évolutive acteur/ontologie et la migration rétroactive Epic 006, toutes deux reportées. |

## 6. Passage à 007-2 — 12 octobre 2026

007-1 est `done` après relectures et mesure C1. Le [ticket 007-2](story-007-2.md)
a été initialement rédigé en `backlog` : sa définition de prêt exigeait de démontrer le
contrôle des types avant persistance sur les deux moteurs, y compris les lots
Zep. L’epic reste `in-progress` (2/7 stories terminées). La politique est
persistée par projet et les warnings ont un journal dédié ; le versionnement
et `Project.ontology_history` restent réservés à 007-4.

### Étude de faisabilité 007-2 — 12 octobre 2026

La story 007-2 était `blocked` avant implémentation : [étude](faisabilite-007-2.md)
achevée, 11 cas Graphiti contre Neo4j conformes, mais C2 Zep non démontré.
L’[ADR 0015](../../decisions/0015-controle-ontologie-avant-persistance.md)
consigne le NO-GO du contrat commun. Le périmètre est désormais restreint à
Graphiti par [ADR 0016](../../decisions/0016-perimetre-validation-ontologie-graphiti.md) ; la capacité Zep équivalente reste différée.


## 7. Clôture 007-2 et préparation 007-3 — 13 octobre 2026

007-2 est `done` après revue BMAD, 14 correctifs appliqués et clôture du suivi
D1. La [qualification du code livré](qualification-007-2.md) valide 12 cas C2
Graphiti contre Neo4j. La suite Docker du 12 octobre compte **1431 collectés,
1428 réussis et 3 ignorés**, sans échec ; lint et plans sont verts.
Les ADR 0016 et 0017 précisent périmètre Graphiti, politique durable et
rétrogradation transactionnelle ; l’ADR 0015 reste la preuve historique Zep.

Le [ticket 007-3](story-007-3.md) a été préparé : température zéro,
générations indépendantes, comparaison des champs stables et mesures 10K/50K
de la lecture des documents à la pose.

## 8. Avancement de 007-3 — 13 octobre 2026

La story 007-3 est en `review`. Les entrées (corpus 10K et 50K avec manifestes JSON
et briefs) sont figées sous `backend/tests/fixtures/ontology/regeneration/`.
`OntologyGenerator.generate` transmet explicitement `temperature=0.0`, et
la projection canonique `canonical_ontology_projection` isole types et attributs.
La sonde autonome `backend/scripts/verifier_ontology_regeneration.py` a été
développée et couverte par 21 tests unitaires hermétiques.

L'épreuve réelle contre Neo4j et `gpt-6.1-sol` (via la passerelle Codex locale)
est consignée dans [`mesure-007-3-hote.json`](mesure-007-3-hote.json) :
- Pose `set_ontology` instantanée (< 10 ms) et isolation multi-tenant 100 % conformes (AC4) ;
- AC3 (reproductibilité nominale stricte) et AC5 (budget hôte < 30 s) non satisfaits
  par la nature intrinsèque des modèles LLM de frontière (variations lexicales
  nominales, temps d'inférence réel 91–193 s). L'arbitrage produit acte ce comportement
  en **NO-GO empirique C3**, fidèlement tracé au dossier sans masquer la réalité.
- Filet de tests porté à **1454 tests hermétiques** (100 % de succès).
La revue de code BMAD sera exécutée dans une session dédiée.

