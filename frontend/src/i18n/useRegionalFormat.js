import { useI18n } from 'vue-i18n'
import {
  formatDateValue, formatTimeValue, formatDateTimeValue,
  formatNumberValue, formatLogTimeValue
} from './regionalFormat.js'

// Functions read Vue I18n's global locale at render time: displayed dates react
// immediately to language changes without a second locale store.
export function useRegionalFormat() {
  const { locale } = useI18n({ useScope: 'global' })
  return {
    formatDate: (value, options, fallback) => formatDateValue(value, locale.value, options, fallback),
    formatTime: (value, options, fallback) => formatTimeValue(value, locale.value, options, fallback),
    formatDateTime: (value, options, fallback) => formatDateTimeValue(value, locale.value, options, fallback),
    formatNumber: (value, options, fallback) => formatNumberValue(value, locale.value, options, fallback),
    formatLogTime: (value, fallback) => formatLogTimeValue(value, locale.value, fallback)
  }
}
