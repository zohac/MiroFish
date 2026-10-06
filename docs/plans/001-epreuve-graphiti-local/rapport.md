# Rapport de mesure — Épreuve Graphiti local sur 30 chunks (Epic 001)

> **Verdict global** : ✅ **GO — EXTRACTION VALIDÉE**  
> **Date de mesure** : 2026-10-06 15:53:40 UTC  
> **Mode d'exécution** : Exécution réelle (OpenCode Go + Neo4j local)

---

## 1. Synthèse des critères de sortie (PRD Epic 001)

| # | Critère | Seuil | Valeur mesurée | Statut |
|---|---|---|---|---|
| C1 | Épisodes extraits sans erreur | ≥ 90 % (≥ 27/30) | **29/30** (96.7 %) | ✅ Conforme |
| C2 | Échecs d'authentification (`MissingSessionID`) | **0** | **0** | ✅ Conforme |
| C3 | Graphe non vide et persistant dans Neo4j | ≥ 1 nœud, ≥ 1 rel. | **49** nœuds, **45** rel. | ✅ Conforme |
| C4 | Temporalité : arêtes avec `valid_at` | ≥ 1 arête | **11** arête(s) | ✅ Conforme |
| C5 | Rapport de mesure versionné | 1 fichier | **1** (`rapport.md`) | ✅ Conforme |

---

## 2. Configuration du banc d'essai

- **Document source** : `uploads/documents/rapport-an-2506-territorialisation-transition-energetique.pdf`
- **Empreinte SHA256** : `4281a931545537f56625c3f4d0907fc66f54be82fef5d7b10e655dcdaf72ce88` (Valide ✓)
- **Volume total du document** : 562 chunks découverts
- **Échantillon mesuré** : 30 chunks séquentiels
- **Découpage** : 500 caractères par chunk, 50 caractères de recouvrement
- **Endpoint LLM** : `https://opencode.ai/zen/go/v1`
- **Modèle LLM** : `space-bunny` (structured output mode: `json_object`)
- **Embedder** : `all-MiniLM-L6-v2` (384 dimensions, 100 % local)
- **Cross-Encoder** : `LocalPassthroughCrossEncoder` (0 € marginal, sans clé externe)
- **Durée totale de l'épreuve** : 232.01 s
- **Latence moyenne par chunk** : 7.73 s/chunk

---

## 3. Résultats détaillés par chunk

| Chunk | Taille (car.) | Durée (s) | Nœuds | Arêtes | `valid_at` | Statut | Erreur / Remarque |
|---|---|---|---|---|---|---|---|
| #01 | 169 | 21.26s | 3 | 2 | 0 | ✅ Succès | - |
| #02 | 442 | 36.14s | 4 | 3 | 1 | ✅ Succès | - |
| #03 | 209 | 13.54s | 2 | 1 | 1 | ✅ Succès | - |
| #04 | 481 | 20.35s | 10 | 9 | 9 | ✅ Succès | - |
| #05 | 464 | 4.32s | 1 | 0 | 0 | ✅ Succès | - |
| #06 | 495 | 4.60s | 1 | 0 | 0 | ✅ Succès | - |
| #07 | 414 | 4.30s | 0 | 0 | 0 | ✅ Succès | - |
| #08 | 494 | 2.77s | 0 | 0 | 0 | ✅ Succès | - |
| #09 | 413 | 2.87s | 0 | 0 | 0 | ✅ Succès | - |
| #10 | 230 | 2.40s | 0 | 0 | 0 | ✅ Succès | - |
| #11 | 333 | 2.66s | 0 | 0 | 0 | ✅ Succès | - |
| #12 | 469 | 2.37s | 0 | 0 | 0 | ✅ Succès | - |
| #13 | 413 | 2.60s | 0 | 0 | 0 | ✅ Succès | - |
| #14 | 232 | 1.84s | 0 | 0 | 0 | ✅ Succès | - |
| #15 | 339 | 2.49s | 0 | 0 | 0 | ✅ Succès | - |
| #16 | 415 | 5.06s | 0 | 0 | 0 | ✅ Succès | - |
| #17 | 340 | 2.66s | 0 | 0 | 0 | ✅ Succès | - |
| #18 | 498 | 3.85s | 0 | 0 | 0 | ✅ Succès | - |
| #19 | 425 | 2.52s | 0 | 0 | 0 | ✅ Succès | - |
| #20 | 421 | 1.99s | 0 | 0 | 0 | ✅ Succès | - |
| #21 | 417 | 12.27s | 0 | 0 | 0 | ✅ Succès | - |
| #22 | 329 | 2.26s | 0 | 0 | 0 | ❌ Échec | ValidationError |
| #23 | 440 | 2.91s | 0 | 0 | 0 | ✅ Succès | - |
| #24 | 361 | 3.12s | 0 | 0 | 0 | ✅ Succès | - |
| #25 | 285 | 3.38s | 0 | 0 | 0 | ✅ Succès | - |
| #26 | 459 | 19.71s | 5 | 4 | 0 | ✅ Succès | - |
| #27 | 381 | 5.54s | 0 | 0 | 0 | ✅ Succès | - |
| #28 | 205 | 5.25s | 0 | 0 | 0 | ✅ Succès | - |
| #29 | 487 | 3.36s | 0 | 0 | 0 | ✅ Succès | - |
| #30 | 381 | 4.25s | 0 | 0 | 0 | ✅ Succès | - |

## 4. Échantillon d'entités et de faits extraits

### Exemples d'entités extraites :
- **Antoine Armand**
- **Assemblée nationale**
- **Claire Lejeune**
- **Commission du développement durable et de l’aménagement du territoire**
- **Constance de Pélichy**
- **Constitution du 4 octobre 1958**
- **Dix-septième législature**
- **Fabrice Roussel**
- **France**
- **Frédéric-Pierre Vos**
- **Mickaël Cosson**
- **Mission d’information sur la territorialisation et le portage des politiques publiques en termes d’aménagement du territoire et de transition énergétique et écologique**
- **Olga Givernet**
- **Pierre Cazeneuve**
- **Vincent Thiébaut**

### Exemples de faits et relations extraits :
- L’Assemblée nationale fonctionne sous le cadre de la Constitution du 4 octobre 1958.
- La Dix-septième législature relève de la Constitution du 4 octobre 1958.
- L’Assemblée nationale a enregistré, le 18 février 2026, le rapport d’information de la Mission d’information sur la territorialisation et le portage des politiques publiques en termes d’aménagement du territoire et de transition énergétique et écologique.
- La Mission d’information sur la territorialisation et le portage des politiques publiques en termes d’aménagement du territoire et de transition énergétique et écologique a déposé son rapport d’information au nom de la Commission du développement durable et de l’aménagement du territoire, en application de l’article 145 du Règlement.
- Constance de Pélichy a présenté le rapport d’information de la Mission d’information sur la territorialisation et le portage des politiques publiques en termes d’aménagement du territoire et de transition énergétique et écologique.
- Constance de Pélichy et Vincent Thiébaut sont conjointement rapporteurs et députés du rapport d’information présenté au nom de la commission du développement durable et de l’aménagement du territoire.
- Mickaël Cosson est président de la mission d’information sur la territorialisation et le portage des politiques publiques en termes d’aménagement du territoire et de transition énergétique et écologique.
- Fabrice Roussel est vice-président de la mission d’information sur la territorialisation et le portage des politiques publiques en termes d’aménagement du territoire et de transition énergétique et écologique.
- Constance de Pélichy est rapporteur de la mission d’information sur la territorialisation et le portage des politiques publiques en termes d’aménagement du territoire et de transition énergétique et écologique.
- Vincent Thiébaut est rapporteur de la mission d’information sur la territorialisation et le portage des politiques publiques en termes d’aménagement du territoire et de transition énergétique et écologique.

## 5. Journal détaillé des anomalies

- **Chunk #22** : `ValidationError`
  - Message : 1 validation error for ExtractedEntities
extracted_entities
  Field required [type=missing, input_value={'$defs': {'ExtractedEnti... ['extracted_entities']}, input_type=dict]
    For further information visit https://errors.pydantic.dev/2.12/v/missing
