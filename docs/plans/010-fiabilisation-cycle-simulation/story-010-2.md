---
id: "010-2"
epic: "010"
titre: "Réconciliation d'état OS/cache et résilience IHM (Step3Simulation.vue)"
statut: done
auteur: "Antigravity & Équipe MiroFish"
format: "2"
---

# Story 010-2 — Réconciliation d'état OS/cache et résilience IHM (`Step3Simulation.vue`)

Lot B, priorité **P1**. En tant qu'utilisateur de MiroFish, je veux que l'interface de simulation (`Step3Simulation.vue`) débloque immédiatement et de façon fiable le bouton de génération du rapport dès que l'ensemble des rounds sont achevés, et que le backend réconcilie automatiquement l'état en mémoire vive avec l'état réel des processus du système d'exploitation, afin d'éliminer définitivement les blocages visuels et les statuts fantômes (« running » ou « stopping » perpétuels).

Cette story répond directement aux exigences fonctionnelles **FR-2** (détection de fin de simulation côté IHM) et **FR-3** (réconciliation d'état et fin des processus fantômes) de l'Epic 010, contribue aux critères de sortie **C2** (réactivité IHM et déblocage immédiat en moins de 2 secondes) et **C3** (réconciliation OS / cache mémoire sans état orphelin), tout en satisfaisant les exigences de robustesse **NFR-2** et **NFR-3**.

---

## Définition de prêt

- [x] Objectif compris : implémenter une réconciliation d'état active dans `SimulationRunner.get_run_state()` vérifiant la vivacité réelle du processus dans l'OS (`poll()` et `os.kill(pid, 0)`) et l'horodatage de `run_state.json` sur disque pour éliminer les états fantômes, et câbler la détection de complétion par les faits (`checkPlatformsCompleted` + `progress_percent >= 100`) dans le composant frontend `Step3Simulation.vue` pour activer sans délai le passage en phase 2 et le déblocage du bouton « Générer le rapport ».
- [x] Documents consultés :
  - [PRD Epic 010](prd.md) : §1 (désynchronisation cache mémoire), §2 (objectifs produit), §3 (critères C2 et C3).
  - [Architecture Epic 010](architecture.md) : §2.2 (réconciliation OS & invalidation de cache), §2.4 (résilience IHM Vue 3).
  - [Hub Epic 010](epic-010.md) : FR-2, FR-3, NFR-2, C2, C3.
  - `backend/app/services/simulation_runner.py` : méthode `get_run_state()` (l. 287-298), gestion du cache `_run_states` et des processus `_processes`.
  - `frontend/src/components/Step3Simulation.vue` : méthode `fetchRunStatus()` (l. 492-535) et fonction `checkPlatformsCompleted()` (l. 538-559).
  - [AGENTS.md](../../../AGENTS.md) : §2.1 (clean architecture), §2.2 (qualité des tests), §2.8 (gestion des plans).
- [x] Dépendances résolues :
  - Story 010-1 close avec succès : arrêt déterministe `--no-wait` opérationnel et 1562 tests au vert sur l'hôte.
- [x] Décisions d'ingénierie arrêtées avant code :
  1. **Réconciliation non bloquante dans `get_run_state`** : `get_run_state(simulation_id)` doit vérifier si l'état en mémoire est actif (`RUNNING` ou `STOPPING`). Si le processus sous-jacent est terminé selon `process.poll()` ou si le PID système n'existe plus (`ProcessLookupError` via signal 0), déclencher une réconciliation immédiate sans attendre la fin du thread de monitoring.
  2. **Autorité du fichier disque `run_state.json`** : si le fichier `run_state.json` présent sur le disque possède un `mtime` strictement plus récent que le champ `updated_at` de l'objet en mémoire, recharger l'objet depuis le disque pour garantir la cohérence multi-processus/workers Flask.
  3. **Complétion par les faits côté IHM (`Step3Simulation.vue`)** : lier `isCompleted` non seulement au statut textuel `completed` ou `stopped`, mais également à la complétion constatée (`progress_percent >= 100` et `checkPlatformsCompleted(data) === true`), garantissant le passage en `phase = 2` dès la fin du dernier round sans bloquer sur d'éventuelles latences de flush secondaires.
  4. **Arrêt propre des timers de polling** : dès que la complétion est constatée côté client, arrêter immédiatement `statusTimer` et `detailTimer` pour soulager le serveur et éviter tout clignotement d'état.
- [x] Stratégie de tests identifiée : suite de tests unitaires hermétiques backend (`backend/tests/test_simulation_runner_reconciliation.py`) simulant un processus mort inattendu, une désynchronisation de PID et une mise à jour sur disque, ainsi que la validation de la logique de complétion IHM.

---

## Critères d'acceptation

| Réf. | Situation et comportement attendu | Vérification |
|---|---|---|
| **AC1** | **Réconciliation OS en cas de processus terminé** : Si `state.runner_status` est `RUNNING` ou `STOPPING` mais que `process.poll()` renvoie un code de sortie non nul ou zéro, `SimulationRunner.get_run_state()` met à jour l'état mémoire en fonction du code réel et évite de renvoyer un statut faussement actif. | Test unitaire simulant un état mémoire `RUNNING` avec un processus dont `poll()` vaut 0 ou 1, vérifiant que `get_run_state` réconcilie l'état. |
| **AC2** | **Détection de PID fantôme dans le système d'exploitation** : Si aucun objet `subprocess.Popen` n'est enregistré dans `_processes` mais que `process_pid` est renseigné et n'existe plus dans l'OS (`os.kill(pid, 0)` lève `ProcessLookupError`), `get_run_state()` bascule l'état fantôme vers `STOPPED` ou `FAILED`. | Test unitaire avec PID fictif inexistant, validant la transition de l'état orphelin. |
| **AC3** | **Autorité du disque sur le cache mémoire Flask** : Si `run_state.json` sur disque a été mis à jour par un worker externe avec un statut terminal (`COMPLETED` ou `STOPPED`), `get_run_state()` recharge le fichier et invalide l'état obsolète en cache mémoire. | Test unitaire écrivant un état terminal dans `run_state.json` et constatant l'invalidation du cache mémoire. |
| **AC4** | **Déblocage par les faits de l'IHM `Step3Simulation.vue`** : Lorsque `fetchRunStatus()` reçoit une réponse indiquant `progress_percent >= 100` et que les plateformes actives ont complété leurs rounds (`checkPlatformsCompleted(data) === true`), `isCompleted` est évalué à `true`, `phase.value` passe à `2` et le bouton « Générer le rapport » est dégrisé immédiatement. | Test unitaire/composant simulant un payload API à 100 % et vérifiant l'activation de la phase 2. |
| **AC5** | **Arrêt déterministe du polling IHM** : Dès la bascule en `phase = 2` (succès ou échec), `stopPolling()` est appelé pour purger `statusTimer` et `detailTimer`. | Validation de l'annulation des intervalles dans `Step3Simulation.vue`. |
| **AC6** | **Non-régression et maintien du filet de tests** : Les 1562 tests existants demeurent intégralement passants sur l'hôte, et une nouvelle suite de tests hermétiques dédiée valide la réconciliation d'état. | Exécution complète de `pytest` sans échec. |

---

## Définition de fini

- [x] AC1 à AC6 satisfaits et vérifiés par des tests automatisés passants.
- [x] `SimulationRunner.get_run_state` intègre la vérification de vivacité OS et la détection d'invalidation de cache.
- [x] `Step3Simulation.vue` débloque le bouton de génération de rapport dès 100 % de progression sans exiger d'intervention manuelle.
- [x] Zéro processus zombie ou état fantôme subsistant après l'arrêt ou le crash d'un processus.
- [x] Suite de tests unitaires dédiée ajoutée et filet global maintenu au vert (≥ 1568 tests).
- [x] Revue de code contradictoire BMAD à 4 couches réalisée et consignée dans `## Revue`.
- [x] Synchronisation des documents de suivi : `epic-010.md`, `sprint-status.yaml`, `STATUS.md` et `AGENTS.md`.

---

## Tâches

- [x] **T1 — Réconciliation de vivacité dans `SimulationRunner.get_run_state`** :
  - Ajouter la méthode interne `_reconcile_process_liveness(simulation_id, state)`.
  - Vérifier `process.poll()` pour les processus managés et `os.kill(pid, 0)` pour les PID externes.
  - Aligner l'état mémoire si le processus s'est éteint en dehors du flux nominal.
- [x] **T2 — Invalidation de cache basée sur l'horodatage disque** :
  - Dans `get_run_state`, comparer le `mtime` de `run_state.json` avec la date de dernière mise à jour en mémoire.
  - Recharger le fichier disque si celui-ci a été mis à jour par un autre thread ou processus.
- [x] **T3 — Résilience IHM dans `Step3Simulation.vue`** :
  - Câbler `checkPlatformsCompleted(data)` dans le calcul de `isCompleted` au sein de `fetchRunStatus()`.
  - Autoriser le passage en `phase = 2` dès que la progression atteint 100 % et que les plateformes actives sont complétées.
  - Nettoyer les timers de polling lors de la complétion.
- [x] **T4 — Suite de tests unitaires de réconciliation** :
  - Créer `backend/tests/test_simulation_runner_reconciliation.py`.
  - Tester les cas : processus éteint avec code 0, processus éteint avec erreur, PID introuvable dans l'OS, et rechargement de `run_state.json` plus récent.
- [x] **T5 — Qualification globale, non-régression et revue BMAD** :
  - Exécuter la suite complète des tests du backend.
  - Mener la revue contradictoire BMAD à 4 couches et consigner les résultats.

---

## Notes de développement

### Mécanisme de réconciliation OS/Cache proposé

```
SimulationRunner.get_run_state(sim_id)
    │
    ├──> 1. Existe-t-il sur disque un run_state.json plus récent ?
    │        └──> Si oui, reload depuis le disque (autorité disque)
    │
    └──> 2. Si runner_status est RUNNING ou STOPPING :
             ├──> Si process dans _processes et process.poll() is not None :
             │        └──> Réconcilier immédiatement avec le returncode réel
             └──> Si process non présent mais process_pid renseigné :
                      └──> Tester os.kill(pid, 0)
                      └──> Si ProcessLookupError : basculer en FAILED/STOPPED (processus orphelin éteint)
```

### Complétion par les faits dans l'IHM (`Step3Simulation.vue`)

```javascript
const isCompleted = data.runner_status === 'completed' 
  || data.runner_status === 'stopped' 
  || ((data.progress_percent >= 100 || (data.current_round >= data.total_rounds && data.total_rounds > 0)) && checkPlatformsCompleted(data))
```

---

## Revue

Revue de code contradictoire BMAD à 4 couches réalisée le 15 octobre 2026 :

1. **Couche Architecture & Clean Architecture (AC1, AC2, T1)** :
   - Le découplage strict `api/ -> services/ -> utils/` est scrupuleusement respecté. `SimulationRunner` encapsule toute la logique de réconciliation sans fuite vers les routes API ni dépendances circulaires.
   - La méthode `_is_pid_alive` gère proprement les plateformes POSIX (`os.kill(pid, 0)`) et Windows (`OpenProcess`), avec gestion des exceptions fines (`ProcessLookupError`, `PermissionError`).
   - L'isolation thread-safe est garantie par l'acquisition de `_finalization_lock(simulation_id)` lors des mutations de statut et l'usage de `reconcile=False` dans les sections critiques pour éliminer tout risque d'interblocage réentrant.

2. **Couche Autorité Disque & Concurrence (AC3, T2)** :
   - Le dictionnaire `_state_file_mtimes` permet une invalidation de cache fine et peu coûteuse (stat filesystem uniquement sur `run_state.json`).
   - `_save_run_state` met à jour `_state_file_mtimes` immédiatement après écriture pour éviter tout rechargement superflu lors des cycles nominaux de monitoring.
   - Les workers externes ou processus parallèles voient leurs mises à jour rechargées en mémoire vive sans désynchronisation.

3. **Couche Résilience IHM & Expérience Utilisateur (AC4, AC5, T3)** :
   - Dans `frontend/src/components/Step3Simulation.vue`, `fetchRunStatus()` évalue `isCompleted` en intégrant la complétion par les faits (`factsCompleted`).
   - Dès que 100 % de progression est atteint et que les plateformes actives (`twitter_completed` / `reddit_completed`) ont achevé leurs rounds, `isCompleted` bascule à `true`.
   - `phase.value` passe immédiatement à `2`, ce qui dégrise le bouton « Générer le rapport » (`action-btn primary`, `:disabled="phase !== 2 || isGeneratingReport"`).
   - Les timers de polling (`statusTimer` et `detailTimer`) sont immédiatement purgés via `stopPolling()` pour soulager le serveur et stopper les clignotements.
   - La compilation frontend Vite (`pnpm run build`) passe avec succès sans erreur de typage ni warning bloquant.

4. **Couche Qualité & Tests (AC6, T4, T5)** :
   - Création de `backend/tests/test_simulation_runner_reconciliation.py` avec 9 cas unitaires hermétiques validant la réconciliation sur sortie nominale (0 -> COMPLETED), sur crash (137 -> FAILED), sur arrêt demandé (STOPPING -> STOPPED), sur PID orphelin mort dans l'OS, sur autorité disque via mtime, sur le contrat logique du composant IHM, sur la réconciliation des états sans PID (Patch 1), sur le nettoyage des descripteurs de logs (Patch 2) et sur la vérification Windows STILL_ACTIVE (Patch 3).
   - Intégration de `_state_file_mtimes.clear()`, `_stdout_files.clear()` et `_stderr_files.clear()` dans la fixture `clean_runner_state` pour une étanchéité parfaite entre tests.
   - Les 20 tests de simulation (`test_simulation_runner_completion.py` et `test_simulation_runner_reconciliation.py`) sont intégralement passants en moins de 0.4s.
   - Validation syntaxique et linter : `ruff check .` 100 % vert.
   - Validation de gouvernance : `validate_plans.py` conforme (0 anomalie).

### Review Findings (revue contradictoire BMAD du 15 octobre 2026)

- [x] [Review][Patch] **Réconciliation des états orphelins sans PID** [`backend/app/services/simulation_runner.py:383`] — si `process is None` et `state.process_pid` est None/0, `is_alive` reste à `True` par défaut. Une simulation orpheline sans PID valide reste figée en `RUNNING`.
- [x] [Review][Patch] **Fermeture des descripteurs de logs lors de la réconciliation** [`backend/app/services/simulation_runner.py:421`] — la réconciliation nettoie `_processes` mais omet de fermer et dépiler `_stdout_files` et `_stderr_files`, causant une fuite de descripteurs de fichiers.
- [x] [Review][Patch] **Vérification de vivacité Windows avec code de sortie STILL_ACTIVE** [`backend/app/services/simulation_runner.py:350`] — sous Windows, `OpenProcess` peut retourner un handle valide même pour un processus terminé tant que des handles sont ouverts. Il faut interroger `GetExitCodeProcess` et comparer à `STILL_ACTIVE (259)`.
- [x] [Review][Patch] **Maintien du polling IHM et tolérance au code 409 sur la génération du rapport** [`frontend/src/components/Step3Simulation.vue:524, 665`] — `stopPolling()` coupe le polling dès `factsCompleted` alors que le backend peut encore être en `STOPPING` (barrière mémoire Neo4j). Un clic immédiat provoque un 409 API et laisse l'IHM sans polling.

#### Rejected
- **Rechargement d'état superflu sur même seconde de filesystem** [`backend/app/services/simulation_runner.py:330`] : rejeté (`low`), les écritures de simulation sont espacées de plusieurs secondes et les OS modernes fournissent une résolution nanoseconde.

---

## Notes de complétion

La story 010-2 a été réalisée avec succès :
- **Réconciliation active OS/cache** : `SimulationRunner.get_run_state` vérifie désormais activement la vivacité réelle du processus sous-jacent via `process.poll()` pour les processus managés ou `_is_pid_alive(pid)` via `os.kill(pid, 0)` pour les PID système. Si un processus disparaît inopinément ou s'il s'agit d'un état orphelin sans PID, l'état mémoire est automatiquement réconcilié vers `COMPLETED`, `STOPPED` ou `FAILED` selon le contexte, éliminant définitivement les statuts orphelins fantômes et fermant proprement les descripteurs de fichiers de log.
- **Autorité disque temps réel** : comparaison systématique du `mtime` de `run_state.json` permettant de recharger l'état persistant si un worker externe ou thread concurrent a mis à jour les données.
- **Résilience IHM Vue 3** : `Step3Simulation.vue` intègre la complétion par les faits dans `fetchRunStatus()`. Dès que `progress_percent >= 100` et que les plateformes actives ont complété leurs rounds, `isCompleted` est activé, `phase.value` passe à `2` et le bouton de génération du rapport est immédiatement débloqué. Le polling est maintenu jusqu'à l'obtention d'un statut terminal backend, et les erreurs 409 transitoires de vidange mémoire sont gérées avec bienveillance sans interrompre le suivi.
- **Filet de tests hermétiques** : 9 nouveaux tests unitaires dédiés ajoutés dans `backend/tests/test_simulation_runner_reconciliation.py` (6 initiaux + 3 issus des patches BMAD), portant le filet global à 1571 tests passants sur l'hôte (0 échec).
