# 0004 — LLM sur endpoint gratuit OpenCode Go, avec compat session

- **Statut** : accepté
- **Date** : 2026-10-03

## Contexte

Pour que le remplacement du graphe soit rentable, le LLM doit être gratuit :
c'est le seul poste qui reste, et il est **massif** (extraction du graphe,
génération de personas, des agents, puis des tours de simulation).

L'endpoint retenu est `https://opencode.ai/zen/go/v1` avec le modèle
`space-bunny-free` : gratuit et illimité, rétention 0 jour, pas
d'entraînement sur les données.

Deux contraintes réelles :

1. La passerelle Go **rejette** toute requête sans identifiant de session stable
   (HTTP 400 `MissingSessionID`) et demande un user-agent identifiant plutôt
   qu'un nom de SDK générique.
2. Un modèle gratuit et « stealth » **ne garantit rien** sur le structured
   output — or Graphiti en dépend pour extraire. C'est le point de rupture du
   projet (`docs/LOCAL-FIRST.md` §6.3).

## Décision

On utilise l'endpoint gratuit, et la compatibilité est **centralisée dans un
seul module** : `backend/app/utils/llm_compat.py`.

- `llm_request_headers()` n'injecte `x-opencode-session` + un user-agent
  honnête **que si l'hôte est `opencode.ai`** — donc aucun effet sur un autre
  fournisseur.
- `llm_completion_kwargs()` transmet `LLM_REASONING_EFFORT` si défini.
- Les tests sont hermétiques : ils neutralisent l'environnement
  (`monkeypatch.delenv`) au lieu de figer une valeur.

## Conséquences

**Positives**

- Coût marginal réellement nul, ce qui rend le graphe local rentable (§7).
- Changer de fournisseur reste possible : la compat est opt-in par hôte.
- L'effort de raisonnement est honoré (14 tokens de raisonnement constatés
  contre 0 en `low`).

**Négatives / risques**

- **Graphiti n'est pas couvert.** Ses appels LLM passent par son propre client
  (`OpenAIGenericClient`) et n'enverront ni session ni user-agent : à l'extraction,
  on obtiendrait un `MissingSessionID` — un échec de plumbing, pas un verdict
  sur le modèle. Il faudra sous-classer le client et overrider `acompletion`.
- La qualité du structured output est **à mesurer** (étape 1 du plan). Si elle
  ne suffit pas, on bascule l'extraction sur un modèle payant ponctuel, ce qui
  reste moins cher que des crédits Zep.
- **Politique d'usage** : la passerelle est conçue pour des agents de code, et
  MiroFish est un moteur de simulation sociale à trafic massif et parallèle. Le
  service est surveillé. Un usage de production tiendrait à vérifier.

## Alternatives rejetées

- **Ollama en local** — aucun coût d'API mais du CPU et du temps ; la qualité
  d'extraction d'un modèle 7–32B sous contrainte de structured output est
  autrement incertaine. Non écarté : reste une option de repli.
- **Modèle payant pour tout** — contredit l'objectif.
- **Simplement configurer l'URL** sans en-têtes — rejeté, ça ne marche pas :
  HTTP 400 `MissingSessionID` dès le premier appel.