---
id: "013-2"
epic: "013"
titre: "Mode replay isolé et vérifiable (replay_frozen) avec empreinte SHA-256"
statut: in-progress
auteur: "Antigravity & Équipe MiroFish"
format: "2"
---

# Story 013-2 — Mode replay isolé et vérifiable (`replay_frozen`) avec empreinte SHA-256

Lot B, priorité **P0**. En tant que chercheur et utilisateur de MiroFish, je veux pouvoir relancer la génération d'un rapport sur les preuves figées d'une simulation existante (`replay_frozen`) sans relancer OASIS ni exécuter d'appels interactifs live, et disposer d'une empreinte cryptographique SHA-256 scellant l'ensemble des données d'entrée (`EvidenceSnapshot`), afin de garantir que des modèles ou configurations LLM comparés travaillent sur un jeu de faits strictement identique.

Cette story répond aux exigences fonctionnelles **FR-04** (régénération de rapport sur run existant sans relancer OASIS) et **FR-05** (empreinte cryptographique SHA-256 du jeu de preuves figé), et prépare la validation des critères **C3** (mode replay déterministe) et **C7** (benchmark A/B documenté) de l'Epic 013.

---

## Définition de prêt

- [x] **Objectif compris et cadré** :
  - Introduire le modèle immuable `EvidenceSnapshot` (`backend/app/models/evidence_snapshot.py`) encapsulant `snapshot_id`, `simulation_id`, `sha256_hash`, `file_hashes`, `total_events`, `total_actors`, `has_archived_interviews`, `created_at`.
  - Implémenter le service `EvidenceSnapshotService` (`backend/app/services/evidence_snapshot_service.py`) chargé de capturer, hasher et vérifier l'empreinte cryptographique des artefacts d'une simulation (`observed_events.jsonl`, `actors.json`, `simulation_config.json`, `simulation_brief.json` ou document brief, etc.).
  - Intégrer l'option `replay_mode: str = "live"` ou `"replay_frozen"` dans `ReportAgent` :
    - En mode `replay_frozen`, désactiver les tentatives de dialogue interactif live vers OASIS (utiliser la synthèse hors-ligne `_synthesize_offline_interviews` et ne pas émettre de signaux de terminaison physique d'environnement interactif).
    - Capturer et rattacher l'empreinte `EvidenceSnapshot` au rapport généré (`report.evidence_snapshot` et `meta.json`).
  - Exposer `replay_mode` dans l'endpoint `POST /api/report/generate`.
  - Prouver par des tests unitaires hermétiques que le calcul de hash est déterministe, reproductible et étanche aux modifications non intentionnelles.
- [x] **Documents consultés** :
  - [PRD Epic 013](prd.md) : §3 (objectifs 2 & 3), §4 (FR-04, FR-05), §5 (NFR-1, NFR-2, NFR-4).
  - [Architecture Epic 013](architecture.md) : §2.2 (`EvidenceSnapshot`), flux de replay.
  - [Hub Epic 013](epic-013.md) : FR-04, FR-05, C3, C7.
  - `backend/app/services/report_agent.py` : cycle de vie `generate_report`, `_gather_interviews`, `_synthesize_offline_interviews`, `ReportManager`.
  - `backend/app/services/simulation_audit_service.py` : hachage SHA-256 existant pour le zip d'audit.
  - `backend/app/services/oasis_log_reader_service.py` : lecture des événements observés.
  - `AGENTS.md` : §2.1 (Clean Architecture), §2.2 (tests hermétiques), §2.8 (gestion des plans).
- [x] **Dépendances résolues** :
  - Story 013-1 validée (`ReportLLMProfile` et effort effectif opérationnels).
  - Filet global de tests : **1 852 tests hôte + 9 tests Node frontend au vert**.
- [x] **Décisions d'ingénierie arrêtées avant code** :
  1. **Modèle `EvidenceSnapshot` immuable (`backend/app/models/evidence_snapshot.py`)** :
     - Dataclass `frozen=True` avec sérialisation `to_dict()` et désérialisation `from_dict()`.
     - `sha256_hash` calculé par concaténation triée canonique des hashes individuels des fichiers de preuves (`f"{rel_path}:{sha256}\n"`).
  2. **Service `EvidenceSnapshotService` (`backend/app/services/evidence_snapshot_service.py`)** :
     - Liste canonique ordonnée des fichiers inspectés dans `simulations/<sim_id>/` :
       - `observed_events.jsonl` (ou base SQLite / logs)
       - `actors.json`
       - `simulation_config.json`
       - `simulation_brief.json` (ou brief texte)
       - `source_manifest.json`
       - `interviews_archive.json` (si présent)
     - Calcul du nombre total d'événements observés et d'acteurs qualifiés pour audit rapide sans réouverture des gros fichiers.
  3. **Intégration transparente dans `ReportAgent`** :
     - Paramètre `replay_mode: str = "live"` (défaut rétrocompatible).
     - En mode `replay_frozen` :
       - Pas d'appels live vers le runner OASIS.
       - Capture / vérification automatique de l'empreinte `EvidenceSnapshot`.
       - Renseignement dans `report.replay_mode` et `report.evidence_snapshot`.
       - Enregistrement dans `meta.json` du rapport.
  4. **Exposition API REST** :
     - Paramètre optionnel `replay_mode: Optional[str] = "live"` dans le corps JSON de `POST /api/report/generate`.
- [x] **Stratégie de tests identifiée** :
  - Tests unitaires hermétiques du calcul de hash de `EvidenceSnapshot` (idempotence, détection de modification de fichier, fichier absent).
  - Test validant l'intégration dans `ReportAgent` en mode `replay_frozen` (isolation des appels live, persistance de l'empreinte).
  - Validation de non-régression de l'ensemble de la suite.

---

### Critères d'acceptation

| Réf. | Situation et comportement attendu | Vérification / preuve |
|---|---|---|
| **AC1** | **Dataclass `EvidenceSnapshot` immuable et sérialisable** : Le modèle encapsule les métadonnées et hashes des preuves figées avec sérialisation/désérialisation symétrique. | Test unitaire validant l'immuabilité et le roundtrip `to_dict`/`from_dict`. |
| **AC2** | **Calcul déterministe d'empreinte SHA-256** : `EvidenceSnapshotService.capture_snapshot(simulation_id)` calcule une empreinte globale SHA-256 déterministe et reproductible au bit près pour un même jeu de fichiers. | Test unitaire contrôlant la stabilité de l'empreinte sur des entrées fixes et la sensibilité au moindre changement de contenu. |
| **AC3** | **Mode `replay_frozen` hermétique dans `ReportAgent`** : Lorsqu'un rapport est généré avec `replay_mode="replay_frozen"`, aucun appel IPC / interactif live n'est effectué vers OASIS, et l'empreinte est rattachée au rapport. | Test unitaire instanciant `ReportAgent` en mode `replay_frozen` et vérifiant l'absence d'appels live et la présence du snapshot dans `report.evidence_snapshot`. |
| **AC4** | **Rétrocompatibilité totale du mode `live` par défaut** : En l'absence de paramètre `replay_mode`, le comportement par défaut demeure `replay_mode="live"`. | Test unitaire vérifiant la parité stricte avec le comportement existant. |
| **AC5** | **Exposition dans l'API `POST /api/report/generate`** : La route accepte `replay_mode: Optional[str] = "live"`, transmet l'argument à `ReportAgent`, et renvoie `replay_mode` dans la réponse JSON. | Test unitaire de la route API Flask avec payload `{"replay_mode": "replay_frozen"}`. |
| **AC6** | **Non-régression globale** : Maintien de l'intégralité des 1 852 tests existants du dépôt au vert. | Exécution complète de `pytest tests/` (0 échec). |

---

## Définition de fini

- [ ] `backend/app/models/evidence_snapshot.py` créé avec modèle immuable et méthodes de sérialisation.
- [ ] `backend/app/services/evidence_snapshot_service.py` créé pour la capture déterministe de l'empreinte SHA-256.
- [ ] `backend/app/services/report_agent.py` enrichi du paramètre `replay_mode` et de l'intégration de `evidence_snapshot`.
- [ ] `backend/app/api/report.py` adapté pour recevoir `replay_mode` dans `POST /api/report/generate`.
- [ ] Suite de tests unitaires hermétiques dédiée créée dans `backend/tests/test_evidence_snapshot_replay.py`.
- [ ] Non-régression validée sur l'ensemble des 1 852 tests existants.
- [ ] Revue de code contradictoire BMAD en 4 couches exécutée et documentée.

---

## Tâches

- [ ] 1. Créer le modèle `EvidenceSnapshot` (`backend/app/models/evidence_snapshot.py`).
- [ ] 2. Créer le service de capture et vérification d'empreinte `EvidenceSnapshotService` (`backend/app/services/evidence_snapshot_service.py`).
- [ ] 3. Intégrer le mode `replay_frozen` et la persistance de l'empreinte dans `ReportAgent` (`backend/app/services/report_agent.py`).
- [ ] 4. Mettre à jour la route API `POST /api/report/generate` (`backend/app/api/report.py`).
- [ ] 5. Écrire la suite de tests unitaires hermétiques `backend/tests/test_evidence_snapshot_replay.py`.
- [ ] 6. Vérifier la non-régression complète (`uv run pytest tests/` et `ruff check`).
- [ ] 7. Exécuter la revue contradictoire BMAD en 4 couches et consigner les conclusions.

---

## Notes de développement

*En attente de démarrage de l'implémentation.*

---

## Revue

*En attente de réalisation.*

---

## Notes de complétion

*En attente de complétion.*
