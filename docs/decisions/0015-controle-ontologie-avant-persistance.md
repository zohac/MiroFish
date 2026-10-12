# 0015 — Contrôle ontologique avant persistance : preuve Graphiti et NO-GO commun

- **Statut** : accepté
- **Date** : 2026-10-12
- **Complète** : [ADR 0014](0014-pose-effective-ontology-graphstore.md), sans le réécrire
- **Concerne** : DoR et C2 de la [story 007-2](../plans/007-ontologie-dynamique/story-007-2.md)
- **Preuve** : [étude de faisabilité](../plans/007-ontologie-dynamique/faisabilite-007-2.md), sonde et mesure liées

## Contexte

La pose des types en 007-1 ne garantit ni le warning ni le refus avant
persistance demandés en 007-2. L’étude Docker des versions verrouillées
(`graphiti-core` 0.30.2, `zep-cloud` 3.25.0) révèle deux situations distinctes.

Graphiti dispose d’un point de contrôle final avant sauvegarde dans
`_process_episode_data`. Un ID d’extraction hors plage est toutefois transformé
en `Entity` avant ce point : la réponse brute doit aussi être contrôlée.
Onze cas contre Neo4j réel démontrent le refus, la rétrogradation et le chemin
batch applicatif. Les signaux du prototype ne sont pas le journal de production.

Zep expose `strict_ontology` sur `graph.add`. Son SDK permet aussi de transmettre
ce champ à `batch.create` par paramètres additionnels. La documentation
[officielle](https://help.getzep.com/customizing-graph-structure) décrit un
filtrage des candidats hors types ; elle ne garantit pas le diagnostic par
candidat requis par C2. Le transport est éprouvé hors ligne, le serveur ne
l’est pas. Aucun point public de contrôle applicatif des candidats avant leur
persistance distante n’a été établi.

L’ADR 0014 §2 annonçait une délégation commune du batch à `add_episode`.
Cette phrase décrit Graphiti, mais pas Zep : notre store Zep utilise directement
`batch.create/add/process`. Ce nouvel ADR précise cette différence sans
modifier la décision acceptée de pose effective des types.

## Décision

**Ne pas autoriser le démarrage de 007-2 sous son contrat commun actuel :
retenir un NO-GO tant que C2 Zep n’est pas démontré ou que son périmètre n’est
pas explicitement révisé.** Le DoR original reste visible et non satisfait.

Le mécanisme Graphiti démontré est le contrôle de la réponse d’extraction
avant normalisation, puis des nœuds hydratés avant délégation à la sauvegarde.
Il couvre le batch séquentiel du store, pas le bulk natif de Graphiti. La
méthode privée est une dépendance à garder par des tests sur la version verrouillée.

Avec une ontologie de types d’entité, ID 0 signifie absence de type métier :
warning en permissif, refus en strict. Un ID hors plage est diagnostiqué comme
tel. Une réponse structurée mal formée est une erreur de validation. Les
fragments valides antérieurs d’un lot restent persistés : aucune atomicité
globale de lot n’est promise.

## Conséquences

- L’investigation est terminée et rejouable ; la story est `blocked` avant
  implémentation par la capacité distante non démontrée.
- Aucune modification de code produit, aucune nouvelle dépendance et aucun
  appel cloud ne sont nécessaires à cette décision.
- C2, l’alignement des deux stores et les critères initiaux restent conservés.
  La restriction à Graphiti ou une nouvelle ingestion Zep exigent un arbitrage
  de périmètre et un complément d’architecture ; ils ne sont pas adoptés ici.
- L’intégration Graphiti devra encore prouver snapshots par requête,
  concurrence, provenance, relations métier et journal durable.

## Alternatives rejetées

- **Cocher le DoR sur la seule présence de `strict_ontology`.** Le filtrage
  serveur n’est pas une exception ni un warning par type refusé.
- **Contrôler après retour ou après traitement du batch.** Les écritures ont
  déjà eu lieu ; les candidats filtrés ne sont plus observables.
- **Supprimer après écriture.** Une compensation ne démontre pas le refus
  avant persistance et peut modifier des données partagées.
- **Recopier le pipeline Graphiti ou modifier le paquet installé.** Le point
  pré-sauvegarde existe ; dupliquer le pipeline ferait diverger le moteur.
- **Déduire la capacité distante d’une réponse HTTP mockée.** Le mock prouve
  uniquement la sérialisation par le SDK, jamais le comportement serveur.
