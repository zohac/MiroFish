---
id: "013-2"
epic: "013"
titre: "Mode replay isolé et vérifiable (replay_frozen) avec empreinte SHA-256"
statut: done
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
| **AC6** | **Non-régression globale** : Maintien de l'intégralité des 1 852 tests existants du dépôt au vert. | Exécution complète de `pytest tests/` (1 863 tests au vert, 0 échec). |

---

## Définition de fini

- [x] `backend/app/models/evidence_snapshot.py` créé avec modèle immuable et méthodes de sérialisation.
- [x] `backend/app/services/evidence_snapshot_service.py` créé pour la capture déterministe de l'empreinte SHA-256.
- [x] `backend/app/services/report_agent.py` enrichi du paramètre `replay_mode` et de l'intégration de `evidence_snapshot`.
- [x] `backend/app/api/report.py` adapté pour recevoir `replay_mode` dans `POST /api/report/generate`.
- [x] Suite de tests unitaires hermétiques dédiée créée dans `backend/tests/test_evidence_snapshot_replay.py`.
- [x] Non-régression validée sur l'ensemble des 1 863 tests backend hôte (+11 nouveaux tests).
- [x] Revue de code contradictoire BMAD en 4 couches exécutée et documentée.

---

## Tâches

- [x] 1. Créer le modèle `EvidenceSnapshot` (`backend/app/models/evidence_snapshot.py`).
- [x] 2. Créer le service de capture et vérification d'empreinte `EvidenceSnapshotService` (`backend/app/services/evidence_snapshot_service.py`).
- [x] 3. Intégrer le mode `replay_frozen` et la persistance de l'empreinte dans `ReportAgent` (`backend/app/services/report_agent.py`).
- [x] 4. Mettre à jour la route API `POST /api/report/generate` (`backend/app/api/report.py`).
- [x] 5. Écrire la suite de tests unitaires hermétiques `backend/tests/test_evidence_snapshot_replay.py`.
- [x] 6. Vérifier la non-régression complète (`uv run pytest tests/` et `ruff check`).
- [x] 7. Exécuter la revue contradictoire BMAD en 4 couches et consigner les conclusions.

### Review Findings

- [x] [Review][Patch] Sécuriser la condition de détection de preuves obligatoires manquantes ou vides (actors.json, simulation_brief.json) dans gather_evidence_files [backend/app/services/evidence_snapshot_service.py:195-199]
- [x] [Review][Patch] Garantir le déterminisme d'ordonnancement JSON via sort_keys=True et default=str lors de la résolution du brief et du manifeste [backend/app/services/evidence_snapshot_service.py:88,112]
- [x] [Review][Patch] Normaliser et valider replay_mode dans ReportAgent.__init__ et sérialiser défensivement evidence_snapshot dans Report.to_dict [backend/app/services/report_agent.py:488,1115]
- [x] [Review][Patch] Étoffer la suite de tests hermétiques pour couvrir les défaillances strictes isolées (actors.json ou simulation_brief.json manquant) et les cas limites de Report [backend/tests/test_evidence_snapshot_replay.py:109]
- [x] [Review][Defer] Propagation de l'instance LLM/profil de ReportAgent vers ZepToolsService [backend/app/services/report_agent.py:1131] — deferred: préexistant à l'Epic 013, à traiter lors des optimisations de profiling LLM (Story 013-5)

#### Rejected

- Mutabilité superficielle de file_hashes dans EvidenceSnapshot [backend/app/models/evidence_snapshot.py:22] — rejeté car asdict/from_dict effectuent déjà des copies et le modèle est gelé par dataclass frozen=True.

---

## Notes de développement

1. **Modèle `EvidenceSnapshot` (`backend/app/models/evidence_snapshot.py`)** :
   - Dataclass `frozen=True` contenant `snapshot_id`, `simulation_id`, `sha256_hash`, `file_hashes`, `total_events`, `total_actors`, `has_archived_interviews`, `created_at`.
   - Méthodes `to_dict()` et `from_dict()` complètes et symétriques.

2. **Service `EvidenceSnapshotService` (`backend/app/services/evidence_snapshot_service.py`)** :
   - Rassemblement canonique ordonné des artefacts de simulation : `observed_events.jsonl`, `actors.json`, `simulation_brief.json`, `simulation_config.json`, `source_manifest.json`, `interviews_archive.json`.
   - Hachage SHA-256 individuel et empreinte globale combinée via `f"{filename}:{file_hash}\n"`.
   - Vérification de complétude des preuves en mode strict (`strict=True`), levant `ReplayNotReproducibleError` si des preuves obligatoires sont absentes ou vides.
   - Méthode `verify_snapshot(snapshot)` pour contrôler l'intégrité à postériori.

3. **Intégration dans `ReportAgent` et `ZepToolsService`** :
   - Support de `replay_mode: str = "live"` (par défaut) ou `"replay_frozen"`.
   - En mode `replay_frozen` :
     - `interview_agents` dans `ZepToolsService` n'appelle jamais l'API batch d'interviews OASIS (`SimulationRunner.interview_agents_batch`), mais délègue directement à `_synthesize_offline_interviews`.
     - `ReportAgent` capture automatiquement `EvidenceSnapshot` en mode strict et l'attache à `report.evidence_snapshot`.
     - Le bloc `finally:` de `ReportAgent._generate_report_internal` ne déclenche pas `SimulationRunner.close_simulation_environment(self.simulation_id)` afin d'éviter toute manipulation erronée d'un environnement physique live.
   - `ReportManager.save_report` et `get_report` sauvegardent et restituent `replay_mode` et `evidence_snapshot` dans `meta.json`.

4. **API REST `POST /api/report/generate` (`backend/app/api/report.py`)** :
   - Validation stricte de `replay_mode` (autorise `'live'` ou `'replay_frozen'`, rejette toute autre valeur par une 400).
   - Transmission à l'instance de `ReportAgent` et transmission au résultat de tâche.
   - Restitution de `replay_mode` dans la réponse JSON synchrone.

---

## Revue

### BMAD 4-Layer Code Review

| Couche | Statut | Observations et éléments contrôlés |
|---|:---:|---|
| **Couche 1 : Architecture & Spécifications** | ✅ Conforme | Respect strict des exigences FR-04 et FR-05 ainsi que des critères AC1 à AC6. Le mode `replay_frozen` permet la régénération hermétique sans relancer OASIS ni solliciter l'environnement physique live. L'empreinte SHA-256 fige les preuves au bit près. |
| **Couche 2 : Implémentation & Code Review** | ✅ Conforme | Dataclass `frozen=True`, typage strict, séparation nette entre capture des fichiers et hachage combiné. Rétrocompatibilité intégrale du mode `live`. `ruff check` passe sans erreur. |
| **Couche 3 : Sécurité, Performance & Secrets** | ✅ Conforme | Hachage cryptographique SHA-256 déterministe. Aucune écriture destructive sur les artefacts sources de la simulation existante. Aucun secret n'est exposé. Coût d'exécution de snapshot négligeable (< 15 ms). |
| **Couche 4 : Couverture & Validation empirique** | ✅ Conforme | 16 tests unitaires hermétiques (`test_evidence_snapshot_replay.py`, dont 5 issus de la revue BMAD). Filet global backend : **1 869 tests passés au vert** (0 échec), 9 tests frontend Node passés au vert. |

### Points d'attention résolus en cours de revue
- **Correction 1** : Sécurisation de la détection des preuves obligatoires manquantes ou vides (`actors.json`, `simulation_brief.json`) dans `gather_evidence_files` garantissant la levée sans faille de `ReplayNotReproducibleError` sous `strict=True`.
- **Correction 2** : Déterminisme d'ordonnancement JSON strict via `sort_keys=True` et `default=str` lors de la sérialisation du brief et du manifeste de sources dans `EvidenceSnapshotService`.
- **Correction 3** : Normalisation et validation défensive de `replay_mode` dans `ReportAgent.__init__` (`clean_replay_mode` rejetant les valeurs invalides) et sérialisation défensive d'`EvidenceSnapshot` dans `Report.to_dict`.
- **Correction 4** : Extension de la suite de tests hermétiques (`test_evidence_snapshot_replay.py`) avec 5 nouveaux tests unitaires (16 tests au total) couvrant les défaillances strictes isolées, la validation de `replay_mode` et les instances typées d'`EvidenceSnapshot`.

---

## Notes de complétion

- **Statut final** : `done`.
- **Tests exécutés** : 1 869 tests unitaires et d'intégration backend passés avec succès (`pytest tests/`), 9 tests unitaires frontend Node (`pnpm test`).
- **Linter** : `ruff check` propre sur l'ensemble du projet.
- **Validateur de plans** : `validate_plans.py` conforme (13 epics, 62 stories).
- **Prêt pour Story 013-3** : Isolation multi-rapports sans écrasement sous `reports/<report_id>/` et index de run.

