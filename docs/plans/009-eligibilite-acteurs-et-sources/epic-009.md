# Epic 009 — Éligibilité des acteurs et fiabilisation des sources

- **Statut** : `in-progress` · **Dépend de** : 004, 005 · **Bloque** : 007
- **Suivi** : [`sprint-status.yaml`](../../sprint-status.yaml)
- **PRD** : [`prd.md`](prd.md) · **Architecture** : [`architecture.md`](architecture.md)
- **Reprise du 10 octobre 2026** : [revue de cohérence et arbitrages ouverts](revue-coherence-2026-10-10.md). La [story 009-1](story-009-1.md) est implémentée et clôturée (`done`, revue contradictoire du 11 octobre 2026) : modèle, classifieur, barrière, intégration et [mesure réelle](mesure-009-1.md) livrés. La [story 009-2](story-009-2.md) est implémentée et passe en `review` (revue à quatre couches du 11 octobre 2026, 15 constats traités) : [ADR 0012](../../decisions/0012-contrat-de-provenance-graphstore.md), [ADR 0013](../../decisions/0013-semantique-des-sources.md), modèles de sources et brief, contrat de provenance dans les deux stores, découpage par document, diagnostics de contexte et [mesure réelle C3](mesure-009-2.md) livrés. Les fichiers de 009-3 et 009-4 restent des emplacements futurs.
- **Rapport source fourni par l'utilisateur** : [matrice de couverture](couverture-rapport-audit.md), incluant diagnostics, contexte long et événements de simulation.

> L'Epic 005 a scellé l'environnement Docker de référence autonome (711 tests verts, Verdict GO).  
> **L'Epic 009 élimine la confusion sémantique entre connaissances et acteurs simulables**.  
> Il introduit une sélection rigoureuse d'éligibilité des agents (`ActorEligibility`), une modélisation typée des documents sources (`SourceDocument`), la persistance du `SimulationBrief`, une étape de prévalidation avant simulation, et la traçabilité des faits dans le rapport final.

---

## 1. Exigences fonctionnelles (FR)

| Réf. | Intitulé | Description |
|---|---|---|
| **FR-1** | Éligibilité des acteurs (`ActorEligibility`) | Qualification de chaque entité du graphe via un rôle (`person`, `organization`, `product`, `concept`, etc.) et un statut (`eligible`, `ineligible`, `review`). |
| **FR-2** | Préservation des connaissances non-acteurs | Seuls les acteurs qualifiés `eligible` génèrent des comptes, dans la préparation comme dans les appels directs au générateur ; les autres restent interrogeables comme contexte passif. |
| **FR-3** | Documents sources structurés | Rôle, date, priorité choisie, source/auteur facultatifs ; statut de validation et conflits documentaires à spécifier. Le nom du fichier ne confère pas d'autorité. |
| **FR-4** | Persistance et portée du brief | Objectif, horizon/déclencheur, sorties attendues, audiences, état initial, règles, hypothèses, références, contexte supplémentaire et version persistés/transmis ; limites de contexte et omissions signalées. Champs avancés facultatifs. |
| **FR-5** | Provenance des fragments et relations | Document, index local base 0 et positions en caractères du fragment ; page/section seulement si connue. `r.episodes` contient les UUID ; origines simulées et inconnues distinctes. |
| **FR-6** | Prévalidation | Inspection/correction des acteurs, fichiers utilisés, erreurs/omissions/troncatures et conflits ; revue humaine facultative, qualification automatique obligatoire, blocage volontaire possible sur doute/conflit. |
| **FR-7** | Rapport vérifiable | Origines distinguées, contradictions visibles et sources conservées ; toute action dite observée renvoie à une trace d'événement du run, un post/intention n'étant pas la preuve d'une autre action. |

---

## 2. Exigences non fonctionnelles (NFR)

| Réf. | Intitulé | Description |
|---|---|---|
| **NFR-1** | Zéro règle métier spécifique | Revue et qualification sur deux domaines ; l'AST contrôle les imports/motifs connus sans prouver seul l'agnosticisme sémantique. |
| **NFR-2** | Rétrocompatibilité `GraphStore` | Appels existants préservés ; extensions de provenance documentées par ADR et implémentées/testées dans les deux stores. |
| **NFR-3** | Résilience et repli propre | En cas d'erreur du classifieur LLM, repli sécurisé sur le filtrage syntaxique avec marquage `review`. |
| **NFR-4** | Filet de tests hermétiques et Docker | Tests automatisés sans réseau externe obligatoire, parité totale validée dans le conteneur Docker. |
| **NFR-5** | Séparation consignes/sources | Texte documentaire traité comme donnée, pas comme message système ni correction autorisée d'éligibilité ; tests des messages et arbitrages. |

---

## 3. Exigences d'expérience utilisateur

- L'utilisateur peut spécifier le rôle de chaque fichier lors de l'import (faits, scénario, personas, etc.) ou laisser le système appliquer le mode simple par défaut.
- Un écran de révision présente la liste ordonnée des acteurs détectés : ceux qui participeront à la simulation (personnes, organisations autorisées) et ceux qui restent passifs en arrière-plan (produits, prix, concepts).
- L'utilisateur peut corriger une qualification avant génération des profils ; une activation exige un rôle d'acteur et une justification. Les entités `review` restent exclues, avec diagnostic si aucun acteur n'est retenu.
- Le rapport final cite ses sources textuelles et n'affirme pas comme fait avéré une action qui relève uniquement d'un post d'agent simulé.
- Les erreurs d'extraction, troncatures et conflits connus sont visibles ; un utilisateur peut choisir de bloquer avant génération en présence de doute/conflit. Le parcours simple n'impose aucun champ documentaire avancé.

---

## 4. Index des stories

| Story | Titre | Statut | Fichier |
|---|---|---|---|
| 009-1 | Modèle `ActorEligibility` et classifieur agnostique à deux passes (Lot A - P0) | `done` | [story-009-1.md](story-009-1.md) |
| 009-2 | Documents sources typés, brief versionné, écriture et lecture de provenance `GraphStore` (Lot B - P1) | `done` | [story-009-2.md](story-009-2.md) |
| 009-3 | Endpoints et interface de prévalidation des acteurs (`preview` & `review`) (Lot C - P1) | `backlog` | [story-009-3.md](story-009-3.md) |
| 009-4 | Outils de provenance, rapport vérifiable et qualification globale (Lot D - P1) | `backlog` | `story-009-4.md` |

| Story | Critères d'acceptation (résumé) |
|---|---|
| 009-1 | Sur ≥ 20 entités de 2 domaines, 0 produit/URL/tarif/concept devenu profil, ≥ 2 acteurs attendus retenus par domaine ; sortie JSON validée, erreurs et faible confiance → `review` ; appels unitaires/par lots, mode sans LLM de personas et profils de secours soumis au verrou ; le rôle qualifié guide les prompts. Préparations historiques/périmées refusées à la réutilisation et au démarrage. Qualification du classifieur réel séparée des tests mockés. |
| 009-2 | ≥ 2 documents de ≥ 2 fragments séparés par source ; positions restituant exactement chaque fragment ; brief complet sauvegardé/transmis (horizon, déclencheur et références inclus), anciens projets lisibles. 1 contexte long > 50 000 caractères traité sans perte silencieuse du brief, diagnostics d'omissions/erreurs conservés. Métadonnées réellement persistées, lecture neutre, isolation par graphe ; origines simulées/héritées signalées. Statut de validation, conflits et ADR du contrat commun fixés avant code. |
| 009-3 | 2 routes POST de sélection/révision avec simulation et révision valide ; parcours Vue de révision, parcours simple sans champs avancés obligatoires et blocage volontaire testés. Fichiers utilisés, diagnostics et conflits connus visibles. Arbitrages durables, UUID étranger et mutations concurrentes refusés ; profils/configurations périmés invalidés. |
| 009-4 | UUID d'épisodes, sources et traces d'événements transmis au rapport ; 5 origines distinguées, 1 contradiction visible avec ses 2 sources, 0 citation inventée. Un post d'intention sans action enregistrée ne devient pas une action observée. Fixtures/sorties intermédiaires et mesure réelle consignées ; qualification globale C1–C7 sous Docker avec skips identifiés. |

### Dépendances et couverture

| Story | Dépend de | Exigences | Critères de sortie |
|---|---|---|---|
| 009-1 | 004 et 005 (`done`) ; définition de prêt satisfaite, politique/fixtures/référence Docker consignées dans la story | FR-1, FR-2 ; NFR-1, NFR-3, NFR-4, NFR-5 | C1, C2, contribution C5 |
| 009-2 | 009-1 ; validation/conflits, contexte long et extension du contrat spécifiés | FR-3, FR-4, FR-5 ; NFR-2, NFR-4, NFR-5 | C3, C4, contribution C5 |
| 009-3 | 009-1, 009-2 ; politique de correction humaine fixée | FR-6 ; NFR-3, NFR-4 | C6, contribution C5 |
| 009-4 | 009-2, 009-3 ; verrou de 009-1 opérationnel | FR-7 ; NFR-2, NFR-4, NFR-5 | C7, validation finale C1–C7 |

Le brief complet de 009-2 ne bloque pas le lot P0 : 009-1 utilise les consignes existantes, puis 009-2 étend et teste leur transport. L'Epic 006 est désormais clos indépendamment ; la qualification d'un graphe migré doit respecter la même barrière, sans exigence de provenance rétroactive impossible.

---

## 5. Documents à consulter

| Document | Ce qu'on y prend |
|---|---|
| [`docs/plans/009-eligibilite-acteurs-et-sources/prd.md`](prd.md) | Contrat d'ingénierie, critères chiffrés C1 à C7. |
| [`docs/plans/009-eligibilite-acteurs-et-sources/architecture.md`](architecture.md) | Schémas Mermaid, modèles de données et flux de classification. |
| [`revue-coherence-2026-10-10.md`](revue-coherence-2026-10-10.md) | Constats sourcés, corrections, arbitrages et résultat des contrôles. |
| [`rapport-audit-mirofish-local-first.md`](rapport-audit-mirofish-local-first.md) | Audit source ajouté pendant la reprise ; recommandations et exceptions de fiction à arbitrer, sans preuve reproductible des runs. |
| [`couverture-rapport-audit.md`](couverture-rapport-audit.md) | Traçabilité des recommandations vers FR/NFR, critères et lots ; limites de couverture du plan. |
| [`preparation-009-1.md`](preparation-009-1.md) | Fixtures, relecture des annotations, contrat d'entrée et preuve Docker de la définition de prêt de 009-1. |
| [`backend/app/services/oasis_profile_generator.py`](../../../backend/app/services/oasis_profile_generator.py) | Entrées unitaires/par lots et choix du prompt selon le rôle. |
| [`backend/app/services/simulation_manager.py`](../../../backend/app/services/simulation_manager.py) | Préparation, sélection persistée et invalidation des artefacts. |
| [`backend/app/services/graph_builder.py`](../../../backend/app/services/graph_builder.py) | Découpage et soumission des lots documentaires. |
| [`backend/app/api/graph.py`](../../../backend/app/api/graph.py) | Upload, contexte supplémentaire et sauvegarde du projet. |
| [`backend/app/models/project.py`](../../../backend/app/models/project.py) | Sérialisation rétrocompatible des projets et fichiers sources. |
| [`backend/app/services/simulation_config_generator.py`](../../../backend/app/services/simulation_config_generator.py) | Construction du contexte et limite de 50 000 caractères. |
| [`backend/app/services/ontology_generator.py`](../../../backend/app/services/ontology_generator.py) | Échantillonnage des longs documents à rendre visible. |
| [`backend/app/utils/graph_store/base.py`](../../../backend/app/utils/graph_store/base.py) | Contrat neutre et DTO actuels. |
| [`backend/app/utils/graph_store/graphiti_store.py`](../../../backend/app/utils/graph_store/graphiti_store.py) | Ingestion/lecture Graphiti et métadonnées actuellement ignorées. |
| [`backend/app/utils/graph_store/zep_store.py`](../../../backend/app/utils/graph_store/zep_store.py) | Contrat concurrent réel à préserver et étendre. |
| [`backend/app/api/simulation.py`](../../../backend/app/api/simulation.py) | Routes de préparation/démarrage et réutilisation des artefacts. |
| [`frontend/src/components/Step2EnvSetup.vue`](../../../frontend/src/components/Step2EnvSetup.vue) | Parcours à faire précéder par la révision d'acteurs. |
| [`backend/app/services/zep_graph_memory_updater.py`](../../../backend/app/services/zep_graph_memory_updater.py) | Origine des épisodes d'activité simulée. |
| [`backend/app/services/zep_tools.py`](../../../backend/app/services/zep_tools.py) | Projections de résultats où les références de provenance sont perdues. |
| [`backend/app/services/report_agent.py`](../../../backend/app/services/report_agent.py) | Consommation des outils et rédaction du rapport. |
| [`backend/scripts/action_logger.py`](../../../backend/scripts/action_logger.py) | Structure des actions réellement enregistrées dans les traces du run. |
| [`ADR 0001`](../../decisions/0001-remplacement-de-zep-par-graphiti.md) | Graphe derrière l'interface commune. |
| [`ADR 0003`](../../decisions/0003-ontologie-differee-en-v2.md) | Ontologie dynamique hors périmètre v1. |
| [`ADR 0006`](../../decisions/0006-docker-first.md) | Docker comme environnement de référence. |
| [`AGENTS.md`](../../../AGENTS.md) | Constitution du dépôt et définitions de prêt/fini. |
