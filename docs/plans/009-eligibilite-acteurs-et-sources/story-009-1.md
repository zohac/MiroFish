---
id: "009-1"
epic: "009"
titre: "Modèle ActorEligibility et classifieur agnostique à deux passes"
statut: backlog
auteur: agent
format: "2"
---

# Story 009-1 — Modèle `ActorEligibility` et classifieur agnostique à deux passes

Lot A, priorité P0. En tant qu'utilisateur, je veux que seules les personnes et
les organisations qualifiées deviennent des agents OASIS, afin que les produits,
tarifs, sites et concepts restent des connaissances discutées dans la simulation.

Cette demande prépare le contrat de développement ; elle ne lance pas
l'implémentation. Couverture : FR-1, FR-2, NFR-1, NFR-3, NFR-4, NFR-5 ; C1,
C2 et contribution à C5. Les garanties de réutilisation ci-dessous ferment le
contournement du verrou P0 ; la révision humaine complète appartient à 009-3.

## Définition de prêt

- [x] PRD, architecture, hub, revue et rapport source consultés ; constats R10 à R15 et exception A02 pris en compte.
- [x] Dépendances 004 et 005 terminées ; ni 006 ni le brief complet de 009-2 ne bloquent ce lot.
- [x] Politique minimale du lot explicitée ci-dessous : personnes et organisations seulement, collectifs en `review`, exception marque/fiction reportée.
- [x] Entrées existantes, mécanisme de secours des profils et réutilisation des préparations identifiés ; formats OASIS à préserver.
- [x] Critères mesurables et stratégie de tests définis, avec séparation des tests hermétiques et de la mesure réelle.
- [x] Fixtures annotées multi-domaines constituées et relues : 46 entités, 23 par domaine, 8 acteurs attendus par domaine ; [preuves et empreintes](preparation-009-1.md).
- [x] État de référence du code courant contrôlé sous Docker avant code métier : 822 réussis, 3 ignorés sur 825 collectés, lint et plans valides ; [versions, protocole et limites](preparation-009-1.md). Recontrôler si le code ou les dépendances changent avant implémentation.

### Critères d'acceptation

| Réf. | Situation et comportement attendu | Vérification |
|---|---|---|
| AC1 | Chaque entité examinée reçoit une qualification liée à son UUID d'entrée : nom, rôle, statut, justification, confiance, type d'origine et attributs. Rôles/statuts inconnus, justification vide et confiance non finie/hors `[0, 1]` sont refusés. Un rôle passif ne peut jamais porter `eligible`. | Tests du modèle, sérialisation et validation des résultats LLM ; aucune identité fournie par le LLM ne remplace l'UUID d'entrée. |
| AC2 | Une valeur entière URL/domaine, montant avec devise, date ou durée est `ineligible` sans requête LLM. Un nom composite contenant un montant, une date, `abonnement` ou `mensuel` n'est pas rejeté par ce seul motif. | Appels LLM espionnés ; cas de domaines variés, noms composites et valeurs vides/ambiguës. |
| AC3 | Les autres entités sont classifiées à partir de nom, résumé, attributs, relations, voisins et `simulation_requirement`. Le client existant produit un JSON validé. Un label `Entity`, `Person` ou métier ne suffit pas à autoriser un compte. | Vérification des entrées du classifieur, des messages et du schéma ; personnes et organisations avec label générique. |
| AC4 | Indisponibilité du client, clé absente, exception, réponse tronquée/invalide/incomplète, rôle/statut incohérent ou confiance `< 0.7` donnent `review` avec diagnostic. Les exclusions déterministes restent `ineligible`. Une défaillance d'une entité ne promeut aucune autre entité et ne détruit pas ses résultats valides. | Cas paramétrés indépendants, dont `0.699`, `0.7`, `NaN`, infini, booléen et chaîne à la place d'une confiance numérique. |
| AC5 | Seuls `person` et `organization` qualifiés `eligible` passent la barrière. `collective` et `unknown` restent `review`. Produits, services, domaines, lieux, événements et concepts restent passifs. Un compte officiel d'organisation est distingué du produit/de la marque ; une consigne demandant de personnifier un produit ne suffit pas à l'activer. | Matrice rôle/statut et exemples de personne, organisation, territoire/institution, produit/compte officiel, groupe informel et fiction. |
| AC6 | La préparation et `/generate-profiles`, ainsi que les appels directs unitaires/par lots du générateur, appliquent le même verrou. `use_llm_for_profiles=False`, `use_llm=False`, `force_regenerate` et le persona de secours n'autorisent aucun `review`/`ineligible`/non qualifié. | Espions avant génération et export ; refus unitaire explicite, filtrage par lots, absence de profil de secours après refus. |
| AC7 | Une personne qualifiée utilise le prompt individuel, une organisation celui du compte organisationnel, même avec `original_type=Entity`. Le rôle qualifié ne réécrit ni les labels du graphe ni les champs historiques de traçabilité du profil. | Vérification des prompts et des UUID ; formats Twitter/Reddit, normalisation des champs et identifiants OASIS préservés. |
| AC8 | Les non-acteurs restent lisibles dans le graphe avec leurs relations et disponibles comme contexte passif. Aucun appel d'écriture/suppression ni requête spécifique à un store n'est introduit par la classification. | Doubles de store avec nœuds/arêtes avant/après ; tests des deux contrats de lecture et revue des dépendances. |
| AC9 | Aucun acteur retenu : préparation en échec explicite, diagnostic des exclusions/reviews, aucun artefact déclaré prêt ni configuration lancée. Dans un lot mixte, les compteurs et la configuration utilisent les acteurs réellement retenus. `entity_types` continue de désigner les types d'origine. | Tests du gestionnaire et des routes : 0 acteur, lot mixte, `max_agents`, progression et échec de tâche. |
| AC10 | Une préparation historique sans preuve du verrou, ou préparée avec des entrées/politique différentes, n'est ni réutilisée comme prête ni démarrée. Une préparation fraîche peut être réutilisée. | Tests `/prepare`, `/prepare/status`, `/start` et contrôle commun de cache ; rejet après changement d'entités/contexte/politique, sans lancer le moteur. |
| AC11 | Sur au moins 20 entités annotées de deux domaines sans lien : 0 produit/URL/tarif/concept devenu profil ; au moins 2 acteurs attendus effectivement retenus par domaine. Cette garantie tient avec et sans LLM de personas, sans changement de code entre domaines. | Fixtures identiques à travers classifieur, gestionnaire, génération unitaire/par lots et export ; C1, volet hermétique de C2. |
| AC12 | Une mesure distincte utilise le classifieur LLM réel sur les mêmes fixtures : au moins 2 acteurs attendus retenus par domaine, 0 faux acteur produit/URL/tarif/concept. Entrées, sorties, modèle, paramètres et bilan par domaine sont versionnés. | Mesure manuelle hors pytest/CI, code retour non nul si seuil manqué ; C2 ne peut pas être validé uniquement avec des mocks. |
| AC13 | Résumés, attributs et voisins provenant du graphe sont des données dans les messages LLM ; ils ne deviennent ni consigne système ni qualification humaine autorisée. Un attribut `status=eligible` ou un extrait demandant de contourner le filtre ne constitue pas une preuve d'éligibilité. | Tests structurels des messages et de la frontière de qualification ; pas de promesse d'immunité générale du modèle. |

## Définition de fini

- [ ] AC1 à AC13 satisfaits, preuves rattachées aux tests et à la mesure réelle ; aucun succès obtenu en excluant tous les acteurs.
- [ ] Modèle et service uniques intégrés aux frontières applicatives et aux scripts appelant le générateur, sans branche Zep/Graphiti dans le nouveau code métier.
- [ ] Refus d'éligibilité distingué d'une erreur de génération de persona ; cache et démarrage ne contournent pas le verrou.
- [ ] Les profils Twitter CSV et Reddit JSON restent conformes ; graphe et types d'origine préservés.
- [ ] Suite hermétique complète, lint et `validate_plans.py` exécutés sous Docker sur le code courant ; décompte et motifs des éventuels skips consignés. Les 771 tests du plan initial et les 800 annoncés après 006 sont des jalons, pas un résultat de cette story.
- [ ] Mesure C2 réelle consignée sans secrets dans `mesure-009-1.md` ; écarts et conditions d'exécution exposés.
- [ ] Revue de code réalisée et corrections traitées ; statut passé par `review` avant `done`.
- [ ] Hub, suivi humain et agrégat d'epic actualisés ; notes de complétion renseignées, aucune case cochée sans preuve.

## Tâches

- [x] T1 — Constituer les deux fixtures et relire leurs annotations avant implémentation (AC2, AC5, AC11) ; 46 entités annotées, 25 contrôles d'intégrité, [relecture consignée](preparation-009-1.md). Les comportements AC2/AC5/AC11 restent à implémenter et qualifier.
- [ ] T2 — Ajouter `app/models/actor_eligibility.py` avec enums, validation commune et sérialisation testées (AC1, AC4, AC5).
- [ ] T3 — Ajouter `app/services/actor_classifier.py` : filtrage syntaxique intégral, client LLM injecté/créé à la demande, réponse structurée validée et diagnostics par entité (AC2–AC5, AC13).
- [ ] T4 — Protéger les entrées unitaires/par lots d'`OasisProfileGenerator`, choisir les prompts par rôle et séparer refus/erreur de persona (AC6–AC8).
- [ ] T5 — Intégrer la classification à la préparation et à `/generate-profiles`, filtrer avant `max_agents`, transmettre uniquement les acteurs à la configuration et corriger les compteurs (AC6, AC9, AC11).
- [ ] T6 — Ajouter la preuve minimale de qualification aux artefacts et contrôler réutilisation/statut/démarrage ; refuser les préparations historiques ou périmées (AC10).
- [ ] T7 — Adapter les tests historiques qui créaient un profil de lieu ou un profil générique non qualifié ; conserver et renforcer leur intention, sans suppression du filet (AC7–AC11).
- [ ] T8 — Ajouter la sonde `scripts/verifier_eligibilite_acteurs.py`, hors CI réseau, et réaliser la mesure réelle multi-domaines (AC12).
- [ ] T9 — Exécuter contrôles Docker, revue et mise à jour des preuves/artefacts ; passer en `review`, puis en `done` après validation.

## Notes de développement

### Politique minimale pour ce lot

Le seuil de confiance est **0.7**, borne incluse ; il est commun aux domaines.
Une confiance élevée ne transforme pas un rôle passif en acteur. `person` désigne
un individu ou une persona humaine décrite ; `organization` un organisme capable
d'action sociale, représenté par son compte officiel. Le nom de produit seul
ne permet pas de déduire une organisation ; les cas ambigus restent `review`.

Les rôles `collective` et `unknown` ne sont pas activés automatiquement. L'exception
du rapport A02 pour personnification d'une marque ou d'un objet fictif est
**reportée dans ce lot** : elle demande une représentation et une autorisation
explicites à spécifier ultérieurement. Un produit ne devient pas une personne par
un simple changement de statut. La correction humaine et le traitement définitif
des collectifs relèvent de 009-3 ; cette restriction permet de fermer C1 maintenant.

La passe déterministe normalise uniquement la présentation pour reconnaître une
**valeur entière**. URL/domaine → `domain`, montant avec devise → `product`, date
→ `event`, durée → `concept`. Pas de liste d'offres, de métiers, de clients ou de
suffixes nationaux. Une valeur ambiguë passe à la seconde passe ; une identité
vide/inexploitable reste `review`. Conserver le nom d'origine pour les preuves.

La validation Pydantic de la réponse porte sur `role`, `status`, `rationale`,
`confidence`, sans champs supplémentaires utilisés comme instructions. Accepter
les valeurs JSON des enums, refuser la coercition d'une chaîne/booléen en confiance,
vérifier finitude et bornes. Construire UUID/nom/type/attributs depuis l'entrée,
jamais depuis une identité inventée dans la réponse. Une sortie incohérente donne
une qualification sûre `review` avec motif, pas un `eligible` corrigé silencieusement.

### Contexte, frontière de confiance et appels

Utiliser `simulation_requirement` comme contexte minimal dès 009-1. Les résumés,
attributs, relations et `related_nodes` d'`EntityNode` fournissent le contexte
documentaire ; ils sont sérialisés séparément des règles système de classification.
Ne pas recopier le texte documentaire dans le message système. Le brief versionné,
les exclusions structurées par UUID et `additional_context` persisté arrivent en
009-2 ; ne pas prétendre que 009-1 interprète fiablement des exclusions libres par nom.

Réutiliser `LLMClient.chat_json` et la compatibilité session/JSON déjà en place.
Injecter un client pour les tests et retarder sa création jusqu'à la seconde passe :
une URL doit pouvoir être exclue sans clé LLM. `use_llm=False` pour les personas
n'éteint pas la classification ; si le classifieur est indisponible, les candidats
non exclus restent `review`, donc aucun profil n'est fabriqué par défaut.
Ne pas ajouter de boucle de retry infinie ni de deuxième client de classification.

Centraliser les combinaisons autorisées et le verrou. Une qualification interne
réutilisée dans un même flux est liée à l'entité et au contexte qui l'ont produite.
Les attributs du graphe ou les champs fournis par l'appelant HTTP ne sont pas une
qualification de confiance. Un appel direct sans qualification interne valide
effectue la classification ; un refus unitaire lève une erreur métier identifiable,
un lot exclut les refus et rend leurs diagnostics. Garder les appels existants
compatibles ; les éventuels nouveaux paramètres sont facultatifs.

Le secours `_generate_profile_rule_based` reste autorisé pour une **entité déjà
éligible** après échec du LLM de personas. Le `except Exception` du lot ne doit
pas capturer un refus et créer ensuite un profil. Les identifiants OASIS doivent
rester cohérents avec l'ordre des profils effectivement exportés.

### Réutilisation minimale, avant la révision humaine de 009-3

Pour AC10, enregistrer dans les artefacts de préparation une preuve automatique
liée à simulation/projet/graphe, à la version de politique et à une empreinte
déterministe des entrées de qualification : UUID, nom, labels, résumé, attributs,
relations/voisins utilisés et consigne. Les UUID des acteurs retenus doivent
correspondre aux profils/configuration produits. Ne pas se fier au seul nombre
de fichiers ou au statut `READY`.

Sans preuve ou si les entrées changent, les routes existantes ne déclarent pas la
préparation fraîche. `/start` refuse avec une demande de nouvelle préparation ;
`/prepare` peut la régénérer après contrôle. Ne pas modifier silencieusement les
profils d'une simulation en cours ou terminée. La sélection durable corrigée,
`actors.json`, ses révisions humaines, les nouveaux endpoints et l'IHM restent en
009-3 ; ce lot n'en implémente pas un protocole parallèle.

Contrôler aussi `/start` quand l'état est déjà `READY` : ce chemin ne passe pas
aujourd'hui par `_check_simulation_prepared`. Toute extension de `SimulationState`
doit être sauvegardée/rechargée et fournir des valeurs par défaut pour les anciens
`state.json`. Conserver `entities_count` comme compteur de connaissances ; préciser
les compteurs d'acteurs/profils, `expected_entities_count` et `total_expected` des
routes temps réel. L'aperçu sans voisinage ne vaut pas sélection définitive et ne
doit pas déclencher une seconde qualification divergente.

### Code existant à modifier et contrats à préserver

| Fichier / entrée | État actuel | Modification attendue et comportement préservé |
|---|---|---|
| `app/services/zep_entity_reader.py` | `EntityNode` porte résumé/attributs/relations/voisins ; `filter_defined_entities` conserve `Entity` sans filtre explicite. | Réutiliser ces DTO et la lecture commune. Garder `get_entity_type`, `FilteredEntities` et les filtres de types existants ; les labels ne sont pas une qualification. |
| `app/services/oasis_profile_generator.py` | `generate_profile_from_entity` choisit individu/groupe à partir du type ; le lot `generate_profiles_from_entities` produit un secours sur exception ; `use_llm=False` produit directement un profil de règles. | Placer le verrou avant ces branches, transporter le rôle qualifié et préserver formats/normalisation/traçabilité. Garder l'enrichissement contextuel via le store. |
| `app/services/simulation_manager.py` | `prepare_simulation` lit les entités, applique la limite, génère les profils et la configuration ; un échec met l'état en erreur. | Qualifier avant limite et génération, transmettre les acteurs retenus à la configuration, préserver les diagnostics et la gestion de progression/erreur. |
| `app/api/simulation.py` | `/prepare` peut réutiliser une préparation ; son aperçu précède le travail asynchrone. `/generate-profiles` appelle le générateur directement. `_check_simulation_prepared` sert aussi au statut/démarrage. | Aucun aperçu ou artefact historique ne vaut autorisation. Garder le protocole de tâches et contrôler à la frontière effective ; compteurs explicites entités/acteurs/review. |
| `app/utils/llm_client.py` | `chat_json` gère réponse tronquée, JSON invalide et repli de capacité JSON via la compatibilité existante. | Le consommer sans le réécrire ; ajouter la validation sémantique au service métier. |

Ne pas modifier `GraphStore`, l'ontologie, les stores ou le moteur OASIS pour ce
lot. Aucun import direct Zep, aucune requête Cypher dans les nouveaux services,
aucune interface à implémentation unique. Python 3.11 sous Docker ; versions du
lock consulté : Pydantic 2.12.5, pytest 8.2.0, `graphiti-core` 0.30.2 et
`camel-oasis` 0.2.5. Aucune nouvelle dépendance ni mise à jour de lock requise.

Le constructeur du générateur exige actuellement une clé et crée `OpenAI` même
sans LLM de personas. Adapter cette initialisation si nécessaire pour laisser
la barrière produire son diagnostic en absence de client, avant toute génération.
Les acteurs déjà qualifiés peuvent utiliser le mode déterministe ; ne pas
promettre qu'il qualifiera des personnes sans classifieur disponible. Le défaut
existant du cache exigeant les fichiers des deux plateformes est distinct :
éviter de le réécrire à l'occasion de cette story.

### Fixtures, tests et qualification

Les fixtures sont constituées dans `backend/tests/fixtures/actor_eligibility/` :
[logiciel de gestion](../../../backend/tests/fixtures/actor_eligibility/logiciel_gestion.json)
et [événement culturel public](../../../backend/tests/fixtures/actor_eligibility/evenement_culturel.json).
Chacun des deux jeux synthétiques comporte 23 entités, dont 2 personnes et
6 organisations attendues comme acteurs, 12 connaissances passives et 3 cas
`review`. Ils couvrent tous les rôles, les vrais homonymes produit/organisation,
les noms composites avec montant/date/durée, les collectifs, la fiction et les
attributs hostiles. UUID, contexte, rôle/statut attendus et justification sont
annotés ; labels génériques et typés représentés. Le [rapport de préparation](preparation-009-1.md)
décrit leur contrat : `expected` et `tags` ne doivent pas être transmis au classifieur.

| Suite prévue | Ce qu'elle démontre |
|---|---|
| `test_actor_eligibility_fixtures.py` (déjà ajouté) | 25 contrôles d'intégrité des jeux annotés ; ne démontre aucun comportement du classifieur. |
| `test_actor_eligibility.py` | Matrice de validation, sérialisation, identité liée à l'entrée. |
| `test_actor_classifier.py` | Syntaxe entière, messages, contexte, seuil/repli, isolation des erreurs et réponses injectées. |
| `test_actor_eligibility_pipeline.py` | Gestionnaire/routes/générateur, deux domaines, modes de personas, zéro acteur, limites et non-mutation du graphe. |
| Tests de préparation/démarrage existants étendus | Artefacts anciens, cache frais/périmé, statut, refus au démarrage et compteur qualifié. |
| `verifier_eligibilite_acteurs.py` + `mesure-009-1.md` | Mesure séparée du classifieur réel ; ce sont des fichiers à créer pendant l'implémentation. |

Les mocks LLM des tests unitaires reproduisent les annotations et les erreurs,
sans simplement tester un mock qui retourne la réponse attendue : vérifier les
messages, les exclusions avant appels et la barrière en aval face à une sortie
malformée ou abusive. Mocker aussi `SimulationConfigGenerator` dans les tests du
pipeline ; les fausses clés globales n'empêchent pas un appel réseau réel.

Adapter les attentes de `test_personas_simulation_graphiti.py` qui produisent
actuellement un troisième profil pour un lieu : attendre les deux acteurs, garder
le lieu en connaissance et vérifier son contexte. Adapter le scénario générique
de `test_zep_entity_reader_graphiti.py` en injectant une qualification valide.
Conserver les tests `test_platform_profiles.py`, `test_profile_field_normalization.py`,
`test_simulation_prepare_failure.py`, `test_zep_simulation_barrier.py`,
`test_graph_reader_refactor.py` et les scripts de qualification existants.
Une modification d'attente doit documenter le défaut corrigé, sans supprimer un test.

La sonde réelle réutilise les fixtures, sans écrire dans un graphe ni lancer une
simulation sociale complète. Son rapport conserve date, commit, versions,
identifiant du modèle, paramètres, messages utiles, sorties brutes/validées,
diagnostics et matrice attendu/obtenu par domaine. Un appel en échec ou un seuil
manqué rend C2 non satisfait ; un mode mock éventuel est identifié comme tel.
Les credentials restent hors des sorties. Ne pas relancer les runs commerciaux
du rapport comme substitut aux deux domaines annotés.

Exécuter sous Docker la suite complète, `ruff check .` et
`python scripts/validate_plans.py`. Pour les tests hermétiques, retirer `.env`,
couper le réseau et monter une copie explicite du code courant : l'image actuelle
peut contenir un arbre ancien (revue, « Contrôles et limites »). Consigner les
commandes réellement exécutées et les skips ; la mesure LLM réelle utilise un
protocole séparé et ne fait pas partie de pytest/CI.

### Documents de référence

- [PRD](prd.md), §4 FR-1/FR-2, NFR-1/3/4/5, §5 C1/C2/C5 et §6.
- [Architecture](architecture.md), §2.1, §3, §5 et §7 ; [hub](epic-009.md).
- [Revue](revue-coherence-2026-10-10.md), R10–R15 et R18 ; [couverture de l'audit](couverture-rapport-audit.md), A01/A02 ; [rapport source](rapport-audit-mirofish-local-first.md), §4 P0 et §7.
- [Constitution](../../../AGENTS.md), §2.1/2.2/2.8/2.9/2.10 ; [suivi](../../sprint-status.yaml) et [état humain](../../STATUS.md).
- [ADR 0001](../../decisions/0001-remplacement-de-zep-par-graphiti.md), [ADR 0003](../../decisions/0003-ontologie-differee-en-v2.md), [ADR 0006](../../decisions/0006-docker-first.md) et [ADR 0011](../../decisions/0011-inventaire-driver-et-format-de-story.md).
- [Lecteur d'entités](../../../backend/app/services/zep_entity_reader.py), [générateur de profils](../../../backend/app/services/oasis_profile_generator.py), [gestionnaire](../../../backend/app/services/simulation_manager.py), [routes](../../../backend/app/api/simulation.py) et [client LLM](../../../backend/app/utils/llm_client.py).
- Documentation officielle Pydantic : [validation stricte](https://docs.pydantic.dev/latest/concepts/strict_mode/) et [contraintes numériques](https://docs.pydantic.dev/latest/api/standard_library_types/#floats), consultées pour contrôler les coercitions et valeurs non finies ; appliquer les API de la version verrouillée.

## Revue

Revue du code à réaliser après implémentation. Examiner en priorité les chemins
de contournement : secours après exception, mode sans LLM personas, générateur
direct, artefacts historiques et démarrage. La relecture du présent contrat ne
valide aucun comportement logiciel ni la mesure réelle C2. La relecture des
46 annotations et les corrections de couverture sont consignées dans la
[preuve de préparation](preparation-009-1.md).

## Notes de complétion

Story rédigée le 10 octobre 2026 à la demande de l'utilisateur, au statut
`backlog`. Aucun modèle, service ou test de fonctionnalité 009 n'est implémenté.
La politique minimale reporte explicitement A02 (marque/fiction) et l'activation
automatique des collectifs. La définition de prêt est satisfaite le même jour :
46 entités annotées et relues, 25 tests d'intégrité ajoutés, contrôle Docker final
de 825 tests collectés (822 réussis, 3 ignorés), lint et plans valides. Voir
[préparation et limites](preparation-009-1.md). T1 est réalisée ; T2 à T9 et toute
la définition de fini restent ouvertes. La story demeure `backlog`, prête pour
le développement métier, sans qualification C1/C2 revendiquée. Compléter cette
section avec résultats, divergences datées et preuves lors de l'implémentation.
