# Couverture du rapport d'audit par l'Epic 009

- **Source** : [rapport d'audit du 10 octobre 2026](rapport-audit-mirofish-local-first.md), fourni par l'utilisateur.
- **Contrats** : [PRD](prd.md), [architecture](architecture.md), [hub](epic-009.md).
- **Date de rapprochement** : 10 octobre 2026.
- **Portée** : couverture du **plan**, pas réalisation. Les quatre stories restent `backlog` ; aucune recommandation de ce tableau n'est déclarée implémentée.

## Traçabilité des recommandations

| Réf. | Recommandation du rapport | Couverture du plan / lot | Preuve attendue ou décision restante |
|---|---|---|---|
| A01 | §4 P0, §7 : séparer connaissance et acteur ; utiliser description, relations et contexte ; conserver les non-acteurs dans le graphe. | FR-1/FR-2, NFR-1/NFR-3 ; 009-1 ; C1/C2. | ≥ 20 entités sur 2 domaines, ≥ 2 acteurs attendus retenus par domaine, 0 non-acteur devenu profil. Sorties invalides/faible confiance exclues, avec et sans LLM de personas. Qualification réelle séparée des mocks. |
| A02 | §4 P0 : permettre une exception explicite pour marque ou fiction ; gérer les collectifs. | Politique minimale de la [story 009-1](story-009-1.md), puis corrections motivées en 009-3. | Pour 009-1 : compte officiel d'organisation distinct du produit discuté, collectifs en `review`, exception marque/fiction explicitement reportée. Son extension demande une représentation dédiée et une autorisation ; un simple changement de statut ne satisfait pas ce besoin. |
| A03 | §4 P1 : fichiers avec rôle, date, priorité choisie, statut de validation et auteur/source si pertinent. | FR-3 ; 009-2. | Sérialisation de l'identifiant stable, du rôle, de la date et de la priorité ; source/auteur facultatifs. Le statut demandé est bien un **statut de validation** : valeurs, transitions et effet sur l'ingestion restent à définir. Un nom `official`/`canonical` ne confère aucune autorité. |
| A04 | §4 P1, §7 : fragments avec position, section/page disponible, texte et provenance jusqu'à la recherche et au rapport. | FR-5 ; 009-2 puis 009-4 ; C3. | Découpage par document ; positions en caractères dans le texte normalisé, plage `[char_start, char_end)` dont l'extraction restitue exactement le fragment. Page/section seulement si connue ; les formats sans pagination ne reçoivent pas de page inventée. |
| A05 | §4 P1, §8 : faire évoluer GraphStore sans casser Zep ; retrouver épisode et source. | NFR-2 ; ADR et 009-2 ; C3/C5. | Métadonnées par fragment et lecture neutre dans **les deux implémentations**. Références manquantes signalées, aucune requête Cypher ni import SDK Zep dans les services. Contrat précis à arrêter avant code. |
| A06 | §4 P1, §7 : ne pas fusionner silencieusement des sources contradictoires ; priorité/date seulement selon une règle déclarée. | FR-3/FR-7 ; 009-2, 009-3, 009-4 ; C7. | Jeu d'essai avec 2 affirmations contradictoires ; les deux sources restent accessibles, conflit affiché. Si une règle de résolution existe, exposer la règle et la décision ; sinon « à confirmer ». L'algorithme et le stockage du conflit restent à spécifier avant 009-2. |
| A07 | §4 P1 : brief versionné comprenant objectif, horizon, déclencheur, sorties attendues, état initial, audiences, règles, hypothèses et références documentaires. | FR-4 ; 009-2 ; C4. | Ajouter horizon, déclencheur, sorties attendues et références au contrat cible. Champs avancés facultatifs ; sauvegarde/relecture et transmission complète vérifiées. Une référence documentaire utilise l'identifiant du document. |
| A08 | §2.1/2.4, §4 P1 : rendre visibles échantillonnage, troncatures, fragments ignorés et erreurs d'extraction. | FR-4/FR-6 ; 009-2, 009-3 ; C4/C6. | Enregistrer les limites appliquées par étape et les sources effectivement utilisées ; présenter les omissions avant préparation. Cas long dépassant 50 000 caractères : conserver les consignes du brief ou signaler un refus explicite, jamais une perte silencieuse. Pas de promesse que tous les documents tiennent dans chaque prompt. |
| A09 | §4/§6 : conserver un mode simple et rendre la revue humaine facultative. | FR-3/FR-6 ; 009-2, 009-3 ; C6. | Parcours avec une consigne et des fichiers sans métadonnées avancées obligatoires. La qualification automatique est toujours appliquée ; l'absence de revue humaine n'autorise pas un acteur `review`. |
| A10 | §4/§7 : prévalidation avec raisons, corrections propres au run et blocage volontaire en cas de doute/conflit majeur. | FR-6 ; 009-3 ; C6. | Sélection persistée et révision vérifiée ; corrections isolées à la simulation ; scénario de blocage volontaire testé. L'utilisateur distingue entités exclues, points à réviser et omissions documentaires. |
| A11 | §4/§7 : distinguer document, événement effectivement enregistré et inférence ; ne pas inventer une vente observée. | FR-7 ; 009-4 ; C7. | Chaque action dite observée dans la simulation renvoie à une trace d'événement du run. Un post/intention ne prouve pas une autre action ; un événement non enregistré reste non observé. Les épisodes de graphe peuvent aider la recherche, mais ne remplacent pas la trace d'événement. |
| A12 | §4 P1 : les contenus documentaires sont des données, pas des instructions système. | NFR-5 ; 009-1/009-2/009-4 ; contribution C5. | Tests de construction des messages et des données de classification : une instruction trouvée dans un fichier ne devient ni message système ni correction d'éligibilité. Les règles explicites du brief restent distinctes du texte des sources. Cela ne démontre pas une immunité générale du LLM. |
| A13 | §6/§7 : jeu d'essai versionné et sorties intermédiaires permettant d'expliquer les résultats. | Qualification finale de 009-4 ; C1–C7. | Fixtures de documents/fragments/entités, sélection et profils attendus, événements et assertions de rapport ; mesure réelle avec paramètres consignés. Utiliser des données synthétiques ou partageables, sans secrets. Les variations entre runs ne sont pas quantifiées par le seul filet unitaire. |
| A14 | §4 P2, §6 lot E : benchmark contrôlé Zep/Graphiti puis ontologie dynamique. | **Hors périmètre de 009**, ADR 0003 et Epic 007. | Ne bloque pas le verrou P0. Toute comparaison ultérieure exige entrées, modèle, paramètres et métriques comparables ; elle ne se confond pas avec C2 multi-domaines et n'est pas exécutée dans cette reprise. |
| A15 | §1/§3/§8 : expliquer les différences exactes des deux simulations commerciales. | Preuve historique encore manquante, revue R17. | Identifiants des runs, documents, graphes, profils, modèle, prompts, paramètres et traces. Le rapport propose une cause probable ; le plan ne transforme pas cette hypothèse en causalité démontrée. |

## Corrections apportées au plan

Le rapprochement complète FR-3 à FR-7, introduit NFR-5 et précise C3/C4/C6/C7. L'architecture décrit les champs manquants et la chaîne de diagnostics/événements ; les critères des lots 009-2 à 009-4 les reprennent. Le nombre de stories reste quatre : aucune story n'est créée avant son démarrage.

Restent à arrêter dans les stories concernées : exception de fiction et collectifs, cycle de validation documentaire et résolution des conflits, contrat commun de provenance, politique de contexte long et mécanisme de blocage volontaire. La structure des références d'événements doit être fondée sur les traces disponibles, sans nouveau type d'action OASIS supposé.

Le rapport source reste intact. Les limites et recommandations ne sont pas transformées en résultats d'essais déjà obtenus.

## Contrôles du complément documentaire

Sous Docker, sur la copie isolée décrite dans la [revue de reprise](revue-coherence-2026-10-10.md), sans `.env` ni réseau :

- `uv run --no-sync python scripts/validate_plans.py` : structure valide, **9 epics et 31 fichiers de story**.
- `uv run --no-sync pytest tests/test_validate_plans.py tests/test_docker_tooling_parity.py -q` : **44 tests réussis**, aucun ignoré, 0,30 s.
- **127 liens locaux valides** dans les artefacts 009, AGENTS et STATUS ; `git diff --check` sans erreur.

Ces contrôles portent sur les documents et leur structure. Ils ne valident ni les nouvelles exigences fonctionnelles ni le code 006 développé en parallèle. Les chiffres de la suite complète exécutée au début de la reprise ne sont pas remplacés par ce sous-ensemble.
