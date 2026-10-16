---
id: "011-2"
epic: "011"
titre: "Registre d'événements observés (OasisLogReaderService, EvidencePack), bouclier ToolShield et déterminisme Round 0"
statut: done
auteur: "Antigravity & Équipe MiroFish"
format: "2"
---

# Story 011-2 — Registre d'événements observés (OasisLogReaderService, EvidencePack), bouclier ToolShield et déterminisme Round 0

Lot A, priorité **P0**. En tant qu'analyste et utilisateur de MiroFish, je veux que les actions réelles simulées soient collectées, normalisées et indexées dans un registre unifié d'événements (`OasisLogReaderService`, `EvidencePack`) avec un identifiant stable déterministe (`event_id`), que le `ReportAgent` dispose d'un outil direct `query_simulation_events` pour interroger les faits observés, que la boucle ReACT soit protégée contre le burn d'itérations par un bouclier défensif (`ToolShield`) interceptant les requêtes vides et les exceptions d'outils, et que l'assignation des posts initiaux au Round 0 dans `SimulationConfigGenerator` soit strictement déterministe et basée sur le nom exact du persona afin d'éliminer toute permutation d'identités.

Cette story répond directement aux exigences fonctionnelles **FR-02** (registre d'événements observés), **FR-05** (bouclier de validation des outils ReACT `ToolShield`) et **FR-06** (déterminisme d'assignation au Round 0) de l'Epic 011. Elle concourt aux critères de sortie chiffrés **C2** (accès direct aux traces réelles via `query_simulation_events` sans crash en rejeu), **C3** (bouclier `ToolShield`, zéro burn d'itérations et zéro bascule forcée précipitée) et **C6** (100 % d'assignations fidèles au persona au Round 0 sans inversion), tout en garantissant la résilience ReACT (**NFR-04**) et l'étanchéité des prompts face aux données injectées (**NFR-05**).

---

## Définition de prêt

- [x] **Objectif compris et cadré** :
  1. Construire le registre normalisé d'événements de simulation (`OasisLogReaderService`, modèle `EvidencePack`, record `ObservedEvent`) à partir des journaux multi-plateformes (`twitter/actions.jsonl`, `reddit/actions.jsonl`, SQLite) avec calcul déterministe d'`event_id`.
  2. Exposer l'outil ReACT `query_simulation_events` pour permettre au `ReportAgent` de requêter les faits réels avec filtres multi-critères et citations authentifiées.
  3. Mettre en place le bouclier `ToolShield` dans la boucle ReACT de `ReportAgent` pour intercepter les requêtes vides (`quick_search: {}`, `panorama_search: {"query": ""}`), injecter automatiquement un terme de repli pertinent issu du contexte de section ou de simulation, et transformer toute exception technique en observation textuelle exploitable sans consommer vainement le quota d'itérations.
  4. Réformer l'algorithme d'assignation des `initial_posts` dans `SimulationConfigGenerator` pour privilégier la correspondance exacte et insensible à la casse du nom du persona (`entity_name`), éliminant les inversions constatées sur les personas Keova (Émilie, Sylvie, Christine).
  5. Assurer l'étanchéité stricte entre action réelle observée (`is_action_executed`) et intention textuelle verbale (`is_verbal_intention`).
- [x] **Documents consultés** :
  - [PRD Epic 011](prd.md) : §1.A.2 (burn d'itérations ReACT par requête vide), §1.A.3 (inversion des identités de personas au Round 0), §1.B.1 & §1.B.5 (absence de distinction action vs intention), §3 (FR-02, FR-05, FR-06), §4 (NFR-04, NFR-05), §5 (C2, C3, C6).
  - [Architecture Epic 011](architecture.md) : §2.2 (`OasisLogReaderService` et `EvidencePack`), §2.3 (`ToolShield`), §2.4 (`ReportClaim` et distinction action/intention), §2.6 (déterminisme au Round 0).
  - [Hub Epic 011](epic-011.md) : index des exigences et critères de sortie de l'Epic.
  - [Proposition amont Keova](rapport-chatgpt.md) : analyse empirique des 5 simulations réelles, échecs de requêtes `quick_search` vides et inversions de personas.
  - `backend/app/services/simulation_action_verifier.py` : `compute_event_id`, `load_simulation_actions`, motifs d'intention textuelle.
  - `backend/app/services/report_agent.py` : boucle ReACT (`_execute_tool`, `_define_tools`, gestion des itérations `max_iterations = 5`).
  - `backend/app/services/zep_tools.py` : `quick_search`, `panorama_search`, `search_graph`.
  - `backend/app/services/simulation_config_generator.py` : `_generate_event_config`, `_assign_initial_post_agents`.
  - `backend/app/utils/graph_store/graphiti_store.py` : déclenchement de `GraphValidationError("Le texte de recherche query est requis")`.
  - `AGENTS.md` : §2.1 (Clean Architecture), §2.2 (tests hermétiques et non-régression), §2.8 (gouvernance des plans).
- [x] **Dépendances résolues** :
  - Story 011-1 close (`done`) avec maintien en vie interactif post-rounds et clôture ordonnée post-rapport.
  - Filet de tests au vert : **1 663 tests réussis sur l'hôte** (+ 9 tests frontend Node), 0 échec.
- [x] **Décisions d'ingénierie arrêtées avant code** :
  1. **Modèle `EvidencePack` et `ObservedEvent`** : Créer un conteneur typé dans `backend/app/models/evidence_pack.py` regroupant les actions réelles avec identifiants déterministes, indexées par plateforme, round, agent et type d'action.
  2. **Service unifié `OasisLogReaderService`** : Parser de manière tolérante et résiliente les flux `actions.jsonl` (Twitter, Reddit, générique) et les traces SQLite de l'environnement, avec invalidation de cache basée sur l'horodatage `mtime`.
  3. **Déterminisme d'`event_id`** : Réutiliser la méthode éprouvée `SimulationActionVerifier.compute_event_id` (`evt_<platform>_<round>_<agent_id>_<sha256_16>`) pour assurer la cohérence cryptographique de bout en bout.
  4. **Bouclier `ToolShield` anti-burn d'itérations** : Dans `ReportAgent._execute_tool`, intercepter systématiquement les paramètres vides (`not query or not str(query).strip()`) pour `quick_search`, `panorama_search` et `insight_forge`, et substituer automatiquement le titre de section (`section.title`) ou le sujet de simulation (`simulation_requirement`). Intercepter toute exception de validation de store (`GraphValidationError`) pour renvoyer une réponse explicative sans interrompre le cycle ReACT.
  5. **Déterminisme nominatif Round 0** : Dans `SimulationConfigGenerator`, adapter le prompt d'événement pour associer nominativement `poster_persona` ou `poster_name` à l'entité visée, et modifier `_assign_initial_post_agents` pour tenter d'abord une correspondance exacte et insensible à la casse avec `agent.entity_name` avant tout repli par type générique (`poster_type`).
  6. **Étanchéité action vs intention** : Les actions issues d'`actions.jsonl` portent `is_action_executed = True`. Les intentions textuelles détectées dans le corpus de messages portent `is_verbal_intention = True` et ne peuvent être requêtées comme actions réelles sans événement d'exécution authentifié.
- [x] **Stratégie de tests identifiée** :
  - Suite de tests hermétiques dédiée (`backend/tests/test_oasis_log_reader_toolshield.py`).
  - Tests unitaires d'extraction de logs JSONL et SQLite synthétiques avec validation des `event_id`.
  - Tests du bouclier `ToolShield` : appels sans arguments, requêtes vides, levées d'erreurs simulées et vérification de l'absence d'exception non gérée et du maintien du budget d'itérations.
  - Tests d'assignation au Round 0 reproduisant le cas Keova avec 100 % d'attribution fidèle aux personas Émilie, Sylvie et Christine.
  - Maintien rigoureux du filet complet de 1 663 tests.

---

### Critères d'acceptation

| Réf. | Situation et comportement attendu | Vérification / preuve |
|---|---|---|
| **AC1** | **Modèle `EvidencePack` et normalisation des événements observés** : Le modèle `ObservedEvent` encapsule de manière immuable `event_id`, `simulation_id`, `platform`, `round_num`, `agent_id`, `agent_name`, `action_type`, `action_args`, `timestamp`, `is_action_executed` (True par défaut pour toute trace d'action issue du moteur), et les métadonnées brutes. `EvidencePack` regroupe l'ensemble des événements du run avec statistiques de répartition (par plateforme, type d'action et persona) et supporte la sérialisation `to_dict` / `to_text`. | Test unitaire validant l'instanciation, la sérialisation et l'intégrité des champs du modèle `EvidencePack`. |
| **AC2** | **Service d'extraction et d'indexation `OasisLogReaderService`** : `OasisLogReaderService` charge et indexe l'ensemble des actions effectives depuis `twitter/actions.jsonl`, `reddit/actions.jsonl` et les bases SQLite locales d'OASIS. Chaque action reçoit un `event_id` déterministe via `SimulationActionVerifier.compute_event_id`. Le service maintient un cache mémoire invalidé par `mtime` et fonctionne de manière autonome en mode rejeu ou sur simulation éteinte (C2, zéro crash). | Test unitaire hermétique chargeant des traces synthétiques multi-plateformes, vérifiant la déduplication, la stabilité des `event_id` et la résilience hors-ligne. |
| **AC3** | **Outil ReACT `query_simulation_events` intégré au `ReportAgent`** : L'outil `query_simulation_events` est déclaré dans `ReportAgent._define_tools` et exécutable dans `_execute_tool`. Il permet au LLM de filtrer les événements par requête textuelle, nom ou identifiant de persona, plateforme, plage de rounds (`round_min`, `round_max`) ou type d'action (`post`, `comment`, `like`, `retweet`, `follow`). Le retour textuel formate clairement chaque fait avec son `event_id` authentifié. | Test unitaire simulant l'appel de `query_simulation_events` avec divers filtres et vérifiant la conformité du format textuel renvoyé au LLM. |
| **AC4** | **Bouclier ReACT `ToolShield` anti-burn d'itérations** : Lorsque le LLM appelle un outil de recherche (`quick_search`, `panorama_search`, `insight_forge`) avec des paramètres vides (`params: {}` ou `query=""`), `ToolShield` intercepte l'appel avant transmission au store et injecte automatiquement un terme de repli pertinent dérivé du contexte actif (`section_title` ou `simulation_requirement`). Si une exception de validation (`GraphValidationError`) survient, `ToolShield` la capture et retourne une observation textuelle constructive au lieu de lever une exception non gérée. 0 crash, 0 burn prématuré vers la génération forcée (C3, NFR-04). | Test unitaire hermétique exécutant `quick_search` et `panorama_search` avec arguments vides ou invalides et vérifiant l'absence d'exception, la substitution du terme de recherche et la conservation du budget ReACT. |
| **AC5** | **Déterminisme strict d'assignation au Round 0 (`SimulationConfigGenerator`)** : Dans `SimulationConfigGenerator`, l'assignation des `initial_posts` (`_assign_initial_post_agents`) privilégie en priorité absolue la correspondance exacte et insensible à la casse du nom du persona (`entity_name`), puis la mention explicite du nom dans le texte du post, avant tout repli par type générique (`poster_type`). 100 % des posts ciblés pour un persona (ex: Émilie, Sylvie, Christine) lui sont attribués sans aucune permutation aléatoire (C6). | Test unitaire hermétique injectant des configurations avec personas homonymes ou de même type et vérifiant l'exactitude stricte de l'attribution sur 10 exécutions consécutives. |
| **AC6** | **Distinction épistémique stricte entre action réelle et intention textuelle** : Le système empêche toute confusion entre une intention déclarée dans un message (ex: « Je vais résilier ») et une action effective consignée dans le registre d'événements. Les faits retournés par `query_simulation_events` garantissent `is_action_executed = True`. Les données d'événements et citations sont injectées dans le prompt du rapport comme données passives strictement étanches sans instruction exécutable (NFR-05). | Test unitaire validant qu'une intention non suivie d'action est signalée comme non exécutée et qu'aucune injection passive ne corrompt le prompt. |
| **AC7** | **Non-régression et couverture hermétique du filet** : Tous les tests existants du dépôt restent au vert (1 663 tests). Une suite dédiée d'au moins 12 tests hermétiques dans `backend/tests/test_oasis_log_reader_toolshield.py` couvre exhaustivement AC1 à AC6. | Exécution complète de `pytest tests/` sans aucun échec ni warning imprévu. |

---

## Définition de fini

- [x] Critères d'acceptation **AC1 à AC7** satisfaits et vérifiés par des tests automatisés passants.
- [x] Modèle `EvidencePack` et `ObservedEvent` créés dans `backend/app/models/evidence_pack.py`.
- [x] Service `OasisLogReaderService` implémenté dans `backend/app/services/oasis_log_reader.py` avec indexation multi-sources (JSONL et SQLite) et calcul déterministe d'`event_id`.
- [x] Outil ReACT `query_simulation_events` opérationnel dans `ReportAgent` et `ZepToolsService` avec filtres multi-critères.
- [x] Bouclier `ToolShield` actif dans `ReportAgent._execute_tool`, éliminant 100 % des exceptions de requêtes vides et protégeant le budget de 5 itérations ReACT.
- [x] Algorithme d'assignation au Round 0 dans `SimulationConfigGenerator` corrigé avec garantie de correspondance nominative stricte (0 permutation de personas).
- [x] Étanchéité épistémique garantie entre intention verbale et action observée effective.
- [x] Suite de tests hermétiques créée dans `backend/tests/test_oasis_log_reader_toolshield.py`.
- [x] Filet global de tests maintenu et accru ($\ge 1 675$ tests réussis sur l'hôte) et parité Docker validée.
- [x] `uv run python backend/scripts/validate_plans.py` et `uv run ruff check backend/` validés sans anomalie.
- [x] Revue contradictoire BMAD à 4 couches réalisée avec findings consignés et résolus.
- [x] Synchronisation des documents de suivi (`epic-011.md`, `sprint-status.yaml`, `STATUS.md`, `AGENTS.md`).

---

## Tâches

- [x] **T1 — Modèle de données `EvidencePack` et `ObservedEvent`** :
  - Créer `backend/app/models/evidence_pack.py`.
  - Définir la dataclass `ObservedEvent` : `event_id`, `simulation_id`, `platform`, `round_num`, `agent_id`, `agent_name`, `action_type`, `action_args`, `timestamp`, `is_action_executed`, `result`, `success`, `raw_payload`.
  - Définir la classe `EvidencePack` : `simulation_id`, `total_events`, `events_by_platform`, `events_by_type`, `events_by_agent`, `events`, `rounds_range`, méthodes `filter_events()`, `to_dict()`, `to_text()`.
- [x] **T2 — Implémentation du service `OasisLogReaderService`** :
  - Créer `backend/app/services/oasis_log_reader.py`.
  - Implémenter l'extraction multi-sources : `twitter/actions.jsonl`, `reddit/actions.jsonl`, `actions.jsonl` racine et tables SQLite d'environnement (`post`, `comment`).
  - Intégrer le calcul d'`event_id` déterministe via `SimulationActionVerifier.compute_event_id` avec gestion de repli d'horodatage stable.
  - Mettre en place un cache mémoire indexé avec invalidation par horodatage de modification `mtime`.
  - Implémenter les méthodes de recherche `query_events(simulation_id, query, agent_name, platform, round_min, round_max, action_type, limit)` et d'assemblage `build_evidence_pack(simulation_id)`.
- [x] **T3 — Bouclier d'outils ReACT `ToolShield` dans `ReportAgent`** :
  - Implémenter la logique `ToolShield` (module dédié `backend/app/services/tool_shield.py` ou intercepteur défensif dans `ReportAgent._execute_tool`).
  - Intercepter les paramètres vides ou non renseignés (`params: {}`, `query=""`, `query: None`) pour `quick_search`, `panorama_search` et `insight_forge`.
  - Injecter un terme de recherche de repli pertinent dérivé de `report_context`, `section.title` ou `simulation_requirement`.
  - Intercepter `GraphValidationError` et exceptions similaires pour retourner un message d'observation clair et instructif au LLM sans lever d'exception non gérée.
  - Tracer chaque activation de `ToolShield` dans les logs d'exécution du rapport.
- [x] **T4 — Intégration de l'outil `query_simulation_events`** :
  - Déclarer l'outil `query_simulation_events` dans `ReportAgent._define_tools` et `VALID_TOOL_NAMES`.
  - Implémenter la méthode correspondante dans `ZepToolsService` et son exécution dans `ReportAgent._execute_tool`.
  - Mettre en forme le résultat sous forme de texte clair et exploitable par le LLM, mettant en avant `event_id`, le round, la plateforme, l'auteur et les arguments d'action.
- [x] **T5 — Déterminisme nominatif de l'assignation au Round 0 (`SimulationConfigGenerator`)** :
  - Mettre à jour le prompt de `_generate_event_config` pour inciter le modèle à renseigner `poster_persona` ou `poster_name` parmi la liste des agents cibles disponibles.
  - Refondre `_assign_initial_post_agents` :
    1. Résolution prioritaire par correspondance exacte et insensible à la casse avec `agent.entity_name`.
    2. Détection du nom du persona dans le texte du post (`post["content"]`).
    3. Résolution secondaire par `poster_type` et alias d'entités avec rotation équitable.
    4. Repli stable par influence sans aléa.
  - Valider l'élimination de toute inversion de persona sur le cas Keova.
- [x] **T6 — Étanchéité épistémique action vs intention** :
  - Consolider le lien entre `OasisLogReaderService` et `SimulationActionVerifier`.
  - Veiller à ce que les actions d'intention identifiées par motifs textuels ne soient jamais labellisées `is_action_executed = True` sans événement correspondant dans les traces.
  - Encapsuler les observations d'événements comme données passives étanches dans les messages ReACT.
- [x] **T7 — Suite de tests hermétiques dédiée** :
  - Créer `backend/tests/test_oasis_log_reader_toolshield.py`.
  - Couvrir les cas : parsing JSONL et SQLite, calcul déterministe d'`event_id`, filtrage multi-critères, activation de `ToolShield` sur requête vide, récupération après erreur de validation de store, déterminisme d'assignation nominative Round 0, et étanchéité action/intention.
- [x] **T8 — Validation globale, exécution des suites et revue BMAD** :
  - Exécuter la suite complète des tests backend (`uv run pytest tests/`).
  - Vérifier la parité sous conteneur Docker.
  - Conduire la revue contradictoire BMAD à 4 couches et consigner les résolutions.

---

## Notes de développement

### 1. Problématique du burn d'itérations ReACT par requête vide (Défaut A.2)

Dans l'état actuel de `ReportAgent` et `GraphitiGraphStore` :
```
LLM ReACT loop (iteration 1/5)
    └──> <tool_call>{"name": "quick_search", "parameters": {}}</tool_call>
             └──> quick_search(query="")
                      └──> store.search(query="")
                               └──> raise GraphValidationError("Le texte de recherche query est requis")
                                        └──> _execute_tool attrape l'erreur : "工具执行失败: Le texte de recherche query est requis"
                                                 └──> LLM perçoit l'échec sans donnée
LLM ReACT loop (iteration 2/5)
    └──> Réessaie ou tente interview_agents (qui échouait avant Story 011-1)
             └──> Quota de 5 itérations épuisé
                      └──> Bascule forcée : "reached max iterations, forcing generation"
                               └──> Section générée à l'aveugle sans facts pertinents !
```

Avec le bouclier `ToolShield` (Story 011-2) :
```
LLM ReACT loop (iteration 1/5)
    └──> <tool_call>{"name": "quick_search", "parameters": {}}</tool_call>
             └──> ToolShield détecte query="" ou manquante
                      ├──> Loggue : "[ToolShield] Requête vide interceptée pour quick_search"
                      ├──> Substitue query = section.title (ex: "Réaction des indépendants face au tarif Keova")
                      └──> quick_search(query="Réaction des indépendants face au tarif Keova")
                               └──> store.search(...) renvoie 10 faits pertinents avec scoring hybride
                                        └──> LLM reçoit des données réelles dès l'itération 1 !
```

### 2. Problématique de l'inversion des personas au Round 0 (Défaut A.3)

Dans l'implémentation historique de `SimulationConfigGenerator._assign_initial_post_agents` :
```python
# Groupement aveugle par type d'entité générique :
agents_by_type["person"] = [Agent(Christine), Agent(Sylvie), Agent(Émilie)]
# Assignation par modulo séquentiel sans égard au nom du persona :
idx = used_indices.get("person", 0) % len(agents)  # Inversion fatale !
```

Avec la refonte nominative déterministe (Story 011-2) :
1. Recherche directe : `agent.entity_name.strip().lower() == target_name.strip().lower()`.
2. Détection contextuelle : si le contenu du post mentionne « En tant qu'Émilie... » ou « Émilie : ... », liaison prioritaire vers l'agent Émilie.
3. Repli sécurisé par type uniquement si aucun persona n'est nommé.

### 3. Architecture du Registre d'Événements (`OasisLogReaderService`)

```
simulations/<sim_id>/
    ├── twitter/actions.jsonl ──┐
    ├── reddit/actions.jsonl  ──┼──> OasisLogReaderService.load_events()
    ├── actions.jsonl         ──┤        ├──> compute_event_id(...) [evt_<platform>_<round>_<agent>_<sha256>]
    └── simulation.db (SQLite)──┘        ├──> indexation multi-clés [platform, round, agent, type]
                                         └──> EvidencePack (statistiques & timeline)
                                                  │
                                                  ▼
                               ReportAgent._execute_tool("query_simulation_events")
                                                  │
                                                  ▼
                               LLM reçoit faits prouvés & event_id pour ses assertions
```

---

## Revue

### Review Findings (Revue contradictoire BMAD à 4 couches)

- [x] [Review][Patch] Sécurisation de l'extraction numérique (`round`, `agent_id`) dans `OasisLogReaderService` (`load_events` et `_load_sqlite_records`) contre `NoneType`/`TypeError` et encapsulation par ligne [`backend/app/services/oasis_log_reader.py:320-345`]
- [x] [Review][Patch] Gestion résiliente des ressources SQLite (`try ... finally: conn.close()`) et fermeture du curseur dans `_load_sqlite_records` [`backend/app/services/oasis_log_reader.py:404-528`]
- [x] [Review][Patch] Détection étendue dans `ToolShield.sanitize_parameters` pour les chaînes vides sérialisées (`"{}"`, `"[]"`, `"null"`, `"\"\""`, `"<empty>"`, `"none"`) [`backend/app/services/tool_shield.py:906-920`]
- [x] [Review][Patch] Unification du traitement d'erreurs ToolShield dans `ReportAgent._execute_tool` via `ToolShield.execute_with_shield` [`backend/app/services/report_agent.py:597-655`]
- [x] [Review][Patch] Sécurisation défensive des paramètres `agent.entity_name` dans `SimulationConfigGenerator` et durcissement des correspondances partielles nominatives [`backend/app/services/simulation_config_generator.py:711-768`]
- [x] [Review][Patch] Sécurisation des arguments de conversion de `query_simulation_events` (`limit`, `round_min`, `round_max`) dans `ReportAgent._execute_tool` [`backend/app/services/report_agent.py:619-628`]
- [x] [Review][Patch] Clôture des cases de tâches T8 et mise à niveau de la Définition de fini dans `story-011-2.md` pour validation complète de `validate_plans.py` [`docs/plans/011-preuve-simulation-et-fiabilite-rapport/story-011-2.md:72-128`]
- [x] [Review][Patch] Ajout de tests unitaires hermétiques couvrant la résilience aux entrées malformées et l'interception ToolShield [`backend/tests/test_oasis_log_reader_toolshield.py`]

#### Rejected findings
- *[Rejected / False]* Troncature brute Unicode dans `query_simulation_events` : les découpes de chaînes en Python 3 opèrent sur les points de code Unicode, aucun risque de corruption d'octet.
- *[Rejected / Low]* Purge complète de simulation avec mtime à 0 : cas limite hors cycle nominal de simulation ne justifiant pas de complexité additionnelle.

---

## Notes de complétion

La Story 011-2 a été complétée et validée avec succès :

1. **Registre d'événements observés (`OasisLogReaderService`, `EvidencePack`)** :
   - Ingestion et normalisation multi-sources : flux JSONL (`twitter/actions.jsonl`, `reddit/actions.jsonl`, `actions.jsonl` racine) et bases SQLite (`simulation.db`, tables `post`, `comment`).
   - Identifiant stable et déterministe `event_id` calculé via `SimulationActionVerifier.compute_event_id` (`evt_<platform>_<round>_<agent>_<sha256>`), éliminant tout aléa temporel et assurant la reproductibilité des citations.
   - Cache mémoire dynamique indexé avec invalidation déterministe basée sur `mtime`.
   - Méthodes d'agrégation `build_evidence_pack` et de requêtage multi-critères `query_events`.

2. **Bouclier `ToolShield` et résilience ReACT** :
   - Interception défensive systématique des requêtes vides (`{}`, `""`, `null`, `"<empty>"`, `"none"`, etc.) pour `quick_search`, `panorama_search`, `insight_forge` et injection contextuelle du titre de section ou du besoin de simulation.
   - Encapsulation des exceptions techniques de store (`GraphValidationError`) transformées en observations exploitables sans lever d'exception non gérée, protégeant l'intégralité du quota de 5 itérations ReACT.
   - Traces d'activation explicites dans les logs d'exécution.

3. **Outil d'accès direct aux preuves `query_simulation_events`** :
   - Exposition dans `ReportAgent._define_tools` et `ZepToolsService`.
   - Filtrage paramétrable par agent, plateforme, round, type d'action et recherche textuelle.
   - Formatage prêt à l'emploi pour le LLM avec citations authentifiées et horodatages.

4. **Déterminisme d'assignation au Round 0 (`SimulationConfigGenerator`)** :
   - Résolution prioritaire par correspondance exacte insensible à la casse avec `agent.entity_name`, éliminant 100 % des permutations d'identités observées sur les personas (Christine, Sylvie, Émilie).
   - Détection nominative dans le contenu du post et repli ordonné par influence.

5. **Revue BMAD 4 couches et durcissement** :
   - 8 patches de durcissement appliqués (sécurisation numérique des entrées JSONL/SQLite, fermeture résiliente des connexions SQLite sous `finally:`, assainissement étendu ToolShield, conversions typées dans `_execute_tool`, robustesse nominative dans `SimulationConfigGenerator`, 4 nouveaux tests unitaires hermétiques).
   - Suite `test_oasis_log_reader_toolshield.py` portée de 13 à 17 tests unitaires au vert.
   - Suite complète hôte portée à 1 677 tests collectés et réussis (0 échec).
