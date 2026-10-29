# Epic 015 : Contrats de preuve de bout en bout, pertinence des rôles et ergonomie IHM de suivi

> **Statut** : `in-progress` (3/6 stories validées : `015-1` `done`, `015-2` `done`, `015-3` `done`, 1 en cours : `015-4` `in-progress`, 2 en `backlog`).
> **Dossier de plan** : `docs/plans/015-contrats-preuve-roles-et-ihm/`
> **PRD** : [`prd.md`](prd.md) · **Architecture** : [`architecture.md`](architecture.md)
> **Épic amont** : 014 (clos, 4/4 stories validées — 2 099 tests hôte + 43 tests Node frontend).

---

## 1. Description & Contexte

L'audit du run R8 (`sim_7a1b02b8c092`, rapport `report_934d3254004b`) et l'inspection du code et de l'IHM aux étapes 3/5 et 4/5 ont mis en évidence que les briques introduites par les Epics 011 à 014 sont bien en place, mais souffrent de **ruptures de contrat aux coutures** et de **deux défauts visuels/télémétriques côté frontend** :

1. **Perte du régime de provenance et faux positifs d'intention** : `SimulationActionVerifier.verify_report_claim` ré-instancie `ReportClaim` dans 11 `return` en oubliant `provenance_regime` (`165/165 null`), `extract_claims_from_content` teste `"va"` et `"compte"` en sous-chaînes brutes avant les actions (`0 OBSERVED_SOCIAL_ACTION`), et le déclassement efface la trace qu'une action avait été affirmée.
2. **Aplatissement des entretiens de rédaction** : `report_interviews.json` concatène les citations sans conserver la liaison `interview_id ↔ répondant ↔ réponse complète`, empêchant l'authentification par auteur des citations d'entretien.
3. **Angle mort « rapport conceptuel » et section limites rigide** : faute d'`action_claims` survivantes, `ReportQualityGate` émet un simple `WARNING` (« rapport conceptuel ») sur un texte qui raconte des actions non prouvées ; la section d'objections/limites échoue si son titre s'écarte de 4 chaînes codées en dur ; et `Sources & Provenance` conserve un littéral statique résiduel en sous-section 3.
4. **Confusion acteurs / objets et caviardage excessif `[persona non admis]`** : les outils logiciels tiers et l'entité objet de l'étude sont instanciés comme agents actifs ; inversement, le filtre de `api/report.py` remplace par `[persona non admis]` toutes les entités `ineligible` (y compris produits, offres et domaines !) dans le brief de planification ; enfin, le dénominateur d'adoption inclut les `ScenarioRole.UNKNOWN`.
5. **Ergonomie IHM Step 3 & Step 4** : sur l'étape 3/5 en vue `Scindé`, les 3 cartes (`Info Plaza`, `Topic Community`, `Mémoire du Graphe`) débordent et collent au bouton ; sur l'étape 4/5, toute la bande de télémétrie affiche `indisponible` pendant la génération (et risque un `404` de course en fin de run).
6. **Cohérence biographique aval et reproductibilité Docker** : une ancienneté inventée dans la prose finale contredit la fiche de départ d'un persona sans être détectée, et `run_manifest.json` affiche `git_commit: unknown-git-commit` et `time_horizon: null`.

---

## 2. Exigences Fonctionnelles (FR)

| ID | Exigence | Priorité |
|---|---|---|
| FR-01 | Préservation intégrale de `provenance_regime` dans `verify_report_claim` et distinction actions vs intentions par frontières lexicales `\b` sans faux positifs par sous-chaîne | P0 |
| FR-02 | Conservation explicite de `asserted_as_action = True` lors du déclassement d'une action non prouvée et contrôle d'appartenance de l'`event_id` au bon acteur résolu | P0 |
| FR-03 | Journal `report_interviews.json` v2 structuré par entretien, tour et répondant avec réponse complète, permettant l'authentification des citations d'entretien sans promotion en événement OASIS | P0 |
| FR-04 | Fermeture de l'angle mort « rapport conceptuel » dans `ReportQualityGate`, contrat structurel `section_role="limitations"` dès le plan, et suppression du dernier littéral statique dans `Sources & Provenance` | P0 |
| FR-05 | Séparation éligibilité ontologique vs participation scénaristique (`ScenarioParticipationPolicy`), filtrage `[persona non admis]` restreint aux seuls personas humains écartés, et dénominateur de conversion par inclusion positive | P0 |
| FR-06 | Correction du layout responsive des 3 cartes et du bouton sur `Step3Simulation.vue`, persistance incrémentale de `usage.json` et rafraîchissement live/terminal sans course sur `Step4Report.vue` | P1 |
| FR-07 | Audit déterministe des faits biographiques chiffrés entre fiches personas et prose finale, injection de `GIT_COMMIT` sous Docker et persistance de `time_horizon` effectif dans `run_manifest.json` | P1 |
| FR-08 | Banc de qualification en `replay_frozen` sur fixture R8 + 3 scénarios synthétiques multi-domaines sans aucune adhérence métier | P1 |

---

## 3. Exigences Non Fonctionnelles (NFR)

| ID | Exigence |
|---|---|
| NFR-1 | **Zéro régression** : ≥ 2 099 tests backend hôte + ≥ 43 tests Node frontend au vert, lecture rétrocompatible des anciens artefacts |
| NFR-2 | **Généricité absolue** : zéro constante, nom d'entreprise, offre, tarif ou persona d'une fixture dans le code applicatif ou les prompts globaux |
| NFR-3 | **KISS & DRY** : enrichissement chirurgical des modèles existants, zéro couche de ledgers/renderers redondante |
| NFR-4 | **Zéro fuite de secret** : étanchéité stricte des exports `usage.json`, `report_interviews.json` et `run_manifest.json` |
| NFR-5 | **Honnêteté** : distinction nette entre « en cours… », « non tarifé / gratuit » et « indisponible » ; zéro certification littérale non prouvée |
| NFR-6 | **Parité i18n & ergonomie** : parité 100 % `fr`/`en`/`zh` et affichage sans collision en modes `Graphe`, `Scindé` et `Établi` |

---

## 4. Découpage en Stories

Conformément à `AGENTS.md §2.8`, chaque fichier `story-015-X.md` est créé au démarrage effectif de la story.

| Story | Titre | Statut | Contenu résumé & Critère central |
|---|---|---|---|
| 015-1 | [Préservation du `provenance_regime`, typage d'actions sans faux positifs et traçabilité du déclassement](story-015-1.md) | `done` | Corriger les 11 `return` de `verify_report_claim` (`dataclasses.replace`), remplacer les sous-chaînes `"va"`/`"compte"` par des motifs `\b`, ajouter `asserted_as_action: bool` sur `ReportClaim`, contrôler l'acteur propriétaire d'`event_id` sans repli silencieux et filtrer les événements OASIS passifs. **Critère central** : 0 perte de régime, 0 faux positif `"va"`/`"compte"`, toute action affirmée non prouvée reste comptée comme action affirmée. |
| 015-2 | [Journal d'entretiens structuré par répondant et authentification des citations d'entretien](story-015-2.md) | `done` | Enrichir `report_interviews.json` en v2 (`interview_id`, `turn_id`, `turn_index`, `agent_id`, `persona_name`, `question`, `answer_text`, `key_quotes` avec offsets exacts), tracer fidèlement le mode effectif (`live`, `offline_archive`, `replay_frozen`) et vérifier dans `SimulationActionVerifier` les citations d'entretien par répondant sans promotion en action OASIS. **Critère central** : toute citation d'entretien est vérifiable par auteur et offset, et 0 entretien ne devient `OBSERVED_SOCIAL_ACTION`. |
| 015-3 | [Barrière `ReportQualityGate` sans angle mort « conceptuel », section `limitations` contractuelle et provenance 100 % calculée](story-015-3.md) | `done` | Faire échouer `ReportQualityGate` dès que `asserted_as_action > 0` et `verified_action_claims == 0` ; lier la section d'objections/limites à `section_role="limitations"` dans `ReportOutline` ; supprimer le littéral statique résiduel de `build_sources_provenance_section` (`:3321`). **Critère central** : R8 ne passe plus en `WARNING` « rapport conceptuel » et `Sources & Provenance` est 100 % alignée sur le registre. |
| 015-4 | [Pertinence scénaristique des acteurs, filtre chirurgical `[persona non admis]` et dénominateur par inclusion positive](story-015-4.md) | `in-progress` | Introduire la politique de participation au scénario (`active_agent` vs `context_only` pour logiciels/objets cités), restreindre le masquage `[persona non admis]` de `api/report.py` aux seuls candidats personas humains rejetés (jamais aux produits/offres/domaines), et passer `prospect_members` en inclusion positive (`PROSPECT` / `conversion_eligible`). **Critère central** : 0 produit/domaine caviardé en `[persona non admis]`, dénominateur exact sur les seuls prospects déclarés. |
| 015-5 | Ergonomie IHM Step 3 (cartes de statut sans débordement) et télémétrie vivante Step 4 | `backlog` | Assainir le CSS `.control-bar` / `.platform-status` / `.action-controls` de `Step3Simulation.vue` (0 débordement ni collision en mode `Scindé`) ; persister `usage.json` de façon incrémentale dans `ReportAgent`, sauver `report` avant `log_report_complete`, rafraîchir la télémétrie au fil du polling et sur `error` dans `Step4Report.vue` avec état « en cours… » honnête. **Critère central** : 0 chevauchement visuel Step 3 et affichage temps réel puis terminal fiable des tokens/durées Step 4. |
| 015-6 | Cohérence biographique fiches ↔ prose finale, métadonnées Docker (`git_commit`, horizon) et qualification multi-domaines | `backlog` | Détecter les contradictions biographiques chiffrées entre fiches personas et prose finale (`PERSONA_BIOGRAPHY_CONTRADICTION`), propager `GIT_COMMIT` au conteneur et `time_horizon` effectif dans `run_manifest.json`, puis qualifier en `replay_frozen` sur R8 et 3 scénarios synthétiques multi-domaines. **Critère central** : détection déterministe d'une ancienneté contradictoire sans bloquer les opinions, manifeste complet et qualification multi-domaines verte. |

### 4.1 Graphe de dépendances

```text
015-1 ──▶ 015-2 ──▶ 015-3 ──┐
015-4 ──────────────────────┼──▶ 015-6 (qualification de bout en bout R8 + multi-domaines)
015-5 (indépendant IHM/télémétrie) ─┘
```

### 4.2 Matrice de couverture (Stories ↔ Exigences ↔ Critères de sortie)

| Story | Dépendances | Exigences FR / NFR | Critères de sortie |
|---|---|---|---|
| `015-1` | Epics 011, 012, 014 (`done`) | FR-01, FR-02 · NFR-1, NFR-2, NFR-3, NFR-5 | C1 (socle C3, C7, C8) |
| `015-2` | `015-1` | FR-03 · NFR-1, NFR-2, NFR-3, NFR-4, NFR-5 | C2 (socle C7, C8) |
| `015-3` | `015-1`, `015-2` | FR-04 · NFR-1, NFR-2, NFR-3, NFR-5 | C3 (socle C7, C8) |
| `015-4` | Epics 009, 012, 014 (`done`) | FR-05 · NFR-1, NFR-2, NFR-3 | C4 (socle C7, C8) |
| `015-5` | Epics 008, 010, 013 (`done`) | FR-06 · NFR-1, NFR-4, NFR-5, NFR-6 | C5, C8 |
| `015-6` | `015-1` à `015-5` | FR-07, FR-08 · NFR-1 à NFR-6 | C6, C7, C8 |

---

## 5. Critères de Sortie de l'Epic (C1 à C8)

1. **C1** : Zéro écrasement de `provenance_regime` dans `verify_report_claim`, zéro faux positif d'intention par sous-chaîne (`"va"`, `"compte"`), conservation de `asserted_as_action` sur tout déclassement.
2. **C2** : `report_interviews.json` v2 trace chaque réponse complète par répondant et authentifie les citations d'entretien sans jamais les compter en événements OASIS.
3. **C3** : `ReportQualityGate` bloque en `FAILED` les rapports contenant des actions affirmées mais 0 vérifiée, reconnaît la section `limitations` par contrat structurel (`section_role`), et `Sources & Provenance` ne contient plus aucun littéral statique de garantie.
4. **C4** : Zéro entité non-persona (produit, offre, domaine, outil) masquée en `[persona non admis]` dans le prompt du rapport ; participation scénaristique distincte de l'éligibilité ontologique ; dénominateur d'adoption en inclusion positive.
5. **C5** : En étape 3/5 (y compris vue `Scindé`), les 3 cartes de statut ne débordent pas et restent séparées du bouton ; en étape 4/5, tokens et durées remontent en cours de génération et s'affichent sans course `404` à la fin.
6. **C6** : Détection des contradictions biographiques chiffrées `fiches ↔ prose finale` ; `git_commit` et `time_horizon` effectif renseignés dans `run_manifest.json`.
7. **C7** : Banc de qualification validé en `replay_frozen` sur R8 et sur 3 scénarios synthétiques multi-domaines (logiciel, débat associatif sans vente, crise de transport avec institution active).
8. **C8** : Filet de tests complet au vert (`pytest`, `node --test`, `ruff check`, `validate_plans.py`, parité i18n `fr`/`en`/`zh`).

---

## 6. Documents à consulter

| Document | Rôle |
|---|---|
| [`prd.md`](prd.md) | Constats vérifiés sur le code et R8, FR/NFR et critères de sortie |
| [`architecture.md`](architecture.md) | Modèles enrichis, flux, correctifs CSS/télémétrie et arbitrages KISS/DRY |
| [`docs/PRD-MiroFish-correctifs-generiques-audit-R8-2026-10-29.md`](../../PRD-MiroFish-correctifs-generiques-audit-R8-2026-10-29.md) | Rapport d'audit externe initial sur R8 |
| `backend/app/services/report_agent.py` | Extraction des claims, entretiens, provenance et télémétrie incrémentale |
| `backend/app/services/simulation_action_verifier.py` | Vérification des claims et préservation du régime |
| `backend/app/services/report_quality_gate.py` | Barrière de publication et contrôle contractuel des sections |
| `backend/app/api/report.py` | Filtrage du contexte de rédaction et endpoints `/usage`, `/claims` |
| `backend/app/models/cohort_coverage.py` | Rôles de scénario et dénominateur par inclusion positive |
| `frontend/src/components/Step3Simulation.vue` | Barre de statut et cartes de suivi de l'étape 3/5 |
| `frontend/src/components/Step4Report.vue` | Bandeau de télémétrie et suivi de génération de l'étape 4/5 |

