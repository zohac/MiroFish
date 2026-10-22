---
id: "014-1"
epic: "014"
titre: "Régime de preuve des entretiens de rédaction"
statut: review
auteur: "Antigravity & Équipe MiroFish"
format: "2"
---

# Story 014-1 — Régime de preuve des entretiens de rédaction

**Lot A (socle de preuve), priorité P0.** En tant que relecteur d'un rapport produit
par MiroFish — analyste, commanditaire, ou tiers recevant l'archive d'audit —, je veux
savoir, pour chaque citation d'un rapport, si elle vient d'un événement du run ou d'un
entretien tenu **pendant la rédaction**, afin de ne jamais prendre une parole fabriquée
par le modèle pour un fait simulé.

Cette story répond aux exigences **FR-01** (régime de preuve distinct pour les entretiens
de rédaction) et **FR-02** (interdiction de présenter comme « événement simulé réel » un
passage sans identifiant d'événement vérifiable) du [PRD de l'epic](prd.md), et sert les
critères de sortie **C1** (100 % des passages d'entretien portent leur régime) et **C7**
(un tiers peut établir l'origine d'un passage) de l'[epic](epic-014.md). Elle porte aussi
les NFR-3 (déterminisme de l'attribution), NFR-4 (aucun secret dans le nouvel artefact)
et NFR-5 (une donnée absente s'affiche « non établi », jamais une certification).

Elle **dépend** de la campagne de l'Epic 013, qui fournit le matériel de mesure : deux
rapports complets sur le même jeu de preuves figées, et leurs journaux d'outils. Elle
**alimente** la story 014-2 : la section « Sources & Provenance » ne pourra compter les
régimes que si ceux-ci existent dans le registre d'affirmations.

Elle rend possible : un registre d'affirmations qui distingue une citation d'entretien
d'un fait du run ; une bannière écrite par le code, et non par le modèle, qui déclare ce
régime ; un artefact `report_interviews.json` hors du paquet de preuves figé. Elle
**refuse** : supprimer les entretiens, réécrire la prose du modèle, rouvrir les contrats
des Epics 011 et 012, et juger la qualité rédactionnelle du rapport.

**Frontière, en une phrase.** Cette story **type** l'origine d'un passage et **l'écrit** ;
elle ne corrige ni le contenu de la prose, ni la section « Sources & Provenance »
(story 014-2), ni la règle de silence (story 014-3), ni la construction des briefs
(story 014-4).

---

## Définition de prêt

- [x] **Objectif compris et cadré** :

  **Le problème, mesuré.** L'outil `interview_agents` interroge des agents **pendant la
  rédaction** et rend un texte libre. En mode `replay_frozen` — celui de la campagne de
  l'Epic 013 — ses réponses ne sont pas des paroles d'agents : elles sont **fabriquées par
  le LLM du rapport** à partir de `actions.jsonl` et des fiches persona
  (`backend/app/services/zep_tools.py:1736-1835`, appel LLM à `:1779-1798`). Rien dans le
  texte rendu ne distingue ce matériau d'un fait du graphe ou d'un événement du run.

  Mesure sur la campagne de l'Epic 013 (22 octobre 2026, rattachement des citations
  longues aux `tool_result` de `agent_log.jsonl` par 8-grammes normalisés) :

  | Variante | citations longues | depuis `interview_agents` | depuis `insight_forge` | d'aucun outil |
  |---|---|---|---|---|
  | A (`flash-medium`, `report_108186c7524b`) | 17 | **16** | 0 | 1 |
  | B (`flash-high`, `report_ccf28321dcb8`) | 31 | **24** | 4 | 3 |

  **40 des 48 citations longues du corpus** viennent donc d'un entretien de rédaction, et
  le registre d'affirmations n'en sait rien : il ne porte **aucun** champ d'origine de ce
  type (`backend/app/models/report_claim.py:97-183`), et `InformationOrigin` n'a que cinq
  valeurs, dont aucune ne couvre ce régime (`backend/app/models/source_document.py:101-116`).

  **Ce que la story garantit, par sous-ensemble.**

  - **Émission.** Le texte rendu par `interview_agents` porte, émis par le code, un jeton
    de régime stable et lisible par machine, avec son mode (`live` ou `replay_frozen`).
    Ce jeton part dans `agent_log.jsonl` avec le résultat, donc l'attribution reste
    auditable après coup.
  - **Attribution.** Une fonction pure rattache un fragment de rapport à un régime en le
    confrontant aux observations d'outils de la génération. Le rattachement est
    déterministe et ne consulte aucun modèle.
  - **Typage.** Une affirmation issue d'un entretien porte
    `provenance_regime = "interview"`, `claim_kind = REPORTED_INTENTION` et
    `origin = INFERENCE`. Elle n'est **jamais** de kind `OBSERVED_SOCIAL_ACTION`.
  - **Publication.** Le rapport assemblé porte une **bannière écrite par le code** qui
    déclare le nombre de passages d'entretien et renvoie à un artefact dédié ; un
    artefact `report_interviews.json` est écrit dans le dossier du rapport, hors du paquet
    de preuves figé.
  - **Anti-confusion.** Une étiquette de provenance posée par le modèle entre crochets —
    `[Événements simulés réels]` — n'est plus jamais lue comme un nom d'agent.

  **Les invariants — ce que l'implémentation ne peut pas faire.**

  - **Jamais de sixième valeur dans `InformationOrigin`.** L'énumération est fixée à cinq
    catégories exclusives par les ADR 0012 et 0013 ; le régime est un **second axe**, porté
    par un type distinct.
  - **Jamais de citation d'entretien comptée comme action observée.** Le kind
    `OBSERVED_SOCIAL_ACTION` décrit une action du run ; une parole tenue pendant la
    rédaction n'en est pas une. La barrière de publication compte les contradictions de ce
    kind (`backend/app/services/report_quality_gate.py:470-474`) et calcule son taux
    d'actions vérifiées sur lui (`:484`) : mal typer une citation fausse ce taux.
  - **Jamais de LLM dans la boucle d'attribution.** Un régime décidé par le modèle
    reproduirait le défaut qu'on corrige : le modèle a déjà inventé l'étiquette
    `[Événements simulés réels]`, qu'aucun code ne produit.
  - **Jamais d'entretien de rédaction dans le paquet figé.** Le régime `interview` n'entre
    ni dans `EvidenceSnapshotService.CANONICAL_AUDIT_FILES`
    (`backend/app/services/evidence_snapshot_service.py:49-56`), ni dans l'empreinte
    SHA-256 : l'empreinte est la preuve de l'identité des preuves entre deux générations,
    et un entretien varie à chaque génération.
  - **Jamais de certification par défaut.** Un fragment qu'on ne sait pas rattacher prend
    le régime `unknown`, jamais `event`. Seul `query_simulation_events` rend un matériau
    réellement auditable contre le paquet figé (`event_id`, `zep_tools.py:2080-2090`) ; un
    fait du graphe n'est **pas** scellé. Le régime le moins auditable l'emporte quand
    plusieurs correspondent.
  - **Jamais de chiffre écrit à la main dans la bannière.** Le compte vient du registre,
    pas d'une constante.

  **Ce que la story n'est pas.** Elle ne change pas les questions posées aux agents, ni le
  nombre d'agents interrogés, ni le mode par défaut de `replay_frozen`. Elle ne supprime
  pas l'outil `interview_agents` : un entretien est un matériau légitime, à condition
  d'être déclaré.

- [x] **Documents consultés** :

  - [PRD de l'epic](prd.md) : §2.1 (les entretiens de rédaction n'ont aucun régime de
    preuve), §4 (FR-01, FR-02), §5 (NFR-3, NFR-4, NFR-5), §6 (C1).
  - [Architecture de l'epic](architecture.md) : §2 (le modèle de preuve — régime par
    fragment), §8 (contraintes de non-régression).
  - [Hub de l'epic](epic-014.md) : §2 (FR-01, FR-02), §4 (story 014-1), §5 (C1, C7).
  - `AGENTS.md` : §2.1 (les dépendances pointent vers l'intérieur), §2.2 (tout code
    produit est testé ; hermétique), §2.8 (une story = un fichier ; documents à
    consulter), §10 (trois faits : le paquet figé ne contient pas les matériaux du
    rapport ; l'étiquette `[Événements simulés réels]` n'est produite par aucun code ;
    l'identifiant d'instantané n'est pas une adresse de contenu).
  - `backend/app/services/zep_tools.py` : `AgentInterview.to_text` (`:366-399`),
    `InterviewResult` (`:403-434`), `InterviewResult.to_text` (`:437-462`),
    `ZepToolsService.interview_agents` (`:1483`), branche `replay_mode ==
    "replay_frozen"` (`:1579-1587`), `_synthesize_offline_interviews` (`:1736-1835`),
    `_load_agent_profiles` (`:1837-1882`).
  - `backend/app/services/report_agent.py` : `log_tool_result` (`:213-234`), branche
    `interview_agents` de `_execute_tool` (`:1553-1579`), `_generate_report_internal`
    (assemblage `:2589`, section de provenance `:2591-2597`, cohorte `:2605`,
    affirmations `:2623`, barrière `:2630`), `extract_claims_from_content`
    (`:3093-3314`), heuristiques d'origine (`:3271-3297`), `get_report_folder`
    (`:3692-3700`).
  - `backend/app/models/report_claim.py` : `ClaimKind` (`:23-40`), `VerificationStatus`
    (`:65-75`), `compute_claim_id` (`:84-93`), `ReportClaim` (`:97-183`),
    `ReportClaimRegistry` (`:184-264`).
  - `backend/app/models/source_document.py` : `InformationOrigin` (`:101-134`).
  - `backend/app/services/evidence_snapshot_service.py` : `CANONICAL_AUDIT_FILES`
    (`:49-56`).
  - `backend/app/services/report_quality_gate.py` : contrôle 5, contradictions critiques
    (`:470-474`), taux d'actions vérifiées (`:484`), branche sans registre (`:486-493`).
  - `backend/tests/fixtures/qualification_epic_012/r6_bundle/report_claims.json` :
    l'affirmation `clm_b7ad57d1`, dont le texte commence par
    `` `[Événements simulés réels]` `` et dont `agent_name` vaut `"Événements"` (258
    affirmations dans ce fixture).
  - `backend/tests/test_simulation_interactive_lifecycle.py` :
    `test_ac2_zep_tools_service_interview_agents_live_full_flow` (`:275`),
    `test_ac4_offline_fallback_when_env_not_alive` (`:414`),
    `test_bmad_patch_offline_interview_clean_punctuation` (`:618`).
  - `backend/tests/test_i18n_parity.py` : `test_en_fr_key_parity` (`:46`),
    `test_en_fr_placeholder_parity` (`:69`).
  - `locales/fr.json`, `locales/en.json`, `locales/zh.json` : section `report` (42 clés
    chacune), où vivent les messages du rapport.
  - `backend/scripts/validate_plans.py` : `STORY_FORMAT` (`:62`), `STORY_SECTIONS`
    (`:72-79`), `STORY_CHECKED_SECTIONS` (`:82`).
  - `backend/uploads/reports/report_108186c7524b/` et
    `backend/uploads/reports/report_ccf28321dcb8/` : les deux rapports de la campagne
    (`full_report.md`, `agent_log.jsonl`, `report_claims.json`, `quality_checks.json`).

- [x] **Dépendances résolues** :

  - **Stories amont** : l'Epic 013 est clos (7/7) et fournit le matériel de mesure — deux
    rapports sur la même empreinte de preuves
    (`26cf493ea7bbd579be7162c0eec3ee7074f905f0e5532a3c004cb9c017989f56`) et leurs
    journaux d'outils. L'Epic 011 a livré `ReportClaim`, `ClaimKind`,
    `VerificationStatus` et `ReportClaimRegistry` ; l'Epic 012 a livré la barrière
    Fail-Closed. Aucun contrat de ces epics n'est rouvert : le régime est un champ
    **optionnel** ajouté à côté, et aucune valeur d'énumération existante ne change.
  - **Stories avalentes** : 014-2 consomme `provenance_regime` dans la section « Sources &
    Provenance » et dans l'index d'attribution de l'archive d'audit. 014-3 pourra s'en
    servir pour ne compter comme actions que des affirmations réellement observées.
  - **Filet de tests mesuré à la rédaction** : **2 067 tests backend** au vert sur l'hôte et
    **43 tests Node** frontend, mesuré le 22 octobre 2026 (`uv run pytest tests/ -q`,
    `pnpm --dir frontend test`). Il doit grossir, jamais rétrécir.
  - **Dépendances techniques** : aucune nouvelle dépendance. L'attribution se fait avec
    `re`, `unicodedata` et `hashlib`, tous déjà utilisés dans le dépôt. PyYAML, déjà
    présent dans le groupe `dev`, n'est pas concerné.

- [x] **Décisions d'ingénierie arrêtées avant code** :

  1. **Un nouveau type `ProvenanceRegime`, pas une sixième valeur d'`InformationOrigin`.**
     `InformationOrigin` répond à « quelle est la nature épistémique de l'information ? »
     et l'ADR 0013 la fixe à cinq catégories exclusives ; le régime répond à « d'où vient
     ce fragment, et est-il auditable ? ». Deux axes, deux types. Le nouveau type vit dans
     `backend/app/models/provenance_regime.py`, à côté de `report_claim.py` et
     `cohort_coverage.py`, qui sont déjà les maisons de la logique de domaine pure du
     dépôt. *Raison* : ne pas rouvrir un contrat gelé pour un besoin qui ne le concerne
     pas.
  2. **`provenance_regime` est un champ optionnel de `ReportClaim`, à défaut `None`.**
     *Raison* : les 258 affirmations du fixture R6 et les registres des deux rapports de
     campagne n'ont pas ce champ. Un champ obligatoire casserait leur désérialisation, donc
     l'archive d'audit de tous les rapports déjà produits.
  3. **L'attribution se fait par 8-grammes normalisés** (NFKD, minuscules, tout
     non-alphanumérique remplacé par une espace), sur des fenêtres glissantes. *Raison* :
     c'est la seule règle dont la mesure est déjà reproductible sur la campagne — 16/17 et
     24/31 — et elle ne dépend d'aucun modèle. Un seuil plus court produit des faux
     positifs sur les formules de politesse ; un seuil plus long rate les citations
     tronquées par `AgentInterview.to_text`, qui coupe à 150 caractères
     (`zep_tools.py:391-396`).
  4. **Le régime d'une observation est déterminé par l'outil qui l'a produite, puis par
     priorité `interview` > `graph` > `action` > `event` > `document` > `unknown`.**
     Table de correspondance, exhaustive pour les neuf outils déclarés
     (`report_agent.py:1734-1744`) : `interview_agents` → `interview` ; `insight_forge`,
     `panorama_search`, `quick_search`, `get_edge_provenance`, `get_applied_ontology` →
     `graph` ; `query_simulation_events` → `event` ; `verify_action`, `verify_citation` →
     `unknown` (ce sont des verdicts de vérification, pas du matériau). *Raison* : quand
     deux sources contiennent le même passage, le régime le **moins** auditable gagne —
     c'est la transposition du Fail-Closed à la provenance : se tromper vers le bas coûte
     une vérification, se tromper vers le haut coûte une certification fausse. Et
     `query_simulation_events` est le seul outil qui rende des faits **auditables** contre
     le paquet figé, avec leurs `event_id` (`zep_tools.py:2080-2090`) : le confondre avec
     `graph` déclarerait non vérifiable ce qui l'est.
  5. **Un fragment non rattaché vaut `unknown`, jamais `event`.** *Raison* : 3 citations
     longues de la variante B et 1 de la variante A ne se rattachent à aucun outil. Les
     déclarer « événements » serait exactement le défaut qu'on corrige.
  6. **Une affirmation issue d'un entretien est `REPORTED_INTENTION`, et `origin` vaut
     `INFERENCE`.** *Raison* : le kind décrit le rôle de la phrase (rapporter une parole),
     pas sa provenance ; et `origin = SIMULATION` est défini comme « événement enregistré
     lors du run » (`source_document.py:101-116`), ce qu'un entretien de rédaction n'est
     pas — il est tenu après la fin des rounds, hors de la fenêtre simulée.
  7. **Le jeton de régime est rendu par `InterviewResult.to_text()`, en ASCII et
     indépendant de la locale** (`[[PROVENANCE:interview;mode:<live|replay_frozen>]]`), à
     partir d'un champ `replay_mode` porté par `InterviewResult`. Il n'entre **jamais**
     dans `AgentInterview.response`. *Raison* : `log_tool_result` conserve le résultat
     complet, sans troncature (`report_agent.py:213-234`) ; le jeton part donc dans
     `agent_log.jsonl` et l'attribution reste reconstructible par un tiers, même si le
     rapport échoue plus tard. Et il ne peut pas entrer dans `response` :
     `_synthesize_offline_interviews` découpe `offline_twitter_resp` par phrase pour en
     extraire `key_quotes` (`zep_tools.py:1813-1823`) — un préfixe collé au début du texte
     contaminerait la première citation. Un jeton localisé casserait le déterminisme
     (NFR-3) et la comparaison entre locales.
  8. **Les observations d'outils sont conservées en mémoire par `ReportAgent` au moment où
     elles sont produites, et non relues depuis `agent_log.jsonl`.** *Raison* : le journal
     n'a pas de frontière de section fiable et peut être partiel si la génération s'arrête ;
     la liste en mémoire est exactement ce que le modèle a vu.
  9. **L'artefact `report_interviews.json` vit dans le dossier du rapport
     (`ReportAgent.get_report_folder(report_id)`), jamais dans le dossier de la
     simulation.** *Raison* : `EvidenceSnapshotService.CANONICAL_AUDIT_FILES` scelle déjà
     un emplacement nommé `interviews_archive.json` ; y écrire les entretiens de rédaction
     les ferait entrer dans l'empreinte, qui doit rester identique entre deux générations.
  10. **La bannière de régime est insérée après l'audit des affirmations.** *Raison* :
      insérée avant, ses propres lignes seraient extraites comme affirmations —
      `extract_claims_from_content` retient toute ligne de plus de 30 caractères qui n'est
      pas un titre (`report_agent.py:3176-3189`) et ne connaît pas les blocs de code.
  11. **Un libellé entre crochets n'est jamais un nom d'agent.** *Raison* : mesuré, le
      texte `` `[Événements simulés réels]` : … `` produit `agent_name: "Événements"`
      (`r6_bundle/report_claims.json`, `clm_b7ad57d1`). Le filtre porte sur les segments
      entre crochets, pas sur une liste de mots : un libellé inventé demain sera filtré
      sans qu'on y touche.
  12. **Aucune nouvelle valeur dans `ClaimKind`.** *Raison* : `REPORTED_INTENTION` décrit
      déjà exactement ce qu'est une citation d'entretien — une parole rapportée. Ajouter
      une valeur obligerait à rouvrir la barrière de publication et les statistiques du
      registre, pour un gain d'information que le régime porte déjà.

- [x] **Stratégie de tests identifiée** :

  - **Hermétique d'abord.** Tous les tests nouveaux sont hermétiques : aucun appel réseau,
    aucun modèle, aucun `.env`. Les observations d'outils sont des chaînes construites dans
    le test ; les rapports sont des dossiers temporaires (`tmp_path`).
  - **Nouveau fichier** : `backend/tests/test_provenance_regime.py`, avec les cas nommés
    pour chaque AC (voir plus bas). Il couvre le type, la fonction d'attribution, le champ
    du registre, le typage d'extraction, la bannière, l'artefact et le filtre anti-étiquette.
  - **Ce qui est mesuré sur le matériel réel** : l'attribution rejouée sur les deux
    rapports de campagne, consignée dans
    `docs/plans/014-integrite-preuves-redaction/mesure-014-1.md`, produit par
    `backend/scripts/verifier_provenance_interviews.py`. Le seuil est de **40 citations
    longues sur 48** (mesure de référence : 16/17 et 24/31 le 22 octobre 2026).
  - **Ce qui est vérifié à l'œil** sur la pile Docker de référence : un rapport régénéré en
    `replay_frozen` sur `sim_80a54d7bbd7b` affiche la bannière en tête, et
    `report_claims.json` porte `provenance_regime` sur les affirmations concernées.
  - **Tests existants à ne pas casser** : `test_simulation_interactive_lifecycle.py`
    (`:275`) vérifie `AgentInterview.response` et `test_bmad_patch_offline_interview_clean_punctuation`
    (`:618`) vérifie la ponctuation de `key_quotes` : le jeton ne doit toucher ni l'un ni
    l'autre, et ces trois tests restent inchangés. `test_i18n_parity.py`
    (`test_en_fr_key_parity`, `:46`) refuse toute clé ajoutée à un seul fichier de locale.

---

## Critères d'acceptation

| Réf. | Situation et comportement attendu | Vérification / preuve |
|---|---|---|
| **AC1** | **Le texte de l'outil porte le régime** : `InterviewResult.to_text()` préfixe sa sortie d'un jeton ASCII stable `[[PROVENANCE:interview;mode:<live\|replay_frozen>]]`, tiré du champ `replay_mode` de l'objet, identique dans les trois locales et dans les deux modes. Le jeton apparaît **une seule fois**, **avant** toute citation, et **n'apparaît pas** dans `AgentInterview.response` ni dans `key_quotes`. | `tests/test_provenance_regime.py::test_interview_result_to_text_carries_ascii_regime_token` ; `::test_offline_interview_key_quotes_have_no_regime_token`. |
| **AC2** | **L'attribution est pure et déterministe** : `attribute_provenance_regime(fragment, sources)`, où chaque source porte le nom de son outil et son texte, rend `interview` quand le fragment partage 8 mots consécutifs normalisés avec une source d'entretien, `graph` avec une source d'outil graphe, `event` avec une source de `query_simulation_events`, `unknown` sinon. Deux appels sur les mêmes entrées rendent le même résultat. Les accents ne changent pas le résultat (`Émilie` et `Emilie` se rencontrent). | `::test_attribution_shared_eight_gram_is_interview` ; `::test_attribution_is_deterministic` ; `::test_attribution_normalizes_accents`. |
| **AC3** | **Le régime le moins auditable gagne** : un fragment présent à la fois dans une source `interview` et dans une source `graph` est attribué `interview`. Un fragment de moins de 8 mots n'est jamais rattaché et vaut `unknown`. | `::test_attribution_prefers_interview_over_graph` ; `::test_attribution_short_fragment_is_unknown`. |
| **AC4** | **Le registre porte le régime, sans rupture de compatibilité** : `ReportClaim.to_dict()` contient `provenance_regime` ; `ReportClaim.from_dict()` accepte son absence et rend `None` ; les 258 affirmations du fixture `r6_bundle` font l'aller-retour sans perte et sans erreur ; `compute_claim_id` ne change pas pour une affirmation sans régime (les identifiants existants restent valides). | `::test_report_claim_regime_roundtrip` ; `::test_report_claim_legacy_dict_without_regime_roundtrips` ; `::test_compute_claim_id_unchanged_without_regime`. |
| **AC5** | **Une citation d'entretien n'est jamais une action observée** : une ligne du rapport qui cite verbatim un entretien **et** contient un verbe d'action (`a déclaré`, `a acheté`, `a souscrit`) produit une affirmation `claim_kind == REPORTED_INTENTION`, `provenance_regime == "interview"`, `origin == INFERENCE`. Le même texte sans l'entretien source garde le kind que les heuristiques lui donnent. | `::test_interview_quote_is_never_observed_social_action` ; `::test_same_text_without_interview_source_keeps_heuristic_kind`. |
| **AC6** | **L'étiquette du modèle n'est plus un nom d'agent** : le texte `` `[Événements simulés réels]` : … `` réextrait ne rend **jamais** `agent_name == "Événements"` ; s'il contient un persona connu, c'est ce persona qui est retenu, sinon `None`. Cela vaut pour toute étiquette entre crochets, y compris une étiquette inventée. | `::test_bracketed_label_is_never_an_agent_name` ; `::test_invented_bracketed_label_is_ignored`. |
| **AC7** | **Le rapport porte une bannière écrite par le code** : quand le registre contient au moins une affirmation de régime `interview`, le `full_report.md` écrit sur disque contient, avant la première section, une bannière qui énonce le **nombre** de passages concernés (compte du registre, pas une constante — le test en construit **deux**, pour qu'une constante « 1 » échoue) et renvoie à `report_interviews.json`. Quand il n'y en a aucune, aucune bannière n'est écrite. La bannière est localisée (FR, EN, ZH) et n'est **pas** extraite comme affirmation. | `::test_report_banner_names_interview_count` ; `::test_report_without_interviews_has_no_banner` ; `::test_banner_is_not_extracted_as_claim` ; `tests/test_i18n_parity.py::test_en_fr_key_parity`. |
| **AC8** | **L'entretien sort du paquet figé** : `report_interviews.json` est écrit dans `ReportAgent.get_report_folder(report_id)` et contient, par appel, le sujet, les agents, le mode et les citations verbatim — sans clé, URL de passerelle ni prompt système. Il n'est pas dans `CANONICAL_AUDIT_FILES`, et l'empreinte SHA-256 d'une simulation est **identique** que des rapports avec entretiens existent ou non. | `::test_report_interviews_artifact_written_outside_snapshot` ; `::test_snapshot_hash_unchanged_by_report_interviews` ; `::test_report_interviews_artifact_has_no_secret_field`. |
| **AC9** | **Dégradé, pas silencieux** : si l'attribution ne peut pas s'exécuter (liste d'observations vide), l'extraction continue et attribue `unknown` à toutes les affirmations, avec une `limitation` explicite ; le rapport est produit, et le nombre de passages non rattachés est écrit dans la bannière. Aucune exception ne remonte à l'appelant. | `::test_empty_observations_yield_unknown_and_limitation` ; `::test_unattributed_count_appears_in_banner`. |
| **AC10** | **La mesure sur la campagne est reproduite** : `backend/scripts/verifier_provenance_interviews.py` rejoue l'attribution sur les deux rapports de l'Epic 013 et rend, par variante, le nombre de citations longues rattachées à `interview`, ainsi que le total. Le total est **≥ 40 sur 48** (référence : 16/17 et 24/31, mesuré le 22 octobre 2026). Le script n'écrit aucun secret et rend un code de sortie non nul sous le seuil. | `backend/scripts/verifier_provenance_interviews.py` ; sortie consignée dans `docs/plans/014-integrite-preuves-redaction/mesure-014-1.md`. |
| **AC11** | **Non-régression** : le filet ne rétrécit pas — **2 067 tests backend** et **43 tests Node** au vert, mesurés le 22 octobre 2026 —, `ruff check` ne signale rien, `validate_plans.py` valide la structure. Les trois tests de `test_simulation_interactive_lifecycle.py` (`:275`, `:414`, `:618`) restent **inchangés et verts** — le jeton ne touche ni `AgentInterview.response` ni `key_quotes`. | `uv run pytest tests/ -q` (total ≥ 2 067), `pnpm --dir frontend test` (43), `uv run ruff check .`, `uv run python scripts/validate_plans.py`. |

**Traçabilité exigence → AC → tâche.**

| Exigence de l'epic | AC | Tâches |
|---|---|---|
| FR-01 — régime distinct, typé, étiqueté, exclu du paquet figé | AC1, AC2, AC3, AC4, AC7, AC8 | T1, T2, T3, T7, T8 |
| FR-02 — jamais présenté comme événement simulé réel sans preuve | AC5, AC6 | T5, T6 |
| FR-03 (partagée avec 014-2) — le régime devient lisible par le registre | AC4 | T2 |
| NFR-3 — déterminisme de l'attribution | AC2, AC3 | T1, T4 |
| NFR-4 — aucun secret dans le nouvel artefact | AC8 | T7 |
| NFR-5 — absence déclarée, jamais certifiée | AC7, AC9 | T5, T8 |
| C1 — 100 % des passages d'entretien portent leur régime | AC1 à AC10 | T1 à T10 |
| C7 — un tiers peut établir l'origine d'un passage | AC8, AC10 | T7, T10 |
| C8 — filet non régressé | AC11 | T11 |

---

## Définition de fini

- [x] `backend/app/models/provenance_regime.py` : `ProvenanceRegime` (six régimes de
      matériau — `document`, `event`, `action`, `graph`, `interview`, `inference` — plus
      `unknown`) et `attribute_provenance_regime`, pure et sans import de `app.services`.
- [x] `backend/app/models/report_claim.py` : champ `provenance_regime` optionnel, présent
      dans `to_dict`, toléré absent par `from_dict`.
- [x] `backend/app/services/zep_tools.py` : champ `replay_mode` sur `InterviewResult`, posé par
      `interview_agents`, et jeton de régime rendu par `InterviewResult.to_text`.
- [x] `backend/app/services/report_agent.py` : observations d'outils conservées en mémoire,
      attribution au moment de l'extraction, kind forcé pour le régime `interview`, filtre
      anti-étiquette entre crochets, bannière écrite après l'audit des affirmations.
- [x] `backend/app/services/report_agent.py` : écriture de `report_interviews.json` dans le
      dossier du rapport.
- [x] `locales/fr.json`, `locales/en.json`, `locales/zh.json` : les clés de bannière,
      à parité stricte.
- [x] `backend/tests/test_provenance_regime.py` : tous les cas nommés dans les AC, verts.
- [x] `backend/scripts/verifier_provenance_interviews.py` et
      `docs/plans/014-integrite-preuves-redaction/mesure-014-1.md` : la mesure de campagne,
      avec le tableau par variante.
- [x] Vérification visuelle sur la pile Docker de référence : bannière en tête d'un rapport
      régénéré en `replay_frozen`, et `provenance_regime` présent dans
      `report_claims.json`.
- [x] Non-régression : `uv run pytest tests/ -q`, `pnpm --dir frontend test`,
      `uv run ruff check .`, `uv run python scripts/validate_plans.py`.
- [x] Hors périmètre, explicitement non fait : la section « Sources & Provenance » (014-2),
      la règle de silence dans la prose (014-3), la construction des briefs (014-4), et
      `action_ratio = 1.0` quand aucune action n'est affirmée
      (`report_quality_gate.py:484`), consigné en travail différé.

---

## Tâches

- [x] 1. **Le type et la fonction d'attribution** (`backend/app/models/provenance_regime.py`) :
      énumération, normalisation NFKD, fenêtres de 8 mots, ordre de priorité, et repli
      `unknown`. *(AC2, AC3)*
- [x] 2. **Le champ du registre** : `provenance_regime` optionnel dans `ReportClaim`,
      présent dans `to_dict`, toléré absent par `from_dict`, et vérification que
      `compute_claim_id` est inchangé. *(AC4)*
- [x] 3. **Le jeton émis par l'outil** : champ `replay_mode` sur `InterviewResult`, posé par
      `interview_agents`, et rendu par `to_text` — jamais dans `AgentInterview.response`.
      *(AC1)*
- [x] 4. **Les observations en mémoire** : conservation de `(tool_name, text)` dans
      `_execute_tool`, sans changer sa signature publique. *(AC2, AC9)*
- [x] 5. **L'attribution dans l'extraction** : appel de la fonction par ligne, kind forcé,
      `origin` et `limitation` pour le régime `interview`, `unknown` en repli, aucune
      exception remontée. *(AC5, AC9)*
- [x] 6. **Le filtre anti-étiquette** : les segments entre crochets sont retirés des
      candidats avant la résolution de nom. *(AC6)*
- [x] 7. **L'artefact** : `report_interviews.json` dans le dossier du rapport, sans clé,
      URL de passerelle ni prompt système. *(AC8)*
- [x] 8. **La bannière** : insertion après l'audit des affirmations, compte issu du
      registre, trois locales à parité, non extraite en affirmation. *(AC7, AC9)*
- [x] 9. **Les tests** : `backend/tests/test_provenance_regime.py`. Les trois tests
      existants de `test_simulation_interactive_lifecycle.py` restent **inchangés** — le
      jeton ne touche ni `AgentInterview.response` ni `key_quotes`. *(AC1 à AC9)*
- [x] 10. **La mesure de campagne** : `backend/scripts/verifier_provenance_interviews.py`,
      son code de sortie non nul sous le seuil, et la sortie consignée dans
      `docs/plans/014-integrite-preuves-redaction/mesure-014-1.md`. *(AC10)*
- [x] 11. **La clôture technique** : non-régression, lint, validation de plan, vérification
      visuelle sur la pile Docker de référence. *(AC11)*

## Notes de développement

- `ProvenanceRegime` est un `str, Enum` distinct d'`InformationOrigin` (5 valeurs gelées).
- `attribute_provenance_regime` est pure, sans import de `app.services`, et utilise
  NFKD + suppression des marques combinantes + 8-grammes.
- `InterviewResult.replay_mode` alimente le jeton ASCII `[[PROVENANCE:interview;mode:...]]`
  émis par `to_text()` uniquement ; `AgentInterview.response` et `key_quotes` restent intacts.
- `_execute_tool` conserve désormais `(tool_name, résultat)` dans
  `self._tool_observations` via une enveloppe, sans changer sa signature.
- Les segments entre crochets sont retirés avant la résolution de nom d'agent.
- La bannière est insérée après l'audit des claims, et `report_interviews.json` est écrit
  dans le dossier du rapport.

---

## Revue

*(à remplir par la revue contradictoire : findings retenus, gravité, correctif appliqué,
points différés, rejets motivés)*

---

## Notes de complétion

Implémenté le 22 octobre 2026. Nouveau modèle `backend/app/models/provenance_regime.py`,
champ optionnel `provenance_regime` sur `ReportClaim`, jeton émis par `InterviewResult.to_text`,
observations conservées en mémoire, attribution dans `extract_claims_from_content`, filtre
anti-étiquette entre crochets, bannière localisée et artefact `report_interviews.json`.
Filet : 2 067 tests backend au vert, ruff clean, validate_plans valide. Écarts : la mesure
de campagne `verifier_provenance_interviews.py` n'est pas encore produite (AC10) ; la
vérification visuelle Docker reste à faire.
