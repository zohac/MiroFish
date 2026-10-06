---
id: "001-5"
epic: "001"
titre: "Script de mesure reproductible et rapport de l'épreuve sur 30 chunks"
statut: backlog
auteur: agent
format: "2"
---

# Story 001-5 — Script de mesure reproductible et rapport de l'épreuve sur 30 chunks

## Pourquoi cette story

L'épreuve Graphiti local (Epic 001) a pour objectif de déterminer empiriquement si le modèle gratuit
`space-bunny-free` sur OpenCode Go est capable d'extraire des entités et des relations
exploitables via Graphiti sur un document parlementaire réel, sans intervention manuelle et à un
coût marginal de 0 € (ADR 0001, ADR 0004 et NFR-1).

Toutes les briques unitaires et préalables techniques sont désormais opérationnels et validés :
1. **Conteneur Neo4j local** : Neo4j 5.26.31-community avec APOC sur compose séparé
   (`docker-compose.neo4j.yml`), testé comportementalement (story 001-2) ;
2. **Driver Neo4j** : forcé à `neo4j 5.28.6` via `override-dependencies` (stories 001-1 et 001-1b) ;
3. **Client LLM** : `MiroFishLLMClient` injectant `x-opencode-session` (0 échec `MissingSessionID`),
   activant `structured_output_mode="json_object"` et relayant `LLM_REASONING_EFFORT` (story 001-3) ;
4. **Embedder local** : `SentenceTransformerEmbedder` avec `all-MiniLM-L6-v2` (384 dimensions),
   opérant hors-ligne en ~7 ms sans clé OpenAI (story 001-4).

Le point de rupture du projet identifié dans `prd.md` et `docs/LOCAL-FIRST.md` §6.3 doit maintenant
être mesuré : un modèle gratuit et léger produit-il un JSON conforme au schéma attendu par
Graphiti sur la durée ?

Cette story assemble ces briques dans un banc de mesure autonome et reproductible
(`backend/scripts/mesurer_extraction_graphiti.py`). Elle exécute l'extraction séquentielle sur les
30 premiers chunks du rapport d'information de l'Assemblée nationale n° 2506, calcule précisément
les critères C1 à C5 de `prd.md`, vérifie la persistance après redémarrage (C3), et consigne
l'ensemble des mesures et erreurs exactes dans le rapport versionné
`docs/plans/001-epreuve-graphiti-local/rapport.md`.

## Définition de prêt

- [ ] Critères Given/When/Then formalisés et mesurables (C1 à C5 de `prd.md`)
- [ ] Document d'épreuve présent dans `backend/uploads/documents/` et validé par son empreinte sha256 (`4281a931545537f56625c3f4d0907fc66f54be82fef5d7b10e655dcdaf72ce88`)
- [ ] Serveur Neo4j d'épreuve prêt à démarrer via `docker compose -f docker-compose.neo4j.yml up -d --wait`
- [ ] Clé OpenCode Go configurée dans l'environnement (`~/.local/share/opencode/auth.json` ou `.env`)
- [ ] Découpeur de texte MiroFish (`FileParser.extract_text`, `split_text_into_chunks`) disponible dans `backend/app/utils/file_parser.py`
- [ ] Piège de `CALL db.indexes()` documenté dans `architecture.md` §4 pris en compte pour la remise à zéro de Neo4j
- [ ] Documents à consulter lus — [`epic-001.md`](epic-001.md), [`prd.md`](prd.md), [`architecture.md`](architecture.md) §4-§6, [ADR 0001](../../decisions/0001-graphiti-neo4j-local.md), [ADR 0004](../../decisions/0004-llm-opencode-go.md), [ADR 0010](../../decisions/0010-override-driver-neo4j.md), [ADR 0011](../../decisions/0011-inventaire-driver-et-format-de-story.md)

## Définition de fini

- [ ] Un script de mesure autonome `backend/scripts/mesurer_extraction_graphiti.py` est implémenté et reproductible
- [ ] Le script valide l'intégrité sha256 du document d'entrée (`backend/uploads/documents/rapport-an-2506-territorialisation-transition-energetique.pdf`)
- [ ] Le script extrait le texte du PDF et le découpe en chunks de 500 caractères (recouvrement 50) via `split_text_into_chunks`
- [ ] Les 30 premiers chunks sont extraits séquentiellement via `graphiti.add_episode(...)`
- [ ] La procédure de remise à zéro de Neo4j nettoie le graphe (`MATCH (n) DETACH DELETE n`) et pose les index sans invoquer la procédure obsolète `CALL db.indexes()`
- [ ] Les métriques C1 (≥ 27/30 chunks sans erreur), C2 (0 `MissingSessionID`), C3 (persistance après redémarrage), C4 (temporalité `valid_at`) sont collectées avec précision
- [ ] Les messages d'erreurs exacts (schémas JSON refusés, timeouts, exceptions de validation) sont journalisés sans perte
- [ ] Le rapport `docs/plans/001-epreuve-graphiti-local/rapport.md` est généré et versionné, consignant les résultats bruts et le tableau complet des 30 chunks
- [ ] Le script supporte un mode `--mock` permettant une exécution rapide et déterministe hors-ligne
- [ ] Une suite de tests hermétiques (`backend/tests/test_mesure_extraction_graphiti.py`) couvre le script en mode mock sans accès réseau ni conteneur externe
- [ ] La suite globale de tests reste 100 % au vert (315+ tests)
- [ ] `ruff check .` et `scripts/validate_plans.py` passent sans avertissement ni erreur
- [ ] Aucun secret ni token n'apparaît dans le diff ou dans `rapport.md`

## Tâches

- [ ] 1. Concevoir le script `backend/scripts/mesurer_extraction_graphiti.py` : arguments CLI (`--mock`, `--limit`, `--chunks-start`), validation sha256 du PDF, découpage en chunks de 500 caractères
- [ ] 2. Implémenter l'initialisation de Graphiti avec `Neo4jDriver`, `MiroFishLLMClient` et `SentenceTransformerEmbedder`
- [ ] 3. Implémenter la remise à zéro sûre du graphe Neo4j sans déclencher `delete_all_indexes` / `CALL db.indexes()`
- [ ] 4. Implémenter la boucle séquentielle d'extraction sur 30 chunks avec mesure des temps, capture d'erreurs fines (schémas refusés vs erreurs réseau) et suivi de la session
- [ ] 5. Implémenter le contrôle de persistance C3 (comptage nœuds/relations, survie au redémarrage Neo4j) et la vérification temporelle C4 (`valid_at`)
- [ ] 6. Implémenter la génération automatique du rapport Markdown `docs/plans/001-epreuve-graphiti-local/rapport.md`
- [ ] 7. Écrire les tests unitaires hermétiques dans `backend/tests/test_mesure_extraction_graphiti.py`
- [ ] 8. Exécuter l'épreuve réelle avec Neo4j et OpenCode Go, archiver les mesures dans `rapport.md` et mettre à jour les statuts de planification

## Notes de développement

**Ce que cette story ne doit pas faire.**
Elle ne doit pas modifier le code de production (`backend/app/services/` ou `backend/app/api/`), qui
demeure branché sur Zep pour l'instant (l'interface `GraphStore` et la migration feront l'objet des
epics 002 et 003). Elle ne doit pas modifier `backend/pyproject.toml` ni `backend/uv.lock`.
Elle ne tranche pas le verdict final go / no-go (c'est l'objet de la story **001-6**).

**Taille des chunks et périmètre de mesure.**
Comme découvert lors du cadrage du PRD (`prd.md` § « Découverte en préparant l'entrée »),
`split_text_into_chunks` découpe en **caractères** et non en mots (`chunk_size=500`, `overlap=50`).
Le document entier génère 562 chunks (~54 mots par chunk). L'épreuve est rigoureusement bornée
aux **30 premiers chunks** (~1 600 mots), ce qui représente un volume d'appels représentatif
et gérable sous le rate-limiting de l'endpoint gratuit.

**Piège de `CALL db.indexes()` sur Neo4j 5.x.**
Dans `graphiti-core 0.30.2`, la méthode `build_indices_and_constraints(delete_existing=True)` appelle
en interne `delete_all_indexes()`, qui tente d'exécuter `CALL db.indexes() YIELD name DROP INDEX name`.
Or sur Neo4j 5.x, cette commande n'existe plus et échoue immédiatement avec `ProcedureNotFound`.
Pour réinitialiser le graphe avant l'épreuve sans provoquer d'erreur :
- Ne pas passer `delete_existing=True` ;
- Vider les données via une requête Cypher explicite : `MATCH (n) DETACH DELETE n` ;
- Appeler `build_indices_and_constraints(delete_existing=False)` pour s'assurer que les index de portée et les contraintes sont bien posés.

**Format d'appel `add_episode` de Graphiti.**
L'insertion d'un chunk s'effectue via :
```python
result = await graphiti.add_episode(
    name=f"Chunk {i:02d}",
    episode_body=chunk_text,
    source=EpisodeType.text,
    source_description="Rapport AN n° 2506",
    reference_time=datetime.now(timezone.utc),
)
```
Le résultat `AddEpisodeResults` expose les nœuds et arêtes créés ou mis à jour, permettant de vérifier
immédiatement le critère C4 (`edge.valid_at is not None`).

**Herméticité en CI.**
Conformément à AGENTS.md §2.2, les tests automatisés ne doivent pas dépendre d'OpenCode Go ni d'un
conteneur Neo4j externe. Le script disposera d'un mode `--mock` activable par paramètre ou
variable d'environnement, simulant les réponses Graphiti de manière déterministe.

## Revue

Revue contradictoire planifiée sur les 4 couches BMad (blind-hunter, edge-case-hunter, verification-gap, acceptance-auditor) :
1. Conformité rigoureuse aux seuils C1 à C5 de `prd.md` ;
2. Résilience face aux erreurs d'API (429, timeouts, schémas JSON invalides) ;
3. Absence d'appel à `CALL db.indexes()` lors de la remise à zéro ;
4. Herméticité des tests unitaires en CI (mode mock déterministe).

## Notes de complétion

À compléter à l'issue de l'exécution de l'épreuve sur les 30 chunks et de la génération du rapport versionné `rapport.md`.
