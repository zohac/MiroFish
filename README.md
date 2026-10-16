<div align="center">

<img src="./static/image/MiroFish_logo_compressed.jpeg" alt="Logo MiroFish" width="65%" />

# MiroFish — Local First

**Simulez des dynamiques sociales avec des agents IA, un graphe de connaissances local et des scénarios documentés.**

[![Branche](https://img.shields.io/badge/branche-local--first-2563eb?style=flat-square)](https://github.com/zohac/MiroFish/tree/local-first)
[![Licence](https://img.shields.io/badge/licence-AGPL--3.0-555?style=flat-square)](LICENSE)
[![CI](https://github.com/zohac/MiroFish/actions/workflows/ci.yml/badge.svg?branch=local-first)](https://github.com/zohac/MiroFish/actions/workflows/ci.yml?query=branch%3Alocal-first)

**[Installation](#-installation-avec-docker-recommandée) · [Fonctionnalités](#-ce-que-change-ce-fork) · [État du projet](#-état-du-projet) · [Documentation](#-documentation)**

</div>

> **À propos de ce dépôt.** Il s'agit du fork [`zohac/MiroFish`](https://github.com/zohac/MiroFish), développé sur la branche `local-first` à partir du projet original [`666ghj/MiroFish`](https://github.com/666ghj/MiroFish). Ce README décrit **le fork et son état actuel**, pas une version officielle de MiroFish. La [documentation chinoise historique](README-ZH.md) et la [présentation anglaise du projet amont](https://github.com/666ghj/MiroFish#readme) concernent principalement la version d'origine.

## 🔎 Présentation

MiroFish est un **moteur de simulation sociale multi-agents**. On lui fournit des documents (études, rapports, scénarios…) et un objectif de simulation. Il construit un graphe de connaissances, identifie les acteurs pertinents, génère leurs profils, fait interagir des agents dans des environnements sociaux simulés (Twitter et Reddit via OASIS), puis produit un rapport exploitable et interrogeable.

**Ce n'est pas un outil de prédiction infaillible.** Ses résultats sont des comportements simulés, dépendants des sources, des modèles, des paramètres et des hypothèses. Ils ne constituent pas à eux seuls des faits observés ni une prévision garantie.

### Le parcours

1. **Créer un projet** et importer des sources (`.pdf`, `.md`, `.txt`).
2. **Construire le graphe** : extraction d'entités et de relations avec Graphiti, stockage dans Neo4j.
3. **Préparer les agents** : ontologie adaptée au projet, qualification des acteurs, contrôle des sources et sélection des participants.
4. **Lancer la simulation** : interactions OASIS sur Twitter, Reddit ou les deux, avec suivi de l'exécution.
5. **Analyser les résultats** : rapport, provenance documentaire, consultation du graphe et outils d'interaction.

## ✨ Ce que change ce fork

| Domaine | Branche `local-first` |
| --- | --- |
| **Graphe de connaissances** | **Graphiti + Neo4j local** via l'abstraction `GraphStore` ; Zep Cloud reste un backend optionnel de compatibilité. |
| **Dépendance Zep** | **Aucune clé `ZEP_API_KEY` nécessaire** avec `ZEP_BACKEND=graphiti`. |
| **Déploiement** | `docker-compose.yml` construit localement trois services : **Neo4j, backend Flask, frontend Vue 3/Vite**. |
| **Installation reproductible** | **pnpm** pour Node.js, **uv** pour Python ; fichiers de verrouillage versionnés. |
| **Modèles IA** | Configuration d'un **endpoint compatible API OpenAI**, distant ou hébergé localement selon les capacités du modèle. |
| **Embeddings** | `sentence-transformers` local (modèle par défaut `all-MiniLM-L6-v2`) ; téléchargement initial du modèle possible. |
| **Ontologie** | Génération, validation, versionnement et réutilisation d'une ontologie propre au projet. |
| **Acteurs et sources** | Éligibilité des acteurs, prévalidation manuelle, traçabilité documentaire et distinction entre intentions exprimées et actions constatées dans les contrôles existants. |
| **Cycle de simulation** | Fin automatique, réconciliation des états des processus et déblocage de la génération de rapport après les rounds. |
| **Langues** | Dictionnaires **français, anglais et chinois**, sélecteur d'interface et formats régionaux ; **qualification française de bout en bout encore en cours**. |
| **Données Zep existantes** | Scripts d'audit, migration vers Neo4j et purge distante contrôlée. |

Le terme **local-first** signifie ici que le **graphe et l'infrastructure applicative peuvent être auto-hébergés**. Il ne garantit **ni un fonctionnement intégralement hors ligne ni l'absence d'appels externes** : tout dépend notamment du LLM choisi et du téléchargement initial des modèles.

## 🚀 Installation avec Docker (recommandée)

C'est l'**environnement de référence du projet**. Le `docker-compose.yml` principal construit les images à partir de **ce fork** et démarre Neo4j, l'API et l'interface. Il n'utilise pas l'image applicative préconstruite du projet amont.

### Prérequis

- Docker avec le plugin **Docker Compose**.
- Une machine disposant de suffisamment de mémoire et d'espace disque pour Neo4j, Python/OASIS et les dépendances d'embedding.
- L'accès à un **LLM compatible API OpenAI** et les identifiants éventuellement requis par ce fournisseur.

### 1. Cloner la bonne branche

```bash
git clone --branch local-first https://github.com/zohac/MiroFish.git
cd MiroFish
cp .env.example .env
```

### 2. Configurer `.env`

Modifiez au minimum ces valeurs dans le fichier `.env` de la racine :

```dotenv
# Backend de graphe local : pas de compte Zep Cloud nécessaire
ZEP_BACKEND=graphiti

# Neo4j : URI pour une exécution du backend sur l'hôte
# Docker Compose substitue automatiquement bolt://neo4j:7687 dans le conteneur.
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=remplacer-par-un-mot-de-passe-fort

# Télémétrie Graphiti désactivée
GRAPHITI_TELEMETRY_ENABLED=false

# LLM : exemple de fournisseur compatible OpenAI, à adapter
LLM_API_KEY=votre_cle_api
LLM_BASE_URL=https://votre-endpoint-compatible-openai/v1
LLM_MODEL_NAME=votre_modele
```

**Important :**

- `NEO4J_PASSWORD` doit correspondre au mot de passe utilisé au **premier démarrage** de Neo4j. Si son volume existe déjà, changer seulement `.env` ne change pas le mot de passe enregistré.
- **Ne commitez jamais `.env`** : il peut contenir des secrets. La clé Zep présente dans le fichier d'exemple est inutile en mode `graphiti` ; vous pouvez la retirer.
- Les variables `LLM_BOOST_*` du fichier d'exemple sont **optionnelles** : retirez ou commentez leurs lignes si vous n'utilisez pas de fournisseur secondaire, plutôt que de laisser des valeurs factices.
- Utilisez un modèle capable de suivre les instructions et de produire des sorties structurées ; un serveur « compatible OpenAI » ne garantit pas à lui seul la compatibilité de tous les comportements Graphiti/OASIS.
- Si le LLM tourne **sur votre ordinateur**, l'URL vue depuis Docker doit être accessible **depuis le conteneur**, pas seulement via `localhost` de l'hôte. Sur Docker Desktop (macOS/Windows), utilisez par exemple `http://host.docker.internal:1234/v1` pour un serveur local écoutant sur le port 1234.

### 3. Démarrer les services

```bash
docker compose up -d --build
docker compose ps
```

| Service | Adresse par défaut |
| --- | --- |
| Interface web | http://localhost:3000 |
| API Flask | http://localhost:5001 |
| Neo4j Browser | http://localhost:7474 |
| Neo4j Bolt | `bolt://localhost:7687` |

Les ports publiés sont configurables avec `FRONTEND_PORT`, `FLASK_PORT`, `NEO4J_HTTP_PORT` et `NEO4J_BOLT_PORT`.

```bash
# Suivre les logs de l'API
docker compose logs -f backend

# Arrêter les services en conservant les données Neo4j
docker compose down
```

> **Attention :** `docker compose down -v` supprime aussi les volumes nommés, donc les données Neo4j. Ne l'utilisez que si vous souhaitez explicitement repartir de zéro.

### Environnement de développement, pas déploiement public

La stack actuelle sert au développement et aux qualifications : le frontend Docker démarre **Vite en mode développement** et Neo4j publie ses ports. **Ne l'exposez pas directement à Internet** sans durcissement (authentification, secrets, restrictions réseau, HTTPS et configuration de production).

## 🧰 Développement local (alternative)

Pour travailler hors de la stack applicative Docker, vous pouvez faire tourner **seulement Neo4j dans Docker**, puis lancer les deux applications sur l'hôte.

**Prérequis :** Node.js ≥ 18, pnpm **10.23.0**, Python ≥ 3.11 et < 3.13 (géré par `uv` si nécessaire), `uv` et Docker pour Neo4j.

```bash
# Depuis la racine du dépôt, après avoir renseigné .env :
corepack enable
corepack prepare pnpm@10.23.0 --activate

# Dépendances Node et Python
pnpm setup:all

# Base Neo4j seule (ne pas démarrer simultanément les deux Compose)
docker compose -f docker-compose.neo4j.yml up -d --wait

# Backend Flask et frontend Vite
pnpm dev
```

**Pour ce mode**, conservez `ZEP_BACKEND=graphiti` et `NEO4J_URI=bolt://localhost:7687` dans `.env`. Le fichier `docker-compose.neo4j.yml` est un environnement de test **Neo4j seul** ; le `docker-compose.yml` principal est la stack complète. Ne démarrez pas les deux simultanément : ils se disputeraient notamment les ports Neo4j.

Commandes individuelles :

```bash
pnpm backend                   # API Flask
pnpm frontend                  # Interface Vite
pnpm --dir frontend build      # Build frontend
```

> Au premier usage, les embeddings locaux peuvent demander le téléchargement du modèle. Avec un fournisseur LLM distant, la simulation nécessite aussi un accès réseau et peut engendrer des frais d'API.

## 🌍 Langues et localisation

Le dépôt comporte les dictionnaires `locales/fr.json`, `locales/en.json` et `locales/zh.json`, utilisés par **Vue I18n**. L'interface propose un sélecteur de langue, conserve la préférence et transmet `Accept-Language` à l'API ; le backend possède également un mécanisme d'instructions linguistiques pour les appels LLM.

**État réel de l'Epic 008 :**

- **008-1 terminée** : dictionnaire français et tests de parité.
- **008-2 en cours de qualification** : traduction et formatage de l'interface implémentés ; vérification visuelle/navigation réelle et critères DoD encore ouverts.
- **008-3 en cours** : propagation de la langue dans les simulations, personas et rapports ; validation sur LLM réel encore nécessaire.

**Ne considérez donc pas toutes les productions des agents et tous les rapports comme garantis à 100 % en français** à ce stade. Détails dans [l'Epic 008](docs/plans/008-support-langue-francaise/epic-008.md).

## 🧪 Tests et qualité

La CI de la branche `local-first` vérifie **Ruff, pytest, la structure des plans, les tests frontend et le build Vite**. Les tests automatisés de CI sont majoritairement hermétiques : leur succès ne remplace pas une simulation réelle avec Neo4j, OASIS et un LLM.

```bash
# Environnement Docker de référence
docker compose run --rm backend uv run ruff check .
docker compose run --rm backend uv run python scripts/validate_plans.py
docker compose run --rm backend uv run pytest tests/ -q

# Sur l'hôte, après installation des dépendances
pnpm --dir frontend test
pnpm --dir frontend build
```

Suivi des qualifications : [`docs/STATUS.md`](docs/STATUS.md) et [workflow CI](https://github.com/zohac/MiroFish/actions/workflows/ci.yml?query=branch%3Alocal-first).

## 📦 Données et migration depuis Zep Cloud

Le backend reste compatible avec les deux implémentations derrière `GraphStore` :

- **`ZEP_BACKEND=graphiti`** : stockage local dans Neo4j, sans `ZEP_API_KEY` (choix recommandé pour ce fork).
- **`ZEP_BACKEND=cloud`** : Zep Cloud, nécessitant `ZEP_API_KEY`. C'est toujours la valeur de repli du backend **lors d'une exécution hors Compose** si la variable est absente ; définissez-la explicitement en développement local.

Si vous avez d'anciens graphes Zep, l'[Epic 006](docs/plans/006-migration-donnees-zep/epic-006.md) documente les outils disponibles :

- `backend/scripts/auditer_graphes_zep.py` — inventorier les graphes distants ;
- `backend/scripts/migrer_zep_vers_graphiti.py` — transférer les nœuds et relations vers Neo4j ;
- `backend/scripts/purger_graphes_zep.py` — supprimer des graphes distants **après confirmation explicite**.

**La migration et la purge ne sont pas exécutées automatiquement** au démarrage. Vérifiez les résultats avant toute suppression de données distantes.

## 🗺️ État du projet

| Chantier | État au 16 octobre 2026 |
| --- | --- |
| Epics **001–006** : Graphiti, GraphStore, remplacement de Zep, Docker et migration | ✅ Terminés |
| Epic **007** : ontologie dynamique | ✅ Terminé |
| Epic **009** : éligibilité des acteurs et traçabilité des sources | ✅ Terminé |
| Epic **010** : fin et réconciliation des simulations | ✅ Terminé |
| Epic **008** : prise en charge complète du français | 🚧 En cours (008-1 terminée, 008-2/008-3 en cours) |
| Epic **011** : preuves des événements, fiabilité des outils et rapports | 📋 Planifié |

**Limite importante :** les protections de provenance et de distinction intention/action déjà livrées ne signifient pas que les rapports sont exempts d'affabulations. L'Epic 011 doit notamment fiabiliser les interviews d'agents après simulation, l'accès aux traces d'actions, les affirmations vérifiables et la validation finale des rapports. Consultez son [périmètre détaillé](docs/plans/011-preuve-simulation-et-fiabilite-rapport/epic-011.md).

Les statuts et chiffres de tests évoluent : la référence à jour reste [`docs/STATUS.md`](docs/STATUS.md), avec le suivi détaillé dans [`docs/sprint-status.yaml`](docs/sprint-status.yaml).

## 📚 Documentation

| Ressource | Utilité |
| --- | --- |
| [`docs/README.md`](docs/README.md) | Index de la documentation et conventions. |
| [`docs/STATUS.md`](docs/STATUS.md) | Ce qui est terminé, en cours et planifié. |
| [`docs/LOCAL-FIRST.md`](docs/LOCAL-FIRST.md) | Historique technique des choix, expérimentations et configurations locales (certaines sections retracent des étapes anciennes). |
| [`docs/architecture/flux-global-simulation.md`](docs/architecture/flux-global-simulation.md) | Architecture et séquence de simulation de bout en bout. |
| [`docs/decisions/README.md`](docs/decisions/README.md) | Décisions d'architecture (ADR). |
| [`docs/plans/`](docs/plans/) | PRD, epics, stories, revues et rapports de qualification. |
| [`AGENTS.md`](AGENTS.md) | Règles du dépôt et exigences de contribution. |

## 🙏 Crédits et licence

Ce fork repose sur le projet original **[MiroFish — 666ghj](https://github.com/666ghj/MiroFish)**. Le moteur de simulation sociale utilise **[OASIS (CAMEL-AI)](https://github.com/camel-ai/oasis)**. Merci aux équipes et contributeurs de ces projets.

**Licence du dépôt : [GNU Affero General Public License v3.0 (AGPL-3.0)](LICENSE).** En cas de redistribution ou de mise à disposition via un réseau, vérifiez les obligations de cette licence, notamment la mise à disposition du code source correspondant.

---

<div align="center">

**[Code du fork](https://github.com/zohac/MiroFish/tree/local-first) · [Projet original](https://github.com/666ghj/MiroFish) · [Issues](https://github.com/zohac/MiroFish/issues)**

</div>
