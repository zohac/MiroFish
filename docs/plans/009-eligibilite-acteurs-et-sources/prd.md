# PRD — Epic 009 : Éligibilité des acteurs et fiabilisation des sources

- **Statut** : `backlog` · **Dépend de** : 004, 005 · **Bloque** : 007
- **Suivi** : [`sprint-status.yaml`](../../sprint-status.yaml)
- **Origine** : Rapport d'audit du 10 octobre 2026 (qualification sémantique et fiabilisation multi-documents)

> L'Epic 005 a scellé l'environnement Docker de référence autonome (711 tests verts, Verdict GO).  
> La tuyauterie technique (Graphiti + Neo4j local, persistance des volumes, conteneurisation) est opérationnelle.  
>
> **L'Epic 009 résout la rupture sémantique fondamentale identifiée lors de l'audit réel** : l'assimilation aveugle d'une entité du graphe de connaissances à un acteur social de simulation. Il introduit un chaînage rigoureux et agnostique :  
> *sources typées → faits traçables → entités du graphe → acteurs éligibles → personas OASIS → simulation → rapport sourcé*.

---

## 1. Le problème

### 1.1 Contexte et constats de l'audit

Deux simulations réelles construites sur des cas d'usage concrets ont démontré que l'infrastructure technique fonctionnait, mais ont révélé des anomalies sémantiques sévères :
1. **Confusion entre entité de connaissances et acteur simulable (P0)** :
   - Dans `backend/app/services/oasis_profile_generator.py`, toute entité non reconnue comme individu dans une liste fermée est traitée par `_build_group_persona_prompt` comme une « organisation / groupe ».
   - En mode Graphiti v1 (sans ontologie custom), toutes les entités reçoivent le label générique `:Entity`.
   - Conséquence : des produits (ex: un nom de logiciel), des formules tarifaires, des URLs, des domaines web ou des concepts abstraits sont transformés en comptes sociaux simulés, tweetant ou publiant sur Reddit en prétendant être des personnes ou des praticiennes.
2. **Absence de contrôle qualité préalable (P0)** :
   - Le passage du graphe aux profils OASIS est aveugle et instantané. L'utilisateur ne dispose d'aucune étape de révision pour valider ou corriger les acteurs retenus avant que la simulation ne soit lancée.
3. **Aplatissement des sources et perte de traçabilité (P1)** :
   - Dans `backend/app/api/graph.py`, les fichiers uploadés sont concaténés sans conservation structurée de leurs rôles (faits avérés, scénarios, hypothèses, contraintes).
   - Les fragments ingérés dans `backend/app/utils/graph_store/graphiti_store.py` portent une description anonyme (`chunk_1`), sans liaison exploitable vers le fichier ou la section d'origine.
   - Les relations Neo4j portent `r.episodes` mais ne peuvent remonter formellement à un document source structuré.
4. **Perte du contexte utilisateur (P1)** :
   - Le champ `additional_context` passé lors de la génération d'ontologie n'est pas persisté dans `backend/app/models/project.py` et est ignoré par les étapes de simulation et de génération de personas.
5. **Rapport final équivoque sur les preuves (P1)** :
   - Le `ReportAgent` ne sépare pas formellement les faits documentés dans les sources, les événements fictifs observés lors de la simulation OASIS et les inférences analytiques du LLM.

---

## 2. L'objectif

Bâtir un sous-système **générique et agnostique** (0 règle métier spécifique, aucun `if Keova` conformément à AGENTS.md §2.1) qui garantit :

1. **Séparation étanche Connaissances vs Acteurs (`ActorEligibility`)** :
   - Une entité extraite du graphe reste un objet de connaissance disponible pour le contexte.
   - Seules les entités explicitement qualifiées comme capables d'action sociale (`person`, `organization` officielle) deviennent des agents OASIS.
   - Les produits, tarifs, offres, sites web, règlements et concepts sont classés `ineligible` et exclus de la génération de profils.
2. **Sources documentaires typées (`SourceDocument`) et traçabilité des fragments** :
   - Chaque fichier importé est modélisé avec un rôle (`facts`, `scenario`, `personas`, `hypotheses`, `constraints`, `reference`) et une date.
   - Chaque fragment (`DocumentChunk`) et chaque épisode Graphiti porte son `source_id`, `filename` et `chunk_index`.
3. **Persistance du contexte de simulation (`SimulationBrief`)** :
   - Un modèle persistant et versionné rattaché au `Project` porte l'objectif, l'état initial, les règles, les hypothèses et les contraintes.
4. **Prévalidation des acteurs avant lancement (IHM / API)** :
   - Une étape d'inspection permet de visualiser les acteurs éligibles, inéligibles et à réviser (`review`), avec possibilité de correction manuelle simple.
5. **Traçabilité des affirmations dans le rapport** :
   - Distinction claire entre fait documenté sourcé, comportement simulé sur OASIS, et synthèse de l'agent d'analyse.

---

## 3. Périmètre

### 3.1 Dans le périmètre
- Modèle de données `ActorEligibility` et service de classification hybride agnostique (filtre déterministe + classifieur LLM structuré léger avec Pydantic).
- Intégration dans `backend/app/services/simulation_manager.py` et `backend/app/services/oasis_profile_generator.py` pour n'accepter que les entités éligibles.
- Modèle `SourceDocument` et enrichissement de `backend/app/models/project.py`.
- Traçabilité des épisodes dans `GraphStore.add_episode()` et `add_text_batch()` reliant `r.episodes` aux documents sources.
- Endpoints REST de prévalidation `/api/simulation/actors/preview` et `/api/simulation/actors/review`.
- Enrichissement des prompts du `ReportAgent` pour labelliser la provenance des conclusions.
- Suite de tests unitaires et d'intégration hermétiques validant la conformité sur au moins 2 cas d'usage distincts.

### 3.2 Hors périmètre
- Ontologie dynamique Graphiti v2 (reste planifiée pour l'Epic 007).
- Modification de la structure interne des profils OASIS (Twitter CSV et Reddit JSON conservent leurs contrats stricts).
- Réécriture lourde du moteur de simulation `camel-oasis`.

---

## 4. Exigences détaillées

### 4.1 Exigences fonctionnelles (FR)

| Réf. | Intitulé | Description |
|---|---|---|
| **FR-1** | Classification d'éligibilité des acteurs | Système à deux passes (déterministe puis LLM structuré) attribuant un rôle (`person`, `organization`, `product`, `concept`, etc.) et une éligibilité (`eligible`, `ineligible`, `review`) avec justification. |
| **FR-2** | Préservation des connaissances non-acteurs | Les entités inéligibles restent dans le graphe Neo4j et demeurent interrogeables pour contextualiser la simulation ; elles ne génèrent aucun agent social. |
| **FR-3** | Documents sources structurés (`SourceDocument`) | Modélisation des fichiers avec rôle (`facts`, `scenario`, `personas`, `hypotheses`, `constraints`, `reference`), statut et priorité. |
| **FR-4** | Persistance du `SimulationBrief` | Sauvegarde durable du contexte et des consignes dans le projet, réinjecté à l'étape de configuration de simulation. |
| **FR-5** | Provenance des faits et fragments | Les nœuds `:Episodic` et les relations `r.episodes` Neo4j contiennent la référence au document et au fragment d'origine. |
| **FR-6** | Prévisualisation et validation des acteurs | Routes API permettant d'inspecter la liste des acteurs avant génération des profils et d'ajuster manuellement leur statut. |
| **FR-7** | Provenance dans le rapport d'analyse | Le rapport final distingue formellement les faits prouvés par les documents des événements simulés. |

### 4.2 Exigences non fonctionnelles (NFR)

| Réf. | Intitulé | Description |
|---|---|---|
| **NFR-1** | Neutralité absolue (Zéro règle en dur) | Aucune heuristique spécifique à un client ou domaine métier dans le code source (bannissement d'expressions codées en dur, vérifié par AST). |
| **NFR-2** | Rétrocompatibilité `GraphStore` | Maintien strict de l'interface `GraphStore` commune à `GraphitiGraphStore` et `ZepGraphStore`. |
| **NFR-3** | Résilience et repli propre | En cas d'indisponibilité ou d'erreur du classifieur LLM, repli sécurisé sur le filtrage déterministe avec marquage `review`. |
| **NFR-4** | Parité Docker et hermétisme | Exécution 100 % validée sous Docker, 0 appel réseau externe obligatoire en mode test. |

---

## 5. Critères de sortie chiffrés (C1 à C5)

| # | Critère | Seuil de succès |
|---|---|---|
| **C1** | **Élimination des faux acteurs** | **0** produit, tarif, URL ou concept abstrait converti en profil social actif sur un jeu d'essai mixte de 20 entités hétérogènes. |
| **C2** | **Validation agnostique multi-domaines** | Classification validée avec succès sur **au moins 2 domaines sans lien** (ex. produit logiciel commercial et rapport parlementaire public) sans modification de code. |
| **C3** | **Traçabilité des faits (Provenance)** | **100 %** des faits extraits dans Neo4j (`r.episodes`) sont traçables jusqu'à leur `SourceDocument` et numéro de fragment. |
| **C4** | **Persistance `SimulationBrief`** | Le brief et le contexte utilisateur sont persistés dans `project.json` et réinjectés sans perte dans les étapes de configuration et de simulation. |
| **C5** | **Filet de tests hermétiques** | 100 % des tests unitaires et d'intégration au vert, régression nulle sur les 711 tests existants. |
