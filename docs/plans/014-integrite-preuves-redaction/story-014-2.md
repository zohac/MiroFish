---
id: "014-2"
epic: "014"
titre: "La section « Sources & Provenance » ne certifie que ce qu'elle prouve"
statut: backlog
auteur: "Antigravity & Équipe MiroFish"
format: "2"
---

# Story 014-2 — La section « Sources & Provenance » ne certifie que ce qu'elle prouve

**Lot B (certification honnête), priorité P0.** En tant que relecteur d'un rapport
produit par MiroFish — analyste, commanditaire ou tiers recevant l'archive d'audit —,
je veux que la section « Sources & Provenance » ne certifie une traçabilité que lorsqu'elle
la calcule réellement à partir du registre d'affirmations, afin de ne plus publier une
traçabilité que le registre du même rapport dément.

Cette story répond aux exigences **FR-03** (la section lit le registre ou s'abstient
explicitement), **FR-04** (les deux populations d'événements sont confrontées et nommées),
**FR-08** (un `project.json` corrompu n'affecte que son projet) et **FR-09** (un tiers
peut établir l'origine de chaque passage) du [PRD de l'epic](prd.md), et sert les
critères de sortie **C2** (aucune affirmation de traçabilité non calculée), **C6**
(isolation d'un projet corrompu) et **C7** (établissement de l'origine) de
l'[epic](epic-014.md). Elle dépend de la story 014-1 pour l'attribution du régime de
provenance dans le registre, et alimente la story 014-3 qui pourra s'appuyer sur une
section honnête pour faire remonter la règle de silence jusqu'à la barrière.

**Frontière, en une phrase.** Cette story **calcule et écrit** ce que la section peut
prouver ; elle ne corrige ni le régime des entretiens (014-1), ni la règle de silence
dans la prose (014-3), ni la construction des briefs (014-4).

---

## Définition de prêt

- [x] **Objectif compris et cadré** :

  **Le problème, mesuré.** La section « Sources & Provenance » est produite par
  `ReportAgent.build_sources_provenance_section()` et insérée dans le rapport
  (`report_agent.py`, assemblage autour de la ligne 2591). Elle est construite **avant**
  l'audit et la persistance du registre d'affirmations (`audit_and_save_report_claims`,
  autour de la ligne 2623) : elle ne peut donc pas lire ce registre. Deux de ses
  affirmations clés sont des **littéraux non calculés** et ne dépendent d'aucune mesure
  du rapport. Sur la campagne de l'Epic 013, la variante B affiche 7 affirmations
  `CONTRADICTED` sur le même persona silencieux avec `failed_checks: 0`, tandis que la
  section certifie une traçabilité que ce registre nie.

  **Ce que la story garantit, par sous-ensemble.**

  - **Ordre.** La section est produite **après** le registre, ou par un second passage
    qui relit le registre déjà persisté. Elle n'est jamais écrite avant que
    `report_claims.json` existe.
  - **Calcul.** Les deux affirmations litigieuses deviennent des valeurs calculées à
    partir du registre : nombre d'affirmations portant un `evidence_refs` non vide,
    nombre portant `provenance_regime`, taux de vérification. Quand la donnée est
    indisponible, la section affiche « non établi », jamais `0` ni une certification.
  - **Confrontation.** Les deux populations d'événements sont nommées et comptées :
    les actions effectives de `actions.jsonl` (216 sur R7) et les événements de
    l'`EvidencePack` (737 sur R7). La section énonce laquelle de ces deux populations
    sert à la réconciliation des affirmations.
  - **Isolation.** `ProjectManager.get_project`, `list_projects` et
    `find_projects_by_graph_id` ne propagent plus l'exception d'un `project.json`
    corrompu : un projet illisible est ignoré, et les autres projets restent résolubles.
  - **Honnêteté.** Un projet non résolu produit « Aucun document source structuré » ;
    il ne produit plus un décompte à zéro présenté comme un fait.

  **Les invariants — ce que l'implémentation ne peut pas faire.**

  - **Jamais de certification sans calcul.** Toute phrase de la section qui affirme une
    traçabilité doit être calculée depuis le registre ou depuis les artefacts du run.
    Un littéral restant est un défaut.
  - **Jamais de propagation d'exception entre projets.** Un fichier `project.json`
    tronqué dans le répertoire des projets ne peut pas priver un autre projet de sa
    section de sources.
  - **Jamais de `0` pour une donnée inconnue.** Un registre absent, un projet non
    résolu ou un artefact manquant s'affichent « non établi » ou « indisponible ».
  - **Jamais de nouvelle valeur dans `InformationOrigin` ni dans `ClaimKind`.** La
    section lit des données existantes ; elle n'étend aucun contrat.
  - **Jamais de dépendance ajoutée.** `json`, déjà utilisé, suffit pour sécuriser la
    lecture.

- [x] **Documents consultés** :

  - [PRD de l'epic](prd.md) : §2.2 (la section certifie une traçabilité que son
    registre nie), §4 (FR-03, FR-04, FR-08, FR-09), §5 (NFR-1, NFR-4, NFR-5), §6 (C2, C6, C7).
  - [Architecture de l'epic](architecture.md) : §3 (le modèle de preuve — le registre
    comme source de la certification), §8 (contraintes de non-régression).
  - [Hub de l'epic](epic-014.md) : §2 (FR-03, FR-04, FR-08, FR-09), §4 (story 014-2),
    §5 (C2, C6, C7).
  - `AGENTS.md` : §2.1 (les dépendances pointent vers l'intérieur), §2.2 (tout code
    produit est testé ; hermétique), §10 (un `project.json` corrompu casse la provenance
    de tous les rapports ; l'étiquette `[Événements simulés réels]` n'est produite par
    aucun code).
  - `backend/app/services/report_agent.py` : `_generate_report_internal`
    (assemblage `:2589`, section de provenance `:2591-2597`, claims `:2618-2625`),
    `build_sources_provenance_section` (`:2996`), `_resolve_project` (`:1410`).
  - `backend/app/models/project.py` : `get_project` (`:307`), `list_projects` (`:328`),
    `find_projects_by_graph_id` (`:352`).
  - `backend/app/models/report_claim.py` : `ReportClaim` et `ReportClaimRegistry`
    (champ `provenance_regime` depuis 014-1).
  - `backend/app/services/simulation_action_verifier.py` : `load_simulation_actions`,
    `analyze_intentions`, `format_conflicts_for_report`.
  - `backend/app/services/oasis_log_reader.py` : `OasisLogReaderService.load_evidence_pack`,
    modèle `EvidencePack`.
  - `backend/app/services/evidence_snapshot_service.py` : `CANONICAL_AUDIT_FILES`
    (`:49-56`), empreinte SHA-256.
  - `backend/app/services/simulation_audit_service.py` : `build_audit_package`,
    `build_run_manifest`.
  - `backend/app/models/source_document.py` : `InformationOrigin`, `SourceDocument`,
    `SourceConflict`.
  - `backend/tests/test_epistemic_sources_and_brief.py` : tests de prévalence épistémique.
  - `backend/tests/test_report_quality_gate_audit.py` : tests de barrière de publication.

- [x] **Dépendances résolues** :

  - **Stories amont** : 014-1 est en cours (`review`) et fournit le champ
    `provenance_regime` dans `ReportClaim` et l'artefact `report_interviews.json`. Les
    Epics 011 et 012 sont clos et fournissent `ReportClaim`, `ReportClaimRegistry`,
    `SimulationActionVerifier`, la barrière Fail-Closed et la prévalence épistémique.
    Aucun contrat de ces epics n'est rouvert.
  - **Stories avalentes** : 014-3 pourra s'appuyer sur une section honnête pour faire
    remonter la règle de silence jusqu'à la barrière.
  - **Filet de tests mesuré à la rédaction** : **2 067 tests backend** au vert sur
    l'hôte et **43 tests Node** frontend, mesuré le 22 octobre 2026
    (`uv run pytest tests/ -q`, `pnpm --dir frontend test`).
  - **Dépendances techniques** : aucune nouvelle dépendance. La sécurisation de la
    lecture JSON utilise `json`, déjà présent.

- [x] **Décisions d'ingénierie arrêtées avant code** :

  1. **La section est produite après le registre.** `build_sources_provenance_section`
     accepte un paramètre optionnel `claims_registry` ; quand il est fourni, la section
     calcule ses affirmations de traçabilité depuis lui. Quand il est absent, elle se
     relit depuis `report_claims.json` déjà persisté, ou s'abstient explicitement.
     *Raison* : la section ne doit jamais être écrite avant que le registre existe.
  2. **Les deux affirmations litigieuses deviennent calculées.** Le nombre
     d'affirmations portant un `evidence_refs` non vide et le nombre portant un
     `provenance_regime` sont comptés depuis le registre. *Raison* : un littéral ne
     peut pas être une preuve.
  3. **Les deux populations sont confrontées et nommées.** La section affiche le nombre
     d'actions de `actions.jsonl` et le nombre d'événements de l'`EvidencePack`, puis
     indique laquelle sert à la réconciliation des affirmations. *Raison* : 216 actions
     contre 737 événements ne sont pas la même chose, et le rapport doit le dire.
  4. **Un registre absent donne « non établi ».** Si `report_claims.json` est absent ou
     illisible, la section affiche « traçabilité non établie », jamais `0` ni une
     certification. *Raison* : NFR-5.
  5. **`ProjectManager` ne propage plus.** `get_project` retourne `None` sur
     `JSONDecodeError`/`OSError` avec un avertissement journalisé ; `list_projects` et
     `find_projects_by_graph_id` ignorent le projet illisible. *Raison* : un projet
     corrompu ne peut pas priver les autres de leur section de sources.
  6. **La section lit un projet résolu ou s'abstient.** Si `_resolve_project()` renvoie
     `None`, la section affiche « Aucun document source structuré » et ne produit aucun
     décompte à zéro. *Raison* : honnêteté par construction.
  7. **L'index d'attribution vit dans l'archive d'audit.** `run_manifest.json` et/ou
     l'archive ZIP portent le chemin de `report_claims.json` et son empreinte, pour qu'un
     tiers puisse établir l'origine de chaque passage. *Raison* : C7.
  8. **Aucune nouvelle valeur dans `InformationOrigin` ni dans `ClaimKind`.** La section
     lit des données existantes. *Raison* : ne pas rouvrir un contrat gelé.

- [x] **Stratégie de tests identifiée** :

  - **Hermétique d'abord.** Tous les tests nouveaux sont hermétiques : aucun appel
    réseau, aucun modèle, aucun `.env`. Les projets et registres sont des dossiers
    temporaires (`tmp_path`).
  - **Nouveau fichier** : `backend/tests/test_sources_provenance_honesty.py`, avec les
    cas nommés pour chaque AC.
  - **Ce qui est vérifié à l'œil** sur la pile Docker de référence : un rapport
    régénéré sur R7 dont la section n'affirme plus une traçabilité que le registre nie.
  - **Tests existants à ne pas casser** : `test_epistemic_sources_and_brief.py`,
    `test_report_quality_gate_audit.py`, `test_i18n_parity.py`.

---

## Critères d'acceptation

| Réf. | Situation et comportement attendu | Vérification / preuve |
|---|---|---|
| **AC1** | **La section est produite après le registre** : dans `_generate_report_internal`, `build_sources_provenance_section` est appelée **après** `audit_and_save_report_claims`, ou relit le registre déjà persisté. Un test sur un registre réel montre que les nombres affichés correspondent aux comptes du registre. | `tests/test_sources_provenance_honesty.py::test_section_reads_claims_registry` |
| **AC2** | **Aucune certification non calculée** : la section ne contient plus les deux affirmations litigieuses sous forme de littéraux. Quand le registre contient 0 affirmation portant `evidence_refs`, la section n'affirme aucune traçabilité documentaire. Quand il en contient N, elle affiche N. | `::test_no_uncalculated_traceability_claim` ; `::test_verified_count_matches_registry` |
| **AC3** | **Les deux populations sont confrontées** : la section affiche le nombre d'actions de `actions.jsonl` et le nombre d'événements de l'`EvidencePack`, et indique laquelle sert à la réconciliation des affirmations. | `::test_both_event_populations_are_named` |
| **AC4** | **Un registre absent donne « non établi »** : si `report_claims.json` est absent ou illisible, la section affiche « traçabilité non établie » et ne montre ni `0` ni une certification. | `::test_missing_registry_yields_not_established` |
| **AC5** | **Un projet corrompu n'affecte que son projet** : `ProjectManager.get_project` retourne `None` sur un `project.json` tronqué ; `list_projects` et `find_projects_by_graph_id` ignorent le projet illisible sans lever ; les autres projets restent résolubles. | `::test_corrupt_project_does_not_break_others` ; `::test_list_projects_skips_corrupt` |
| **AC6** | **Un projet non résolu s'abstient** : si `_resolve_project()` renvoie `None`, la section affiche « Aucun document source structuré » et aucun décompte à zéro. | `::test_unresolved_project_abstains` |
| **AC7** | **L'index d'attribution est dans l'archive** : `run_manifest.json` ou l'archive ZIP d'audit porte le chemin de `report_claims.json` et son empreinte SHA-256, pour qu'un tiers puisse établir l'origine de chaque passage. | `::test_audit_archive_carries_claims_index` |
| **AC8** | **Non-régression** : le filet ne rétrécit pas — **2 067 tests backend** et **43 tests Node** au vert, mesurés le 22 octobre 2026 —, `ruff check` ne signale rien, `validate_plans.py` valide la structure. | `uv run pytest tests/ -q` (total ≥ 2 067), `pnpm --dir frontend test` (43), `uv run ruff check .`, `uv run python scripts/validate_plans.py` |

**Traçabilité exigence → AC → tâche.**

| Exigence de l'epic | AC | Tâches |
|---|---|---|
| FR-03 — la section lit ou s'abstient | AC1, AC2, AC4 | T1, T2, T3 |
| FR-04 — confrontation des deux populations | AC3 | T4 |
| FR-08 — isolation d'un projet corrompu | AC5, AC6 | T5, T6 |
| FR-09 — établissement de l'origine par un tiers | AC7 | T7 |
| NFR-1 — zéro régression | AC8 | T10 |
| NFR-5 — honnêteté | AC2, AC4, AC6 | T2, T3, T6 |
| C2 — aucune certification non calculée | AC1, AC2 | T1, T2 |
| C6 — isolation d'un projet corrompu | AC5 | T5 |
| C7 — établissement de l'origine | AC7 | T7 |

---

## Définition de fini

- [ ] `backend/app/services/report_agent.py` : `build_sources_provenance_section` produite après le registre ou relisant `report_claims.json`, avec ses affirmations de traçabilité calculées.
- [ ] `backend/app/services/report_agent.py` : `_generate_report_internal` appelle la section après `audit_and_save_report_claims`.
- [ ] `backend/app/services/report_agent.py` : la section confronte et nomme les deux populations d'événements.
- [ ] `backend/app/models/project.py` : `get_project`, `list_projects` et `find_projects_by_graph_id` résilients à un `project.json` corrompu.
- [ ] `backend/app/services/simulation_audit_service.py` : l'archive d'audit porte l'index d'attribution des claims.
- [ ] `backend/tests/test_sources_provenance_honesty.py` : tous les cas nommés dans les AC, verts.
- [ ] Non-régression : `uv run pytest tests/ -q`, `pnpm --dir frontend test`, `uv run ruff check .`, `uv run python scripts/validate_plans.py`.
- [ ] Vérification visuelle sur la pile Docker de référence : un rapport régénéré sur R7 dont la section n'affirme plus une traçabilité que le registre nie.

---

## Tâches

- [ ] 1. **Réordonner la production de la section** : appeler `build_sources_provenance_section` après
      `audit_and_save_report_claims`, ou la faire relire le registre persisté. *(AC1)*
- [ ] 2. **Rendre les affirmations calculées** : remplacer les deux littéraux par des
      comptes issus du registre (`evidence_refs`, `provenance_regime`). *(AC2)*
- [ ] 3. **Afficher « non établi »** quand le registre est absent ou illisible. *(AC4)*
- [ ] 4. **Confronter les deux populations** : afficher et nommer les actions de
      `actions.jsonl` et les événements de l'`EvidencePack`, et indiquer laquelle sert à la
      réconciliation. *(AC3)*
- [ ] 5. **Sécuriser `ProjectManager`** : `get_project` retourne `None` sur JSON corrompu ;
      `list_projects` et `find_projects_by_graph_id` ignorent le projet illisible. *(AC5)*
- [ ] 6. **Faire s'abstenir la section** quand le projet n'est pas résolu. *(AC6)*
- [ ] 7. **Porter l'index d'attribution dans l'archive** : chemin et empreinte de
      `report_claims.json` dans `run_manifest.json` ou dans le ZIP d'audit. *(AC7)*
- [ ] 8. **Les tests** : `backend/tests/test_sources_provenance_honesty.py`. *(AC1 à AC7)*
- [ ] 9. **La clôture technique** : non-régression, lint, validation de plan, vérification
      visuelle sur la pile Docker de référence. *(AC8)*

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