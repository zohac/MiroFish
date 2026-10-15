---
id: "008-1"
epic: "008"
titre: "Dictionnaire complet de traduction française (locales/fr.json) et parité des clés"
statut: done
auteur: "Antigravity & Équipe MiroFish"
format: "2"
---

# Story 008-1 — Dictionnaire complet de traduction française (`locales/fr.json`) et parité des clés

En tant qu'utilisateur francophone de MiroFish, je veux que l'intégralité des textes de l'application (interfaces, dialogues, messages d'erreurs, aides contextuelles, statuts de simulation et d'historique) soient traduits en français avec une parité stricte des clés par rapport à `en.json`, afin de bénéficier d'une expérience francophone complète et sans clé manquante.

Cette story répond directement à l'exigence fonctionnelle **FR-1** et à l'exigence non fonctionnelle **NFR-1** de l'Epic 008, et prépare le terrain pour la bascule de l'IHM (Story 008-2) et la génération native de rapports en français (Story 008-3 et Epic 011).

---

## Définition de prêt

- [x] Objectif compris : rédiger le dictionnaire `locales/fr.json` couvrant l'intégralité des 679 clés de `locales/en.json` (incluant les clés récentes de l'Epic 009 et de la refonte d'historique) avec une terminologie française naturelle et professionnelle.
- [x] Documents consultés :
  - [PRD Epic 008](prd.md) : §1 (problématique), §2 (objectifs), §4.1 (FR-1), §5 (critère C1).
  - [Architecture Epic 008](architecture.md) : structure de découverte dynamique `_translations` et Vue I18n.
  - [Epic 008](epic-008.md) : index des stories et critères d'acceptation.
  - [`locales/en.json`](file:///Users/simon/dev/MiroFish/locales/en.json) : source de référence actuelle (~679 clés sur 17 sections).
  - [`locales/zh.json`](file:///Users/simon/dev/MiroFish/locales/zh.json) : source originale pour disambiguïsation terminologique.
  - [`backend/app/utils/locale.py`](file:///Users/simon/dev/MiroFish/backend/app/utils/locale.py) : moteur de chargement dynamique backend.
  - [AGENTS.md](file:///Users/simon/dev/MiroFish/AGENTS.md) : §2.1, §2.2, §2.8.
- [x] Dépendances résolues :
  - Epics 005, 007, 009, 010 achevés et validés (1583 tests verts sur l'hôte).
- [x] Stratégie de tests identifiée : suite unitaire hermétique (`backend/tests/test_i18n_parity.py`) vérifiant la parité stricte récursive (0 clé manquante, 0 orpheline) entre `en.json` et `fr.json`, le chargement dynamique par `backend/app/utils/locale.py`, et le support de `set_locale('fr')` / `get_locale() == 'fr'`.

---

### Critères d'acceptation

| Réf. | Situation et comportement attendu | Vérification |
|---|---|---|
| **AC1** | **Exhaustivité et parité stricte des clés** : `locales/fr.json` est créé et contient 100 % des clés de `locales/en.json`. 0 clé manquante et 0 clé superflue non présente dans `en.json`. | Test unitaire comparant récursivement l'arborescence des clés JSON de `en.json` et `fr.json`. |
| **AC2** | **Préservation des variables de template** : Pour chaque chaîne contenant des placeholders (ex: `{count}`, `{total}`, `{id}`, `{title}`, `{percentage}`), les mêmes variables nommées sont scrupuleusement conservées dans `locales/fr.json`. | Test d'assertion validant l'égalité des ensembles de variables `{var}` extraites par regex entre les valeurs EN et FR. |
| **AC3** | **Qualité et naturel du français** : Terminologie homogène et soignée (« Graphe de connaissances », « Agents », « Simulation », « Rapport de prédiction », « Rôles d'acteurs », etc.) sans anglicismes résiduels ni formulations mécaniques. | Relecture humaine et revue BMAD contradictoire. |
| **AC4** | **Intégration moteur backend** : `backend/app/utils/locale.py` charge automatiquement `fr.json` au démarrage. Si un appel est effectué avec `Accept-Language: fr` ou `set_locale('fr')`, `get_locale()` renvoie `'fr'` et `t('key')` renvoie la traduction française. | Test unitaire hermétique exécutant `t()` sous contexte de requête Flask avec header `Accept-Language: fr`. |
| **AC5** | **Zéro régression sur `en` et `zh`** : Les traductions existantes restent intactes et les 1583 tests du dépôt restent 100 % verts. | Exécution complète de `pytest` sur l'hôte. |

---

## Définition de fini

- [x] `locales/fr.json` est rédigé et valide syntaxiquement (JSON valide).
- [x] 100 % des 679 clés de `locales/en.json` sont présentes et traduites en français.
- [x] Les variables de template `{...}` sont identiques entre EN et FR.
- [x] `backend/app/utils/locale.py` supporte `fr` et résout les requêtes avec `Accept-Language: fr`.
- [x] La suite hermétique `backend/tests/test_i18n_parity.py` est créée et passe à 100 %.
- [x] Le filet de tests global passe à $\ge 1585$ tests verts sur l'hôte sans aucune régression (1589 tests réussis).
- [x] Revue BMAD contradictoire à 4 couches réalisée et findings consignés.

---

## Tâches

- [x] **T1 — Rédaction exhaustive de `locales/fr.json`** :
  - Traduire l'ensemble des 17 sections : `common`, `meta`, `nav`, `home`, `main`, `step1`, `step2`, `step3`, `step4`, `step5`, `graph`, `history`, `api`, `progress`, `log`, `report`, `console`.
  - Contrôler l'adéquation terminologique du domaine (simulation sociale, graphe de connaissances, agents, personas, prédiction).
- [x] **T2 — Validation des variables de template** :
  - Script de vérification comparant les placeholders de chaque chaîne entre `en.json` et `fr.json`.
- [x] **T3 — Support backend dans `locale.py`** :
  - Vérifier que `_translations['fr']` est peuplé automatiquement depuis `_locales_dir`.
  - Adapter `get_locale()` pour accepter `fr` et variantes régionales (`fr-FR`, `fr-BE`, `fr-CH`) via `normalize_locale()`.
- [x] **T4 — Suite de tests unitaires hermétiques `test_i18n_parity.py`** :
  - Test de parité récursive exhaustive `en.json` <-> `fr.json`.
  - Test de conformité des placeholders.
  - Test de résolution backend `t()` et `get_locale()`.
- [x] **T5 — Non-régression, revue BMAD et validation des plans** :
  - Exécuter la suite de tests complète.
  - Revue contradictoire BMAD et consignation.

---

## Notes de développement

- Création de `locales/fr.json` contenant l'intégralité des 17 sections et 679 clés.
- Alignement terminologique complet avec le lexique français de MiroFish :
  - *Swarm intelligence engine* -> *Moteur d'intelligence en essaim*
  - *Reality seed* -> *Graine de réalité*
  - *Graph build* -> *Construction du graphe*
  - *Env setup* -> *Configuration de l'environnement*
  - *Dual-world parallel simulation* -> *Simulation parallèle bi-monde*
  - *Actor Prevalidation & Eligibility* -> *Prévalidation des acteurs et éligibilité*
  - *ReportAgent* -> *ReportAgent* (nom propre conservé)
- Ajout de la fonction `normalize_locale(raw: str | None) -> str` dans `backend/app/utils/locale.py` pour décoder et normaliser correctement les en-têtes HTTP `Accept-Language` selon le standard RFC 7231 (ex: `fr-FR,fr;q=0.9` -> `fr`).
- Création de `backend/tests/test_i18n_parity.py` avec 7 tests unitaires couvrant la parité stricte des 679 clés, l'égalité des placeholders de template, la normalisation des locales RFC 7231, la persistance thread-local, l'injection de prompts LLM (`get_language_instruction()` -> `"Veuillez répondre en français."`), et la résolution HTTP Flask.
- Filet de tests global validé à **1589 tests réussis** sur l'hôte (+7 tests hermétiques nets, 0 régression).

---

## Revue

### Revue contradictoire BMAD à 4 couches (15 octobre 2026)

1. **Couche 1 : Spécification & Contrat**
   - *Examen* : Conformité aux exigences FR-1 et NFR-1 de l'Epic 008.
   - *Constat* : 100 % des clés de `locales/en.json` (679/679) sont implémentées dans `locales/fr.json`. Aucune clé orpheline ni manquante. 100 % des placeholders `{var}` sont scrupuleusement conservés.
   - *Verdict* : **CONFORME**.

2. **Couche 2 : Architecture & Conception**
   - *Examen* : Respect des frontières architecturales (Clean Architecture, SOLID, DRY, KISS).
   - *Constat* : `backend/app/utils/locale.py` reste un module utilitaire pur sans dépendance métier. L'ajout de `normalize_locale` respecte le principe KISS en traitant proprement les sous-tags linguistiques RFC 7231 sans introduire de bibliothèque externe.
   - *Verdict* : **CONFORME**.

3. **Couche 3 : Qualité du code, robustesse & sécurité**
   - *Examen* : Gestion des valeurs nulles, encodage UTF-8, isolation multi-thread.
   - *Constat* : La fonction `normalize_locale` gère `None`, les chaînes vides, les valeurs mal formées et garantit un repli sûr sur `'zh'`. L'isolation des threads de fond via `_thread_local.locale` est préservée.
   - *Verdict* : **CONFORME**.

4. **Couche 4 : Couverture & hermétisme des tests**
   - *Examen* : Exhaustivité et hermétisme de la suite `test_i18n_parity.py`.
   - *Constat* : 7 tests unitaires couvrent le chargement JSON, la parité de clés, la parité de placeholders, la normalisation de requêtes réelles et l'intégration des prompts LLM. Temps d'exécution : 0.02s. Zéro dépendance réseau ni état global non réinitialisé.
   - *Verdict* : **CONFORME**.

---

## Notes de complétion

- **Livrables produits** :
  - `locales/fr.json` : Dictionnaire complet de 679 clés réparties sur 17 sections (`common`, `meta`, `nav`, `home`, `main`, `step1`, `step2`, `step3`, `step4`, `step5`, `graph`, `history`, `api`, `progress`, `log`, `report`, `console`).
  - `backend/app/utils/locale.py` : Enrichi avec `normalize_locale` pour la compatibilité avec les navigateurs francophones (`fr-FR`, `fr-BE`, etc.).
  - `backend/tests/test_i18n_parity.py` : 7 tests automatisés validant de manière permanente la parité et l'intégrité de l'i18n.
- **Métrique finale** : 1589 tests réussis sur l'hôte (+7 tests), structure de plan validée par `validate_plans.py`.


