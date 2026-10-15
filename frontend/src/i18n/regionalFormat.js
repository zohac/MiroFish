// Pure display-only formatters. Never change ISO values sent to the API.
const LOCALE_TAGS = Object.freeze({ fr: 'fr-FR', en: 'en-US', zh: 'zh-CN' })
const DATE_OPTIONS = Object.freeze({ day: '2-digit', month: '2-digit', year: 'numeric' })
const TIME_OPTIONS = Object.freeze({ hour: '2-digit', minute: '2-digit', hour12: false })
const DATETIME_OPTIONS = Object.freeze({ ...DATE_OPTIONS, ...TIME_OPTIONS })
const LOG_TIME_OPTIONS = Object.freeze({ ...TIME_OPTIONS, second: '2-digit' })

export function intlLocale(locale) {
  return LOCALE_TAGS[locale] || LOCALE_TAGS.zh
}

export function validDate(value) {
  if (value === null || value === undefined || value === '') return null
  const date = value instanceof Date ? value : new Date(value)
  return Number.isNaN(date.getTime()) ? null : date
}

export function formatDateValue(value, locale, options = {}, fallback = '—') {
  const date = validDate(value)
  return date ? new Intl.DateTimeFormat(intlLocale(locale), { ...DATE_OPTIONS, ...options }).format(date) : fallback
}

export function formatTimeValue(value, locale, options = {}, fallback = '—') {
  const date = validDate(value)
  return date ? new Intl.DateTimeFormat(intlLocale(locale), { ...TIME_OPTIONS, ...options }).format(date) : fallback
}

export function formatDateTimeValue(value, locale, options = {}, fallback = '—') {
  const date = validDate(value)
  return date ? new Intl.DateTimeFormat(intlLocale(locale), { ...DATETIME_OPTIONS, ...options }).format(date) : fallback
}

export function formatNumberValue(value, locale, options = {}, fallback = '—') {
  if (value === null || value === undefined || value === '' || !Number.isFinite(Number(value))) return fallback
  return new Intl.NumberFormat(intlLocale(locale), options).format(Number(value))
}

export function formatLogTimeValue(value, locale, fallback = '—') {
  const date = validDate(value)
  if (!date) return fallback
  return `${formatTimeValue(date, locale, LOG_TIME_OPTIONS)}.${String(date.getMilliseconds()).padStart(3, '0')}`
}
