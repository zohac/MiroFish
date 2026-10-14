---
id: "010-1"
epic: "010"
titre: "Arrêt déterministe (--no-wait) et statut COMPLETED automatique"
statut: backlog
auteur: "Antigravity & Équipe MiroFish"
format: "2"
---

# Story 010-1 — Arrêt déterministe (`--no-wait`) et statut `COMPLETED` automatique

Lot A, priorité **P0**. En tant qu'utilisateur de MiroFish, je veux que la simulation s'arrête de manière totalement autonome dès que l'ensemble des rounds programmés sont terminés et que son statut bascule immédiatement à `COMPLETED`, afin de ne plus avoir à intervenir manuellement pour débloquer la fin de la simulation ou forcer son arrêt.

Cette story répond directement à l'exigence fonctionnelle **FR-1** de l'Epic 010, contribue aux critères de sortie **C1** (100 % des simulations achevées passent à `COMPLETED` en moins de 5 secondes) et **C5** (filet de tests de référence enrichi et maintenu au vert), tout en respectant l'exigence de propreté des processus **NFR-3** (zéro processus zombie ou en veille orpheline).

---

## Définition de prêt

- [ ] Objectif compris : injecter par défaut `--no-wait` dans la commande CLI de `run_parallel_simulation.py` au lancement depuis `SimulationRunner`, détecter l'achèvement effectif de l'ensemble des plateformes actives dans `_monitor_simulation`, envoyer la commande IPC `send_close_env()` si le processus tarde à quitter, et basculer de façon déterministe vers `RunnerStatus.COMPLETED` après drain mémoire complet sans jamais nécessiter d'appel manuel à `POST /api/simulation/stop`.
- [ ] Documents consultés :
  - [PRD Epic 010](prd.md) : §1 (deadlock de fin de simulation), §2 (objectifs produit), §3 (critère C1).
  - [Architecture Epic 010](architecture.md) : §1 (diagramme de séquence de fin de cycle), §2.1 (arrêt déterministe).
  - [Hub Epic 010](epic-010.md) : FR-1 (arrêt automatique), NFR-1 (non-régression), NFR-3 (propreté des processus).
  - `backend/app/services/simulation_runner.py` : construction de la commande `cmd` (l. 516-525), boucle de monitoring `_monitor_simulation` (l. 639-745), lecture des logs et complétion (l. 804-828, 881-906).
  - `backend/scripts/run_parallel_simulation.py` : gestion de `--no-wait` et boucle `wait_for_commands` (l. 1539, 1599-1638).
  - `backend/tests/test_zep_simulation_barrier.py` : préservation du verrou et de la barrière de drain mémoire `ZepGraphMemoryManager`.
  - [AGENTS.md](../../../AGENTS.md) : §2.1 (clean architecture), §2.2 (qualité des tests), §2.8 (gestion des plans).
- [ ] Dépendances résolues :
  - Epic 005 (Docker de référence unifié), Epic 007 (Ontologie dynamique v2), Epic 009 (Éligibilité des acteurs et fiabilisation des sources) sont clos avec succès.
  - Filet de tests au démarrage : **1550 tests réussis sur l'hôte**, 1547 réussis + 3 ignorés sous Docker.
- [ ] Décisions d'ingénierie arrêtées avant code :
  1. **Comportement par défaut déterministe** : `--no-wait` est systématiquement transmis par `SimulationRunner._start_simulation` pour les simulations standard pilotées par l'API et l'IHM. Un champ facultatif `keep_alive_on_completion: bool = False` dans la configuration permettra de désactiver ce comportement dans l'éventualité de scénarios d'interviews interactives post-simulation.
  2. **Supervision active de complétion** : `_monitor_simulation` ne doit plus se reposer uniquement sur la sortie passive du processus (`while process.poll() is None:`). Dès que `_check_all_platforms_completed(state)` est `True`, un compte à rebours de grâce s'enclenche.
  3. **Arrêt gracieux par IPC puis terminaison forcée** : si le sous-processus ne s'éteint pas au terme de la temporisation de grâce (5 s), le runner transmet l'ordre IPC `close_env` via `SimulationIPCService.send_close_env()`. Si le processus résiste encore après 5 s supplémentaires, `_terminate_process` est invoqué.
  4. **Invariant de la barrière mémoire** : le passage au statut `RunnerStatus.COMPLETED` s'effectue strictement au sein du bloc `with cls._finalization_lock(simulation_id):` après que `ZepGraphMemoryManager.stop_updater()` a totalement vidé les activités en attente vers Neo4j. Si le drain échoue, la simulation bascule en `RunnerStatus.FAILED` conformément au contrat de fiabilité existant.
- [ ] Stratégie de tests identifiée : suite unitaire hermétique (`backend/tests/test_simulation_runner_completion.py`) mockant `subprocess.Popen`, `_check_all_platforms_completed` et `ZepGraphMemoryManager`, complétée par la vérification de non-régression sur `test_zep_simulation_barrier.py`.

---

### Critères d'acceptation

| Réf. | Situation et comportement attendu | Vérification |
|---|---|---|
| **AC1** | **Injection systématique de `--no-wait`** : Lors du lancement d'une simulation standard par `SimulationRunner._start_simulation`, l'argument `--no-wait` est injecté dans la liste d'arguments `cmd` passée à `run_parallel_simulation.py`. Si la configuration spécifie explicitement `keep_alive_on_completion=True`, l'argument n'est pas ajouté. | Tests unitaires sur `SimulationRunner._start_simulation` vérifiant la composition de `cmd` selon les options de configuration. |
| **AC2** | **Détection active de complétion des plateformes** : Dans `_monitor_simulation`, lorsque `_check_all_platforms_completed(state)` devient vrai (chaque plateforme activée a loggué l'événement `simulation_end`), le runner consigne l'achèvement et amorce la procédure de finalisation sans bloquer indéfiniment. | Test unitaire simulant la lecture d'un log `simulation_end` et constatant l'initiation de la finalisation. |
| **AC3** | **Arrêt gracieux par commande IPC et fermeture propre** : Si le processus de simulation reste actif après la fin de l'ensemble des plateformes, le runner émet la commande IPC `close_env` après un délai de 5 s. Si le processus ne s'est toujours pas éteint après un timeout de secours de 5 s supplémentaires, `_terminate_process` est exécuté. | Test unitaire avec sous-processus mocké ne répondant pas immédiatement, validant l'appel à `send_close_env()` puis la terminaison de sécurité. |
| **AC4** | **Transition automatique vers `COMPLETED` et horodatage** : Lorsque le processus s'éteint normalement (code 0) et que la vidange mémoire réussit, `state.runner_status` passe à `RunnerStatus.COMPLETED`, `state.completed_at` est horodaté (ISO 8601), l'état est écrit dans `run_state.json`, et le statut est notifié à `SimulationManager`. | Test unitaire vérifiant l'état terminal `COMPLETED`, la présence de `completed_at` non nul et la persistance sur disque. |
| **AC5** | **Respect de la barrière mémoire et intégrité en cas d'erreur** : La transition vers `COMPLETED` ne contourne jamais `ZepGraphMemoryManager.stop_updater()`. Si une exception survient pendant le drain final du graphe, la simulation bascule en `RunnerStatus.FAILED` avec le message d'erreur approprié. | Test de non-régression validant que `test_zep_simulation_barrier.py` reste intégralement passant. |
| **AC6** | **Filet de tests hermétiques et parité** : Aucun test existant ne régresse (1550+ tests au vert). Une suite de tests hermétiques dédiée (`backend/tests/test_simulation_runner_completion.py`) d'au moins 6 tests valide les scénarios d'arrêt déterministe. | Exécution complète de `pytest` sur l'hôte et confirmation de l'absence d'échecs. |

---

## Définition de fini

- [ ] AC1 à AC6 satisfaits et vérifiés par des tests automatisés passants.
- [ ] `SimulationRunner._start_simulation` transmet l'argument `--no-wait` par défaut à `run_parallel_simulation.py`.
- [ ] `SimulationRunner._monitor_simulation` supervise activement la complétion des plateformes et garantit l'arrêt propre du sous-processus.
- [ ] La simulation passe à `RunnerStatus.COMPLETED` en moins de 5 secondes après la fin des rounds lors d'un cycle nominal.
- [ ] Aucun processus zombie ou sous-processus orphelin ne subsiste après la simulation.
- [ ] Le filet de tests s'accroît à ≥ 1558 tests au vert sur l'hôte, sans régression sur les tests Zep/Docker/Ontologie existants.
- [ ] Revue BMAD contradictoire à 4 couches réalisée, findings traités et consignés dans la section `## Revue`.
- [ ] Documentation et suivi synchronisés : `epic-010.md`, `sprint-status.yaml`, `STATUS.md` et `AGENTS.md`.

---

## Tâches

- [ ] **T1 — Injection de l'argument `--no-wait` au démarrage** :
  - Modifier `SimulationRunner._start_simulation` (`backend/app/services/simulation_runner.py`) pour ajouter `--no-wait` dans `cmd` par défaut.
  - Supporter la clé optionnelle `keep_alive_on_completion` pour préserver le mode persistant si explicitement requis.
- [ ] **T2 — Détection d'achèvement et compte à rebours de complétion** :
  - Dans `_monitor_simulation`, dès que `_check_all_platforms_completed(state)` est vérifié, initialiser un horodatage d'achèvement des plateformes (`platforms_completed_at`).
  - Si le processus ne quitte pas après 5 secondes, déclencher la fermeture ordonnée.
- [ ] **T3 — Émission de secours IPC `close_env` et temporisation de fermeture** :
  - Câbler l'appel à `SimulationIPCService.send_close_env(simulation_id)` lorsque la temporisation de grâce expire.
  - Prévoir un repli par `cls._terminate_process(process, simulation_id)` si le processus est toujours actif après 5 secondes additionnelles.
- [ ] **T4 — Finalisation atomique et transition vers `RunnerStatus.COMPLETED`** :
  - Valider l'ordonnancement dans le bloc `with cls._finalization_lock(simulation_id):` : vidange `ZepGraphMemoryManager.stop_updater()`, assignation de `RunnerStatus.COMPLETED`, renseignement de `completed_at`, sauvegarde `_save_run_state(state)` et notification `_sync_simulation_status`.
- [ ] **T5 — Suite de tests unitaires hermétiques** :
  - Créer `backend/tests/test_simulation_runner_completion.py`.
  - Couvrir les cas : argument `--no-wait` présent par défaut, argument omis si `keep_alive_on_completion=True`, sortie nominale du processus, déclenchement du secours IPC `close_env`, terminaison de sécurité par timeout, et échec du drain mémoire menant à `FAILED`.
- [ ] **T6 — Qualification globale, non-régression et revue BMAD** :
  - Exécuter la suite complète des tests du dépôt (`uv run pytest tests/`).
  - Lancer la revue de code contradictoire BMAD et consigner les remarques.

---

## Notes de développement

### Séquence de complétion actuelle vs attendue

#### Comportement historique (problématique) :
```
run_parallel_simulation.py (rounds finis)
    └──> wait_for_commands = True (car pas de --no-wait)
             └──> Boucle infinie d'écoute IPC (process.poll() is None indéfiniment)

_monitor_simulation()
    └──> while process.poll() is None: time.sleep(2)
             └──> Ne quitte JAMAIS de lui-même !
             └──> runner_status reste bloqué à "running"
```

#### Comportement corrigé (Story 010-1) :
```
SimulationRunner._start_simulation()
    └──> cmd.append("--no-wait")

run_parallel_simulation.py (rounds finis)
    └──> wait_for_commands = False
    └──> Fermeture des environnements Twitter/Reddit
    └──> Sortie propre du processus (sys.exit(0), process.poll() == 0)

_monitor_simulation()
    ├──> Sortie immédiate de la boucle `while process.poll() is None:`
    │    (ou déclenchement IPC send_close_env si délai > 5s)
    └──> finally: with _finalization_lock:
             ├──> ZepGraphMemoryManager.stop_updater() (drain mémoire)
             ├──> state.runner_status = RunnerStatus.COMPLETED
             ├──> state.completed_at = now()
             └──> _sync_simulation_status(COMPLETED)
```

---

## Revue

_Section réservée à la revue contradictoire BMAD (sera complétée lors du passage de la story en phase `review`)._

---

## Notes de complétion

_Story en statut backlog — les notes de complétion seront rédigées lors de la clôture de la story._
