---
id: "015-2"
epic: "015"
titre: "Journal d'entretiens structuré par répondant et authentification des citations d'entretien"
statut: in-progress
auteur: "Antigravity & Équipe MiroFish"
format: "2"
---

# Story 015-2 — Journal d'entretiens structuré par répondant et authentification des citations d'entretien

**Lot A (socle d'intégrité des entretiens de rédaction), priorité P0.** En tant que
relecteur d'un rapport analytique MiroFish — analyste métier, commanditaire ou auditeur
indépendant inspectant `report_interviews.json`, `report_claims.json` et l'archive ZIP
d'audit —, je veux que chaque session d'entretien tenue pendant la rédaction enregistre
chaque tour par répondant canonique avec sa question, sa réponse intégrale (`answer_text`),
son mode d'exécution réel et ses citations exactes bornées par offsets caractères, et que
`SimulationActionVerifier` authentifie les citations et déclarations d'entretien par
répondant sans jamais les promouvoir en événements sociaux OASIS, afin de pouvoir vérifier
hors-ligne qu'une parole attribuée à un persona en entretien a réellement été tenue par ce
répondant précis, détecter toute attribution croisée ou altération entre guillemets, et
maintenir à `0` le nombre d'entretiens comptés comme `OBSERVED_SOCIAL_ACTION`.

Cette story répond à l'exigence **FR-03** (journal `report_interviews.json` v2 structuré par
entretien, tour et répondant avec réponse complète et authentification sans promotion en
action OASIS) du [PRD de l'epic](prd.md), porte les exigences non fonctionnelles **NFR-1**
(zéro régression et compatibilité ascendante de lecture sur les artefacts `v1`), **NFR-2**
(généricité absolue sans constante ni nom métier issu d'une fixture), **NFR-3**
(enrichissement KISS/DRY des modèles et services existants sans couche redondante),
**NFR-4** (zéro fuite de secret ou de prompt système interne dans `report_interviews.json`)
et **NFR-5** (honnêteté épistémique du mode d'entretien effectif et des verdicts de
vérification), et valide le critère de sortie **C2** de l'[epic 015](epic-015.md) tout en
alimentant **C7** et **C8**.

Elle **dépend** directement de la story **[015-1](story-015-1.md)** (`done` — survie de
`provenance_regime` sur les 11 chemins de `verify_report_claim`, booléen
`asserted_as_action` et sceau `ProvenanceRegime.INTERVIEW`), ainsi que des contrats des
stories `011-1` (entretiens interactifs post-rounds et synthèse hors-ligne sur archives),
`012-1` / `012-3` (`AgentIdentityResolver` sans collision par sous-chaîne), `013-2` /
`013-3` (empreinte `EvidenceSnapshotService` et isolation par `report_id`) et `014-1`
(régime `ProvenanceRegime.INTERVIEW` et exclusion du paquet figé). Elle **alimente** la
story **015-3** (qui s'appuie sur un registre `report_claims.json` où les entretiens portent
leurs références `ivw_*` sans fausser `asserted_action_claims` ni `verified_action_claims`,
et aligne la sous-section 3 de « Sources & Provenance ») ainsi que la story **015-6**
(qualification de bout en bout en `replay_frozen` sur R8 et sur 3 scénarios synthétiques
multi-domaines).

Elle rend possible : un artefact `report_interviews.json` `schema_version: "2.0"` traçant
chaque réponse complète par `interview_id`, `turn_id` (`ivw_..._tXX`), `turn_index`,
`agent_id` et `persona_name` canonique ; la distinction fidèle entre mode `live` OASIS,
repli `offline_archive` et mode `replay_frozen` ; des `key_quotes` vérifiant l'invariant
`answer_text[char_start:char_end] == quote` ; la lecture tolérante des anciens fichiers
`v1` ; et l'authentification déterministe par répondant dans
`SimulationActionVerifier.verify_report_claim` (`VERIFIED` + `turn_id` si bon auteur,
`CONTRADICTED` si citation d'un autre répondant, `UNSUPPORTED` si citation altérée ou
fabriquée, toujours hors `OBSERVED_SOCIAL_ACTION` et avec `asserted_as_action = False`).
Elle **refuse** : créer une couche de services parallèle (`InterviewLedger`,
`EvidenceLedger`, `ReportRenderer`), modifier `ReportQualityGate`, `section_role="limitations"`
ou le littéral résiduel de `report_agent.py:3211` (`015-3`), modifier `ActorClassifier`,
`prospect_members` ou le filtre `[persona non admis]` (`015-4`), modifier l'IHM Vue 3
(`015-5`), auditer les biographies aval ou `GIT_COMMIT` (`015-6`), inclure
`report_interviews.json` dans `EvidenceSnapshotService.CANONICAL_AUDIT_FILES`, ou toucher à
`backend/app/utils/report_benchmark_score.py` (`1.1.0`).

---

## Définition de prêt

- [x] **Objectif compris et cadré** :

  **Le problème, mesuré sur le code au `HEAD` (`b41ec04`) et sur les artefacts R8 (`29 octobre 2026`).**
  L'inspection conjointe de `report_934d3254004b` (`sim_7a1b02b8c092`) et du pipeline
  `ZepToolsService.interview_agents` → `ReportAgent._execute_tool_impl` →
  `ReportAgent.audit_and_save_report_claims` → `SimulationActionVerifier.verify_report_claim`
  met en évidence cinq ruptures mécaniques qui empêchent toute authentification d'entretien :

  | Fait mesuré le 29 oct. 2026 sur R8 (`report_934d3254004b`) et le code | Cause racine vérifiée ligne par ligne dans le code (`HEAD` `b41ec04`) |
  |---|---|
  | **Aplatissement complet de `report_interviews.json`** : le fichier est une liste racine de **`4` entrées** cumulant **`21` tours répondants** (`6 + 6 + 6 + 3`) mais **`63` courts extraits aplatis** (`18 + 18 + 18 + 9`), avec `0` `interview_id`, `0` `turn_id`, `0` `agent_id`, `0` `answer_text` et aucun lien entre une citation et son auteur. | Dans `ReportAgent._execute_tool_impl` (`backend/app/services/report_agent.py:1669-1686`), la collecte fait `citations.extend(list(getattr(iv, "key_quotes", []) or []))` en mélangeant tous les répondants d'un même appel dans un tableau plat `citations`, et jette `iv.response` ainsi que `iv.question`. |
  | **`21 / 21` répondants (`100 %`) enregistrés sous leur `username` technique** (`nathalie_962`, `florence_927`, `simon_518`, `marie_bourel_852`) au lieu de leur `persona_name` canonique (`Nathalie`, `Florence`, `Simon`, `Marie Bourel`). | `reddit_profiles.json` stocke l'identifiant sous `"user_id"` et le nom sous `"name"` (sans clé `"realname"`), alors que `zep_tools.py` (`:1634`, `:1767`, `:1915`) et `report_agent.py` (`:1675`) ne lisent que `agent.get("realname")` avant de se replier sur `"username"`, sans consulter `"name"` ni `AgentIdentityResolver`, et `AgentInterview` (`zep_tools.py:347-364`) ne porte aucun champ `agent_id`. |
  | **Mode effectif falsifié sur `4 / 4` sessions (`100 %`)** : `report_interviews.json` affiche `"mode": "live"` et `agent_log.jsonl` émet `[[PROVENANCE:interview;mode:live]]`, alors que les `4` sorties contiennent `"【Twitter - Mode archives / Hors-ligne】"` (`0` réponse live OASIS). | Dans `ZepToolsService.interview_agents` (`zep_tools.py:1532-1536`, `:1694-1705`), `result.replay_mode` est initialisé à `"live"` et n'est **pas** mis à jour lorsque `SimulationRunner.interview_agents_batch` lève `ValueError` et bascule vers `_synthesize_offline_interviews` (synthèse par le LLM du rapport). |
  | **Extraits `key_quotes` impropres à une vérification par offset** : ponctuation chinoise `"。"` ajoutée en mode live (`zep_tools.py:1666-1674`), point final synthétique ajouté en mode hors-ligne (`:1828-1830`), et résidus Markdown (`"** J'ai refermé..."` dans R8 `:15`). | La découpe de `zep_tools.py:1666` (`re.split(r'[。！？]', clean_text)`) ignore `.!?` sur un texte français/anglais et concatène `"。"` absent de `response`, empêchant de garantir `answer_text[char_start:char_end] == quote`. |
  | **`0` citation d'entretien authentifiée dans `report_claims.json`** alors que `full_report.md` contient `103` citations entre guillemets (`>= 15` car.) dont **`31` sous-chaînes exactes** des sorties d'`interview_agents` ; de plus `report_interviews.json` est écrit **après** l'audit des claims et est omis si `0` entretien a eu lieu. | 1) `generate_report` appelle `audit_and_save_report_claims` (`report_agent.py:2730`) **avant** l'écriture de `report_interviews.json` (`:2810-2824`) et sans transmettre les entretiens à `verify_report_claim` (`:3918-3925`) ; 2) `verify_report_claim` (`simulation_action_verifier.py:1354-1390`) ne confronte `REPORTED_INTENTION` qu'à `evidence_pack` (`verify_simulated_citation`), marquant systématiquement les entretiens `UNSUPPORTED` sans référence `ivw_*` et sans détecter ni faux auteur ni citation altérée. |

  **Ce que la story garantit, par sous-ensemble.**

  - **Modèle de données `v2` et lecture rétrocompatible `v1` (`backend/app/models/report_interviews.py`).**
    Un module de modèles purs (dataclasses standard `InterviewQuoteSpan`, `InterviewTurn`,
    `InterviewSession`, `ReportInterviewsPayload`) formalise l'enveloppe `schema_version: "2.0"`
    avec identifiants déterministes `interview_id` (`ivw_<NN>_<sha8>`) et `turn_id`
    (`ivw_<NN>_<sha8>_t<MM>`), extraction de tranches exactes garantissant
    `answer_text[char_start:char_end] == quote`, écriture atomique sur disque (`.tmp` +
    `os.replace`) sans fuite de secret, et lecture tolérante des formats historiques `v1`
    (liste plate ou enveloppe `{"interviews": [...]}`).
  - **Capture fidèle des répondants et du mode effectif (`ZepToolsService` & `ReportAgent`).**
    `AgentInterview` conserve `agent_id: Optional[int] = None` et résout le nom depuis
    `realname -> name -> entity_name -> username` ; `InterviewResult` distingue le mode
    effectivement exécuté (`"live"`, `"offline_archive"`, `"replay_frozen"`) jusque dans son
    jeton `[[PROVENANCE:interview;mode:...]]` ; `ReportAgent` résout chaque répondant via
    `AgentIdentityResolver` et persiste `report_interviews.json` v2 **avant**
    `audit_and_save_report_claims` (y compris avec `"sessions": []` si `0` entretien n'a été
    appelé).
  - **Authentification par répondant sans promotion OASIS (`SimulationActionVerifier`).**
    `verify_report_claim` accepte `report_interviews` et vérifie déterministement les
    affirmations de régime `ProvenanceRegime.INTERVIEW` (ainsi que les citations directes non
    issues d'actions affirmées dont l'extrait entre guillemets provient d'un `answer_text`
    sans trace dans `evidence_pack`) :
    - citation verbatim ou déclaration 8-grammes appartenant bien au `answer_text` du
      répondant résolu → `VerificationStatus.VERIFIED`, `evidence_refs` enrichi du `turn_id`
      (`ivw_..._tXX`), `claim_kind = ClaimKind.REPORTED_INTENTION`,
      `origin = InformationOrigin.INFERENCE`, `provenance_regime = ProvenanceRegime.INTERVIEW`,
      `asserted_as_action = False` ;
    - citation ou segment d'entretien appartenant au `answer_text` d'un **autre** répondant →
      `VerificationStatus.CONTRADICTED`, `confidence = 0.0`, `evidence_refs = []`, limitation
      explicite nommant le répondant réel et son `turn_id` ;
    - citation entre guillemets altérée lexicalement/numériquement, référence `ivw_*`
      inexistante, ou paraphrase d'entretien non rattachable à un répondant identifié →
      `VerificationStatus.UNSUPPORTED`, `evidence_refs = []`, limitation diagnostique dédiée.
  - **Étanchéité d'audit (`EvidenceSnapshotService` vs `SimulationAuditService`).**
    `report_interviews.json` reste strictement exclu de
    `EvidenceSnapshotService.CANONICAL_AUDIT_FILES` (l'empreinte du jeu de preuves figé ne
    bouge pas d'un bit entre régénérations), tout en étant inclus en `v2` et scellé dans
    `checksums.sha256` par `SimulationAuditService.gather_audit_files`.

  **Les invariants — ce que l'implémentation ne peut pas faire.**

  - **Jamais de promotion d'un entretien en `ClaimKind.OBSERVED_SOCIAL_ACTION` ni en
    `InformationOrigin.SIMULATION`, et jamais `asserted_as_action = True` sur un entretien.**
    Une réponse d'entretien (même authentifiée `VERIFIED` avec `turn_id` `ivw_*`) demeure une
    parole déclarative post-run / hors run (`ClaimKind.REPORTED_INTENTION`,
    `origin = InformationOrigin.INFERENCE`, `provenance_regime = ProvenanceRegime.INTERVIEW`,
    `asserted_as_action = False`).
  - **Jamais de blanchiment d'une action sociale OASIS non prouvée par un entretien.** Si une
    affirmation a été extraite comme action sociale exécutée (`was_asserted_action is True`,
    ex. *« Claire a publié sur Twitter : "…" »*) et échoue contre `evidence_pack`, elle reste
    `UNSUPPORTED` avec `asserted_as_action = True` : la présence d'une phrase voisine dans
    `report_interviews.json` ne peut jamais la certifier `VERIFIED`.
  - **Jamais de correspondance floue permissive (`SequenceMatcher`) pour valider une citation
    entre guillemets.** Entre guillemets (`« … »`, `“…”`, `"…"`), seules les normalisations
    typographiques neutres (apostrophes `' / ’`, espaces insécables, espaces multiples, casse
    initiale) projetées sur une tranche contiguë exacte `(char_start, char_end)` de
    `answer_text` sont admises ; toute modification de mot, de négation ou de nombre est
    rejetée.
  - **Jamais de rupture du type `AgentInterview.key_quotes: List[str]`** dans
    `backend/app/services/zep_tools.py` (`test_simulation_interactive_lifecycle.py:652-655`
    itère dessus comme `str`) : la structure `{"quote", "char_start", "char_end"}` est portée
    par `InterviewTurn.key_quotes` dans `backend/app/models/report_interviews.py`.
  - **Jamais de couche parallèle `InterviewLedger` / `EvidenceLedger` / `ReportRenderer`**
    dupliquant `ReportClaimRegistry` ou `ReportManager` (`NFR-3`, `architecture.md` §3).
  - **Jamais d'inclusion de `report_interviews.json` dans
    `EvidenceSnapshotService.CANONICAL_AUDIT_FILES`** (`backend/app/services/evidence_snapshot_service.py:49-56`).
  - **Jamais de clé API, d'URL interne de passerelle LLM ni de prompt système d'incarnation**
    dans `report_interviews.json` (`NFR-4`).
  - **Jamais de constante, nom d'entreprise, offre, tarif ou persona issu d'une fixture**
    dans `backend/app/**` (`NFR-2`).

- [x] **Documents consultés** :
  - `AGENTS.md` : §1 (état de l'Epic 015), §2.8 (cycle de vie `backlog → in-progress → review → done`), §2.10 (langue française), §5 (invariants).
  - `docs/decisions/0012-contrat-de-provenance-graphstore.md` et `docs/decisions/0013-semantique-des-sources.md` : gel des 5 valeurs exclusives d'`InformationOrigin`.
  - `docs/plans/015-contrats-preuve-roles-et-ihm/prd.md` : §2.2 (`:31-36`), §4 `FR-03` (`:91`), §5 `NFR-1` à `NFR-5` (`:104-108`), §6 `C2` (`:118`).
  - `docs/plans/015-contrats-preuve-roles-et-ihm/architecture.md` : §1 (`:21-33`), §2.2 (`:77-115`, schéma `v2` et authentification sans promotion), §3 (`:177-185`, rejet de `InterviewLedger`).
  - `docs/plans/015-contrats-preuve-roles-et-ihm/epic-015.md` : §2 (`:29`), §4 `015-2` (`:58`), §4.1 (`:66-70`), §4.2 (`:77`), §5 `C2` (`:88`).
  - `docs/plans/015-contrats-preuve-roles-et-ihm/story-015-1.md` : contrats `done` sur `ReportClaim.asserted_as_action`, `dataclasses.replace` et sceau `ProvenanceRegime.INTERVIEW`.
  - `docs/plans/014-integrite-preuves-redaction/story-014-1.md` : régime `ProvenanceRegime.INTERVIEW`, exclusion du paquet figé, et point différé `:230` sur la présence systématique de `report_interviews.json`.
  - `docs/PRD-MiroFish-correctifs-generiques-audit-R8-2026-10-29.md` : diagnostic D02 (`:57-62`) et P0-2 (`:177-187`).
  - `backend/scripts/validate_plans.py` : règles machine du format `"2"` (`:63-88`, `:217-331`).
  - `backend/app/services/zep_tools.py` : `AgentInterview` (`:346-399`), `InterviewResult` (`:402-469`), `interview_agents` (`:1491-1722`), `_synthesize_offline_interviews` (`:1745-1845`), `_load_agent_profiles` (`:1846-1891`), `_select_agents_for_interview` (`:1893-1950`).
  - `backend/app/services/report_agent.py` : initialisation/réinitialisation `_interview_records` (`:1260`, `:2493`), branche `interview_agents` de `_execute_tool_impl` (`:1645-1687`), assemblage `generate_report` (`:2725-2824`), `build_sources_provenance_section` (`:3291-3347`), `extract_claims_from_content` (`:3500-3749`), `audit_and_save_report_claims` (`:3810-3950`), `ReportManager._get_report_interviews_path` (`:4217-4224`).
  - `backend/app/services/simulation_action_verifier.py` : `verify_simulated_citation` (`:835-929`), `verify_report_claim` (`:932-1435`).
  - `backend/app/models/report_claim.py` (`:97-225`), `backend/app/models/provenance_regime.py` (`:24-238`), `backend/app/models/cohort_coverage.py` (`:29-160`).
  - `backend/app/services/simulation_audit_service.py` (`:346-358`) et `backend/app/services/evidence_snapshot_service.py` (`:49-56`).
  - Suites de tests existantes : `backend/tests/test_simulation_interactive_lifecycle.py` (`:317-327`, `:463-476`, `:618-656`), `backend/tests/test_story_015_1_claim_contracts.py` (`:416-440`, `:688-728`), `backend/tests/test_report_claims_reconciliation.py`, `backend/tests/test_sources_provenance_honesty.py`.

- [x] **Dépendances résolues** :
  - **Stories amont livrées (`done`)** : `011-1` (cycle de vie interactif et repli `_synthesize_offline_interviews`), `011-3` (`ReportClaim`, `SimulationActionVerifier`), `012-1` / `012-3` (`AgentIdentityResolver`), `013-2` (`EvidenceSnapshotService`), `013-3` (stockage isolé `reports/<report_id>/`), `014-1` (`ProvenanceRegime.INTERVIEW`, bannières et `report_interviews.json`), `015-1` (préservation de `provenance_regime` sur les 11 retours, `asserted_as_action` et sceau `INTERVIEW`).
  - **Stories aval alimentées** : `015-3` (barrière `ReportQualityGate` et sous-section 3 calculée de « Sources & Provenance »), `015-6` (qualification R8 en `replay_frozen` et scénarios multi-domaines).
  - **État du filet de tests mesuré à la rédaction (`29 octobre 2026`, commit `b41ec04`)** : **`2 109` tests backend hôte passants** (`1 warning`, `0` échec via `cd backend && uv run pytest tests/ -q`) et **`43` tests Node frontend passants** (`0` échec via `pnpm --dir frontend test`).
  - **Dépendances techniques** : aucune bibliothèque externe nouvelle (modules standard `dataclasses`, `datetime`, `hashlib`, `json`, `os`, `re`, `unicodedata` uniquement).

- [x] **Décisions d'ingénierie arrêtées avant code** :
  1. **D1 — Modèle de schéma `report_interviews.json` v2 (`backend/app/models/report_interviews.py`) et identifiants déterministes** : création d'un module de dataclasses pures sans dépendance réseau ni service (`InterviewQuoteSpan`, `InterviewTurn`, `InterviewSession`, `ReportInterviewsPayload`) sérialisant l'enveloppe `schema_version: "2.0"`, `simulation_id`, `report_id`, `sessions: [...]`. Chaque `InterviewSession` porte `interview_id = f"ivw_{session_index:02d}_{sha256_8}"` (où `sha256_8` hache `f"{simulation_id}|{report_id}|{session_index}|{subject.strip()}"`), `session_index` (`>= 1`), `subject`, `questions: List[str]`, `mode` (`"live"`, `"offline_archive"` ou `"replay_frozen"`), `recorded_at` (ISO 8601 UTC `"YYYY-MM-DDTHH:MM:SSZ"`) et `turns: List[InterviewTurn]`. Chaque `InterviewTurn` porte `turn_id = f"{interview_id}_t{turn_index:02d}"`, `turn_index` (`>= 1`), `agent_id: Optional[int]`, `persona_name: str`, `question: str`, `answer_text: str` et `key_quotes: List[InterviewQuoteSpan]` (`{"quote": str, "char_start": int, "char_end": int}`). *Raison* : satisfait conjointement `prd.md` `FR-03` (`turn_index`) et `architecture.md` §2.2 (`turn_id` `ivw_..._tXX`, offsets exacts) tout en respectant l'architecture en couches `models <- services` sans créer de service `InterviewLedger` redondant.
  2. **D2 — Invariant d'offset exact `answer_text[char_start:char_end] == quote` et préservation de `AgentInterview.key_quotes: List[str]`** : `AgentInterview.key_quotes` dans `zep_tools.py` reste `List[str]` pour ne casser ni `AgentInterview.to_text()` ni `test_simulation_interactive_lifecycle.py:652-655`, mais la découpe de phrases de `zep_tools.py` (`:1665-1681`, `:1822-1833`) est corrigée pour extraire par `re.finditer` des phrases complètes ponctuées FR/EN/CJK (`[.!?。！？]`) sans concaténer de `"。"` artificiel sur un texte latin ni laisser de préfixes Markdown `**`. Lors de la construction d'un `InterviewTurn`, `extract_quote_spans_from_answer(answer_text, candidate_quotes)` projette chaque extrait sur sa tranche exacte `(char_start, char_end)` dans `answer_text` (en retirant tout point terminal synthétique absent de `answer_text`, et en excluant les en-têtes techniques `【...】` / `[Mode archives...]`) ; `InterviewTurn.__post_init__` valide `0 <= q.char_start < q.char_end <= len(self.answer_text)` et `self.answer_text[q.char_start:q.char_end] == q.quote`. *Raison* : rend `100 %` des `key_quotes` vérifiables mécaniquement par tranche directe sur `answer_text`.
  3. **D3 — Résolution canonique de `agent_id` et `persona_name` dès `ZepToolsService` puis `AgentIdentityResolver`** : dans `ZepToolsService` (`zep_tools.py:1632-1637`, `:1765-1771`, `:1877-1886`, `:1911-1920`), l'identifiant entier du profil est lu via `agent.get("agent_id") if agent.get("agent_id") is not None else agent.get("user_id")` (repli `agent_idx`) et transmis à un nouveau champ optionnel `AgentInterview.agent_id: Optional[int] = None` (en dernière position avec défaut `None` pour compatibilité positionnelle) ; le nom brut est résolu dans l'ordre `realname -> name -> entity_name -> username -> f"Agent_{effective_agent_id}"`. Dans `ReportAgent._execute_tool_impl`, chaque répondant est ensuite canonisé via `AgentIdentityResolver` (`resolver.id_to_name.get(agent_id)` en priorité, sinon `resolver.resolve_name(raw_name) or raw_name`). *Raison* : corrige le défaut mesuré sur R8 où `21/21` répondants sortaient en `username` (`nathalie_962`) faute de clé `"realname"` dans `reddit_profiles.json`, tout en restant `100 %` compatible avec les fixtures de test existantes.
  4. **D4 — Honnêteté du mode d'exécution (`live`, `offline_archive`, `replay_frozen`)** : `InterviewResult` (`zep_tools.py:425, 440-446`) distingue le mode effectif : `"replay_frozen"` lorsque `replay_mode == "replay_frozen"` (`:1588`), `"live"` lorsque `SimulationRunner.interview_agents_batch` répond avec succès (`:1611-1692`), et `"offline_archive"` lorsque `SimulationRunner.interview_agents_batch` lève `ValueError` et bascule sur `_synthesize_offline_interviews` (`:1694-1705`). `InterviewResult.to_text()` émet `[[PROVENANCE:interview;mode:{effective_mode}]]` en autorisant ces trois valeurs. *Raison* : élimine la fausse certification `"mode": "live"` mesurée sur les `4` sessions hors-ligne de R8 (`NFR-5`).
  5. **D5 — Lecture rétrocompatible `v1` et tolérance aux pannes (`ReportInterviewsPayload.from_raw` / `load_from_file`)** : `ReportInterviewsPayload.from_raw` accepte sans exception : (a) un dictionnaire `v2` (`schema_version == "2.0"`), (b) une liste racine `v1` (`[{"subject", "agents", "mode", "citations"}, ...]`) ou une liste de dicts ad-hoc (`[{"interviewee", "transcript"}]` utilisé dans `test_story_015_1_claim_contracts.py:689`), et (c) l'enveloppe historique `{"report_id": ..., "interviews": [...]}`. Pour les entrées `v1` plates dépourvues de `answer_text` par répondant, la session est chargée avec `schema_version = "1.0"` et `turns = []` (en conservant `legacy_agents` et `legacy_citations` en lecture seule), tandis que les entrées ad-hoc `{"interviewee", "transcript"}` génèrent un tour attribué à `interviewee` pour préserver la compatibilité des tests unitaires. Un fichier absent, vide ou JSON invalide retourne `None` avec `logger.warning`, sans jamais interrompre l'appelant. *Raison* : respect strict de `NFR-1` sur tous les rapports antérieurs à l'Epic 015.
  6. **D6 — Ordonnancement dans `ReportAgent` et présence systématique de `report_interviews.json` v2** : dans `ReportAgent.generate_report`, `report_interviews.json` v2 est écrit de manière atomique (`tmp` + `os.replace`) **avant** l'appel à `audit_and_save_report_claims` (`report_agent.py:2730`), et ce **même si `0` session d'entretien n'a eu lieu** (`sessions: []`, clôturant ainsi l'ambiguïté différée de `story-014-1.md:230`). Dans `audit_and_save_report_claims`, le payload d'entretiens est résolu en priorité depuis la mémoire de l'instance (`self._interview_sessions` / `self._interview_records`) puis, à défaut, relu depuis `ReportManager.get_report_interviews_path(rep_id)` s'il existe sur disque, et transmis à `SimulationActionVerifier.verify_report_claim(..., report_interviews=interviews_payload)`. En outre, `extract_claims_from_content` reconnaît les références explicites `\b(ivw_[a-z0-9_]+)\b` et les force sous `ProvenanceRegime.INTERVIEW`. *Raison* : garantit la disponibilité des entretiens aussi bien pendant la génération en direct que lors d'un ré-audit hors-ligne d'un dossier de rapport existant.
  7. **D7 — Algorithme d'authentification des citations et déclarations d'entretien dans `SimulationActionVerifier`** : ajout de la méthode pure `SimulationActionVerifier.verify_interview_citation` et intégration dans `verify_report_claim(..., report_interviews: Optional[Any] = None)` (paramètre optionnel à `None` par défaut, préservant à `100 %` les appelants existants et les 11 chemins testés en `015-1`). Lorsque `report_interviews` est fourni et que `was_asserted_action is False` :
     - **Condition d'entrée** : la branche d'authentification d'entretien s'exécute (i) pour tout claim ayant `is_interview == True` (`ProvenanceRegime.INTERVIEW` ou référence explicite `ivw_*`), ainsi que (ii) pour tout claim `REPORTED_INTENTION` ou `ANALYST_INFERENCE` non validé contre `evidence_pack` qui comporte entre guillemets (`« … »`, `“…”`, `"…"`, `「…」`) un extrait substantiel (`>= 12` caractères et `>= 3` mots) retrouvé dans au moins un `turn.answer_text` de `report_interviews` (rattrapant les citations verbatim courtes `< 8` mots que `attribute_provenance_regime` avait laissées à `UNKNOWN`).
     - **Contrôle des références explicites `ivw_*` sans repli silencieux** : si `claim.evidence_refs` contient un ou plusieurs `ivw_*`, ceux-ci doivent exister dans `report_interviews` et appartenir au répondant résolu (`norm_claim_agent`) ; si un `ivw_*` appartient à un autre répondant → `CONTRADICTED` (`confidence = 0.0`, `evidence_refs = []`) ; s'il est introuvable → `UNSUPPORTED` (`evidence_refs = []`), sans repli sur d'autres tours.
     - **Contrôle des citations entre guillemets (alignement exact par tranche, zéro flou)** : chaque extrait entre guillemets (`>= 4` caractères en régime `INTERVIEW`, `>= 12` caractères / `>= 3` mots en rattrapage hors régime) est projeté sur `turn.answer_text` par normalisation typographique bijective (`’ -> '`, `\u00a0 -> ' '`, condensation d'espaces, insensibilité à la casse) retournant `(char_start, char_end)` exacts dans `turn.answer_text` :
       1. Si toutes les citations appartiennent à un ou plusieurs tours du répondant résolu (`own_turns`, ou d'au moins un tour répondant lorsque `claim.agent_name is None`) → `VerificationStatus.VERIFIED`, `provenance_regime = ProvenanceRegime.INTERVIEW`, `claim_kind = ClaimKind.REPORTED_INTENTION`, `origin = InformationOrigin.INFERENCE`, `asserted_as_action = False`, et ajout déterministe des `turn.turn_id` correspondants dans `evidence_refs` (après purge de tout `evt_*`).
       2. Si `claim.agent_name` est résolu vers `A`, qu'une citation est absente de `own_turns` (et absente des événements de `A` dans `evidence_pack`), mais présente en tranche exacte dans le `turn.answer_text` d'un **autre** répondant `B` → `VerificationStatus.CONTRADICTED`, `provenance_regime = ProvenanceRegime.INTERVIEW`, `claim_kind = ClaimKind.REPORTED_INTENTION`, `origin = InformationOrigin.INFERENCE`, `asserted_as_action = False`, `confidence = 0.0`, `evidence_refs = []`, avec limitation explicite citant `B` et `turn_b.turn_id`.
       3. Si une citation entre guillemets n'apparaît en tranche exacte chez aucun répondant (citation altérée lexicalement/numériquement ou forgée) → `VerificationStatus.UNSUPPORTED`, `provenance_regime = ProvenanceRegime.INTERVIEW`, `claim_kind = ClaimKind.REPORTED_INTENTION`, `origin = InformationOrigin.INFERENCE`, `asserted_as_action = False`, `confidence = min(claim.confidence, 0.5)`, `evidence_refs = []`, avec limitation distinguant une altération détectée (`SequenceMatcher >= 0.65` sur `own_turns`) d'une citation introuvable.
     - **Contrôle des déclarations `INTERVIEW` sans guillemets (discours indirect par 8-grammes)** : si `claim.text` ne contient pas de citation entre guillemets mais porte `ProvenanceRegime.INTERVIEW` :
       1. Si `claim.agent_name` partage au moins un 8-gramme normalisé avec son propre `turn.answer_text` (`own_turns`) → `VERIFIED` + `turn.turn_id` dans `evidence_refs` (`REPORTED_INTENTION`, `INFERENCE`, `asserted_as_action = False`).
       2. Si `claim.agent_name` ne partage aucun 8-gramme avec `own_turns` mais partage un 8-gramme avec le `turn.answer_text` d'un autre répondant `B` → `CONTRADICTED` (`confidence = 0.0`, `evidence_refs = []`, limitation nommant `B` et `turn_b.turn_id`).
       3. Sinon (ex. 8-gramme issu du résumé global `InterviewResult.summary` ou d'un artefact `v1` sans `turns`) → `UNSUPPORTED`, `evidence_refs = []`, limitation explicite d'absence de tour individuel rattachable.
     *Raison* : couvre l'intégralité de la table de vérité (bon répondant, mauvais répondant, altération entre guillemets, synthèse anonyme, référence `ivw_*` fautive, format `v1`) sans jamais promouvoir un entretien en action OASIS ni compter une affirmation contredite dans les `evidence_refs` de « Sources & Provenance ».
  8. **D8 — Non-blanchiment absolu des actions sociales affirmées (`was_asserted_action == True`)** : lorsqu'une affirmation a été extraite comme action sociale exécutée hors entretien (`was_asserted_action == True`, ex. *« Nathalie a publié un post affirmant "…" »*) et échoue à la réconciliation contre `evidence_pack` (`simulation_action_verifier.py:1342`), elle retourne immédiatement `UNSUPPORTED` avec `asserted_as_action = True` sans interroger `report_interviews`. *Raison* : empêche qu'une parole d'entretien post-run ne valide une fausse allégation de publication pendant la simulation.
  9. **D9 — Étanchéité des secrets (`NFR-4`) et alignement de `SimulationAuditService` / `EvidenceSnapshotService`** : `ReportInterviewsPayload` n'enregistre jamais le prompt système d'incarnation (`INTERVIEW_PROMPT_PREFIX`, `system_prompt` de `_synthesize_offline_interviews`), ni clé API, ni URL de passerelle ; un assainisseur `sanitize_interview_text` masque par sécurité tout motif accidentel `Bearer <token>`, `sk-[A-Za-z0-9_-]{16,}` ou URL privée contenant des identifiants. `SimulationAuditService.gather_audit_files` (`simulation_audit_service.py:346-358`) émet en repli l'enveloppe `v2` vide (`schema_version: "2.0"`, `simulation_id`, `report_id`, `sessions: []`) et inclut `report_interviews.json` dans `checksums.sha256`, tandis que `EvidenceSnapshotService.CANONICAL_AUDIT_FILES` (`evidence_snapshot_service.py:49-56`) demeure strictement inchangé. *Raison* : conformité simultanée à `NFR-4`, `013-2` (stabilité de l'empreinte de replay) et `014-1` AC8.

- [x] **Stratégie de tests identifiée** :
  - **Tests unitaires et d'intégration 100 % hermétiques** (aucun appel LLM réseau, aucun Neo4j, aucune dépendance à `backend/uploads/` ignoré par Git ; usage exclusif de fixtures mémoire, mocks déterministes et `tmp_path`).
  - **Nouveau fichier dédié** : `backend/tests/test_story_015_2_interview_ledger.py`, regroupant les 9 tests nommés dans `AC1` à `AC9` :
    - schéma `v2` complet (`interview_id`, `turn_id`, `turn_index`, `agent_id`, `persona_name`, `question`, `answer_text`, `key_quotes`) et vérification stricte `answer_text[char_start:char_end] == quote` ;
    - capture des 3 modes d'exécution (`live`, `offline_archive` sur `ValueError` OASIS, `replay_frozen`), jeton `[[PROVENANCE:interview;mode:...]]` et résolution canonique de `persona_name` / `agent_id` sur profils de type `reddit_profiles.json` (`name` + `user_id` sans `realname`) ;
    - lecture rétrocompatible `v1` (liste plate de type R8, enveloppe `{"interviews": []}`, format ad-hoc `{"interviewee", "transcript"}`) et dégradation sans exception sur fichier absent ou JSON corrompu ;
    - authentification `VERIFIED` d'une citation d'entretien du bon répondant (en régime `INTERVIEW` comme en rattrapage de citation courte `< 8` mots hors événement OASIS) avec attachement de `turn_id` (`ivw_..._tXX`) et maintien strict de `claim_kind == ClaimKind.REPORTED_INTENTION`, `origin == InformationOrigin.INFERENCE`, `asserted_as_action is False` ;
    - détection `CONTRADICTED` (`confidence == 0.0`, `evidence_refs == []`) lorsqu'une citation ou un 8-gramme d'entretien du répondant `B` est attribué au répondant `A`, ou lorsqu'un `ivw_*` explicite appartient à `B` ;
    - marquage `UNSUPPORTED` (`evidence_refs == []`) lorsqu'une citation entre guillemets est altérée lexicalement/numériquement (ex. `29 €` → `49 €`), fabriquée, issue uniquement du résumé global sans tour répondant, ou dotée d'un `ivw_*` inexistant ;
    - non-promotion absolue en `OBSERVED_SOCIAL_ACTION` et non-blanchiment d'une action sociale affirmée (`was_asserted_action == True`) échouant contre `evidence_pack` ;
    - ordonnancement de bout en bout dans `ReportAgent` (`report_interviews.json` v2 écrit avant `audit_and_save_report_claims`, écriture avec `sessions: []` quand `0` entretien, présence dans le ZIP et `checksums.sha256` de `SimulationAuditService`, invariance au bit près du SHA-256 de `EvidenceSnapshotService`) ;
    - étanchéité `NFR-4` (absence de prompt système interne, de clé API et d'URL privée dans `report_interviews.json`).
  - **Suites de non-régression ciblées puis globales** : `test_story_015_1_claim_contracts.py`, `test_simulation_interactive_lifecycle.py`, `test_report_claims_reconciliation.py`, `test_report_claim_epistemic.py`, `test_sources_provenance_honesty.py`, `test_silence_rule_reaches_prose.py`, `test_report_storage_isolation.py`, puis `cd backend && uv run pytest tests/ -q` et `pnpm --dir frontend test`.
  - **Contrôle de diagnostic en lecture seule** : relecture en mémoire du `report_interviews.json` `v1` et de `agent_log.jsonl` de R8 (si présents localement, sans aucune écriture dans `backend/uploads/`) validant la tolérance du lecteur `v1` et la reconstruction `v2` sur données réelles.

---

## Critères d'acceptation

| Réf. | Situation et comportement attendu | Vérification / preuve |
|---|---|---|
| **AC1** | **Schéma `report_interviews.json` v2 par session, tour et répondant avec offsets exacts** : Lorsqu'un ou plusieurs appels `interview_agents` sont exécutés pendant la rédaction d'un rapport, `report_interviews.json` est sérialisé avec `schema_version == "2.0"`, `simulation_id`, `report_id` et `sessions`, où chaque session expose `interview_id` (`^ivw_\d{2,}_[0-9a-f]{8}$`), `session_index`, `subject`, `questions`, `mode`, `recorded_at` (ISO 8601 UTC) et `turns`, et où chaque tour issu d'`interview_agents` expose `turn_id` (`^ivw_\d{2,}_[0-9a-f]{8}_t\d{2,}$`), `turn_index`, `agent_id` (`int`, `Optional[int]` uniquement pour les entrées historiques sans identifiant numérique), `persona_name` (`str` non vide), `question`, `answer_text` complet et `key_quotes` vérifiant pour `100 %` des éléments `0 <= char_start < char_end <= len(answer_text)` et `answer_text[char_start:char_end] == quote`. | `backend/tests/test_story_015_2_interview_ledger.py::test_report_interviews_v2_schema_and_exact_quote_offsets` |
| **AC2** | **Honnêteté du mode effectif (`live`, `offline_archive`, `replay_frozen`) et résolution canonique des répondants** : Sur un jeu de profils de format `reddit_profiles.json` portant `"user_id"` et `"name"` sans clé `"realname"` (accompagné d'`AgentIdentityResolver`), `ZepToolsService.interview_agents` et `ReportAgent._execute_tool_impl` enregistrent `agent_id == user_id` et le `persona_name` canonique (jamais le `username` technique `*_962`), préservent `AgentInterview.key_quotes` sous forme `List[str]`, et marquent `mode == "live"` si `interview_agents_batch` réussit, `mode == "offline_archive"` si `interview_agents_batch` lève `ValueError` (bascule hors-ligne) et `mode == "replay_frozen"` lorsque `replay_mode == "replay_frozen"` (à la fois dans `report_interviews.json` et dans le jeton `[[PROVENANCE:interview;mode:...]]`). | `backend/tests/test_story_015_2_interview_ledger.py::test_interview_modes_honesty_and_canonical_respondent_resolution` |
| **AC3** | **Compatibilité ascendante de lecture `v1` et tolérance aux fichiers absents ou corrompus (`NFR-1`)** : `ReportInterviewsPayload.from_raw` et `ReportInterviewsPayload.load_from_file` relisent sans lever d'exception : (a) une liste racine historique `v1` (`[{"subject", "agents", "mode", "citations"}]`), (b) une enveloppe de repli `{"report_id": "...", "interviews": []}`, et (c) une liste ad-hoc `[{"interviewee", "transcript"}]` ; face à un chemin inexistant, un fichier vide ou un JSON tronqué, `load_from_file` journalise un avertissement et retourne `None` sans exception non gérée. | `backend/tests/test_story_015_2_interview_ledger.py::test_v1_backward_compatibility_and_corrupted_file_resilience` |
| **AC4** | **Authentification `VERIFIED` d'une citation ou déclaration d'entretien appartenant au bon répondant** : Lorsqu'une affirmation attribuée au répondant `A` cite entre guillemets un extrait présent en tranche exacte (à la normalisation typographique `' / ’` et d'espaces près) dans `turn.answer_text` de `A` — que son régime initial soit `ProvenanceRegime.INTERVIEW` ou `UNKNOWN` sur une citation courte de `>= 12` caractères et `>= 3` mots absente d'`evidence_pack` —, ou paraphrase sans guillemets un 8-gramme présent dans `turn.answer_text` de `A` sous `ProvenanceRegime.INTERVIEW`, `SimulationActionVerifier.verify_report_claim` retourne `verification_status == VerificationStatus.VERIFIED`, ajoute `turn.turn_id` (`ivw_..._tXX`) dans `evidence_refs`, fixe `provenance_regime == ProvenanceRegime.INTERVIEW`, `claim_kind == ClaimKind.REPORTED_INTENTION`, `origin == InformationOrigin.INFERENCE` et maintient `asserted_as_action is False`. | `backend/tests/test_story_015_2_interview_ledger.py::test_authentic_respondent_interview_quote_verified_with_turn_id` |
| **AC5** | **Détection `CONTRADICTED` d'une citation ou référence d'entretien attribuée au mauvais répondant** : Lorsqu'une affirmation attribuée au répondant `A` cite un extrait (ou partage un 8-gramme d'entretien, ou référence explicitement un `turn_id` `ivw_*`) absent des réponses `answer_text` (et des événements `evidence_pack`) de `A`, mais appartenant à la réponse `turn_b.answer_text` d'un autre répondant `B`, `verify_report_claim` retourne `verification_status == VerificationStatus.CONTRADICTED`, `confidence == 0.0`, `evidence_refs == []`, `claim_kind == ClaimKind.REPORTED_INTENTION`, `provenance_regime == ProvenanceRegime.INTERVIEW`, `asserted_as_action is False`, et consigne dans `limitations` le nom canonique de `B` ainsi que `turn_b.turn_id`. | `backend/tests/test_story_015_2_interview_ledger.py::test_misattributed_interview_quote_to_wrong_respondent_contradicted` |
| **AC6** | **Rejet `UNSUPPORTED` d'une citation d'entretien altérée entre guillemets, fabriquée ou à `ivw_*` introuvable** : Lorsqu'une affirmation sous `ProvenanceRegime.INTERVIEW` (ou porteuse d'un `ivw_*` explicite) contient entre guillemets un extrait dont un mot, une négation ou un nombre a été modifié par rapport au `answer_text` du répondant, ou un extrait totalement absent de toutes les réponses d'entretien, ou référence un `ivw_*` inexistant, ou ne correspond qu'au résumé global hors `turns`, `verify_report_claim` retourne `verification_status == VerificationStatus.UNSUPPORTED`, `evidence_refs == []`, `asserted_as_action is False`, et ajoute un diagnostic explicite dans `limitations`. | `backend/tests/test_story_015_2_interview_ledger.py::test_altered_or_fabricated_interview_quote_marked_unsupported` |
| **AC7** | **Interdiction absolue de promotion en action OASIS et non-blanchiment d'une action affirmée non exécutée** : Aucune affirmation authentifiée via `report_interviews` ne sort de `verify_report_claim` avec `claim_kind == ClaimKind.OBSERVED_SOCIAL_ACTION`, `origin == InformationOrigin.SIMULATION` ou `asserted_as_action is True` ; inversement, une affirmation extraite hors entretien comme action sociale exécutée (`asserted_as_action is True`, ex. *« Claire a publié sur Twitter : "…" »*) qui n'a aucun événement exécuté correspondant dans `evidence_pack` reste `VerificationStatus.UNSUPPORTED` avec `asserted_as_action is True` et `evidence_refs == []`, même si `report_interviews` contient le même texte dans une réponse d'entretien de Claire. | `backend/tests/test_story_015_2_interview_ledger.py::test_interview_never_promoted_to_action_and_never_whitewashes_unverified_action` |
| **AC8** | **Persistance atomique avant audit des claims, cas `0` entretien et étanchéité `EvidenceSnapshotService` / `SimulationAuditService`** : Dans `ReportAgent`, `report_interviews.json` v2 est écrit atomiquement dans `reports/<report_id>/report_interviews.json` avant l'exécution de `audit_and_save_report_claims` (avec `sessions == []` lorsqu'aucun entretien n'a été appelé), permettant à `audit_and_save_report_claims` de peupler les `ivw_*` dans `report_claims.json` tant lors de la génération en direct que lors d'un ré-audit depuis le disque ; `SimulationAuditService.gather_audit_files` inclut ce `report_interviews.json` v2 et son condensat dans `checksums.sha256` ; et `EvidenceSnapshotService.CANONICAL_AUDIT_FILES` n'inclut pas `report_interviews.json` (empreinte `snapshot_hash` identique au bit près avant et après écriture d'entretiens). | `backend/tests/test_story_015_2_interview_ledger.py::test_persistence_order_zero_interview_envelope_and_snapshot_isolation` |
| **AC9** | **Zéro fuite de secret ni de prompt système interne dans `report_interviews.json` (`NFR-4`)** : `report_interviews.json` ne contient ni le préfixe système d'entretien (`INTERVIEW_PROMPT_PREFIX` ou `system_prompt` d'incarnation hors-ligne), ni jeton d'authentification (`Bearer …`, `sk-…`), ni URL interne de passerelle LLM avec identifiants, même lorsqu'une chaîne sensible est injectée dans une réponse simulée ou une question de test. | `backend/tests/test_story_015_2_interview_ledger.py::test_report_interviews_sanitizes_secrets_and_excludes_system_prompts` |
| **AC10** | **Non-régression globale, généricité stricte (`NFR-2`) et conformité outillage** : La suite backend complète passe à `100 %` (`>= 2 109` tests existants + les `9` nouveaux tests de `test_story_015_2_interview_ledger.py`, `0` échec, incluant `test_story_015_1_claim_contracts.py`, `test_simulation_interactive_lifecycle.py`, `test_report_claims_reconciliation.py`, `test_report_claim_epistemic.py` et `test_sources_provenance_honesty.py`), la suite Node frontend passe (`43` tests, `0` échec), `ruff check` sur tous les fichiers Python créés/modifiés renvoie `0` erreur, `validate_plans.py` renvoie `0`, et les fichiers applicatifs de `backend/app/` ne contiennent `0` nom d'entreprise, d'offre, de domaine, de tarif ou de persona issu de la fixture R8. | `cd backend && uv run pytest tests/ -q` ; `cd backend && uv run ruff check app/models/report_interviews.py app/services/zep_tools.py app/services/simulation_action_verifier.py app/services/report_agent.py app/services/simulation_audit_service.py tests/test_story_015_2_interview_ledger.py` ; `cd backend && uv run python scripts/validate_plans.py` ; `pnpm --dir frontend test` |

---

## Définition de fini

- [ ] `backend/app/models/report_interviews.py` : dataclasses `InterviewQuoteSpan`, `InterviewTurn`, `InterviewSession` et `ReportInterviewsPayload` (`schema_version: "2.0"`), identifiants déterministes `ivw_<NN>_<sha8>` et `ivw_<NN>_<sha8>_t<MM>`, extracteur de tranches exactes `answer_text[char_start:char_end] == quote`, assainissement anti-secret (`NFR-4`), écriture atomique sur disque et lecteur rétrocompatible `v1` / tolérant aux fichiers corrompus.
- [ ] `backend/app/services/zep_tools.py` : champ optionnel `agent_id: Optional[int] = None` sur `AgentInterview` sans casser `key_quotes: List[str]`, résolution de nom `realname -> name -> entity_name -> username`, distinction honnête du mode effectif (`live`, `offline_archive`, `replay_frozen`) dans `InterviewResult` et `to_text()`, et découpe propre des phrases FR/EN/CJK sans ajout de `"。"` artificiel sur texte latin.
- [ ] `backend/app/services/report_agent.py` : construction des `InterviewSession` v2 par tour et répondant canonisé via `AgentIdentityResolver` dans `_execute_tool_impl`, écriture atomique systématique de `report_interviews.json` v2 (y compris `sessions: []` si `0` entretien) **avant** `audit_and_save_report_claims`, détection des références explicites `ivw_*` dans `extract_claims_from_content`, et transmission de `report_interviews` à `SimulationActionVerifier.verify_report_claim`.
- [ ] `backend/app/services/simulation_action_verifier.py` : méthode `verify_interview_citation` et branche d'authentification d'entretien dans `verify_report_claim(..., report_interviews=None)` validant l'appartenance au répondant (`VERIFIED` + `turn_id` vs `CONTRADICTED` sur autre répondant vs `UNSUPPORTED` sur citation altérée/fabriquée/`ivw_*` invalide) sans jamais promouvoir en `OBSERVED_SOCIAL_ACTION` ni blanchir `was_asserted_action == True`.
- [ ] `backend/app/services/simulation_audit_service.py` : enveloppe de repli `report_interviews.json` alignée sur `schema_version: "2.0"` (`sessions: []`) dans `gather_audit_files`, avec maintien strict de `EvidenceSnapshotService.CANONICAL_AUDIT_FILES` inchangé.
- [ ] `backend/tests/test_story_015_2_interview_ledger.py` : `9` tests hermétiques nommés couvrant `AC1` à `AC9` verts.
- [ ] Non-régression complète validée : `cd backend && uv run pytest tests/ -q` (`>= 2 118` tests verts, `0` échec), `pnpm --dir frontend test` (`43` tests verts, `0` échec), et `ruff check` propre sur tous les fichiers touchés.
- [ ] Validation documentaire : `cd backend && uv run python scripts/validate_plans.py` retourne `0`.
- [ ] Contrôle de diagnostic en lecture seule exécuté en mémoire sur `report_934d3254004b` (si présent localement, sans écriture dans `backend/uploads/`) attestant la relecture `v1` sans erreur.
- [ ] Hors périmètre explicitement respecté : aucune modification de `report_quality_gate.py` ni du littéral de `report_agent.py:3211` (`015-3`), de `actor_classifier.py` / `cohort_coverage.py` / `api/report.py` (`015-4`), de `frontend/**` (`015-5`), de `brief_consistency.py` pour l'audit aval (`015-6`), de `EvidenceSnapshotService.CANONICAL_AUDIT_FILES`, ni de `backend/app/utils/report_benchmark_score.py` (`1.1.0`).

---

## Tâches

- [ ] 1. Créer le module `backend/app/models/report_interviews.py` implémentant `InterviewQuoteSpan`, `InterviewTurn`, `InterviewSession` et `ReportInterviewsPayload` (`schema_version: "2.0"`), le calcul déterministe des `interview_id` / `turn_id`, l'extracteur d'offsets exacts `extract_quote_spans_from_answer` (`answer_text[char_start:char_end] == quote`), l'assainissement anti-secret `sanitize_interview_text`, la sauvegarde atomique `save_to_file` et la relecture rétrocompatible `from_raw` / `load_from_file` (`v2`, liste plate `v1`, enveloppe `interviews`, format ad-hoc de test et JSON corrompu). *(AC1, AC3, AC9)*
- [ ] 2. Mettre à jour `backend/app/services/zep_tools.py` (`AgentInterview`, `InterviewResult`, `interview_agents`, `_synthesize_offline_interviews`, `_load_agent_profiles`, `_select_agents_for_interview`) pour conserver `agent_id: Optional[int] = None`, résoudre les noms via `realname -> name -> entity_name -> username`, tracer fidèlement le mode effectif (`live`, `offline_archive`, `replay_frozen`) jusque dans `to_text()`, et extraire des `key_quotes: List[str]` propres sur textes FR/EN/CJK sans ajout de `"。"` artificiel sur un texte latin ni fuite de prompt système. *(AC1, AC2, AC9)*
- [ ] 3. Étendre `backend/app/services/simulation_action_verifier.py` avec `verify_interview_citation` (projection bijective vers une tranche contiguë exacte de `turn.answer_text`, contrôle des 8-grammes par répondant, contrôle strict des `ivw_*` explicites sans repli silencieux) et câbler `verify_report_claim(..., report_interviews: Optional[Any] = None)` pour produire `VERIFIED` (+ `turn_id`), `CONTRADICTED` (mauvais répondant) ou `UNSUPPORTED` (altération entre guillemets, fabrication, résumé global non attribué) tout en interdisant `OBSERVED_SOCIAL_ACTION` et le blanchiment de `was_asserted_action == True`. *(AC4, AC5, AC6, AC7)*
- [ ] 4. Mettre à jour `backend/app/services/report_agent.py` (`__init__`, `generate_report`, `_execute_tool_impl`, `extract_claims_from_content`, `audit_and_save_report_claims`) pour enregistrer chaque session d'entretien en `InterviewSession` v2 avec `persona_name` canonisé par `AgentIdentityResolver`, détecter les références `ivw_*` à l'extraction, persister atomiquement `report_interviews.json` v2 avant `audit_and_save_report_claims` (y compris avec `sessions: []` en l'absence d'entretien), et transmettre `report_interviews` à `verify_report_claim` en direct comme en ré-audit depuis le disque. *(AC1, AC2, AC4, AC8)*
- [ ] 5. Aligner le repli de `SimulationAuditService.gather_audit_files` (`backend/app/services/simulation_audit_service.py:346-358`) sur l'enveloppe `v2` (`schema_version: "2.0"`, `simulation_id`, `report_id`, `sessions: []`) sans modifier `EvidenceSnapshotService.CANONICAL_AUDIT_FILES`. *(AC8, AC9)*
- [ ] 6. Créer la suite hermétique `backend/tests/test_story_015_2_interview_ledger.py` couvrant les `9` tests nommés dans `AC1` à `AC9` (schéma `v2` et offsets exacts, 3 modes et résolution `reddit_profiles.json`, rétrocompatibilité `v1` et résilience JSON corrompu, `VERIFIED` + `turn_id`, `CONTRADICTED` mauvais répondant, `UNSUPPORTED` citation altérée/fabriquée, non-promotion et non-blanchiment d'action, ordre de persistance + `0` entretien + isolation `EvidenceSnapshotService` + archive `SimulationAuditService`, étanchéité anti-secret `NFR-4`). *(AC1, AC2, AC3, AC4, AC5, AC6, AC7, AC8, AC9)*
- [ ] 7. Exécuter les suites ciblées puis la suite complète backend (`cd backend && uv run pytest tests/ -q`), la suite Node frontend (`pnpm --dir frontend test`), `ruff check`, `validate_plans.py` et un diagnostic non destructif en mémoire sur R8, puis mettre à jour la story et les agrégats de suivi pour passage en `review`. *(AC3, AC10)*

---

## Notes de développement

*(À renseigner lors de l'implémentation de la story.)*

---

## Revue

*(À renseigner lors de la revue contradictoire BMAD.)*

---

## Notes de complétion

*(À renseigner à la clôture de la story.)*
