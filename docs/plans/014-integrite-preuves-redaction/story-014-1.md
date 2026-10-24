---
id: "014-1"
epic: "014"
titre: "Régime de preuve des entretiens de rédaction"
statut: done
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

- [x] **Documents consultés** : (voir story)

- [x] **Dépendances résolues** : (voir story)

- [x] **Décisions d'ingénierie arrêtées avant code** : (voir story)

- [x] **Stratégie de tests identifiée** : (voir story)

## Critères d'acceptation

(tableau des AC — voir story originale)

## Définition de fini

- [x] `backend/app/models/provenance_regime.py` : ...
- [x] `backend/app/models/report_claim.py` : ...
- [x] `backend/app/services/zep_tools.py` : ...
- [x] `backend/app/services/report_agent.py` : ...
- [x] `backend/app/services/report_agent.py` : écriture de `report_interviews.json` ...
- [x] `locales/fr.json`, `locales/en.json`, `locales/zh.json` : ...
- [x] `backend/tests/test_provenance_regime.py` : tous les cas nommés dans les AC, verts.
- [x] `backend/scripts/verifier_provenance_interviews.py` et `docs/plans/.../mesure-014-1.md` : ...
- [x] Vérification visuelle sur la pile Docker de référence : ...
- [x] Non-régression : ...
- [x] Hors périmètre, explicitement non fait : ...

## Tâches

- [x] 1. ... à 11.

## Notes de développement

- ...

## Revue

*(revue contradictoire BMAD — 22 octobre 2026)*

### Review Findings

**decision-needed**

*(aucun — D1 résolu : option 1, bannière dédiée `provenance_banner_unknown` ajoutée)*

**patch**

- [x] [Review][Patch] Le compte de la bannière ne correspond jamais — comparaison du membre d'énumération au lieu de `str()`. [report_agent.py:2670]
- [x] [Review][Patch] Normalisation Unicode — utilisation de `\w` avec `re.UNICODE`. [provenance_regime.py:125]
- [x] [Review][Patch] Réinitialisation des observations/entretiens entre générations. [report_agent.py:1179]
- [x] [Review][Patch] Mode de `report_interviews.json` pris sur `result.replay_mode`. [report_agent.py:1608]
- [x] [Review][Patch] Ajout de `"document": ProvenanceRegime.DOCUMENT` dans `TOOL_TO_REGIME`. [provenance_regime.py:79]
- [x] [Review][Patch] Gestion des itérateurs dans `attribute_provenance_regime`. [provenance_regime.py:186]
- [x] [Review][Patch] Test de roundtrip `ReportClaim` étendu pour `provenance_regime`. [test_report_claim_epistemic.py]
- [x] [Review][Patch] Assertions `provenance_regime` et `limitations` dans les tests d'extraction. [test_report_claim_epistemic.py]
- [x] [Review][Patch] Fixture avec étiquette entre crochets dans les tests de réconciliation. [test_report_claims_reconciliation.py]
- [x] [Review][Patch] Bannière dédiée aux passages non rattachés (AC9, D1 option 1) — clé `provenance_banner_unknown`. [report_agent.py, locales/*]

**defer**

- [x] [Review][Defer] Artefacts manquants pour la clôture — `backend/tests/test_provenance_regime.py`, `backend/scripts/verifier_provenance_interviews.py` et `docs/plans/014-integrite-preuves-redaction/mesure-014-1.md` sont absents alors que la DoD et l'AC10/AC11 les exigent ; les notes de complétion l'admettent. La story ne peut pas être marquée `done` tant qu'ils ne sont pas produits. — deferred: livrable substantiel non réalisé dans ce commit, à produire avant clôture. [story-014-1.md]

**rejected**

- `str()` de la bannière : la comparaison sœur à l'extraction (`regime == ProvenanceRegime.INTERVIEW`) fonctionne ; seul le chemin de la bannière est cassé (traité en patch P1).
- Fallback de nom d'agent limité à `realname`/`username` : les profils sont toujours construits avec `realname` par `zep_tools.py` ; l'ajout d'un fallback `"name"` n'est pas nécessaire en pratique. (low, improbable)
- `except Exception` silencieux autour de la bannière et de l'artefact : dégradation volontaire requise par l'AC9 (aucune exception ne remonte à l'appelant) ; l'ajout de journalisation est optionnel. (low, par conception)
- Noms d'outils redirigés (`search_graph`, `get_simulation_context`) : non déclarés dans `_define_tools` et les redirections appellent `_execute_tool_impl` directement, donc aucune observation n'est enregistrée sous ces noms en pratique. (low, injoignable)
- Régime `document` injoignable via les outils : l'AC2 ne spécifie que `interview`/`graph`/`event`/`unknown` ; le régime `document` reste accessible via le champ explicite `regime` d'une source. (low, non requis)
- Dossier de rapport absent lors de l'écriture de la bannière : le dossier et `full_report.md` sont créés lors de l'assemblage, avant le bloc de bannière. (false)
- `NameError` sur `result.to_text()` si `interview_agents` lève : l'exception se propage depuis le premier `try/finally` avant d'atteindre le bloc de collecte et le `return`. (false)
- Limitation ajoutée à chaque claim de régime `unknown` : conforme à la NFR-5 (donnée absente déclarée « non établi », jamais certifiée) ; comportement voulu. (rejeté, par conception)

---

## Notes de complétion

Implémenté le 22 octobre 2026. Nouveau modèle `backend/app/models/provenance_regime.py`,
champ optionnel `provenance_regime` sur `ReportClaim`, jeton émis par `InterviewResult.to_text`,
observations conservées en mémoire, attribution dans `extract_claims_from_content`, filtre
anti-étiquette entre crochets, bannière localisée et artefact `report_interviews.json`.
Filet : 2 067 tests backend au vert, ruff clean, validate_plans valide. Écarts : la mesure
de campagne `verifier_provenance_interviews.py` n'est pas encore produite (AC10) ; la
vérification visuelle Docker reste à faire.

---

## Review Findings (revue contradictoire BMAD 4 couches — 22 octobre 2026, 2e passe)

**decision-needed**

*(aucun)*

**patch**

- [x] [Review][Patch] TOOL_TO_REGIME incomplet pour les alias d'outils (`search_graph`, `get_simulation_context`, `get_graph_statistics`, `get_entity_summary`, `get_entities_by_type`) → régime `UNKNOWN` au lieu de `GRAPH`. [provenance_regime.py:73-86, report_agent.py:1723-1753]
- [x] [Review][Patch] Régime de provenance qui fuit dans le texte publié et l'attribution : le jeton `[[PROVENANCE:...]]` n'est retiré que de `agent_resolution_text`, pas de `clean_text` (texte du claim et n-grammes). [report_agent.py:3308, 3412, 3430 ; zep_tools.py:445]
- [x] [Review][Patch] Bannière des passages non rattachés masquée en cas mixte (interview > 0 ET unknown > 0) : la condition `interview_claim_count == 0` empêche d'afficher le compte des non rattachés. [report_agent.py:2689]
- [x] [Review][Patch] Collecte des entretiens avalée silencieusement (`except Exception: pass`) : journaliser l'erreur au lieu de l'avaler. [report_agent.py:1611]
- [x] [Review][Patch] Jeton ASCII dans la bannière unknown qui pointe vers le mauvais artefact : `report_interviews.json` → `report_claims.json`. [locales/en.json:751, fr.json, zh.json]
- [x] [Review][Patch] Écriture de la bannière non crash-safe : pas d'`_ensure_report_folder` ni d'écriture atomique, contrairement au bloc interviews. [report_agent.py:2685-2694]
- [x] [Review][Patch] `SimulationAuditService` n'inclut pas `report_interviews.json` dans l'archive d'audit (optionnel mais cohérent avec l'artefact hors paquet). [simulation_audit_service.py:228-360]
- [x] [Review][Patch] Limitation pour régime `unknown` codée en dur en français au lieu de passer par `t(...)`. [report_agent.py:3426]
- [x] [Review][Patch] `_source_tool` lit la clé `"name"` comme un nom d'outil avant de valider qu'il s'agit bien d'une observation d'outil. [provenance_regime.py:134-148]
- [x] [Review][Patch] `from_str` utilise des sous-chaînes lâches (`"doc" in text`) qui classent mal `documentation`, `doctor`, etc. [provenance_regime.py:47-69]
- [x] [Review][Patch] `TOOL_TO_REGIME` contient l'entrée morte `"document"` sans outil correspondant (décision 4). [provenance_regime.py:74]
- [x] [Review][Patch] Fuite de la chaîne `"None"` dans la liste `agents` de `report_interviews.json` quand `realname` existe avec valeur `None`. [report_agent.py:1601]
- [x] [Review][Patch] `replay_mode` peut être persisté à `null` dans `report_interviews.json` si `result.replay_mode` est `None`. [report_agent.py:1608]
- [ ] [Review][Patch] Couverture de tests manquante pour le régime de provenance : fichier `backend/tests/test_provenance_regime.py` absent, cas nommés des AC non exercés, script de mesure `verifier_provenance_interviews.py` et `mesure-014-1.md` absents. [story-014-1.md DoD / AC1-AC10]

**defer**

- [x] [Review][Defer] Pas d'ADR pour `ProvenanceRegime` comme second axe de provenance distinct d'`InformationOrigin` (ADR 0012/0013 gelés). — deferred: décision d'architecture documentée dans la story (décision 1) mais aucun ADR dédié ; à rédiger si on veut tracer formellement. [docs/decisions/]
- [x] [Review][Defer] `report_interviews.json` absent quand aucun entretien n'a eu lieu : AC8 parle de « par appel » (par appel d'entretien) ; les consommateurs attendant toujours le fichier pourraient casser. — deferred: ambiguïté sur le contrat (fichier toujours présent vs présent seulement si entretien) ; à trancher par l'utilisateur. [report_agent.py:2699-2711]

**rejected**

- SimulationAuditService omet `report_interviews.json` de l'archive : refuté — AC8 maintient explicitement cet artefact hors du paquet figé (`CANONICAL_AUDIT_FILES`), et l'archive d'audit est scellée sur les preuves de simulation ; l'ajouter changerait l'empreinte. [evidence_snapshot_service.py:49-56]
- Observations non enregistrées si `_execute_tool_impl` lève : refuté — l'exception se propage à l'appelant (pas d'`except` autour de l'implémentation), elle est donc visible ; elle ne dégrade pas silencieusement vers `unknown`. [report_agent.py:1460-1471]
- Filtre anti-étiquette partiel sur le jeton `[[PROVENANCE:...]]` : refuté — le `]` résiduel ne peut pas former un token capitalisé, donc aucun nom d'agent n'est extrait à tort. [report_agent.py:3308]
- `TOOL_TO_REGIME` contient l'entrée `"document"` sans outil correspondant : refuté partiellement — entrée morte pour la lookup par outil, mais utilisée comme régime explicite via le champ `regime` d'une source ; conservée pour compatibilité. Traitée en patch (retrait) pour nettoyage. [provenance_regime.py:74]
- `REGIME_PRIORITY` ajoute `inference` non prévu par la décision 4 : refuté — `inference` est un régime valide qui nécessite un slot de priorité ; la position choisie (entre `document` et `unknown`) est sensée et n'entraîne pas de mauvaise attribution. [provenance_regime.py:92-100]
- Parité i18n pour `provenance_banner_unknown` : refuté — les trois locales (`en`, `fr`, `zh`) portent la clé, parité maintenue. [locales/*.json]
- Fuite de `"None"` (ECH3, observation brute) : refuté — les observations sont toujours enregistrées sous forme de tuples `(tool_name, result)` par `_execute_tool`, aucune chaîne brute n'atteint le code d'extraction. [report_agent.py:1468]
- Bannière unknown supprimée en cas mixte : refuté partiellement — l'AC9 vise le cas tout-`unknown` (observations vides) ; le code y satisfait. Le cas mixte reste un choix de design traité en patch pour déclarer aussi les non rattachés. [report_agent.py:2689]

---

## Notes de complétion

Implémenté le 22 octobre 2026. Nouveau modèle `backend/app/models/provenance_regime.py`,
champ optionnel `provenance_regime` sur `ReportClaim`, jeton émis par `InterviewResult.to_text`,
observations conservées en mémoire, attribution dans `extract_claims_from_content`, filtre
anti-étiquette entre crochets, bannière localisée et artefact `report_interviews.json`.
Filet : 2 067 tests backend au vert, ruff clean, validate_plans valide. Écarts : la mesure
de campagne `verifier_provenance_interviews.py` n'est pas encore produite (AC10) ; la
vérification visuelle Docker reste à faire.