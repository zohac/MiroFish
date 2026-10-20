import test from 'node:test'
import assert from 'node:assert/strict'

import {
  COMPARABILITY_REASONS,
  STOP_REASON_I18N_KEYS,
  buildComparisonVersion,
  computeDelta,
  describeStopReason,
  diffSections,
  evaluateComparability,
  isRunningReport,
  parseMarkdownSections,
  readEvidenceFingerprint,
  shortReportId,
  sortReportHistory,
  summarizeUsage,
} from '../src/utils/reportComparison.js'

const SHA_A = 'a'.repeat(64)
const SHA_B = 'b'.repeat(64)

test('history is sorted chronologically with a stable fallback on report_id', () => {
  const entries = [
    { report_id: 'report_c', created_at: '2026-10-19T12:00:00Z' },
    { report_id: 'report_a', created_at: '2026-10-19T10:00:00Z' },
    { report_id: 'report_b', created_at: '2026-10-19T10:00:00Z' },
  ]
  const sorted = sortReportHistory(entries)
  assert.deepEqual(sorted.map(entry => entry.report_id), ['report_a', 'report_b', 'report_c'])
})

test('history sorting never mutates the source list and tolerates broken input', () => {
  const entries = [
    { report_id: 'report_b', created_at: '2026-10-19T12:00:00Z' },
    { report_id: 'report_a', created_at: '2026-10-19T10:00:00Z' },
  ]
  const snapshot = [...entries]
  sortReportHistory(entries)
  assert.deepEqual(entries, snapshot)
  assert.deepEqual(sortReportHistory(null), [])
  assert.deepEqual(sortReportHistory(undefined), [])
})

test('history entries without a date keep a deterministic order', () => {
  const entries = [
    { report_id: 'report_z' },
    { report_id: 'report_y' },
  ]
  assert.deepEqual(
    sortReportHistory(entries).map(entry => entry.report_id),
    ['report_y', 'report_z'],
  )
})

test('two captures of the same frozen evidence are comparable through their SHA-256', () => {
  const left = { evidence_snapshot_id: 'snap_aaa', evidence_snapshot_sha256: SHA_A }
  const right = { evidence_snapshot_id: 'snap_bbb', evidence_snapshot_sha256: SHA_A }
  const verdict = evaluateComparability(left, right)
  assert.equal(verdict.comparable, true)
  assert.deepEqual(verdict.reasons, [])
  assert.equal(verdict.evidenceIdentity, 'sha256')
})

test('different evidence fingerprints are never declared comparable', () => {
  const verdict = evaluateComparability(
    { evidence_snapshot_id: 'snap_aaa', evidence_snapshot_sha256: SHA_A },
    { evidence_snapshot_id: 'snap_bbb', evidence_snapshot_sha256: SHA_B },
  )
  assert.equal(verdict.comparable, false)
  assert.ok(verdict.reasons.includes(COMPARABILITY_REASONS.EVIDENCE_MISMATCH))
})

test('a report without any frozen snapshot is never comparable', () => {
  const verdict = evaluateComparability(
    { evidence_snapshot_id: 'snap_aaa', evidence_snapshot_sha256: SHA_A },
    { profile_id: 'flash-medium' },
  )
  assert.equal(verdict.comparable, false)
  assert.ok(verdict.reasons.includes(COMPARABILITY_REASONS.SNAPSHOT_ABSENT))
})

test('reports from two different simulations are never comparable', () => {
  const verdict = evaluateComparability(
    { simulation_id: 'sim_one', evidence_snapshot_id: 'snap_aaa', evidence_snapshot_sha256: SHA_A },
    { simulation_id: 'sim_two', evidence_snapshot_id: 'snap_bbb', evidence_snapshot_sha256: SHA_A },
  )
  assert.equal(verdict.comparable, false)
  assert.ok(verdict.reasons.includes(COMPARABILITY_REASONS.SIMULATION_MISMATCH))
})

test('without a SHA-256 the snapshot identifier alone decides', () => {
  const same = evaluateComparability(
    { evidence_snapshot_id: 'snap_aaa' },
    { evidence_snapshot_id: 'snap_aaa' },
  )
  assert.equal(same.comparable, true)
  assert.ok(same.reasons.includes(COMPARABILITY_REASONS.HASH_UNAVAILABLE))

  const different = evaluateComparability(
    { evidence_snapshot_id: 'snap_aaa' },
    { evidence_snapshot_id: 'snap_bbb' },
  )
  assert.equal(different.comparable, false)
  assert.ok(different.reasons.includes(COMPARABILITY_REASONS.SNAPSHOT_MISMATCH))
})

test('the fingerprint is read from a history entry or from a report detail', () => {
  assert.deepEqual(
    readEvidenceFingerprint({ evidence_snapshot_id: 'snap_1', evidence_snapshot_sha256: SHA_A }),
    { snapshotId: 'snap_1', sha256: SHA_A },
  )
  assert.deepEqual(
    readEvidenceFingerprint({ evidence_snapshot: { snapshot_id: 'snap_2', sha256_hash: SHA_B } }),
    { snapshotId: 'snap_2', sha256: SHA_B },
  )
  assert.deepEqual(readEvidenceFingerprint(null), { snapshotId: null, sha256: null })
})

test('the fingerprint is also read from an assembled comparison version', () => {
  assert.deepEqual(
    readEvidenceFingerprint({ snapshotId: 'snap_3', sha256: SHA_A }),
    { snapshotId: 'snap_3', sha256: SHA_A },
  )
})

test('an assembled comparison version is judged on its own fingerprint', () => {
  const left = buildComparisonVersion({
    historyEntry: {
      report_id: 'report_a',
      simulation_id: 'sim_one',
      evidence_snapshot_id: 'snap_aaa',
      evidence_snapshot_sha256: SHA_A,
    },
  })
  const right = buildComparisonVersion({
    historyEntry: {
      report_id: 'report_b',
      simulation_id: 'sim_one',
      evidence_snapshot_id: 'snap_bbb',
      evidence_snapshot_sha256: SHA_A,
    },
  })
  const verdict = evaluateComparability(left, right)
  assert.equal(verdict.comparable, true)
  assert.equal(verdict.evidenceIdentity, 'sha256')
  assert.equal(left.snapshotId, 'snap_aaa')
  assert.equal(left.sha256, SHA_A)
})

test('an assembled comparison version without snapshot stays non comparable', () => {
  const left = buildComparisonVersion({ historyEntry: { report_id: 'report_a' } })
  const right = buildComparisonVersion({
    historyEntry: {
      report_id: 'report_b',
      evidence_snapshot_id: 'snap_bbb',
      evidence_snapshot_sha256: SHA_B,
    },
  })
  const verdict = evaluateComparability(left, right)
  assert.equal(verdict.comparable, false)
  assert.ok(verdict.reasons.includes(COMPARABILITY_REASONS.SNAPSHOT_ABSENT))
})

test('an assembled version never derives is_publishable from the final status', () => {
  const version = buildComparisonVersion({
    quality: { final_status: 'passed', publication_status: 'needs_review', is_publishable: false },
  })
  assert.equal(version.isPublishable, false)
  assert.equal(version.publicationStatus, 'needs_review')
})

test('markdown is split into titled sections with a preamble', () => {
  const sections = parseMarkdownSections('intro\n\n# Title\nbody\n\n## Sub\nmore\n')
  assert.equal(sections.length, 3)
  assert.equal(sections[0].title, '')
  assert.deepEqual(sections[0].lines, ['intro', ''])
  assert.equal(sections[1].title, 'Title')
  assert.equal(sections[2].title, 'Sub')
})

test('diff detects an added section', () => {
  const sections = diffSections('# Title\nbody\n', '# Title\nbody\n\n## New\nfresh\n')
  const added = sections.find(section => section.title === 'New')
  assert.equal(added.status, 'added')
  assert.ok(added.ops.every(op => op.type === 'added'))
})

test('diff detects a removed section', () => {
  const sections = diffSections('# Title\nbody\n\n## Old\ngone\n', '# Title\nbody\n')
  const removed = sections.find(section => section.title === 'Old')
  assert.equal(removed.status, 'removed')
  assert.ok(removed.ops.every(op => op.type === 'removed'))
})

test('diff reports an unchanged section as identical', () => {
  const sections = diffSections('# Title\nsame line\n', '# Title\nsame line\n')
  assert.equal(sections.length, 1)
  assert.equal(sections[0].status, 'same')
  assert.ok(sections[0].ops.every(op => op.type === 'context'))
})

test('diff reports a modified line inside a section', () => {
  const sections = diffSections('# Title\nalpha\nbeta\n', '# Title\nalpha\ngamma\n')
  assert.equal(sections.length, 1)
  assert.equal(sections[0].status, 'changed')
  const removed = sections[0].ops.filter(op => op.type === 'removed').map(op => op.text)
  const added = sections[0].ops.filter(op => op.type === 'added').map(op => op.text)
  assert.deepEqual(removed, ['beta'])
  assert.deepEqual(added, ['gamma'])
})

test('diff normalizes line endings and trailing spaces', () => {
  const sections = diffSections('# Title\r\nalpha  \r\n', '# Title\nalpha\n')
  assert.equal(sections[0].status, 'same')
})

test('diff of an empty document yields no section', () => {
  assert.deepEqual(diffSections('', ''), [])
})

test('usage without provider data is unavailable, never a zero cost', () => {
  const summary = summarizeUsage({ usage_available: false, estimated_cost_usd: 0 })
  assert.equal(summary.usageAvailable, false)
  assert.equal(summary.costAvailable, false)
  assert.equal(summary.estimatedCostUsd, null)
  assert.equal(summary.totalTokens, null)
  assert.equal(summary.costIsEstimate, true)
})

test('usage without a pricing entry forbids any cost comparison', () => {
  const summary = summarizeUsage({
    usage_available: true,
    pricing_available: false,
    estimated_cost_usd: 1.23,
    total_tokens: 100,
  })
  assert.equal(summary.pricingAvailable, false)
  assert.equal(summary.costAvailable, false)
  assert.equal(summary.estimatedCostUsd, null)
  assert.equal(summary.totalTokens, 100)
})

test('usage exposes tokens, durations and an estimated cost', () => {
  const summary = summarizeUsage({
    usage_available: true,
    pricing_available: true,
    estimated_cost_usd: 0.42,
    theoretical_cost_usd: 1.5,
    currency: 'USD',
    prompt_tokens: 100,
    completion_tokens: 50,
    thinking_tokens: 25,
    total_tokens: 150,
    calls_count: 4,
    duration_seconds: 12.5,
    wall_seconds: 20.0,
    model: 'gemini-3.8-flash',
    reasoning_effort_requested: 'high',
    reasoning_effort_effective: 'high',
  })
  assert.equal(summary.costAvailable, true)
  assert.equal(summary.estimatedCostUsd, 0.42)
  assert.equal(summary.theoreticalCostUsd, 1.5)
  assert.equal(summary.totalTokens, 150)
  assert.equal(summary.thinkingTokens, 25)
  assert.equal(summary.callsCount, 4)
  assert.equal(summary.durationSeconds, 12.5)
  assert.equal(summary.wallSeconds, 20)
  assert.equal(summary.effortRequested, 'high')
})

test('a controlled stop exposes its reason and its translation key', () => {
  assert.equal(describeStopReason('budget_exceeded').i18nKey, STOP_REASON_I18N_KEYS.budget_exceeded)
  assert.equal(describeStopReason('timeout').i18nKey, 'step4.stopReasonTimeout')
  assert.equal(describeStopReason('pricing_unavailable').i18nKey, 'step4.stopReasonPricingUnavailable')
  assert.equal(describeStopReason('mystery').i18nKey, 'step4.stopReasonUnknown')
  assert.equal(describeStopReason(null), null)
})

test('a null or broken usage payload stays displayable', () => {
  for (const payload of [null, undefined, 'text', 42]) {
    const summary = summarizeUsage(payload)
    assert.equal(summary.usageAvailable, false)
    assert.equal(summary.costAvailable, false)
    assert.equal(summary.totalTokens, null)
  }
})

test('delta is a raw difference and refuses to invent a value', () => {
  assert.equal(computeDelta(10, 25), 15)
  assert.equal(computeDelta(25, 10), -15)
  assert.equal(computeDelta(null, 10), null)
  assert.equal(computeDelta(10, undefined), null)
  assert.equal(computeDelta('abc', 10), null)
})

test('running reports are detected from their status', () => {
  assert.equal(isRunningReport({ status: 'generating' }), true)
  assert.equal(isRunningReport({ status: 'planning' }), true)
  assert.equal(isRunningReport({ status: 'completed' }), false)
  assert.equal(isRunningReport(null), false)
})

test('short identifier drops the prefix and keeps the full one available', () => {
  assert.equal(shortReportId('report_abc123def456'), 'abc123de')
  assert.equal(shortReportId('report_short'), 'short')
  assert.equal(shortReportId(''), '')
})

test('history sorting compares instants, not date strings of mixed formats', () => {
  // Le serveur écrit une horodatage local naïf, le navigateur un horodatage
  // UTC : une comparaison lexicale des deux écritures rangeait l'entrée UTC
  // avant l'entrée locale pour tout décalage négatif.
  const entries = [
    { report_id: 'report_utc', created_at: '2026-10-20T07:32:00.000Z' },
    { report_id: 'report_local', created_at: '2026-10-20T02:32:00.123456' },
  ]
  const sorted = sortReportHistory(entries)
  // 02:32 locales précèdent 07:32 UTC : le tri suit l'instant, pas la chaîne.
  assert.deepEqual(sorted.map(entry => entry.report_id), ['report_local', 'report_utc'])
})

test('a heading inside a code fence is not a section title', () => {
  const markdown = [
    '# Titre réel',
    '',
    '```python',
    '# commentaire qui ressemble à un titre',
    'print("ok")',
    '```',
    '',
    '## Section suivante',
  ].join('\n')
  const sections = parseMarkdownSections(markdown)
  assert.deepEqual(sections.map(section => section.title), ['Titre réel', 'Section suivante'])
})

test('the usage summary of the history entry is the fallback of the usage payload', () => {
  const version = buildComparisonVersion({
    historyEntry: {
      report_id: 'report_historique',
      usage_summary: {
        usage_available: true,
        pricing_available: true,
        estimated_cost_usd: 0.42,
        currency: 'USD',
        total_tokens: 1234,
        stop_reason: 'budget_exceeded',
        stop_message: 'Plafond budgétaire atteint',
      },
    },
  })
  assert.equal(version.usage.usageAvailable, true)
  assert.equal(version.usage.totalTokens, 1234)
  assert.equal(version.usage.estimatedCostUsd, 0.42)
  assert.equal(version.stopReason.reason, 'budget_exceeded')
  assert.equal(version.stopMessage, 'Plafond budgétaire atteint')
})

test('an assembled version exposes the publication and claim breakdown', () => {
  const version = buildComparisonVersion({
    report: { report_id: 'report_details', simulation_id: 'sim_x' },
    quality: { publication_status: 'needs_review', is_publishable: false },
    claims: {
      total_claims: 10,
      verified_claims: 4,
      unsupported_claims: 5,
      contradicted_claims: 1,
      verification_ratio: 40.0,
    },
    historyEntry: { report_id: 'report_details', audit_available: true },
  })
  assert.equal(version.publicationStatus, 'needs_review')
  assert.equal(version.isPublishable, false)
  assert.equal(version.totalClaims, 10)
  assert.equal(version.supportedClaims, 4)
  assert.equal(version.unsupportedClaims, 5)
  assert.equal(version.contradictedClaims, 1)
  assert.equal(version.verificationRatio, 40.0)
  assert.equal(version.auditAvailable, true)
})

test('a version without quality result leaves publishability unknown', () => {
  const version = buildComparisonVersion({
    report: { report_id: 'report_sans_qualite' },
  })
  assert.equal(version.isPublishable, null)
  assert.equal(version.auditAvailable, false)
})
