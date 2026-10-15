---
id: "008-3"
epic: "008"
titre: "Génération de personas, simulations et rapports en français (prompts LLM et banc de validation)"
statut: in-progress
auteur: "Équipe MiroFish"
format: "2"
---

# Story 008-3 — Génération de personas, simulations et rapports en français (prompts LLM et banc de validation)

En tant qu'utilisateur ayant créé une simulation en **français**, je veux que les agents OASIS génèrent des profils et des interventions en français et que le `ReportAgent` rédige son analyse finale en français, sans qu'une opération asynchrone ou un redémarrage de processus fasse perdre cette langue, afin de bénéficier d'un parcours linguistiquement cohérent de la configuration jusqu'au rapport.

Cette story réalise **FR-4**, **FR-5**, **NFR-2** et **NFR-3** de l'[Epic 008](epic-008.md), et son critère **C4** dans le [PRD](prd.md). Elle s'appuie sur la traduction de l'IHM en [008-1](story-008-1.md) et sa propagation HTTP en [008-2](story-008-2.md). **Les sorties LLM sont nouvelles** : les documents d'origine, faits sourcés, citations et rapports déjà générés ne sont jamais traduits ou modifiés rétroactivement.

> **Frontière avec l'Epic 011.** 008-3 garantit la **langue** et la continuité du contexte linguistique du pipeline. La véracité des affirmations, la disponibilité d'`interview_agents`, la traçabilité des événements, le contrat `ReportClaim` et la barrière générale de publication `ReportQualityGate` relèvent de l'[Epic 011](../011-preuve-simulation-et-fiabilite-rapport/epic-011.md). Ne pas recréer ces mécanismes ici.

---

## Définition de prêt

- [x] **Contrat identifié** : le contexte `fr` doit traverser la création de simulation, la préparation, la génération de profils/configuration, le lancement OASIS (Twitter, Reddit, parallèle), puis la planification, les sections et la conversation du rapport.
- [x] **Références examinées** : [PRD](prd.md) (§2–§5), [architecture](architecture.md) (§2), [epic](epic-008.md), [008-1](story-008-1.md), [008-2](story-008-2.md), [AGENTS.md](../../../AGENTS.md) (§2.1, §2.2, §2.8, §2.9, §2.10) et [Epic 011](../011-preuve-simulation-et-fiabilite-rapport/epic-011.md).
- [x] **Acquis du dépôt relevés (15 octobre 2026)** :
  - `locales/languages.json` contient `fr.llmInstruction = "Veuillez répondre en français."` ; `backend/app/utils/locale.py` gère `normalize_locale()`, `get_locale()`, `set_locale()`, `get_language_instruction()`.
  - Les API de préparation (`backend/app/api/simulation.py`) et de rapport (`backend/app/api/report.py`) capturent déjà la locale HTTP puis appellent `set_locale()` dans leurs threads. Le pool de `OasisProfileGenerator` propage déjà la locale aux workers.
  - `ontology_generator.py`, `oasis_profile_generator.py`, `simulation_config_generator.py` et `report_agent.py` ajoutent déjà une consigne linguistique à **certains** prompts système. Leur **efficacité** sur le modèle et les chemins d'échec reste à prouver.
  - `SimulationRunner.start_simulation()` lance trois scripts OASIS possibles via `subprocess.Popen(env=os.environ.copy())` ; **aucun contexte de langue explicite n'est actuellement injecté au processus fils**.
  - `SimulationManager.create_simulation()` ne fixe pas actuellement la locale dans `SimulationState` ; un changement de langue entre création, préparation, démarrage et rapport risque donc de mélanger les langues.
  - Des prompts métier et replis statiques demeurent en chinois/anglais (dont `report_agent.py` et le fallback persona). Il ne suffit pas d'ajouter une consigne française à la fin d'un prompt pour prouver que le modèle la respectera.
- [x] **Architecture de principe retenue** : un seul contexte de langue **canonique et persistant par simulation** ; pas d'état global par utilisateur et pas de nouvel orchestrateur. Les demandes HTTP servent à choisir la langue au moment de la création, pas à réécrire silencieusement celle d'une simulation existante.
- [ ] **Préconditions d'exécution** : 008-2 clôturée conformément à son DoD (encore in-progress) ; CI de référence verte (run 38807586884) ; stack Docker + modèle configuré accessibles pour l'épreuve comportementale réelle (non vérifiés) ; corpus de validation sans secrets à identifier.
- [x] **Plan de qualification défini** : tests hermétiques à tous les points de frontière et banc Docker réel mesurant séparément personas, actions des plateformes et rapport, avec conservation des artefacts/échecs et retour d'expérience BMAD.

---

### Critères d'acceptation

| Réf. | Comportement attendu | Vérification / preuve |
|---|---|---|
| **AC1 — Langue figée par simulation** | Quand `POST /api/simulation/create` reçoit `Accept-Language: fr` ou `fr-FR`, la simulation créée porte `locale = "fr"` de façon persistante. La préparation, le lancement, la génération du rapport et la reprise après redémarrage reprennent cette valeur. `en` et `zh` sont acceptés ; simulation historique sans champ ou valeur inconnue → `zh`. | Tests API/modèle de sérialisation, rechargement depuis `state.json`, compatibilité ascendante ; une simulation `fr` et une `en` simultanées n'interfèrent pas. |
| **AC2 — Propagation jusqu'aux workers et processus** | La locale effective d'une simulation est conservée lors du passage Flask → thread de préparation → pool de personas → runner/monitor → subprocess OASIS (`parallel`, `twitter`, `reddit`) → job `ReportAgent`. Aucune lecture tardive d'un header absent dans un worker et aucune fuite de `thread_local` entre tâches. | Captures des appels/paramètres et de l'environnement ou de la configuration des fils ; tests d'entrelacement `fr/en/zh` et de restauration du contexte après échec. |
| **AC3 — Prompts LLM cohérents** | Tous les prompts qui produisent du **texte destiné aux utilisateurs ou agents** portent la consigne de langue sélectionnée : ontologie descriptive, profils individuels/collectifs, configuration narrative, sujets/posts initiaux, consignes d'action OASIS, plan, sections et chat du rapport. La règle « données non fiables ≠ instructions » demeure prioritaire. | Tests de capture des messages LLM, y compris retries, générations groupées et voies dégradées. Vérifier qu'aucun appel de génération ciblé n'échappe à la politique. |
| **AC4 — Contrats techniques invariants** | Les clés JSON, types d'entités en `PascalCase`, relations `UPPER_SNAKE_CASE`, identifiants de plateforme, champs CSV Twitter/JSON Reddit et enums comme `gender`, `stance` et `poster_type` restent compatibles. Seuls les champs narratifs sont localisés. | Tests de contrats OASIS et de schéma/config, validation du parsing, sauvegarde/relecture et zéro modification des identifiants techniques. |
| **AC5 — Personas en français** | Avec un scénario francophone et le modèle de référence, les bios, personas, motivations, styles, centres d'intérêt et autres champs narratifs générés sont en français naturel pour toutes les personnes/organisations éligibles. Le fallback après échec LLM respecte lui aussi la langue et conserve les données d'entité d'origine. | Tests hermétiques des champs, du fallback et des deux exports ; contrôle comportemental des profils réellement générés, pas seulement de la présence de `llmInstruction` dans le prompt. |
| **AC6 — Activité OASIS en français** | Les nouvelles publications, commentaires, réponses et actions **textuelles générées par les agents** sur Twitter, Reddit et leur exécution parallèle suivent la langue de la simulation. Journaux techniques, noms propres, citations de sources et textes d'entrée restent inchangés. | Banc sur les trois chemins de lancement ; inspection des `actions.jsonl` et export des messages produits, y compris après reprise. Un nom français dans une bio ne suffit pas à réussir ce critère. |
| **AC7 — Rapport en français et structurément intact** | L'outline (titre, résumé, sections), les sections complètes, la synthèse et les réponses du `ReportAgent` sont générés en français. Les citations sont reproduites fidèlement dans leur langue d'origine ; une éventuelle traduction est annoncée, jamais substituée à l'original. Les marqueurs ReACT, références, noms d'outils et schémas restent parseables. | Tests des appels `PLAN` / `SECTION` / `CHAT`, export/relecture du rapport et banc de génération réelle. Ne pas déclarer un rapport conforme sur la seule langue de son titre. |
| **AC8 — Validation reproductible et non-régression** | Les tests existants `zh/en` et les nouveaux tests passent en CI. Le banc réel couvre au minimum un scénario francophone déterministe sur trois voies (profil, activité, rapport), avec taux de conformité documenté, échantillons inspectables, anomalies et limitations déclarées. | `ruff`, `pytest`, parité des locales, validation des plans, build frontend, Docker ; rapport de qualification versionné. Aucune preuve de CI ou d'inférence réelle ne peut être inventée. |

**Critère de sortie empirique (C4)** : sur un lot de qualification documenté, atteindre **100 %** de champs narratifs structurés en français dans les profils vérifiés, **100 %** de titres/résumés/sections de rapport vérifiés en français et **au moins 95 %** de messages générés en français sur chaque plateforme, en excluant explicitement les citations verbatim, noms propres, codes, URLs, messages vides et données préexistantes. Publier **N contrôlés / N éligibles** pour chaque dénominateur, conserver tous les écarts et ne pas déclarer `done` si le modèle de référence ne satisfait pas ces seuils. Ce seuil mesure le comportement LLM, pas une garantie universelle pour tous les modèles.

---

## Définition de fini

- [ ] La simulation possède une `locale` canonique persistée et backward-compatible, fixée à la création, relue par toutes les étapes et préservée après redémarrage.
- [ ] Les appels LLM ciblés (ontologie descriptive, personas, config, posts OASIS, rapport et chat) ont une politique de sortie linguistique explicite, testée et sans altération des données sources.
- [ ] Les modes OASIS `twitter`, `reddit` et `parallel` reçoivent la langue **effective** de la simulation ; isolement correct entre simulations parallèles.
- [ ] Les champs techniques et schémas OASIS/JSON/CSV, la provenance et les protections contre l'injection ne régressent pas.
- [ ] Les replis et erreurs (LLM indisponible, JSON invalide, persona de base, locale absente) produisent un résultat explicite et sûr, sans fausse conformité.
- [ ] Les tests unitaires et d'intégration hermétiques couvrent **AC1 à AC7** (au moins les parcours nominaux, invalides, concurrents et régénérations).
- [ ] La compilation Vite, la parité i18n, `uv run python scripts/validate_plans.py`, `uv run ruff check .` et `uv run pytest tests/ -q` passent en local/Docker de référence et dans la CI GitHub.
- [ ] Un **banc Docker sur LLM réel** est exécuté et son rapport de qualification versionné confirme **AC5–AC8** avec compteurs, traces et seuils ; les échecs ne sont pas masqués.
- [ ] Revue contradictoire BMAD des contrats, de la conception, des risques OASIS/LLM et des preuves effectuée, findings résolus ou explicitement acceptés.
- [ ] Statut passé selon **`backlog → in-progress → review → done`**, suivi de l'epic et notes de complétion actualisés avec commit(s) et verdict.

---

## Tâches

- [x] **T1 — Cartographier et instrumenter le flux de langue de bout en bout**
  - Construire une matrice des producteurs LLM et des frontières de contexte : `backend/app/api/{simulation,report}.py`, `simulation_manager.py`, `oasis_profile_generator.py`, `simulation_config_generator.py`, `ontology_generator.py`, `simulation_runner.py`, `backend/scripts/run_{parallel,twitter,reddit}_simulation.py`, `report_agent.py`.
  - Inventorier les prompts réels de chaque appel et chemin alternatif (retries, fallback, batch, conversation, outil). Distinguer résultat destiné à l'utilisateur, champ technique, donnée passive, source externe et journal brut.
  - Établir une CI de référence et des fixtures sans LLM vivant ; consigner les hypothèses sur les hooks réellement exposés par OASIS.

- [x] **T2 — Définir et persister la locale canonique d'une simulation**
  - Introduire un seul champ `SimulationState.locale`, normalisé avec `normalize_locale()`, transmis par `SimulationManager.create_simulation()` et `POST /api/simulation/create` ; maintenir le comportement des créations programmatiques antérieures (défaut `zh`).
  - Ajouter le champ à `to_dict()` / chargement depuis `state.json` sans casser les données historiques. Le résoudre depuis **la simulation**, non depuis le navigateur ayant envoyé la dernière requête.
  - Contrat immuable par simulation : changer la langue du sélecteur après création **ne traduit pas** une simulation existante ; refaire une simulation pour générer dans une autre langue. Éviter une migration de masse.
  - Ajouter des tests de normalisation, sérialisation, cas manquant/corrompu, persistance et deux simulations concurrentes.

- [x] **T3 — Sécuriser la propagation asynchrone**
  - Au début des tâches `prepare` et `report`, appliquer la locale persistée, et restaurer l'ancien contexte dans un `finally` ou un petit contexte dédié réutilisable. Faire de même pour les pools de profils ; vérifier les chemins de reprise/régénération.
  - Transmettre la locale explicitement au runner puis **à chaque processus OASIS** via un argument/configuration/environnement strictement contrôlé ; lire cette valeur dans les scripts avant toute génération susceptible de l'utiliser. Un `get_locale()` dans le seul processus Flask n'est **pas** suffisant.
  - Tester les trois modes et l'entrelacement `fr/en/zh` sans dépendance à l'ordre des tests ; vérifier les relances forcées et le mode persistant après la fin des rounds.

- [ ] **T4 — Appliquer la langue aux producteurs LLM et aux replis**
  - Réutiliser `get_language_instruction()` et, si utile, un **petit helper de composition** pour les champs narratifs ; pas de nouvelle interface sans deux implémentations réelles, ni de remplacement global des prompts chinois qui modifierait la logique métier.
  - Vérifier concrètement `OasisProfileGenerator` : prompt système, profils individuels/collectifs, validation du JSON et champs `bio`/`persona`, personnalisation des replis sans inventer de faits.
  - Vérifier `SimulationConfigGenerator` et `OntologyGenerator` : descriptions, justification narrative, thèmes, événements et posts initiaux dans la langue visée ; **identifiants, types, enums et clés en anglais**.
  - Étudier les points d'injection d'OASIS (profils, descriptions d'agents et instructions système) pour faire respecter le français aux **actions** des agents. Si la bibliothèque ne permet pas d'imposer la langue, le signaler avec preuve et proposer la plus petite adaptation viable, sans fausse promesse.

- [ ] **T5 — Garantir la rédaction et la conversation du rapport**
  - Vérifier les quatre chemins `ReportAgent` : `PLAN_SYSTEM_PROMPT`, `SECTION_SYSTEM_PROMPT_TEMPLATE`, finalisation forcée ReACT, `CHAT_SYSTEM_PROMPT_TEMPLATE` ; auditer les éventuels autres appels.
  - Garantir titres, plans, résumés, analyses et réponses en français, sans traduire les faits du graphe ni les citations ; préserver les marqueurs de parsing, les noms d'outils, le suffixe anti-injection et les références de provenance.
  - Éviter les rapports « fr » sur simulation « en » à cause du header de la requête de génération ; couvrir les réouvertures et la génération différée.

- [ ] **T6 — Couvrir les contrats avec des tests hermétiques**
  - Ajouter des tests unitaires du contexte de langue (API → persistance → worker → processus) et de composition des prompts avec un client LLM simulé enregistrant les messages.
  - Simuler la génération de profils, de configuration et de rapport sous `fr`, `en`, `zh` ; comparer les valeurs stables des clés et champs structurés.
  - Simuler une réponse LLM invalide, un timeout, un fallback, un redémarrage, une demande de régénération et deux tâches concurrentes : aucun mélange de locales.
  - Préférer les assertions de contrat et de comportements à des tests qui recherchent simplement la sous-chaîne « français » dans le prompt.

- [ ] **T7 — Produire la preuve comportementale sous Docker**
  - Exécuter un scénario de simulation **francophone reproductible**, avec petite cohorte de personnages réellement éligibles, pour les trois chemins de génération (personas, actions Twitter/Reddit, rapport), à partir d'un jeu de documents fixé et versionné sans secret.
  - Capturer la configuration (identité/version du modèle, paramètres, scénario, plateforme, nombre de tours, date, commit), les prompts sans secrets, les sorties brutes, les exclusions justifiées et les comptages. Le comportement LLM n'est pas supposé déterministe ; ne pas promettre une reproductibilité textuelle bit à bit.
  - Contrôler manuellement un échantillon vérifiable, y compris les erreurs ambiguës de détection automatique de la langue ; publier un rapport `docs/plans/008-support-langue-francaise/rapport-qualification-008-3.md` avec **GO / NO-GO**, et comparer un scénario témoin en `en` et `zh`.
  - Si le modèle de référence ou Docker est indisponible, consigner `NON EXÉCUTÉ` et garder la story ouverte.

- [ ] **T8 — Revue BMAD et clôture documentaire**
  - Revue contradictoire à quatre couches : **contrat**, **architecture**, **résilience/sécurité**, **tests et preuves réelles** ; prioriser et corriger les findings.
  - Exécuter la CI, vérifier les seuils empiriques, mettre à jour `epic-008.md`, `docs/sprint-status.yaml`, notes de complétion, DoD et commit(s) ; ne passer `done` qu'après `review` et clôture vérifiée de tous les critères.

---

## Notes de développement

### État établi lors du cadrage (15 octobre 2026)

Les mécanismes **déjà présents** ne doivent pas être dupliqués :

| Point de passage | État actuel | Écart à résoudre dans 008-3 |
|---|---|---|
| `locale.py` et `languages.json` | Support `fr` et instruction LLM disponible | Politique de portée et absence de fuite entre workers |
| `simulation.py`, `report.py` | Locale capturée dans certains threads à partir du HTTP | Langue fixée et récupérée **depuis l'objet simulation** |
| `OasisProfileGenerator` | `get_language_instruction()`, propagation aux threads du pool | Qualité réelle des textes et repli localisé |
| `SimulationConfigGenerator` / `OntologyGenerator` | Consignes ajoutées à des prompts système | Audit exhaustif des chemins, stabilité du JSON et des codes |
| `SimulationRunner` | Lance des scripts enfants, environnement copié, locale pour monitor | Locale transmise et appliquée **dans le processus enfant** |
| `ReportAgent` | Instruction ajoutée à planification, sections et chat | Cohérence effective du rapport, régénération sans changement de langue |

**Choix de conception** : la langue des contenus générés est un **attribut de l'exécution**, pas l'état courant de l'IHM. Ne pas créer de second registre de traduction ni de proxy de traduction universel. La normalisation des locales reste dans `backend/app/utils/locale.py` ; les services composent leurs prompts sans dépendre de Flask. Toute métadonnée persistée suit le même mécanisme que `SimulationState`. L'ajout d'un champ au modèle exige un test d'anciens fichiers sans ce champ.

**Protection des faits et invariants** : les descriptions et sorties narratives sont localisables ; `event_id`, `source_entity_uuid`, rôles techniques, variables de template, labels de schéma, citations verbatim, références et données factuelles ne le sont pas. Une traduction d'une citation éventuelle est toujours explicitement étiquetée et accompagnée de son original. Ne jamais confondre langue française et nationalité du personnage : préserver les identités et noms fournis.

**Limitation fondamentale** : OASIS est une bibliothèque externe. Une instruction dans un profil ne constitue pas une preuve que les actions de tous les agents seront en français. L'acceptation AC6 repose sur des traces du moteur réellement exécuté ; toute limite constatée est un finding bloquant ou un arbitrage documenté de l'epic, pas un succès implicite.

**Architecture, qualité et sécurité** : respecter `api → services → utils`, la règle d'une interface seulement avec ≥ 2 implémentations, le principe DRY (une seule résolution de locale), KISS (pas d'usine à prompts) et la règle de tests hermétiques (§2.2). Pas de secrets ni de contenu médical/personnel réel dans les corpus versionnés. Préserver les protections NFR-5 des prompts du rapport et les règles métier des Epics 007/009/010/011.

### Commandes de qualification prévues (non exécutées à ce stade)

```bash
# Validations déterministes (hôte ou conteneur selon l'environnement)
pnpm --dir frontend test
pnpm --dir frontend build
cd backend && uv run ruff check . && uv run python scripts/validate_plans.py
cd backend && uv run pytest tests/ -q

# Environnement de référence
docker compose up -d
docker compose ps
docker compose run --rm backend uv run pytest tests/ -q
# Le banc 008-3 à ajouter sera exécuté depuis l'environnement de référence.
docker compose down   # ne jamais ajouter -v sans raison explicite
```

---

## Revue

**En cours — statut `in-progress`.** À l'implémentation, consigner ici les findings et correctifs de chaque couche BMAD :

1. **Contrat** : AC1–AC8, distinction IHM / contenu LLM et frontière avec l'Epic 011.
2. **Architecture** : immutabilité de la locale d'une simulation, absence de fuite cross-thread/cross-process, contrats d'export JSON/CSV stables.
3. **Résilience/sécurité** : données passives protégées, retries, fallback, erreurs, cas historiques, citations originales et changements de langue a posteriori.
4. **Preuves** : tests hermétiques, CI verte, mesures comportementales réelles avec dénominateurs, exclusions justifiées et seuils atteints.

Ne jamais cocher le DoD ni attribuer de verdict GO tant qu'aucune mesure réelle n'a été conduite. La validation empirique des sorties OASIS, des profils et du rapport demeure bloquante pour `done`.

---

## Notes de complétion

**Implémentation initiale en cours sur `local-first`** : `SimulationState.locale` persistée, contexte `use_locale` restauré, propagation aux sous-processus OASIS et aides linguistiques des profils, tests hermétiques. Les épreuves sur un modèle LLM réel et la validation Docker ne sont pas encore réalisées. Lors de la clôture, consigner les fichiers changés, références des commits, tests exécutés et résultats, matrice AC1–AC8, modèle et environnement du banc réel, constats de revue et éventuelles limites acceptées.
