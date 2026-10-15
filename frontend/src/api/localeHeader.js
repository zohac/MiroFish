// Read the current language for each request, never at client creation time.
export function setLocaleHeader(config, getLocale) {
  const locale = getLocale()
  if (typeof config.headers?.set === 'function') {
    config.headers.set('Accept-Language', locale)
  } else {
    config.headers = { ...config.headers, 'Accept-Language': locale }
  }
  return config
}
