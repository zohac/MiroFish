"""Le veto à la télémétrie de `graphiti-core`, et sa vraie valeur par défaut.

`graphiti-core` embarque `posthog` et envoie une télémétrie d'initialisation à
`us.i.posthog.com`. La bibliothèque la laisse **active par défaut** :

```python
# graphiti_core/telemetry/telemetry.py:36
env_value = os.environ.get(TELEMETRY_ENV_VAR, 'true').lower()
```

et l'appelle depuis `Graphiti.__init__` (`graphiti.py:248`). Pour un projet dont
la thèse est le local-first (ADR 0005), une sortie non demandée n'est pas un
détail de dépendance : c'est le genre de chose que personne ne remarque, parce
qu'elle ne se voit dans aucune sortie.

Ces tests vérifient donc deux choses distinctes :

1. **ce que MiroFish décide** — la config vaut `false` par défaut ;
2. **ce que `graphiti-core` lit réellement** — l'environnement porte cette
   décision au moment où le client est construit, pas seulement dans notre
   Config, qui pourrait être du décor.
"""

import os
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]


def _config_flags(telemetry: str | None) -> bool:
    """`Config.GRAPHITI_TELEMETRY_ENABLED` avec un environnement fabriqué."""
    script = (
        "from app.config import Config\n"
        "print('oui' if Config.GRAPHITI_TELEMETRY_ENABLED else 'non')\n"
    )
    env = {k: v for k, v in os.environ.items() if k != "GRAPHITI_TELEMETRY_ENABLED"}
    if telemetry is not None:
        env["GRAPHITI_TELEMETRY_ENABLED"] = telemetry
    done = subprocess.run(
        [sys.executable, "-c", script],
        cwd=BACKEND,
        env={**env, "PATH": os.environ.get("PATH", "")},
        capture_output=True,
        text=True,
    )
    assert done.returncode == 0, done.stderr
    return done.stdout.strip() == "oui"


def _graphiti_would_telemetry(telemetry: str | None) -> bool:
    """Ce que la bibliothèque décide, l'environnement réellement fourni."""
    script = (
        "from graphiti_core.telemetry.telemetry import is_telemetry_enabled\n"
        "print('oui' if is_telemetry_enabled() else 'non')\n"
    )
    env = {k: v for k, v in os.environ.items() if k != "GRAPHITI_TELEMETRY_ENABLED"}
    if telemetry is not None:
        env["GRAPHITI_TELEMETRY_ENABLED"] = telemetry
    done = subprocess.run(
        [sys.executable, "-c", script],
        cwd=BACKEND,
        env={**env, "PATH": os.environ.get("PATH", "")},
        capture_output=True,
        text=True,
    )
    assert done.returncode == 0, done.stderr
    return done.stdout.strip() == "oui"


# --------------------------------------------------------------------------
# Ce que MiroFish décide
# --------------------------------------------------------------------------

def test_telemetry_is_off_when_nothing_is_configured():
    assert _config_flags(None) is False


def test_telemetry_can_be_turned_on_explicitly():
    assert _config_flags("true") is True


def test_telemetry_accepts_the_usual_truthy_spellings():
    for value in ("1", "yes", "on", "TRUE", "On"):
        assert _config_flags(value) is True, value


def test_telemetry_stays_off_for_a_near_miss_value():
    """`maybe` n'est pas une vérité : une faute de frappe ne rallume rien."""
    for value in ("maybe", "", "false", "0", "no", "off"):
        assert _config_flags(value) is False, value


# --------------------------------------------------------------------------
# Ce que graphiti_core lit réellement
# --------------------------------------------------------------------------

def test_importing_config_is_enough_to_disable_the_library():
    """Le cas qui compte : sans rien faire, la télémétrie doit être coupée.

    Un simple `import app.config` doit suffire à poser la variable, parce que
    `Graphiti.__init__` la lit dans `os.environ` et pas dans notre Config. Si ce
    test échoue, notre config est décorative et le client part en télémétrie dès
    la première construction.
    """
    script = (
        "import app.config\n"  # noqa: F401 — l'import est le comportement testé
        "from graphiti_core.telemetry.telemetry import is_telemetry_enabled\n"
        "print('oui' if is_telemetry_enabled() else 'non')\n"
    )
    env = {k: v for k, v in os.environ.items() if k != "GRAPHITI_TELEMETRY_ENABLED"}
    done = subprocess.run(
        [sys.executable, "-c", script],
        cwd=BACKEND,
        env={**env, "PATH": os.environ.get("PATH", "")},
        capture_output=True,
        text=True,
    )
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == "non", (
        "importer app.config ne suffit pas à couper la télémétrie de graphiti_core"
    )


def test_the_library_default_would_have_been_on():
    """Ce que la bibliothèque fait de sa propre initiative, sans notre config.

    Sans cette preuve, « on est coupé » ne distingue pas « on a décidé » de
    « la bibliothèque a changé d'avis ». Si un jour Graphiti corrige son défaut,
    ce test tombe — et c'est utile : on saura que le filet n'est plus nécessaire.
    """
    assert _graphiti_would_telemetry(None) is True