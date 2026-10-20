<template>
  <section class="history-selector" :aria-label="$t('step4.historyTitle')">
    <header class="history-header">
      <div class="history-heading">
        <span class="history-title">{{ $t('step4.historyTitle') }}</span>
        <span class="history-count mono">{{ sortedReports.length }}</span>
      </div>
      <button
        class="history-refresh"
        type="button"
        :disabled="loading"
        :title="$t('step4.historyRefresh')"
        :aria-label="$t('step4.historyRefresh')"
        @click="$emit('refresh')"
      >
        <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2">
          <polyline points="23 4 23 10 17 10"></polyline>
          <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"></path>
        </svg>
      </button>
    </header>

    <p v-if="error" class="history-error" role="alert">{{ error }}</p>

    <p v-if="loading && sortedReports.length === 0" class="history-hint">{{ $t('step4.historyLoading') }}</p>

    <p v-else-if="sortedReports.length === 0" class="history-hint">{{ $t('step4.historyEmpty') }}</p>

    <ul v-else class="history-list">
      <li v-for="entry in sortedReports" :key="entry.report_id" class="history-item">
        <button
          type="button"
          class="history-entry"
          :class="{ 'is-current': entry.report_id === currentReportId }"
          :aria-current="entry.report_id === currentReportId ? 'true' : 'false'"
          :title="entry.report_id"
          @click="select(entry)"
        >
          <span class="entry-top">
            <span class="entry-id mono">{{ shortId(entry.report_id) }}</span>
            <span v-if="entry.report_id === currentReportId" class="entry-current">{{ $t('step4.historyCurrent') }}</span>
            <span v-if="isRunning(entry)" class="entry-running">{{ $t('step4.historyRunning') }}</span>
          </span>
          <span class="entry-meta">
            <span class="entry-date">{{ formatDateTime(entry.created_at) }}</span>
            <span v-if="entry.profile_id" class="entry-profile mono">{{ entry.profile_id }}</span>
          </span>
          <span class="entry-badges">
            <span v-if="entry.replay_mode" class="entry-badge" :class="`entry-badge--${entry.replay_mode}`">
              {{ replayModeLabel(entry.replay_mode) }}
            </span>
            <span
              v-if="entry.publication_status"
              class="entry-badge"
              :class="`entry-badge--${entry.publication_status}`"
            >
              {{ publicationLabel(entry.publication_status) }}
            </span>
            <span v-else-if="entry.status" class="entry-badge entry-badge--plain">
              {{ entry.status }}
            </span>
          </span>
        </button>
      </li>
    </ul>
  </section>
</template>

<script setup>
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRegionalFormat } from '../i18n/useRegionalFormat.js'
import { isRunningReport, shortReportId, sortReportHistory } from '../utils/reportComparison.js'

const props = defineProps({
  reports: { type: Array, default: () => [] },
  currentReportId: { type: String, default: '' },
  loading: { type: Boolean, default: false },
  error: { type: String, default: '' },
})

const emit = defineEmits(['select', 'refresh'])

const { t } = useI18n()
const { formatDateTime } = useRegionalFormat()

const sortedReports = computed(() => sortReportHistory(props.reports))

const shortId = (reportId) => shortReportId(reportId)

const isRunning = (entry) => isRunningReport(entry)

const select = (entry) => {
  if (!entry || !entry.report_id) return
  if (entry.report_id === props.currentReportId) return
  emit('select', entry.report_id)
}

const replayModeLabel = (mode) => {
  const normalized = String(mode || '').toLowerCase()
  if (normalized === 'replay_frozen') return t('step4.replayModeFrozen')
  if (normalized === 'live') return t('step4.replayModeLive')
  return normalized || t('step4.replayModeUnknown')
}

const publicationLabel = (status) => {
  const normalized = String(status || '').toLowerCase()
  if (normalized === 'verified_publishable') return t('step4.publicationVerifiedPublishable')
  if (normalized === 'needs_review') return t('step4.publicationNeedsReview')
  if (normalized === 'failed_validation') return t('step4.publicationFailedValidation')
  if (normalized === 'draft') return t('step4.publicationDraft')
  return normalized
}
</script>

<style scoped>
.history-selector {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.history-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.history-heading {
  display: flex;
  align-items: center;
  gap: 8px;
}

.history-title {
  font-size: 12px;
  font-weight: 700;
  color: #111827;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.history-count {
  font-size: 11px;
  color: #6B7280;
  background: #F3F4F6;
  border: 1px solid #E5E7EB;
  border-radius: 9999px;
  padding: 1px 8px;
}

.history-refresh {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border: 1px solid #E5E7EB;
  background: #FFFFFF;
  border-radius: 6px;
  color: #4B5563;
  cursor: pointer;
  transition: all 0.2s ease;
}

.history-refresh:hover:not(:disabled) {
  border-color: #D1D5DB;
  color: #111827;
}

.history-refresh:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.history-hint {
  margin: 0;
  font-size: 11px;
  color: #6B7280;
}

.history-error {
  margin: 0;
  font-size: 11px;
  color: #991B1B;
  background: #FEF2F2;
  border: 1px solid #FECACA;
  border-radius: 6px;
  padding: 6px 8px;
}

.history-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
  max-height: 260px;
  overflow-y: auto;
}

.history-entry {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 4px;
  text-align: left;
  padding: 8px 10px;
  border: 1px solid #E5E7EB;
  border-radius: 8px;
  background: #FFFFFF;
  cursor: pointer;
  transition: all 0.2s ease;
}

.history-entry:hover {
  border-color: #D1D5DB;
  background: #FAFAFA;
}

.history-entry:focus-visible {
  outline: 2px solid #2563EB;
  outline-offset: 2px;
}

.history-entry.is-current {
  border-color: #2563EB;
  background: #EFF6FF;
}

.entry-top {
  display: flex;
  align-items: center;
  gap: 8px;
}

.entry-id {
  font-size: 11px;
  font-weight: 700;
  color: #111827;
}

.entry-current,
.entry-running {
  font-size: 10px;
  font-weight: 600;
  border-radius: 9999px;
  padding: 1px 7px;
}

.entry-current {
  background: #DBEAFE;
  color: #1D4ED8;
}

.entry-running {
  background: #FEF3C7;
  color: #92400E;
}

.entry-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 10px;
  color: #6B7280;
}

.entry-profile {
  color: #4B5563;
}

.entry-badges {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.entry-badge {
  font-size: 9px;
  font-weight: 600;
  border-radius: 9999px;
  padding: 1px 7px;
  border: 1px solid transparent;
}

.entry-badge--replay_frozen {
  background: #EDE9FE;
  color: #5B21B6;
  border-color: #DDD6FE;
}

.entry-badge--live {
  background: #F3F4F6;
  color: #4B5563;
  border-color: #E5E7EB;
}

.entry-badge--verified_publishable {
  background: #DCFCE7;
  color: #166534;
  border-color: #86EFAC;
}

.entry-badge--needs_review {
  background: #FEF3C7;
  color: #92400E;
  border-color: #FCD34D;
}

.entry-badge--failed_validation {
  background: #FEE2E2;
  color: #991B1B;
  border-color: #FCA5A5;
}

.entry-badge--draft,
.entry-badge--plain {
  background: #F3F4F6;
  color: #4B5563;
  border-color: #D1D5DB;
}
</style>
