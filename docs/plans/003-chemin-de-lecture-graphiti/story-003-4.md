---
id: "003-4"
epic: "003"
titre: "Adaptation du chemin de lecture (zep_entity_reader.py) pour les entités génériques Graphiti"
statut: done
auteur: agent
format: "2"
---

# Story 003-4 — Adaptation du chemin de lecture (zep_entity_reader.py) pour les entités génériques Graphiti (ADR 0003)

## Pourquoi cette story

Les stories 003-1, 003-2 et 003-3 ont implémenté et validé l'intégralité du backend local `GraphitiGraphStore` : initialisation des dépendances locales, cycle de vie, ingestion d'épisodes, requêtes Cypher de lecture, parcours de voisinage et recherche hybride temporelle (545 tests verts).

Toutefois, une faille structurelle identifiée lors de l'audit initial et consignée dans l'ADR 0003 bloque l'exploitation du graphe par les couches applicatives en aval (préparation de simulation, génération de personas et agents `camel-oasis`) :

1. **Le filtrage aveugle hérité de Zep Cloud (ADR 0003, `LOCAL-FIRST.md` §12.3)** :
   Dans le code amont de `backend/app/services/zep_entity_reader.py:266`, la sélection d'entités repose sur l'hypothèse que Zep Cloud a étiqueté les nœuds avec des classes d'ontologie spécifiques (ex. `:Politician`, `:Organization`, `:Student`) :
   ```python
   custom_labels = [l for l in labels if l not in ["Entity", "Node"]]
   if not custom_labels:
       # Nœud sans label spécifique ignoré silencieusement !
       continue
   ```
   De même, la méthode `EntityNode.get_entity_type()` (lignes 50-55) et `GraphNode.get_entity_type()` (`app/utils/graph_store/base.py`) retournent `None` si le nœud ne porte que les étiquettes standard `"Entity"` ou `"Node"`.

2. **L'incompatibilité avec Graphiti sans ontologie custom (v1)** :
   Conformément à l'arbitrage de l'ADR 0003 (« L'ontologie dynamique est une v2 : le chemin de lecture d'abord »), Graphiti v1 extrait des entités et relations temporelles sans injecter de modèles Pydantic dynamiques au moment de l'extraction. Graphiti persiste par conséquent les nœuds dans Neo4j avec l'unique label `:Entity`.
   En conséquence directe, `filter_defined_entities()` rejette aujourd'hui **100 % des nœuds Graphiti**, et les générateurs de simulation reçoivent une liste vide (`total_count > 0`, mais `filtered_count = 0`). C'était la cause exacte de l'échec des tentatives précédentes constatées dans les forks communautaires.

3. **L'objectif de la Story 003-4 (Critère C4 du PRD)** :
   Adapter `zep_entity_reader.py` et les modèles associés (`EntityNode`, `GraphNode`) pour que le chemin de lecture devienne totalement agnostique de l'origine du graphe :
   - Traiter les nœuds ne portant que le label `:Entity` comme des entités exploitables à part entière ;
   - Résoudre le type d'entité selon une chaîne de priorité élégante : labels spécifiques d'ontologie Zep > attribut explicite (`entity_type`, `type`, `category`) > repli par défaut sur `"Entity"` ;
   - Maintenir une parité et une non-régression absolue pour les graphes Zep Cloud historiques (100 % des tests existants au vert) ;
   - Vérifier la chaîne complète jusqu'à `simulation_config_generator.py` et `oasis_profile_generator.py`.

## Définition de prêt

- [x] Contrat et fonctionnement de `zep_entity_reader.py` audités (`filter_defined_entities`, `get_entity_with_context`, `get_entities_by_type`, `EntityNode.get_entity_type`)
- [x] Décision d'architecture ADR 0003 documentée et approuvée (ontologie dynamique différée en v2, priorité au chemin de lecture)
- [x] Spécification architecturale de la solution définie dans [`architecture.md §6`](architecture.md)
- [x] Backend `GraphitiGraphStore` opérationnel en lecture et recherche (Story 003-3 validée, 545 tests verts)
- [x] Critère d'acceptation C4 du PRD documenté (sur un graphe Graphiti, `get_all_nodes()` et `zep_entity_reader.py` retournent un nombre > 0 d'entités exploitables, 0 nœud filtré à tort)
- [x] Points de couplage dans les services consommateurs identifiés (`simulation_config_generator.py`, `oasis_profile_generator.py`, `api/simulation.py`)
- [x] Documents consultés : [`prd.md`](prd.md), [`architecture.md`](architecture.md), [`epic-003.md`](epic-003.md), [ADR 0001](../../decisions/0001-remplacement-de-zep-par-graphiti.md), [ADR 0003](../../decisions/0003-ontologie-differee-en-v2.md), [AGENTS.md](../../../AGENTS.md)

## Définition de fini

- [x] `EntityNode.get_entity_type()` et `GraphNode.get_entity_type()` résolvent le type métier via les custom labels, ou à défaut via les attributs (`entity_type`, `type`, `category`), ou à défaut se replient sur `"Entity"` (ne renvoient plus `None` pour un nœud portant `:Entity`)
- [x] `zep_entity_reader.py:filter_defined_entities()` n'ignore plus les nœuds ne portant que le label générique `:Entity`
- [x] Si `defined_entity_types` est spécifié (liste non vide), le filtrage accepte les nœuds dont le type résolu (ou l'un des labels) correspond, et supporte explicitement `"Entity"`
- [x] Si `defined_entity_types` est `None` ou vide, tous les nœuds valides du graphe sont retenus (0 rejet silencieux d'entités valides)
- [x] `get_entities_by_type()` permet d'extraire les entités par type résolu (notamment `entity_type="Entity"`)
- [x] `get_entity_with_context()` retourne un `EntityNode` complet, typé et enrichi de ses arêtes incidentes pour les entités Graphiti
- [x] Les flux consommateurs (`simulation_config_generator._summarize_entities`, `oasis_profile_generator.generate_profiles_from_entities`) exploitent avec succès les entités typées `"Entity"` avec leur nom et résumé
- [x] Une suite de tests unitaires hermétiques mockés couvre exhaustivement les cas de filtrage (Zep avec labels, Graphiti générique, typage par attributs, filtrage avec et sans liste de types)
- [x] Non-régression totale : 100 % des tests existants restent au vert (`uv run pytest tests/ -q` ≥ 545 tests)
- [x] Outils de qualité validés : `uv run ruff check .` et `uv run python scripts/validate_plans.py` passent sans avertissement

## Tâches

- [x] Adapter la méthode `get_entity_type()` sur `EntityNode` (`zep_entity_reader.py`) et `GraphNode` (`base.py`) avec résolution ordonnée (labels métier > attributs `entity_type`/`type`/`category` > `"Entity"`)
- [x] Mettre à jour la logique de filtrage dans `zep_entity_reader.py:filter_defined_entities()` pour lever le blocage systématique `if not custom_labels: continue`
- [x] Implémenter la logique de correspondance pour `defined_entity_types` prenant en compte le type résolu et le type générique
- [x] Valider le comportement de `get_entities_by_type()` et `get_entity_with_context()` pour les entités Graphiti
- [x] Créer une suite de tests unitaires dédiée dans `backend/tests/test_zep_entity_reader_graphiti.py` vérifiant tous les scénarios de lecture et de filtrage
- [x] Vérifier la non-régression des tests existants de lecture (`test_graph_reader_refactor.py`, `test_zep_entity_reader_edges.py`)
- [x] Valider l'intégration avec `simulation_config_generator` et `oasis_profile_generator`
- [x] Exécuter la suite complète de tests (`pytest`), le linter (`ruff`) et la validation de structure (`validate_plans.py`)

### Review Findings

- [x] [Review][Patch] Sécurisation null-safe sur labels et attributes (node.get() or {}) pour parer aux dictionnaires à champs None [backend/app/services/zep_entity_reader.py:279-280, 325-326]
- [x] [Review][Patch] Filtrage des labels vides ou constitués d'espaces dans EntityNode.get_entity_type et GraphNode.get_entity_type [backend/app/services/zep_entity_reader.py:33-35, backend/app/utils/graph_store/base.py:137-139]
- [x] [Review][Patch] Tests unitaires hermétiques validant la robustesse face aux nœuds contenant des valeurs None [backend/tests/test_zep_entity_reader_graphiti.py]

#### Rejected

- [Rejet des attributs si un custom label est présent lors du filtrage] : rejeté (`false`) — Conforme à l'arbitrage architectural d'une cascade exclusive ordonnée : custom label d'ontologie > attribut > générique Entity.
- [Duplication de MockGraphitiStore dans test_zep_entity_reader_graphiti.py] : rejeté (`low`) — Hermétisme et indépendance des fichiers de tests unitaires préférés au couplage inter-tests.
- [Sensibilité stricte à la casse et aux espaces sur defined_entity_types] : rejeté (`low`) — Respect du contrat de typage Zep amont (noms d'entités stricts en PascalCase).

## Notes de développement

- **Chaîne de résolution de type d'entité** :
  La méthode `get_entity_type()` sur `EntityNode` et `GraphNode` suit désormais une résolution déterministe en cascade :
  1. Étiquettes spécifiques (labels autres que `"Entity"` et `"Node"`) : si présentes, la première étiquette spécifique constitue le type métier (cas nominal Zep Cloud ou future ontologie v2).
  2. Attributs du nœud : si le nœud possède un dictionnaire d'attributs contenant `"entity_type"`, `"type"` ou `"category"`, cette valeur est utilisée.
  3. Repli générique : si le nœud porte le label `"Entity"` ou `"Node"`, son type est `"Entity"`.
  4. Si aucun label ni attribut de type n'existe (nœud corrompu / vide), retourne `None`.

- **Logique de filtrage dans `filter_defined_entities`** :
  - Détermination des types candidats : `custom_labels` si présents, sinon attributs (`entity_type`/`type`/`category`), sinon `["Entity"]` si `"Entity"` ou `"Node"` dans `labels`.
  - Rejet des nœuds sans aucun type candidat identifiable.
  - Correspondance avec `defined_entity_types` : si spécifié, matching sur `candidate_types` puis sur l'ensemble des `labels`.
  - Si `defined_entity_types` est `None` ou vide, tous les nœuds valides sont retenus (0 rejet silencieux).

- **Consommation par les personas et la simulation** :
  Dans `simulation_config_generator.py` et `oasis_profile_generator.py`, le regroupement et l'analyse s'appuient sur `entity.get_entity_type() or "Entity"` ainsi que sur `entity.name` et `entity.summary`.
  Le repli sur `"Entity"` permet aux prompts LLM de contextualiser les acteurs de la simulation à partir de leur description textuelle et de leurs faits relationnels sans blocage.

## Revue

- **Revue contradictoire BMad (9 octobre 2026)** :
  1. *Critère C4 du PRD (Validation Graphiti)* : Un graphe avec label unique `:Entity` retourne désormais 100 % de ses entités exploitables via `filter_defined_entities(graph_id)` et `get_all_nodes(graph_id)` (`filtered_count == total_count > 0`).
  2. *Non-régression Zep Cloud (NFR-1)* : Les nœuds dotés de labels d'ontologie spécifiques (ex: `:Politician`, `:Student`) conservent leur priorité de typage et leur comportement de filtrage ciblé.
  3. *Clean Architecture & Découplage (NFR-2)* : Aucun import direct de `graphiti_core` ou de bibliothèques tierces dans `zep_entity_reader.py` ni dans `oasis_profile_generator.py`. Respect strict de l'AST et de la hiérarchie en couches.
  4. *Résolution de type déterministe* : Parité stricte entre `EntityNode.get_entity_type()` et `GraphNode.get_entity_type()`.
  5. *Gestion des cas limites et 3 patchs BMad appliqués* : Sécurisation null-safe défensive sur `labels` et `attributes` (support des clés `None` et conversion flexible dict / `GraphNode`), filtrage strict des labels vides ou constitués d'espaces avec `.strip()`, et test unitaire dédié couvrant l'ensemble de ces cas limites.
  6. *Filet de sécurité* : 555 tests unitaires et d'intégration au vert (+10 tests hermétiques dédiés). Lint `ruff` et `validate_plans.py` impeccables.

## Notes de complétion

- **Date de complétion** : 9 octobre 2026.
- **Bilan d'implémentation** :
  - Adaptation de `GraphNode.get_entity_type()` (`app/utils/graph_store/base.py`) et `EntityNode.get_entity_type()` (`app/services/zep_entity_reader.py`) avec la chaîne ordonnée (labels spécifiques > attributs `entity_type`/`type`/`category` > `"Entity"` > `None`).
  - Refonte de `filter_defined_entities` dans `zep_entity_reader.py` : suppression du blocage systématique sur `:Entity`, support du typage agnostique et filtrage ciblé avec ou sans `defined_entity_types`.
  - Mise à jour des contrats de tests existants (`test_graph_store_contract.py`, `test_graph_reader_refactor.py`).
  - Création de la suite de tests dédiée `backend/tests/test_zep_entity_reader_graphiti.py` (10 tests couvrant l'ensemble des scénarios de filtrage, lecture de contexte, enrichissement relationnel, flux consommateurs en aval et cas limites null/whitespace).
  - Intégration et validation des 3 patchs de la revue contradictoire BMad.
  - Total de **555 tests unitaires verts** (+10 tests).
  - Statut : **VALIDÉ / DONE**.
