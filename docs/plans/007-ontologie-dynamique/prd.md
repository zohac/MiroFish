# PRD — Epic 007 : Ontologie dynamique (v2)

- **Statut** : `in-progress` · **Dépend de** : 003, 004, 005, 009 · **Bloque** : 010
- **Suivi** : [`sprint-status.yaml`](../../sprint-status.yaml)
- **Origine** : [ADR 0003](../../decisions/0003-ontologie-differee-en-v2.md) (« l'ontologie dynamique est une v2 ; le chemin de lecture d'abord »), [`docs/LOCAL-FIRST.md` §6.1](../../LOCAL-FIRST.md) (« le point dur »), reprise de l'epic 009 (qui a qualifié le verrou d'éligibilité et aiguisé le besoin d'un typage plus fin que `:Entity`).
- **Nature** : cible proposée, aucune story démarrée. Le périmètre est délibérément restreint à **persistance + validation** (cf. arbitrage de cadrage du 12 octobre 2026) : l'ontologie devient effective, pas un raffinement auto-évolutif.

> L'Epic 009 (« Éligibilité des acteurs et fiabilisation des sources ») est close (4/4 stories, **1157 tests verts**, Verdict GO). L'actor selection est qualifiée, l'anti-affabulation C7 tient, la section « Sources & Provenance » est dans le rapport.  
>
> **L'Epic 007 transforme l'ontologie générée en typage réel du graphe** : `OntologyGenerator` produit déjà 10 types d'entité et de relation par appel LLM, mais `GraphStore.set_ontology` est un **no-op** depuis l'ADR 0003. La v1 livre donc une ontologie morte : les nœuds Graphiti ne portent que le label générique `:Entity`, et le lecteur (`zep_entity_reader.get_entity_type`) résout en cascade sur les attributs. La v2 pose effectivement les labels sur les nœuds, valide l'écriture, et régénère sur événement.

---

## 1. Le problème

### 1.1 L'ontologie est générée mais jamais appliquée

`backend/app/services/ontology_generator.py` (814 lignes) consomme le brief, échantillonne les documents (`_build_document_context` plafonné à 50 000 caractères, story 009-2), et retourne un dictionnaire contenant `entity_types` (10 max) et `edge_types`. Le résultat est **remis au `GraphBuilderService` puis passé à `GraphStore.set_ontology(graph_id, ontology)`**.

Dans les deux implémentations concrètes du store :

- `GraphitiGraphStore.set_ontology` (ligne 462 de `backend/app/utils/graph_store/graphiti_store.py`) — *no-op* explicite avec un log `debug`. Commentaire : *« no-op en v1 conformément à l'ADR 0003 »*.
- `ZepGraphStore.set_ontology` (ligne 298) — code de scaffolding laissé en suspens, jamais exercé par les tests d'intégration Epic 002.

Conséquence mesurable dans la v1 : **tous** les nœuds du graphe portent le label générique `:Entity` (et `:Node`). La résolution de type par `EntityNode.get_entity_type()` ne peut donc s'appuyer que sur la cascade de repli (label `Entity` exclu → attribut `entity_type` → `"Entity"` → `None`). Les types métier (PersonEntity, MediaOrganization, etc.) sont perdus.

### 1.2 Le verrou d'éligibilité masque le manque

L'Epic 009 a posé un classifieur agnostique (`ActorClassifierService`, story 009-1) qui prend une entité du graphe et qualifie son rôle **sans** dépendre du label Graphiti. C'était la bonne décision pour découpler le filet de sécurité de l'ontologie (NFR-1). Mais le dédoublement a un coût : `ActorClassifierService` est appelé une fois par entité candidate, même quand un label d'ontologie (`PersonEntity`) répondrait déjà à la question.

Une fois l'ontologie réellement appliquée, le classifieur peut **s'appuyer** sur le label comme signal primaire, et le coût de qualification baisse. Mais le classifieur ne doit pas disparaître : l'ontologie ne couvre pas tous les cas (entités nouvelles, typage ambigu, hiérarchie de rôles). La v2 doit donc composer les deux, sans dupliquer la qualification.

### 1.3 La régénération est sans grammaire

L'Epic 006 a montré qu'une migration de graphe est coûteuse. Si l'ontologie est régénérée à chaque ingestion (cohérence doc → type), la migration devient triviale ; si elle ne l'est pas, les types divergent du corpus réel et la qualification se dégrade.

L'ADR 0003 §3 nomme ces trois questions à arbitrer en v2 :

1. Quand régénère-t-on ? (à l'ajout de document, au changement de brief, sur demande explicite)
2. Quelle politique de remplacement ? (préserver les anciens labels, fusionner, rétrograder)
3. Quelle exposition à l'utilisateur ? (rapport seulement, ou IHM de revue)

---

## 2. L'objectif

Rendre l'ontologie **effective, validée et régénérable** sur événement, sans dupliquer ce que l'Epic 009 pose déjà. À la fin de l'epic :

1. **L'ontologie générée pose réellement ses labels sur les nœuds du graphe.** `GraphStore.add_episode` consomme l'ontologie du projet et l'utilise pour contraindre l'extraction, et les nœuds résultants portent les labels déclarés (`PersonEntity`, `MediaOrganization`, etc.).
2. **L'écriture est validée** : un nœud dont le type n'est pas dans l'ontologie est soit rejeté avec un diagnostic explicite, soit rétrogradé vers `:Entity` avec un `warning` tracé, selon la politique configurée (rétrogradation avec warning par défaut, refus via `strict_ontology=True`).
3. **La régénération est déclenchée sur événement** : ajout de document au projet, modification du brief de simulation, demande explicite via API. La régénération préserve les labels existants et ajoute les types nouveaux.
4. **L'ontologie est une par projet** : deux simulations du même projet partagent l'ontologie ; un nouveau projet génère la sienne. Pas d'ontologie globale, pas de duplication.
5. **L'ontologie est composable avec l'actor selection 009** : `ActorClassifierService` lit le label d'ontologie comme signal primaire quand il existe, conserve sa cascade de repli sinon, et n'est jamais contredit par un label absent.
6. **L'ontologie est auditée** : la liste des types appliqués, leur description, leur origine (document, brief, héritage) et le compte d'entités par type sont requêtables et apparaissent dans la section « Sources & Provenance » du rapport (story 009-4) ou une section équivalente dédiée.
7. **L'étanchéité NFR-5 est préservée** : la consigne ontologique est une donnée utilisateur (entrée du LLM), pas une instruction système. Le test qui le vérifie est posé dès 009-4 (`test_report_agent_nfr5_suffix_in_plan_prompt`).

---

## 3. Périmètre

### 3.1 Dans le périmètre

- **Persistance effective des labels d'ontologie** : `GraphStore.add_episode` accepte l'ontologie et la passe au store concret ; `GraphitiGraphStore` la traduit en Pydantic pour Graphiti, et après ingestion, les nœuds portent les labels déclarés. `ZepGraphStore` aligne son comportement (le contrat `GraphStore` est commun, ADR 0001).
- **Validation à l'écriture** : un nœud dont le `entity_type` n'est pas dans l'ontologie déclenche un `GraphValidationWarning` et, selon la politique, un refus. La politique par défaut est « rétrograder vers `:Entity` avec `warning` » ; un override `strict_ontology=True` active le refus explicite.
- **Régénération sur événement** : ajout de document, modification du brief (`SimulationBrief` de 009-2), demande explicite via endpoint. L'événement est tracé dans le journal du projet.
- **Stockage projet** : `Project` porte un champ `applied_ontology` (référence à la dernière ontologie appliquée, versionnée), avec un identifiant d'ontologie permettant de tracer le delta entre deux versions.
- **Compatibilité avec `ActorClassifierService` (009-1)** : le classifieur consulte d'abord le label d'ontologie, puis seulement ensuite applique sa cascade. Le test d'actor classification de 009-1 reste vert ; un test dédié à l'orchestration ajoute les deux nouveaux cas (label présent et label absent).
- **Audit dans le rapport** : une section « Ontologie appliquée » apparaît dans `build_sources_provenance_section()` (introduit en 009-4), listant types, descriptions, origines et compte d'entités. Cette section s'ajoute aux 5 sections actuelles et reste compatible avec la sortie 1157 tests verts de l'Epic 009.
- **Suite de tests unitaires et d'intégration** : ≥ 2 projets à corpus distincts (mêmes fixtures que C2 et C3 de l'Epic 009), ≥ 80 % des entités avec un label custom, 100 % des écritures hors ontologie capturées, deux simulations d'un même projet partageant l'ontologie.

### 3.2 Hors périmètre

- **Ontologie auto-évolutive au cours d'une simulation** (boucle acteur → ontologie → extraction). Cette lecture est explicitement écartée par l'arbitrage de cadrage du 12 octobre 2026. Une note est consignée dans `docs/deferred-work.md` pour la suite éventuelle.
- **Ontologie multi-niveaux** (base partagée + delta par projet). L'arbitrage « une ontologie par projet » exclut ce raffinement.
- **Édition manuelle des types d'ontologie par l'utilisateur** via une IHM dédiée. L'ontologie reste inférée du corpus et du brief. Une IHM de revue pourra être ajoutée dans un lot ultérieur si l'arbitrage change.
- **Migration automatique des graphes Epic 006 vers l'ontologie v2.** Les graphes migrés restent sur `:Entity` (leur étiquette d'origine, ADR 0012) et ne sont pas ré-typés. Une migration rétroactive est documentée dans `docs/deferred-work.md`.
- **Personnalisation utilisateur de la langue de l'ontologie** (FR/EN/ mixte). L'ontologie reste en anglais PascalCase pour les types et `UPPER_SNAKE_CASE` pour les relations, conformément au contrat actuel d'`OntologyGenerator`. La traduction des descriptions est du ressort de l'Epic 008 (localisation).
- **Interface utilisateur de politique.** La préférence `strict_ontology` est persistée par projet et exposée par API en 007-2 ; une bascule dans l’IHM est reportée.

---

## 4. Critères de sortie chiffrés

| Réf. | Critère | Seuil chiffré | Méthode de mesure |
|---|---|---|---|
| **C1** | Persistance effective des labels d'ontologie | ≥ 80 % des entités extraites sur un corpus d'épreuve (≥ 5 documents, ≥ 2 domaines) portent un label custom non-`:Entity` après `add_episode` avec ontologie. | Banc d'intégration contre Neo4j local (`docker-compose.yml`), exécution sur 2 fixtures distinctes, comptage Cypher sur les nœuds `:Entity` du `group_id`, en excluant `:Entity` et `:Node` de la liste des labels. **Mesuré** : le contexte d'extraction de Graphiti place toujours un type générique `Entity` en identifiant 0 et les types déclarés à partir de 1 ; un nœud que le LLM n'a pas su typer porte donc `:Entity` seul, et compte au dénominateur sans compter au numérateur. Le seuil de 80 % se mesure malgré cette ponctuation, pas grâce à elle. |
| **C2** | Validation à l'écriture | 100 % des écritures avec un `entity_type` hors ontologie déclenchent un `GraphValidationWarning` (mode défaut) ou un `GraphValidationError` (mode `strict_ontology`). Aucun nœud écrit avec un label non déclaré n'est laissé silencieux. | Tests unitaires sur `GraphitiGraphStore` et `ZepGraphStore` exerçant chacune des branches (mode défaut + mode strict, type absent + type présent), captures des logs et exceptions. |
| **C3** | Régénération sous budget | Pour un corpus de 50 000 caractères, la régénération d'ontologie (de la lecture des documents à la pose de l'ontologie) prend **< 30 secondes** sur l'hôte et **< 45 secondes** sous Docker, avec `temperature=0.0` et un corpus identique deux fois produisant deux ontologies identiques au mot près (champs stables : `entity_types[].name`, `edge_types[].name`, `attributes[].name`). | Sonde de mesure `verifier_qualification_epic_007.py` exerçant 2 corpus (50K et 10K) deux fois chacun, comparant les diffs JSON. |
| **C4** | Régénération sur ajout de document | Ajouter un document à un projet dont l'ontologie est déjà appliquée déclenche une régénération **dans les 5 secondes** suivant l'upload. Les nœuds existants conservent leur label ; les nouveaux types du delta apparaissent dans l'ontologie. | Test d'intégration : ingestion d'un premier document, vérification des labels, ajout d'un second document, vérification que les labels anciens sont préservés et qu'au moins un type nouveau est apparu. |
| **C5** | Cohérence projet (une ontologie par projet) | Deux simulations successives d'un même projet, sans ajout de document ni modification de brief entre les deux, **partagent la même ontologie** (même `applied_ontology_id`, même contenu). Une simulation d'un autre projet a une ontologie distincte. | Test d'intégration créant 2 projets à corpus distincts, simulant 2 fois le premier, comparant les `applied_ontology_id`. |
| **C6** | Compatibilité avec l'actor selection (Epic 009) | `ActorClassifierService` continue de retourner les mêmes verdicts qu'en 009-1 sur les fixtures canoniques (≥ 8/8 acteurs retenus sur `space-bunny`, ≥ 0 faux acteur). Quand le nœud porte un label d'ontologie `PersonEntity`, le classifieur le consulte et **évite l'appel LLM**. Quand le label est absent, il retombe sur la cascade 009-1. Mesure : ≥ 1 test « label présent court-circuite LLM » et ≥ 1 test « label absent conserve le comportement 009-1 ». | Tests unitaires + intégration, mock du LLM pour vérifier l'absence d'appel quand le label est suffisant. |
| **C7** | Auditabilité dans le rapport | La section « Sources & Provenance » (009-4) inclut une **sous-section « Ontologie appliquée »** listant : types d'entité (nom + description + origine : document / brief / héritage), types de relation (idem), compte d'entités par type, identifiant de version d'ontologie. La section est absente si et seulement si le projet n'a pas d'ontologie appliquée. | Test de génération de rapport vérifiant la présence de la sous-section et son contenu sur 2 fixtures, plus un test négatif sur un projet sans ontologie. |
| **C8** | Étanchéité NFR-5 et filet de régression | La consigne ontologique est passée au LLM **uniquement en `user_message`**, jamais en `system_prompt`. Le filet de tests global est **supérieur à 1157 + 20 tests verts** sur l'hôte, **0 échec** sous Docker, `ruff check .` propre, `validate_plans.py` valide. | Tests d'inspection des messages LLM, exécution complète de la suite, inspection des images Docker (pas de secret). |

---

## 5. Hypothèses et risques

### 5.1 Hypothèses

- **H1 — Les 10 types max d'`OntologyGenerator` suffisent.** Le contrat actuel plafonne à 10 types d'entité ; aucun usage réel connu ne le dépasse. Si un corpus nécessite plus, le seuil est un paramètre à exposer, pas à supprimer.
- **H2 — Graphiti pose réellement les labels passés en Pydantic.** Vérifié empiriquement en Epic 003 (story 003-2, `custom_entity_types` documenté). Si Graphiti change ce comportement, le contrat `GraphStore` reste neutre et l'implémentation s'adapte.
- **H3 — L'actor selection 009 ne duplique pas le typage.** Le classifieur regarde le label comme signal, pas comme vérité. La règle « ne pas contredire l'ontologie, ne pas la dupliquer non plus » est testable.
- **H4 — Le format de stockage d'ontologie est portable entre Zep et Graphiti.** Le contrat `GraphStore.set_ontology` accepte un dict `{entity_types, edge_types, attributes}`. La traduction Pydantic (Graphiti) et l'enregistrement JSON (Zep) sont deux implémentations du même contrat.

### 5.2 Risques

| Risque | Probabilité | Impact | Mitigation |
|---|---|---|---|
| **R1 — Graphiti rejette des Pydantic générés à l'exécution** | Moyenne | Élevé (le store concret casse) | Construire les Pydantic en deux temps : d'abord valider le squelette (champs, types primitifs), puis injecter dans Graphiti. Tester avec un mock du compilateur Pydantic avant d'attaquer le store concret. |
| **R2 — La régénération invalide l'actor selection en cache** | Faible | Moyen (UX) | `ActorSelection` (009-3) est rattachée à une empreinte SHA-256 du brief + corpus. Si l'ontologie change, l'empreinte du brief ne change pas : la sélection est simplement rejouée. Documenter ce comportement ; pas de bug à fermer. |
| **R3 — Le coût de qualification LLM augmente avec l'ontologie** | Faible | Faible (performance) | L'ontologie est un signal, pas une charge. Le test C6 vérifie que le label court-circuite l'appel LLM dans le cas simple. |
| **R4 — Les graphes migrés Epic 006 perturbent les fixtures** | Moyenne | Moyen (tests fragiles) | Les graphes migrés portent `:Entity` sans label custom. Les fixtures de test utilisent un corpus neuf, jamais migré. Les graphes migrés restent sur `:Entity` par défaut et ne sont pas concernés par la v2 (cf. §3.2). |
| **R5 — La double indexation (Pydantic + label) double le coût d'écriture** | Faible | Faible (performance) | Graphiti indexe déjà par label. La pose d'un label custom supplémentaire n'ajoute pas d'index implicite. Mesure au banc Epic 005-4 (persistance) ; ajustement si le coût devient visible. |

---

## 6. Dépendances et pré-requis

### 6.1 Epics bloquants

- **Epic 003** (GraphitiGraphStore, closed) — fournit le contrat `GraphStore.set_ontology` et les hooks d'extraction qui consomment l'ontologie.
- **Epic 004** (bascule sans Zep, closed) — confirme que l'environnement local-first tient sans clé Zep. L'ontologie v2 s'exécute dans ce cadre.
- **Epic 005** (Docker de référence, closed) — l'environnement de validation est l'image `mirofish-backend:local` orchestrée par `docker-compose.yml`.
- **Epic 009** (actor eligibility, closed) — fournit `ActorClassifierService`, `SimulationBrief`, `SourceDocument`, `SourceConflict`, et la section « Sources & Provenance » du rapport. C'est l'**échéance de dépendance** la plus haute : sans Epic 009, l'ontologie n'a pas d'utilisateur identifié.

### 6.2 ADRs

- **ADR 0001** — Interface `GraphStore` à deux implémentations. L'ontologie v2 respecte ce contrat.
- **ADR 0003** — Ontologie différée en v2 (immédiat, accepté). La v2 honore cette décision.
- **ADR 0012** — Contrat de provenance commun aux deux stores. L'ontologie ne contredit pas la provenance : un type d'ontologie ne **crée** pas une origine, il **étiquette** un nœud.
- **ADR 0013** — Sémantique des sources (statut de validation, conflits). La sous-section « Ontologie appliquée » (C7) coexiste avec les sections de validation et de conflits sans les écraser.

### 6.3 Pré-requis d'implémentation

- Le module `OntologyGenerator` (814 lignes) reste l'unique point de génération ; il ne change pas de signature, seulement le contrat de retour est versionné.
- Le `Project` (009-2) reçoit deux nouveaux champs : `applied_ontology_id: Optional[str]` et `applied_ontology_version: int`. Le champ est rétrocompatible : un projet sans ontologie voit ces champs à `None` / `0`.
- `GraphitiGraphStore.add_episode` (Epic 003, story 003-2) reçoit un paramètre `ontology: Optional[Dict[str, Any]]` ; la rétrocompatibilité est garantie par défaut `None` (comportement v1).
- Le `ReportAgent._execute_tool` (009-4) reçoit un nouvel outil `get_applied_ontology` qui retourne la sérialisation JSON de l'ontologie projet et le compte d'entités par type.

---

## 7. Plan de livraison indicatif

L'epic est trop large pour une seule story. Un découpage en 6 à 8 stories est attendu (à figer dans `epic-007.md`) :

1. **007-1 — Persistance effective des labels d'ontologie** (C1). Modifie `GraphitiGraphStore` (et aligne `ZepGraphStore`) pour que `add_episode` accepte une ontologie, la traduise en Pydantic, et que les nœuds portent les labels déclarés. Tests d'intégration sur Neo4j.
2. **007-2 — Validation à l'écriture** (C2). Ajoute `GraphValidationWarning`, politique par défaut « rétrograder vers `:Entity` + warning », override `strict_ontology=True`. Tests des deux branches sur les deux stores.
3. **007-3 — Régénération déterministe et budget** (C3). Pose `temperature=0.0` par défaut, expose un mode de mesure sur 50K et 10K, vérifie la déterminisme via diff JSON.
4. **007-4 — Régénération sur événement** (C4 + C5 partiel). Câble l'événement « ajout de document » et « modification de brief » à la régénération, et pose `applied_ontology_id` / `applied_ontology_version` sur le `Project`.
5. **007-5 — Cohérence projet (C5 strict) + compatibilité actor selection** (C6). Vérifie que 2 simulations du même projet partagent l'ontologie et que le classifieur court-circuite le LLM quand le label est suffisant.
6. **007-6 — Audit dans le rapport** (C7). Ajoute la sous-section « Ontologie appliquée » à `build_sources_provenance_section` et expose `get_applied_ontology` comme outil LLM.
7. **007-7 — Qualification globale C1–C8 et clôture** (C8). Banc `verifier_qualification_epic_007.py`, filet de tests > 1177, verdict GO.

Le détail (couvertures, critères internes) sera posé dans l'`epic-007.md` au démarrage de la première story.

---

## 8. Questions ouvertes

| Question | Effet si la réponse change |
|---|---|
| **Q1 — Politique par défaut : rétrograder ou refuser ?** La section §3.1 fixe « rétrograder + warning » comme défaut et « refuser » comme override. Si l'arbitrage penche pour « refuser par défaut », la perte d'entités en cas d'ontologie incomplète est plus visible mais bloque l'extraction. | Story 007-2 : interface de politique, tests des deux branches, valeur par défaut. |
| **Q2 — Quand « modification de brief » déclenche-t-elle la régénération ?** Une modification mineure (faute de frappe) ne doit pas tout régénérer. Un diff sémantique du brief est-il requis ? | Story 007-4 : politique de diff sur `SimulationBrief`. Le seuil peut être un simple `difflib.SequenceMatcher` ou un re-run LLM. |
| **Q3 — Les graphes migrés Epic 006 peuvent-ils recevoir un typage rétroactif ?** Le périmètre §3.2 dit non, mais une passe de typage a posteriori (label `:Entity` → label d'ontologie par inférence) est techniquement possible. Coût vs valeur à arbitrer. | `docs/deferred-work.md` (déjà documenté) ; Epic 010 le cas échéant. |
| **Q4 — Faut-il exposer `applied_ontology` dans l'API publique `/api/project/<id>` ?** La visibilité aide l'IHM de revue (cf. §1.3), mais c'est un couplage de plus. | Story 007-6 : endpoint dédié ou simple inclusion dans la réponse `Project`. |

---

## 9. Ce qui est déjà mesuré

Ces faits, vérifiés avant le cadrage de la v2, ne sont pas à re-dériver :

| Fait | Source |
|---|---|
| `set_ontology` est un no-op documenté dans `GraphitiGraphStore` (ligne 462) et un scaffolding non exercé dans `ZepGraphStore` (ligne 298). | `backend/app/utils/graph_store/graphiti_store.py`, `zep_store.py`. |
| `OntologyGenerator.generate` produit au plus 10 types d'entité (`MAX_ONTOLOGY_TYPES = 10`), en `temperature=0.3` par défaut, avec diagnostics de contexte (`last_context_diagnostics`) posés en 009-2. | `backend/app/utils/ontology.py:6`, `backend/app/services/ontology_generator.py:200-260`. |
| `zep_entity_reader.get_entity_type` (story 003-4) résout en cascade : label non-`Entity` → attribut `entity_type`/`type`/`category` → `"Entity"` → `None`. La v2 n'a pas à modifier cette cascade : elle alimente la première branche. | `backend/app/services/zep_entity_reader.py:50-68`. |
| L'Epic 009 (close, 1157 tests verts) a déjà qualifié l'actor selection, la section « Sources & Provenance » du rapport, et l'étanchéité NFR-5. C'est la **dépendance la plus haute** : l'ontologie v2 s'insère sans rien casser. | `docs/plans/009-eligibilite-acteurs-et-sources/rapport-qualification-epic-009.md`. |
| Le filet de référence au 12 octobre 2026 est **1157 tests verts sur l'hôte** (référence post-009-4 et revue BMAD) ; l'epic 007 doit le porter à **1177+** sans régression. | `AGENTS.md §2.2`. |

---

## 10. Hors périmètre (rappel)

Ces chantiers sont explicitement reportés :

- Boucle auto-évolutive acteur → ontologie (note dans `docs/deferred-work.md`).
- Migration rétroactive des graphes Epic 006 (note dans `docs/deferred-work.md`).
- Édition manuelle des types via IHM (lot ultérieur, dépend de l'arbitrage utilisateur).
- Localisation FR des types d'ontologie (Epic 008).
- Régénération par simulation d'événements externes (RSS, API) — non couvert par la v2.

## 11. Clarification du ticket 007-2 — 12 octobre 2026

Le contrat détaillé de l’epic et de l’architecture est retenu : rétrogradation
avec warning par défaut, refus en mode strict, politique sérialisable par projet
et endpoint PATCH idempotent. Les formulations contraires des §2/3.2 sont
corrigées. Les warnings sont conservés dans un journal dédié par graphe, sans
mélange avec l’historique d’identifiants de versions prévu en 007-4. La garantie
de refus exige un contrôle avant persistance ; sa faisabilité est une condition
de prêt explicite de 007-2.

## 12. Résultat de faisabilité C2 — 12 octobre 2026

[Étude 007-2](faisabilite-007-2.md), [ADR 0015](../../decisions/0015-controle-ontologie-avant-persistance.md) :
point pré-persistance Graphiti démontré ; garanties C2 Zep non démontrées.
C2 reste inchangé. La story 007-2 est `blocked` avant implémentation ; une
modification de périmètre ou une nouvelle architecture d’ingestion devra être
arbitrée explicitement avant reprise.
