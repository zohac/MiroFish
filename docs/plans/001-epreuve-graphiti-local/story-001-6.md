---
id: "001-6"
epic: "001"
titre: "Verdict go / no-go documenté et clôture de l'epic 001"
statut: backlog
auteur: agent
format: "2"
---

# Story 001-6 — Verdict go / no-go documenté et clôture de l'epic 001

## Pourquoi cette story

L'epic 001 (« Épreuve Graphiti local ») a été conçu pour tester le point de rupture technique et économique
majeur du projet MiroFish en mode local-first : déterminer si le modèle d'inférence gratuit et léger
`space-bunny` (sur OpenCode Go) est capable d'extraire des entités et des relations exploitables via
Graphiti sur un document parlementaire réel, sans intervention manuelle et à un coût marginal de 0 €
(ADR 0001, ADR 0004, NFR-1).

L'ensemble des étapes d'ingénierie préalables et des briques unitaires ont été implémentés, testés
et validés :
1. **Résolution du conflit de dépendances** : l'`override-dependencies` du driver `neo4j` forcé à `5.28.6`
   sans extra pour `graphiti-core 0.30.2` a été posé et prouvé réversible (stories 001-1 et 001-1b) ;
2. **Contact serveur et persistance** : le conteneur `Neo4j 5.26.31-community` avec APOC sur compose
   séparé (`docker-compose.neo4j.yml`) a subi avec succès 17 contrôles comportementaux et confirmé la
   survie des données aux redémarrages (story 001-2) ;
3. **Client LLM compatible** : `MiroFishLLMClient` injecte automatiquement `x-opencode-session`, active
   `structured_output_mode="json_object"` et relaie `LLM_REASONING_EFFORT` sans régression pour les
   autres fournisseurs (story 001-3) ;
4. **Embedder local autonome** : `SentenceTransformerEmbedder` (`all-MiniLM-L6-v2`, 384 dimensions)
   opère localement en ~7 ms sans clé OpenAI ni extra (story 001-4) ;
5. **Banc de mesure et épreuve réelle** : le banc autonome `backend/scripts/mesurer_extraction_graphiti.py`
   a exécuté l'épreuve complète sur les 30 premiers chunks du rapport de l'Assemblée nationale n° 2506
   (story 001-5) et produit le rapport versionné `docs/plans/001-epreuve-graphiti-local/rapport.md`.

Les résultats mesurés en conditions réelles sont les suivants :
- **C1 (Taux d'extraction sans erreur)** : **29/30 chunks (96.7 %)**, surpassant le seuil d'acceptation de 90 % (≥ 27/30).
  La seule anomalie rencontrée (chunk 22) est une erreur isolée de validation Pydantic (`ExtractedEntities`),
  parfaitement tracée sans blocage de la chaîne d'extraction.
- **C2 (Authentification et session)** : **0 échec `MissingSessionID`**, aucune déconnexion ni rejet d'en-tête.
- **C3 (Persistance du graphe Neo4j)** : **49 nœuds et 45 relations** persistés dans Neo4j et relus avec succès.
- **C4 (Temporalité des faits)** : **11 arêtes temporelles** avec attribut `valid_at` explicite.
- **C5 (Rapport de mesure)** : [`rapport.md`](rapport.md) généré, daté et versionné.

Conformément à la règle de décision de `prd.md` (§ « Décision attendue à la fin »), tous les critères
critiques (C1 à C5) étant validés, le verdict est formellement **GO** : aucun modèle payant externe n'est
requis pour l'extraction de connaissances.

Cette story 001-6 a pour mission de formaliser la décision, de synchroniser l'ensemble de la documentation
d'état (`docs/STATUS.md`, `docs/sprint-status.yaml`, `docs/plans/001-epreuve-graphiti-local/epic-001.md`,
`AGENTS.md`) et de clôturer définitivement l'epic 001, débloquant ainsi le démarrage de l'epic 002
(Interface `GraphStore`).

## Définition de prêt

- [ ] Rapport d'épreuve `docs/plans/001-epreuve-graphiti-local/rapport.md` versionné et validé (mesure réelle sur 30 chunks)
- [ ] Résultats chiffrés des critères C1 à C5 de `prd.md` confirmés et conformes (C1 ≥ 90 %, C2 = 0, C3 > 0, C4 ≥ 1, C5 = 1)
- [ ] Suite globale de tests hermétiques au vert (333 tests passés avec succès)
- [ ] Revue contradictoire BMad 4 couches de la story 001-5 achevée et corrigée (8 patchs appliqués)
- [ ] Documents à consulter lus — [`epic-001.md`](epic-001.md), [`prd.md`](prd.md), [`rapport.md`](rapport.md), [`docs/STATUS.md`](../../STATUS.md), [`docs/sprint-status.yaml`](../../sprint-status.yaml), [`AGENTS.md`](../../../AGENTS.md) §1 et §7, [ADR 0001](../../decisions/0001-graphiti-neo4j-local.md), [ADR 0004](../../decisions/0004-llm-opencode-go.md)

## Définition de fini

- [ ] Le verdict global GO est documenté et motivé dans `docs/STATUS.md` avec le récapitulatif des 5 critères C1-C5
- [ ] Les sections d'avancement de `docs/STATUS.md` (« Où on en est », « Fait », « En cours », « À faire ») sont mises à jour pour acter la clôture de l'epic 001 et annoncer l'epic 002
- [ ] Les conditions de sortie de `docs/plans/001-epreuve-graphiti-local/epic-001.md` (« L'epic est terminé quand ») sont intégralement cochées
- [ ] Le statut de l'epic 001 dans `docs/sprint-status.yaml` passe à `done` avec le bilan consolidé, et l'epic 002 est débloqué pour démarrage
- [ ] La constitution `AGENTS.md` §1 (« La tâche du moment ») et §7 (« Définition de fini ») est alignée sur la fin de l'epic 001
- [ ] `validate_plans.py` confirme la validité de l'ensemble de la structure documentaire
- [ ] Tous les tests existants restent 100 % au vert (`uv run pytest tests/ -q`, 333 tests) et `uv run ruff check .` est vierge
- [ ] Aucun secret ni token d'authentification n'apparaît dans le commit

## Tâches

- [ ] 1. Rédiger la décision formelle de verdict GO dans `docs/STATUS.md` (critères C1-C5, confirmation de l'hypothèse et feuille de route)
- [ ] 2. Mettre à jour les sections de statut (« Où on en est », « Fait », « En cours », « À faire ») dans `docs/STATUS.md`
- [ ] 3. Cocher les critères de sortie dans `docs/plans/001-epreuve-graphiti-local/epic-001.md` (« L'epic est terminé quand »)
- [ ] 4. Mettre à jour `docs/sprint-status.yaml` (passage de l'epic 001 à `done`, déblocage de l'epic 002)
- [ ] 5. Aligner `AGENTS.md` §1 (« La tâche du moment ») sur la clôture de l'epic 001 et le passage au jalon suivant
- [ ] 6. Conduire la revue contradictoire BMad 4 couches et vérifier la conformité via `validate_plans.py`, `pytest` et `ruff`

## Notes de développement

**Justification du verdict GO.**
Le PRD de l'epic 001 posait une règle de décision binaire : si C1 < 90 % ou C2 > 0, verdict NO-GO imposant
le recours à un modèle commercial payant consigné dans un nouvel ADR.
Les mesures réelles démontrent une robustesse remarquable du modèle gratuit `space-bunny` :
- C1 = 96.7 % (29/30 chunks extraits sans erreur, au-delà des 90 % exigés) ;
- C2 = 0 défaut de session (étanchéité parfaite de `MiroFishLLMClient`) ;
- C3 = 49 nœuds et 45 relations persistés dans Neo4j 5.26 ;
- C4 = 11 relations temporelles horodatées (`valid_at`).
Le verdict est donc un **GO franc et sans réserve**. Aucun modèle payant n'est requis pour la suite
du développement, validant la thèse du projet (0 € marginal).

**Ce que cette story ne doit pas faire.**
Cette story a un rôle de gouvernance, de documentation d'architecture et de clôture d'epic. Elle ne doit
pas implémenter le code de l'interface `GraphStore` ni de ses implémentations concrètes (`ZepGraphStore`,
`GraphitiGraphStore`), qui font l'objet des epics 002 et 003.

**Synchronisation stricte des artefacts.**
Conformément à AGENTS.md §2.8 :
- `docs/sprint-status.yaml` est la source unique d'agrégat d'epic ;
- `docs/STATUS.md` en est la restitution humaine détaillée ;
- `docs/plans/001-epreuve-graphiti-local/epic-001.md` est le contrat d'ingénierie local ;
- `AGENTS.md` est la constitution du dépôt.
Aucune divergence d'état ou d'indicateur ne doit subsister entre ces quatre documents.

## Revue

Revue contradictoire planifiée sur les 4 couches BMad (blind-hunter, edge-case-hunter, verification-gap, acceptance-auditor) :
1. Exactitude mathématique des critères C1 à C5 reportés depuis `rapport.md` ;
2. Cohérence du verdict GO avec les règles de décision fixées dans `prd.md` ;
3. Absence d'incohérence ou de redondance contradictoire entre `STATUS.md`, `sprint-status.yaml`, `epic-001.md` et `AGENTS.md` ;
4. Validation stricte par `validate_plans.py`.

## Notes de complétion

À compléter lors de la prise de décision formelle et de la clôture de l'epic 001.
