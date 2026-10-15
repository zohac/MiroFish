// Pure locale preference policy: the loaded dictionaries are the authority.
export function resolveLocale(value, supportedLocales, fallback = 'zh') {
  return typeof value === 'string' && supportedLocales.includes(value) ? value : fallback
}

export function loadLocale(storage, supportedLocales, fallback = 'zh') {
  try {
    return resolveLocale(storage?.getItem('locale'), supportedLocales, fallback)
  } catch {
    return fallback // Disabled or inaccessible storage must not prevent rendering.
  }
}

export function persistLocale(storage, locale) {
  try {
    storage?.setItem('locale', locale)
  } catch {
    // Preferences are best-effort; application navigation must remain usable.
  }
}
