---
id: "003-4"
epic: "003"
titre: "Adaptation du chemin de lecture (zep_entity_reader.py) pour les entités génériques Graphiti"
statut: in-progress
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

- [ ] `EntityNode.get_entity_type()` et `GraphNode.get_entity_type()` résolvent le type métier via les custom labels, ou à défaut via les attributs (`entity_type`, `type`, `category`), ou à défaut se replient sur `"Entity"` (ne renvoient plus `None` pour un nœud portant `:Entity`)
- [ ] `zep_entity_reader.py:filter_defined_entities()` n'ignore plus les nœuds ne portant que le label générique `:Entity`
- [ ] Si `defined_entity_types` est spécifié (liste non vide), le filtrage accepte les nœuds dont le type résolu (ou l'un des labels) correspond, et supporte explicitement `"Entity"`
- [ ] Si `defined_entity_types` est `None` ou vide, tous les nœuds valides du graphe sont retenus (0 rejet silencieux d'entités valides)
- [ ] `get_entities_by_type()` permet d'extraire les entités par type résolu (notamment `entity_type="Entity"`)
- [ ] `get_entity_with_context()` retourne un `EntityNode` complet, typé et enrichi de ses arêtes incidentes pour les entités Graphiti
- [ ] Les flux consommateurs (`simulation_config_generator._summarize_entities`, `oasis_profile_generator.generate_profiles_from_entities`) exploitent avec succès les entités typées `"Entity"` avec leur nom et résumé
- [ ] Une suite de tests unitaires hermétiques mockés couvre exhaustivement les cas de filtrage (Zep avec labels, Graphiti générique, typage par attributs, filtrage avec et sans liste de types)
- [ ] Non-régression totale : 100 % des tests existants restent au vert (`uv run pytest tests/ -q` ≥ 545 tests)
- [ ] Outils de qualité validés : `uv run ruff check .` et `uv run python scripts/validate_plans.py` passent sans avertissement

## Tâches

- [ ] Adapter la méthode `get_entity_type()` sur `EntityNode` (`zep_entity_reader.py`) et `GraphNode` (`base.py`) avec résolution ordonnée (labels métier > attributs `entity_type`/`type`/`category` > `"Entity"`)
- [ ] Mettre à jour la logique de filtrage dans `zep_entity_reader.py:filter_defined_entities()` pour lever le blocage systématique `if not custom_labels: continue`
- [ ] Implémenter la logique de correspondance pour `defined_entity_types` prenant en compte le type résolu et le type générique
- [ ] Valider le comportement de `get_entities_by_type()` et `get_entity_with_context()` pour les entités Graphiti
- [ ] Créer une suite de tests unitaires dédiée dans `backend/tests/test_zep_entity_reader_graphiti.py` vérifiant tous les scénarios de lecture et de filtrage
- [ ] Vérifier la non-régression des tests existants de lecture (`test_graph_reader_refactor.py`, `test_zep_entity_reader_edges.py`)
- [ ] Valider l'intégration avec `simulation_config_generator` et `oasis_profile_generator`
- [ ] Exécuter la suite complète de tests (`pytest`), le linter (`ruff`) et la validation de structure (`validate_plans.py`)

## Notes de développement

- **Chaîne de résolution de type d'entité** :
  La méthode `get_entity_type()` doit suivre une résolution déterministe :
  1. Étiquettes spécifiques (labels autres que `"Entity"` et `"Node"`) : si présentes, la première étiquette spécifique constitue le type métier (cas nominal Zep Cloud ou future ontologie v2).
  2. Attributs du nœud : si le nœud possède un dictionnaire d'attributs contenant `"entity_type"`, `"type"` ou `"category"`, cette valeur est utilisée.
  3. Repli générique : si le nœud porte le label `"Entity"` ou `"Node"`, son type est `"Entity"`.
  4. Si aucun label ni attribut de type n'existe, retourne `None`.

- **Logique de filtrage dans `filter_defined_entities`** :
  ```python
  for node in all_nodes:
      labels = node.get("labels", [])
      attributes = node.get("attributes", {})
      
      # 1. Custom labels spécifiques (compatibilité ontologie Zep Cloud)
      custom_labels = [l for l in labels if l not in ["Entity", "Node"]]
      
      # 2. Détermination des types candidats
      if custom_labels:
          candidate_types = custom_labels
      else:
          inferred = (
              attributes.get("entity_type")
              or attributes.get("type")
              or attributes.get("category")
              or ("Entity" if ("Entity" in labels or "Node" in labels) else None)
          )
          candidate_types = [inferred] if inferred else []
      
      # Si aucun type ne peut être attribué au nœud, on le rejette
      if not candidate_types:
          continue
      
      # 3. Filtrage selon defined_entity_types (si renseigné)
      if defined_entity_types:
          matching = [t for t in candidate_types if t in defined_entity_types]
          if not matching:
              continue
          entity_type = matching[0]
      else:
          entity_type = candidate_types[0]
      
      entity_types_found.add(entity_type)
      # Création du EntityNode et enrichissement...
  ```

- **Consommation par les personas et la simulation** :
  Dans `simulation_config_generator.py` et `oasis_profile_generator.py`, le regroupement et l'analyse s'appuient sur `entity.get_entity_type() or "Entity"` ainsi que sur `entity.name` et `entity.summary`.
  Le repli sur `"Entity"` permet aux prompts LLM de contextualiser les acteurs de la simulation à partir de leur description textuelle et de leurs faits relationnels sans blocage.

## Revue

- **Revue contradictoire BMad (prévue lors du passage en `review`)** :
  - *Critère C4 du PRD* : Vérifier qu'un graphe peuplé d'entités avec label unique `:Entity` retourne un ensemble non vide d'entités exploitables (`filtered_count > 0`).
  - *Non-régression Zep Cloud (NFR-1)* : Vérifier que les comportements existants avec labels d'ontologie custom restent strictement inchangés.
  - *Clean Architecture (NFR-2)* : S'assurer qu'aucun import direct de `graphiti_core` ou de bibliothèques tierces n'est introduit dans `zep_entity_reader.py`.
  - *Gestion des cas limites* : Nœuds sans labels, attributs vides, `defined_entity_types` ciblant `"Entity"`, `None` ou types inconnus.

## Notes de complétion

- Story en cours de cadrage et de développement initial (statut `in-progress`).
- Les notes de complétion définitives seront rédigées à l'issue de l'implémentation, de la suite de tests et de la revue contradictoire BMad.
