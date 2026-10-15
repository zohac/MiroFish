import test from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import axios from 'axios'
import { loadLocale, resolveLocale, persistLocale } from '../src/i18n/localePreference.js'
import { intlLocale, formatDateValue, formatDateTimeValue, formatTimeValue, formatNumberValue, formatLogTimeValue } from '../src/i18n/regionalFormat.js'
import { setLocaleHeader } from '../src/api/localeHeader.js'

const supported = ['zh', 'en', 'fr']
const sample = '2026-10-15T14:05:06.123Z'
const utc = { timeZone: 'UTC' }

test('French dictionary is present once among discovered locale files', async () => {
  const languages = JSON.parse(await readFile(new URL('../../locales/languages.json', import.meta.url), 'utf8'))
  const locales = []
  for (const locale of supported) {
    const contents = await readFile(new URL(`../../locales/${locale}.json`, import.meta.url), 'utf8')
    locales.push(JSON.parse(contents))
  }
  assert.equal(languages.fr.label, 'Français')
  assert.equal(new Set(supported).size, supported.length)
  const flatten = (object, prefix = '') => Object.entries(object).flatMap(([key, value]) => typeof value === 'object' && value !== null ? flatten(value, `${prefix}${key}.`) : [`${prefix}${key}`])
  assert.deepEqual(flatten(locales[0]).sort(), flatten(locales[1]).sort())
  assert.deepEqual(flatten(locales[1]).sort(), flatten(locales[2]).sort())
})

test('unknown and corrupted preferences fall back to zh', () => {
  for (const candidate of [null, '', 'fr-BE', 'INVALID', 5, '__proto__']) {
    assert.equal(resolveLocale(candidate, supported), 'zh')
  }
  for (const candidate of supported) assert.equal(resolveLocale(candidate, supported), candidate)
})

test('storage absence and failures never block locale initialization', () => {
  assert.equal(loadLocale(null, supported), 'zh')
  assert.equal(loadLocale({ getItem: () => 'fr' }, supported), 'fr')
  assert.equal(loadLocale({ getItem: () => { throw new Error('blocked') } }, supported), 'zh')
  assert.doesNotThrow(() => persistLocale({ setItem: () => { throw new Error('blocked') } }, 'fr'))
})

test('native language control shares the global reactive locale', async () => {
  const component = await readFile(new URL('../src/components/LanguageSwitcher.vue', import.meta.url), 'utf8')
  const i18n = await readFile(new URL('../src/i18n/index.js', import.meta.url), 'utf8')
  assert.match(component, /<select\s+v-model="locale"/)
  assert.match(component, /:aria-label="\$t\('ui.language'\)"/)
  assert.match(component, /useScope:\s*'global'/)
  assert.match(i18n, /document\.documentElement\.lang = locale/)
  assert.match(i18n, /watch\(i18n\.global\.locale/)
})

test('French date and time use regional conventions without changing UTC instant', () => {
  assert.equal(intlLocale('fr'), 'fr-FR')
  assert.equal(formatDateValue(sample, 'fr', utc), '15/10/2026')
  assert.equal(formatDateTimeValue(sample, 'fr', utc), '15/10/2026 14:05')
  assert.equal(formatTimeValue(sample, 'fr', utc), '14:05')
  assert.match(formatDateValue(sample, 'en', utc), /10\/15\/2026/)
  assert.match(formatDateValue(sample, 'zh', utc), /2026/)
})

test('French numbers use a comma decimal and grouped thousands', () => {
  assert.equal(formatNumberValue(1234.5, 'fr'), '1\u202f234,5')
  assert.equal(formatNumberValue(1234.5, 'en'), '1,234.5')
  assert.equal(formatNumberValue(1234.5, 'zh'), '1,234.5')
})

test('null and invalid temporal values yield a stable placeholder', () => {
  for (const value of [null, '', undefined, 'not-a-date', new Date(NaN)]) {
    assert.equal(formatDateValue(value, 'fr'), '—')
    assert.equal(formatTimeValue(value, 'en'), '—')
    assert.equal(formatDateTimeValue(value, 'zh'), '—')
    assert.equal(formatLogTimeValue(value, 'fr'), '—')
  }
  assert.equal(formatNumberValue(NaN, 'fr'), '—')
})

test('log timestamps retain milliseconds and regional time', () => {
  assert.match(formatLogTimeValue(sample, 'fr'), /^\d{2}:\d{2}:\d{2}\.123$/)
})

test('Axios interceptor resolves Accept-Language freshly for every request', async () => {
  let locale = 'fr'
  const client = axios.create({ adapter: async config => ({ config, data: {}, headers: {}, status: 200, statusText: 'OK' }) })
  client.interceptors.request.use(config => setLocaleHeader(config, () => locale))
  for (const expected of ['fr', 'en', 'zh']) {
    locale = expected
    const result = await client.get('/isolated')
    assert.equal(result.config.headers.get('Accept-Language'), expected)
  }
})
