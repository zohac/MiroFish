# Epic 010 : Fiabilisation du cycle de vie et de la complétion des simulations

> **Statut :** Planifié (Backlog)  
> **Date de formalisation :** 15 octobre 2026  
> **Responsable :** Équipe MiroFish & Antigravity  
> **Dépendances :** Epic 005 (Docker local), Epic 007 (Ontologie dynamique), Epic 009 (Éligibilité des acteurs)  
> **Dossier de plan :** `docs/plans/010-fiabilisation-cycle-simulation/`

---

## 1. Description & Contexte

L'Epic 010 fiabilise de bout en bout l'achèvement des simulations sociales, de la fin du dernier round dans le moteur OASIS jusqu'au déblocage du bouton de génération de rapport dans l'interface web Vue 3.

Cet epic résout définitivement les blocages constatés lors des simulations en environnement de référence (processus qui reste en veille infinie à la fin des rounds, cache mémoire Flask désynchronisé du disque, et erreurs de concurrence PyTorch lors de la mise à jour mémoire du graphe).

---

## 2. Exigences Fonctionnelles (FR)

- **FR-1 : Arrêt automatique et passage à l'état COMPLETED** :  
  Lorsque toutes les plateformes actives ont atteint le dernier round (`all_completed = True`), le processus de simulation s'arrête proprement et `SimulationRunner` bascule immédiatement l'état en `COMPLETED`.
- **FR-2 : Détection de fin de simulation côté IHM** :  
  L'interface web `Step3Simulation.vue` débloque le bouton « Générer le rapport » dès que la progression atteint 100 % ou que les plateformes signalent leur achèvement, sans exiger d'appel manuel à l'API d'arrêt.
- **FR-3 : Réconciliation d'état et fin des processus fantômes** :  
  Le backend détecte si un processus de simulation n'est plus en vie dans le système d'exploitation et aligne l'état en mémoire vive avec le fichier `run_state.json`.
- **FR-4 : Tolérance aux fautes lors du drain mémoire** :  
  La vidange finale de `ZepGraphMemoryUpdater` est protégée contre les erreurs de concurrence d'embeddings PyTorch et ne bloque jamais la transition vers l'état terminal.

---

## 3. Exigences Non Fonctionnelles (NFR)

- **NFR-1 : Zéro régression** : Les 1550 tests unitaires et d'intégration existants doivent rester intégralement au vert.
- **NFR-2 : Temps de bascule IHM** : Le déblocage du bouton de génération de rapport doit intervenir en moins de 2 secondes après la réception du statut 100 %.
- **NFR-3 : Propreté des processus** : Aucun processus Python résiduel ni descripteur de fichier ouvert ne doit subsister après la fin d'une simulation.

---

## 4. Découpage en Stories

| Story | Titre | Statut | Fichier |
|---|---|---|---|
| 010-1 | Arrêt déterministe (`--no-wait`) et statut `COMPLETED` automatique | `done` | [story-010-1.md](story-010-1.md) |
| 010-2 | Réconciliation d'état OS/cache et résilience IHM (`Step3Simulation.vue`) | `backlog` | [story-010-2.md](story-010-2.md) |
| 010-3 | Thread-safety SentenceTransformers et drain mémoire résilient | `backlog` | `story-010-3.md` |

---

## 5. Critères de Sortie de l'Epic

1. **C1 : Transition terminale automatique** : 100 % des simulations qui atteignent leur dernier round passent automatiquement au statut `COMPLETED` en moins de 5 secondes.
2. **C2 : Déblocage immédiat de l'IHM** : Le bouton « Générer le rapport » s'active sans intervention utilisateur dès la fin des rounds.
3. **C3 : Résilience aux pannes** : Aucun état fantôme n'est conservé si un processus de simulation meurt ou est arrêté.
4. **C4 : Thread-safety vérifiée** : Zéro exception `Cannot copy out of meta tensor` observée lors de requêtes concurrentes d'embeddings.
5. **C5 : Filet de tests au vert** : 1550+ tests collectés et réussis avec couverture dédiée pour l'Epic 010.
