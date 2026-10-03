# Travail différé

Choses réelles, mais hors du périmètre de la revue en cours. Chaque entrée dit
pourquoi elle est différée et ce qui la déclencherait.

## Deferred from: code review of story-001-1.md (2026-10-03)

Revue des commits `c1e17e0` + `0cdf1c0` (`ad4ef4c..HEAD`), le 3 octobre 2026.

- **`AGENTS.md:231` — `definition_of_ready` annoncé comme un identifiant lu par `validate_plans.py`.** `STORY_META_REQUIRED` vaut `("id", "epic", "titre", "statut", "auteur")` ; la clé n'est lue nulle part et ne subsiste que dans le tableau YAML d'ADR 0007, le format que l'ADR 0009 a supprimé. Un agent qui suit `AGENTS.md` §2.10 ajoutera une clé que le validateur ignore en silence. *Différé : le correctif édite un fichier de contexte agent.*
- **`AGENTS.md:428` — ancre `LOCAL-FIRST.md §11.4` pendante.** §11 « Points ouverts » n'a aucune sous-section ; ses items sont une liste numérotée. §12, lui, a bien `### 12.1`–`### 12.6`. Deux notations pour deux types de sections, dans le tableau « ce qui est déjà réglé — ne pas re-dériver » dont la valeur tient à ce que les ancres restent valides. *Différé : le correctif édite un fichier de contexte agent.*
- **`docs/decisions/0010-override-driver-neo4j.md` — la revalidation à chaque release du driver n'a pas de propriétaire.** L'ADR nomme le coût, admet que « rien ne surveille la dérive en continu », et ne dit ni qui revalide ni comment on le remarquerait. La version résolue est désormais consignée (`neo4j 5.28.6`, ADR 0011), ce qui fixe **ce qui** est testé ; il reste à dire **qui** réévalue quand le driver sort une 5.x. *Différé : l'ADR est accepté, le corriger suppose un ADR de précision. La partie `LOCAL-FIRST.md` §12.6 de ce constat a été traitée dans le même mouvement que le patch documentaire.*
- **`docs/README.md:29-33` — l'ADR 0010 n'y figure pas.** L'index s'arrête à 0005 ; 0006-0009 manquent déjà. Ce diff ajoute 0010 à `docs/decisions/README.md` mais pas à `docs/README.md`, que `AGENTS.md` §9 liste pourtant comme index de la documentation. *Différé : préexistant, et de faible enjeu.*
- **`backend/scripts/validate_plans.py:43-50,101-108` — titres de section en NFD (décomposition Unicode).** Le motif `^##\s+Tâches\s*$` ne correspondrait pas à un titre en NFD, qui serait rapporté « section obligatoire absente » pour les six sections à la fois. *Différé : `maybe-false` — aucun fichier de story de ce dépôt n'est en NFD, et l'échec serait bruyant en nommant le titre attendu. Ce qui trancherait : un fichier de story en NFD atteignant le validateur, et la confirmation qu'un plan rédigé sur un poste macOS peut en produire un.*
