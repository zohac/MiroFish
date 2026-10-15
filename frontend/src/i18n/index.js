import { watch } from 'vue'
import { createI18n } from 'vue-i18n'
import languages from '../../../locales/languages.json'
import { loadLocale, persistLocale, resolveLocale } from './localePreference.js'

// Vite discovers actual dictionaries; languages.json only supplies their labels.
const localeFiles = import.meta.glob('../../../locales/!(languages).json', { eager: true })
const messages = {}
const availableLocales = []

for (const path of Object.keys(localeFiles)) {
  const key = path.match(/\/([^/]+)\.json$/)?.[1]
  if (key && languages[key]) {
    messages[key] = localeFiles[path].default
    availableLocales.push({ key, label: languages[key].label })
  }
}
const supportedLocales = Object.keys(messages)
const storage = (() => {
  try {
    return typeof window === 'undefined' ? null : window.localStorage
  } catch {
    return null
  }
})()

const i18n = createI18n({
  legacy: false,
  locale: loadLocale(storage, supportedLocales),
  fallbackLocale: 'zh',
  messages
})

// One source of truth for UI, persisted preference, document and API requests.
watch(i18n.global.locale, (requestedLocale) => {
  const locale = resolveLocale(requestedLocale, supportedLocales)
  if (locale !== requestedLocale) {
    i18n.global.locale.value = locale
    return
  }
  if (typeof document !== 'undefined') document.documentElement.lang = locale
  persistLocale(storage, locale)
}, { immediate: true, flush: 'sync' })

export { availableLocales }
export default i18n
