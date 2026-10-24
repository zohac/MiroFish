---
id: "014-4"
epic: "014"
titre: "Le brief et les fiches persona ne font plus diverger deux biographies"
statut: in-progress
auteur: "Antigravity & Équipe MiroFish"
format: "2"
---

# Story 014-4 — Le brief et les fiches persona ne font plus diverger deux biographies

**Lot D (hygiène du brief et des fiches), priorité P0.** En tant que relecteur d'un
rapport produit par MiroFish — analyste, commanditaire ou tiers recevant l'archive
d'audit —, je veux qu'un épisode biographique attribué à un persona dans le brief ne
puisse pas réapparaître dans la fiche d'un autre persona, et que les fiches des personas
non admis ne soient pas injectées dans le contexte de rédaction, afin qu'un rapport ne
raconte plus deux biographies contradictoires.

Cette story répond aux exigences **FR-07** (le brief et les fiches persona ne peuvent pas
faire diverger deux biographies de départ ; les fiches non admises ne sont pas dans le
contexte de rédaction) et sert les critères de sortie **C5** (aucune divergence de
biographies, fiches non admises hors du contexte) et **C8** (re-qualification sans
certification mensongère) du [PRD](prd.md) et de l'[epic](epic-014.md). Elle **dépend**
des stories 014-1, 014-2 et 014-3, qui ont typé le registre, rendu la section honnête et
fait remonter la règle de silence ; elle **alimente** la re-qualification finale sur R7
(C8).

**Frontière, en une phrase.** Cette story agit **en amont** — sur la construction du brief
et des fiches persona — et sur le **contexte de rédaction** qui en dérive ; elle ne
corrige ni le régime des entretiens (014-1), ni la section « Sources & Provenance »
(014-2), ni la règle de silence (014-3), ni la prose du rapport au-delà du retrait des
fiches non admises.

---

## Définition de prêt

- [x] **Objectif compris et cadré** :

  **Le problème, mesuré.** Le brief de R7 (`proj_cc8bc57b87fe`, `simulation_requirement`
  de 6 384 caractères) attribue explicitement l'épisode « 1 500 € en agence WordPress » au
  persona **Émilie**. Or Émilie est `eligibility_status: review` (`actors.json` : 41
  entités, 17 `eligible`, **1 `review`**, 23 `ineligible` ; 0 action, `present_no_action`) :
  elle n'est ni dans `simulation_config.json` (17 agents), ni dans `reddit_profiles.json`
  (17 profils), ni dans les 737 événements. Pourtant, les deux rapports de la campagne de
  l'Epic 013 attribuent cet épisode à **Nathalie** : la confusion précède donc le rapport,
  elle est dans les fiches persona et le brief. Le bloc de brief est injecté tel quel dans
  **chaque** prompt de génération de persona
  (`backend/app/services/oasis_profile_generator.py:_build_brief_block`, appelé par
  `_build_individual_persona_prompt` et `_build_group_persona_prompt`), si bien que
  l'épisode d'Émilie peut être recopié dans la fiche de n'importe quel autre persona.

  Par ailleurs, `backend/app/api/report.py:196` lit `project.simulation_requirement` et le
  transmet tel quel au `ReportAgent` (`:306-309`, `:724-730`) ; la story 014-3 a filtré la
  table de cohorte, mais le **texte du brief** nomme toujours les personas non admis, qui
  entrent donc dans le prompt de rédaction.

  **Ce que la story garantit, par sous-ensemble.**

  - **Détection à la construction.** Un service pur et déterministe compare le brief et les
    fiches persona générées. Il signale une **contradiction** quand un même épisode
    (montant + mot-clé) est attribué à deux personas distincts, ou quand l'épisode attribué
    par le brief à un persona apparaît dans la fiche d'un autre.
  - **Échec à la construction, pas à la rédaction.** `SimulationManager.prepare_simulation`
    lève `BriefPersonaContradictionError` et bascule `SimulationState.status` en
    `SimulationStatus.FAILED` avant de persister profils et configuration. La
    contradiction ne peut pas atteindre le rapport.
  - **Contexte de rédaction filtré.** Le `simulation_requirement` transmis au `ReportAgent`
    est filtré des personas non admis (`review`, `ineligible`) avant d'entrer dans le
    prompt.
  - **Traçabilité.** Le résultat de l'audit est persisté en `brief_consistency.json` dans
    le dossier de simulation et joint à l'archive d'audit, avec les contradictions
    nommées.

  **Les invariants — ce que l'implémentation ne peut pas faire.**

  - **Jamais de LLM dans la détection.** Un épisode décidé par le modèle reproduirait le
    défaut qu'on corrige. L'extraction est lexicale, déterministe et testée.
  - **Jamais d'échec à la rédaction.** La contradiction se détecte et se refuse **avant**
    la rédaction ; le `ReportAgent` n'est pas modifié pour rattraper en aval.
  - **Jamais de nouvelle valeur dans `InformationOrigin`, `ClaimKind` ou `ProvenanceRegime`.**
    La story lit des textes ; elle n'étend aucun contrat gelé.
  - **Jamais de champ ajouté à `SimulationBrief`.** L'audit est une fonction pure sur le
    texte et les fiches, pas une extension du modèle.
  - **Jamais de dépendance ajoutée.** `re`, `json` et `unicodedata` sont déjà utilisés.
  - **Jamais de filtrage des acteurs admissibles.** Seuls les statuts `review` et
    `ineligible` sont retirés du contexte de rédaction ; un `eligible` n'est jamais retiré.

- [x] **Documents consultés** :

  - [PRD de l'epic](prd.md) : §2.3 (la fiction d'un persona non admis, mesurée sur R7),
    §2.4 (le brief confond les biographies), §4 (FR-07), §5 (NFR-1, NFR-2, NFR-3, NFR-5),
    §6 (C5, C8).
  - [Architecture de l'epic](architecture.md) : §5 (le brief et les fiches persona — agir
    en amont, faire échouer la construction), §8 (contraintes de non-régression).
  - [Hub de l'epic](epic-014.md) : §2 (FR-07), §4 (story 014-4), §5 (C5, C8), §6 (preuves
    de l'état de départ).
  - `AGENTS.md` : §2.1 (les dépendances pointent vers l'intérieur), §2.2 (tout code
    produit est testé ; hermétique), §10 (la fiction de scénario d'un persona non admis
    fuit dans la prose).
  - `backend/app/models/simulation_brief.py` : `SimulationBrief`, `build_minimal_brief`,
    `advanced_text`, `is_minimal`, `audit_brief`.
  - `backend/app/services/oasis_profile_generator.py` : `generate_profiles_from_entities`
    (`:1055`), `_build_brief_block` (`:830`), `_build_individual_persona_prompt` (`:853`),
    `_build_group_persona_prompt` (`:903`), `OasisAgentProfile` (`:96`).
  - `backend/app/services/simulation_manager.py` : `prepare_simulation` (`:524`),
    génération des profils (`:812-827`), persistance `reddit_profiles.json` /
    `twitter_profiles.csv` (`:836-852`), `get_actor_selection`.
  - `backend/app/api/graph.py` : construction du brief (`:506-516`).
  - `backend/app/api/report.py` : lecture de `project.simulation_requirement` (`:196`),
    instanciation de `ReportAgent` (`:306-309`, `:724-730`).
  - `backend/app/services/report_agent.py` : injections de `simulation_requirement`
    (`:642`, `:688`, `:1063`, `:2107`).
  - `backend/app/models/actor_eligibility.py` : `EligibilityStatus` (`:45`).
  - `backend/app/models/actor_selection.py` : `ActorItem`, `ActorSelection`.
  - `backend/app/models/cohort_coverage.py` : `CohortCoverageTable`, `is_silent`.
  - `backend/app/services/simulation_audit_service.py` : `build_audit_package`.
  - `backend/tests/test_epistemic_sources_and_brief.py` : fixtures de brief.
  - `backend/tests/test_personas_simulation_graphiti.py` : génération de personas.
  - `backend/tests/test_cohort_coverage_time.py` : table de cohorte.
  - `docs/deferred-work.md` : « La fiction de scénario d'un persona non admis fuit dans
    les affirmations "observées" ».

- [x] **Dépendances résolues** :

  - **Stories amont** : 014-1 (`done`) fournit le régime de provenance et la distinction
    entretien/fait ; 014-2 (`done`) fournit la section honnête et `ProjectManager`
    résilient ; 014-3 (`done`) fournit le filtre `review`/`ineligible` dans la cohorte et
    la règle de silence jusqu'à la barrière. Les Epics 011 et 012 sont clos (barrière
    Fail-Closed, prévalence épistémique). Aucun contrat n'est rouvert.
  - **Stories avalentes** : la re-qualification finale sur R7 (C8) consomme l'audit de
    cohérence et le contexte filtré.
  - **Filet de tests mesuré à la rédaction** : **2 083 tests backend** au vert sur l'hôte
    (`uv run pytest tests/ --collect-only -q`) et **43 tests Node** frontend
    (`pnpm --dir frontend test`), mesuré le 24 octobre 2026.
  - **Dépendances techniques** : aucune nouvelle dépendance. `re`, `json` et
    `unicodedata` sont déjà présents.

- [x] **Décisions d'ingénierie arrêtées avant code** :

  1. **La détection vit dans un service pur, sans LLM.** Nouveau module
     `backend/app/services/brief_consistency.py` : `extract_episodes(text)`,
     `audit_brief_persona_consistency(brief_text, profiles)` et
     `BriefPersonaContradictionError`. *Raison* : le modèle a déjà inventé l'étiquette
     `[Événements simulés réels]` (014-1) ; une détection par LLM reproduirait le défaut.
  2. **Un « épisode » est un couple (montant, mot-clé) normalisé.** Le montant est extrait
     par `\d[\d\s.,]*\s?(?:€|euros?|EUR)` ; le mot-clé est le mot capitalisé (≥ 3
     caractères, hors mots vides) le plus proche dans la même phrase. La signature est
     normalisée (chiffres seuls + `eur`, NFKD, minuscules). *Raison* : « 1 500 € en agence
     WordPress » doit produire une signature stable, testable et indépendante de la
     langue de rédaction.
  3. **L'échec est porté par `prepare_simulation`, pas par le `ReportAgent`.** L'audit
     s'exécute après `generate_profiles_from_entities` et avant la persistance des
     profils ; une contradiction lève `BriefPersonaContradictionError` et laisse
     `SimulationState.status = ERROR`. *Raison* : l'architecture §5 exige un échec à la
     construction, et filtrer à la rédaction laisserait le brief contradictoire dans les
     artefacts.
  4. **Le contexte de rédaction est filtré, pas le brief stocké.** La fonction
     `filter_non_admitted_personas_from_text(text, admitted_names, excluded_names)` est
     appliquée au `simulation_requirement` au moment de construire le `ReportAgent`
     (`api/report.py`). *Raison* : le brief d'origine reste auditable, et seule la copie
     destinée au prompt est nettoyée. Aucun persona `eligible` n'est retiré.
  5. **Le filtre retire les phrases attribuant une action à un persona non admis, ou
     remplace son nom par un jeton explicite.** Le choix par défaut est le **retrait de la
     phrase** quand elle nomme un non-admis ; à défaut, le nom est remplacé par
     `[persona non admis]`. *Raison* : ne pas laisser une identité non admise devenir un
     acteur par simple lecture du prompt.
  6. **L'audit est persisté en `brief_consistency.json` et joint à l'archive.** Le fichier
     porte `is_consistent`, `contradictions` (signature, owner, personas) et les
     diagnostics. *Raison* : C7/NFR-6 — un tiers doit pouvoir établir pourquoi un brief a
     été refusé ou accepté.
  7. **Aucun champ ajouté à `SimulationBrief`.** L'audit lit `goal`, `initial_state`,
     `rules`, `hypotheses` et `additional_context` via `advanced_text()`, sans étendre le
     modèle. *Raison* : ne pas rouvrir un contrat de l'Epic 009.
  8. **Déterminisme strict.** À brief et fiches identiques, la liste des contradictions
     est identique (ordre trié par signature puis nom). *Raison* : NFR-3.
  9. **Un persona non admis n'apparaît jamais dans le contexte filtré, même s'il est cité
     dans plusieurs phrases.** Le filtre traite tout le texte, pas seulement la première
     occurrence. *Raison* : une seule phrase résiduelle suffit à réintroduire l'acteur.

- [x] **Stratégie de tests identifiée** :

  - **Hermétique d'abord.** Aucun réseau, aucun modèle, aucun `.env`. Les briefs et fiches
    sont des dictionnaires en mémoire ou des fixtures sous
    `backend/tests/fixtures/brief_consistency/`.
  - **Nouveau fichier** : `backend/tests/test_brief_persona_consistency.py`, avec les cas
    nommés pour chaque AC.
  - **Fixtures** : `brief_contradictory.json` (épisode d'Émilie repris par Nathalie) et
    `brief_consistent.json` (épisode attribué au bon persona), plus les fiches persona
    correspondantes. Aucun nom de simulation ou de persona réel n'est codé en dur dans le
    service (NFR-2) : les fixtures portent les noms.
  - **Ce qui est vérifié à l'œil** sur la pile Docker de référence : une préparation de
    simulation sur R7 dont le brief contradictoire est refusé, puis une préparation sur un
    brief cohérent qui passe.
  - **Tests existants à ne pas casser** : `test_epistemic_sources_and_brief.py`,
    `test_personas_simulation_graphiti.py`, `test_cohort_coverage_time.py`,
    `test_report_quality_gate_audit.py`, `test_sources_provenance_honesty.py`.

---

## Critères d'acceptation

| Réf. | Situation et comportement attendu | Vérification / preuve |
|---|---|---|
| **AC1** | **Un épisode partagé par deux personas est une contradiction** : quand le même couple (montant, mot-clé) apparaît dans les fiches de deux personas distincts, `audit_brief_persona_consistency` renvoie `is_consistent=False` et nomme les deux personas. | `tests/test_brief_persona_consistency.py::test_shared_episode_across_two_personas_is_contradiction` |
| **AC2** | **Un épisode attribué au mauvais persona est une contradiction** : quand le brief attribue un épisode au persona A et que la fiche du persona B le contient, l'audit renvoie `is_consistent=False` et nomme l'owner (A) et le porteur (B). | `::test_episode_owner_mismatch_is_contradiction` |
| **AC3** | **Un brief cohérent passe** : quand chaque épisode reste dans la fiche de son owner et qu'aucun épisode n'est partagé, `is_consistent=True`, `contradictions=[]`, et aucune exception n'est levée. | `::test_consistent_brief_passes` |
| **AC4** | **La préparation échoue à la construction** : `SimulationManager.prepare_simulation` lève `BriefPersonaContradictionError` quand l'audit détecte une contradiction, et `SimulationState.status` vaut `SimulationStatus.FAILED` (`state.error` renseigné). Aucun profil n'est persisté. | `::test_prepare_simulation_fails_on_contradiction` |
| **AC5** | **Un persona non admis est filtré du contexte de rédaction** : `filter_non_admitted_personas_from_text` retire toute phrase nommant un persona `review` ou `ineligible`, ou remplace son nom par `[persona non admis]` ; un persona `eligible` n'est jamais retiré. Le `simulation_requirement` transmis au `ReportAgent` ne contient plus le nom du non-admis. | `::test_non_admitted_personas_filtered_from_drafting_context` ; `::test_eligible_persona_is_preserved` |
| **AC6** | **L'audit est persisté et archivé** : le résultat est écrit en `brief_consistency.json` dans le dossier de simulation et joint à l'archive d'audit, avec `is_consistent`, les contradictions et les diagnostics. | `::test_consistency_audit_persisted` ; `::test_consistency_audit_in_archive` |
| **AC7** | **Déterminisme** : deux appels successifs sur le même brief et les mêmes fiches renvoient la même liste de contradictions, dans le même ordre, sans appel LLM. | `::test_consistency_is_deterministic` |
| **AC8** | **Le cas mesuré de R7 est reproduit** : une fixture reproduisant l'épisode « 1 500 € / WordPress » attribué à Émilie dans le brief et repris dans la fiche de Nathalie produit une contradiction nommant Émilie et Nathalie. | `::test_r7_episode_leak_detected` |
| **AC9** | **Non-régression** : le filet ne rétrécit pas — **2 083 tests backend** et **43 tests Node** au vert, mesurés le 24 octobre 2026 —, `ruff check` ne signale rien, `validate_plans.py` valide la structure. | `uv run pytest tests/ -q` (total ≥ 2 083), `pnpm --dir frontend test` (43), `uv run ruff check .`, `uv run python scripts/validate_plans.py` |

**Traçabilité exigence → AC → tâche.**

| Exigence de l'epic | AC | Tâches |
|---|---|---|
| FR-07 — pas de divergence de biographies | AC1, AC2, AC3, AC8 | T1, T2, T3 |
| FR-07 — fiches non admises hors du contexte | AC5 | T5, T6 |
| NFR-1 — zéro régression | AC9 | T9 |
| NFR-2 — généricité | AC1, AC2, AC8 | T1, T2 |
| NFR-3 — déterminisme | AC7 | T4 |
| NFR-5 — honnêteté | AC6 | T7 |
| NFR-6 — traçabilité | AC6 | T7 |
| C5 — aucune divergence de biographies | AC1, AC2, AC3, AC8 | T1, T2, T3 |
| C8 — re-qualification sans certification mensongère | AC4, AC5 | T5, T8 |

---

## Définition de fini

- [ ] `backend/app/services/brief_consistency.py` : `extract_episodes`, `audit_brief_persona_consistency`, `filter_non_admitted_personas_from_text`, `BriefPersonaContradictionError`.
- [ ] `backend/app/services/simulation_manager.py` : `prepare_simulation` exécute l'audit après `generate_profiles_from_entities` et échoue en `ERROR` sur contradiction.
- [ ] `backend/app/services/simulation_manager.py` : `brief_consistency.json` persisté dans le dossier de simulation.
- [ ] `backend/app/api/report.py` : le `simulation_requirement` transmis au `ReportAgent` est filtré des personas non admis.
- [ ] `backend/app/services/simulation_audit_service.py` : `brief_consistency.json` joint à l'archive d'audit.
- [ ] `backend/tests/test_brief_persona_consistency.py` : tous les cas nommés dans les AC, verts.
- [ ] `backend/tests/fixtures/brief_consistency/` : fixtures du cas contradictoire et du cas cohérent.
- [ ] Non-régression : `uv run pytest tests/ -q`, `pnpm --dir frontend test`, `uv run ruff check .`, `uv run python scripts/validate_plans.py`.
- [ ] Vérification visuelle sur la pile Docker de référence : une préparation de simulation sur R7 avec brief contradictoire refusée, puis une préparation cohérente acceptée.

---

## Tâches

- [ ] 1. **Extraire les épisodes** : `extract_episodes(text)` déterministe (montant + mot-clé, normalisation NFKD). *(AC1, AC2, AC8)*
- [ ] 2. **Auditer la cohérence brief/fiches** : `audit_brief_persona_consistency` détecte l'épisode partagé et l'owner mismatch. *(AC1, AC2, AC3, AC8)*
- [ ] 3. **Définir le résultat et l'erreur** : `ConsistencyResult` et `BriefPersonaContradictionError`. *(AC1, AC3)*
- [ ] 4. **Garantir le déterminisme** : tri stable par signature puis nom. *(AC7)*
- [ ] 5. **Faire échouer la préparation** : brancher l'audit dans `prepare_simulation`, marquer `ERROR`, ne rien persister. *(AC4)*
- [ ] 6. **Filtrer le contexte de rédaction** : `filter_non_admitted_personas_from_text` appliqué dans `api/report.py`. *(AC5)*
- [ ] 7. **Persister et archiver l'audit** : `brief_consistency.json` dans le dossier de simulation et dans l'archive. *(AC6)*
- [ ] 8. **Les tests** : `backend/tests/test_brief_persona_consistency.py` et les fixtures. *(AC1 à AC8)*
- [ ] 9. **La clôture technique** : non-régression, lint, validation de plan, vérification visuelle sur la pile Docker de référence. *(AC9)*

## Notes de développement

*(à remplir pendant l'implémentation : ce qui a été décidé en codant, et pourquoi ; les
points non résolus)*

---

## Revue

*(à remplir par la revue contradictoire : findings retenus, gravité, correctif appliqué,
points différés, rejets motivés)*

---

## Notes de complétion

*(à remplir à la clôture : statut final, tests exécutés, lint, validation de plan, écarts
avec le plan et pourquoi, ce que la story ne fait pas, effets de bord observés)*
