# MiroFish local-first — Rapport d’audit et recommandations produit / développement

**Date :** 10 octobre 2026  
**Dépôt :** https://github.com/zohac/MiroFish  
**Branche examinée :** `local-first`  
**Objet :** fiabiliser l’exploitation de plusieurs documents et la génération d’agents sans spécialiser MiroFish pour un domaine métier.

## 1. Synthèse et décision demandée

La migration de Zep Cloud vers Graphiti + Neo4j est une évolution technique substantielle. Les documents de qualification du dépôt annoncent un pipeline opérationnel et une suite de 711 tests réussis. Cela valide surtout le fonctionnement technique déclaré, **pas la pertinence sémantique des acteurs ni la fiabilité des rapports prédictifs**.

Deux simulations commerciales construites autour de la même offre ont produit une conclusion générale comparable, mais plusieurs personnages simulés sont incohérents : des domaines, une formule commerciale ou le produit lui-même semblent intervenir comme des praticiennes. D’autres objections reposent sur des informations produit déjà documentées comme connues.

**Décision recommandée :** conserver une architecture généraliste et introduire un chaînage explicite *sources → faits → entités → acteurs éligibles → personas → simulation → rapport*, avec des contrôles entre les étapes. Ne pas coder de règles propres à Keova.

## 2. Ce qui est établi dans le code consulté

### 2.1. Ingestion multifichier existante, mais peu structurée

Dans `backend/app/api/graph.py`, route `/ontology/generate` :

- L’API accepte plusieurs fichiers via `request.files.getlist('files')`.
- Les textes sont extraits et nettoyés individuellement, puis ajoutés à `document_texts`.
- Une seconde représentation, `all_text`, concatène les contenus avec un séparateur mentionnant le nom du fichier ; elle est sauvegardée et réutilisée pour construire le graphe.
- Le champ `additional_context` est transmis au générateur d’ontologie. Le chemin observé ne démontre pas qu’il soit conservé comme contexte structuré pour les étapes suivantes.

Dans `backend/app/services/ontology_generator.py`, l’analyse de documents longs utilise un plafond de **50 000 caractères**, puis un échantillonnage de fragments. Les différentes sources ne reçoivent pas, à cette étape, une priorité explicite selon leur type ou leur autorité.

Dans `backend/app/services/graph_builder.py`, le texte commun est fractionné avant ingestion (valeurs par défaut visibles : blocs de 500 caractères, recouvrement de 50). Dans `backend/app/utils/graph_store/graphiti_store.py`, les épisodes créés en lot ont des descriptions comme `chunk_1`, sans référence exploitable au fichier et à la section d’origine. La méthode `add_episode` accepte un paramètre `metadata`, mais l’implémentation consultée ne l’injecte pas dans l’appel à Graphiti.

**Conséquence :** fournir plusieurs fichiers est possible ; cela n’équivaut pas encore à une compréhension structurée et traçable des sources. Leur rôle, leur fraîcheur et leurs éventuelles contradictions risquent d’être aplatis.

### 2.2. Ontologie générée, mais non appliquée par Graphiti en v1

`GraphitiGraphStore.set_ontology()` est explicitement un **no-op**, conformément à l’ADR 0003. L’ontologie dynamique reste reportée à une évolution ultérieure.

`backend/app/services/zep_entity_reader.py` prévoit un fallback vers le type générique `Entity` et conserve les entités valides lorsqu’aucun filtre de types n’est fourni. Cela résout un problème d’entités invisibles, mais ne garantit pas qu’une entité représente une personne ou un organisme apte à agir dans une simulation sociale.

### 2.3. La sélection des agents doit être fiabilisée

`backend/app/services/simulation_manager.py` passe les entités filtrées à `OasisProfileGenerator.generate_profiles_from_entities()`. Dans `backend/app/services/oasis_profile_generator.py` :

- la classification « individu » repose sur une liste finie de noms de types ;
- toute entité non reconnue comme individu passe dans la branche de génération de profil de groupe / organisation ;
- la génération produit donc potentiellement un compte social pour un produit, une URL, une formule ou un concept.

**Cause probable des anomalies observées :** la qualification « entité du graphe » est confondue avec la qualification « acteur simulable ». Cette hypothèse doit être vérifiée sur les graphes, profils et journaux des deux runs ; les rapports seuls ne prouvent pas la causalité.

### 2.4. Troncatures supplémentaires avant simulation

Dans `backend/app/services/simulation_config_generator.py`, le contexte de configuration est limité à **50 000 caractères**, et le texte source est inséré après la consigne et les résumés d’entités, puis tronqué selon l’espace restant. Un document peut donc être fourni et ingéré tout en n’étant que partiellement présent dans certains prompts ultérieurs.

## 3. Problèmes prioritaires à résoudre

| Priorité | Problème | Risque utilisateur |
|---|---|---|
| **P0** | Toute entité valide peut devenir un agent | Comptes et comportements absurdes ; simulation trompeuse |
| **P0** | Pas de contrôle qualité obligatoire des acteurs avant lancement | Erreur détectée seulement dans le rapport final |
| **P1** | Rôle et priorité des fichiers non structurés | Faits, hypothèses, anciennes versions et consignes mélangés |
| **P1** | Traçabilité insuffisante des fragments jusqu’au document d’origine | Difficile d’expliquer ou corriger une affirmation |
| **P1** | Incohérences entre contexte fourni et propos du rapport | Objections fondées sur des prémisses incorrectes |
| **P2** | Ontologie dynamique absente en mode Graphiti v1 | Précision de typage potentiellement inférieure à l’ancien chemin Zep |

Ne pas interpréter ces priorités comme la preuve qu’une régression provient exclusivement de Graphiti. Les documents, prompts, modèles et graines aléatoires des deux simulations n’ont pas été établis comme identiques.

## 4. Évolutions recommandées — génériques et compatibles avec GraphStore

### P0 — Séparer entités du graphe et acteurs de simulation

Créer une étape explicite `ActorSelection` / `ActorEligibility` entre lecture du graphe et génération de profils. Une entité peut être importante dans le contexte **sans** avoir le droit de publier ni de prendre des décisions.

Proposer un modèle de rôles générique et extensible : `person`, `organization`, `collective`, `product`, `service`, `domain`, `place`, `event`, `concept`, `unknown`. Ajouter indépendamment `actor_eligibility = eligible | ineligible | review` et une justification.

Ne pas décider uniquement par la casse ou le libellé d’un type (`Coach`, `Person`, `Entity`, etc.). Appuyer la décision sur les propriétés, la description, les relations, le contexte du scénario et, si besoin, un classifieur LLM à sortie structurée. Une organisation peut agir par un compte officiel ; une URL, un abonnement ou un thème ne devraient pas agir par défaut. Autoriser une exception **explicite** pour les scénarios qui mettent intentionnellement en scène une marque ou une entité fictive.

La validation doit être visible avant `generate_profiles_from_entities()`. Les entités rejetées **restent dans le graphe** comme objets de connaissance ; seules celles retenues deviennent des agents. Prévoir le statut `review` et une correction manuelle.

### P1 — Introduire des documents typés, pas simplement des fichiers joints

Faire évoluer l’import vers un modèle interne `SourceDocument` comprenant au minimum : identifiant stable, nom du fichier, rôle (`facts`, `scenario`, `personas`, `hypotheses`, `constraints`, `reference`), date, statut de validation, source / auteur si pertinent, et priorité explicitement choisie. **Ne pas déduire qu’un fichier est vrai ou prioritaire uniquement parce que son nom contient `canonical` ou `official`.**

Un `DocumentChunk` doit porter `source_id`, section ou page, positions dans le texte, texte, et éventuelles dates de validité. Conserver ces informations à l’ingestion Graphiti, dans la recherche et dans les éléments remis au générateur de rapport. Vérifier le contrat `GraphStore` avant d’étendre `add_text_batch()` ; privilégier une évolution compatible avec l’implémentation Zep.

Prendre en charge les contradictions : deux sources affirmant des choses incompatibles ne doivent pas fusionner silencieusement. Les marquer `conflict`, résoudre par priorité/dates quand une règle déclarée existe, sinon conserver « à confirmer ».

### P1 — Donner au contexte utilisateur une portée explicite

Le système dispose déjà d’un champ `additional_context`, mais sa portée actuelle est principalement celle de la génération d’ontologie. Ajouter un objet `SimulationBrief` persistant et versionné, accessible aux étapes qui en ont besoin :

- **Objectif :** question à simuler, horizon temporel, événement déclencheur et sorties attendues.
- **État initial :** faits avérés à l’instant de départ, distincts des événements simulés.
- **Acteurs souhaités :** profils recherchés et exclusions éventuelles.
- **Règles :** limites, contraintes et comportements impossibles.
- **Hypothèses :** éléments que les agents peuvent explorer sans les présenter comme établis.
- **Références :** documents à consulter et leur niveau de fiabilité.

Conserver l’option « simple » : un utilisateur doit pouvoir simuler avec seulement une consigne et quelques fichiers. Le mode « avancé » permet de renseigner les métadonnées sans devenir obligatoire. Les contenus des documents restent des **données à interpréter**, non des instructions système exécutables.

### P1 — Ajouter un écran ou rapport de prévalidation

Avant le lancement : afficher les fichiers effectivement ingérés, les éventuelles erreurs d’extraction, les fragments ignorés/tronqués, les contradictions, les catégories d’entités, les acteurs retenus et rejetés, ainsi que les raisons. Permettre : « conserver comme contexte », « autoriser comme acteur », « exclure des agents », « corriger ce type ». La correction doit être enregistrée pour le run, sans altérer arbitrairement les autres simulations.

### P1 — Rendre le rapport final plus honnête sur les preuves

Exiger une provenance pour les affirmations importantes : **fait provenant d’un document**, **événement effectivement enregistré pendant la simulation**, ou **inférence du ReportAgent**. Une absence d’événement de souscription dans un run ne prouve pas une impossibilité commerciale. Une citation d’agent synthétique n’est pas un témoignage réel. Si l’identité d’un acteur ou une fonctionnalité demeure incertaine, le rapport doit le dire.

Ajouter une vérification automatique des conclusions contredisant un fait prioritaire connu et distinguer systématiquement « simulé », « sourcé » et « hypothétique ».

### P2 — Évaluer ensuite l’ontologie dynamique Graphiti

L’ADR 0003 reporte volontairement cette fonctionnalité. Ne pas réintroduire d’emblée toute l’ontologie custom comme condition de correction des agents : l’étape de sélection explicite peut corriger une grande partie du problème sans attendre. Mesurer ensuite le gain de typage de `custom_entity_types` au regard de son coût et de sa complexité.

## 5. Améliorations possibles côté documents utilisateur, dès maintenant

En attendant les changements logiciels, un utilisateur peut réduire l’ambiguïté en fournissant des fichiers **courts, datés et non contradictoires**, aux rôles distincts :

1. `00-brief-simulation.md` — question exacte, événement de départ, durée, groupes à observer, critères de succès ; préciser qu’il s’agit d’une simulation et non d’une enquête réelle.
2. `01-faits-valides.md` — seules les informations confirmées à la date du scénario, avec sections « inclus », « exclus », « en cours », « inconnus » et sources.
3. `02-acteurs-et-roles.md` — catégories d’acteurs possibles, motivations, contraintes ; préciser que les sites, produits, prix et offres sont des **objets de discussion**, pas des utilisateurs.
4. `03-hypotheses-a-tester.md` — hypothèses ouvertes et objections potentielles ; ne pas les présenter comme des faits.
5. `04-sources-et-contradictions.md` — anciennes versions, historique, fiabilité relative et points à vérifier.

Préciser dans la consigne de simulation : « Utiliser les fichiers de faits pour déterminer l’état initial. Ne pas transformer les noms de produits, offres ou domaines en personnes. Faire apparaître les inconnues comme telles. Ne pas déduire une conversion réelle d’une intention ou d’un commentaire simulé. »

**Limite :** ces règles textuelles n’ont pas valeur de validation automatique dans le code actuel. Elles aident le LLM, mais ne remplacent pas `ActorEligibility` et la provenance structurée.

## 6. Plan de mise en œuvre conseillé

| Lot | Travail | Bénéfice | Coût / principal risque |
|---|---|---|---|
| **A — Priorité immédiate** | Instrumenter la création du graphe, classifier les entités et ajouter `ActorEligibility` | Éliminer les agents manifestement incohérents | Complexité des cas limites (organisations, marques, fiction) |
| **B** | Métadonnées de documents, fragments sourcés et `SimulationBrief` persistant | Fiabilité et transparence du contexte | Adaptation des interfaces de stockage et migration compatible |
| **C** | Prévisualisation des agents et validation avant exécution | Contrôle humain des simulations | Une étape UX supplémentaire, à rendre facultative |
| **D** | Rapport avec provenance des affirmations et gestion des contradictions | Distinguer les faits des sorties fictives | Travaux sur le ReportAgent et les données d’événements |
| **E — Après mesure** | Benchmark contrôlé Zep vs Graphiti, puis décision sur ontologie v2 | Mesurer la qualité réelle de la migration | Coût en exécutions LLM et constitution d’un jeu d’évaluation |

## 7. Critères d’acceptation et tests à ajouter

- **Sélection d’agents :** dans un jeu d’essai mêlant humains, organismes, pages web, prix et produits, les non-acteurs sont conservés dans le graphe mais ne deviennent pas des comptes sociaux par défaut ; un acteur organisationnel explicitement sélectionné reste autorisé.
- **Généricité :** le mécanisme fonctionne sur **au moins deux domaines de test sans lien** (par exemple logiciel métier et événement public), sans règle `if Keova` ni spécialité hardcodée.
- **Provenance :** un fragment et un fait attribuable à une source peuvent être reliés à un fichier et à une section ; la perte éventuelle de provenance est signalée.
- **Contexte :** les contraintes du `SimulationBrief` sont accessibles lors de la sélection d’acteurs et de la configuration ; leur utilisation par chaque étape est testée.
- **Conflits :** une offre ancienne contradictoire avec une décision récente produit un avertissement, pas un mélange silencieux.
- **Prévalidation :** une simulation peut être bloquée volontairement si un acteur est `review` ou si une contradiction majeure n’est pas résolue ; le mode simple reste utilisable.
- **Rapport :** un commentaire d’agent est étiqueté comme contenu simulé ; une vente ne peut être dite « observée » que si l’événement correspondant figure dans les traces du run.
- **Non-régression :** mêmes garanties avec les deux implémentations de `GraphStore` ; tests unitaires, intégration Neo4j et scénario complet sur la branche local-first.

Constituer un jeu d’essai versionné, avec sorties intermédiaires (`documents.json`, `chunks.json`, `entities.json`, `actors.json`, `profiles.json`, `simulation_events.json`, `report.md`) et mesurer la justesse des acteurs, la couverture des faits prioritaires, les contradictions non signalées, la provenance et la stabilité d’un run à l’autre.

## 8. Questions techniques à trancher par le développeur

- Le champ `additional_context` est-il sauvegardé et réinjecté ailleurs que dans la génération d’ontologie, via un autre chemin non examiné ?
- Quels attributs du graphe Graphiti permettent de relier sans ambiguïté un fait à l’épisode et au fichier initial ?
- Quelle stratégie de classification générique est la plus robuste : déterministe, LLM à sortie structurée, ou hybride avec revue humaine ?
- Comment conserver les corrections utilisateur et la provenance tout en gardant le contrat `GraphStore` compatible Zep/Graphiti ?
- Quelles différences exactes existaient entre les deux runs : documents, modèle, température, nombre d’agents/tours, graine et prompts ?

## 9. Références examinées

- `backend/app/api/graph.py` — import multifichier, `additional_context`, concaténation, lancement de construction.
- `backend/app/services/ontology_generator.py` — consigne, échantillonnage long texte et limite de contexte.
- `backend/app/services/graph_builder.py` — segmentation de texte et ingestion par lot.
- `backend/app/utils/graph_store/graphiti_store.py` — ontologie no-op et épisodes locaux.
- `backend/app/services/zep_entity_reader.py` — types d’entités et fallback générique.
- `backend/app/services/simulation_manager.py` — transfert des entités vers les profils.
- `backend/app/services/oasis_profile_generator.py` — classification individu/groupe et génération.
- `backend/app/services/simulation_config_generator.py` — contextes limités et troncature.
- `docs/decisions/0003-ontologie-differee-en-v2.md` — arbitrage v1/v2.
- `docs/STATUS.md` et `docs/plans/005-docker-local/rapport-qualification-epic-005.md` — qualification technique revendiquée au 10 octobre 2026.

**Conclusion :** ne pas spécialiser MiroFish pour Keova. Investir d’abord dans des sources structurées, une vraie distinction entre connaissance et acteur, et des preuves traçables. Des fichiers utilisateurs plus explicites amélioreront les résultats immédiatement, mais une fiabilisation logicielle est nécessaire pour rendre cette amélioration reproductible.
