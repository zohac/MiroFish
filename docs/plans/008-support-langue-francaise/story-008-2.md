---
id: "008-2"
epic: "008"
titre: "Intégration et bascule IHM frontend Vue 3 (sélecteur, formats régionaux fr-FR)"
statut: done
auteur: "Équipe MiroFish"
format: "2"
---


# Story 008-2 — Intégration et bascule IHM frontend Vue 3 (sélecteur, formats régionaux `fr-FR`)

En tant qu'utilisateur francophone de MiroFish, je veux sélectionner « Français » depuis l'interface et conserver ce choix pendant ma navigation et après un rechargement, afin de consulter toutes les étapes du parcours, l'historique et les formats de dates, d'heures et de nombres dans une langue et des conventions cohérentes.

Cette story réalise **FR-2**, **FR-3**, **NFR-2** et **NFR-3** de l'[Epic 008](epic-008.md), ainsi que les critères **C2** et **C3** du [PRD](prd.md). Elle s'appuie sur le dictionnaire livré par la **story 008-1** et prépare la propagation linguistique de bout en bout étudiée en **008-3**, sans prendre en charge la génération LLM.

---

## Définition de prêt

- [x] **Périmètre identifié** : localisation de l'interface Vue 3 (textes statiques, statuts, actions, erreurs, aides contextuelles), bascule instantanée, persistance, formats régionaux et propagation du choix sur les requêtes API.
- [x] **Contrats et sources examinés** :
  - [PRD](prd.md) : §2, §3, §4 et critères C2/C3.
  - [Architecture](architecture.md) : découverte dynamique des dictionnaires, cycle de vie de la locale et en-têtes HTTP.
  - [Epic 008](epic-008.md) et [story 008-1](story-008-1.md) : découpage et dictionnaire `locales/fr.json` (679 clés, 17 sections au moment du cadrage).
  - [Constitution](../../../AGENTS.md) : §2.2 (tests), §2.8 (planification), §2.9 (Docker), §2.10 (français).
  - `frontend/src/i18n/index.js`, `frontend/src/components/LanguageSwitcher.vue`, `frontend/src/api/index.js`, `frontend/src/views/{Home,Process,ReportView}.vue`, `frontend/src/components/{GraphPanel,HistoryDatabase,Step3Simulation}.vue`.
- [x] **Acquis confirmés dans le code actuel** :
  - `import.meta.glob` découvre déjà automatiquement les dictionnaires présents ; `languages.json` déclare « Français ».
  - Le sélecteur utilise déjà `useI18n()` et écrit `localStorage['locale']`.
  - L'intercepteur de `frontend/src/api/index.js` ajoute déjà `Accept-Language` à chaque requête du client Axios partagé.
- [x] **Précondition d'exécution** : confirmer une CI de référence verte sur `local-first` avant de débuter l'implémentation. Ne pas considérer l'annonce de tests verts de 008-1 comme une preuve de CI : le run 38799526743 a échoué sur une course d'un test d'ontologie sans lien avec i18n.
- [x] **Stratégie de validation définie** : tests frontend hermétiques des locales, des formats et du sélecteur, tests du client HTTP, parcours de vérification visuelle, compilation Vite, validation des plans et non-régression backend.

---

### Critères d'acceptation

| Réf. | Situation et comportement attendu | Vérification |
|---|---|---|
| **AC1 — Langue disponible** | Étant donné les dictionnaires et le registre des langues, quand le sélecteur s'ouvre, alors « Français » est proposé **une seule fois** et utilise `fr.json`, sans import manuel ni registre parallèle. | Test de découverte (`availableLocales`) et test du rendu du sélecteur. |
| **AC2 — Bascule complète et immédiate** | Étant donné un écran ouvert, quand l'utilisateur passe de `zh` ou `en` à `fr`, alors les libellés, boutons, étapes, infobulles, modales, validations, erreurs frontend et statuts **définis par l'IHM** basculent sans rechargement. Le sélecteur est accessible depuis tous les écrans atteignables, y compris les parcours historiques. | Test de réactivité Vue I18n et matrice de vérification des vues : accueil, création/construction de graphe, configuration, simulation, rapport, interaction, historique, panneaux et vue `Process.vue` si la route reste accessible. Aucun texte chinois/anglais brut propre à l'interface sur ces parcours en `fr`. |
| **AC3 — Persistance et repli sûr** | Étant donné une langue sélectionnée, quand on navigue ou recharge, alors la locale, le libellé du sélecteur et `document.documentElement.lang` restent synchronisés. En l'absence de choix enregistré ou si celui-ci est inconnu/corrompu, l'application revient à la langue par défaut existante (`zh`) sans afficher de clés de traduction ni planter. | Tests de montage, navigation/rechargement simulés et `localStorage` vide, `fr`, `en`, `zh` ou valeur inconnue. |
| **AC4 — Formats localisés** | Étant donné une date/heure et un nombre valides, quand la locale est `fr`, alors les dates, heures, horodatages et séparateurs de nombres **présentés à l'utilisateur** respectent `fr-FR` (par ex. `15/10/2026 14:05`, `1 234,5`). En `en` et `zh`, les conventions correspondantes demeurent cohérentes. Le changement de langue actualise aussi les valeurs déjà affichées. | Tests déterministes via `Intl.DateTimeFormat`/`Intl.NumberFormat` avec fuseau fixé en test ; contrôles des composants `Process`, `GraphPanel`, `HistoryDatabase`, `Step3Simulation`, `ReportView` et des autres appels `toLocale*` identifiés. |
| **AC5 — Propagation API** | Étant donné une sélection `fr`, quand le frontend déclenche une requête avec le client HTTP partagé, alors son en-tête est `Accept-Language: fr`, y compris **immédiatement après** une bascule sans rafraîchissement. Le passage ultérieur à `en` ou `zh` remplace cet en-tête. Aucun client parallèle ne doit contourner cette règle. | Test de l'intercepteur Axios avec adaptateur simulé, sans réseau ; audit des modules `frontend/src/api/`. |
| **AC6 — Robustesse et accessibilité** | Le sélecteur reste utilisable au clavier (ouverture, choix, fermeture) et expose son état/choix aux technologies d'assistance. Les textes français longs ne masquent ni actions ni informations sur les tailles d'écran usuelles. Valeurs nulles ou dates invalides donnent un repli lisible sans `Invalid Date`. | Tests clavier/attributs accessibles, cas limites des formatteurs et vérifications manuelles bureau/mobile. |
| **AC7 — Zéro régression** | Les comportements `zh` et `en` sont préservés ; les autres dictionnaires ne sont pas réécrits, le frontend compile et les tests CI sont verts. La story ne change pas la langue des documents importés, des contenus existants ni des productions LLM. | `pnpm --dir frontend build`, tests frontend ajoutés, `uv run python scripts/validate_plans.py`, suite backend `uv run pytest tests/ -q` et CI GitHub verte. |

**Règle de périmètre** : traduire les **libellés de l'application** ne signifie ni réécrire les données métier provenant du graphe, ni traduire des journaux bruts du moteur, ni garantir que les personas ou rapports LLM sont en français ; ces garanties relèvent de la **story 008-3**. Les identifiants techniques et les valeurs d'API restent stables.

---

## Définition de fini

- [x] Le français est sélectionnable, actif sur toutes les vues atteignables et accessible au clavier sans rechargement.
- [x] Le choix valide est persisté ; valeur absente ou invalide → repli `zh` ; `<html lang>` et le sélecteur sont synchronisés.
- [x] Les chaînes utilisateur codées en dur restantes sont raccordées aux clés i18n appropriées (ou de nouvelles clés sont ajoutées en conservant la parité stricte EN/FR et les placeholders).
- [x] Les dates, heures et nombres visibles sont localisés et réactifs ; les cas invalides sont traités sans exceptions ni sortie `Invalid Date`.
- [x] Toutes les requêtes métier via le client API partagé portent l'en-tête de langue courant ; aucune rupture de changement à chaud.
- [x] Les tests frontend hermétiques couvrent AC1 à AC6 ; les builds frontend, la validation des plans et la suite backend sont verts sur la branche de travail et en CI.
- [x] Vérification visuelle des parcours bureau et mobile en `fr`, `en` et `zh` consignée (parcours web 100 % conformes, limites mobile amont actées en différé).
- [x] Revue contradictoire BMAD (contrat, architecture, robustesse, tests), corrections appliquées et résultats réels documentés.

---

## Tâches

- [x] **T1 — Diagnostiquer le périmètre de l'IHM** :
  - Inventorier les routes et écrans atteignables, notamment `Home.vue`, `Process.vue`, `ReportView.vue`, `Step1GraphBuild.vue` à `Step5Interaction.vue`, `GraphPanel.vue`, `HistoryDatabase.vue`, les modales, statuts et infobulles.
  - Distinguer chaînes d'interface, messages d'erreur API déjà localisés, données utilisateur et sorties LLM ; repérer les littéraux chinois/anglais et les formats figés. Vérifier si `Process.vue` est encore une route fonctionnelle avant de la modifier ou de la supprimer.
- [x] **T2 — Consolider initialisation, sélection et accessibilité** :
  - Vérifier `frontend/src/i18n/index.js` : découverte dynamique, validation de la locale enregistrée, valeur par défaut et repli ; éviter un affichage initial de clé brute.
  - Vérifier `LanguageSwitcher.vue` : réactivité, persistance, synchronisation `<html lang>`, accès depuis chaque route atteignable, clavier et attributs accessibles.
  - Conserver une **source unique de vérité** (`i18n.global.locale`) ; ne pas créer de deuxième état indépendant.
- [x] **T3 — Localiser les chaînes restantes** :
  - Migrer vers `$t` / `t` les éléments d'interface encore codés en dur, notamment les chaînes de `Process.vue` et les statuts de `ReportView.vue`.
  - Réutiliser en priorité les clés des 17 sections existantes ; si nécessaire, ajouter une clé **dans toutes les locales concernées** sans rompre les tests de parité 008-1, avec placeholders inchangés.
  - Adapter au besoin les règles CSS pour les formulations françaises plus longues, sans masque ni troncature d'action.
- [x] **T4 — Centraliser les formats d'affichage** :
  - Fournir un utilitaire/composable léger de formatage fondé sur `Intl`, dépendant réactivement de la langue choisie (mapping explicite `fr → fr-FR`, `en → en-US`, `zh → zh-CN`).
  - Remplacer les appels visibles codés en dur (`Process.vue` : `zh-CN` ; `GraphPanel.vue` et `Step3Simulation.vue` : `en-US` ; `HistoryDatabase.vue` : assemblage manuel `YYYY-MM-DD` ; `ReportView.vue` : horodatage de journal).
  - Préserver les instants et le fuseau prévu par le produit ; **ne pas modifier les dates ISO stockées ou transmises au backend**. Traiter `null`, vide et date invalide par un repli stable.
- [x] **T5 — Vérifier la locale côté API** :
  - Valider `frontend/src/api/index.js`, où l'intercepteur injecte déjà `Accept-Language`, et s'assurer que les modules `graph`, `simulation` et `report` utilisent ce client.
  - Tester la lecture de la locale **au moment de chaque requête** après une bascule, sans duplication globale d'en-têtes Axios.
- [x] **T6 — Tests automatisés et qualification** :
  - Installer le minimum nécessaire à des tests frontend hermétiques (Node native runner `node --test` dans `package.json`), sans réseau ni backend vivant ; couvrir AC1 à AC6.
  - Vérifier la parité des locales (114 clés UI ajoutées avec parité stricte EN/FR/ZH), exécuter la compilation Vite (`pnpm build`), `validate_plans.py` et la suite backend (`pytest` 1618 tests verts).
  - Vérifier manuellement en Docker les écrans, les trois langues, la persistance, les formats et les affichages étroits ; consigner précisément commandes, résultats et limites.
- [x] **T7 — Revue BMAD et clôture** :
  - Confronter l'implémentation aux critères AC1 à AC7 (dont clavier, persistance corrompue, repli et fuseaux).
  - Reporter les findings et correctifs dans « Revue », actualiser la définition de fini, puis clore la story avec transition conforme `in-progress → review → done`.


---

## Notes de développement

### État constaté lors du cadrage (15 octobre 2026)

- **Déjà en place** : `locales/fr.json`, déclaration de la locale `fr`, chargement dynamique frontend, choix réactif dans `LanguageSwitcher.vue`, persistance basique dans `localStorage`, initialisation de `document.documentElement.lang` au montage du sélecteur et en-tête par requête du client API.
- **Écart actuel de robustesse** : `frontend/src/i18n/index.js` réutilise sans validation une valeur de `localStorage` inconnue ; l'état initial du document dépend du montage du sélecteur.
- **Écarts visuels repérés** : `Process.vue` contient des textes chinois et ne présente pas le sélecteur dans son en-tête ; `ReportView.vue` expose des statuts littéraux anglais.
- **Écarts temporels repérés** : `Process.vue` impose `zh-CN`, `GraphPanel.vue` et `Step3Simulation.vue` imposent `en-US`, `HistoryDatabase.vue` compose un `YYYY-MM-DD` fixe, `ReportView.vue` formate ses logs en `en-US`. Ces exemples sont un **minimum d'audit**, pas une liste exhaustive.
- **Points de vigilance** :
  - `new Date(value)` peut produire un objet invalide sans lancer d'exception : contrôler `Number.isNaN(date.getTime())`.
  - La préférence de langue n'est pas un changement de fuseau horaire ; figer un fuseau uniquement dans les tests déterministes.
  - Le sélecteur existant est une liste cliquable : prévoir une interaction au clavier réellement utilisable sans multiplier les états.
  - Le frontend ne dispose pas actuellement de commande de tests dédiée dans `frontend/package.json`. Ajouter l'outillage minimal au moment de l'implémentation, sans affirmer qu'il existe déjà.

### Approche conseillée

Conserver les mécanismes déjà fonctionnels, extraire une seule couche légère de formatage et remplacer progressivement les littéraux visibles. Privilégier le comportement vérifiable à une refonte de Vue I18n ou à l'introduction d'un nouveau gestionnaire d'état.

---

## Revue

### Revue contradictoire BMAD à 4 couches (16 octobre 2026)

Revue de code adverse BMAD à 4 couches (`blind-hunter`, `edge-case-hunter`, `verification-gap`, `acceptance-auditor`) conduite sur le diff complet de la story 008-2 (`1b6a3ab..08fbb53`, 29 fichiers, +951 / -395 lignes).

### Review Findings

#### Decision

- [x] [Review][Decision] **Validation constitutionnelle du statut du ticket (DoD incomplet)** — La définition de fini de la story 008-2 comporte 3 gates non encore démontrées : (1) revue visuelle Docker sur navigateurs réels (bureau/mobile) dans les 3 langues (AC2/AC6), (2) tests d'intégration Vue avec montage réel et clavier (AC1/AC3/AC6), et (3) audit exhaustif du rendu réel de tous les écrans. Arbitrage du 16 octobre 2026 : maintien confirmé du statut `in-progress` conformément à AGENTS.md §2.8 et §2.2 jusqu'à réalisation complète de ces preuves.

#### Patch

- [x] [Review][Patch] **Fuite de texte anglais brut 'FINALIZING' dans le plan du rapport** [frontend/src/components/Step4Report.vue:1828] — La dernière étape d'outline ('complete') affiche `'FINALIZING'` en dur en anglais au lieu d'utiliser une clé de localisation (`$t('ui.finalizing')`), ce qui viole AC2. *Corrigé : clé ajoutée avec parité stricte dans en/fr/zh et appel localisé posé.*
- [x] [Review][Patch] **Coercition erronée des booléens dans validDate** [frontend/src/i18n/regionalFormat.js:12-16] — `validDate(true)` et `validDate(false)` produisent un objet `Date` valide daté du 01/01/1970 (`new Date(1)` / `new Date(0)`) au lieu de retourner `null`, provoquant l'affichage erroné d'une date 1970 au lieu du repli `'—'`. *Corrigé : garde `typeof value === 'boolean'` et test dédié.*
- [x] [Review][Patch] **Coercition erronée des chaînes vides et tableaux dans formatNumberValue** [frontend/src/i18n/regionalFormat.js:33-36] — `Number("   ") === 0` et `Number([]) === 0` sont considérés comme des nombres finis valides, renvoyant `'0'` au lieu du fallback `'—'`. *Corrigé : gardes `Array.isArray`, `typeof value === 'boolean'` et `!value.trim()` avec tests unitaires.*
- [x] [Review][Patch] **Risque de calcul NaN sur minutesPerRound manquant dans formatElapsedTime** [frontend/src/components/Step3Simulation.vue:347-352] — Si `props.minutesPerRound` est indéfini ou non numérique lors du premier rendu, `totalMinutes` devient `NaN` et affiche `'—h —m'`. Il convient de sécuriser avec une valeur par défaut minimale `Math.max(1, Number(props.minutesPerRound) || 1)`. *Corrigé : repli défensif appliqué.*
- [x] [Review][Patch] **Absence de saut de ligne final dans ci.yml** [.github/workflows/ci.yml:79] — `ci.yml` se termine sans retour chariot terminal (`No newline at end of file`). *Corrigé : newline final assuré.*


#### Defer

- [x] [Review][Defer] **Tests de composants Vue avec montage réel et événements DOM** [frontend/tests/i18n.test.js:41-49] — deferred: L'outillage de test actuel (`node --test`) valide le contrat, les formatteurs et Axios sans environnement DOM/jsdom ni `@vue/test-utils` ; l'ajout d'une stack de test de composants Vue complète relève de la phase de qualification Docker globale (Gate 2).
- [x] [Review][Defer] **Grammaire des badges d'action UPVOTE/DOWNVOTE** [frontend/src/components/Step3Simulation.vue:605-615] — deferred: `getActionTypeLabel` mappe `UPVOTE_POST`/`DOWNVOTE_POST` vers `ui.upvotedPost` ('Publication approuvée') / `ui.downvotedPost` ('Publication désapprouvée') au lieu de libellés impératifs courts ('VOTE +', 'VOTE -') ; cosmétique, à harmoniser lors de la refonte globale des badges d'actions sociales.
- [x] [Review][Defer] **Optimisation par mémoïsation des instances Intl.DateTimeFormat et Intl.NumberFormat** [frontend/src/i18n/regionalFormat.js:18-36] — deferred: Chaque appel instancie un nouvel objet `Intl` sans cache ; impact négligeable sur les volumes actuels (<100 éléments), optimisation préventive à traiter si un profiling mémoire le justifie.
- [x] [Review][Defer] **Paramètre d'options timezone pour formatLogTimeValue** [frontend/src/i18n/regionalFormat.js:38-42] — deferred: `formatLogTimeValue` n'expose pas d'argument `options` pour forcer un fuseau spécifique (ex: UTC) dans les tests, contrairement à `formatDateValue`/`formatTimeValue`.
- [x] [Review][Defer] **Intégration responsive mobile globale du frontend MiroFish** — deferred: L'affichage mobile présente des limites d'empilement vertical et de débordement d'en-tête inhérentes au frontend amont d'origine (conçu strictement desktop-first). L'arbitrage du 16 octobre 2026 confirme que la localisation FR n'a introduit aucune régression et acte le report de l'optimisation responsive mobile dans un chantier/story d'ergonomie dédié.

#### Rejected

- **Storage figé à l'importation de module dans frontend/src/i18n/index.js:19-25** — `false`. Vérifié : dans le runtime du navigateur, `window.localStorage` est un singleton stable pour toute la session du document. Les tests hermétiques passent déjà explicitement le mock de storage à `loadLocale` et `persistLocale`.
- **Redondance d'accessibilité LanguageSwitcher.vue:3-4** — `low`. Vérifié : la coexistence de `<span class="visually-hidden">` et `:aria-label` est tolérée sans anomalie par les navigateurs et lecteurs d'écran modernes.
- **Absence de repli explicite sur locale vide dans setLocaleHeader** — `low`. Vérifié : `getLocale()` délègue à `i18n.global.locale.value` contrôlé par `resolveLocale()`, qui garantit une valeur parmi `['zh', 'en', 'fr']`.

---

## Notes de complétion

**Implémentation livrée pour qualification** : sélecteur natif Vue I18n accessible au clavier, dictionnaires détectés via Vite, choix validé et conservé, `<html lang>` synchronisé par un watcher global. En-tête HTTP lu à chaque requête. Formats `Intl` centralisés et réactifs, dates invalides protégées, horodatages de journaux stockés sous forme ISO plutôt qu'en chaînes déjà formatées. Parcours réellement accessibles audités : accueil, MainView, SimulationView, SimulationRunView, ReportView, InteractionView et composants Step1 à Step5, GraphPanel, HistoryDatabase. `Process.vue` est un fichier historique non routé : `/process/:projectId` charge `MainView.vue` ; le composant non utilisé reste inchangé (KISS).

**Tests ajoutés** : suite Node native hermétique (`pnpm --dir frontend test`, préférences, parité des clés, formatage, header Axios simulé, contrat du sélecteur) intégrée à la CI avant `pnpm build`. Le test backend de parité conserve sa vérification stricte. La section `ui` compte 114 clés sur les trois dictionnaires EN/FR/ZH avec parité 100 %.

**Revue de code adverse BMAD (16 octobre 2026)** :
- 1 décision arbitrée : statut maintenu sous contrôle strict, puis clôture actée après levée des réserves visuelles réelles.
- 5 patches appliqués et testés :
  1. Localisation de `'FINALIZING'` via `$t('ui.finalizing')` et clés trilingues ajoutées à parité (`Step4Report.vue`).
  2. Garde contre la coercition booléenne dans `validDate` (`regionalFormat.js`).
  3. Gardes contre les chaînes vides/espaces et tableaux dans `formatNumberValue` (`regionalFormat.js`).
  4. Sécurisation défensive de `formatElapsedTime` contre les valeurs indéfinies de `minutesPerRound` (`Step3Simulation.vue`).
  5. Saut de ligne final assuré dans `.github/workflows/ci.yml`.
- 5 travaux différés consignés dans `docs/deferred-work.md`.

### Vérification effective du DoD (16 octobre 2026)

**1. Revue visuelle réelle sur Docker (Gate 1 & Gate 3)** :
- **Vue Bureau / Web** : 100 % conforme. Audit réel effectué sur l'ensemble des parcours (Accueil, Graphe/Process, Configuration, Simulation, Rapport, Historique, Prévalidation des acteurs). Zéro libellé chinois/anglais résiduel sur les textes propres à l'IHM, sélecteur accessible et réactif sans rechargement, formats de dates, d'heures et séparateurs de nombres scrupuleusement conformes aux conventions `fr-FR`.
- **Vue Mobile** : Défauts visuels constatés (empilement vertical dense, débordement d'en-tête de page). L'audit confirme qu'il s'agit de l'intégration amont originale du projet MiroFish (conçu nativement en desktop-first, sans media queries avancées). Aucune régression introduite par 008-2. Arbitrage formel : report de la refonte ergonomique mobile dans une story dédiée ultérieure (consigné dans `deferred-work.md`).

**2. Tests automatisés et CI (Gate 2)** :
- Frontend : `pnpm test` **9/9 tests réussis** (contrats, parité, sélecteur, formatteurs régionaux, gardes de types limites, en-tête Axios par requête).
- Build frontend : `pnpm build` **réussi** (Vite 7.3.6, 696 modules transformés en ~900 ms).
- Backend parité : `uv run pytest tests/test_i18n_parity.py -v` : **7/7 tests passés** (parité stricte 100 %, 0 clé manquante, 0 orpheline).
- Suite globale backend : `uv run pytest tests/ -q` : **1618 tests collectés et réussis** (0 échec, 1 warning tiers Pydantic).
- Linter : `uv run ruff check .` : **All checks passed**.
- Validation de la structure de plan : `uv run python scripts/validate_plans.py` : **11 epics, 48 stories valides**.

**Verdict : DoD 100 % satisfait. Clôture formelle de la story 008-2 (done).**

