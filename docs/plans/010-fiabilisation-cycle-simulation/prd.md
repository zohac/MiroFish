# PRD — Epic 010 : Fiabilisation du cycle de vie et de la complétion des simulations

> **Statut :** Planifié (Backlog)  
> **Date de rédaction :** 15 octobre 2026  
> **Auteur :** Antigravity & Équipe MiroFish  
> **Périmètre :** Backend (`simulation_runner.py`, `simulation_ipc.py`, `zep_graph_memory_updater.py`, `graphiti_embedder.py`), Frontend (`Step3Simulation.vue`).

---

## 1. Contexte & Problématique

Lors des simulations sociales réelles sur MiroFish (notamment les simulations multi-agents de 40 à 72 rounds comptant de 3 à 24 personas et plusieurs centaines d'actions), deux dysfonctionnements majeurs ont été constatés de manière répétée à la fin de la simulation :

1. **Deadlock de fin de simulation (Processus en veille infinie)** :
   - Lorsque les plateformes (Twitter et Reddit) terminent l'ensemble de leurs rounds (progression à 100 %), le script de simulation `run_parallel_simulation.py` entre en mode d'attente de commandes IPC (`wait_for_commands`).
   - Le script attend indéfiniment des ordres d'interview interactive ou de fermeture (`close_env`).
   - Le backend (`simulation_runner.py`) constate la fin des rounds mais boucle dans un `while process.poll() is None: time.sleep(2)` en attendant que le processus s'arrête de lui-même.
   - Le statut `runner_status` reste bloqué à `"running"`.
   - Côté interface web (`Step3Simulation.vue`), le bouton **« Générer le rapport »** reste désactivé (`disabled`) car il attend strictement `runner_status === 'completed' || runner_status === 'stopped'`.

2. **Désynchronisation du cache mémoire Flask et processus orphelins** :
   - Le backend conserve l'état dans un dictionnaire mémoire `cls._run_states`. Si le processus meurt ou est arrêté en tâche de fond, Flask continue de servir son ancien état mémoire en boucle (`"stopping"` ou `"running"`), sans jamais recharger l'état réel écrit sur le disque dans `run_state.json`.

3. **Crash PyTorch / Thread-safety dans l'ingestion mémoire du graphe** :
   - Lors de la vidange des activités vers Neo4j par `ZepGraphMemoryUpdater`, des appels concurrents à `SentenceTransformerEmbedder` provoquent des erreurs PyTorch (`Cannot copy out of meta tensor; no data!`).
   - Cette exception dans `updater.stop()` fait échouer la finalisation normale et coince la simulation dans l'état intermédiaire `"stopping"`.

---

## 2. Objectifs Produit & Valeur Utilisateur

- **Fluidité totale sans intervention manuelle** : L'utilisateur qui lance une simulation doit voir le bouton « Générer le rapport » s'activer **immédiatement et automatiquement** dès que les rounds sont terminés (progression à 100 %).
- **Robuste supervision des processus** : Aucun processus ne doit rester en veille orpheline et aucun état fantôme ne doit être servi par l'API.
- **Résilience du drain mémoire** : Une erreur sur un batch de logs secondaire ne doit jamais bloquer la clôture de la simulation ni empêcher la génération du rapport final.

---

## 3. Critères de Sortie Chiffrés (Acceptance Criteria)

| Réf. | Intitulé | Critère mesurable |
|---|---|---|
| **C1** | **Arrêt déterministe et statut COMPLETED** | 100 % des simulations qui atteignent le dernier round passent automatiquement au statut `COMPLETED` en moins de 5 secondes après la dernière action, sans appel manuel à `/stop`. |
| **C2** | **Réactivité de l'IHM Vue 3** | Le bouton « Générer le rapport » de `Step3Simulation.vue` s'active dès `progress_percent === 100` ou achèvement des plateformes, indépendamment d'un délai d'attente résiduel du processus. |
| **C3** | **Réconciliation d'état et fin des processus fantômes** | Si un processus de simulation n'est plus actif dans l'OS (`poll() is not None`), `get_run_state()` ne renvoie jamais `running` ni `stopping` et aligne immédiatement la mémoire sur la réalité du système. |
| **C4** | **Thread-safety de l'embedder SentenceTransformers** | 0 exception `Cannot copy out of meta tensor` observée sur 100 batches d'embeddings concurrents ; `updater.stop()` tolère les erreurs partielles sans bloquer la transition terminale. |
| **C5** | **Filet de tests hermétiques** | 100 % des tests existants (1550+) restent passants, enrichis d'une suite de tests unitaires couvrant les fins de simulation et les processus orphelins. |
