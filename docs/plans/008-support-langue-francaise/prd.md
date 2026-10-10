# PRD — Epic 008 : Support complet de la langue française (Localisation FR)

- **Statut** : `backlog` · **Dépend de** : 005 · **Bloque** : aucun
- **Suivi** : [`sprint-status.yaml`](../../sprint-status.yaml)

> L'Epic 005 a scellé l'environnement Docker de référence autonome (711 tests verts, Verdict GO).  
> MiroFish fonctionne désormais 100 % local-first, sans dépendance externe vers Zep Cloud.  
>
> **L'Epic 008 concrétise la localisation francophone intégrale du projet** : interface utilisateur Vue 3, prompts système LLM, personas OASIS, dynamiques de simulation et rapports finaux en langue française native.

---

## 1. Le problème

### 1.1 Contexte et état des lieux

MiroFish a été initialement développé en langue chinoise avec une couche de traduction anglaise partielle.  
L'architecture i18n du projet a déjà posé les fondations :
- [`locales/languages.json`](../../locales/languages.json) déclare le registre des langues supportées et contient déjà l'entrée pour le français :
  ```json
  "fr": {
    "label": "Français",
    "llmInstruction": "Veuillez répondre en français."
  }
  ```
- [`backend/app/utils/locale.py`](../../backend/app/utils/locale.py) charge dynamiquement les fichiers de traduction `locales/*.json` et injecte `get_language_instruction()` dans les prompts des générateurs LLM.
- [`frontend/src/i18n/index.js`](../../frontend/src/i18n/index.js) découvre dynamiquement les fichiers de langues via `import.meta.glob` et peuple le composant [`LanguageSwitcher.vue`](../../frontend/src/components/LanguageSwitcher.vue).

### 1.2 La rupture actuelle

Bien que l'infrastructure i18n soit présente, **le fichier de traduction française n'existe pas** :
1. **Absence du dictionnaire français** :
   - Seuls `locales/zh.json` (36 kB) et `locales/en.json` (38 kB, 668 lignes) sont présents.
   - Le fichier `locales/fr.json` est manquant. Par conséquent, le français n'apparaît pas dans la liste des langues sélectionnables du frontend et le backend se replie systématiquement sur le chinois (`zh`) ou l'anglais.
2. **Formats régionaux non adaptés** :
   - Certains composants frontend forcent les formats en dur (ex: `toLocaleString('zh-CN')` dans `Process.vue` ou `en-US` dans `GraphPanel.vue`).
3. **Absence de validation e2e en langue française** :
   - Aucun test automatisé ne certifie la parité stricte des clés entre les langues.
   - La génération de personas, d'événements et de rapports en français n'a pas été formellement validée avec le modèle LLM local-first (`space-bunny`).

---

## 2. L'objectif

Fournir une expérience utilisateur et un pipeline d'IA **100 % opérationnels en français** :

1. **Parité totale du dictionnaire IHM** : disposer d'un fichier [`locales/fr.json`](../../locales/fr.json) traduisant l'intégralité des 668 clés de `en.json` avec une terminologie française fluide, professionnelle et naturelle.
2. **Activation et persistance dans le frontend** : afficher "Français" dans le sélecteur [`LanguageSwitcher.vue`](../../frontend/src/components/LanguageSwitcher.vue), mémoriser le choix dans `localStorage`, et adapter les formats de dates et nombres (`fr-FR`).
3. **Transmission du contexte linguistique au backend** : s'assurer que les en-têtes HTTP `Accept-Language: fr` sont transmis par le frontend et pris en compte par Flask pour injecter `"Veuillez répondre en français."` dans tous les prompts des agents.
4. **Validation de la chaîne de simulation en français** : vérifier que les personas OASIS (Reddit/Twitter) ont des bios, traits et interventions rédigés en français, et que le `ReportAgent` rédige son rapport d'analyse en français.
5. **Filet de tests i18n** : poser une suite de tests unitaires vérifiant la parité exhaustive des clés entre `en.json`, `zh.json` et `fr.json` pour empêcher toute régression lors des évolutions futures.

---

## 3. Périmètre

### 3.1 Dans le périmètre
- Création de [`locales/fr.json`](../../locales/fr.json) avec couverture 100 % des clés de `en.json`.
- Configuration et persistance de la langue dans le frontend Vue 3.
- Adaptation des formatages de dates et d'heures au locale français (`fr-FR`).
- Vérification de l'injection des instructions de langue dans `ontology_generator.py`, `oasis_profile_generator.py`, `simulation_config_generator.py` et `report_agent.py`.
- Suite de tests unitaires vérifiant l'intégrité et la symétrie des dictionnaires i18n.
- Validation sur le conteneur Docker de référence.

### 3.2 Hors périmètre
- Traduction des documents sources importés (les documents restent dans leur langue d'origine, ex: rapport AN n° 2506 en français).
- Traduction des identifiants techniques internes du code (qui restent en anglais par convention, ADR 0001, AGENTS.md §2.10).
- Support d'autres langues supplémentaires (espagnol, allemand, etc. qui restent en backlog ultérieur).

---

## 4. Exigences détaillées

### 4.1 Exigences fonctionnelles (FR)

| Réf. | Intitulé | Description |
|---|---|---|
| **FR-1** | Dictionnaire français complet | `locales/fr.json` contient 100 % des sections et clés de `en.json` (`common`, `meta`, `nav`, `home`, `process`, `simulation`, `graph`, `report`, etc.). |
| **FR-2** | Sélecteur IHM réactif | L'utilisateur peut basculer en "Français" à tout moment depuis n'importe quel écran via `LanguageSwitcher.vue`. |
| **FR-3** | Formats régionaux `fr-FR` | Dates, horodatages et séparateurs numériques sont formatés selon les conventions françaises. |
| **FR-4** | Prompts LLM en français | `get_language_instruction()` transmet `"Veuillez répondre en français."` aux requêtes de génération de persona, de posts et de rapport. |
| **FR-5** | Rapport final en français | Le `ReportAgent` produit un rapport analytique structuré entièrement rédigé en français. |

### 4.2 Exigences non fonctionnelles (NFR)

| Réf. | Intitulé | Description |
|---|---|---|
| **NFR-1** | Parité stricte des clés | Aucune clé manquante entre `en.json` et `fr.json` (garanti par test unitaire automatique). |
| **NFR-2** | Zéro régression sur `zh` et `en` | Le fonctionnement existant en chinois et en anglais reste strictement inchangé. |
| **NFR-3** | Zéro latence additionnelle | Les dictionnaires sont pré-chargés au build / démarrage, sans surcoût réseau au runtime. |
| **NFR-4** | Parité Docker | Les traductions françaises sont automatiquement intégrées dans les images conteneurisées locales. |

---

## 5. Critères de sortie chiffrés (C1 à C5)

| # | Critère | Seuil de succès |
|---|---|---|
| **C1** | Parité de clés `locales/fr.json` | **100 %** des clés de `en.json` présentes dans `fr.json` (0 clé manquante ou orpheline). |
| **C2** | Bascule IHM et persistance | Choix "Français" actif, persisté dans `localStorage`, 0 chaîne brute non traduite sur les pages principales. |
| **C3** | Formats temporels localisés | Dates affichées au format français (ex: `JJ/MM/AAAA HH:mm`). |
| **C4** | Personas et rapport en français | Profils OASIS générés avec bios/posts en français et rapport de simulation rédigé en français. |
| **C5** | Filet de tests au vert | $\ge 711$ tests existants passants + nouvelle suite de tests d'intégrité i18n (100 % vert). |
