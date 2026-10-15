import json
import os
import threading
from contextlib import contextmanager
from flask import request, has_request_context

_thread_local = threading.local()

_locales_dir = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'locales')

# Load language registry
with open(os.path.join(_locales_dir, 'languages.json'), 'r', encoding='utf-8') as f:
    _languages = json.load(f)

# Load translation files
_translations = {}
for filename in os.listdir(_locales_dir):
    if filename.endswith('.json') and filename != 'languages.json':
        locale_name = filename[:-5]
        with open(os.path.join(_locales_dir, filename), 'r', encoding='utf-8') as f:
            _translations[locale_name] = json.load(f)


def normalize_locale(raw: str | None) -> str:
    """Normalize a locale string or Accept-Language header into a supported locale key."""
    if not isinstance(raw, str) or not raw.strip():
        return 'zh'
    if raw in _translations:
        return raw
    # Parse RFC 7231 Accept-Language header components
    for item in raw.split(','):
        tag = item.split(';')[0].strip()
        if not tag:
            continue
        if tag in _translations:
            return tag
        # Try language subtag without region (e.g. 'fr-FR' -> 'fr')
        lang = tag.split('-')[0].strip().lower()
        if lang in _translations:
            return lang
    return 'zh'


def set_locale(locale: str):
    """Set locale for the current thread's background work."""
    _thread_local.locale = normalize_locale(locale)


@contextmanager
def use_locale(locale: str):
    """Temporarily set the simulation locale, even inside a Flask request.

    Scoped overrides do not leak to subsequent tasks on the same thread.
    """
    previous = getattr(_thread_local, 'forced_locale', None)
    _thread_local.forced_locale = normalize_locale(locale)
    try:
        yield
    finally:
        if previous is None:
            del _thread_local.forced_locale
        else:
            _thread_local.forced_locale = previous



def get_locale() -> str:
    forced = getattr(_thread_local, 'forced_locale', None)
    if forced is not None:
        return forced
    if has_request_context():
        raw = request.headers.get('Accept-Language', 'zh')
        return normalize_locale(raw)
    locale = getattr(_thread_local, 'locale', None)
    return normalize_locale(locale) if locale else 'zh'


def t(key: str, **kwargs) -> str:
    locale = get_locale()
    messages = _translations.get(locale, _translations.get('zh', {}))

    value = messages
    for part in key.split('.'):
        if isinstance(value, dict):
            value = value.get(part)
        else:
            value = None
            break

    if value is None:
        value = _translations.get('zh', {})
        for part in key.split('.'):
            if isinstance(value, dict):
                value = value.get(part)
            else:
                value = None
                break

    if value is None:
        return key

    if kwargs:
        for k, v in kwargs.items():
            value = value.replace(f'{{{k}}}', str(v))

    return value


def get_language_instruction() -> str:
    locale = get_locale()
    lang_config = _languages.get(locale, _languages.get('zh', {}))
    return lang_config.get('llmInstruction', '请使用中文回答。')
