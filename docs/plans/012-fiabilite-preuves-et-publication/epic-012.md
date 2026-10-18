# Epic 012 : Fiabilité des acteurs, intégrité des preuves et publication stricte

> **Statut :** En cours (In-Progress) — 3/6 stories validées  
> **Date de formalisation :** 17 octobre 2026  
> **Responsable :** Équipe MiroFish & Antigravity  
> **Dépendances :** Epic 005 (Docker local), Epic 007 (Ontologie dynamique), Epic 008 (Localisation FR), Epic 009 (Éligibilité des acteurs), Epic 010 (Cycle de vie des simulations), Epic 011 (Preuve par les faits simulés)  
> **Dossier de plan :** `docs/plans/012-fiabilite-preuves-et-publication/`  
> **PRD :** [`prd.md`](prd.md) · **Architecture :** [`architecture.md`](architecture.md) · **Audit amont R6 :** [`../../retour-essai-6/PRD-MiroFish-correctifs-audit-reel-R6-2026-10-17.md`](../../retour-essai-6/PRD-MiroFish-correctifs-audit-reel-R6-2026-10-17.md)

---

## 1. Description & Contexte

L'Epic 011 a mis en place les piliers de traçabilité factuelle : journalisation JSONL/SQLite des actions (`observed_events.jsonl`), contrat structuré d'affirmations `ReportClaim`, tableau de couverture de cohorte, respect de l'horizon temporel, barrière de qualité et archive scellée SHA-256.

Toutefois, l'audit approfondi du 6ᵉ essai de simulation réelle (cas Keova : 16 agents, 72 heures simulées, 40 rounds, export `sim_ea4f3cfe1028` / `report_77d96ea4c1c9`) a révélé des dysfonctionnements majeurs :
1. **Collision d'identités d'agents** : Les 23 événements d'`Agent_1` ont été absorbés par `Agent_16` en raison d'un matching par sous-chaîne dans `CohortCoverageTable`.
2. **Cohorte polluée et dédoublée** : Inclusion d'acteurs inéligibles (Stripe, CPAM, WhatsApp) et dédoublement des alias techniques `Agent_X` portant la cohorte à 63 membres au lieu des 20 agents réels.
3. **Attribution de rôles et décisions d'adoption invalides** : Classification de tout profil humain en `PROSPECT` (y compris fondateurs) et passage automatique à `ADOPTED` pour tout agent actif sans objection formulée.
4. **Déconnexion complète claims $\leftrightarrow$ traces** : 0 claim vérifié sur 258 (`0 VERIFIED`), 241 `UNSUPPORTED`, et détection de mots courants (« Si », « Dès ») pris pour des noms de personas.
5. **Barrière de publication permissive (« Fail-Open »)** : Statut `is_publishable=true` accordé malgré un taux de vérification de 0,0 % et des dizaines d'actions d'agents sans preuve.

L'**Epic 012** résout ces anomalies à la racine pour établir une étanchéité absolue de l'attribution d'identités, une qualification honnête des décisions et une barrière de publication fail-closed sans compromis.

---

## 2. Exigences Fonctionnelles (FR)

- **FR-01 : Résolution d'identités sans collision (`AgentIdentityResolver`)** :  
  Appariement des événements d'actions d'abord par identifiant d'instance OASIS entier (`agent_id` int), puis par égalité stricte normalisée des noms. Suppression totale du matching par inclusion partielle de sous-chaîne. 0 événement d'`Agent_1` comptabilisé chez `Agent_16`.
- **FR-02 : Filtrage strict et séparation des populations de cohorte** :  
  Filtrage strict sur `eligibility_status == "eligible"`. Exclusion des tiers inéligibles du tableau de cohorte. Remplacement des identifiants techniques `Agent_X` par les personas nommés correspondants (0 doublon).
- **FR-03 : Rôles de scénario fidèles et statuts de décision déterministes** :  
  Rôles basés sur le brief et les profils (`FOUNDER`, `TEAM_MEMBER`, `EXISTING_USER`, `PROSPECT`, `PARTNER`, `UNKNOWN`). Statut `ADOPTED_VERIFIED` conditionné à une preuve d'action probante. Statut `NOT_APPLICABLE` pour les fondateurs et organisations.
- **FR-04 : Extraction et réconciliation robuste des claims avec l'`EvidencePack`** :  
  Validation préalable des sujets d'assertions contre la liste des personas réels. Réconciliation déterministe avec les traces de l'`EvidencePack` par acteur, round et nature d'action (sans dépendre d'IDs `evt_*` dans le texte).
- **FR-05 : Barrière de publication stricte « Fail-Closed »** :  
  Typage de publication en 4 états (`draft`, `needs_review`, `verified_publishable`, `failed_validation`). Blocage strict de la certification de publication (`is_publishable=false`) si 0 claim événementiel n'est vérifié ou en présence de contradictions critiques.
- **FR-06 : Traçabilité des sources, brief structuré et reproductibilité** :  
  Prévalence stricte de `epistemic_kind` sur le rôle générique. Détection des lacunes du brief. Intégration de fixtures de non-régression basées sur les anomalies R6.

---

## 3. Exigences Non Fonctionnelles (NFR)

- **NFR-1 : Généricité absolue** : 0 mot-clé ni logique spécifique au domaine Keova dans le code source.
- **NFR-2 : Non-régression totale** : Préservation des 1 761 tests backend existants au vert.
- **NFR-3 : Rétrocompatibilité** : Capacité de désérialisation sans erreur des fichiers de runs antérieurs.
- **NFR-4 : Déterminisme** : 100 % de reproductibilité des calculs de cohorte, de claims et de qualité.

---

## 4. Découpage en Stories

| Story | Titre | Statut | Fichier |
|---|---|---|---|
| 012-1 | Résolution stricte des identités d'acteurs et couverture de cohorte sans collision | `done` | [`story-012-1.md`](story-012-1.md) |
| 012-2 | Rôles de scénario et statuts de décision d'adoption déterministes | `done` | [`story-012-2.md`](story-012-2.md) |
| 012-3 | Extraction d'assertions assainie et réconciliation déterministe avec l'`EvidencePack` | `done` | [`story-012-3.md`](story-012-3.md) |
| 012-4 | Barrière de publication « Fail-Closed » et états de certification du rapport | `backlog` | [`story-012-4.md`](story-012-4.md) |
| 012-5 | Séparation épistémique des sources, intégrité du brief et détection de contradictions | `backlog` | `story-012-5.md` |
| 012-6 | Banc de qualification sur cas réel R6, complétude du manifeste et non-régression | `backlog` | `story-012-6.md` |

---

## 5. Critères de Sortie de l'Epic (C1 à C8)

1. **C1 : Zéro collision d'identités** : Rapprochement exact par `agent_id` int et égalité stricte normalisée. 0 événement de `Agent_1` dans `Agent_16`.
2. **C2 : Cohorte propre et sans doublon** : Filtrage strict sur les acteurs éligibles. 0 entité inéligible (Stripe, CPAM) dans la cohorte cible. Dédoublonnage des alias techniques.
3. **C3 : Rôles et adoptions étayés** : Les fondateurs/pilotes ne sont plus marqués `PROSPECT`. 0 faux statut `ADOPTED` déduit de la seule absence d'objection.
4. **C4 : Réconciliation probante des claims** : Rapprochement automatisé des actions réelles avec l'`EvidencePack`. Taux $\ge 80\ %$ d'actions observées vérifiées sur run nominal.
5. **C5 : Barrière de publication Fail-Closed** : Blocage du statut « vérifié » (`verified_publishable`) si 0 claim vérifié ou présence de contradictions bloquantes.
6. **C6 : Étanchéité documentaire** : Priorité de `epistemic_kind` sur le rôle, alertes sur briefs lacunaires.
7. **C7 : Validation sur fixture du run réel R6** : L'ancien export invalide est correctement détecté et rejeté par la nouvelle barrière.
8. **C8 : Non-régression globale** : $\ge 1 785$ tests au vert sur l'hôte, 0 échec.

---

## 6. Documents à consulter

| Document | Rôle |
|---|---|
| [`prd.md`](prd.md) | Spécifications fonctionnelles et métriques cibles. |
| [`architecture.md`](architecture.md) | Architecture technique, diagrammes de flux et modèles de données. |
| [`../../retour-essai-6/PRD-MiroFish-correctifs-audit-reel-R6-2026-10-17.md`](../../retour-essai-6/PRD-MiroFish-correctifs-audit-reel-R6-2026-10-17.md) | Rapport d'audit contradictoire du run réel R6. |
| [`../../retour-essai-6/audit_bundle_mirofish.py`](../../retour-essai-6/audit_bundle_mirofish.py) | Script d'audit ayant révélé les 5 anomalies. |
| [`../../backend/app/models/cohort_coverage.py`](../../backend/app/models/cohort_coverage.py) | Implémentation du tableau de cohorte et matching d'identités. |
| [`../../backend/app/services/report_agent.py`](../../backend/app/services/report_agent.py) | Extraction des claims et persistance. |
| [`../../backend/app/services/report_quality_gate.py`](../../backend/app/services/report_quality_gate.py) | Barrière de publication et contrôles qualité. |
| [`../../AGENTS.md`](../../AGENTS.md) | Constitution du dépôt (§2.1, §2.2, §2.8). |
