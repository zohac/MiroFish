---
id: "001-6"
epic: "001"
titre: "Verdict go / no-go documenté et clôture de l'epic 001"
statut: done
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

- [x] Rapport d'épreuve `docs/plans/001-epreuve-graphiti-local/rapport.md` versionné et validé (mesure réelle sur 30 chunks)
- [x] Résultats chiffrés des critères C1 à C5 de `prd.md` confirmés et conformes (C1 ≥ 90 %, C2 = 0, C3 > 0, C4 ≥ 1, C5 = 1)
- [x] Suite globale de tests hermétiques au vert (333 tests passés avec succès)
- [x] Revue contradictoire BMad 4 couches de la story 001-5 achevée et corrigée (8 patchs appliqués)
- [x] Documents à consulter lus — [`epic-001.md`](epic-001.md), [`prd.md`](prd.md), [`rapport.md`](rapport.md), [`docs/STATUS.md`](../../STATUS.md), [`docs/sprint-status.yaml`](../../sprint-status.yaml), [`AGENTS.md`](../../../AGENTS.md) §1 et §7, [ADR 0001](../../decisions/0001-graphiti-neo4j-local.md), [ADR 0004](../../decisions/0004-llm-opencode-go.md)

## Définition de fini

- [x] Le verdict global GO est documenté et motivé dans `docs/STATUS.md` avec le récapitulatif des 5 critères C1-C5
- [x] Les sections d'avancement de `docs/STATUS.md` (« Où on en est », « Fait », « En cours », « À faire ») sont mises à jour pour acter la clôture de l'epic 001 et annoncer l'epic 002
- [x] Les conditions de sortie de `docs/plans/001-epreuve-graphiti-local/epic-001.md` (« L'epic est terminé quand ») sont intégralement cochées
- [x] Le statut de l'epic 001 dans `docs/sprint-status.yaml` passe à `done` avec le bilan consolidé, et l'epic 002 est débloqué pour démarrage
- [x] La constitution `AGENTS.md` §1 (« La tâche du moment ») et §7 (« Définition de fini ») est alignée sur la fin de l'epic 001
- [x] `validate_plans.py` confirme la validité de l'ensemble de la structure documentaire
- [x] Tous les tests existants restent 100 % au vert (`uv run pytest tests/ -q`, 333 tests) et `uv run ruff check .` est vierge
- [x] Aucun secret ni token d'authentification n'apparaît dans le commit

## Tâches

- [x] 1. Rédiger la décision formelle de verdict GO dans `docs/STATUS.md` (critères C1-C5, confirmation de l'hypothèse et feuille de route)
- [x] 2. Mettre à jour les sections de statut (« Où on en est », « Fait », « En cours », « À faire ») dans `docs/STATUS.md`
- [x] 3. Cocher les critères de sortie dans `docs/plans/001-epreuve-graphiti-local/epic-001.md` (« L'epic est terminé quand »)
- [x] 4. Mettre à jour `docs/sprint-status.yaml` (passage de l'epic 001 à `done`, déblocage de l'epic 002)
- [x] 5. Aligner `AGENTS.md` §1 (« La tâche du moment ») sur la clôture de l'epic 001 et le passage au jalon suivant
- [x] 6. Conduire la revue contradictoire BMad 4 couches et vérifier la conformité via `validate_plans.py`, `pytest` et `ruff`

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

Revue contradictoire exécutée selon le protocole BMad 4 couches :

1. **Couche 1 : blind-hunter (audit des faits, chiffres et cohérence de décision)** :
   - Exactitude des chiffres C1-C5 : 29/30 chunks (96.7 %), 0 défaut de session, 49 nœuds et 45 relations Neo4j, 11 arêtes temporelles, rapport versionné. Conforme à l'octet près avec `docs/plans/001-epreuve-graphiti-local/rapport.md`.
   - Règle de décision : C1 ≥ 90 % (seuil à 27) et C2 = 0. La condition stricte de `prd.md` § « Décision attendue à la fin » est satisfaite. Le verdict GO est formel et ne nécessite aucun ADR de contournement payant.
   - Compteur de tests consolidé à 333 (183 initial + 9 revue + 12 001-1b + 30 revue + 45 001-2 + 17 001-3 + 18 001-4 + 17 001-5 + 2 durcissements). Aligné partout.

2. **Couche 2 : edge-case-hunter (cohérence croisée des statuts et artefacts)** :
   - Audit des états inter-documents : `docs/sprint-status.yaml` a basculé l'epic 001 à `done`. L'epic 002 est conservé en `backlog` (débloqué, `depend_de: ["001"]`), évitant l'erreur de `validate_plans.py` qui interdirait un epic `in-progress` sans dossier de plan préalable.
   - Alignement constitutionnel : `AGENTS.md` §1 (« La tâche du moment »), §10 (« Ce qui est déjà réglé ») et §11 (« Contrat de session ») sont parfaitement synchronisés.

3. **Couche 3 : verification-gap (lacunes de vérification et outillage)** :
   - `uv run python scripts/validate_plans.py` exécuté avec succès (0 anomalie détectée).
   - `uv run pytest tests/ -q` confirme 333 tests passés avec 1 warning pydantic amont.
   - `uv run ruff check .` confirme l'absence totale de violation de style ou de lint.
   - Audit git diff : aucun token, secret d'environnement ni clé d'API commité.

4. **Couche 4 : acceptance-auditor (contrôle strict des critères de fini)** :
   - Les 8 critères de la Définition de fini sont tous objectivement vérifiés et cochés.
   - Les 6 tâches de la story sont accomplies.
   - Clôture formelle prête pour la transition finale vers `done`.

## Notes de complétion

**Verdict formel GO acté et clôture de l'Epic 001.**
L'épreuve empirique et technique menée dans l'epic 001 a permis de trancher de manière définitive et incontestable
la question fondatrice du projet MiroFish en mode local-first : l'extraction d'entités et de relations temporelles
par Graphiti sur un document réel sans cloud payant est pleinement réalisable et performante avec un coût marginal
de 0 €.

**Bilan des critères d'acceptation du PRD :**
1. **C1 (Taux d'extraction sans erreur)** : **96.7 % (29/30 chunks)**, surpassant largement le seuil requis de 90 % (≥ 27/30).
   Une unique erreur isolée de validation Pydantic (`ValidationError` sur le chunk 22) a été capturée et tracée sans bloquer la chaîne.
2. **C2 (Session et authenticité)** : **0 échec `MissingSessionID`**, confirmant l'étanchéité parfaite de `MiroFishLLMClient`.
3. **C3 (Persistance graphe Neo4j)** : **49 nœuds et 45 relations** persistés dans le conteneur Neo4j 5.26 et relus après cycle.
4. **C4 (Temporalité des faits)** : **11 arêtes temporelles** avec horodatage `valid_at` explicite.
5. **C5 (Rapport de mesure versionné)** : [`rapport.md`](rapport.md) généré, daté et versionné avec le verdict GO en tête.

**Divergences par rapport aux hypothèses initiales :**
- *Fausse hypothèse de dépendance levée (001-4)* : l'anticipation d'un conflit de versions `sentence-transformers` identique à `neo4j`
  s'est révélée infondée : `graphiti-core` utilise l'abstraction `EmbedderClient` sans extra interne, permettant l'usage direct
  de `sentence-transformers==3.0.0` déjà présent via `camel-oasis`.
- *Cross-encoder local* : le repli pass-through local a permis d'éliminer toute dépendance aux logprobs ou à un reranker externe payant.
- *Délai inter-chunks* : l'ajout d'une pause de 1 seconde entre les chunks a totalement neutralisé le risque de rate-limiting sur OpenCode Go.

**Synchronisation documentaire et passage au jalon suivant :**
- `docs/STATUS.md` : verdict formel GO documenté, bilan consolidé des 6 stories, sections d'avancement et critères mis à jour.
- `docs/sprint-status.yaml` : statut de l'epic 001 passé à `done` avec synthèse complète, epic 002 débloqué pour démarrage.
- `docs/plans/001-epreuve-graphiti-local/epic-001.md` : statut passé à `done`, table des stories à jour, critères de sortie intégralement cochés.
- `AGENTS.md` : alignement constitutionnel de la section 1 (« La tâche du moment »), de la section 10 (« Ce qui est déjà réglé ») et du contrat de session (333 tests).
- Suite de tests : 333 tests 100 % au vert, lint ruff impeccable, `validate_plans.py` sans anomalie.

L'epic 001 est définitivement **clos**. La voie est libre pour le cadrage et le développement de l'**Epic 002 (Interface `GraphStore`)**.
