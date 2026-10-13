---
id: "007-3"
epic: "007"
titre: "Régénération déterministe et budget de performance"
statut: backlog
auteur: "Simon"
format: "2"
---

# Story 007-3 — Régénération déterministe et budget de performance

En tant qu’utilisateur de MiroFish, je veux qu’un même corpus et un même brief
produisent une ontologie reproductible dans un délai mesuré, afin de conserver
un typage stable et de qualifier le coût des futures régénérations.

**Lot B — P1.** Exigences : NFR-3, NFR-6 ; contribution FR-3, C3 et C8.
Dépendances : 007-1 et 007-2 terminées ; Docker de référence opérationnel.
Les événements E1–E4, le versionnement et les endpoints de régénération restent
à réaliser en 007-4. Cette story prépare le générateur et une sonde autonome.

## Définition de prêt

- [x] PRD §4/C3, architecture §1/§10, epic §4 et constitution consultés.
- [x] 007-1 fournit la pose effective ; 007-2 fournit la politique durable et
  son refus pré-persistance (ADR 0014, 0016, 0017).
- [x] Générateur, client LLM et tests existants analysés : température actuelle
  `0.3`, interface publique conservée, reprises JSON déjà disponibles.
- [x] Champs stables, périmètre du chronométrage et stratégie de preuve définis.
- [x] Tests hermétiques et qualification réelle séparés ; fixtures télécom et
  énergie identifiées et réutilisables sans dépendre des uploads privés.
- [ ] Avant implémentation : figer les fichiers 10K/50K et leurs briefs dans le
  dépôt, vérifier leurs tailles et préparer la configuration LLM de mesure.

### Critères d’acceptation

| Réf. | Contrat mesurable | Vérification |
|---|---|---|
| AC1 | `OntologyGenerator.generate` transmet explicitement `temperature=0.0` au client livré. Sa signature et les paramètres des autres consommateurs LLM restent inchangés ; `max_tokens=None` et `max_attempts=2` sont préservés. | Client enregistreur puis transport HTTP doublé : la température zéro atteint la requête effective, y compris après reprise JSON. Aucun test limité à lire une constante. |
| AC2 | Avec documents ordonnés, brief, contexte additionnel, langue et configuration identiques, deux appels produisent des messages identiques et les mêmes diagnostics de contexte. Chaque appel effectue une génération indépendante. | Deux appels sur une même instance puis deux instances neuves ; comparer les messages réellement transmis et `last_context_diagnostics`. Aucune date, UUID ou ordre aléatoire ajouté au prompt. |
| AC3 | Deux générations indépendantes de chacun des corpus 10K et 50K ont une projection identique des noms de types d’entité, de relation et de leurs attributs. Le nom d’attribut reste rattaché à son type parent. | Diff JSON canonique des résultats post-traités ; ordre des types/attributs neutralisé par tri, doublons conservés pour ne pas les masquer. Descriptions, exemples et `analysis_summary` sont hors comparaison C3 ; sorties complètes conservées pour audit. |
| AC4 | Chaque résultat mesuré est valide et effectivement posé via `GraphStore.set_ontology`, avec la politique stricte du graphe conservée. La mesure n’utilise pas un résultat déjà présent ni un cache du premier essai. | Sonde sur graphes dédiés Graphiti, relecture par instance neuve de l’état appliqué. Erreur de génération ou de validation : pas de pose du résultat invalide, état antérieur intact. |
| AC5 | Pour chaque essai 50K, temps total de lecture des documents jusqu’au retour réussi de `set_ontology` **< 45 s sous Docker**. Le seuil hôte **< 30 s** du PRD est conservé et mesuré dans une session de secours distincte. Les essais 10K ont aussi une durée publiée. | Horloge monotone ; durées individuelles et phases, sans sélectionner seulement le meilleur essai ni soustraire reprises/attentes réseau. Aucun verdict C3 complet si la preuve hôte manque. |
| AC6 | La sonde produit une preuve rejouable, versionnée, avec verdict par critère et code de sortie non nul sur différence, dépassement ou erreur. Un mode avec LLM simulé ne vaut jamais preuve de C3 réel. | Sorties JSON, empreintes des corpus, briefs, messages et sources, configuration non secrète du fournisseur/modèle, paramètres effectifs, résultats, diagnostics et durées. Tests de la sonde avec horloge et clients contrôlés. |
| AC7 | Les contrats de génération existants sont conservés : au plus 10 types, types de repli, normalisation des noms et attributs, résolution des extrémités de relation, budget de contexte et absence de fuite documentaire vers le message système. | Régressions existantes ; marqueurs distincts dans documents, brief et contexte additionnel, inspectés dans les messages LLM. Aucun nouveau catalogue métier. |
| AC8 | Au moins **20 nouveaux tests hermétiques** ; suite Docker sans échec, lint et plans valides. Le filet de départ est **1431 collectés / 1428 réussis + 3 ignorés**. | Compteurs, commandes et limites dans les notes de complétion ; pytest ne contacte ni fournisseur LLM ni Neo4j réel. |

## Définition de fini

- [ ] AC1–AC8 satisfaits et preuves rattachées à chaque critère.
- [ ] Deux générations réellement indépendantes par corpus, aucune substitution
  du résultat attendu ni réutilisation silencieuse du premier résultat.
- [ ] Mesures Docker et hôte distinctes consignées ; seuils non affaiblis.
- [ ] Sonde du parcours livré réutilisable par 007-7, sorties versionnées et
  nettoyage limité aux graphes temporaires qu’elle a créés.
- [ ] Tests Docker, `ruff check .`, `validate_plans.py` et diff contrôlés.
- [ ] Revue effectuée après passage en `review`, correctifs traités.
- [ ] Notes de complétion, hub, suivi agrégé et contexte actualisés ; aucun secret.

## Tâches

- [ ] T1 — Figer les entrées de qualification (AC2, AC3, AC5).
  Réutiliser les fixtures télécom/énergie de 007-1 ; préparer deux corpus UTF-8
  de **10 000 et 50 000 caractères Python**, hors brief/contexte additionnel,
  avec manifeste d’ordre et SHA-256. Leur composition doit rester intelligible,
  sans remplissage répétitif destiné à rendre artificiellement le LLM rapide.
- [ ] T2 — Passer la température du générateur à zéro (AC1, AC7).
  Vérifier le transport réel via les helpers existants et la reprise JSON ;
  conserver la signature et les budgets de sortie du générateur.
- [ ] T3 — Vérifier la construction reproductible du contexte (AC2, AC7).
  Préserver échantillonnage, bornes documentaires et diagnostics 009-2 ; corriger
  seulement une source de variabilité effectivement démontrée.
- [ ] T4 — Écrire la projection canonique et ses régressions (AC3).
  Trier par nom de type et par nom d’attribut dans chaque type ; ne pas aplatir
  tous les noms en un ensemble. Prouver qu’ajout/retrait/renommage/déplacement
  d’attribut vers un autre type produit un diff, et qu’un changement de
  description seul ne change pas le verdict des champs stables.
- [ ] T5 — Créer `backend/scripts/verifier_ontology_regeneration.py` (AC4–AC6).
  Appeler `OntologyGenerator.generate` puis le contrat neutre `GraphStore`,
  lire la politique effective avant pose et la transmettre explicitement.
  Ne pas accéder directement au SDK Zep depuis un service.
- [ ] T6 — Tester la sonde et ses verdicts sans réseau (AC4–AC6, AC8).
  Doubler uniquement les frontières externes et l’horloge ; tester dépassement,
  changement structurel, erreur LLM, validation refusée, politique conservée
  et nettoyage sur exception. Ne pas construire un faux pipeline validant
  qui rendrait les tests verts lorsque le contrôle livré est retiré.
- [ ] T7 — Rejouer les quatre générations réelles sous Docker (AC3–AC6).
  Consigner `mesure-007-3-docker.json` et un protocole explicite. Organiser
  séparément la mesure hôte `mesure-007-3-hote.json` conformément à l’ADR 0006.
- [ ] T8 — Exécuter le filet complet, rédiger la complétion et passer en revue
  (AC7, AC8). 007-7 orchestrera cette sonde ; ne pas créer son banc global ici.

## Notes de développement

### Documents et fichiers à consulter

- [PRD](prd.md), [architecture](architecture.md), [epic](epic-007.md),
  [007-1](story-007-1.md), [007-2](story-007-2.md) et sa
  [qualification livrée](qualification-007-2.md).
- ADR [0006](../../decisions/0006-docker-first.md),
  [0014](../../decisions/0014-pose-effective-ontology-graphstore.md),
  [0016](../../decisions/0016-perimetre-validation-ontologie-graphiti.md),
  [0017](../../decisions/0017-politique-ontologique-durable-et-retrogradation-transactionnelle.md).
- `backend/app/services/ontology_generator.py`,
  `backend/app/utils/llm_client.py`, `backend/app/utils/llm_compat.py`,
  `backend/app/utils/ontology.py`, `backend/app/utils/graph_store/base.py`.
- `backend/tests/test_ontology_generator.py`, `test_ontology_attributes.py`,
  `test_llm_client.py`, `test_config_context_budget.py`,
  `test_ontology_persistence_contract.py`, `test_ontology_validation_pipeline.py`.
- `backend/tests/fixtures/ontology/{telecom,energie}/` et
  `backend/scripts/verifier_ontology_validation.py` pour la séparation
  entre sonde réelle et tests hermétiques ainsi que le nettoyage des ressources.

### État actuel et modifications attendues

`generate(document_texts, simulation_requirement, additional_context=None)`
construit deux messages, enrichit le système avec la langue, puis appelle
`chat_json(temperature=0.3, max_tokens=None, max_attempts=2)`. Il retourne le
dictionnaire post-traité et expose `last_context_diagnostics`, réinitialisé
au début de chaque appel. Réduire la température ici ; ne pas changer le défaut
global de `LLMClient.chat_json`, utilisé par d’autres fonctions.

Le contexte documentaire est plafonné à 50K caractères avec chunks de 8K,
recouvrement 200, échantillonnage représentatif et conservation des extrémités.
Le seuil concerne le **contexte documentaire**, pas la longueur totale des
messages avec brief et consignes. Publier taille brute, taille utilisée et
nombre de fragments retenus ; ne pas qualifier un corpus court comme « 50K »
au seul motif que la limite configurée vaut 50K.

`_validate_and_process` normalise les noms, élimine certains doublons, ajoute
`Person`/`Organization`, plafonne à `MAX_ONTOLOGY_TYPES` et résout les extrémités
après plafonnement. Conserver ces interactions. La projection C3 porte sur le
résultat livré, pas uniquement sur la réponse brute du fournisseur.

`LLMClient` gère déjà compatibilité OpenCode Go, en-têtes de session, JSON,
reprises et erreurs. Réutiliser ce client ; ne pas ajouter un SDK ni imposer
`seed` à un endpoint qui ne le démontre pas. Aucune dépendance ni mise à niveau
n’est nécessaire. Les locks restent les références de versions.

### Mesure et limites de la preuve

La sonde prépare le store et son graphe isolé avant le chronométrage de chaque
régénération, puis mesure lecture des fichiers → contexte → LLM et reprises →
post-traitement → validation/traduction → pose durable réussie. L’initialisation
à froid est publiée séparément, jamais confondue avec le temps de régénération.
Les deux essais de chaque corpus sont consécutifs, sans cache et avec paramètres
identiques. Ne pas ajouter de seuil d’annulation au produit : les 30/45 secondes
sont des seuils de qualification, pas un nouveau timeout fonctionnel.

Une température nulle ne garantit pas à elle seule des réponses identiques.
La [documentation officielle sur la reproductibilité](https://cookbook.openai.com/examples/reproducible_outputs_with_the_seed_parameter)
précise aussi les limites de répétabilité côté fournisseur. Cela ne démontre
aucune capacité spécifique d’OpenCode Go. C3 exige une **répétabilité observée
sur les fixtures et le fournisseur mesurés** ; si elle échoue, publier le diff
et un NO-GO, sans masquer la variation par cache ou modifier le seuil.

Les mesures réelles sont séparées de pytest. La preuve hôte se fait dans une
session de secours explicite, pas en mélangeant les environnements au sein
d’une session Docker. Si elle manque, conserver le critère ouvert et nommer
la limite. Ne pas déclarer C3 entièrement satisfait sur la seule preuve Docker.

### Régressions et périmètre

La revue 007-2 a montré qu’une preuve de prototype et des tests d’un helper
isolé pouvaient laisser le câblage livré non vérifié. Exercer ici `generate`
et le transport effectif, conserver les instantanés bruts et les résultats
post-traités. Un changement de politique seul ne retype aucun nœud ; le refus
Zep strict reste celui de l’ADR 0016. Ne pas créer `OntologyVersion`,
`ontology_history`, endpoints, fusion de versions ou boucle de régénération
sur événement : ces travaux appartiennent aux stories suivantes.

Commandes de validation dans l’environnement de référence :

```bash
docker compose build backend
docker compose run --rm backend uv run pytest tests/ -q
docker compose run --rm backend uv run ruff check .
docker compose run --rm backend uv run python scripts/validate_plans.py
# Après implémentation de la sonde :
docker compose run --rm backend uv run python scripts/verifier_ontology_regeneration.py
```

## Revue

Ticket rédigé le **13 octobre 2026** à partir du code et du contrat C3.
L’implémentation et sa revue de code restent à effectuer. La revue du ticket
vérifie notamment les générations indépendantes, les champs comparés, le
périmètre du chronométrage et la séparation Docker/hôte.

## Notes de complétion

Préparation du ticket uniquement : aucun changement du générateur, aucun
nouveau test produit et aucune mesure C3 annoncée. Le passage à `in-progress`
nécessite de compléter la définition de prêt ; la livraison devra consigner
les commandes, sorties, écarts éventuels et résultats des deux environnements.
