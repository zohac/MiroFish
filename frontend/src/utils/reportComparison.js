// Fonctions pures de comparaison de rapports (Story 013-5, FR-08, C6).
//
// Règles :
//   - Aucune dépendance, aucune requête réseau, aucun état global : le module
//     est testable hors navigateur (node --test).
//   - Aucune décision de supériorité : le module compare des faits, il ne
//     désigne jamais de « modèle gagnant ». L'arbitrage appartient à la revue
//     aveugle de la story 013-6.
//   - Aucun secret : seules des métadonnées déjà exposées par l'API sont
//     manipulées ici.

/** Motifs de non-comparabilité, dans un ordre stable. */
export const COMPARABILITY_REASONS = Object.freeze({
  /** L'un des deux rapports ne porte aucun instantané de preuves figées. */
  SNAPSHOT_ABSENT: 'snapshot_absent',
  /** Les deux rapports ne portent pas la même simulation. */
  SIMULATION_MISMATCH: 'simulation_mismatch',
  /** Les empreintes SHA-256 des preuves diffèrent : preuves distinctes. */
  EVIDENCE_MISMATCH: 'evidence_mismatch',
  /** Les identifiants d'instantané diffèrent et aucune empreinte ne permet de conclure. */
  SNAPSHOT_MISMATCH: 'snapshot_mismatch',
  /** Les instantanés coïncident mais l'empreinte n'est pas exposée des deux côtés. */
  HASH_UNAVAILABLE: 'hash_unavailable',
})

/** Clés i18n des motifs d'arrêt contrôlé (Story 013-4). */
export const STOP_REASON_I18N_KEYS = Object.freeze({
  budget_exceeded: 'step4.stopReasonBudgetExceeded',
  timeout: 'step4.stopReasonTimeout',
  pricing_unavailable: 'step4.stopReasonPricingUnavailable',
  stopped: 'step4.stopReasonStopped',
})

/** Statuts de rapport considérés comme « en cours ». */
export const RUNNING_REPORT_STATUSES = Object.freeze(['pending', 'planning', 'generating'])

/** Nombre maximal de cellules de la matrice LCS au-delà duquel on diffère. */
const MAX_LCS_CELLS = 1000000

function firstNonEmpty(...values) {
  for (const value of values) {
    if (value === null || value === undefined) continue
    const text = String(value).trim()
    if (text) return text
  }
  return null
}

function asFiniteNumber(value) {
  if (value === null || value === undefined || value === '' || typeof value === 'boolean') return null
  const numeric = Number(value)
  return Number.isFinite(numeric) ? numeric : null
}

function asTrimmedString(value) {
  if (value === null || value === undefined || typeof value === 'boolean') return null
  const text = String(value).trim()
  return text || null
}

/**
 * Extrait l'identité des preuves d'un rapport, quelle que soit sa forme.
 *
 * Trois sources sont acceptées : l'entrée d'historique
 * (`evidence_snapshot_id` / `evidence_snapshot_sha256`), le détail d'un
 * rapport (`evidence_snapshot.snapshot_id` / `evidence_snapshot.sha256_hash`)
 * et la version déjà assemblée par `buildComparisonVersion`
 * (`snapshotId` / `sha256`).
 */
export function readEvidenceFingerprint(source) {
  const empty = { snapshotId: null, sha256: null }
  if (!source || typeof source !== 'object') return empty
  const snapshot = source.evidence_snapshot && typeof source.evidence_snapshot === 'object'
    ? source.evidence_snapshot
    : {}
  return {
    snapshotId: firstNonEmpty(
      source.evidence_snapshot_id,
      snapshot.snapshot_id,
      source.snapshotId,
    ),
    sha256: firstNonEmpty(
      source.evidence_snapshot_sha256,
      snapshot.sha256_hash,
      source.sha256,
    ),
  }
}

/** Lit l'identifiant de simulation quelle que soit la forme de la source. */
export function readSimulationId(source) {
  if (!source || typeof source !== 'object') return null
  return firstNonEmpty(source.simulation_id, source.simulationId)
}

/**
 * Trie l'historique des rapports du plus ancien au plus récent.
 *
 * Le tri se fait sur l'instant, pas sur la chaîne : le serveur écrit une
 * horodatage local naïf (`2026-10-20T09:32:00.123456`) et le navigateur
 * produit un horodatage UTC (`2026-10-20T07:32:00.000Z`). Une comparaison
 * lexicale des deux formats rangeait l'entrée UTC avant l'entrée locale pour
 * tout décalage négatif (Story 013-5, revue BMAD du 20 octobre 2026). Le
 * repli stable sur `report_id` est conservé en cas d'égalité ou d'absence.
 */
export function sortReportHistory(reports) {
  if (!Array.isArray(reports)) return []
  return [...reports].sort((left, right) => {
    const leftStamp = parseTimestamp(left && left.created_at)
    const rightStamp = parseTimestamp(right && right.created_at)
    if (leftStamp !== null && rightStamp !== null && leftStamp !== rightStamp) {
      return leftStamp < rightStamp ? -1 : 1
    }
    const leftKey = String((left && left.created_at) || '')
    const rightKey = String((right && right.created_at) || '')
    if (leftKey !== rightKey) return leftKey < rightKey ? -1 : 1
    const leftId = String((left && left.report_id) || '')
    const rightId = String((right && right.report_id) || '')
    if (leftId === rightId) return 0
    return leftId < rightId ? -1 : 1
  })
}

/**
 * Convertit un horodatage en millisecondes, ou `null` s'il est illisible.
 *
 * `Date.parse` interprets un horodatage sans décalage comme l'heure locale et
 * un horodatage suffixé `Z` comme l'UTC : les deux écritures du dépôt sont
 * donc comparables sans conversion manuelle.
 */
function parseTimestamp(value) {
  if (value === null || value === undefined || value === '') return null
  const stamp = Date.parse(String(value))
  return Number.isNaN(stamp) ? null : stamp
}

/**
 * Indique si une entrée d'historique (ou une chaîne brute de statut) décrit un rapport encore en cours.
 */
export function isRunningReport(entry) {
  if (!entry) return false
  if (typeof entry === 'string') {
    return RUNNING_REPORT_STATUSES.includes(entry.trim().toLowerCase())
  }
  if (typeof entry !== 'object') return false
  return RUNNING_REPORT_STATUSES.includes(String(entry.status || '').trim().toLowerCase())
}

/**
 * Raccourci d'identifiant de rapport pour l'affichage (le complet reste lisible
 * via l'attribut `title`).
 */
export function shortReportId(reportId) {
  const text = String(reportId || '').trim()
  if (!text) return ''
  const withoutPrefix = text.includes('_') ? text.slice(text.indexOf('_') + 1) : text
  return withoutPrefix.length > 8 ? withoutPrefix.slice(0, 8) : withoutPrefix
}

/**
 * Décide si deux rapports peuvent être comparés sur des preuves identiques.
 *
 * L'identité des preuves est établie par l'empreinte SHA-256 lorsqu'elle est
 * exposée des deux côtés : c'est la seule adresse de contenu des preuves
 * figées. L'identifiant d'instantané est un identifiant de *capture* (uuid) :
 * deux générations successives sur les mêmes preuves portent deux identifiants
 * distincts pour une empreinte identique, et l'inverse est impossible.
 *
 * Le verdict ne dit jamais quel rapport est meilleur : il dit seulement si la
 * comparaison est contrôlée.
 */
export function evaluateComparability(left, right) {
  const leftFingerprint = readEvidenceFingerprint(left)
  const rightFingerprint = readEvidenceFingerprint(right)
  const leftSimulation = readSimulationId(left)
  const rightSimulation = readSimulationId(right)

  const details = {
    leftSnapshotId: leftFingerprint.snapshotId,
    rightSnapshotId: rightFingerprint.snapshotId,
    leftSha256: leftFingerprint.sha256,
    rightSha256: rightFingerprint.sha256,
    evidenceIdentity: null,
  }
  const reasons = []

  if (!leftFingerprint.snapshotId || !rightFingerprint.snapshotId) {
    reasons.push(COMPARABILITY_REASONS.SNAPSHOT_ABSENT)
    return { comparable: false, reasons, ...details }
  }

  if (leftSimulation && rightSimulation && leftSimulation !== rightSimulation) {
    reasons.push(COMPARABILITY_REASONS.SIMULATION_MISMATCH)
    return { comparable: false, reasons, ...details }
  }

  if (leftFingerprint.sha256 && rightFingerprint.sha256) {
    if (leftFingerprint.sha256 === rightFingerprint.sha256) {
      details.evidenceIdentity = 'sha256'
      return { comparable: true, reasons, ...details }
    }
    reasons.push(COMPARABILITY_REASONS.EVIDENCE_MISMATCH)
    return { comparable: false, reasons, ...details }
  }

  if (leftFingerprint.snapshotId === rightFingerprint.snapshotId) {
    reasons.push(COMPARABILITY_REASONS.HASH_UNAVAILABLE)
    details.evidenceIdentity = 'snapshot_id'
    return { comparable: true, reasons, ...details }
  }

  reasons.push(COMPARABILITY_REASONS.SNAPSHOT_MISMATCH)
  return { comparable: false, reasons, ...details }
}

/**
 * Découpe un Markdown en sections titrées.
 *
 * Le contenu placé avant le premier titre constitue une section de préambule
 * (titre vide). Chaque section conserve ses lignes brutes, normalisées.
 *
 * Les blocs de code délimités par des accents graves sont respectés : une
 * ligne `#` qui y figure est du code, pas un titre. Sans cette garde, le diff
 * par section découperait le rapport au mauvais endroit, sans aucun indice
 * visuel pour l'utilisateur (Story 013-5, revue BMAD du 20 octobre 2026).
 */
export function parseMarkdownSections(markdown) {
  const text = typeof markdown === 'string' ? markdown : ''
  const lines = text.replace(/\r\n/g, '\n').split('\n')
  const sections = []
  let current = { title: '', lines: [] }
  let inCodeFence = false
  for (const rawLine of lines) {
    const line = rawLine.replace(/\s+$/, '')
    if (/^\s*```/.test(line)) {
      inCodeFence = !inCodeFence
      current.lines.push(line)
      continue
    }
    const heading = inCodeFence ? null : line.match(/^(#{1,6})\s+(.*)$/)
    if (heading) {
      if (current.lines.length > 0 || current.title !== '') sections.push(current)
      current = { title: heading[2].trim(), lines: [] }
      continue
    }
    current.lines.push(line)
  }
  if (current.lines.length > 0 || current.title !== '') sections.push(current)
  // Un préambule entièrement vide (document vide) n'est pas une section.
  return sections.filter(
    section => section.title !== '' || section.lines.some(line => line.trim() !== ''),
  )
}

function lcsDiff(leftLines, rightLines) {
  if (leftLines.length === 0) return rightLines.map(text => ({ type: 'added', text }))
  if (rightLines.length === 0) return leftLines.map(text => ({ type: 'removed', text }))

  if (leftLines.length * rightLines.length > MAX_LCS_CELLS) {
    // Repli déterministe : le bloc est remplacé en bloc plutôt que calculé.
    return [
      ...leftLines.map(text => ({ type: 'removed', text })),
      ...rightLines.map(text => ({ type: 'added', text })),
    ]
  }

  const rows = leftLines.length
  const cols = rightLines.length
  const table = Array.from({ length: rows + 1 }, () => new Uint32Array(cols + 1))
  for (let i = rows - 1; i >= 0; i -= 1) {
    for (let j = cols - 1; j >= 0; j -= 1) {
      table[i][j] = leftLines[i] === rightLines[j]
        ? table[i + 1][j + 1] + 1
        : Math.max(table[i + 1][j], table[i][j + 1])
    }
  }

  const ops = []
  let i = 0
  let j = 0
  while (i < rows && j < cols) {
    if (leftLines[i] === rightLines[j]) {
      ops.push({ type: 'context', text: leftLines[i] })
      i += 1
      j += 1
    } else if (table[i + 1][j] >= table[i][j + 1]) {
      ops.push({ type: 'removed', text: leftLines[i] })
      i += 1
    } else {
      ops.push({ type: 'added', text: rightLines[j] })
      j += 1
    }
  }
  while (i < rows) {
    ops.push({ type: 'removed', text: leftLines[i] })
    i += 1
  }
  while (j < cols) {
    ops.push({ type: 'added', text: rightLines[j] })
    j += 1
  }
  return ops
}

function diffLines(leftLines, rightLines) {
  let start = 0
  while (
    start < leftLines.length &&
    start < rightLines.length &&
    leftLines[start] === rightLines[start]
  ) start += 1

  let endLeft = leftLines.length
  let endRight = rightLines.length
  while (
    endLeft > start &&
    endRight > start &&
    leftLines[endLeft - 1] === rightLines[endRight - 1]
  ) {
    endLeft -= 1
    endRight -= 1
  }

  const ops = []
  for (let index = 0; index < start; index += 1) {
    ops.push({ type: 'context', text: leftLines[index] })
  }
  ops.push(...lcsDiff(leftLines.slice(start, endLeft), rightLines.slice(start, endRight)))
  for (let index = endLeft; index < leftLines.length; index += 1) {
    ops.push({ type: 'context', text: leftLines[index] })
  }
  return ops
}

function groupByTitle(sections) {
  const groups = new Map()
  for (const section of sections) {
    const key = section.title
    if (!groups.has(key)) groups.set(key, [])
    groups.get(key).push(section)
  }
  return groups
}

/**
 * Compare deux rapports Markdown section par section.
 *
 * Une section absente d'un côté est marquée « ajoutée » ou « supprimée ». Les
 * lignes sont normalisées (fins de ligne et espaces de bord) avant comparaison.
 * Le résultat est du texte brut : aucun HTML n'est produit, donc aucune
 * injection n'est possible dans l'IHM.
 */
export function diffSections(markdownA, markdownB) {
  const leftGroups = groupByTitle(parseMarkdownSections(markdownA))
  const rightGroups = groupByTitle(parseMarkdownSections(markdownB))

  const orderedTitles = []
  for (const title of leftGroups.keys()) orderedTitles.push(title)
  for (const title of rightGroups.keys()) {
    if (!leftGroups.has(title)) orderedTitles.push(title)
  }

  return orderedTitles.map(title => {
    const leftOccurrences = leftGroups.get(title) || []
    const rightOccurrences = rightGroups.get(title) || []
    const occurrenceCount = Math.max(leftOccurrences.length, rightOccurrences.length)
    const results = []

    for (let index = 0; index < occurrenceCount; index += 1) {
      const left = leftOccurrences[index]
      const right = rightOccurrences[index]
      if (!left && right) {
        results.push({
          title,
          status: 'added',
          ops: right.lines.map(text => ({ type: 'added', text })),
        })
        continue
      }
      if (left && !right) {
        results.push({
          title,
          status: 'removed',
          ops: left.lines.map(text => ({ type: 'removed', text })),
        })
        continue
      }
      const ops = diffLines(left.lines, right.lines)
      const changed = ops.some(op => op.type !== 'context')
      results.push({
        title,
        status: changed ? 'changed' : 'same',
        ops,
      })
    }

    return results
  }).flat()
}

/**
 * Décrit un motif d'arrêt contrôlé, avec sa clé de traduction.
 */
export function describeStopReason(stopReason) {
  const normalized = String(stopReason || '').trim().toLowerCase()
  if (!normalized) return null
  return {
    reason: normalized,
    i18nKey: STOP_REASON_I18N_KEYS[normalized] || 'step4.stopReasonUnknown',
  }
}

/**
 * Résume la télémétrie d'usage d'un rapport en vue d'affichage honnête.
 *
 * Contrat d'honnêteté (AC4) :
 *   - `usage_available === false` ⇒ aucune métrique chiffrée n'est affirmée ;
 *     le coût ne vaut jamais « 0 $ », il est « indisponible » ;
 *   - `pricing_available === false` ⇒ aucune comparaison de coût n'est possible ;
 *   - le coût affiché est une **estimation**, jamais une facture.
 */
export function summarizeUsage(usage) {
  const source = usage && typeof usage === 'object' ? usage : {}
  const usageAvailable = source.usage_available === true
  const pricingAvailable = source.pricing_available !== false
  const estimatedCostUsd = asFiniteNumber(source.estimated_cost_usd)
  const theoreticalCostUsd = asFiniteNumber(source.theoretical_cost_usd)
  const costAvailable = usageAvailable && pricingAvailable && estimatedCostUsd !== null

  return {
    usageAvailable,
    pricingAvailable,
    costAvailable,
    costIsEstimate: true,
    currency: asTrimmedString(source.currency) || 'USD',
    model: asTrimmedString(source.model),
    providerId: asTrimmedString(source.provider_id),
    profileId: asTrimmedString(source.profile_id),
    effortRequested: asTrimmedString(source.reasoning_effort_requested),
    effortEffective: asTrimmedString(source.reasoning_effort_effective),
    promptTokens: usageAvailable ? asFiniteNumber(source.prompt_tokens) : null,
    completionTokens: usageAvailable ? asFiniteNumber(source.completion_tokens) : null,
    thinkingTokens: usageAvailable ? asFiniteNumber(source.thinking_tokens) : null,
    totalTokens: usageAvailable ? asFiniteNumber(source.total_tokens) : null,
    callsCount: usageAvailable ? asFiniteNumber(source.calls_count) : null,
    durationSeconds: usageAvailable ? asFiniteNumber(source.duration_seconds) : null,
    wallSeconds: usageAvailable ? asFiniteNumber(source.wall_seconds) : null,
    estimatedCostUsd: costAvailable ? estimatedCostUsd : null,
    theoreticalCostUsd: usageAvailable && pricingAvailable ? theoreticalCostUsd : null,
    stopReason: asTrimmedString(source.stop_reason),
    stopMessage: asTrimmedString(source.stop_message),
    budgetExceeded: source.budget_exceeded === true,
    timeoutExceeded: source.timeout_exceeded === true,
  }
}

/**
 * Écart brut entre deux valeurs numériques, ou `null` si l'une des deux est
 * absente. Aucun signe n'est interprété : l'IHM affiche une différence, pas
 * un classement.
 */
export function computeDelta(leftValue, rightValue) {
  const left = asFiniteNumber(leftValue)
  const right = asFiniteNumber(rightValue)
  if (left === null || right === null) return null
  return right - left
}

/**
 * Assemble une « version de rapport » comparable à partir des quatre sources
 * disponibles : détail du rapport, télémétrie d'usage, résultat de la barrière
 * qualité et registre des affirmations (l'entrée d'historique sert de repli).
 *
 * Règle d'honnêteté : `is_publishable` est lu tel quel dans le résultat de la
 * barrière. Il n'est jamais déduit de `final_status` (AC4).
 */
export function buildComparisonVersion({
  report = null,
  usage = null,
  quality = null,
  claims = null,
  historyEntry = null,
} = {}) {
  const details = report && typeof report === 'object' ? report : {}
  const entry = historyEntry && typeof historyEntry === 'object' ? historyEntry : {}
  const qualityData = quality && typeof quality === 'object' ? quality : {}
  const claimsData = claims && typeof claims === 'object' ? claims : {}

  const detailFingerprint = readEvidenceFingerprint(details)
  const entryFingerprint = readEvidenceFingerprint(entry)
  const fingerprint = {
    snapshotId: detailFingerprint.snapshotId || entryFingerprint.snapshotId,
    sha256: detailFingerprint.sha256 || entryFingerprint.sha256,
  }

  // Repli sur le résumé d'usage porté par l'entrée d'historique : un rapport
  // dont le fichier `usage.json` est absent (antérieur à la story 013-4, ou
  // effacé) reste ainsi lisible, au lieu d'afficher « indisponible » partout
  // (Story 013-5, note 5 des Notes de développement).
  const usageSource = usage && typeof usage === 'object' && Object.keys(usage).length > 0
    ? usage
    : (entry.usage_summary && typeof entry.usage_summary === 'object' ? entry.usage_summary : null)
  const usageSummary = summarizeUsage(usageSource)
  const reportId = asTrimmedString(details.report_id) || asTrimmedString(entry.report_id)

  const totalClaims = asFiniteNumber(claimsData.total_claims)
    ?? asFiniteNumber(entry.total_claims)
  const supportedClaims = asFiniteNumber(claimsData.verified_claims)
    ?? asFiniteNumber(entry.supported_claims)
  const unsupportedClaims = asFiniteNumber(claimsData.unsupported_claims)
    ?? asFiniteNumber(entry.unsupported_claims)
  const contradictedClaims = asFiniteNumber(claimsData.contradicted_claims)
    ?? asFiniteNumber(entry.contradicted_claims)

  return {
    reportId,
    shortId: shortReportId(reportId),
    simulationId: asTrimmedString(details.simulation_id) || asTrimmedString(entry.simulation_id),
    profileId: asTrimmedString(details.profile_id) || asTrimmedString(entry.profile_id),
    model: usageSummary.model
      || asTrimmedString(details.llm_profile && details.llm_profile.model),
    providerId: usageSummary.providerId,
    effortRequested: usageSummary.effortRequested
      || asTrimmedString(details.llm_profile && details.llm_profile.reasoning_effort),
    effortEffective: usageSummary.effortEffective,
    replayMode: asTrimmedString(details.replay_mode) || asTrimmedString(entry.replay_mode),
    publicationStatus: asTrimmedString(qualityData.publication_status)
      || asTrimmedString(entry.publication_status),
    isPublishable: qualityData.is_publishable === true
      ? true
      : (qualityData.is_publishable === false ? false : null),
    totalClaims,
    supportedClaims,
    unsupportedClaims,
    contradictedClaims,
    verificationRatio: asFiniteNumber(claimsData.verification_ratio),
    adoptionRate: asFiniteNumber(entry.adoption_rate),
    usage: usageSummary,
    stopReason: describeStopReason(usageSummary.stopReason),
    stopMessage: usageSummary.stopMessage,
    auditAvailable: entry.audit_available === true,
    snapshotId: fingerprint.snapshotId,
    sha256: fingerprint.sha256,
    markdown: typeof details.markdown_content === 'string' ? details.markdown_content : '',
    createdAt: asTrimmedString(details.created_at) || asTrimmedString(entry.created_at),
    status: asTrimmedString(details.status) || asTrimmedString(entry.status),
  }
}

/**
 * Détermine de façon déterministe l'état d'affichage de chaque métrique
 * de télémétrie du rapport (Story 015-5, AC6).
 *
 * États possibles par métrique :
 *   - 'ready'       : donnée mesurée et prête à formater
 *   - 'pending'     : génération en cours, valeur en attente de premier calcul
 *   - 'unpriced'    : tokens mesurés mais modèle absent de la table de tarification
 *   - 'unavailable' : donnée non disponible (rapport terminé sans artefact, etc.)
 *
 * @param {Object} params
 * @param {Object|null} params.usage Résumé produit par summarizeUsage()
 * @param {Object|null} params.claims Registre des claims (report_claims.json)
 * @param {boolean} params.isGenerating Rapport activement en cours de génération
 * @param {number|null} [params.fallbackElapsedSeconds] Temps écoulé alternatif
 * @returns {Object} États et valeurs pour tokens, inference, wall, cost, claims
 */
export function resolveLiveTelemetryDisplay({
  usage = null,
  claims = null,
  isGenerating = false,
  fallbackElapsedSeconds = null,
} = {}) {
  const hasUsage = usage && typeof usage === 'object' && usage.usageAvailable === true
  const totalTokens = hasUsage && typeof usage.totalTokens === 'number' ? usage.totalTokens : null
  const durationSeconds = hasUsage && typeof usage.durationSeconds === 'number' ? usage.durationSeconds : null
  const wallSeconds = hasUsage && typeof usage.wallSeconds === 'number'
    ? usage.wallSeconds
    : (isGenerating && typeof fallbackElapsedSeconds === 'number' && Number.isFinite(fallbackElapsedSeconds) ? fallbackElapsedSeconds : null)

  // 1. Tokens
  let tokensState = 'unavailable'
  if (totalTokens !== null) {
    tokensState = 'ready'
  } else if (isGenerating) {
    tokensState = 'pending'
  }

  // 2. Durée d'inférence
  let inferenceState = 'unavailable'
  if (durationSeconds !== null) {
    inferenceState = 'ready'
  } else if (isGenerating) {
    inferenceState = 'pending'
  }

  // 3. Temps mural
  let wallState = 'unavailable'
  if (wallSeconds !== null) {
    wallState = 'ready'
  } else if (isGenerating) {
    wallState = 'pending'
  }

  // 4. Coût estimé
  let costState = 'unavailable'
  if (hasUsage) {
    if (usage.costAvailable === true && typeof usage.estimatedCostUsd === 'number') {
      costState = 'ready'
    } else if (usage.pricingAvailable === false) {
      costState = 'unpriced'
    } else if (isGenerating) {
      costState = 'pending'
    }
  } else if (isGenerating) {
    costState = 'pending'
  }

  // 5. Affirmations (claims)
  let claimsState = 'unavailable'
  const claimsTotal = claims && typeof claims === 'object' && typeof claims.total_claims === 'number'
    ? claims.total_claims
    : null
  const claimsVerified = claims && typeof claims === 'object' && typeof claims.verified_claims === 'number'
    ? claims.verified_claims
    : null
  if (claimsTotal !== null && claimsVerified !== null) {
    claimsState = 'ready'
  } else if (isGenerating) {
    claimsState = 'pending'
  }

  return {
    tokens: { state: tokensState, value: totalTokens },
    inferenceDuration: { state: inferenceState, value: durationSeconds },
    wallDuration: { state: wallState, value: wallSeconds },
    cost: {
      state: costState,
      value: costState === 'ready' ? usage.estimatedCostUsd : null,
      currency: (usage && usage.currency) || 'USD',
    },
    claims: {
      state: claimsState,
      total: claimsTotal,
      verified: claimsVerified,
    },
  }
}
