<template>
  <section class="comparison-panel" :aria-label="$t('step4.comparisonTitle')">
    <header class="comparison-header">
      <h2 class="comparison-title">{{ $t('step4.comparisonTitle') }}</h2>
      <button
        type="button"
        class="comparison-close"
        :aria-label="$t('step4.comparisonClose')"
        @click="$emit('close')"
      >
        <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2">
          <line x1="18" y1="6" x2="6" y2="18"></line>
          <line x1="6" y1="6" x2="18" y2="18"></line>
        </svg>
      </button>
    </header>

    <p v-if="loading" class="panel-hint">{{ $t('step4.comparisonLoading') }}</p>
    <p v-else-if="error" class="panel-error" role="alert">{{ error }}</p>

    <template v-else-if="left && right">
      <!-- Verdict de comparabilité -->
      <div class="verdict" :class="verdict.comparable ? 'verdict--ok' : 'verdict--ko'">
        <span class="verdict-icon">{{ verdict.comparable ? '✓' : '✗' }}</span>
        <div class="verdict-body">
          <strong class="verdict-title">
            {{ verdict.comparable ? $t('step4.comparableControlled') : $t('step4.comparableNotControlled') }}
          </strong>
          <span v-if="verdict.reasons.length > 0" class="verdict-reasons">
            {{ verdictReasons }}
          </span>
          <span v-else class="verdict-reasons">{{ $t('step4.comparableEvidenceIdentical') }}</span>
        </div>
      </div>

      <!-- Tableau factuel -->
      <table class="comparison-table">
        <caption class="sr-only">{{ $t('step4.comparisonTableCaption') }}</caption>
        <thead>
          <tr>
            <th scope="col">{{ $t('step4.comparisonMetric') }}</th>
            <th scope="col" class="column-version">{{ leftLabel }}</th>
            <th scope="col" class="column-version">{{ rightLabel }}</th>
            <th scope="col">{{ $t('step4.comparisonDelta') }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in rows" :key="row.key">
            <th scope="row" class="row-label">{{ row.label }}</th>
            <td class="cell-value">{{ row.left }}</td>
            <td class="cell-value">{{ row.right }}</td>
            <td class="cell-delta">{{ row.delta }}</td>
          </tr>
        </tbody>
      </table>

      <!-- Téléchargement des audits -->
      <div class="audit-links">
        <a v-if="left && left.auditAvailable" class="audit-link" :href="auditUrl(left)" target="_blank" rel="noopener">
          {{ $t('step4.comparisonAuditLeft', { id: left.shortId || left.reportId }) }}
        </a>
        <a v-if="right && right.auditAvailable" class="audit-link" :href="auditUrl(right)" target="_blank" rel="noopener">
          {{ $t('step4.comparisonAuditRight', { id: right.shortId || right.reportId }) }}
        </a>
        <p v-if="!auditAvailable" class="panel-hint">{{ $t('step4.comparisonAuditUnavailable') }}</p>
      </div>

      <!-- Diff par section -->
      <div class="diff-section">
        <h3 class="diff-title">{{ $t('step4.comparisonDiffTitle') }}</h3>
        <p v-if="diffSections.length === 0" class="panel-hint">{{ $t('step4.comparisonDiffEmpty') }}</p>
        <details
          v-for="(section, index) in diffSections"
          :key="`${section.title}-${section.status}-${index}`"
          class="diff-item"
          :class="`diff-item--${section.status}`"
        >
          <summary class="diff-summary">
            <span class="diff-section-title">{{ section.title || $t('step4.comparisonPreamble') }}</span>
            <span class="diff-status" :class="`diff-status--${section.status}`">{{ statusLabel(section.status) }}</span>
          </summary>
          <pre class="diff-body"><span
            v-for="(op, index) in section.ops"
            :key="index"
            class="diff-line"
            :class="`diff-line--${op.type}`"
          >{{ op.text }}
</span></pre>
        </details>
      </div>
    </template>

    <p v-else class="panel-hint">{{ $t('step4.comparisonMissingVersion') }}</p>
  </section>
</template>

<script setup>
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRegionalFormat } from '../i18n/useRegionalFormat.js'
import { getReportAuditDownloadUrl } from '../api/report.js'
import { computeDelta, diffSections as computeDiffSections } from '../utils/reportComparison.js'

const props = defineProps({
  left: { type: Object, default: null },
  right: { type: Object, default: null },
  verdict: { type: Object, default: () => ({ comparable: false, reasons: [] }) },
  loading: { type: Boolean, default: false },
  error: { type: String, default: '' },
})

defineEmits(['close'])

const { t } = useI18n()
const { formatNumber } = useRegionalFormat()

const leftLabel = computed(() => {
  if (!props.left) return ''
  return props.left.profileId || props.left.shortId || props.left.reportId || ''
})

const rightLabel = computed(() => {
  if (!props.right) return ''
  return props.right.profileId || props.right.shortId || props.right.reportId || ''
})

const verdictReasons = computed(() => {
  const reasons = Array.isArray(props.verdict?.reasons) ? props.verdict.reasons : []
  return reasons.map(reason => t(`step4.comparableReason.${reason}`)).join(' · ')
})

const unavailable = computed(() => t('step4.metricUnavailable'))

const diffSections = computed(() => {
  if (!props.left || !props.right) return []
  return computeDiffSections(props.left.markdown || '', props.right.markdown || '')
})

const auditUrl = (version) => {
  if (!version || !version.reportId) return '#'
  return getReportAuditDownloadUrl(version.reportId)
}

// Une archive d'audit n'existe que pour les rapports produits après la
// story 011-5 : le lien n'est proposé que lorsqu'elle est réellement là.
const auditAvailable = computed(() =>
  Boolean(props.left && props.left.auditAvailable)
  || Boolean(props.right && props.right.auditAvailable)
)

const statusLabel = (status) => {
  if (status === 'added') return t('step4.diffStatusAdded')
  if (status === 'removed') return t('step4.diffStatusRemoved')
  if (status === 'changed') return t('step4.diffStatusChanged')
  return t('step4.diffStatusSame')
}

const formatTokens = (value) => {
  if (value === null || value === undefined) return unavailable.value
  return formatNumber(value)
}

const formatSeconds = (value) => {
  if (value === null || value === undefined) return unavailable.value
  return `${formatNumber(value, { maximumFractionDigits: 1 })} s`
}

const formatCost = (usage) => {
  if (!usage || !usage.costAvailable || usage.estimatedCostUsd === null) return unavailable.value
  // La devise vient du fichier de télémétrie : une valeur illisible y ferait
  // lever `Intl.NumberFormat` (RangeError) et casserait tout le panneau.
  const currency = ['USD', 'EUR'].includes(usage.currency) ? usage.currency : 'USD'
  const amount = formatNumber(usage.estimatedCostUsd, {
    style: 'currency',
    currency,
    minimumFractionDigits: 2,
    maximumFractionDigits: 4,
  })
  return `${amount} · ${t('step4.costIsEstimate')}`
}

const formatDeltaNumber = (leftValue, rightValue) => {
  const delta = computeDelta(leftValue, rightValue)
  if (delta === null) return unavailable.value
  const formatted = formatNumber(delta, { maximumFractionDigits: 4 })
  if (delta > 0) return `+${formatted}`
  return formatted
}

const formatClaims = (version) => {
  if (!version) return unavailable.value
  const total = version.totalClaims
  const supported = version.supportedClaims
  if (total === null || total === undefined || supported === null || supported === undefined) {
    return unavailable.value
  }
  return `${formatNumber(supported)} / ${formatNumber(total)}`
}

const formatEffort = (version, key) => {
  const value = version && version[key]
  return value ? value : unavailable.value
}

const formatStopReason = (version) => {
  if (!version || !version.stopReason) return unavailable.value
  const label = t(version.stopReason.i18nKey)
  // Le code dit *quoi*, le message dit *pourquoi* (AC4).
  return version.stopMessage ? `${label} — ${version.stopMessage}` : label
}

const formatPublishable = (version) => {
  if (!version || version.isPublishable === null || version.isPublishable === undefined) {
    return unavailable.value
  }
  return version.isPublishable
    ? t('step4.publishableYes')
    : t('step4.publishableNo')
}

const formatCount = (value) => {
  if (value === null || value === undefined) return unavailable.value
  return formatNumber(value)
}

const formatRatio = (value) => {
  if (value === null || value === undefined) return unavailable.value
  return `${formatNumber(value, { maximumFractionDigits: 1 })} %`
}

const publicationLabel = (version) => {
  if (!version || !version.publicationStatus) return unavailable.value
  const status = String(version.publicationStatus).toLowerCase()
  if (status === 'verified_publishable') return t('step4.publicationVerifiedPublishable')
  if (status === 'needs_review') return t('step4.publicationNeedsReview')
  if (status === 'failed_validation') return t('step4.publicationFailedValidation')
  if (status === 'draft') return t('step4.publicationDraft')
  return status
}

const replayModeLabel = (version) => {
  if (!version || !version.replayMode) return unavailable.value
  const mode = String(version.replayMode).toLowerCase()
  if (mode === 'replay_frozen') return t('step4.replayModeFrozen')
  if (mode === 'live') return t('step4.replayModeLive')
  return mode
}

const rows = computed(() => {
  const left = props.left
  const right = props.right
  if (!left || !right) return []
  const leftUsage = left.usage || {}
  const rightUsage = right.usage || {}
  return [
    { key: 'model', label: t('step4.metricModel'), left: left.model || unavailable.value, right: right.model || unavailable.value, delta: '—' },
    { key: 'effortRequested', label: t('step4.metricEffortRequested'), left: formatEffort(left, 'effortRequested'), right: formatEffort(right, 'effortRequested'), delta: '—' },
    { key: 'effortEffective', label: t('step4.metricEffortEffective'), left: formatEffort(left, 'effortEffective'), right: formatEffort(right, 'effortEffective'), delta: '—' },
    { key: 'replayMode', label: t('step4.metricReplayMode'), left: replayModeLabel(left), right: replayModeLabel(right), delta: '—' },
    { key: 'publication', label: t('step4.metricPublicationStatus'), left: publicationLabel(left), right: publicationLabel(right), delta: '—' },
    { key: 'publishable', label: t('step4.metricPublishable'), left: formatPublishable(left), right: formatPublishable(right), delta: '—' },
    { key: 'claims', label: t('step4.metricClaims'), left: formatClaims(left), right: formatClaims(right), delta: formatDeltaNumber(left.supportedClaims, right.supportedClaims) },
    { key: 'unsupportedClaims', label: t('step4.metricUnsupportedClaims'), left: formatCount(left.unsupportedClaims), right: formatCount(right.unsupportedClaims), delta: formatDeltaNumber(left.unsupportedClaims, right.unsupportedClaims) },
    { key: 'contradictedClaims', label: t('step4.metricContradictedClaims'), left: formatCount(left.contradictedClaims), right: formatCount(right.contradictedClaims), delta: formatDeltaNumber(left.contradictedClaims, right.contradictedClaims) },
    { key: 'verificationRatio', label: t('step4.metricVerificationRatio'), left: formatRatio(left.verificationRatio), right: formatRatio(right.verificationRatio), delta: formatDeltaNumber(left.verificationRatio, right.verificationRatio) },
    { key: 'tokens', label: t('step4.metricTokens'), left: formatTokens(leftUsage.totalTokens), right: formatTokens(rightUsage.totalTokens), delta: formatDeltaNumber(leftUsage.totalTokens, rightUsage.totalTokens) },
    { key: 'duration', label: t('step4.metricInferenceDuration'), left: formatSeconds(leftUsage.durationSeconds), right: formatSeconds(rightUsage.durationSeconds), delta: formatDeltaNumber(leftUsage.durationSeconds, rightUsage.durationSeconds) },
    { key: 'wall', label: t('step4.metricWallDuration'), left: formatSeconds(leftUsage.wallSeconds), right: formatSeconds(rightUsage.wallSeconds), delta: formatDeltaNumber(leftUsage.wallSeconds, rightUsage.wallSeconds) },
    { key: 'cost', label: t('step4.metricEstimatedCost'), left: formatCost(leftUsage), right: formatCost(rightUsage), delta: leftUsage.costAvailable && rightUsage.costAvailable ? formatDeltaNumber(leftUsage.estimatedCostUsd, rightUsage.estimatedCostUsd) : unavailable.value },
    { key: 'stopReason', label: t('step4.metricStopReason'), left: formatStopReason(left), right: formatStopReason(right), delta: '—' },
  ]
})
</script>

<style scoped>
.comparison-panel {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 14px 16px;
  background: #FFFFFF;
  border: 1px solid #E5E7EB;
  border-radius: 10px;
  /* Hauteur bornée : le panneau vit dans la barre de version, qui ne défile
     pas. Sans borne, un diff long réduisait la zone des journaux à une
     hauteur nulle (Story 013-5, revue BMAD du 20 octobre 2026). */
  max-height: 45vh;
  overflow-y: auto;
}

.comparison-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.comparison-title {
  margin: 0;
  font-size: 13px;
  font-weight: 700;
  color: #111827;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.comparison-close {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  border: none;
  background: transparent;
  border-radius: 6px;
  color: #6B7280;
  cursor: pointer;
}

.comparison-close:hover {
  background: #F3F4F6;
  color: #111827;
}

.panel-hint {
  margin: 0;
  font-size: 11px;
  color: #6B7280;
}

.panel-error {
  margin: 0;
  font-size: 11px;
  color: #991B1B;
  background: #FEF2F2;
  border: 1px solid #FECACA;
  border-radius: 6px;
  padding: 6px 8px;
}

.verdict {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 8px 10px;
  border-radius: 8px;
  border: 1px solid transparent;
}

.verdict--ok {
  background: #F0FDF4;
  border-color: #86EFAC;
}

.verdict--ko {
  background: #FFFBEB;
  border-color: #FCD34D;
}

.verdict-icon {
  font-size: 12px;
  font-weight: 700;
}

.verdict--ok .verdict-icon { color: #166534; }
.verdict--ko .verdict-icon { color: #92400E; }

.verdict-body {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.verdict-title {
  font-size: 12px;
  color: #111827;
}

.verdict-reasons {
  font-size: 11px;
  color: #4B5563;
}

.comparison-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 11px;
}

.comparison-table th,
.comparison-table td {
  text-align: left;
  padding: 6px 8px;
  border-bottom: 1px solid #F3F4F6;
  vertical-align: top;
}

.comparison-table thead th {
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: #6B7280;
  border-bottom: 1px solid #E5E7EB;
}

.row-label {
  font-weight: 600;
  color: #374151;
  white-space: nowrap;
}

.cell-value,
.cell-delta {
  color: #111827;
}

.cell-delta {
  color: #6B7280;
  font-variant-numeric: tabular-nums;
}

.audit-links {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
}

.audit-link {
  font-size: 11px;
  color: #2563EB;
  text-decoration: none;
  border-bottom: 1px dashed #93C5FD;
}

.audit-link:hover {
  color: #1D4ED8;
}

.diff-section {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.diff-title {
  margin: 0;
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: #6B7280;
}

.diff-item {
  border: 1px solid #E5E7EB;
  border-radius: 6px;
  overflow: hidden;
}

.diff-summary {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 6px 10px;
  background: #F9FAFB;
  cursor: pointer;
  font-size: 11px;
}

.diff-section-title {
  font-weight: 600;
  color: #111827;
}

.diff-status {
  font-size: 9px;
  font-weight: 700;
  border-radius: 9999px;
  padding: 1px 7px;
}

.diff-status--same { background: #F3F4F6; color: #4B5563; }
.diff-status--changed { background: #FEF3C7; color: #92400E; }
.diff-status--added { background: #DCFCE7; color: #166534; }
.diff-status--removed { background: #FEE2E2; color: #991B1B; }

.diff-body {
  margin: 0;
  padding: 8px 10px;
  font-family: 'JetBrains Mono', monospace;
  font-size: 11px;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 320px;
  overflow-y: auto;
}

.diff-line--added { background: #DCFCE7; color: #166534; display: inline; }
.diff-line--removed { background: #FEE2E2; color: #991B1B; display: inline; }
.diff-line--context { color: #4B5563; display: inline; }

.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}
</style>
