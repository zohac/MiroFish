# Documentation — MiroFish local-first

Tout ce qui doit survivre à une session vit ici. `AGENTS.md` (à la racine) est
la **constitution** ; ce dossier est le **fond**.

---

## Organisation

| Dossier | Contenu | Convention de nommage |
|---|---|---|
| `docs/` (racine) | contexte technique de référence, état du projet | un fichier = un sujet |
| `docs/plans/` | un dossier par epic : PRD, architecture, stories | `<NNN>-<slug>/` |
| `docs/decisions/` | ADR : décisions d'architecture | `NNNN-titre-en-kebab-case.md` |
| `docs/architecture/` | schémas Mermaid — existant et cible | un fichier = une vue |

À la racine du dépôt : `sprint-status.yaml` (suivi machine-readable) et
`AGENTS.md` (constitution).

## Index

| Document | Statut | Contenu |
|---|---|---|
| [`LOCAL-FIRST.md`](LOCAL-FIRST.md) | vivant | installation, rôle de Zep, inventaire du couplage, obstacles, plan, audit des forks |
| [`STATUS.md`](STATUS.md) | vivant | fait / en cours / à faire, critères de l'épreuve en cours |
| [`plans/001-epreuve-graphiti-local/`](plans/001-epreuve-graphiti-local/prd.md) | vivant | PRD, architecture et stories de l'épreuve Graphiti |
| [`architecture/cible-graphstore.md`](architecture/cible-graphstore.md) | vivant | architecture cible du graphe (contexte + séquence) |
| [`decisions/README.md`](decisions/README.md) | vivant | conventions et index des ADR |
| [`decisions/0001-remplacement-de-zep-par-graphiti.md`](decisions/0001-remplacement-de-zep-par-graphiti.md) | accepté | Graphiti + Neo4j derrière une interface |
| [`decisions/0002-forks-adoption-refusee.md`](decisions/0002-forks-adoption-refusee.md) | accepté | ne pas adopter de fork : prendre la forme |
| [`decisions/0003-ontologie-differee-en-v2.md`](decisions/0003-ontologie-differee-en-v2.md) | accepté | ontologie dynamique reportée en v2 |
| [`decisions/0004-llm-opencode-go.md`](decisions/0004-llm-opencode-go.md) | accepté | endpoint LLM gratuit + compat session |
| [`decisions/0005-licence-agpl.md`](decisions/0005-licence-agpl.md) | accepté | rester local ; exposer en réseau ⇒ sources publiées |

## Règles d'écriture

- **Français** pour les docs, **anglais** pour le code et les identifiants.
- **Toute affirmation technique porte sa source** : chemin de fichier + ligne,
  ou commande exécutée. Une affirmation sans source est une hypothèse —
  marque-la « À confirmer ».
- **Les chiffres sont datés** (« au 3 octobre 2026 ») : ils vieillissent, et un
  tableau non daté devient un mensonge.
- **Pas de doublon** : on lie vers le document existant plutôt que de le
  recopier.
- **Une décision = un ADR**, jamais un paragraphe enfoui dans un document de
  contexte.
- Les schémas distinguent toujours l'**existant observé**, la **cible
  proposée** et les **hypothèses**. Un schéma qui ne fait pas la différence
  ment.

## Cycle de vie

1. Le contexte technique évolue dans `LOCAL-FIRST.md`.
2. Quand un choix est figé → un ADR.
3. Un ADR accepté n'est **pas** réécrit. Pour le changer, on écrit un nouvel
   ADR qui le supersède et on le référence ici.
4. `AGENTS.md` indexe tout et se met à jour en fin de session si le cadre a
   bougé.