---
id: "009-2"
epic: "009"
titre: "Documents sources typés, brief versionné, écriture et lecture de provenance `GraphStore`"
statut: review
auteur: agent
format: "2"
---

# Story 009-2 — Documents sources typés, brief versionné, écriture et lecture de provenance `GraphStore`

Lot B, priorité P1. En tant qu'utilisateur, je veux que chaque fragment de
document ingéré conserve son origine (fichier, rôle, position exacte) et que les
consignes de simulation soient persistées et transmises sans perte, afin que
les faits du graphe et les affirmations du rapport puissent être rattachés à
leurs sources au lieu d'être aplatis.

La story dépend de 009-1 (`done`) : la barrière d'acteurs est opérationnelle et
la preuve de qualification est liée à sa simulation. Elle couvre FR-3, FR-4 et
FR-5 ; NFR-2, NFR-4 et NFR-5 ; critères C3 et C4, contribution à C5.

Trois décisions sont **préconditions de code** (revue de cohérence, arbitrages
2 et 3) : l'ADR du contrat de provenance commun aux deux stores, la sémantique
du statut de validation documentaire (valeurs, transitions, effets) et le
modèle minimal des conflits de sources. Elles sont produites en T1 avant toute
écriture de contrat ou d'ingestion, et consignées avec la story.

## Définition de prêt

- [x] Objectif compris : typer les documents sources (`SourceDocument`, `DocumentChunk`), persister un `SimulationBrief` versionné et non tronqué, étendre le contrat `GraphStore` (écriture des métadonnées de fragment, lecture neutre des épisodes/sources) dans **les deux** implémentations, et transmettre le tout sans perte jusqu'à la classification, aux personas et à la configuration.
- [x] Documents consultés : [PRD](prd.md) §4 FR-3–FR-5, §5 C3/C4/C5, §6 ; [architecture](architecture.md) §2.2, §4, §7, §9 ; [revue de cohérence](revue-coherence-2026-10-10.md) R03–R06, R08, R15, R19 et arbitrages 2–3 ; [hub](epic-009.md) ; [matrice de couverture](couverture-rapport-audit.md) A03–A09 et A12 ; [story 009-1](story-009-1.md) (état de la barrière et de la preuve) ; [ADR 0001](../../decisions/0001-remplacement-de-zep-par-graphiti.md) ; [AGENTS.md](../../../AGENTS.md) §2.1/2.2/2.5/2.8/2.10.
- [x] Dépendances résolues : 009-1 (`done`), 004 et 005 (`done`) ; le filet de référence du 11 octobre 2026 est **924 réussis sur l'hôte, 921 réussis + 3 ignorés sous Docker** ; il doit grossir, jamais rétrécir.
- [x] Décisions à figer avant code (T1) : ADR du contrat de provenance (signatures, DTO de lecture, erreurs, identités d'opération) ; valeurs/transitions/effets du statut de validation ; modèle minimal des conflits (stockage, détection bornée) ; budget de contexte par étape et comportement exact du cas long.
- [x] Stratégie de tests identifiée (table « Fixtures, tests et qualification ») : hermétique par défaut, plus une sonde réelle Neo4j pour C3 séparée de pytest/CI.
- [x] Fixtures définies : deux documents synthétiques (≥ 2 fragments chacun après découpage), un cas long > 50 000 caractères généré, un ancien `project.json` témoin sans documents ni brief.

### Critères d'acceptation

| Réf. | Situation et comportement attendu | Vérification |
|---|---|---|
| AC1 | Chaque fichier importé obtient un `SourceDocument` : identifiant stable (UUID), nom d'origine, nom sauvegardé, rôle, priorité (1–5), date et source/auteur facultatifs, statut de validation. Mode simple par défaut : rôle `facts`, priorité 1, date inconnue, statut non validé. Aucun nom de fichier ne confère d'autorité (ni `officiel`, ni `canonical`). L'ajout est rétrocompatible : un ancien `project.json` reste lisible. | Tests du modèle et des valeurs par défaut ; aller-retour `to_dict`/`from_dict` ; ancien JSON témoin ; cas aux noms trompeurs. |
| AC2 | Chaque document est découpé **séparément** (jamais sur la concaténation) ; chaque fragment porte `source_document_id`, `source_filename`, `chunk_index` (base 0 local au document) et le rôle du document ; `char_start`/`char_end` portent sur le texte normalisé du document et `document_text[char_start:char_end] == chunk_text` pour 100 % des fragments ; page/section seulement si l'extracteur les fournit. | Fixtures 2 documents ≥ 2 fragments ; restitution exacte, dernier fragment et chevauchement compris ; cas sans pagination (aucune page inventée). |
| AC3 | Extension de contrat **rétrocompatible** : les appels existants (`chunks: List[str]`) restent valides ; un paramètre facultatif de métadonnées alignées (une entrée par fragment, ordre préservé) est validé avant écriture (longueurs, types, champs requis) ; un désalignement échoue visiblement, sans ingestion partielle silencieuse. L'ADR est écrit **avant** le code ; l'extension est implémentée et testée dans les deux stores ; aucun Cypher ni import direct de backend dans les services. | Tests de contrat des deux implémentations avec doubles ; appels anciens inchangés (filet GraphStore au vert) ; revue des dépendances/AST. |
| AC4 | Les métadonnées de fragment sont **réellement persistées** (le `metadata` de `GraphitiGraphStore.add_episode` n'est plus ignoré) et les UUID proviennent du résultat réellement persisté ; une erreur d'annotation ne produit jamais un succès d'ingestion. | Test d'écriture avec double et vérification sur Neo4j réel (sonde C3) ; échec injecté : l'erreur remonte et l'opération est signalée. |
| AC5 | Lecture neutre de provenance : une arête se résout vers ses épisodes, puis vers document + fragment + rôle, **dans le même graphe** ; listes vides, épisodes absents, origines mixtes, anciennes ou inconnues sont signalés distinctement, jamais inventés ; les épisodes d'activité simulée conservent leur origine (`simulation_id`, plateforme) et ne sont pas comptés comme faits documentaires. | Tests de contrat et d'isolation par `group_id` (0 fuite inter-graphes) ; cas vide/absent/mixte ; sonde réelle : 100 % des références des **nouvelles** ingestions documentaires se résolvent. |
| AC6 | `SimulationBrief` versionné persisté : objectif, état initial, audiences cibles, exclusions, règles, hypothèses, `additional_context`, version de schéma, horizon, déclencheur, sorties attendues et références documentaires (par `document_id`). 100 % des champs survivent à sauvegarde/relecture ; `additional_context` n'est plus perdu ; ancien projet lisible (brief absent → défauts, sans reconstruction inventée) ; le brief est transmis à la classification, aux personas et à la configuration, et copié dans les artefacts de configuration. | Round-trips complets ; projet ancien témoin ; tests de transmission (messages du classifieur, prompts personas, contexte config, copie d'artefact) ; 0 champ perdu. |
| AC7 | Contexte long : les textes placés dans les prompts portent des diagnostics par étape et par document (échantillonnage, troncature, fragments ignorés, erreurs d'extraction). Cas > 50 000 caractères : omissions documentaires signalées ; le brief explicite n'est **jamais** tronqué silencieusement — conservé, ou refus explicite avec diagnostic s'il dépasse lui-même le budget. | Fixture longue générée ; test du refus explicite ; diagnostics vérifiés dans les journaux/artefacts ; toute réduction de contexte documentaire est listée. |
| AC8 | Statut de validation et conflits : valeurs/transitions/effets figés en T1 et appliqués ; une affirmation contradictoire conserve **ses deux sources** et leurs métadonnées, aucune fusion silencieuse ; la résolution n'utilise que des règles déclarées et exposées, sinon « à confirmer » ; le modèle de conflit est stocké. L'arbitrage humain et l'affichage appartiennent à 009-3, la preuve C7 à 009-4. | Tests du modèle et de la conservation ; fixture de deux affirmations contradictoires résolubles avec leurs deux sources ; aucune résolution implicite par date/priorité sans règle. |
| AC9 | Séparation consignes/sources : les contenus documentaires restent des **données** — jamais message système ni correction d'éligibilité ; les règles du brief restent distinctes du texte documentaire dans les messages construits. | Tests structurels des messages étendus aux documents et au brief ; aucune instruction issue d'un fichier ne devient règle de classification. |
| AC10 | Filet hermétique et parité Docker : 0 échec sous Docker sans `.env` ni réseau externe ; décompte (collectés/réussis/ignorés) consigné et supérieur au filet de référence (924 hôte / 921 + 3 ignorés Docker) ; `ruff check .` et `validate_plans.py` verts ; docs et suivi actualisés ; sonde C3 réelle rejouable et consignée sans secrets. | Exécutions consignées ; skips identifiés ; sonde versionnée (sortie md) ; artefacts de plan à jour. |

## Définition de fini

- [x] AC1 à AC10 satisfaits, preuves rattachées aux tests et à la sonde réelle ; fixtures versionnées avec empreintes.
- [x] ADR du contrat de provenance accepté et référencé ; sémantique du statut de validation et modèle des conflits datés et appliqués.
- [x] Les deux stores étendus (écriture et lecture), appels existants intacts, filet `GraphStore` au vert ; aucun Cypher ni import Zep direct dans les services.
- [x] Rétrocompatibilité : anciens projets et simulations lisibles ; provenance historique signalée « inconnue », jamais reconstruite ni inventée.
- [x] Brief transmis de bout en bout (classification, personas, configuration) et copié dans les artefacts ; cas long > 50 000 caractères traité selon AC7.
- [x] Sonde réelle C3 exécutée contre Neo4j local : ≥ 2 documents × 2 fragments, 100 % des références résolues, positions exactes, origines signalées ; sortie consignée sans secrets.
- [x] Suite hermétique complète, lint et `validate_plans.py` exécutés sous Docker sur le code courant ; décomptes et motifs des skips consignés (référence post-009-1 : 921 réussis + 3 ignorés sous Docker, 924 sur l'hôte).
- [x] Revue de code réalisée et corrections traitées ; statut passé par `review` avant `done` ; hub, suivi et notes de complétion renseignés.

## Tâches

- [x] T1 — Figer avant tout code : ADR du contrat de provenance (signatures, DTO de lecture, erreurs, identités d'opération) ; sémantique du statut de validation (valeurs, transitions, effets) ; modèle minimal des conflits (stockage, détection bornée) ; budget de contexte par étape (AC3, AC5, AC7, AC8).
- [x] T2 — `app/models/source_document.py` : `DocumentRole`, `SourceDocument`, `DocumentChunk` (validation des positions, `to_dict`/`from_dict`) (AC1, AC2).
- [x] T3 — `app/models/simulation_brief.py` : `SimulationBrief` complet et versionné, sérialisation rétrocompatible (AC6).
- [x] T4 — `app/models/project.py` : champs additifs `source_documents`, `simulation_brief`, `additional_context` persisté ; anciens `project.json` lisibles ; stockage du texte normalisé par document (AC1, AC2, AC6).
- [x] T5 — `app/api/graph.py` : conserver le texte extrait **par document**, renseigner les métadonnées (défauts du mode simple), persister documents, brief initial (`goal` = consigne existante) et `additional_context` (AC1, AC2, AC6).
- [x] T6 — `app/utils/graph_store/base.py` : paramètre facultatif de métadonnées alignées, vérifications avant écriture, DTO et méthode de lecture de provenance (AC3, AC5).
- [x] T7 — `graphiti_store.py` : persister `metadata` sur `:Episodic`, UUID réellement persistés, lecture par arête avec `group_id` (AC4, AC5).
- [x] T8 — `zep_store.py` : même extension d'écriture et de lecture sans régression des appels existants (AC3–AC5).
- [x] T9 — `graph_builder.py` : découpage par document, métadonnées alignées (positions, index), concaténation conservée comme contexte seulement, diagnostics par document (AC2, AC7).
- [x] T10 — Transmission du brief (classification, personas, configuration) et du budget de contexte ; diagnostics d'omission/troncature ; copie du brief dans les artefacts de configuration (AC6, AC7, AC9).
- [x] T11 — Tests et fixtures (table ci-dessous) ; adaptation des tests existants touchés, sans suppression (AC1–AC10).
- [x] T12 — Sonde `scripts/verifier_provenance_documents.py` et protocole associé (C3 réel) ; qualification Docker complète ; artefacts, suivi et passage en `review` (AC10).

### Review Findings

Revue contradictoire à quatre couches (Blind Hunter, Edge Case Hunter,
Verification Gap, Acceptance Auditor) sur les changements non commités, le
11 octobre 2026. Un second tour a relu les correctifs. Constats traités :

| # | Couche | Constat | Traitement |
|---|---|---|---|
| F1 | Blind/Edge/Auditor | **Bloquant** — le brief persisté n'était jamais transmis : `api/simulation.py` appelait `prepare_simulation` sans `simulation_brief`, donc `additional_context` et les champs avancés restaient perdus. | `project.get_brief()` est câblé ; `_build_document_sections` fournit les documents par document ; test de transmission de bout en bout (`test_simulation_brief_transmission.py`). |
| F2 | Blind/Edge/Auditor | **Majeur** — `OntologyGenerator` tronquait et échantillonnait sans diagnostic (ADR 0013 §3). | `last_context_diagnostics` par document, consommé et journalisé par l'API ; tests dédiés. |
| F3 | Blind/Edge | **Majeur** — positions de fragments fausses sur texte répétitif (`str.find` renvoyait la première occurrence). | Positions issues du découpage (`split_text_into_chunk_spans`) ; `find_chunk_span` retiré ; tests sur texte répétitif. |
| F4 | Blind/Edge/Verif | **Majeur** — clés de métadonnées non validées interpolées dans le Cypher ; `source` écrasait un `EpisodeType` Graphiti. | Liste blanche stricte dans `validate_chunk_metadata`, clés réservées refusées à l'annotation, `source` retiré des métadonnées d'activité simulée, test de refus. |
| F5 | Blind/Edge/Verif | **Majeur** — une provenance documentaire incomplète comptait comme fait documentaire ; `source_role` absent des champs requis. | `is_documentary` exige `missing_reason is None` et `source_role` est requis dans les deux stores. |
| F6 | Blind/Edge | **Majeur** — `recency` comparait des dates comme des chaînes. | `_parse_date` ISO strict ; une date non interprétable laisse le conflit « à confirmer ». |
| F7 | Blind/Edge | **Majeur** — Zep avalait toute panne de lecture en « non résolu ». | Seuls `NotFoundError` et `ApiError` 404 deviennent `unresolved` ; le reste remonte. |
| F8 | Blind/Verif | **Majeur** — un seul texte manquant faisait perdre la provenance de **tous** les documents. | Repli sur la concaténation seulement si aucun document n'a de texte ; les autres gardent leur provenance ; test dédié. |
| F9 | Auditor/Verif | **Majeur** — le modèle de conflit n'était stocké nulle part. | `Project.source_conflicts` + `get_source_conflicts`/`record_source_conflicts` ; test de stockage. |
| F10 | Auditor | **Majeur** — le budget de configuration ne nommait pas les documents ; `chunks_*` comptaient des caractères. | `documents_included`/`omitted` portent les `document_id` ; champs renommés `characters_*`. |
| F11 | Verif | **Majeur** — l'annotation Graphiti n'était pas vérifiée, l'identité d'opération était tautologique. | Requête d'annotation assertée (`:Episodic`, `group_id`, champs) ; digest figé pour `operation_id` sans provenance. |
| F12 | Edge (2ᵉ tour) | **Majeur** — `source` en métadonnée écrasait une propriété Graphiti. | Voir F4. |
| F13 | Edge (2ᵉ tour) | **Moyen** — le brief n'entrait pas dans l'empreinte de fraîcheur. | `fingerprint_qualification_inputs` inclut le brief ; la fraîcheur reconstruit le même brief minimal. |
| F14 | Edge (2ᵉ tour) | **Moyen** — spans dupliqués quand `overlap → chunk_size`. | Déduplication des plages après rognage ; tests `overlap/cs` proches de 1. |
| F15 | Edge (2ᵉ tour) | **Faible** — diagnostic ontologie par document sans compteur d'échantillons ; personas tronquées en silence ; `is_minimal` toujours faux. | Compteurs par document, `context_diagnostics` personas, `is_minimal` ignore `source_document_ids`. |

F1 était le seul **bloquant** ; F2–F15 sont corrigés et couverts par des tests.
Deux points sont assumés et documentés plutôt que corrigés : la détection de
conflits reste lexicale et bornée (elle le déclare), et `split_text_into_chunks`
a une progression plus sûre que la version d'origine sur les `overlap` extrêmes.

## Notes de développement

### Décisions à figer en T1 (préconditions de code)

- **ADR du contrat de provenance** : arrêter la forme de l'extension (paramètre facultatif de métadonnées alignées sur `add_text_batch`, persistance sur `:Episodic`, DTO/méthode de lecture neutre), les erreurs, la contribution des métadonnées à l'identité d'opération, et l'inclusion éventuelle de T8 (Zep) dans le même geste. L'ADR précède le code ; il précise ce que « référence résolue » veut dire pour C3.
- **Statut de validation documentaire** : valeurs (a minima : non validé par défaut, validé, en conflit), transitions (jamais par le nom du fichier), et effet sur l'ingestion et les priorités. Le nom `official`/`canonical` ne confère aucune autorité.
- **Conflits de sources** : modèle de stockage (affirmations gardant chacune leurs sources), détection bornée et explicite pour ce lot ; résolution uniquement par règle déclarée et affichée, sinon « à confirmer ». L'affichage/arbitrage humain appartient à 009-3 ; C7 (contradiction visible) est la cible de 009-4.
- **Budget de contexte** : plafonds par étape (ontologie, configuration, personas), diagnostics d'omission associés, et comportement du brief long (conservation ou refus explicite, jamais de troncature silencieuse). Le plafond actuel de 50 000 caractères est une référence, pas un dû.

### Modèles et sérialisation

Les modèles cibles sont décrits dans [architecture.md](architecture.md) §2.2 : `DocumentRole` (`facts`, `scenario`, `personas`, `hypotheses`, `constraints`, `reference`), `SourceDocument` (`document_id`, `filename`, `role`, `saved_filename`, `priority`, `date`, `total_chunks`, `author`, `source`, `validation_status`) et `DocumentChunk` (`source_document_id`, `source_filename`, `chunk_index`, `text`, `source_role`, `char_start`, `char_end`, `section`, `page`). Noms canoniques : `document_id` pour le document, `source_document_id` pour sa référence, `source_filename` pour le nom d'origine porté par le fragment.

`SimulationBrief` : `goal`, `initial_state`, `target_audiences`, `excluded_actors`, `rules`, `hypotheses`, `additional_context`, `schema_version`, `time_horizon`, `trigger_event`, `expected_outputs`, `source_document_ids`. Le champ `additional_context` est aujourd'hui perdu après l'ontologie : il devient persisté et transmis.

Les positions comptent des **caractères du texte normalisé** (sortie de `TextProcessor.preprocess_text`), pas des octets ni des positions PDF. Pour chaque fragment, `document_text[char_start:char_end] == text` doit être vrai. Le texte normalisé par document est conservé pour que la vérification soit possible plus tard ; la lecture seule d'un ancien projet ne fabrique ni document ni position.

### Ingestion : par document, jamais sur la concaténation

L'API collecte aujourd'hui les textes par fichier puis ne persiste qu'une concaténation ; `GraphBuilderService` découpe cette concaténation. C'est ce qui rend un fragment chevauchant deux fichiers non attribuable. La cible : conserver et découper **chaque document séparément**, produire des métadonnées alignées avec les fragments (une entrée par fragment, dans l'ordre), et n'utiliser la concaténation que comme contexte de prompt. Le découpage utilise `chunk_size`/`chunk_overlap` du projet ; les index de fragments sont locaux au document, base 0.

Une erreur d'annotation (longueur non alignée, champ manquant, type invalide) interrompt l'ingestion avec un diagnostic ; elle ne produit jamais un lot partiel déclaré réussi.

### Contrat `GraphStore` : écriture et lecture de provenance

- **Écriture** : `add_text_batch(graph_id, chunks, batch_size, ...)` gagne un paramètre facultatif de métadonnées par fragment. Les appels existants restent valides. `GraphitiGraphStore.add_episode` valide `metadata` puis ne le transmet pas à Graphiti — à corriger ; l'UUID retourné doit être celui réellement persisté (pas de repli `uuid4` silencieux). `ZepGraphStore` transmet déjà les métadonnées : l'aligner sur le même contrat.
- **Lecture** : le contrat actuel n'offre aucune lecture d'épisode/source ; `EpisodeRecord` porte `uuid`, `graph_id`, `processed`, `created_at` seulement. Le DTO et la méthode (par arête, isolée par `group_id`) sont arrêtés dans l'ADR. Côté Graphiti, la requête part de l'arête dans le graphe cible et résout `r.episodes` sans masquer les références manquantes (`OPTIONAL MATCH`) ; aucune requête Cypher ne remonte dans les services (le store porte le Cypher, comme aujourd'hui).
- **Origines** : documentaires (résolues), simulées (`simulation_id`, plateforme), héritées/migrées (sans épisode), inconnues. Chacune est signalée distinctement ; aucune n'est comptée comme fait documentaire pour C3. Les graphes migrés de l'epic 006 restent utilisables : provenance « inconnue » signalée, jamais reconstruite.

### Brief : persistance et transmission

Le brief vit dans `project.json` (source de vérité) et une copie est écrite dans les artefacts de configuration de la simulation au moment de la préparation, pour conserver le contexte réellement utilisé. La transmission 009-2 :
1. classification (le contexte de paraphrase/données du classifieur reçoit les champs utiles du brief, sans le texte documentaire dans les règles système — NFR-5) ;
2. personas (prompts) ;
3. configuration de simulation (contexte borné + diagnostics).
Le mode simple ne rend aucun champ avancé obligatoire : un brief minimal (`goal` = consigne existante) suffit ; les champs avancés s'ajoutent sans casser les appels.

### Contexte long et diagnostics

`SimulationConfigGenerator` borne le contexte à `MAX_CONTEXT_LENGTH = 50000` (troncature avec marge de 500 caractères) et `OntologyGenerator` échantillonne les longs documents (`MAX_TEXT_LENGTH_FOR_LLM = 50000`, `MAX_LONG_TEXT_CHUNKS = 60`). Ces réductions doivent devenir **visibles** : par document et par étape, consigner erreurs d'extraction, fragments ignorés, échantillonnage et troncature, sources effectivement utilisées. Le brief explicite est protégé : conservé en priorité, et si lui-même dépasse le budget, l'étape refuse avec un diagnostic explicite au lieu de retirer des consignes en silence.

### Code existant à modifier et contrats à préserver

| Fichier / entrée | État actuel | Modification attendue et comportement préservé |
|---|---|---|
| `app/utils/graph_store/base.py` | `add_episode(metadata=...)` existe ; `add_text_batch(chunks: List[str])` sans métadonnées par fragment ; `EpisodeRecord` sans contenu/source. | Ajouter le paramètre facultatif aligné, la validation et le DTO/lecture de provenance. Garder les signatures existantes utilisables et les tests de contrat au vert. |
| `app/utils/graph_store/graphiti_store.py` | `metadata` validé puis ignoré ; `add_text_batch` pose `source_description=f"chunk_{idx}"` ; aucune lecture d'épisode. | Persister les métadonnées sur `:Episodic` ; UUID réels ; lecture par arête avec `group_id` et `OPTIONAL MATCH`. |
| `app/utils/graph_store/zep_store.py` | Métadonnées déjà transmises ; pas de lecture d'épisode neutre. | Même extension de lecture/écriture ; non-régression stricte du contrat Zep. |
| `app/services/graph_builder.py` | Découpe la concaténation (`TextProcessor.split_text`, l.148) et soumet via `add_text_batches`. | Découper par document, produire les métadonnées alignées, conserver la concaténation comme contexte seulement ; préserver `validate_batch_chunks`, `build_operation_id` et les limites de lots. |
| `app/api/graph.py` | Textes par fichier collectés puis seule la concaténation est persistée (`all_text`) ; `additional_context` passé à l'ontologie mais jamais persisté. | Persister texte par document, `source_documents`, brief initial et `additional_context` ; garder le protocole de tâches et les réponses existantes. |
| `app/models/project.py` | `files` sans rôle/priorité ; pas de brief ni de documents ; texte extrait unique. | Champs additifs sérialisés avec défauts ; anciens `project.json` lisibles à l'identique. |
| `app/services/simulation_config_generator.py` | `MAX_CONTEXT_LENGTH = 50000`, troncature avec marge (`_build_context`, l.402). | Budget explicite par étape, diagnostics d'omission, brief protégé, refus explicite si le brief dépasse. |
| `app/services/ontology_generator.py` | Échantillonnage/`_excerpt_text` bornés (l.251–424), sans restitution structurée. | Exposer les limites appliquées (échantillonnage, troncature) dans les diagnostics par document. |
| Tests existants `GraphStore` | Contrats des deux stores, isolation AST, factory. | Ne rien supprimer ; étendre les contrats, garder l'isolation 0 import Zep/Cypher dans `services/` et `api/`. |

### Fixtures, tests et qualification

| Suite prévue | Ce qu'elle démontre |
|---|---|
| `test_source_document_models.py` | Modèles, défauts du mode simple, validations de positions, sérialisation et rétrocompatibilité (AC1, AC2). |
| `test_simulation_brief.py` | Brief complet, round-trip 100 % des champs, ancien projet sans brief, `additional_context` conservé (AC6). |
| `test_provenance_store_contract.py` | Extension des deux stores avec doubles : métadonnées alignées, échec visible au désalignement, lecture neutre, isolation par graphe, origines signalées (AC3–AC5). |
| `test_graph_builder_document_chunks.py` | Découpage par document, index locaux, positions exactes, concaténation contexte seulement, diagnostics (AC2, AC7). |
| `test_project_documents_persistence.py` | Upload : documents + brief + `additional_context` persistés, ancien JSON témoin, aucune invention (AC1, AC2, AC6). |
| `test_config_context_budget.py` | Budget par étape, diagnostics de troncature, brief protégé, refus explicite du brief trop long (AC7). |
| `test_message_boundaries_documents.py` | Consignes vs sources dans les messages (documents = données ; règles du brief distinctes) (AC9). |
| `test_verifier_provenance_documents.py` | Protocole de la sonde réelle (C3) : seuils, modes, sortie sans secret. |
| `scripts/verifier_provenance_documents.py` + sortie versionnée | Sonde réelle Neo4j : 2 documents × ≥ 2 fragments, 100 % des références résolues, positions exactes, origines signalées (C3). |

Fixtures dans `backend/tests/fixtures/source_documents/` : deux documents synthétiques dont le découpage produit ≥ 2 fragments chacun, et un `project.json` ancien témoin. Le cas long > 50 000 caractères est généré par le harnais (motif déterministe), pas committé en clair.

Sondes existantes à préserver : `verifier_integration_graphiti.py`, `verifier_ingestion_graphiti.py`, `verifier_qualification_local_first.py` (la barrière y est injectée, cf. 009-1), `test_graph_store_isolation.py`. La sonde C3 s'exécute hors pytest/CI, sans `.env` et sans écriture sur les graphes utilisateurs ; ses credentials restent hors des sorties.

### Documents de référence

- [PRD](prd.md), §4 FR-3/FR-4/FR-5, NFR-2/4/5, §5 C3/C4/C5 et §6.
- [Architecture](architecture.md), §2.2 (modèles), §4 (traçabilité Neo4j), §7 (sélection persistée), §9 (contextes longs, diagnostics, conflits).
- [Revue de cohérence](revue-coherence-2026-10-10.md), R03–R06, R08, R15, R19 et arbitrages 2–3.
- [Matrice de couverture](couverture-rapport-audit.md), A03–A09 et A12 ; [hub](epic-009.md).
- [Constitution](../../../AGENTS.md), §2.1/2.2/2.5/2.8/2.9/2.10 ; [suivi](../../sprint-status.yaml) et [état humain](../../STATUS.md).
- [ADR 0001](../../decisions/0001-remplacement-de-zep-par-graphiti.md) (interface à deux implémentations).
- Code : [`base.py`](../../../backend/app/utils/graph_store/base.py), [`graphiti_store.py`](../../../backend/app/utils/graph_store/graphiti_store.py), [`zep_store.py`](../../../backend/app/utils/graph_store/zep_store.py), [`graph_builder.py`](../../../backend/app/services/graph_builder.py), [`api/graph.py`](../../../backend/app/api/graph.py), [`project.py`](../../../backend/app/models/project.py), [`simulation_config_generator.py`](../../../backend/app/services/simulation_config_generator.py), [`ontology_generator.py`](../../../backend/app/services/ontology_generator.py).

## Revue

Revue contradictoire à quatre couches menée le 11 octobre 2026, consignée dans
`### Review Findings` ci-dessus (Tâches). Un second tour a relu les correctifs.
Verdict : un défaut bloquant (F1) et quatorze constats majeurs/mineurs trouvés et
traités ; les deux limites assumées sont écrites. La story peut passer en
`review`.

## Notes de complétion

**Livré.** Les documents sources typés (`SourceDocument`, `DocumentChunk`,
`DocumentRole`, statut de validation, conflits), le `SimulationBrief` versionné,
l'extension rétrocompatible du contrat `GraphStore` (métadonnées alignées,
annotation `:Episodic` vérifiée, lecture neutre `get_edge_provenance` dans les
deux stores), le découpage par document avec positions exactes, la transmission
du brief jusqu'à la classification, aux personas et à la configuration, et le
budget de contexte par étape avec diagnostics et refus explicite. Les ADR
[0012](../../decisions/0012-contrat-de-provenance-graphstore.md) et
[0013](../../decisions/0013-semantique-des-sources.md) ont été écrits **avant**
le code, conformément à la définition de prêt.

**Preuves.**

- Sonde réelle C3 : [`mesure-009-2.md`](mesure-009-2.md) — 2 documents × 2
  fragments, 8/8 références documentaires résolues, 8/8 positions exactes,
  isolation par graphe prouvée, sortie sans secret. Rejouée sous Docker contre le
  Neo4j du compose.
- Filet hermétique : **1110 réussis** sur l'hôte (hors 3 contrôles Docker CLI) et
  **1107 réussis + 3 ignorés** sous Docker sur le code courant, pour une référence
  post-009-1 de 924 hôte / 921 + 3 Docker. Les 3 ignorés sont les contrôles qui
  exigent la CLI Docker, inchangés.
- `ruff check .` : aucune erreur. `validate_plans.py` : 9 epics, 33 fichiers de
  story. Aucun secret dans le diff.

**Écarts au plan.**

- `find_chunk_span` (recherche de sous-chaîne) a été remplacé par une découpe
  qui **rend** les positions : la recherche par `str.find` choisissait la
  première occurrence et donnait des positions fausses sur texte répétitif.
- `split_text_into_chunks` a été rendue sûre sur les `overlap` extrêmes
  (progression d'au moins un caractère) ; le comportement change légèrement là
  où l'ancienne version pouvait boucler ou reculer.
- Le diagnostic de provenance n'a pas de méthode publique « par épisode » : la
  lecture passe par l'arête, conformément à l'ADR 0012 §4. La classification des
  quatre origines est prouvée par les tests hermétiques ; la sonde prouve le
  chemin documentaire de bout en bout.
- Un document dont le texte normalisé manque conserve sa trace dans
  `documents_omitted` ; les autres gardent leur provenance (le repli global est
  réservé aux projets entièrement dépourvus de texte typé).
- L'arbitrage humain des conflits et leur affichage restent à 009-3 ; la
  contradiction visible dans le rapport reste à 009-4.

