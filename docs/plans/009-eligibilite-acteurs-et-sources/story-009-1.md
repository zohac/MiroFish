---
id: "009-1"
epic: "009"
titre: "Modèle ActorEligibility et classifieur agnostique à deux passes"
statut: done
auteur: agent
format: "2"
---

# Story 009-1 — Modèle `ActorEligibility` et classifieur agnostique à deux passes

Lot A, priorité P0. En tant qu'utilisateur, je veux que seules les personnes et
les organisations qualifiées deviennent des agents OASIS, afin que les produits,
tarifs, sites et concepts restent des connaissances discutées dans la simulation.

Cette story est implémentée et validée après revue (voir `### Review Findings`) :
le modèle, le classifieur, la barrière du générateur, l'intégration au
gestionnaire et aux routes, la preuve de qualification et la mesure réelle sont
livrés. Couverture : FR-1, FR-2, NFR-1, NFR-3, NFR-4, NFR-5 ; C1, C2 et
contribution à C5. Les garanties de réutilisation ci-dessous ferment le
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

- [x] AC1 à AC13 satisfaits, preuves rattachées aux tests et à la mesure réelle ; aucun succès obtenu en excluant tous les acteurs (16 acteurs retenus sur 46 entités, 8/8 par domaine).
- [x] Modèle et service uniques intégrés aux frontières applicatives et aux scripts appelant le générateur, sans branche Zep/Graphiti dans le nouveau code métier.
- [x] Refus d'éligibilité distingué d'une erreur de génération de persona (`ActorNotEligibleError`) ; cache et démarrage ne contournent pas le verrou.
- [x] Les profils Twitter CSV et Reddit JSON restent conformes ; graphe et types d'origine préservés.
- [x] Suite hermétique complète, lint et `validate_plans.py` exécutés sous Docker sur le code courant ; décompte et motifs des éventuels skips consignés (921 réussis, 3 ignorés sous Docker après la revue du 11 octobre 2026, image reconstruite ; 924 réussis sur l'hôte). Les 771 tests du plan initial et les 800 annoncés après 006 sont des jalons, pas un résultat de cette story.
- [x] Mesure C2 réelle consignée sans secrets dans `mesure-009-1.md` ; écarts et conditions d'exécution exposés.
- [x] Revue de code réalisée et corrections traitées ; statut passé par `review` avant `done`.
- [x] Hub, suivi humain et agrégat d'epic actualisés ; notes de complétion renseignées, aucune case cochée sans preuve.

## Tâches

- [x] T1 — Constituer les deux fixtures et relire leurs annotations avant implémentation (AC2, AC5, AC11) ; 46 entités annotées, 25 contrôles d'intégrité, [relecture consignée](preparation-009-1.md). Les comportements AC2/AC5/AC11 restent à implémenter et qualifier.
- [x] T2 — `app/models/actor_eligibility.py` livré : enums `ActorRole`/`EligibilityStatus`, dataclass `ActorEligibility` validée (rationale, confiance finie bornée, rôle passif jamais `eligible`), réponse LLM Pydantic stricte et `qualify_from_response`. Tests `test_actor_eligibility.py` (AC1, AC4, AC5).
- [x] T3 — `app/services/actor_classifier.py` livré : passe 1 déterministe (URL/domaine, montant avec devise, date, durée entiers), client injectable créé paresseusement, réponse validée, diagnostics par entité, empreinte des entrées. Tests `test_actor_classifier.py` (AC2–AC5, AC13).
- [x] T4 — `OasisProfileGenerator` protégé : entrées unitaire et par lots filtrées, `ActorNotEligibleError` distincte, prompt choisi par rôle qualifié, `source_entity_type` d'origine préservé. La création du client LLM de personas est devenue facultative (AC6–AC8).
- [x] T5 — `SimulationManager.prepare_simulation` et `POST /generate-profiles` classifient avant limite, transmettent uniquement les acteurs à la configuration et corrigent les compteurs (`actors_count`, `review_count`, `ineligible_count`). Tests `test_actor_eligibility_pipeline.py` (AC6, AC9, AC11).
- [x] T6 — Preuve `actor_qualifications.json` (politique, projet/graphe, empreinte, UUID retenus) écrite à la préparation ; `/prepare`, `/prepare/status` et `/start` refusent une préparation historique ou périmée. Tests de routes (AC10).
- [x] T7 — Tests historiques adaptés (`test_personas_simulation_graphiti.py`, `test_zep_entity_reader_graphiti.py`, `test_zep_graph_lifecycle.py`, `test_zep_report_barrier.py`) et sonde 004 (`verifier_qualification_local_first.py`) alignée sur la barrière ; aucune suppression de test (AC7–AC11).
- [x] T8 — Sonde `scripts/verifier_eligibilite_acteurs.py` (mode `--mock` identifié) et mesure réelle sur les deux domaines consignée dans [mesure-009-1.md](mesure-009-1.md) et [mesure-009-1.json](mesure-009-1.json) (AC12).
- [x] T9 — Contrôles Docker (suite hermétique, `ruff check .`, `validate_plans.py`), artefacts et suivi mis à jour ; passage en `review`.

### Review Findings

Revue contradictoire à quatre couches du 11 octobre 2026 (diff non commité de la story : code, tests, sondes, docs). Verdicts de triage vérifiés fichier et ligne en main.

- [x] [Review][Patch] AC10 — relecture d'entrées au `/start` (empreinte + consigne), motif transmis ; statut documentaire assumé [backend/app/api/simulation.py:1744] — décision du 11 octobre 2026 : corriger maintenant au démarrage (une lecture de graphe, pas à chaque polling) ; le statut reste un contrôle documentaire.
- [x] [Review][Patch] AC9 — le temps réel utilise `actors_count` quand il est connu ; l'aperçu d'entités du `/prepare` est documenté comme pré-classification ; tests de progression étendus [backend/app/api/simulation.py:1262] — décision du 11 octobre 2026 : préciser les compteurs maintenant.
- [x] [Review][Patch] Empreinte d'entrées non déterministe : listes non triées et ordre instable des voisins/arêtes [backend/app/services/actor_classifier.py:389] — `_canonical` ne trie pas les listes ; `related_nodes` vient d'un `set` (zep_entity_reader.py:348) et `related_edges` d'un Cypher sans `ORDER BY` (`graphiti_store.py`) : après redémarrage du processus, l'empreinte peut changer sans changement d'entrées et forcer une régénération sur `/prepare`.
- [x] [Review][Patch] Le verdict de la mesure C2 ignore les activations `review`→`eligible` et n'utilise pas le champ `match` [backend/scripts/verifier_eligibilite_acteurs.py:155-163] — `passed` ne dépend que de `actors_retained >= 2` et des seuls `ineligible` devenus `eligible` ; un collectif activé passerait en « 0 faux acteur ».
- [x] [Review][Patch] Fixtures : les résumés des cas composites énoncent la conclusion attendue [backend/tests/fixtures/actor_eligibility/*.json] — la mesure réelle montre surtout la capacité à recopier une consigne présente dans la donnée ; le documenter dans mesure-009-1.md et ajouter des cas à résumé neutre si la généralisation doit être prouvée.
- [x] [Review][Patch] Trois rationales corrompus (sorties mélangées du fournisseur) dans la preuve, non signalés [docs/plans/009-eligibilite-acteurs-et-sources/mesure-009-1.json] — (Hugo Bernard, navette, ouverture du festival) ; aucune note dans mesure-009-1.md alors que les écarts doivent être exposés.
- [x] [Review][Patch] mesure-009-1.md n'est pas la sortie de la sonde (champ commit reformulé) et le champ commit a été rempli à la main sans le dire [docs/plans/009-eligibilite-acteurs-et-sources/mesure-009-1.md:5] — `_git_commit()` retournerait « inconnu » dans l'image sans git ; régénérer ou annoter.
- [x] [Review][Patch] Refus de `/start` et `/prepare/status` : le motif de qualification est jeté et le message affiche « status: ready » [backend/app/api/simulation.py:1822-1828,844-856] — `prepare_info` est disponible mais absent de la réponse ; à transmettre (et éviter « not ready / status: ready »).
- [x] [Review][Patch] Diagnostics d'éligibilité en français codés en dur hors dictionnaire [backend/app/services/simulation_manager.py:618-631] — renvoyés tels quels en 400 par `/generate-profiles` et via `task.error` ; le reste de l'API passe par `t()` (défaut zh).
- [x] [Review][Patch] Personas déterministes : le rôle qualifié écrase le gabarit du type d'origine [backend/app/services/oasis_profile_generator.py:864-870] — un étudiant qualifié reçoit « Expert and thought leader », âge 35-60 ; les gabarits student/media deviennent inatteignables.
- [x] [Review][Patch] Mode dégradé sans clé LLM (personas) non observé ni testé [backend/app/services/oasis_profile_generator.py:274-280,588-592] — la génération retombe silencieusement sur le déterministe (un warning) sans indicateur d'état ; aucun test ne fixe le nouveau comportement.
- [x] [Review][Patch] `last_classification` écrit à trois endroits, jamais lu [backend/app/services/oasis_profile_generator.py:288,351,984,987] — mort ou à brancher (KISS).
- [x] [Review][Patch] Identité sans nom mais avec résumé : envoi au LLM et activation possible d'un profil sans nom [backend/app/services/actor_classifier.py:165-183] — `name == ""` + résumé non vide passe en passe 2 ; attendu « identité vide/inexploitable reste review ».
- [x] [Review][Patch] Test de route manquant pour la barrière de `/generate-profiles` (+ `simulation_requirement` absent de la docstring) [backend/app/api/simulation.py:1541-1610] — aucun test n'appelle la route ; injecter/monkeypatcher le classifieur pour prouver le 400 sans acteur.
- [x] [Review][Patch] Appel d'une méthode privée du service depuis la route [backend/app/api/simulation.py:1596] — `SimulationManager._no_actor_diagnostic` ; exposer un point d'entrée public.
- [x] [Review][Patch] `sprint-status.yaml` : trois « commentaires » sont en réalité dans le scalaire `pourquoi` de l'epic 009 [docs/sprint-status.yaml]
- [x] [Review][Patch] Sonde 004-5 : le classifieur d'éligibilité est stubbé sans le dire [backend/scripts/verifier_qualification_local_first.py:177-209] — `DeterministicEligibilityLLMClient` décide par type d'origine ; le rapport ne mentionne pas le stub.
- [x] [Review][Patch] Preuve non liée à sa simulation : paramètre `simulation_id` inutilisé, `simulation_id` stocké jamais comparé [backend/app/api/simulation.py:282-313]
- [x] [Review][Patch] Robustesse du fichier de preuve : écriture non atomique, absence et corruption confondues [backend/app/services/simulation_manager.py:86-99]
- [x] [Review][Patch] Champs écrits jamais lus : `state.qualification_fingerprint` et la liste `qualifications` de la preuve [backend/app/services/simulation_manager.py:129,431,81]
- [x] [Review][Patch] Branche `except ActorNotEligibleError` du lot jamais exercée [backend/app/services/oasis_profile_generator.py:1052-1055] — défense en profondeur à tester (appel direct d'une entité non qualifiée) ou à simplifier.
- [x] [Review][Patch] Tests manquants : le rejet par écart `graph_id`/`project_id` n'est jamais exercé [backend/app/api/simulation.py:301-312]
- [x] [Review][Patch] Sonde 004-4 : `prepare_simulation` appelé sans classifieur — échoue sans clé, appelle le réseau en mode mock [backend/scripts/verifier_personas_simulation_graphiti.py:272-278]
- [x] [Review][Patch] AC4 : seuil 0,7 appliqué aux seules réponses `eligible` [backend/app/models/actor_eligibility.py:204-212] — une exclusion peu confiante reste `ineligible`, sans diagnostic.
- [x] [Review][Patch] Import `EligibilityStatus` inutilisé [backend/app/api/simulation.py:26]
- [x] [Review][Defer] Index documentaires périmés après la barrière [AGENTS.md:535] — deferred: corrections d'index (§4/§11, LOCAL-FIRST.md) et d'état (§1/§2.2 de AGENTS.md, STATUS.md) hors du lot de code, à traiter avec la mise à jour documentaire suivante.
- [x] [Review][Defer] `prd.md` et `architecture.md` toujours en `backlog` et « non implémentés » [docs/plans/009-eligibilite-acteurs-et-sources/prd.md:3] — deferred: mise à jour d'artefacts de plan, à faire à la prochaine actualisation d'epic.
- [x] [Review][Defer] Décompte Docker non reproductible par la commande standard [docker-compose.yml:63-65] — deferred: l'image locale est figée (le compose ne monte pas le code) et `AGENTS.md` §2.9 dit l'inverse ; reconstruction d'image et consignation du protocole à faire dans un geste séparé.

#### Rejected

- [Métadonnées de modèle lues dans l'environnement plutôt que dans le client] : rejeté (`false`) — `Config` charge `.env` dans `os.environ` dès l'import (`load_dotenv(override=True)`, config.py:11) et `_default_client()` l'a déjà importé avant la rédaction du rapport ; le client résout `model`/`base_url` des mêmes sources. La divergence « inconnu » n'existe que sans aucun réglage, cas où la sonde marque déjà `classifier_available` faux et le run en ÉCHEC.
- [Fenêtre de régénération : une préparation périmée serait « already_prepared » pendant l'exécution] : rejeté (`false`) — `prepare_simulation` remet `config_generated=False` avant toute lecture/classification (simulation_manager.py:366-372) et `_check_simulation_prepared` l'exige (simulation.py:444) : pendant la régénération, le statut renvoie la progression et `/start` refuse. La fenêtre décrite n'existe pas.
- [Contrat de message dupliqué entre classifieur et clients de test/sonde] : rejeté (`low`) — la fragilité ne se manifeste qu'en cas de changement du format de prompt, et elle est alors bruyante (les parseurs lèvent, tests et sonde échouent) ; la centralisation proposée est plus qu'une correction directe.

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

Revue de code effectuée après implémentation. Chemins de contournement
examinés : le refus unitaire lève `ActorNotEligibleError` sans créer de profil de
secours ; le lot filtre avant génération ; `use_llm_for_profiles=False`,
`use_llm=False` et le persona de secours ne rouvrent pas la barrière ; les
artefacts historiques sans preuve et les préparations périmées sont refusés au
statut, au démarrage et à la réutilisation. La relecture du présent contrat ne
valide aucun comportement logiciel ; la mesure réelle C2 est consignée dans
[`mesure-009-1.md`](mesure-009-1.md). La relecture des 46 annotations et les
corrections de couverture sont consignées dans la
[preuve de préparation](preparation-009-1.md).

Revue contradictoire à quatre couches du 11 octobre 2026 (Blind Hunter, Edge
Case Hunter, Verification Gap, Acceptance Auditor) sur les changements non
commités : constats et verdicts dans `### Review Findings` (Tâches) ; 25
correctifs appliqués, 3 constats différés (index documentaires, statut du PRD,
décompte Docker), 2 affirmations réfutées par vérification. Les garanties
faibles ont été refermées : relecture d'entrées au `/start`, verdict de la
mesure C2 renforcé, empreinte déterministe, préparation liée à sa simulation,
personas déterministes préservés par type d'origine.

## Notes de complétion

Implémentation du 10 octobre 2026, sur la branche `local-first`, arbre
`2ca4057` + modifications non commitées. La story passe en `review`, puis est
close après la revue contradictoire du 11 octobre 2026 (voir `## Revue`).

Livré :

- `app/models/actor_eligibility.py` (enums, dataclass validée, réponse LLM
  Pydantic stricte, `qualify_from_response`, `ACTOR_ELIGIBILITY_POLICY_VERSION`).
- `app/services/actor_classifier.py` (passe 1 déterministe, passe 2 LLM
  paresseuse, diagnostics par entité, `fingerprint_qualification_inputs`).
- Barrière dans `OasisProfileGenerator` (unitaire et par lots), prompts par rôle,
  `ActorNotEligibleError`.
- Intégration `SimulationManager.prepare_simulation` et `POST /generate-profiles`.
- Preuve `actor_qualifications.json` et contrôles de fraîcheur dans
  `_check_simulation_prepared`, `_qualification_inputs_are_fresh`, `/prepare`,
  `/prepare/status` et `/start`.

Preuves :

- Suite hermétique : **921 réussis, 3 ignorés sous Docker** après la revue du
  11 octobre 2026 (image reconstruite ; les trois skips sont ceux de la
  préparation : CLI Docker absente dans l'image), **924 réussis sur l'hôte**.
  `ruff check .` et `scripts/validate_plans.py` sans erreur.
- Mesure réelle C2 ([`mesure-009-1.md`](mesure-009-1.md)) : modèle `space-bunny`
  sur OpenCode Go, **8/8 acteurs retenus et 0 faux acteur par domaine**, soit
  16/16 acteurs et 0/46 faux acteurs sur les deux domaines. La sonde réelle n'a
  produit aucune écriture de graphe.

Divergences et choix, datés :

- Le constructeur `OasisProfileGenerator` ne lève plus quand `LLM_API_KEY` est
  absent : le client de personas est facultatif, pour laisser la barrière
  produire son diagnostic avant toute génération (exigence de la story). Aucun
  test n'attendait l'ancien `ValueError`.
- La détection de changement d'entités est recomparée par empreinte sur
  `/prepare` (régénération) et, depuis la revue du 11 octobre 2026, refusée sur
  `/start` avec motif (une seule relecture de graphe) ; `/prepare/status` reste
  un contrôle documentaire pour le polling, sans lecture de graphe à chaque
  interrogation.
- La sonde 004 `verifier_qualification_local_first.py` construisait une
  préparation sans classifieur : elle produit désormais un
  `DeterministicEligibilityLLMClient` par type d'entité du graphe de banc. Le
  défaut corrigé est l'absence de barrière à l'époque ; le test conservé n'a pas
  été supprimé.
- La sonde réelle n'a pas pu lire `git rev-parse` dans l'image (git absent) : le
  champ `commit` a été renseigné à la main (`2ca4057`, arbre de travail).

Restent hors de ce lot, conformément au plan : A02 (personnification
marque/fiction), activation automatique des collectifs, `actors.json`, endpoints
et IHM de révision (009-3), brief complet et provenance (009-2).

Corrections de la revue du 11 octobre 2026 (25 correctifs, voir
`### Review Findings`) :

- Empreinte d'entrées triée par contenu (listes comprises) : plus de
  régénération fantôme après redémarrage du processus.
- `/start` refuse une préparation dont les entrées de qualification ont changé
  (motif transmis) ; preuve liée à sa simulation ; écriture atomique et lecture
  distinguant absence et corruption.
- Mesure C2 : une activation `review`→`eligible` compte désormais comme faux
  acteur ; limites de la mesure consignées dans `mesure-009-1.md`.
- Seuil de confiance appliqué à tout statut (une exclusion peu confiante devient
  `review`) ; identité sans nom laissée en `review` sans appel LLM.
- Personas déterministes : le gabarit suit le type d'origine (plus de « Expert
  and thought leader » pour un étudiant) ; compteur `degraded_generations` ;
  `last_classification` mort supprimé.
- Diagnostics `no_actor_diagnostic` localisés via `t()` ; compteurs temps réel
  basés sur les acteurs retenus quand connus ; tests de route de
  `/generate-profiles`, de liaison de preuve et de fraîcheur ajoutés.
- Sondes 004 alignées et honnêtes : classifieur déterministe déclaré pour le
  banc global, barrière injectée pour le banc personas.
