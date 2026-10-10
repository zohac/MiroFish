# Epic 008 — Support complet de la langue française (Localisation FR)

- **Statut** : `backlog` · **Dépend de** : 005 · **Bloque** : aucun
- **Suivi** : [`sprint-status.yaml`](../../sprint-status.yaml)
- **PRD** : [`prd.md`](prd.md) · **Architecture** : [`architecture.md`](architecture.md)

> L'Epic 005 a validé l'environnement conteneurisé de référence (Docker-first, 711 tests verts, Verdict GO).  
> **L'Epic 008 fournit une localisation française complète** couvrant l'interface utilisateur Vue 3, l'adaptation des formats régionaux, l'injection des consignes linguistiques dans les prompts système LLM et la validation e2e de personas et rapports d'analyse en français.

---

## 1. Exigences fonctionnelles (FR)

| Réf. | Intitulé | Description |
|---|---|---|
| **FR-1** | Dictionnaire français complet | `locales/fr.json` traduit l'ensemble des ~668 clés de `en.json` sans clé manquante ni texte brut non traduit. |
| **FR-2** | Sélecteur IHM et persistance | Sélection réactive du français dans `LanguageSwitcher.vue`, persistance du choix dans `localStorage`. |
| **FR-3** | Formats régionaux `fr-FR` | Dates, heures et nombres au format français (ex: `JJ/MM/AAAA HH:mm`). |
| **FR-4** | Prompts LLM en français | `get_language_instruction()` transmet `"Veuillez répondre en français."` aux requêtes de génération de persona, posts et rapports. |
| **FR-5** | Rapports de simulation en français | Le `ReportAgent` produit une analyse finale structurée en français. |

---

## 2. Exigences non fonctionnelles (NFR)

| Réf. | Intitulé | Description |
|---|---|---|
| **NFR-1** | Parité stricte des clés | Test automatisé certifiant 100 % de correspondance entre les clés de `en.json` et `fr.json`. |
| **NFR-2** | Zéro régression | Les langues existantes (`zh`, `en`) restent 100 % opérationnelles. |
| **NFR-3** | Parité Docker | Fichier `locales/fr.json` automatiquement synchronisé dans les conteneurs backend et frontend. |

---

## 3. UX requirements

- L'utilisateur francophone accède à MiroFish et peut choisir "Français" d'un simple clic.
- L'ensemble des libellés de l'interface (création de projet, graphe, configuration, simulation, rapport) s'affichent en français naturel et fluide.
- Les personas générés possèdent des noms, rôles, bios et publications en français.

---

## 4. Index des stories

| Story | Titre | Statut | Fichier |
|---|---|---|---|
| 008-1 | Dictionnaire complet de traduction française (`locales/fr.json`) et parité des clés | `backlog` | `story-008-1.md` |
| 008-2 | Intégration et bascule IHM frontend Vue 3 (sélecteur, formats régionaux `fr-FR`) | `backlog` | `story-008-2.md` |
| 008-3 | Génération de personas, simulations et rapports en français (prompts LLM & banc de validation) | `backlog` | `story-008-3.md` |

| Story | Critères d'acceptation (résumé) |
|---|---|
| 008-1 | Given le fichier `locales/en.json`, when `locales/fr.json` est rédigé, then 100 % des clés sont traduites ; une suite de tests unitaires valide la parité stricte des clés et l'absence d'orphelins. |
| 008-2 | Given l'application web frontend, when la langue française est sélectionnée, then toute l'IHM bascule en français, le choix est conservé au rechargement de page (`localStorage`), et les dates adoptent le format `fr-FR`. |
| 008-3 | Given une requête de simulation avec le header `Accept-Language: fr`, when les agents OASIS et le ReportAgent s'exécutent, then les profils, messages et le rapport final sont générés en français par le LLM. |

---

## 5. Documents à consulter

| Document | Ce qu'on y prend |
|---|---|
| [`locales/languages.json`](../../locales/languages.json) | Déclaration de la langue `fr` et de son `llmInstruction`. |
| [`locales/en.json`](../../locales/en.json) | Source de référence des ~668 clés de traduction. |
| [`backend/app/utils/locale.py`](../../backend/app/utils/locale.py) | Gestionnaire de localisation backend et injection de prompts. |
| [`frontend/src/i18n/index.js`](../../frontend/src/i18n/index.js) | Configuration Vue I18n et découverte dynamique. |
| [`AGENTS.md`](../../AGENTS.md) | Constitution du dépôt (§2.8, §2.10). |
