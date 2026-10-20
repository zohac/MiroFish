import service from './index'

/**
 * 开始报告生成
 * @param {Object} data - { simulation_id, force_regenerate? }
 */
export const generateReport = (data) => {
  return service.post('/api/report/generate', data)
}

/**
 * 获取报告生成状态
 * @param {string} reportId
 */
export const getReportStatus = (reportId) => {
  return service.get(`/api/report/generate/status`, { params: { report_id: reportId } })
}

/**
 * 获取 Agent 日志（增量）
 * @param {string} reportId
 * @param {number} fromLine - 从第几行开始获取
 */
export const getAgentLog = (reportId, fromLine = 0) => {
  return service.get(`/api/report/${reportId}/agent-log`, { params: { from_line: fromLine } })
}

/**
 * 获取控制台日志（增量）
 * @param {string} reportId
 * @param {number} fromLine - 从第几行开始获取
 */
export const getConsoleLog = (reportId, fromLine = 0) => {
  return service.get(`/api/report/${reportId}/console-log`, { params: { from_line: fromLine } })
}

/**
 * 获取报告详情
 * @param {string} reportId
 */
export const getReport = (reportId) => {
  return service.get(`/api/report/${reportId}`)
}

/**
 * 与 Report Agent 对话
 * @param {Object} data - { simulation_id, message, chat_history? }
 */
export const chatWithReport = (data) => {
  return service.post('/api/report/chat', data)
}

/**
 * 获取报告质量检测结果 (Story 011-5, FR-09)
 * Ressource optionnelle : le fichier qualité n'existe qu'une fois la barrière
 * évaluée, son absence pendant la génération est normale (AC6).
 * @param {string} reportId
 */
export const getReportQuality = (reportId) => {
  return service.get(`/api/report/${reportId}/quality`, { suppressErrorLog: true })
}

/**
 * Obtenir l'URL de téléchargement du dossier d'audit du rapport (Story 011-5, FR-10)
 * @param {string} reportId
 */
export const getReportAuditDownloadUrl = (reportId) => {
  return `/api/report/${reportId}/audit/download`
}

/**
 * Obtenir l'URL de téléchargement du dossier d'audit de la simulation (Story 011-5, FR-10)
 * @param {string} simulationId
 */
export const getSimulationAuditDownloadUrl = (simulationId) => {
  return `/api/report/simulation/${simulationId}/audit/download`
}

/**
 * Obtenir l'historique complet des rapports d'une simulation (Story 013-3, FR-06)
 * @param {string} simulationId
 */
export const getReportHistory = (simulationId) => {
  return service.get(`/api/report/simulation/${simulationId}/history`)
}

/**
 * Obtenir la télémétrie d'usage d'un rapport (Story 013-4, FR-08)
 * Ressource optionnelle : un rapport antérieur à la story 013-4 n'a pas
 * d'usage.json, et son absence est un état normal, pas une erreur (AC6).
 * @param {string} reportId
 */
export const getReportUsage = (reportId) => {
  return service.get(`/api/report/${reportId}/usage`, { suppressErrorLog: true })
}

/**
 * Obtenir le registre des affirmations d'un rapport (Story 013-3, FR-06)
 * Ressource optionnelle : l'absence de registre est un état normal (AC6).
 * @param {string} reportId
 */
export const getReportClaims = (reportId) => {
  return service.get(`/api/report/${reportId}/claims`, { suppressErrorLog: true })
}

/**
 * Obtenir le catalogue serveur des profils LLM de rapport (Story 013-5, FR-08)
 * Aucun secret n'est exposé : ce sont des métadonnées de modèle.
 */
export const getReportProfiles = () => {
  return service.get('/api/report/profiles')
}
