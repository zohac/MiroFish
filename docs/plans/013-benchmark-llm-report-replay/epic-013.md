# Epic 013 : Benchmark LLM du ReportAgent et mode replay non destructif

> **Statut :** En cours (In-Progress)  
> **Date de formalisation :** 19 octobre 2026  
> **Responsable :** Équipe MiroFish & Antigravity  
> **Dépendances :** Epic 005 (Docker local), Epic 007 (Ontologie dynamique), Epic 008 (Localisation FR), Epic 009 (Éligibilité des acteurs), Epic 010 (Cycle de vie des simulations), Epic 011 (Preuve par les faits simulés), Epic 012 (Fiabilité des preuves et publication stricte)  
> **Dossier de plan :** `docs/plans/013-benchmark-llm-report-replay/`  
> **PRD :** [`prd.md`](prd.md) · **Architecture :** [`architecture.md`](architecture.md)

---

## 1. Description & Contexte

Les Epics 011 et 012 ont doté MiroFish d'une barrière de traçabilité factuelle et de certification stricte « Fail-Closed ». Lors du septième essai de simulation réelle (R7, `sim_80a54d7bbd7b` / `report_aaa93b86048c`), la barrière a correctement bloqué la certification automatique (`needs_review`) car 0 affirmation sur 167 n'était vérifiée par rapport aux traces d'actions de l'EvidencePack.

Avant d'ajouter de nouvelles règles ou heuristiques dans le code applicatif, il est impératif d'évaluer scientifiquement l'impact de la **qualité et de l'effort de raisonnement des modèles LLM** utilisés par le `ReportAgent`. Cependant, ré-exécuter des simulations complètes de 72h via OASIS à chaque essai est lent, coûteux et introduit un biais stochastique qui empêche une comparaison A/B rigoureuse.

L'**Epic 013** met en place la capacité de **régénérer des rapports en mode replay à preuves figées (`replay_frozen`)**, sans relancer OASIS ni refaire de graphes, avec une **configuration LLM dédiée par job de rapport** (`ReportLLMProfile`), une **isolation étanche de chaque version sous `reports/<report_id>/`** pour bannir tout écrasement destructif, et un **banc de qualification A/B** pour comparer objectivement `gemini-3.8-flash` en `medium` vs `high` (sur le serveur Antigravity local actuel), puis tester des modèles alternatifs via l'API OpenCode GO.

---

## 2. Exigences Fonctionnelles (FR)

- **FR-01 : Configuration LLM dédiée par job de rapport (`ReportLLMProfile`)** :  
  Permettre d'injecter une configuration LLM spécifique (modèle, effort, température, budget) à une instance de `ReportAgent` sans altérer `os.environ` ni impacter les autres processus.
- **FR-02 : Transmission et prise en compte de `reasoning_effort`** :  
  Permettre le passage explicite de l'effort (`low`, `medium`, `high`) dans les requêtes OpenAI-compatibles, et adapter le serveur Antigravity local ([`antigravity_proxy.py`](../../backend/scripts/antigravity_proxy.py)) pour traduire cet effort en `thinkingConfig` Gemini effectif.
- **FR-03 : Mode replay à preuves figées (`replay_frozen`)** :  
  Régénérer un rapport à partir d'un run existant en neutralisant les appels OASIS interactifs live au profit des archives déjà capturées (`observed_events.jsonl`, `actors.json`, sources, brief).
- **FR-04 : Empreinte de reproductibilité SHA-256** :  
  Calculer et journaliser le hash cryptographique des entrées rejouées afin de prouver que deux rapports comparés ont été soumis à un jeu de données strictement identique.
- **FR-05 : Isolation multi-rapports sans écrasement** :  
  Isoler la totalité des artefacts générés (`report.md`, `report_claims.json`, `cohort_coverage.json`, `quality_checks.json`, `run_manifest.json`, ZIP) sous `reports/<report_id>/`.
- **FR-06 : Endpoints d'API d'historique et de replay** :  
  Fournir l'historique des rapports d'une simulation, le téléchargement d'audit par `report_id`, et l'option de déclenchement d'un rejeu paramétré.
- **FR-07 : Télémétrie d'usage et estimation budgétaire** :  
  Consigner les tokens consommés (dont tokens de réflexion), le temps d'inférence et le coût estimé, avec garde-fous anti-dépassement.
- **FR-08 : Sélecteur et comparateur IHM Vue 3 (Step 4)** :  
  Permettre à l'utilisateur de sélectionner et comparer les différents rapports générés pour une même simulation et de lancer une régénération avec un profil ciblé.
- **FR-09 : Campagne de benchmark A/B et qualification finale** :  
  Automatiser la comparaison contrôlée de `gemini-3.8-flash` `medium` vs `high` sur le cas réel R7 figé et documenter formellement les résultats.

---

## 3. Exigences Non Fonctionnelles (NFR)

- **NFR-1 : Généricité absolue** : 0 terme spécifique à Keova en dur dans les profils ou vérificateurs.
- **NFR-2 : Non-régression totale** : Préservation des 1 842 tests hôte + 9 tests Node frontend au vert.
- **NFR-3 : Sûreté concurrentielle** : Deux générations simultanées ne doivent jamais échanger ni écraser leurs paramètres ou leurs fichiers.
- **NFR-4 : Zéro fuite de secret** : 0 clé API ou token privé présent dans les logs, manifestes ou exports d'audit.

---

## 4. Découpage en Stories

| Story | Titre | Statut | Fichier |
|---|---|---|---|
| 013-1 | Configuration LLM dédiée au ReportAgent et support effectif de l'effort | `in-progress` | [`story-013-1.md`](story-013-1.md) |
| 013-2 | Mode replay isolé et vérifiable (`replay_frozen`) avec empreinte SHA-256 | `backlog` | `story-013-2.md` |
| 013-3 | Isolation multi-rapports sous `reports/<report_id>/` et API d'historique | `backlog` | `story-013-3.md` |
| 013-4 | Télémétrie d'usage, mesure des temps et plafonds budgétaires | `backlog` | `story-013-4.md` |
| 013-5 | Interface Vue 3 Step 4 : sélecteur de rapport, régénération et comparaison | `backlog` | `story-013-5.md` |
| 013-6 | Banc de benchmark contrôlé A/B et qualification globale de l'Epic 013 | `backlog` | `story-013-6.md` |

---

## 5. Critères de Sortie de l'Epic (C1 à C8)

1. **C1 : Configuration LLM découplée par instance** : `ReportLLMProfile` fonctionnel, aucune mutation d'`os.environ` requise pour changer de modèle ou d'effort.
2. **C2 : Prise en compte effective de `reasoning_effort`** : Mesure effective de variation de tokens de réflexion ou de prompt entre `medium` et `high` sur le serveur Antigravity local et OpenCode GO.
3. **C3 : Mode replay déterministe** : Régénération réussie d'un rapport sur simulation existante sans déclenchement d'appels live OASIS.
4. **C4 : 0 écrasement destructif de rapport** : Deux rapports successifs sur le même `simulation_id` possèdent chacun leur dossier complet sous `reports/<report_id>/`.
5. **C5 : Traçabilité des coûts et consommation** : Télémétrie complète (tokens, durée, coût estimé) consignée dans les manifestes.
6. **C6 : Ergonomie de comparaison IHM** : L'écran Step 4 permet de basculer entre les rapports générés et de consulter leurs statuts d'audit respectifs.
7. **C7 : Benchmark A/B documenté** : Rapport formel de qualification consignant la comparaison contrôlée de `gemini-3.8-flash` `medium` vs `high` sur R7.
8. **C8 : Non-régression globale** : $\ge 1 842$ tests au vert sur l'hôte, 0 échec.

---

## 6. Documents à consulter

| Document | Rôle |
|---|---|
| [`prd.md`](prd.md) | Spécifications produit et stratégie d'expérimentation. |
| [`architecture.md`](architecture.md) | Architecture technique et contrats de données. |
| [`../../PRD-MiroFish-benchmark-LLM-ReportAgent-replay-2026-10-19.md`](../../PRD-MiroFish-benchmark-LLM-ReportAgent-replay-2026-10-19.md) | Document source du cadrage de benchmark. |
| [`../../backend/scripts/antigravity_proxy.py`](../../backend/scripts/antigravity_proxy.py) | Passerelle locale vers Google Cloud Code Assist. |
| [`../../backend/app/utils/openai_chat_compat.py`](../../backend/app/utils/openai_chat_compat.py) | Adaptateur OpenAI Chat Completions. |
| [`../../backend/app/services/report_agent.py`](../../backend/app/services/report_agent.py) | Service de génération de rapport. |
| [`../../AGENTS.md`](../../AGENTS.md) | Constitution du dépôt. |
