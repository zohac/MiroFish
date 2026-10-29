---
id: "015-1"
epic: "015"
titre: "Préservation du provenance_regime, typage d'actions sans faux positifs et traçabilité du déclassement"
statut: done
auteur: "Antigravity & Équipe MiroFish"
format: "2"
---

# Story 015-1 — Préservation du `provenance_regime`, typage d'actions sans faux positifs et traçabilité du déclassement

**Lot A (socle d'intégrité du registre d'affirmations), priorité P0.** En tant que
relecteur d'un rapport analytique MiroFish — analyste métier, commanditaire ou auditeur
indépendant inspectant `report_claims.json`, la section « Sources & Provenance » et
l'archive d'audit —, je veux que chaque affirmation extraite conserve son régime de
provenance de bout en bout, que les actions sociales narrées soient distinguées des
intentions par frontières lexicales strictes sans faux positifs par sous-chaîne, que toute
action affirmée puis déclassée faute de preuve garde sa trace d'assertion d'action, et
qu'un événement OASIS ne valide une action que s'il appartient à l'acteur résolu et à la
famille d'interaction correspondante, afin que `0` affirmation ne perde son
`provenance_regime` lors de la vérification, que les bannières de provenance et les
compteurs d'actions affirmées vs vérifiées reflètent fidèlement la prose sans dilution par
sous-chaînes (`"va"`, `"compte"`), et qu'aucun événement technique passif ou étranger à
l'acteur ne certifie une action non exécutée.

Cette story répond aux exigences **FR-01** (préservation intégrale de `provenance_regime`
dans `verify_report_claim` et distinction actions vs intentions par frontières lexicales
`\b`) et **FR-02** (conservation explicite de `asserted_as_action = True` lors du
déclassement et contrôle d'appartenance de l'`event_id` au bon acteur résolu) du
[PRD de l'epic](prd.md), porte les exigences transverses **NFR-1** (zéro régression et
compatibilité ascendante `v1`), **NFR-2** (généricité absolue sans adhérence métier),
**NFR-3** (enrichissement KISS/DRY des modèles existants) et **NFR-5** (honnêteté
épistémique), et valide le critère de sortie **C1** de l'[epic 015](epic-015.md) tout en
préparant les fondations de **C3**, **C7** et **C8**.

Elle **dépend** des contrats posés par les Epics 011, 012 et 014 (`done` — modèle
`ReportClaim`, `ProvenanceRegime`, `SimulationActionVerifier`, `AgentIdentityResolver` et
règle de silence `014-3`). Elle **alimente** directement la story **015-2** (qui ne peut
authentifier les citations d'entretien par répondant que si `provenance_regime == INTERVIEW`
survit à `verify_report_claim`), la story **015-3** (qui s'appuie sur
`asserted_as_action` et `asserted_action_claims` / `verified_action_claims` pour fermer
l'angle mort « rapport conceptuel » dans `ReportQualityGate` et rendre la sous-section 3
de « Sources & Provenance » 100 % calculée), ainsi que la story **015-6** (qualification en
`replay_frozen` sur R8 et scénarios multi-domaines).

Elle rend possible : la survie garantie de `provenance_regime` sur les 11 sorties de
`verify_report_claim` ; le rétablissement automatique des bannières de provenance et du
décompte de la sous-section 7 de « Sources & Provenance » ; un booléen immuable
`asserted_as_action` et ses compteurs de registre (`asserted_action_claims`,
`verified_action_claims`) ; une séparation lexicale compilée `\b` couvrant le passé composé
comme le présent de narration sans pièges d'homographes français ; le rejet sans repli
silencieux des `evt_*` étrangers à l'acteur ; et l'exclusion des événements OASIS passifs
(`SIGN_UP`, `REFRESH`, `DO_NOTHING`, `SEARCH_POSTS`, `TREND`). Elle **refuse** : modifier
le schéma de `report_interviews.json` (`015-2`), modifier les seuils de `ReportQualityGate`,
`section_role="limitations"` ou le littéral résiduel de `report_agent.py:3137` (`015-3`),
toucher à la sélection des acteurs ou au filtre `[persona non admis]` (`015-4`), modifier
l'IHM Vue 3 (`015-5`), auditer les biographies aval (`015-6`), ou altérer la grille figée
`1.1.0` de `backend/app/utils/report_benchmark_score.py`.

---

## Définition de prêt

- [x] **Objectif compris et cadré** :

  **Le problème, mesuré sur le code et sur les artefacts R8 (`29 octobre 2026`).** L'inspection
  conjointe du code au `HEAD` et du run R8 (`sim_7a1b02b8c092`, rapport `report_934d3254004b`)
  établit quatre courts-circuits mécaniques dans la chaîne `extract_claims_from_content` →
  `SimulationActionVerifier.verify_report_claim` → `ReportClaimRegistry` :

  | Fait mesuré le 29 oct. 2026 sur R8 (`report_934d3254004b`) | Cause racine vérifiée ligne par ligne dans le code |
  |---|---|
  | **`165 / 165` claims (`100 %`)** ont `provenance_regime: null` dans `report_claims.json`, alors qu'à la sortie d'`extract_claims_from_content` **66 claims** portaient un régime résolu (`INTERVIEW`, `GRAPH` ou `EVENT`) et **99 claims** le régime `UNKNOWN` (attesté par la limitation `"Régime de provenance non établi (unknown)."` présente sur exactement 99 entrées). Conséquence en aval : `interview_claim_count == 0` (`report_agent.py:2708`), la bannière `report.provenance_banner` n'est jamais émise, `unknown_claim_count` monte artificiellement à `165` (`:2710`), et la sous-section 7 affiche `Affirmations portant un provenance_regime : 0` (`:3231`). | `ReportAgent.extract_claims_from_content` (`backend/app/services/report_agent.py:3584-3654`) renseigne bien `provenance_regime=regime`, mais `SimulationActionVerifier.verify_report_claim` (`backend/app/services/simulation_action_verifier.py:909-1340`) reconstruit un nouvel objet `ReportClaim(...)` à la main dans **chacun de ses 11 points de `return`** (`:950`, `:991`, `:1014`, `:1037`, `:1206`, `:1232`, `:1259`, `:1276`, `:1300`, `:1314`, `:1329`) sans jamais transmettre `provenance_regime`, qui retombe à sa valeur par défaut `None`. |
  | **`0` `OBSERVED_SOCIAL_ACTION`** finale contre **`83` `REPORTED_INTENTION`**, alors que `full_report.md` relate de nombreuses actions sociales concrètes au présent de narration (`:236` approbations et suivis, `:244` suivis et réponses, `:252` citations de posts). Sur les **25 claims hors entretien** captées par la branche d'intention, **`24 / 25` (`96 %`)** ne contiennent aucun verbe d'intention entier. | Dans `extract_claims_from_content` (`report_agent.py:3562`), `elif any(k in text_lower for k in ("va", "veut", "compte", ...))` est évalué **avant** les verbes d'action (`:3565`) par **sous-chaîne brute (`in`)** : `"va"` capture *valeur*, *invalide*, *éprouvable*, *travail*, *avant*, *avaient*, *observation* ; `"compte"` capture *compte tenu*, *rendre compte*, *son compte*. De plus, `:3565-3570` ne couvre que le passé composé FR et le prétérit EN, ignorant le présent de narration FR. |
  | **Perte de trace des actions déclassées.** L'unique action extraite sur R8 (`clm_18a0e445`) est déclassée en `REPORTED_INTENTION` par `:1232-1243` sans laisser d'indicateur booléen qu'une action exécutée avait été affirmée. | `verify_report_claim` écrase `claim_kind` vers `REPORTED_INTENTION` (`:1235`) ou `SPECULATIVE_PROJECTION` (`:953`, `:1017`, `:1033`) sans champ `asserted_as_action`, rendant indiscernables après coup une simple déclaration d'intention et une allégation d'action non prouvée. |
  | **Deux brèches de sur-validation dans `verify_report_claim` dès que l'extracteur produira davantage d'`OBSERVED_SOCIAL_ACTION`.** Dans l'`EvidencePack` de R8 (`953` événements chargés par `OasisLogReaderService.load_evidence_pack`), **`151` événements sont passifs/techniques** (`refresh`: `105`, `sign_up`: `36`, `search_posts`/`SEARCH_POSTS`: `6`, `trend`/`TREND`: `2`, `do_nothing`/`DO_NOTHING`: `2`) et **`506` sont des interactions non textuelles** (`LIKE_POST`: `311`, `LIKE_COMMENT`: `102`, `FOLLOW`: `92`, `REPOST`: `2`), tous marqués `is_action_executed=True`. | 1) Aux lignes `:1071-1108`, si `claim.evidence_refs` cite un `evt_*` appartenant à un **autre** acteur, `candidate_events` reste vide et `:1088` **se replie silencieusement** sur tous les événements de `claim.agent_name`, blanchissant la fausse référence. 2) Aux lignes `:1130-1199`, `is_pure_messaging` omet `CREATE_COMMENT` et `QUOTE_POST`, et le `else:` de `:1193` valide automatiquement (`has_valid_event = True`) **tout** événement non-messaging hors transaction : un simple `SIGN_UP`, `REFRESH` ou `FOLLOW` validerait n'importe quelle affirmation d'action non citée de cet agent. |

  **Ce que la story garantit, par sous-ensemble.**

  - **Contrat du modèle (`ReportClaim` & `ReportClaimRegistry`).** `ReportClaim` porte un
    booléen immuable `asserted_as_action: bool = False`, normalisé automatiquement à `True`
    pour toute `OBSERVED_SOCIAL_ACTION` hors régime `INTERVIEW` et préservé lors des
    reclassements ultérieurs. `ReportClaimRegistry` expose et sérialise
    `asserted_action_claims` et `verified_action_claims` sans altérer les clés existantes.
  - **Intégrité à la traversée de `verify_report_claim`.** Les 11 sorties de
    `SimulationActionVerifier.verify_report_claim` utilisent `dataclasses.replace(claim, ...)` :
    `provenance_regime` et `asserted_as_action` ne sont jamais perdus.
  - **Séparation lexicale `\b` sans pièges d'homographes.** `extract_claims_from_content`
    remplace les sous-chaînes brutes par des motifs compilés Unicode distinguant les
    auxiliaires/modaux prospectifs (`va + infinitif`, `compte + infinitif`, `veut`,
    `souhaite`, `prévoit`), les actions sociales accomplies au passé composé comme au
    présent de narration, et les négations pures d'action.
  - **Réconciliation stricte des événements OASIS.** Un `evt_*` explicite étranger à
    l'acteur résolu ou absent de l'`EvidencePack` échoue sans repli sur d'autres événements ;
    les événements techniques passifs ne valident jamais une action sociale ; les
    interactions non textuelles (`LIKE_*`, `FOLLOW`, `REPOST`) ne valident que les
    affirmations exprimant la même famille d'interaction.

  **Les invariants — ce que l'implémentation ne peut pas faire.**

  - **Jamais de ré-instanciation manuelle `ReportClaim(...)` dans `verify_report_claim`.**
    Toute branche de retour dérive de `dataclasses.replace(claim, ...)`.
  - **Jamais de `ClaimKind.OBSERVED_SOCIAL_ACTION` ni de `asserted_as_action=True` sous
    `ProvenanceRegime.INTERVIEW`.** Le sceau posé par la story `014-1` est absolu : un
    entretien tenu pendant la rédaction n'est jamais compté comme action sociale du run, ni
    à l'extraction ni à la vérification.
  - **Jamais de détection d'intention ou d'action par sous-chaîne brute (`in`).** Seules
    des expressions régulières compilées à frontières lexicales Unicode sont autorisées.
  - **Jamais de repli silencieux sur le balayage général des événements d'un acteur** quand
    `claim.evidence_refs` contient explicitement un ou plusieurs identifiants `evt_*` et
    qu'aucun d'eux n'appartient à l'acteur résolu dans l'`EvidencePack`.
  - **Jamais de validation d'une `OBSERVED_SOCIAL_ACTION` par un événement OASIS passif**
    (`DO_NOTHING`, `REFRESH`, `SIGN_UP`, `SEARCH_POSTS`, `SEARCH_USER`, `TREND`) ni par une
    interaction d'une autre famille sémantique.
  - **Jamais de modification de la graine SHA-256 de `compute_claim_id`**
    (`backend/app/models/report_claim.py:84-94`), afin de ne casser aucun identifiant
    `clm_*` des fixtures existantes (`r6_bundle`).
  - **Jamais de constante, nom d'entreprise, offre, tarif ou persona issu d'une fixture**
    dans `backend/app/**` (`NFR-2`).
  - **Toujours rétrocompatible en lecture (`NFR-1`)** : `ReportClaim.from_dict` accepte les
    JSON historiques dépourvus de la clé `asserted_as_action`.

- [x] **Documents consultés** :
  - `AGENTS.md` : §1 (état du projet), §2.8 (cycle de vie des stories `backlog → in-progress → review → done`), §2.10 (langue française), §5 (invariants).
  - `docs/decisions/0012-contrat-de-provenance-graphstore.md` : gel des 5 valeurs exclusives d'`InformationOrigin`.
  - `docs/plans/015-contrats-preuve-roles-et-ihm/prd.md` : §2.1 (constats R8 P0), §4 (`FR-01`, `FR-02`), §5 (`NFR-1`, `NFR-2`, `NFR-3`, `NFR-5`), §6 (`C1`).
  - `docs/plans/015-contrats-preuve-roles-et-ihm/architecture.md` : §1 (flux), §2.1 (contrat `ReportClaim` enrichi et règles d'intégrité), §3 (arbitrages KISS/DRY).
  - `docs/plans/015-contrats-preuve-roles-et-ihm/epic-015.md` : §2, §4 (`015-1`), §4.1 (graphe de dépendances), §5 (`C1`).
  - `docs/plans/014-integrite-preuves-redaction/story-014-1.md` et `story-014-3.md` : contrats établis sur `ProvenanceRegime.INTERVIEW`, bannières `report.provenance_banner` / `report.provenance_banner_unknown` et inhibition des personas silencieux.
  - `docs/deferred-work.md` : vérification des travaux différés de l'Epic 014.
  - `backend/scripts/validate_plans.py` : spec machine du format `"2"` (`:63-88`, `:217-291`).
  - `backend/app/models/report_claim.py` : `ClaimKind` (`:20-49`), `VerificationStatus` (`:52-81`), `compute_claim_id` (`:84-94`), `ReportClaim` (`:97-191`), `ReportClaimRegistry` (`:195-278`).
  - `backend/app/models/provenance_regime.py` : `ProvenanceRegime` (`:24-44`), `attribute_provenance_regime` (`:183-233`).
  - `backend/app/services/simulation_action_verifier.py` : `INTENTION_PATTERNS` (`:129-258`), `verify_simulated_citation` (`:812-906`), `verify_report_claim` (`:909-1340`, 11 retours vérifiés).
  - `backend/app/services/report_agent.py` : bannières de provenance (`:2699-2735`), sous-section 7 de `build_sources_provenance_section` (`:3217-3273`), `extract_claims_from_content` (`:3302-3657`), `audit_and_save_report_claims` (`:3715-3858`).
  - `backend/app/services/oasis_log_reader.py` : `OasisLogReaderService.load_evidence_pack` et chargement des `action_type` JSONL/SQLite (`:67-230`).
  - `backend/app/utils/report_benchmark_score.py` : `_score_claims` (`:182-255`, vérification de non-casse de la grille `1.1.0`).
  - Suites de tests de référence : `backend/tests/test_report_claim_epistemic.py`, `backend/tests/test_report_claims_reconciliation.py`, `backend/tests/test_silence_rule_reaches_prose.py`, `backend/tests/test_sources_provenance_honesty.py`.

- [x] **Dépendances résolues** :
  - **Stories amont livrées (`done`)** : `011-3` (`ReportClaim`, `SimulationActionVerifier`), `012-3` (`AgentIdentityResolver`, réconciliation sans sous-chaîne sur les noms), `014-1` (`ProvenanceRegime`, attribution par 8-grammes et bannières), `014-2` (sous-section 7 calculée dans `build_sources_provenance_section`), `014-3` (inhibition des personas silencieux dans `extract_claims_from_content`).
  - **Stories aval alimentées** : `015-2` (authentification par répondant des citations de régime `INTERVIEW`), `015-3` (`ReportQualityGate` sur `asserted_action_claims > 0` avec `verified_action_claims == 0` et sous-section 3 de « Sources & Provenance »), `015-6` (qualification R8 en `replay_frozen`).
  - **État du filet de tests mesuré à la rédaction (`29 octobre 2026`)** : **`2 099` tests backend hôte passants** (`1 warning`, `246,00 s` via `cd backend && uv run pytest tests/ -q`) et **`43` tests Node frontend passants** (`0 fail` via `pnpm --dir frontend test`).
  - **Dépendances techniques** : aucune nouvelle bibliothèque externe (modules standard `dataclasses`, `re`, `unicodedata` uniquement).

- [x] **Décisions d'ingénierie arrêtées avant code** :
  1. **D1 — Champ immuable `asserted_as_action: bool = False` sur `ReportClaim` et stabilité de `compute_claim_id`** : `ReportClaim` conserve `@dataclass(frozen=True)`. Dans `__post_init__`, si `self.provenance_regime == ProvenanceRegime.INTERVIEW`, `asserted_as_action` est forcé à `False` ; sinon, si `self.claim_kind == ClaimKind.OBSERVED_SOCIAL_ACTION`, `asserted_as_action` est forcé à `True` ; sinon `bool(self.asserted_as_action)` est préservé. `to_dict()` sérialise `"asserted_as_action": self.asserted_as_action`. `from_dict()` lit `bool(data["asserted_as_action"])` lorsque la clé existe et, sur les artefacts historiques `v1` où la clé est absente, applique le repli `(parsed_kind == ClaimKind.OBSERVED_SOCIAL_ACTION and parsed_regime != ProvenanceRegime.INTERVIEW)`. `compute_claim_id` reste inchangé. *Raison* : traçabilité complète du déclassement sans rompre l'immuabilité ni modifier un seul `claim_id` existant.
  2. **D2 — Compteurs d'actions affirmées vs vérifiées sur `ReportClaimRegistry`** : ajout des propriétés `asserted_action_claims: int` (`sum(1 for c in self.claims if c.asserted_as_action)`) et `verified_action_claims: int` (`sum(1 for c in self.claims if c.claim_kind == ClaimKind.OBSERVED_SOCIAL_ACTION and c.verification_status == VerificationStatus.VERIFIED)`), incluses dans `ReportClaimRegistry.to_dict()`. Les cinq clés agrégées existantes restent intactes. *Raison* : expose dès `report_claims.json` le contrat exact que consommeront `ReportQualityGate` et `build_sources_provenance_section` en story `015-3`, sans impacter les clés lues par `report_benchmark_score.py`.
  3. **D3 — Passage systématique par `dataclasses.replace(claim, ...)` sur les 11 sorties de `verify_report_claim`** : suppression des 11 appels `ReportClaim(...)` manuels dans `SimulationActionVerifier.verify_report_claim`. Une variable locale `was_asserted_action = (claim.provenance_regime != ProvenanceRegime.INTERVIEW) and (claim.asserted_as_action or claim.claim_kind == ClaimKind.OBSERVED_SOCIAL_ACTION)` est évaluée à l'entrée et transmise via `asserted_as_action=was_asserted_action` sur toutes les branches de déclassement ou de contradiction (silence C7 `:950`, contradiction entreprise QA-12 `:991`, hors horizon C8 `:1014`, métrique fantôme C8 `:1037`, anti-affabulation C4 `:1232`). *Raison* : rend impossible par construction toute perte présente ou future de `provenance_regime` et de `asserted_as_action`.
  4. **D4 — Sceau d'entretien (`ProvenanceRegime.INTERVIEW`) invariant de l'extraction à la vérification** : tant dans `extract_claims_from_content` que dans `verify_report_claim`, toute affirmation portant `ProvenanceRegime.INTERVIEW` se voit interdire `ClaimKind.OBSERVED_SOCIAL_ACTION` (rabattue en `ClaimKind.REPORTED_INTENTION` si un appelant direct lui avait donné `OBSERVED_SOCIAL_ACTION`, y compris sur la branche QA-12 `:991` qui maintient `VerificationStatus.CONTRADICTED` sur `ClaimKind.REPORTED_INTENTION`) et porte `asserted_as_action = False`. *Raison* : garantit l'invariant Epic 014 C1 sur tous les chemins d'appel, sans qu'une parole post-run puisse fausser le dénominateur d'actions OASIS.
  5. **D5 — Expressions régulières compilées à frontières de mots (`\b`) et règles de gouvernance modale / négation dans `extract_claims_from_content`** : suppression du `elif any(k in text_lower for k in ("va", "veut", "compte", ...))` (`report_agent.py:3562`) au profit de motifs compilés Unicode (`re.IGNORECASE | re.UNICODE`) :
     - **Intentions (`_INTENTION_CLAIM_RE`)** : semi-auxiliaire `aller` suivi d'un infinitif (`\b(?:va|vont)\s+(?:ne\s+pas\s+|pas\s+)?(?:se\s+|s['’]|y\s+|en\s+|le\s+|la\s+|les\s+|lui\s+|leur\s+)?[a-zàâäéèêëîïôöùûüç]{3,}(?:er|ir|re|oir)\b`) ; verbes prospectifs/volitifs entiers (`\b(?:veut|veulent|souhaite|souhaitent|prévoit|prévoient|envisage|envisagent|songe|songent|espère|espèrent|hésite|hésitent)\b`) ; `compter` suivi d'un infinitif (`\b(?:compte|comptent)\s+(?:ne\s+pas\s+|pas\s+)?(?:se\s+|s['’]|y\s+|en\s+)?[a-zàâäéèêëîïôöùûüç]{3,}(?:er|ir|re|oir)\b`, excluant *un/le/son compte*, *compte tenu*, *rendre compte*) ; locutions d'intention FR/EN (`\b(?:a\s+l['’]intention\s+de|ont\s+l['’]intention\s+de|plans?\s+to|intends?\s+to|wants?\s+to|is\s+going\s+to|are\s+going\s+to)\b`).
     - **Actions accomplies (`_ACTION_CLAIM_RE`)** : passé composé FR (`a/ont` + adverbe intercalé optionnel + participe passé d'action sociale ou transactionnelle : `publié`, `posté`, `tweeté`, `commenté`, `répondu`, `réagi`, `partagé`, `cité`, `republié`, `aimé`, `liké`, `suivi`, `souscrit`, `acheté`, `payé`, `commandé`, `résilié`, `voté`, `boycotté`, `déclaré`, `formulé`, `interrogé`, `critiqué`, `salué`, `souligné`, `manifesté`, `rejeté`) ; présent de narration sociale FR encadré contre les homographes (`publie|publient`, `poste|postent`, `tweete|tweetent`, `commente|commentent`, `répond|répondent`, `réagit|réagissent`, `partage|partagent`, `republie|republient`, `(?:le|la|les|l['’])\s+cite\b|\bcite\s+(?:le|la|les|ce|cet|cette|son|sa|ses)\s+(?:post|publication|message|tweet|commentaire|réponse)\b`, `\baime\s+(?:le|la|les|ce|cet|cette|son|sa|ses)\s+(?:post|publication|message|tweet|commentaire|réponse)\b`, `(?:le|la|les)\s+suit\b|\bsuit\s+(?:le\s+compte|la\s+page|[A-ZÀÂÄÉÈÊËÎÏÔÖÙÛÜÇ][\wÀ-ÿ'-]+)` en excluant `comme suit` et `s['’]en\s+suit`) ; et prétérit EN (`\b(?:posted|tweeted|commented|replied|reacted|shared|liked|followed|quoted|reposted|retweeted|subscribed|purchased|bought)\b`, jamais le mot nu `comment`).
     - **Gouvernance modale et négation** : (a) une action directement régie par un modal prospectif (*« va publier »*, *« compte souscrire »*, *« souhaite répondre »*, *« plans to post »*) est classée `REPORTED_INTENTION` (`asserted_as_action=False`) ; (b) une action accomplie introduisant un discours rapporté d'intention ou de refus (*« Julien a posté qu'il refuse de souscrire »*, *« Claire répond qu'elle va réfléchir »*) reste `OBSERVED_SOCIAL_ACTION` (`asserted_as_action=True`) ; (c) une négation pure d'action sans verbe d'action positif (*« Marc n'a pas souscrit »*, *« aucun des six profils n'a acheté »*, *« sans publier »*) n'est pas classée `OBSERVED_SOCIAL_ACTION` (`asserted_as_action=False`). *Raison* : élimine les 24/25 faux positifs de sous-chaîne, capte le présent de narration de R8, pare les homographes français (`comment`, `comme suit`, `compte`) et préserve `test_patch9_negation_not_treated_as_transaction_claim`.
  6. **D6 — Ordonnancement avec l'inhibition des personas silencieux (`Story 014-3`)** : dans `extract_claims_from_content`, `asserted_as_action` est capturé *après* l'application du sceau `ProvenanceRegime.INTERVIEW` (`:3592`) et *avant* l'inhibition `_agent_is_silent` (`:3612`). Ainsi, une action hors entretien attribuée à un persona silencieux garde `claim_kind = ClaimKind.REPORTED_INTENTION` et son marqueur `[inhibé — persona silencieux, aucune action observée]` tout en conservant `asserted_as_action = True` jusqu'à `verify_report_claim` (`CONTRADICTED`), tandis qu'une simple opinion/intention attribuée à un silencieux garde `asserted_as_action = False`. *Raison* : compatibilité stricte avec `test_silence_rule_reaches_prose.py` sans perdre le compte des actions alléguées à tort.
  7. **D7 — Propriété stricte des `evt_*` explicites sans repli silencieux** : dans `verify_report_claim`, on isole `explicit_ev_refs = [r for r in claim.evidence_refs if str(r).startswith("evt_")]`. Si `evidence_pack` est fourni et que `explicit_ev_refs` est non vide, seules ces références explicites sont examinées : si aucune d'elles n'existe avec `is_action_executed=True` dans l'`EvidencePack` sous l'identité canonique `norm_claim_agent`, `verify_report_claim` **n'exécute pas** le balayage de repli sur les autres événements de l'acteur, purge les `evt_*` invalides, ajoute une limitation motivée (identifiant introuvable ou rattaché à un autre acteur) et déclasse en `REPORTED_INTENTION` / `UNSUPPORTED` avec `asserted_as_action=True`. Le balayage des événements de l'acteur ne s'active que lorsque `explicit_ev_refs` est vide. *Raison* : ferme le contournement de `FR-02` où un `evt_*` étranger était masqué par un autre post du persona.
  8. **D8 — Partition stricte des `action_type` OASIS en quatre familles** : dans `verify_report_claim`, les `ev.action_type.upper()` sont classés en quatre ensembles disjoints :
     1. **Passifs / techniques** (`DO_NOTHING`, `REFRESH`, `SIGN_UP`, `SEARCH_POSTS`, `SEARCH_USER`, `TREND`) : ignorés systématiquement (`continue`), incapables de valider la moindre `OBSERVED_SOCIAL_ACTION`.
     2. **Messagerie textuelle** (`CREATE_POST`, `POST`, `TWEET`, `COMMENT`, `CREATE_COMMENT`, `QUOTE_POST`, `MESSAGE`) : soumis au contrôle de citation entre guillemets ou de recouvrement lexical significatif (`:1144-1192`), incapables de prouver `claims_transaction`.
     3. **Interactions sociales non textuelles** : approbation (`LIKE_POST`, `LIKE_COMMENT`, `UPVOTE`, `UPVOTE_POST`, `UPVOTE_COMMENT`), désapprobation (`DISLIKE_POST`, `DISLIKE_COMMENT`, `DOWNVOTE`, `DOWNVOTE_POST`, `DOWNVOTE_COMMENT`), suivi (`FOLLOW` vs `UNFOLLOW`, `MUTE`) et rediffusion (`REPOST`, `RETWEET`) — chacune ne valide une affirmation sans citation incompatible que si le texte de l'affirmation exprime explicitement la famille d'interaction correspondante, et ne valide jamais `claims_transaction`.
     4. **Transactions métier dédiées** (`SUBSCRIBE`, `BUY`, `PURCHASE`, `ORDER`, `PAY`) : seules habilitées à valider `claims_transaction == True`.
     *Raison* : élimine la faille du `else:` de `:1193` qui aurait laissé les `151` événements passifs ou les `506` interactions non textuelles de R8 certifier n'importe quelle allégation d'action.
  9. **D9 — Gel de `backend/app/utils/report_benchmark_score.py` (`1.1.0`)** : ce fichier n'est pas modifié par la story `015-1` ; la consommation de `asserted_as_action` par `ReportQualityGate` et la réécriture de la sous-section 3 de `build_sources_provenance_section` relèvent exclusivement de la story `015-3`. *Raison* : respect strict du découpage vertical de l'epic et préservation de la grille versionnée de l'Epic 013.

- [x] **Stratégie de tests identifiée** :
  - **Tests unitaires et d'intégration 100 % hermétiques** (aucun appel LLM, aucun accès Neo4j, aucune lecture de `backend/uploads/` ignoré par Git afin de garantir le passage en CI sur un clone vierge ; usage exclusif de fixtures en mémoire et `tmp_path`).
  - **Nouveau fichier dédié** : `backend/tests/test_story_015_1_claim_contracts.py`, regroupant les 9 fonctions de test nommées dans `AC1` à `AC9` :
    - balayage paramétré des 11 branches de retour de `verify_report_claim` × tous les membres de `ProvenanceRegime` + `None` ;
    - sérialisation / désérialisation `ReportClaim` et `ReportClaimRegistry`, compatibilité ascendante `v1` et invariance de `compute_claim_id` ;
    - matrice lexicale FR/EN contre les faux positifs par sous-chaîne (`travail`, `avaient`, `avant`, `valide`, `observation`, `compte tenu`, `son compte`, `rendre compte`) et les homographes (`comment`, `comme suit`) ;
    - séparation des actions au passé / présent de narration, des modaux prospectifs (`va + inf`, `compte + inf`, `souhaite`) et des négations pures d'action ;
    - conservation de `asserted_as_action=True` sur déclassement C4, silence C7, horizon C8 et métrique fantôme C8 ;
    - étanchéité du sceau `ProvenanceRegime.INTERVIEW` (y compris sur QA-12) ;
    - rejet sans repli silencieux d'un `evt_*` étranger à l'acteur ou absent du pack ;
    - rejet des événements OASIS passifs (`SIGN_UP`, `REFRESH`, `DO_NOTHING`, `SEARCH_POSTS`, `TREND`) et correspondance stricte par famille d'interaction (`FOLLOW`, `LIKE_POST`, `REPOST`) ;
    - assemblage de bout en bout via `ReportAgent.audit_and_save_report_claims`, écriture des bannières de provenance et vérification de la sous-section 7 de `build_sources_provenance_section`.
  - **Suites de non-régression ciblées puis globales** : `test_report_claim_epistemic.py`, `test_report_claims_reconciliation.py`, `test_silence_rule_reaches_prose.py`, `test_sources_provenance_honesty.py`, `test_report_benchmark_score.py`, puis `cd backend && uv run pytest tests/ -q` et `pnpm --dir frontend test`.
  - **Contrôle de diagnostic en lecture seule** : vérification ponctuelle en répertoire temporaire sur une copie mémoire de la prose et des observations R8 (si présentes localement, sans écriture dans `backend/uploads/`) confirmant la disparition de `provenance_regime: null` et des faux positifs `"va"`/`"compte"`.

---

## Critères d'acceptation

| Réf. | Situation et comportement attendu | Vérification / preuve |
|---|---|---|
| **AC1** | **Préservation intégrale de `provenance_regime` sur les 11 chemins de retour de `verify_report_claim`** : Pour chacune des 11 branches de sortie de `SimulationActionVerifier.verify_report_claim` (silence C7, contradiction de fait d'entreprise QA-12, hors horizon C8, métrique fantôme C8, action vérifiée, action déclassée C4, intention vérifiée, intention non vérifiée, barrière C5 source fictive, fait source standard, autre type analytique) et pour chaque valeur de `ProvenanceRegime` (`EVENT`, `INTERVIEW`, `GRAPH`, `DOCUMENT`, `UNKNOWN`) ainsi que `None`, le `ReportClaim` retourné conserve exactement `verified.provenance_regime == claim.provenance_regime`. | `backend/tests/test_story_015_1_claim_contracts.py::test_verify_report_claim_preserves_provenance_regime_all_11_paths` |
| **AC2** | **Modèle `ReportClaim.asserted_as_action`, compteurs `ReportClaimRegistry` et compatibilité ascendante `v1`** : `ReportClaim` expose `asserted_as_action: bool = False`, forcé à `True` lorsque `claim_kind == ClaimKind.OBSERVED_SOCIAL_ACTION` (hors régime `INTERVIEW`) et sérialisé dans `to_dict()` ; `ReportClaim.from_dict()` relit un dictionnaire historique dépourvu de la clé `asserted_as_action` en déduisant `True` pour `OBSERVED_SOCIAL_ACTION` (hors `INTERVIEW`) et `False` pour les autres types, tout en conservant `compute_claim_id` strictement identique au SHA-256 antérieur ; `ReportClaimRegistry.to_dict()` expose `asserted_action_claims` et `verified_action_claims` égaux aux comptes exacts des claims correspondants. | `backend/tests/test_story_015_1_claim_contracts.py::test_report_claim_asserted_as_action_roundtrip_and_v1_compat` |
| **AC3** | **Élimination des faux positifs d'intention par sous-chaîne (`"va"`, `"compte"`) et des homographes français** : Lors de l'appel à `ReportAgent.extract_claims_from_content` sur des phrases contenant `"va"` ou `"compte"` à l'intérieur d'un mot ou d'un syntagme nominal (*« Le travail mené avant la réunion valide l'observation qu'elles avaient faite »*, *« Compte tenu de son compte social, elle rend compte de son analyse »*, *« Elle explique comment la grille se lit comme suit »*), aucune de ces phrases n'est classée `ClaimKind.REPORTED_INTENTION` ni `ClaimKind.OBSERVED_SOCIAL_ACTION` (`claim_kind == ClaimKind.ANALYST_INFERENCE` et `asserted_as_action is False`). | `backend/tests/test_story_015_1_claim_contracts.py::test_extract_claims_eliminates_substring_and_homograph_false_positives` |
| **AC4** | **Séparation des actions au passé / présent de narration, des modaux prospectifs et des négations pures** : `ReportAgent.extract_claims_from_content` classe en `ClaimKind.OBSERVED_SOCIAL_ACTION` (`asserted_as_action is True`) les actions accomplies au passé composé comme au présent de narration (*« Claire aime le post d'Hélène et la suit »*, *« Marc lui répond et cite sa publication »*, *« Julien a posté qu'il refuse de souscrire »*), classe en `ClaimKind.REPORTED_INTENTION` (`asserted_as_action is False`) les actions régies par un modal prospectif (*« Claire va publier un retour »*, *« Marc compte souscrire demain »*, *« Julien souhaite répondre »*), et ne classe pas en `ClaimKind.OBSERVED_SOCIAL_ACTION` une négation pure d'action (*« Aucun des six profils n'a souscrit à la formule »*, `asserted_as_action is False`). | `backend/tests/test_story_015_1_claim_contracts.py::test_extract_claims_separates_narrated_actions_modals_and_negations` |
| **AC5** | **Persistance de `asserted_as_action=True` après déclassement ou contradiction hors entretien** : Lorsqu'une affirmation extraite avec `claim_kind == ClaimKind.OBSERVED_SOCIAL_ACTION` (hors régime `INTERVIEW`) est déclassée faute de preuve dans `verify_report_claim` (`ClaimKind.REPORTED_INTENTION`, `VerificationStatus.UNSUPPORTED`) ou reclassée par la règle de silence C7 (`CONTRADICTED`), la garde d'horizon temporel C8 (`SPECULATIVE_PROJECTION`) ou la garde de métrique fantôme C8, le `ReportClaim` retourné conserve `asserted_as_action is True`, incrémente `registry.asserted_action_claims` de `1` et laisse `registry.verified_action_claims` à `0`. | `backend/tests/test_story_015_1_claim_contracts.py::test_downgraded_and_contradicted_actions_preserve_asserted_as_action` |
| **AC6** | **Étanchéité du régime `ProvenanceRegime.INTERVIEW` face aux verbes d'action** : Une affirmation portant `provenance_regime == ProvenanceRegime.INTERVIEW` (attribuée par 8-grammes dans `extract_claims_from_content` ou passée directement à `verify_report_claim`, y compris sur la branche de contradiction QA-12) ne sort jamais avec `claim_kind == ClaimKind.OBSERVED_SOCIAL_ACTION` et porte systématiquement `asserted_as_action is False`. | `backend/tests/test_story_015_1_claim_contracts.py::test_interview_regime_never_becomes_action_or_asserted_action` |
| **AC7** | **Rejet strict d'un `event_id` appartenant à un autre acteur ou introuvable, sans repli silencieux** : Lorsqu'une affirmation `OBSERVED_SOCIAL_ACTION` attribuée à l'acteur `A` référence explicitement dans `evidence_refs` un identifiant `evt_*` appartenant à l'acteur `B` (ou absent de l'`EvidencePack`), `verify_report_claim` retourne `VerificationStatus.UNSUPPORTED`, `ClaimKind.REPORTED_INTENTION`, `asserted_as_action is True`, retire l'`evt_*` fautif de `evidence_refs` et consigne le motif dans `limitations`, même si l'`EvidencePack` contient par ailleurs un autre événement valide de l'acteur `A` sur le même thème. | `backend/tests/test_story_015_1_claim_contracts.py::test_explicit_foreign_or_missing_event_id_rejected_without_fallback` |
| **AC8** | **Filtrage des événements OASIS passifs et concordance par famille d'interaction** : Dans `verify_report_claim`, un événement technique passif (`DO_NOTHING`, `REFRESH`, `SIGN_UP`, `SEARCH_POSTS`, `SEARCH_USER`, `TREND`) ne valide aucune `OBSERVED_SOCIAL_ACTION` ; une interaction non textuelle (`LIKE_POST`, `LIKE_COMMENT`, `FOLLOW`, `REPOST`) valide une affirmation sans citation contradictoire de cet acteur uniquement lorsque le verbe de l'affirmation appartient à la même famille d'interaction (un événement `FOLLOW` valide *« Claire suit Hélène »* en `VERIFIED` avec son `evt_*`, mais dégrade *« Claire publie une analyse détaillée »* en `UNSUPPORTED`). | `backend/tests/test_story_015_1_claim_contracts.py::test_oasis_passive_events_rejected_and_interaction_families_matched` |
| **AC9** | **Restauration de bout en bout des compteurs de provenance et bannières dans `ReportAgent`** : Sur un rapport assemblé mêlant observations d'outils (`interview_agents`, `query_simulation_events`, `insight_forge`) et prose narrative au présent, `audit_and_save_report_claims` écrit un `report_claims.json` ayant `0` entrée avec `provenance_regime: null`, l'assemblage insère la bannière `report.provenance_banner` avec le compte exact des affirmations `interview`, et `build_sources_provenance_section` affiche dans sa sous-section 7 `Affirmations portant un provenance_regime : <total_claims>`. | `backend/tests/test_story_015_1_claim_contracts.py::test_end_to_end_audit_preserves_regimes_and_triggers_banner` |
| **AC10** | **Non-régression globale, généricité stricte et conformité outillage** : La suite backend complète passe à 100 % (`>= 2 099` tests existants + nouveaux tests de `test_story_015_1_claim_contracts.py`, `0` échec, incluant `test_silence_rule_reaches_prose.py`, `test_report_claims_reconciliation.py`, `test_report_claim_epistemic.py`, `test_sources_provenance_honesty.py` et `test_report_benchmark_score.py`), la suite Node frontend passe (`43` tests, `0` échec), `ruff check` sur les fichiers Python touchés renvoie `0` alerte, `validate_plans.py` renvoie `0`, et les fichiers applicatifs modifiés ne contiennent `0` nom propre ou terme métier issu de la fixture R8. | `cd backend && uv run pytest tests/ -q` ; `cd backend && uv run ruff check app/models/report_claim.py app/services/simulation_action_verifier.py app/services/report_agent.py tests/test_story_015_1_claim_contracts.py` ; `cd backend && uv run python scripts/validate_plans.py` ; `pnpm --dir frontend test` |

---

## Définition de fini

- [x] `backend/app/models/report_claim.py` : champ `asserted_as_action: bool = False` sur `ReportClaim`, normalisation sous `__post_init__`, rétrocompatibilité `from_dict` pour les JSON `v1`, invariance de `compute_claim_id`, et compteurs `asserted_action_claims` / `verified_action_claims` sur `ReportClaimRegistry`.
- [x] `backend/app/services/simulation_action_verifier.py` : remplacement des 11 retours manuels de `verify_report_claim` par `dataclasses.replace(claim, ...)`, propagation de `asserted_as_action`, respect du sceau `ProvenanceRegime.INTERVIEW`, contrôle strict de propriété des `evt_*` explicites sans repli silencieux, et partition des `action_type` OASIS en 4 familles excluant les événements passifs.
- [x] `backend/app/services/report_agent.py` : motifs compilés Unicode à frontières de mots (`_INTENTION_CLAIM_RE`, `_ACTION_CLAIM_RE`) dans `extract_claims_from_content` couvrant le présent de narration, la gouvernance modale et les négations sans faux positifs `"va"`/`"compte"` ni homographes, avec capture d'`asserted_as_action` avant l'inhibition des personas silencieux.
- [x] `backend/tests/test_story_015_1_claim_contracts.py` : 9 tests hermétiques nommés couvrant `AC1` à `AC9` verts.
- [x] Non-régression complète validée : `pytest tests/ -q` (`2 108` tests verts, `0` échec), `pnpm --dir frontend test` (`43` tests verts, `0` échec), et `ruff check` propre sur tous les fichiers touchés.
- [x] Validation de la structure de planification : `cd backend && uv run python scripts/validate_plans.py` retourne `0`.
- [x] Vérification de diagnostic en lecture seule (en mémoire, sans modifier `backend/uploads/`) attestant `0` `provenance_regime: null` après extraction / audit.
- [x] Hors périmètre explicitement respecté : aucune modification de `report_interviews.json` (`015-2`), de `report_quality_gate.py` ni du littéral de `report_agent.py:3137` (`015-3`), de `actor_classifier.py` / `cohort_coverage.py` / `api/report.py` (`015-4`), de `frontend/**` (`015-5`), ni de `backend/app/utils/report_benchmark_score.py` (`v1.1.0`).

---

## Tâches

- [x] 1. Enrichir `ReportClaim` (`asserted_as_action: bool = False`, normalisation dans `__post_init__`, sérialisation `to_dict`, repli `v1` dans `from_dict` sans toucher à `compute_claim_id`) et exposer `asserted_action_claims` ainsi que `verified_action_claims` dans `ReportClaimRegistry` (`backend/app/models/report_claim.py`). *(AC2, AC5, AC6)*
- [x] 2. Refactorer les 11 points de retour de `SimulationActionVerifier.verify_report_claim` vers `dataclasses.replace(claim, ...)` afin de préserver intégralement `provenance_regime`, propager `asserted_as_action` lors de tout déclassement ou contradiction hors entretien, et garantir le sceau `ProvenanceRegime.INTERVIEW` y compris sur la branche QA-12 (`backend/app/services/simulation_action_verifier.py`). *(AC1, AC5, AC6)*
- [x] 3. Durcir la réconciliation d'`OBSERVED_SOCIAL_ACTION` dans `SimulationActionVerifier.verify_report_claim` : bloquer tout repli sur d'autres événements lorsqu'un `evt_*` explicite est introuvable ou appartient à un autre acteur résolu, ignorer les événements OASIS passifs (`DO_NOTHING`, `REFRESH`, `SIGN_UP`, `SEARCH_POSTS`, `SEARCH_USER`, `TREND`), inclure `CREATE_COMMENT` et `QUOTE_POST` dans la messagerie textuelle, et vérifier la famille d'interaction pour les événements non textuels (`LIKE_*`, `DISLIKE_*`, `FOLLOW`, `REPOST`) (`backend/app/services/simulation_action_verifier.py`). *(AC7, AC8)*
- [x] 4. Remplacer la détection par sous-chaînes de `ReportAgent.extract_claims_from_content` par des expressions régulières compilées Unicode à frontières de mots (`_INTENTION_CLAIM_RE`, `_ACTION_CLAIM_RE`) gérant le passé composé et le présent de narration, les garde-fous d'homographes français (`comment`, `comme suit`, `compte`), la gouvernance modale, les négations pures et la capture d'`asserted_as_action` avant l'inhibition des personas silencieux (`backend/app/services/report_agent.py`). *(AC3, AC4, AC5, AC6, AC9)*
- [x] 5. Créer la suite hermétique `backend/tests/test_story_015_1_claim_contracts.py` implémentant les 9 tests nommés dans `AC1` à `AC9` (11 retours × régimes, roundtrip `v1`, sous-chaînes et homographes, actions narrées / modaux / négations, persistance d'`asserted_as_action`, sceau `INTERVIEW`, `evt_*` étranger sans repli, familles d'`action_type` OASIS, et assemblage de bout en bout avec bannières et sous-section 7). *(AC1, AC2, AC3, AC4, AC5, AC6, AC7, AC8, AC9)*
- [x] 6. Exécuter les suites ciblées puis la suite complète backend (`pytest tests/ -q`), la suite frontend (`pnpm --dir frontend test`), `ruff check`, `validate_plans.py`, ainsi qu'un contrôle de diagnostic non destructif, puis mettre à jour la story et les agrégats pour passage en `review`. *(AC9, AC10)*

---

## Notes de développement

- **Implémentation de `asserted_as_action`** : Déclaré avec valeur par défaut `False` dans `ReportClaim`. La normalisation dans `__post_init__` force `False` pour tout régime `INTERVIEW` (invariant absolu Epic 014/015), force `True` pour toute `OBSERVED_SOCIAL_ACTION` hors entretien, et préserve la valeur explicite dans les autres cas. Dans `ReportClaim.from_dict()`, le repli sur les dictionnaires historiques `v1` (où la clé est absente) déduit `True` si et seulement si `parsed_kind == ClaimKind.OBSERVED_SOCIAL_ACTION and parsed_regime != ProvenanceRegime.INTERVIEW`.
- **Remplacement systématique par `replace(claim, ...)`** : L'ensemble des 11 branches de sortie de `SimulationActionVerifier.verify_report_claim` dérive désormais de `dataclasses.replace`, éliminant définitivement le bug d'écrasement de `provenance_regime` constaté sur R8 (où 100 % des claims perdaient leur régime).
- **Partition des familles d'événements OASIS** :
  - Passifs : `DO_NOTHING`, `REFRESH`, `SIGN_UP`, `SEARCH_POSTS`, `SEARCH_USER`, `TREND` ignorés systématiquement.
  - Messagerie textuelle : étendue pour inclure `CREATE_COMMENT` et `QUOTE_POST`.
  - Interactions sociales non textuelles : vérification de l'adéquation sémantique de l'affirmation (`LIKE_*` / `UPVOTE` -> approbation, `FOLLOW` -> suivi, `REPOST` -> rediffusion).
  - Transactions : seules autorisées à valider `claims_transaction`.
- **Expressions régulières compilées `\b`** : `_INTENTION_CLAIM_RE`, `_MODAL_ACTION_RE`, `_ACTION_CLAIM_RE` et `_PURE_NEGATION_ACTION_RE`. Les homographes courants en français (`comme suit`, `s'en suit`, `compte`, `comment`) sont neutralisés par lookbehind et motifs contextuels.
- **Vérification de diagnostic R8 en mémoire** : Exécutée sur le texte de `full_report.md` de R8 sans modifier le disque (`backend/uploads/` préservé). Constat : 0 claim avec `provenance_regime: null`, 174 inférences d'analyste, 14 intentions, 6 actions observées (au lieu de 0) et 0 faux positif sur `"va"`/`"compte"`.

---

## Revue

### Review Findings

- [x] [Review][Patch] Utiliser des expressions régulières compilées \b au lieu de sous-chaînes brutes pour les familles d'interaction OASIS [backend/app/services/simulation_action_verifier.py:1189-1200]
- [x] [Review][Patch] Dissocier UNFOLLOW et MUTE de FOLLOW dans follow_event_types [backend/app/services/simulation_action_verifier.py:1185,1273]
- [x] [Review][Patch] Fermer la faille fail-open else: pour les événements OASIS inconnus [backend/app/services/simulation_action_verifier.py:1284-1288]
- [x] [Review][Patch] Exiger claims_transaction pour les événements transaction_event_types [backend/app/services/simulation_action_verifier.py:1281-1283]
- [x] [Review][Patch] Prioriser has_action_match sur has_modal_action lors d'actions accomplies introduisant un modal [backend/app/services/report_agent.py:3636-3642]
- [x] [Review][Patch] Couvrir les négations au présent de narration dans _PURE_NEGATION_ACTION_RE [backend/app/services/report_agent.py:110-123]
- [x] [Review][Patch] Ajouter les formes plurielles de narration (citent, aiment, suivent) dans _ACTION_CLAIM_RE [backend/app/services/report_agent.py:98-102]
- [x] [Review][Patch] Étendre les particules de négation (plus, rien, guère) et verbes sociaux dans _PURE_NEGATION_ACTION_RE [backend/app/services/report_agent.py:110-123]
- [x] [Review][Patch] Ajouter le contrôle de l'insertion de la bannière dans le test d'assemblage e2e [backend/tests/test_story_015_1_claim_contracts.py:586-637]
- [x] [Review][Patch] Relâcher le seuil de longueur de verbe dans _INTENTION_CLAIM_RE pour les verbes courts (dire, voir, lire, agir) [backend/app/services/report_agent.py:61,67]
- [x] [Review][Patch] Neutraliser le lookbehind 'qui suit' et l'insensibilité à la casse sur [A-Z] dans _ACTION_CLAIM_RE [backend/app/services/report_agent.py:102]
- [x] [Review][Patch] Préserver les références non-evt_* (sources documentaires, entretiens) dans new_refs de verify_report_claim [backend/app/services/simulation_action_verifier.py:1293]
- [x] [Review][Patch] Forcer claim_kind = REPORTED_INTENTION si provenance_regime == INTERVIEW dans ReportClaim.__post_init__ [backend/app/models/report_claim.py:161-163]
- [x] [Review][Defer] Résolution et validation du ciblage (target user / post ID) des événements sociaux non-textuels (LIKE_POST, FOLLOW) [backend/app/services/simulation_action_verifier.py:1267] — deferred: architecture préexistante d'OASIS, hors du périmètre strict de Story 015-1 qui se concentre sur les 4 familles d'interactions et l'exclusion des passifs.

#### Rejected

- Rejet `low` : Narration anglaise au présent dans `_ACTION_CLAIM_RE` (BH-14) — le corpus analytique et les récits de simulation en anglais emploient quasi-exclusivement le prétérit (`posted`, `tweeted`, `subscribed`), déjà couvert.
- Rejet `low` : Assertion redondante sur `provenance_regime` étranger (BH-17) — la préservation du régime sur les 11 sorties est déjà prouvée de façon exhaustive et paramétrée dans `test_verify_report_claim_preserves_provenance_regime_on_all_11_returns`.
- Rejet de conformité : Propositions de réécriture de la spec elle-même formulées hors code — rejetées en application des règles de triage BMad.

---

## Notes de complétion

- **Livrables réalisés** :
  - `backend/app/models/report_claim.py` : enrichissement avec `asserted_as_action`, normalisation et compteurs de registre `asserted_action_claims` et `verified_action_claims`.
  - `backend/app/services/simulation_action_verifier.py` : refactorisation intégrale des 11 points de sortie de `verify_report_claim` via `dataclasses.replace`, propriété stricte d'`event_id` sans repli silencieux, étanchéité du sceau `INTERVIEW`, partitionnement en 4 familles d'`action_type`, et validation par regex compilées Unicode `\b` sans sous-chaînes brutes.
  - `backend/app/services/report_agent.py` : motifs compilés Unicode `\b`, gestion du présent de narration, formes plurielles, pronominaux, modaux prospectifs, négations pures et capture de `asserted_as_action` avant l'inhibition des silencieux.
  - `backend/tests/test_story_015_1_claim_contracts.py` : 10 tests unitaires et d'intégration hermétiques couvrant l'ensemble des critères `AC1` à `AC9` et les cas limites issus de la revue BMAD.
- **Conformité aux exigences** : `FR-01` et `FR-02` satisfaits, critères `C1` de l'epic 015 validé, critères `NFR-1`, `NFR-2`, `NFR-3` et `NFR-5` rigoureusement respectés.
- **Divergences du plan** : Aucune divergence substantielle ; 13 correctifs appliqués suite à la revue contradictoire BMAD à 4 couches.
- **Filet de tests** : 2 109 tests backend passants (+10 tests nouveaux, 0 fail), 43 tests frontend Node passants (0 fail), `ruff check` 100 % propre.
