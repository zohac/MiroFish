# PRD — Epic 009 : Éligibilité des acteurs et fiabilisation des sources

- **Statut** : `backlog` · **Dépend de** : 004, 005 · **Bloque** : 007
- **Suivi** : [`sprint-status.yaml`](../../sprint-status.yaml)
- **Origine** : [rapport d'audit du 10 octobre 2026](rapport-audit-mirofish-local-first.md), ajouté pendant la reprise ; [revue de cohérence versionnée](revue-coherence-2026-10-10.md).
- **Nature** : cible proposée, aucune story démarrée ; les arbitrages ouverts sont recensés dans la revue.
- **Traçabilité du rapport source** : [matrice de couverture](couverture-rapport-audit.md), recommandations retenues, preuves attendues et écarts encore à arbitrer.

> L'Epic 005 a scellé l'environnement Docker de référence autonome (711 tests verts, Verdict GO).  
> La tuyauterie technique (Graphiti + Neo4j local, persistance des volumes, conteneurisation) est opérationnelle.  
>
> **L'Epic 009 résout la rupture sémantique fondamentale identifiée lors de l'audit réel** : l'assimilation aveugle d'une entité du graphe de connaissances à un acteur social de simulation. Il introduit un chaînage rigoureux et agnostique :  
> *sources typées → faits traçables → entités du graphe → acteurs éligibles → personas OASIS → simulation → rapport sourcé*.

---

## 1. Le problème

### 1.1 Contexte et constats de l'audit

Le cadrage initial rapporte deux simulations réelles, mais ne fournit ni identifiants ni sorties permettant de les reproduire. Le rapport d'audit désormais joint décrit deux runs commerciaux autour d'une même offre : ils ne constituent pas une validation sur deux domaines distincts. Les défauts suivants sont confirmés par lecture du code ; la [revue](revue-coherence-2026-10-10.md) donne leurs références. La validation multi-domaines reste à produire :
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

Bâtir un sous-système **générique et agnostique** (0 règle propre à un client, conformément à AGENTS.md §2.1) qui garantit :

1. **Séparation étanche Connaissances vs Acteurs (`ActorEligibility`)** :
   - Une entité extraite du graphe reste un objet de connaissance disponible pour le contexte.
   - Seules les entités explicitement qualifiées comme capables d'action sociale (`person`, `organization` officielle) deviennent des agents OASIS.
   - Les produits, tarifs, offres, sites web, règlements et concepts sont classés `ineligible` et exclus de la génération de profils.
2. **Sources documentaires typées (`SourceDocument`) et traçabilité des fragments** :
   - Chaque fichier importé est modélisé avec un rôle (`facts`, `scenario`, `personas`, `hypotheses`, `constraints`, `reference`) et une date.
   - Chaque fragment (`DocumentChunk`) et chaque épisode documentaire Graphiti porte `source_document_id`, `source_filename` et `chunk_index` (index local au document, base 0).
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
- Acheminement des références de sources via `GraphStore` et `ZepToolsService` jusqu'au `ReportAgent`, puis présentation distincte des documents, observations simulées et inférences.
- Suite de tests unitaires et d'intégration hermétiques validant la conformité sur au moins 2 cas d'usage distincts.

### 3.2 Hors périmètre
- Ontologie dynamique Graphiti v2 (reste planifiée pour l'Epic 007).
- Modification de la structure interne des profils OASIS (Twitter CSV et Reddit JSON conservent leurs contrats stricts).
- Réécriture lourde du moteur de simulation `camel-oasis`.
- Reconstruction automatique de la provenance de graphes anciens ou migrés depuis Zep : une référence absente est signalée comme inconnue, jamais inventée.
- Localisation globale de l'application (Epic 008) ; l'interface de prévalidation ciblée par FR-6 appartient bien à cet epic.

---

## 4. Exigences détaillées

### 4.1 Exigences fonctionnelles (FR)

| Réf. | Intitulé | Description |
|---|---|---|
| **FR-1** | Classification d'éligibilité des acteurs | Système à deux passes (déterministe puis LLM structuré) attribuant un rôle (`person`, `organization`, `product`, `concept`, etc.) et une éligibilité (`eligible`, `ineligible`, `review`) avec justification. |
| **FR-2** | Préservation des connaissances non-acteurs | Les entités inéligibles restent dans le graphe Neo4j et demeurent interrogeables pour contextualiser la simulation ; elles ne génèrent aucun agent social. |
| **FR-3** | Documents sources structurés (`SourceDocument`) | Fichiers avec rôle, date de validité facultative, priorité choisie et source/auteur facultatifs. Statut de **validation** documentaire et gestion des conflits de sources à spécifier avant 009-2 ; aucune autorité déduite du nom du fichier. |
| **FR-4** | Persistance et utilisation du `SimulationBrief` | Contexte versionné : objectif, horizon, déclencheur, sorties attendues, état initial, audiences/exclusions, règles, hypothèses, références documentaires et `additional_context`. Champs avancés facultatifs. Sauvegarde et transmission à la classification, aux personas et à la configuration ; limites de contexte et pertes éventuelles signalées explicitement. |
| **FR-5** | Provenance des faits et fragments | Épisodes documentaires reliés au document, à l'index et aux positions du fragment dans le texte normalisé ; page/section seulement si connue. `r.episodes` contient leurs UUID. Les épisodes simulés conservent leur origine, simulation et plateforme. |
| **FR-6** | Prévisualisation et validation | Inspection/correction des acteurs avant génération, avec fichiers utilisés, erreurs d'extraction, omissions/troncatures et conflits connus. Revue humaine facultative, contrôle automatique obligatoire ; possibilité de blocage volontaire en présence de `review` ou d'un conflit majeur. |
| **FR-7** | Provenance dans le rapport | Document, hypothèse/scénario, simulation, inférence et origine inconnue distingués. Une action dite observée renvoie à un événement enregistré du run ; un post/intention ne prouve pas une autre action. Sources contradictoires conservées avec règle de résolution explicite, ou « à confirmer ». |

### 4.2 Exigences non fonctionnelles (NFR)

| Réf. | Intitulé | Description |
|---|---|---|
| **NFR-1** | Neutralité absolue (Zéro règle en dur) | Aucune heuristique propre à un client. Revue du code et essais sur deux domaines ; les contrôles AST vérifient les imports et motifs connus, sans prétendre démontrer seuls la neutralité sémantique. |
| **NFR-2** | Rétrocompatibilité `GraphStore` | Les appels existants restent valides. Toute extension de provenance est commune aux deux stores, testée et documentée par ADR avant implémentation ; aucune requête Cypher ni bifurcation de backend dans les services. |
| **NFR-3** | Résilience et repli propre | En cas d'indisponibilité ou d'erreur du classifieur LLM, repli sécurisé sur le filtrage déterministe avec marquage `review`. |
| **NFR-4** | Parité Docker et hermétisme | Exécution 100 % validée sous Docker, 0 appel réseau externe obligatoire en mode test. |
| **NFR-5** | Séparation consignes et sources | Les contenus des fichiers restent des données ; ils ne deviennent ni messages système ni corrections autorisées d'éligibilité. Les règles explicites du brief restent distinctes du texte documentaire. Tests de construction des messages et des arbitrages, sans prétendre prouver une immunité générale du LLM. |

---

## 5. Critères de sortie chiffrés (C1 à C7)

| # | Critère | Seuil de succès |
|---|---|---|
| **C1** | **Élimination des faux acteurs** | **0** produit, tarif, URL ou concept abstrait converti en profil actif sur **au moins 20 entités** réparties sur deux domaines ; **au moins 2 acteurs attendus par domaine** effectivement retenus, pour éviter un succès obtenu en excluant tout. Barrière vérifiée avec et sans LLM de personas. |
| **C2** | **Validation agnostique multi-domaines** | **Au moins 2 domaines sans lien** sans changement de code ; résultats attendus annotés dans les fixtures, plus une mesure du classifieur réel séparée des tests hermétiques, avec modèle, entrées et sorties consignés. Un LLM mocké ne qualifie pas à lui seul le classifieur réel. |
| **C3** | **Traçabilité documentaire** | Sur une ingestion neuve d'**au moins 2 documents de 2 fragments chacun**, **100 %** des relations documentaires ont une liste non vide d'épisodes, dont **toutes** les références se résolvent dans le même graphe vers un document et un fragment ; **100 %** des positions restituent exactement le fragment du texte normalisé. Origines simulées, mixtes, anciennes et inconnues signalées séparément. |
| **C4** | **Persistance et portée du brief** | **100 %** des champs, dont `additional_context`, horizon/déclencheur/références et version, survivent à sauvegarde/relecture et parviennent aux étapes concernées. Projet ancien lisible. **1 cas long > 50 000 caractères** : omissions documentaires signalées et brief conservé, ou refus explicite si lui-même dépasse la limite ; **0** perte silencieuse de consignes. |
| **C5** | **Filet de tests hermétiques** | **0 échec** sur le filet existant sous Docker, sans réseau externe ni `.env`. Référence historique : **771 tests verts** après 006-2 ; le décompte exécuté et les tests ignorés sont consignés dans la revue, sans confondre collecte et réussite. |
| **C6** | **Prévalidation effective** | **2 routes POST**, **1 parcours IHM de révision**, **1 parcours simple sans métadonnées avancées obligatoires**, **1 blocage volontaire** sur doute/conflit testés. Diagnostics d'extraction et troncature visibles. **0** arbitrage perdu, **0** sélection périmée utilisée, **0** mutation pendant préparation/exécution. |
| **C7** | **Rapport vérifiable** | Jeu d'essai avec **5 origines** et **1 contradiction** : toutes les références résolues, sources contradictoires conservées, **0** citation fabriquée ni événement simulé présenté comme fait documentaire. **1 post d'intention sans action correspondante enregistrée** ne peut devenir une action observée ; toute observation revendiquée est reliée à une trace du run. |

## 6. Conditions de préparation des stories

- La [story 009-1 rédigée](story-009-1.md) traite le verrou P0 avec `simulation_requirement` existant comme contexte minimal ; elle ne dépend pas de la persistance complète du brief en 009-2. Politique minimale du lot : personnes et organisations seulement, collectifs en `review`, exception marque/fiction explicitement reportée. Fixtures annotées et contrôle de référence restent requis avant code.
- Le filtrage syntaxique porte sur une valeur entière (URL, montant, date), jamais sur un mot isolé trouvé dans un nom d'acteur. Une décision LLM invalide ou de confiance insuffisante reste `review` et ne produit aucun profil.
- Une correction humaine doit rester compatible avec un rôle d'acteur ; l'activation directe d'un produit/concept par simple changement de statut est interdite. Le protocole exact de requalification est à fixer dans 009-3.
- 009-2 précède 009-3 et 009-4 pour le brief et la provenance. Les anciennes données non traçables restent utilisables avec un avertissement explicite ; une reconstruction éventuelle exige les documents originaux.
- La [revue de cohérence](revue-coherence-2026-10-10.md) liste les décisions restantes et les preuves attendues. Cet audit documentaire ne vaut ni qualification fonctionnelle ni clôture de story.
- La [matrice de couverture du rapport](couverture-rapport-audit.md) précise les compléments retenus et les arbitrages de fiction, validation/conflits documentaires, contextes longs et blocage volontaire. Le benchmark Zep/Graphiti et l'ontologie v2 restent distincts de l'epic 009.
