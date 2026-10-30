# Rapport de qualification globale — Epic 015

> **Date d'exécution :** 2026-10-30T15:17:28.337340+00:00  
> **Branche :** `local-first`  
> **Verdict global :** **VERDICT GO** (8/8 critères validés)  
> **Stories couvertes :** `015-1`, `015-2`, `015-3`, `015-4`, `015-5`, `015-6`  
> **Scénarios d'acceptation source qualifiés :** `AT-01` à `AT-20` de bout en bout  

---

## 1. Synthèse des résultats par critère de sortie

| Critère | Description | Statut | Détails clés |
|---|---|:---:|---|
| **C1** | Régime de provenance, séparation action/intention, traçabilité | **✅ PASS** | Régime `INTERVIEW` préservé, séparation lexicale `\b` conforme, événements passifs OASIS filtrés (`AT-01`, `AT-02`, `AT-03`, `AT-04`) |
| **C2** | Registre `report_interviews.json` v2 et authentification des citations | **✅ PASS** | Schéma 2.0 par répondant, authentification des verbatim avec identifiants stables `ivw_*` (`AT-05`, `AT-06`, `AT-10`) |
| **C3** | Fermeture angle mort conceptuel & section Sources & Provenance 100% calculée | **✅ PASS** | Barrière Fail-Closed sur rapport sans action affirmée, rôle structurel `section_role="limitations"` (`AT-07`, `AT-12`, `AT-13`, `AT-14`) |
| **C4** | Gouvernance des rôles (`ParticipationPolicy`) & dénominateur d'adoption | **✅ PASS** | Organisations actives autorisées hors cohorte de décision, dénominateur en inclusion positive (`ADOPTER_ROLES`) (`AT-08`, `AT-09`, `AT-19`) |
| **C5** | Ergonomie & substitution chirurgicale `[persona non admis]` | **✅ PASS** | Caviardage sans altération syntaxique des phrases mixtes, non-régression IHM Step 3/4 responsive (`AT-10`) |
| **C6** | Cohérence biographique fiches ↔ prose finale | **✅ PASS** | Contradiction Sylvie (17 ans vs 2.5 ans) et transfert d'épisode détectés (`PERSONA_BIOGRAPHY_CONTRADICTION`), liberté d'opinion préservée (`AT-11`) |
| **C7** | Reproductibilité Docker (`GIT_COMMIT`) & horizon temporel traçable | **✅ PASS** | `ARG`/`ENV GIT_COMMIT` câblés, commit résolu (`3f9cce21ba87`), horizon résolu `72h` (`inferred_from_goal`) (`AT-15`, `AT-16`) |
| **C8** | Généricité multi-domaines (3 scénarios synthétiques) | **✅ PASS** | `0` constante R8 en dur (scan AST/regex propre), validation SaaS B2B, débat associatif (taux 0%) et grève de transports (`AT-17`, `AT-18`, `AT-19`, `AT-20`) |

---

## 2. Démonstrations spécifiques sur la fixture d'audit R8 (`sim_7a1b02b8c092` / `report_934d3254004b`)

1. **Cohérence biographique fiches ↔ prose (`AT-11`)** :
   - Fiche canonique de Sylvie (`reddit_profiles.json`) : `installée depuis deux ans et demi à Angers` ($2.5$ ans).
   - Prose du rapport (`full_report.md` ligne 34) : `installée depuis 17 ans avec un carnet plein` ($17.0$ ans).
   - Résultat d'audit : `PERSONA_BIOGRAPHY_CONTRADICTION` levée avec succès, claim marquée `CONTRADICTED` (`confidence=0.0`).
   - Évolution d'opinion et doutes exprimés en simulation : aucune fausse contradiction levée.

2. **Reproductibilité Docker et horizon temporel (`AT-15`, `AT-16`)** :
   - `backend/Dockerfile` déclare `ARG GIT_COMMIT=unknown-git-commit` et `ENV GIT_COMMIT=${GIT_COMMIT}`.
   - `docker-compose.yml` propage `build.args.GIT_COMMIT` et `environment.GIT_COMMIT`.
   - Le manifeste d'audit `run_manifest.json` résout le commit effectif `3f9cce21ba87dc1d32867e5ac615e9db64f3bac1`.
   - `time_horizon` résolu en cascade : `72h` avec `time_horizon_is_inferred: true` et `time_horizon_source: "inferred_from_goal"`.

3. **Généricité absolue du code de production (`AT-17`, `AT-18`)** :
   - Scan regex/AST sur `backend/app/`, `frontend/src/` et `locales/` : **0 violation**.

---

## 3. Verdict formel d'ingénierie

Le banc de qualification confirme que les 8 critères de sortie **C1 à C8** et l'intégralité des scénarios d'acceptation de l'audit externe (**AT-01 à AT-20**) sont formellement satisfaits.

**VERDICT FINAL : VERDICT GO**
