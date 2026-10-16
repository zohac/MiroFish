---
id: "011-1"
epic: "011"
titre: "Maintien en vie interactif d'OASIS post-rounds, rétablissement d'interview_agents et clôture différée"
statut: done
auteur: "Antigravity & Équipe MiroFish"
format: "2"
---

# Story 011-1 — Maintien en vie interactif d'OASIS post-rounds, rétablissement d'interview_agents et clôture différée

Lot A, priorité **P0**. En tant qu'analyste et utilisateur de MiroFish, je veux que le sous-processus OASIS reste vivant et en écoute interactive (`wait_for_commands`) après l'achèvement des 100 % de rounds d'une simulation afin que le `ReportAgent` puisse exécuter avec succès l'outil `interview_agents` en direct avec les personas actifs, et que le processus soit proprement clôturé par `send_close_env()` dès la complétion et la sauvegarde du rapport.

Cette story répond directement à l'exigence fonctionnelle **FR-01** de l'Epic 011, contribue au critère de sortie **C1** (maintien d'OASIS vivant, 100 % de succès d'`interview_agents` sans avertissement `env not running`, et extinction propre post-rapport), respecte l'exigence de propreté des processus **NFR-03** (zéro processus zombie ou orphelin) ainsi que la résilience ReACT **NFR-04** (aucun crash lors d'interviews sur simulation archivée).

---

## Définition de prêt

- [x] **Objectif compris et cadré** : découpler la complétion logique des rounds de simulation (passage à `COMPLETED` côté IHM et API après drain mémoire Neo4j) de l'extinction physique du sous-processus OS. Permettre les interviews en direct pendant la génération du rapport, puis déclencher l'extinction ordonnée post-rapport.
- [x] **Documents consultés** :
  - [PRD Epic 011](prd.md) : §1.A.1 (régression d'arrêt prématuré et échec d'interview), §3 (FR-01), §4 (NFR-03, NFR-04), §5 (C1).
  - [Architecture Epic 011](architecture.md) : §1 (diagramme de séquence du cycle de vie vivant), §2.1 (découplage complétion / extinction).
  - [Hub Epic 011](epic-011.md) : description globale, FR-01, NFR-03, découpage et critères C1.
  - [Proposition amont Keova](rapport-chatgpt.md) : §1, §2 (référentiel technique et constat d'échec sur les 5 simulations).
  - `backend/app/services/simulation_runner.py` : méthode `start_simulation` (l. 538), gestion de `--no-wait` (l. 700), boucle de surveillance `_monitor_simulation` (l. 810-880), méthode `interview_agents_batch` (l. 2000).
  - `backend/app/services/simulation_ipc.py` : `SimulationIPCClient`, `check_env_alive()`, `send_batch_interview()`, `send_close_env()`.
  - `backend/app/services/zep_tools.py` : méthode `interview_agents()` (l. 1477-1620).
  - `backend/app/services/report_agent.py` : exécution de l'outil `interview_agents` dans `_execute_tool()` (l. 1285) et finalisation du rapport.
  - `backend/app/api/report.py` : barrière de statut de simulation (l. 103-117) exigeant `RunnerStatus.COMPLETED` ou `STOPPED`.
  - `AGENTS.md` : §2.1 (Clean Architecture), §2.2 (qualité et herméticité des tests), §2.8 (gestion des plans).
- [x] **Dépendances résolues** :
  - Epic 005 (Docker local), Epic 007 (Ontologie dynamique v2), Epic 008 (Localisation FR), Epic 009 (Éligibilité des acteurs) et Epic 010 (Fiabilisation du cycle de vie) sont intégralement clos avec succès.
  - Filet de tests au démarrage : **1 649 tests réussis sur l'hôte** (+ 9 tests frontend Node), 0 échec.
- [x] **Décisions d'ingénierie arrêtées avant code** :
  1. **Découplage complétion logique vs cycle de vie OS** : dès que toutes les plateformes actives ont atteint le round final (`_check_all_platforms_completed(state) == True`) et que le drain mémoire Neo4j est effectué sous le verrou de finalisation, `run_state.runner_status` bascule à `RunnerStatus.COMPLETED`, `completed_at` est horodaté et `_sync_simulation_status` notifie l'IHM. La simulation est prête pour la génération du rapport.
  2. **Maintien du mode interactif post-rounds** : ne plus injecter `--no-wait` par défaut dans les simulations pilotées par le runner lorsque le mode interactif d'interview est requis. Le sous-processus OASIS (`run_parallel_simulation.py`, `run_twitter_simulation.py`, `run_reddit_simulation.py`) entre dans sa boucle passive d'écoute IPC `wait_for_commands`.
  3. **Non-extinction prématurée dans `_monitor_simulation`** : suspendre la terminaison forcée automatique (5s/10s) tant que la simulation est en attente de son rapport analytique. `check_env_alive(simulation_id)` continue de retourner `True`.
  4. **Clôture ordonnée post-rapport (`send_close_env`)** : dès que `ReportAgent.generate_report()` a achevé la rédaction et la persistance du rapport (ou via hook API dans `POST /api/report/generate`), `SimulationRunner.close_simulation_environment(simulation_id)` transmet la commande IPC `send_close_env()` pour demander la sortie gracieuse du processus.
  5. **Repli gracieux hors-ligne (`OfflineInterviewService` / fallback relecture)** : si un rapport est régénéré ultérieurement sur une simulation déjà éteinte (serveur redémarré, rejeu hors-ligne), `interview_agents` détecte `check_env_alive() == False` et bascule gracieusement sur une interview hors-ligne synthétisée à partir des fiches personas et des traces d'actions existantes (`actions.jsonl`), sans lever d'exception ni consommer le quota ReACT.
  6. **Garantie anti-zombie (NFR-03)** : un délai de garde maximal d'inactivité (par ex. 15 minutes post-rounds sans lancement de rapport), l'appel explicite à `POST /api/simulation/stop` ou l'arrêt du backend via `SimulationRunner.cleanup_all_simulations()` garantissent l'extinction systématique de tout processus orphelin.
- [x] **Stratégie de tests identifiée** :
  - Suite de tests hermétiques dédiée (`backend/tests/test_simulation_interactive_lifecycle.py`) avec mocks de sous-processus, d'IPC et de `ReportAgent`.
  - Vérification de l'enchaînement : fin des rounds $\rightarrow$ statut `COMPLETED` avec sous-processus vivant $\rightarrow$ interview réussie à 100 % $\rightarrow$ clôture ordonnée post-rapport $\rightarrow$ repli hors-ligne en mode archivé.
  - Maintien rigoureux du filet complet de 1 649 tests.

---

### Critères d'acceptation

| Réf. | Situation et comportement attendu | Vérification / preuve |
|---|---|---|
| **AC1** | **Découplage complétion logique / vivacité du processus** : Lorsque les plateformes actives terminent leur dernier round (`_check_all_platforms_completed(state) == True`), le drain mémoire Neo4j est exécuté et `state.runner_status` passe à `RunnerStatus.COMPLETED` (`completed_at` horodaté, progression à 100%). Le sous-processus OASIS n'est pas tué et demeure en écoute IPC (`SimulationRunner.check_env_alive(sim_id) == True`). | Test unitaire hermétique constatant le passage de l'état à `COMPLETED` tout en vérifiant que le mock de sous-processus ne reçoit aucun signal d'extinction prématurée. |
| **AC2** | **Rétablissement du succès de `interview_agents` en direct** : Lorsque `ReportAgent` invoque `interview_agents` sur une simulation passée à `COMPLETED` avec son processus en veille interactive, l'appel IPC `send_batch_interview` est transmis à l'environnement vivant et renvoie 100 % de succès avec les réponses des agents, sans message d'échec `env not running`. | Test unitaire simulant l'appel de `ReportAgent._execute_tool("interview_agents", ...)` et validant la transmission IPC et la structure du résultat. |
| **AC3** | **Clôture différée ordonnée post-rapport (`send_close_env`)** : Dès que la génération du rapport se termine avec succès (sauvegarde du fichier final), `SimulationRunner.close_simulation_environment(simulation_id)` transmet la commande IPC `send_close_env()`. Le sous-processus se termine avec code de sortie 0 et les descripteurs de logs sont fermés. | Test unitaire validant l'émission de `send_close_env()` lors de la complétion du rapport et la fermeture des ressources associées. |
| **AC4** | **Repli gracieux hors-ligne sur simulation éteinte** : Lorsque `interview_agents` est exécuté sur une simulation dont le processus OASIS est déjà arrêté (`check_env_alive() == False`, rejeu historique ou régénération tardive), l'outil ne lève aucune exception non gérée, ne bloque pas la boucle ReACT et retourne un résultat d'interview contextualisé basé sur les profils et les traces `actions.jsonl`. | Test unitaire hermétique sur simulation éteinte vérifiant l'absence d'exception, le retour structuré d'interview et l'étiquetage explicite du mode hors-ligne. |
| **AC5** | **Garantie anti-zombie et nettoyage d'urgence** : Si aucun rapport n'est déclenché avant l'expiration du timeout d'inactivité post-rounds, ou si `stop_simulation` / `cleanup_all_simulations` est appelé, l'environnement OASIS est proprement fermé par IPC puis terminé si nécessaire. Aucun processus zombie ne subsiste. | Test unitaire vérifiant l'extinction automatique par timeout d'inactivité et l'efficacité du nettoyage lors d'un appel à `cleanup_all_simulations()`. |
| **AC6** | **Non-régression et filet hermétique** : Tous les tests existants du dépôt restent au vert (1 649 tests). Une suite dédiée d'au moins 8 tests hermétiques dans `test_simulation_interactive_lifecycle.py` couvre exhaustivement AC1 à AC5. | Exécution complète de `pytest tests/` sans aucun échec ni warning imprévu. |

---

## Définition de fini

- [x] Critères d'acceptation **AC1 à AC6** satisfaits et vérifiés par des tests automatisés passants.
- [x] Le sous-processus OASIS reste en écoute interactive `wait_for_commands` après la fin des rounds lors d'un cycle nominal de simulation.
- [x] `SimulationRunner` bascule à `RunnerStatus.COMPLETED` dès la fin des rounds et le drain mémoire Neo4j, permettant le déblocage immédiat de l'IHM et de l'endpoint de rapport.
- [x] L'outil `interview_agents` dialogue avec succès en direct via IPC avec les agents simulés lors de la génération du rapport (0 avertissement `env not running`).
- [x] La fermeture gracieuse de l'environnement OASIS (`send_close_env()`) est systématiquement déclenchée dès la complétion du rapport.
- [x] Le repli hors-ligne pour les rejeux ou régénérations sur environnement éteint est fonctionnel et ne lève aucune exception non gérée.
- [x] La propreté des processus (NFR-03) est garantie : zéro processus orphelin ou zombie après rapport, après timeout d'inactivité ou après arrêt manuel.
- [x] Suite de tests hermétiques dédiée créée dans `backend/tests/test_simulation_interactive_lifecycle.py`.
- [x] Suite complète de tests au vert sur l'hôte (filet $\ge 1657$ tests : **1 663 tests réussis**) et parité validée sous Docker.
- [x] `uv run python backend/scripts/validate_plans.py` et `uv run ruff check backend/` validés sans anomalie.
- [x] Revue contradictoire BMAD à 4 couches réalisée, findings résolus ou documentés.
- [x] Documents de suivi synchronisés (`docs/plans/011-preuve-simulation-et-fiabilite-rapport/epic-011.md`, `docs/sprint-status.yaml`, `docs/STATUS.md`, `AGENTS.md`).

---

## Tâches

- [x] **T1 — Découplage de la complétion et politique de vivacité dans `SimulationRunner`** :
  - Ajuster la construction de la commande de lancement dans `SimulationRunner._start_simulation` pour ne plus injecter `--no-wait` par défaut lorsqu'un rapport avec interview est attendu.
  - Dans `_monitor_simulation`, séparer le constat d'achèvement des plateformes (`_check_all_platforms_completed`) de l'extinction du sous-processus : déclencher le drain mémoire Neo4j sous `_finalization_lock`, horodater `completed_at`, basculer vers `RunnerStatus.COMPLETED` et notifier `_sync_simulation_status` tout en maintenant le thread de monitoring et le sous-processus en vie.
- [x] **T2 — Gestion de l'état interactif et sécurisation de l'API IPC** :
  - Exposer un indicateur explicite de vivacité interactive (`is_interactive_available` ou maintien de `SimulationRunner.check_env_alive`).
  - Vérifier que `SimulationRunner.interview_agents_batch` s'exécute avec succès lorsque le statut de simulation est `COMPLETED` et que le sous-processus est actif.
- [x] **T3 — Clôture ordonnée post-rapport (`close_simulation_environment`)** :
  - Implémenter la méthode `SimulationRunner.close_simulation_environment(simulation_id)` émettant `send_close_env()` avec timeout gracieux puis terminaison de sécurité si nécessaire.
  - Câbler l'appel à cette méthode en fin de génération dans `ReportAgent.generate_report()` (ou dans le contrôleur API `POST /api/report/generate` après persistance du rapport).
- [x] **T4 — Repli hors-ligne résilient pour `interview_agents`** :
  - Dans `ZepToolsService.interview_agents` (ou composant dédié `OfflineInterviewService`), détecter l'inaccessibilité de l'environnement IPC (`check_env_alive() == False`).
  - Implémenter une génération de réponse de repli basée sur les personas du graphe/state et les actions enregistrées dans `actions.jsonl`, avec mention explicite du mode hors-ligne sans lever d'exception.
- [x] **T5 — Sécurité anti-zombie et nettoyage d'inactivité** :
  - Implémenter un mécanisme de temporisation d'inactivité post-rounds dans `_monitor_simulation` (ex. extinction automatique après 15 minutes sans requête de rapport).
  - Vérifier l'extinction complète lors de l'appel manuel `POST /api/simulation/stop` et lors de `SimulationRunner.cleanup_all_simulations()`.
- [x] **T6 — Suite de tests unitaires et d'intégration hermétiques** :
  - Créer `backend/tests/test_simulation_interactive_lifecycle.py`.
  - Couvrir les cas : passage à `COMPLETED` sans tuer le processus, exécution d'interviews en direct via IPC avec succès, clôture ordonnée post-rapport, repli hors-ligne en mode archivé, extinction sur timeout d'inactivité, et non-régression sur les barrières mémoires existantes.
- [x] **T7 — Validation d'ensemble, exécution des suites et revue BMAD** :
  - Exécuter la suite complète des tests backend (`uv run pytest tests/`).
  - Vérifier la parité sous conteneur Docker de référence.
  - Conduire la revue contradictoire BMAD à 4 couches et consigner les résolutions.

---

## Notes de développement

### Cycle de vie historique (Epic 010) vs Cycle de vie vivant (Epic 011)

#### Cycle historique (Story 010-1) :
```
SimulationRunner._start_simulation()
    └──> cmd.append("--no-wait")

run_parallel_simulation.py (rounds finis)
    └──> wait_for_commands = False
    └──> Sortie immédiate du processus (sys.exit(0))

_monitor_simulation()
    └──> Constate la fin du processus
    └──> finally: drain Neo4j -> RunnerStatus.COMPLETED

ReportAgent.generate_report()
    └──> interview_agents() -> API IPC
             └──> ÉCHEC : "模拟环境未运行或已关闭" (0/16 agents interviewés !)
```

#### Cycle vivant interactif (Story 011-1) :
```
SimulationRunner._start_simulation()
    └──> Mode interactif activé (pas de --no-wait destructeur)

run_parallel_simulation.py (rounds finis)
    └──> Loggue simulation_end pour toutes les plateformes
    └──> Entre dans wait_for_commands (RESTE EN VIE en écoute IPC)

_monitor_simulation()
    ├──> Détecte _check_all_platforms_completed(state) == True
    ├──> Exécute le drain mémoire Neo4j sous _finalization_lock
    ├──> state.runner_status = RunnerStatus.COMPLETED (completed_at = now())
    ├──> _sync_simulation_status(COMPLETED) -> Débloque l'IHM et l'API de rapport
    └──> Maintient le sous-processus actif (en veille avec timeout de garde)

ReportAgent.generate_report()
    ├──> interview_agents() -> SimulationIPCClient.send_batch_interview()
    │        └──> SUCCÈS : 16/16 agents répondent en direct avec leur persona !
    └──> Rapport rédigé et persisté

Clôture différée post-rapport :
    └──> SimulationRunner.close_simulation_environment(simulation_id)
             ├──> SimulationIPCClient.send_close_env()
             ├──> Processus OASIS quitte proprement (code 0)
             └──> Fermeture des fichiers et libération des handles
```

---

## Revue

### Review Findings (Revue contradictoire BMAD à 4 couches)

- **Couche 1 (Spécification / PRD / Contrat AC1-AC6)** :
  - *Constat* : AC1 respecté sur le découplage logique, mais la valeur par défaut de `keep_alive_on_completion` (False) entraîne toujours l'injection de `--no-wait` lors d'un lancement standard via IHM ou API (Finding 2).
  - *Constat* : AC2 respecté, `interview_agents_batch` opérationnel sur simulation en statut `COMPLETED`.
  - *Constat* : AC3 respecté sur le câblage de `close_simulation_environment`, mais si le processus est éteint avec un code non nul (SIGTERM/SIGKILL), `_monitor_simulation` écrase le statut `COMPLETED` en `FAILED` (Finding 1).
  - *Constat* : AC4 respecté, `_synthesize_offline_interviews` fournit une interview étiquetée mode archives/hors-ligne sans lever d'exception. Ponctuation terminale à normaliser (Finding 4).
  - *Constat* : AC5 respecté, watchdog 15 minutes (`SIMULATION_INACTIVITY_TIMEOUT_SECONDS`) et nettoyage étanche dans `cleanup_all_simulations`.
  - *Constat* : AC6 respecté, 9 tests hermétiques dédiés dans `test_simulation_interactive_lifecycle.py`, 1 659 tests au total (0 régression). Tests d'injection par défaut et de code de sortie à enrichir (Finding 5).

- **Couche 2 (Clean Architecture & Invariants SOLID/DRY)** :
  - *Constat* : Dépendances conformes (`api` $\rightarrow$ `services` $\rightarrow$ `utils`).
  - *Constat* : Pas d'import circulaire. `SimulationRunner` fournit `close_simulation_environment` sans dépendre de `report_agent`.

- **Couche 3 (Sécurité des processus & Anti-Zombie NFR-03)** :
  - *Constat* : Nettoyage sous verrou des processus, queues et handles de fichiers (`_stdout_files`, `_stderr_files`).
  - *Constat* : Repli `_terminate_process` garanti en cas d'échec ou d'expiration de timeout de `send_close_env()`.

- **Couche 4 (Qualité des tests & Herméticité)** :
  - *Constat* : Tests 100 % mockés, sans dépendance réseau ni fichiers temporaires résiduels.
  - *Constat* : Fixture autouse `clean_runner_state` nettoyant les registres avant et après chaque exécution.

#### Actions issues de la revue (Findings)

- [x] [Review][Patch] Résilience du statut terminal face à exit_code non nul post-complétion [backend/app/services/simulation_runner.py:974-987]
- [x] [Review][Patch] Activation par défaut du mode interactif post-rounds (keep_alive=True) sans injection de --no-wait [backend/app/services/simulation_runner.py:572, backend/app/api/simulation.py:1975]
- [x] [Review][Patch] Préservation de completed_at dans le bloc finally de _monitor_simulation [backend/app/services/simulation_runner.py:1021]
- [x] [Review][Patch] Normalisation de la ponctuation et locale neutre dans _synthesize_offline_interviews et tests associés [backend/app/services/zep_tools.py:1741, 1796-1800, backend/tests/test_simulation_interactive_lifecycle.py]

#### Annexe des rejets (Rejected)
- Rejet 1 (low) : Popping prématuré de `cls._processes` dans `close_simulation_environment` — le dictionnaire statique est déjà protégé sous `_finalization_lock` et le thread de monitoring possède déjà la référence locale à l'objet `process`.
- Rejet 2 (false) : Risque de ré-exécution destructrice de `close_simulation_environment` dans `report.py` après `ReportAgent` — vérifié : `close_simulation_environment` est idempotent et court-circuite silencieusement quand l'environnement est déjà fermé.

---

## Notes de complétion

- **Date de complétion** : 16 octobre 2026.
- **Statut** : Clos avec succès (`done`).
- **Filet de tests validé** : **1 663 tests réussis** sur l'hôte (1 650 initiaux + 13 nouveaux tests hermétiques), 1 warning bénin déprécié pydantic amont, 0 échec.
- **Artefacts produits / modifiés** :
  - `backend/app/services/simulation_runner.py` : découplage complétion logique vs extinction sous-processus, watchdog inactivité 15 min, méthode unifiée `close_simulation_environment`, résilience du statut COMPLETED et préservation de completed_at.
  - `backend/app/services/report_agent.py` : déclenchement différé de `close_simulation_environment` dans `finally:`.
  - `backend/app/api/report.py` : filet de sécurité supplémentaire pour la clôture différée dans le worker de génération.
  - `backend/app/api/simulation.py` : propagation transparente du mode interactif par défaut.
  - `backend/app/services/simulation_config_generator.py` : activation native de `keep_alive_on_completion: True` dans les configurations générées.
  - `backend/app/services/zep_tools.py` : méthode `_synthesize_offline_interviews` pour le repli gracieux hors-ligne (mode archives), normalisation ponctuation.
  - `backend/tests/test_simulation_interactive_lifecycle.py` : 13 tests unitaires hermétiques validant AC1 à AC5 et les 4 patches BMAD.

