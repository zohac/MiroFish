---
id: "007-4"
epic: "007"
titre: "Régénération sur événement (E1 ajout document, E2 modification brief, E3 demande explicite)"
statut: done
auteur: "Simon"
format: "2"
---

# Story 007-4 — Régénération sur événement (E1 ajout document, E2 modification brief, E3 demande explicite)

En tant qu’utilisateur de MiroFish, je veux que l’ontologie de mon projet soit
automatiquement réévaluée lors de l'ajout de nouveaux documents ou de la
modification substantielle du brief de simulation, ou à la demande via l'API, afin
que le graphe de connaissances reflète l'évolution du corpus sans écraser ni
dégrader les données déjà acquises.

**Lot B — P1.** Exigences : FR-3, FR-4, FR-7 (partiel) ; NFR-2, NFR-3 ; contribution aux critères C4, C5 et C8.
Dépendances : 007-1, 007-2 et 007-3 terminées (`done`).
Cette story implémente le modèle immuable `OntologyVersion`, le magasin `OntologyVersionStore`,
l'extension du `Project` (`applied_ontology_id`, `applied_ontology_version`, `ontology_history`),
la détection de diff sémantique du brief (`SequenceMatcher`), les déclencheurs d'événements
E1, E2, E3 (et initialisation E4), ainsi que les endpoints de régénération et de consultation.

## Définition de prêt

- [x] PRD §3.1/§4/C4, architecture §2/§5/§8/§9, epic-007 §1/§4 et constitution consultés.
- [x] Stories 007-1 (pose effective), 007-2 (validation et politique durable) et 007-3 (régénération déterministe `temperature=0.0`, projection canonique, sonde C3) terminées et validées.
- [x] Modèles existants analysés : `Project` (`app/models/project.py`), `SimulationBrief` (`app/models/simulation_brief.py`), `SourceDocument` (`app/models/source_document.py`).
- [x] Invariants du PRD et de l'architecture identifiés : `OntologyVersion` immuable avec identifiant `ont_<uuid12>`, non-destruction des labels existants sur les nœuds déjà écrits, seuil de diff du brief `difflib.SequenceMatcher.ratio() < 0.95`.
- [x] Endpoints cible définis : `POST /api/project/<id>/ontology/regenerate` (E3), `GET /api/project/<id>/ontology`, et déclencheur E1 branché sur l'ajout de document.
- [x] Avant implémentation : valider les scénarios de test d'événements E1, E2 et E3 avec mocks LLM hermétiques, et concevoir la sonde ou le test d'intégration pour mesurer la régénération sur ajout de document (C4).

### Critères d’acceptation

| Réf. | Contrat mesurable | Vérification |
|---|---|---|
| AC1 | Modèle `OntologyVersion` (`version_id` `ont_<uuid12>`, `project_id`, `entity_types: Tuple`, `edge_types: Tuple`, `created_at` ISO 8601 UTC, `source_summary`, `parent_version_id`) et magasin `OntologyVersionStore` (`create`, `get`, `list_for_project`). Les types d'entité et de relation sont représentés par des dataclasses immutables (`OntologyEntityType`, `OntologyEdgeType`). La persistance repose sur des fichiers JSON immuables sous `Config.UPLOAD_FOLDER/ontologies/<version_id>.json` avec index projet. | Tests unitaires hermétiques validant immutabilité, sérialisation JSON round-trip, génération d'identifiant `ont_<uuid12>` déterministe ou aléatoire sécurisé, et isolation des répertoires de test. |
| AC2 | Le modèle `Project` (`app/models/project.py`) gagne trois champs rétrocompatibles : `applied_ontology_id: Optional[str] = None`, `applied_ontology_version: int = 0`, `ontology_history: List[str] = field(default_factory=list)`. La méthode `apply_ontology(version)` incrémente le compteur monotone, met à jour l'ID courant et alimente l'historique. La méthode `get_applied_ontology()` relit la version courante depuis `OntologyVersionStore`. La désérialisation de projets existants préserve ces valeurs par défaut sans régression. | Tests unitaires vérifiant l'application successive de versions, la monotonicité de `applied_ontology_version`, la relecture exacte et la non-régression sur les fixtures JSON de projets de l'Epic 009. |
| AC3 | Événement E1 (Ajout de document) : lorsqu'un nouveau document est ajouté à un projet dont l'ontologie est déjà initialisée, la régénération est déclenchée avec le corpus cumulé et le brief courant (`OntologyGenerator.generate(temperature=0.0)`). Une nouvelle `OntologyVersion` fille est stockée et appliquée au graphe via `GraphStore.set_ontology`. Les nœuds préexistants dans Neo4j conservent leur label sans altération ; les nouveaux nœuds issus du document ajouté portent les labels de la nouvelle version (C4). | Test d'intégration / composant avec graphe mocké ou Neo4j : injection d'un document 1, vérification des labels posés, ajout d'un document 2 déclenchant E1, vérification que les labels du document 1 sont préservés et que les nœuds du document 2 portent la nouvelle ontologie. |
| AC4 | Événement E2 (Modification du brief) : la modification du brief de simulation compare l'ancien et le nouveau texte via `difflib.SequenceMatcher.ratio()`. Si le ratio est $\ge 0.95$ (retouche mineure, correction typographique), aucune régénération LLM n'est déclenchée. Si le ratio est $< 0.95$ (changement sémantique substantiel), l'événement E2 déclenche la régénération de l'ontologie, la création d'une nouvelle `OntologyVersion` fille et la mise à jour du projet. | Tests unitaires avec paires de briefs à ratio $\ge 0.95$ (0 appel régénération, version inchangée) et ratio $< 0.95$ (régénération déclenchée, version incrémentée). |
| AC5 | Événement E3 (Demande explicite) : l'endpoint `POST /api/project/<project_id>/ontology/regenerate` force la régénération immédiate de l'ontologie à partir des documents et du brief du projet. Il répond HTTP 200 avec la sérialisation de la nouvelle `OntologyVersion`, HTTP 404 si le projet est introuvable, HTTP 409 si une ingestion/régénération est déjà en cours, et HTTP 422 si l'ontologie générée est invalide. | Tests d'API Flask (client de test) couvrant les codes 200, 404, 409 (concurrence) et 422 (validation Pydantic échouée). |
| AC6 | Consultation et contextualisation (FR-7) : l'endpoint `GET /api/project/<project_id>/ontology` retourne la version courante de l'ontologie (HTTP 200) ou 404 si aucune ontologie n'est appliquée. Les avertissements `GraphValidationWarning` (007-2) sont rattachés à `applied_ontology_id` lors de leur émission pour tracer la version active. | Tests d'API vérifiant le format JSON retourné, la gestion du 404 pour projet neuf sans ontologie, et la présence de `applied_ontology_id` dans les métadonnées de warning. |
| AC7 | Événement E4 (Initialisation à la création) : lors de la création d'un projet (`POST /api/graph/ontology/generate` ou factory de projet), la première version `OntologyVersion` (v1, `parent_version_id=None`) est enregistrée dans `OntologyVersionStore`, et le projet est initialisé avec `applied_ontology_version=1` et `ontology_history=[version_id]`. | Tests unitaires et d'API vérifiant la création atomique de la version initiale v1 lors de l'appel existant de génération initiale. |
| AC8 | Au moins **25 nouveaux tests hermétiques** ajoutés ; le filet global de tests progresse de **1459 à 1484+ tests verts** sur l'hôte, 0 régression. `ruff check .` et `validate_plans.py` strictement conformes. | Exécution complète de la suite pytest, linting ruff sans violation et validation des plans validée. |

## Définition de fini

- [x] AC1–AC8 satisfaits avec preuves de tests unitaires et d'intégration hermétiques associées.
- [x] Modèles `OntologyVersion`, `OntologyEntityType`, `OntologyEdgeType` et magasin `OntologyVersionStore` implémentés et testés sans résidu hors du dossier temporaire de test.
- [x] Modèle `Project` enrichi avec `applied_ontology_id`, `applied_ontology_version`, `ontology_history`, rétrocompatibilité validée sur les projets existants.
- [x] Déclencheurs d'événements E1 (ajout doc), E2 (diff brief < 0.95), E3 (API POST) et E4 (création) implémentés avec isolation et gestion d'erreurs.
- [x] Préservation stricte des labels des nœuds existants lors d'une régénération prouvée par test (non-régression C4).
- [x] Endpoints Flask `POST /api/project/<id>/ontology/regenerate` et `GET /api/project/<id>/ontology` opérationnels et testés.
- [x] Filet global $\ge 1484$ tests verts sur l'hôte, `ruff check .` propre, `validate_plans.py` conforme.
- [x] Revue de code adverse BMAD 4 couches effectuée et patches traités.
- [x] Notes de complétion rédigées, suivi `sprint-status.yaml`, `STATUS.md` et `epic-007.md` actualisés.

## Tâches

- [x] T1 — Modèles de données `OntologyVersion`, `OntologyEntityType`, `OntologyEdgeType` et tests unitaires (AC1).
  Définir les dataclasses immutables dans `backend/app/models/ontology_version.py` avec validation des types, longueurs et contraintes (au plus 10 types d'entité).
- [x] T2 — Magasin `OntologyVersionStore` avec persistance JSON et index projet (AC1).
  Implémenter `OntologyVersionStore` dans `backend/app/models/ontology_version.py` (ou `services/`) assurant écriture atomique (fichier temporaire + rename), relecture et indexation par `project_id`.
- [x] T3 — Extension du modèle `Project` et méthodes d'ontologie (AC2).
  Ajouter `applied_ontology_id`, `applied_ontology_version`, `ontology_history`, `apply_ontology()` et `get_applied_ontology()` dans `backend/app/models/project.py`. Assurer la rétrocompatibilité `from_dict`/`to_dict`.
- [x] T4 — Détection de modification du brief (E2) avec seuil `SequenceMatcher` (AC4).
  Créer le helper de comparaison de brief dans `backend/app/services/ontology_events.py` (ou `ontology_policy.py`), calculant le ratio de similarité textuelle et déclenchant la régénération si `ratio < 0.95`.
- [x] T5 — Câblage de l'événement E1 (Ajout de document) et préservation des labels (AC3, C4).
  Brancher l'ajout de document sur le recalcul de l'ontologie cumulée, la création de version fille et la mise à jour du `GraphStore`, en vérifiant la préservation des nœuds existants.
- [x] T6 — Câblage de l'événement E4 (Génération initiale de projet) (AC7).
  Intégrer la création de la version v1 dans la route existante `POST /api/graph/ontology/generate` et la sauvegarde du projet.
- [x] T7 — Endpoints d'API `POST /regenerate` et `GET /ontology` dans `app/api/project.py` (AC5, AC6).
  Ajouter les routes avec gestion des codes HTTP (200, 404, 409, 422) et validation des autorisations / états de tâche.
- [x] T8 — Rattachement de la version d'ontologie aux `GraphValidationWarning` (AC6).
  Associer `applied_ontology_id` lors de la journalisation des warnings de validation pour une traçabilité audit complète.
- [x] T9 — Tests unitaires, intégration et validation de non-régression globale (AC8).
  Écrire les suites de tests hermétiques dans `tests/test_ontology_version.py` et `tests/test_ontology_events.py`, vérifier les 1484+ tests, lint et validateur de plans.

## Notes de développement

### Architecture et flux des événements

L'architecture respecte les couches de dépendance strictes (AGENTS.md §2.1) :
```
app/api/project.py  -->  app/services/ontology_events.py  -->  app/models/ontology_version.py
                     -->  app/models/project.py
```

1. **Cycle de vie d'une version d'ontologie** :
   - Une version d'ontologie (`OntologyVersion`) est créée avec un identifiant de type `ont_<uuid12>`.
   - Elle contient les tuples figés d'`OntologyEntityType` et d'`OntologyEdgeType`, ainsi que le `parent_version_id` (permettant de retracer l'arbre des évolutions sans stocker un diff complexe).
   - Les fichiers JSON sont stockés sous `Config.UPLOAD_FOLDER / "ontologies" / f"{version_id}.json"`.
   - `OntologyVersionStore` utilise une écriture atomique (écriture dans un `.tmp` puis `os.replace`) pour prévenir toute corruption en cas d'interruption.

2. **Événements E1 à E4** :
   - **E1 (Ajout document)** : lorsqu'un fichier est ajouté, `GraphBuilderService` ou le service de gestion de projet réévalue le corpus global (tous les documents du projet) avec `OntologyGenerator.generate(temperature=0.0)`. L'ontologie résultante est enregistrée en version $N+1$ avec `parent_version_id = version_N.version_id`. La pose `store.set_ontology()` est appelée. Les nœuds existants conservent leur label Cypher dans Neo4j (non destructif, pas de `REMOVE`).
   - **E2 (Modification brief)** : lors de la mise à jour du brief (`simulation_requirement` ou `SimulationBrief`), `difflib.SequenceMatcher(None, brief_precedent, brief_nouveau).ratio()` est évalué. Si `ratio >= 0.95`, l'événement est ignoré. Si `ratio < 0.95`, une nouvelle version est générée et appliquée.
   - **E3 (Demande explicite)** : `POST /api/project/<project_id>/ontology/regenerate` déclenche la régénération forcée indépendamment du brief ou des documents. Si le projet est déjà en état `GRAPH_BUILDING`, un code 409 Conflict est retourné.
   - **E4 (Création)** : initialisation à la création de projet (`POST /api/graph/ontology/generate`), version initiale v1 (`parent_version_id=None`).

3. **Préservation des données et non-régression** :
   - Conformément à l'arbitrage du PRD (§3.2, Q3) et de l'architecture (§5.2), la régénération ne re-touche pas aux nœuds existants. Les nouveaux épisodes ingérés héritent de la nouvelle ontologie.
   - Si la politique du projet est `strict_ontology=True`, les futures écritures de nœuds hors de la nouvelle ontologie seront refusées, mais les anciens nœuds demeurent intacts.

4. **Commandes de validation locale** :
```bash
cd backend && uv run pytest tests/ -q
cd backend && uv run ruff check .
cd backend && uv run python scripts/validate_plans.py
```

## Revue

Revue contradictoire BMAD à 4 couches réalisée le **14 octobre 2026** sur la branche `local-first` :
- **Couche 1 : blind-hunter** :
  - Vérification de l'étanchéité des écritures disque : `OntologyVersionStore` utilise un fichier temporaire unique (`.tmp`) suivi de `os.replace` atomique.
  - Résilience de l'index projet : la corruption éventuelle du JSON d'index est interceptée avec reconstruction/retour défensif propre (test `test_ontology_version_store_index_resilience`).
  - Validation des formats d'identifiants : `ont_<uuid12>` imposé dès la création et vérifié par regex et validation explicite.
- **Couche 2 : edge-case-hunter** :
  - Concurrence et verrouillage : `project_lock(project_id)` est systématiquement acquis autour des transitions d'ontologie.
  - Briefs vides ou identiques : gestion des cas limites dans `calculate_brief_similarity` (1.0 sur briefs identiques/vides, 0.0 sur vide unilatéral).
  - Validation de la cardinalité : plafond strict à 10 types d'entité (`MAX_ONTOLOGY_TYPES`) validé dans `OntologyVersion.__post_init__`.
  - Intégrité lors d'un échec de régénération : si `OntologyGenerator.generate` échoue, la transaction est annulée et l'ancienne version reste intacte sans corruption de `applied_ontology_id`.
- **Couche 3 : verification-gap** :
  - Préservation des labels existants (C4) : le test `test_e1_document_added_and_c4_label_preservation` prouve formellement que l'ajout d'un document n'écrase ni ne modifie les labels des nœuds existants sur le store.
  - Rattachement de la version aux avertissements (AC6) : `applied_ontology_id` est rattaché aux instances de `GraphValidationWarning` dans `OntologyPolicyService.warnings`.
  - Non-régression totale : 26 nouveaux tests hermétiques ajoutés (`test_ontology_version.py` et `test_ontology_events.py`), suite globale portée de **1459 à 1485 tests passants** (100 % succès).
- **Couche 4 : acceptance-auditor** :
  - 100 % des critères d'acceptation AC1 à AC8 satisfaits.
  - `ruff check .` rigoureusement propre (0 warning, 0 erreur).
  - `validate_plans.py` conforme (9 epics, 39 stories validées).

## Notes de complétion

- **Modèles immuables (`app/models/ontology_version.py`)** :
  - `OntologyEntityType` et `OntologyEdgeType` définis sous forme de dataclasses `frozen=True` avec validation de schéma PascalCase/UPPER_SNAKE_CASE et conversion réversible `from_dict`/`to_dict`.
  - `OntologyVersion` encapsule la version immuable du projet (`ont_<uuid12>`), le chaînage d'ascendance `parent_version_id`, l'horodatage UTC ISO 8601 et la conversion pour `GraphStore.set_ontology`.
  - `OntologyVersionStore` implémente la persistance JSON sous `Config.UPLOAD_FOLDER/ontologies/<version_id>.json` avec indexation atomique multi-projets.
- **Extension de `Project` (`app/models/project.py`)** :
  - Ajout des champs `applied_ontology_id`, `applied_ontology_version` et `ontology_history`.
  - Implémentation des méthodes `apply_ontology` (incrément monotone) et `get_applied_ontology` (relecture en direct depuis le magasin sans cache stale).
  - Rétrocompatibilité garantie sur les projets existants (désérialisation par défaut sûre).
- **Service d'événements (`app/services/ontology_events.py`)** :
  - Helper `calculate_brief_similarity` et seuil `difflib.SequenceMatcher.ratio() < 0.95`.
  - Déclencheurs réactifs : E1 (ajout de document), E2 (diff brief substantiel), E3 (demande explicite API) et E4 (initialisation atomique v1 lors de la création de projet).
  - Application directe sur `GraphStore.set_ontology` garantissant la non-altération des nœuds préexistants.
- **Endpoints API (`app/api/project.py` et `app/api/graph.py`)** :
  - `GET /api/project/<project_id>/ontology` : consultation de la version courante (200 / 404).
  - `POST /api/project/<project_id>/ontology/regenerate` : forçage explicite (200 / 404 / 409 / 422).
  - `POST /api/project/<project_id>/documents` : ajout de document déclenchant E1.
  - `PATCH /api/project/<project_id>/brief` : modification de brief avec régénération conditionnelle E2.
  - `POST /api/graph/ontology/generate` étendu pour initialiser automatiquement la version v1 (E4).
- **Validation globale** :
  - Filet global : **1485 tests verts** sur l'hôte (+26 tests hermétiques).
  - Code linté sans erreur (`ruff check .`), gouvernance des plans validée (`validate_plans.py`).
