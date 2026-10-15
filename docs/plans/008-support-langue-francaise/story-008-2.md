---
id: "008-2"
epic: "008"
titre: "Intégration et bascule IHM frontend Vue 3 (sélecteur, formats régionaux fr-FR)"
statut: review
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

- [ ] Le français est sélectionnable, actif sur toutes les vues atteignables et accessible au clavier sans rechargement.
- [ ] Le choix valide est persisté ; valeur absente ou invalide → repli `zh` ; `<html lang>` et le sélecteur sont synchronisés.
- [ ] Les chaînes utilisateur codées en dur restantes sont raccordées aux clés i18n appropriées (ou de nouvelles clés sont ajoutées en conservant la parité stricte EN/FR et les placeholders).
- [ ] Les dates, heures et nombres visibles sont localisés et réactifs ; les cas invalides sont traités sans exceptions ni sortie `Invalid Date`.
- [ ] Toutes les requêtes métier via le client API partagé portent l'en-tête de langue courant ; aucune rupture de changement à chaud.
- [ ] Les tests frontend hermétiques couvrent AC1 à AC6 ; les builds frontend, la validation des plans et la suite backend sont verts sur la branche de travail et en CI.
- [ ] Vérification visuelle des parcours bureau et mobile en `fr`, `en` et `zh` consignée.
- [ ] Revue contradictoire BMAD (contrat, architecture, robustesse, tests), corrections appliquées et résultats réels documentés.

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
- [ ] **T6 — Tests automatisés et qualification** :
  - Installer le minimum nécessaire à des tests frontend hermétiques (par exemple Vitest + Vue Test Utils, non présents dans le `package.json` actuel), sans réseau ni backend vivant ; couvrir AC1 à AC6.
  - Vérifier la parité des locales si des clés sont ajoutées, exécuter la compilation Vite, `validate_plans.py` et la suite backend.
  - Vérifier manuellement en Docker les écrans, les trois langues, la persistance, les formats et les affichages étroits ; consigner précisément commandes, résultats et limites.
- [ ] **T7 — Revue BMAD et clôture** :
  - Confronter l'implémentation aux critères AC1 à AC7 (dont clavier, persistance corrompue, repli et fuseaux).
  - Reporter les findings et correctifs dans « Revue », actualiser la définition de fini, puis seulement faire évoluer le statut `backlog → in-progress → review → done` et les vues de suivi requises.

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

**Revue statique initiale du 15 octobre 2026 — statut `review`.** La vérification CI post-commit et la revue visuelle Docker sur navigateurs réels restent à compléter. Axes examinés :

1. **Contrat** : AC1–AC7 démontrés, séparation nette entre IHM et génération LLM (008-3).
2. **Architecture** : source unique de locale, aucun registre supplémentaire, en-têtes API sans désynchronisation.
3. **Robustesse et UX** : valeurs corrompues, dates invalides, réactions au changement de langue, navigation clavier, affichages étroits et régression `zh`/`en`.
4. **Preuves** : tests hermétiques, build, CI, revue visuelle et éventuels écarts chiffrés.

Consigner ici les findings, leur sévérité, la décision et les correctifs effectivement appliqués avant le passage à `done`.

---

## Notes de complétion

**Implémentation livrée en revue** : sélecteur natif Vue I18n accessible au clavier, dictionnaires détectés via Vite, choix validé et conservé, `<html lang>` synchronisé par un watcher global. En-tête HTTP lu à chaque requête. Formats `Intl` centralisés et réactifs, dates invalides protégées, horodatages de journaux stockés sous forme ISO plutôt qu'en chaînes déjà formatées. Parcours réellement accessibles audités : accueil, MainView, SimulationView, SimulationRunView, ReportView, InteractionView et composants Step1 à Step5, GraphPanel, HistoryDatabase. `Process.vue` est un fichier historique non routé : `/process/:projectId` charge `MainView.vue` ; le composant non utilisé reste inchangé (KISS).

**Tests ajoutés** : suite Node native hermétique (`pnpm --dir frontend test`, préférences, parité des clés, formatage, header Axios simulé, contrat du sélecteur) intégrée à la CI avant `pnpm build`. Le test backend de parité conserve sa vérification stricte et abandonne seulement le nombre figé de clés après ajout de chaînes UI. La nouvelle section `ui` a 110 clés sur les trois dictionnaires EN/FR/ZH.

**Findings** :
- H1 (corrigé) : préférence inconnue/stockage bloqué faisait échouer ou dégrader l'initialisation ; repli strict `zh` et écriture best-effort.
- H2 (corrigé) : affichages de dates et journaux codés `en-US`/assemblage manuel, non réactifs, et `Invalid Date` possible ; formatteurs purs et horodatages ISO.
- M1 (corrigé) : statuts, textes de navigation et titres de panneaux de simulation et de rapport en anglais ; dictionnaire commun ajouté avec parité.
- M2 (corrigé) : liste cliquable sans garanties clavier/lecteur d'écran ; `<select>` natif avec étiquette traduite.
- L1 (assumé) : contenus de graphe et LLM non traduits, hors périmètre 008-3.

**Qualification non revendiquée** : la build, les tests Node, la suite backend et la validation des plans devront être vérifiés sur le commit GitHub ; aucun contrôle visuel Docker bureau/mobile n'a été réalisé depuis cet environnement. Maintenir le statut `review` tant que ces preuves manquent. Ne pas déclarer `done` sans elles.

À la clôture, consigner les fichiers modifiés, les tests réellement exécutés et leurs résultats, les écarts résiduels, les commits associés ainsi que le verdict de la revue. Ne pas cocher la définition de fini ni annoncer une CI verte sans preuve.
