<template>
  <div 
    class="history-database"
    ref="historyContainer"
  >
    <!-- 背景装饰：技术网格线 -->
    <div class="tech-grid-bg">
      <div class="grid-pattern"></div>
      <div class="gradient-overlay"></div>
    </div>

    <!-- 标题区域 -->
    <div class="section-header">
      <div class="section-line"></div>
      <div class="section-title-wrap">
        <span class="section-title">{{ $t('history.title') }}</span>
        <span v-if="totalCount > 0" class="total-badge">{{ formatNumber(totalCount) }}</span>
      </div>
      <div class="section-line"></div>
    </div>

    <!-- 顶栏控制栏：搜索、筛选与刷新 -->
    <div class="history-controls">
      <!-- 搜索输入框 -->
      <div class="search-input-wrapper">
        <span class="search-icon">⌕</span>
        <input 
          type="text"
          v-model="searchQuery"
          :placeholder="$t('history.searchPlaceholder')"
          class="search-input"
          @keydown.esc="clearSearch"
        />
        <button 
          v-if="searchQuery" 
          class="clear-search-btn"
          @click="clearSearch"
          :title="$t('common.close')"
        >×</button>
      </div>

      <!-- 状态筛选胶囊 -->
      <div class="status-filters">
        <button 
          class="filter-pill"
          :class="{ active: activeFilter === 'all' }"
          @click="setFilter('all')"
        >
          {{ $t('history.filterAll') }}
        </button>
        <button 
          class="filter-pill"
          :class="{ active: activeFilter === 'completed' }"
          @click="setFilter('completed')"
        >
          <span class="pill-dot dot-completed">●</span>
          {{ $t('history.filterCompleted') }}
        </button>
        <button 
          class="filter-pill"
          :class="{ active: activeFilter === 'in_progress' }"
          @click="setFilter('in_progress')"
        >
          <span class="pill-dot dot-in-progress">●</span>
          {{ $t('history.filterInProgress') }}
        </button>
        <button 
          class="filter-pill"
          :class="{ active: activeFilter === 'has_report' }"
          @click="setFilter('has_report')"
        >
          <span class="pill-dot dot-report">◆</span>
          {{ $t('history.filterHasReport') }}
        </button>
      </div>

      <!-- 刷新按钮 -->
      <button 
        class="refresh-btn"
        :class="{ spinning: loading }"
        @click="refreshHistory"
        :title="$t('history.refresh')"
      >
        <span class="refresh-icon">↻</span>
      </button>
    </div>

    <!-- 加载中指示器 (初始全屏) -->
    <div v-if="loading && projects.length === 0" class="loading-state">
      <span class="loading-spinner"></span>
      <span class="loading-text">{{ $t('history.loadingText') }}</span>
    </div>

    <!-- 空状态：无项目或无搜索结果 -->
    <div v-else-if="projects.length === 0" class="empty-results">
      <div class="empty-icon">◇</div>
      <p class="empty-title">{{ hasActiveFilters ? $t('history.noResultsFound') : $t('history.noFiles') }}</p>
      <button 
        v-if="hasActiveFilters" 
        class="reset-filters-btn"
        @click="resetAllFilters"
      >
        {{ $t('history.resetFilters') }}
      </button>
    </div>

    <!-- 卡片网格容器 -->
    <div v-else class="cards-grid-wrapper">
      <div class="cards-grid">
        <div 
          v-for="project in projects" 
          :key="project.simulation_id"
          class="project-card"
          @click="navigateToProject(project)"
        >
          <!-- 角落取景框装饰 -->
          <div class="corner-mark top-left"></div>
          <div class="corner-mark bottom-right"></div>

          <!-- 卡片头部：simulation_id + 复制 + 功能状态图标 -->
          <div class="card-header">
            <div class="card-id-wrap" @click.stop="copySimulationId(project.simulation_id)">
              <span class="card-id">{{ formatSimulationId(project.simulation_id) }}</span>
              <span class="copy-icon" :title="$t('history.copyId')">
                {{ copiedId === project.simulation_id ? '✓' : '⧉' }}
              </span>
            </div>

            <!-- 功能可用指示器 -->
            <div class="card-status-icons">
              <span 
                class="status-icon" 
                :class="{ available: project.project_id, unavailable: !project.project_id }"
                :title="$t('history.graphBuild')"
              >◇</span>
              <span 
                class="status-icon available" 
                :title="$t('history.envSetup')"
              >◈</span>
              <span 
                class="status-icon" 
                :class="{ available: project.report_id, unavailable: !project.report_id }"
                :title="$t('history.analysisReport')"
              >◆</span>
            </div>
          </div>

          <!-- 文件列表区域 -->
          <div class="card-files-wrapper">
            <div class="files-list" v-if="project.files && project.files.length > 0">
              <div 
                v-for="(file, fileIndex) in project.files.slice(0, 2)" 
                :key="fileIndex"
                class="file-item"
              >
                <span class="file-tag" :class="getFileType(file.filename)">{{ getFileTypeLabel(file.filename) }}</span>
                <span class="file-name">{{ truncateFilename(file.filename, 22) }}</span>
              </div>
              <div v-if="project.files.length > 2" class="files-more">
                {{ $t('history.moreFiles', { count: project.files.length - 2 }) }}
              </div>
            </div>
            <div class="files-empty" v-else>
              <span class="empty-file-icon">◇</span>
              <span class="empty-file-text">{{ $t('history.noFiles') }}</span>
            </div>
          </div>

          <!-- 项目名称标签（如有） -->
          <div v-if="project.project_name" class="card-project-name">
            <span class="project-tag-icon">📁</span>
            <span class="project-tag-text">{{ truncateText(project.project_name, 28) }}</span>
          </div>

          <!-- 卡片标题 -->
          <h3 class="card-title">{{ getSimulationTitle(project.simulation_requirement) }}</h3>

          <!-- 卡片描述 -->
          <p class="card-desc">{{ truncateText(project.simulation_requirement, 70) }}</p>

          <!-- 卡片底部：时间、进度与报告直达 -->
          <div class="card-footer">
            <div class="card-datetime">
              <span class="card-date">{{ formatDate(project.created_at) }}</span>
              <span class="card-time">{{ formatTime(project.created_at) }}</span>
            </div>

            <div class="footer-right">
              <!-- 直达报告按钮 (如果可用) -->
              <button 
                v-if="project.report_id"
                class="direct-report-pill"
                @click.stop="goToReportDirect(project.report_id)"
                :title="$t('history.viewReportDirect')"
              >
                ◆ {{ $t('history.viewReportDirect') }}
              </button>

              <span class="card-progress" :class="getProgressClass(project)">
                <span class="status-dot">●</span> {{ formatRounds(project) }}
              </span>
            </div>
          </div>

          <!-- 底部 hover 装饰线 -->
          <div class="card-bottom-line"></div>
        </div>
      </div>

      <!-- 加载更多区域 -->
      <div v-if="hasMore || loadingMore" class="load-more-section">
        <button 
          class="load-more-btn"
          @click="loadMore"
          :disabled="loadingMore"
        >
          <span v-if="loadingMore" class="loading-spinner-sm"></span>
          <span>{{ loadingMore ? $t('history.loadingMore') : $t('history.loadMore') }}</span>
          <span v-if="!loadingMore" class="count-hint">({{ projects.length }} / {{ totalCount }})</span>
        </button>
      </div>
    </div>

    <!-- 历史回放详情弹窗 (Modal) -->
    <Teleport to="body">
      <Transition name="modal">
        <div v-if="selectedProject" class="modal-overlay" @click.self="closeModal">
          <div class="modal-content">
            <!-- 弹窗头部 -->
            <div class="modal-header">
              <div class="modal-title-section">
                <span class="modal-id">{{ formatSimulationId(selectedProject.simulation_id) }}</span>
                <span class="modal-progress" :class="getProgressClass(selectedProject)">
                  <span class="status-dot">●</span> {{ formatRounds(selectedProject) }}
                </span>
                <span class="modal-create-time">{{ formatDate(selectedProject.created_at) }} {{ formatTime(selectedProject.created_at) }}</span>
              </div>
              <button class="modal-close" @click="closeModal">×</button>
            </div>

            <!-- 弹窗内容 -->
            <div class="modal-body">
              <!-- 项目名称（如有） -->
              <div v-if="selectedProject.project_name" class="modal-section">
                <div class="modal-label">{{ $t('ui.projectName') }}</div>
                <div class="modal-project-name">{{ selectedProject.project_name }}</div>
              </div>

              <!-- 模拟需求 -->
              <div class="modal-section">
                <div class="modal-label">{{ $t('history.simRequirement') }}</div>
                <div class="modal-requirement">{{ selectedProject.simulation_requirement || $t('common.none') }}</div>
              </div>

              <!-- 文件列表 -->
              <div class="modal-section">
                <div class="modal-label">{{ $t('history.relatedFiles') }}</div>
                <div class="modal-files" v-if="selectedProject.files && selectedProject.files.length > 0">
                  <div v-for="(file, index) in selectedProject.files" :key="index" class="modal-file-item">
                    <span class="file-tag" :class="getFileType(file.filename)">{{ getFileTypeLabel(file.filename) }}</span>
                    <span class="modal-file-name">{{ file.filename }}</span>
                  </div>
                </div>
                <div class="modal-empty" v-else>{{ $t('history.noRelatedFiles') }}</div>
              </div>
            </div>

            <!-- 推演回放分割线 -->
            <div class="modal-divider">
              <span class="divider-line"></span>
              <span class="divider-text">{{ $t('history.replayTitle') }}</span>
              <span class="divider-line"></span>
            </div>

            <!-- 导航按钮 -->
            <div class="modal-actions">
              <button 
                class="modal-btn btn-project" 
                @click="goToProject"
                :disabled="!selectedProject.project_id"
              >
                <span class="btn-step">Step1</span>
                <span class="btn-icon">◇</span>
                <span class="btn-text">{{ $t('history.step1Button') }}</span>
              </button>
              <button 
                class="modal-btn btn-simulation" 
                @click="goToSimulation"
              >
                <span class="btn-step">Step2</span>
                <span class="btn-icon">◈</span>
                <span class="btn-text">{{ $t('history.step2Button') }}</span>
              </button>
              <button 
                class="modal-btn btn-report" 
                @click="goToReport"
                :disabled="!selectedProject.report_id"
              >
                <span class="btn-step">Step4</span>
                <span class="btn-icon">◆</span>
                <span class="btn-text">{{ $t('history.step4Button') }}</span>
              </button>
            </div>
            <!-- 不可回放提示 -->
            <div class="modal-playback-hint">
              <span class="hint-text">{{ $t('history.replayHint') }}</span>
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useRegionalFormat } from '../i18n/useRegionalFormat.js'
import { getSimulationHistory } from '../api/simulation'

const router = useRouter()
const route = useRoute()
const { t } = useI18n()
const { formatDate, formatTime, formatNumber } = useRegionalFormat()

// 状态管理
const projects = ref([])
const totalCount = ref(0)
const loading = ref(true)
const loadingMore = ref(false)
const hasMore = ref(false)
const selectedProject = ref(null)
const copiedId = ref('')

// 搜索与筛选
const searchQuery = ref('')
const activeFilter = ref('all')
const PAGE_SIZE = 24
let searchDebounceTimer = null

const hasActiveFilters = computed(() => {
  return searchQuery.value.trim() !== '' || activeFilter.value !== 'all'
})

// 加载历史数据
const loadHistory = async (reset = true) => {
  try {
    if (reset) {
      loading.value = true
    } else {
      loadingMore.value = true
    }

    const offset = reset ? 0 : projects.value.length
    const params = {
      limit: PAGE_SIZE,
      offset,
      search: searchQuery.value.trim() || undefined,
      status: activeFilter.value !== 'all' ? activeFilter.value : undefined
    }

    const response = await getSimulationHistory(params)
    if (response.success) {
      const incoming = response.data || []
      if (reset) {
        projects.value = incoming
      } else {
        projects.value.push(...incoming)
      }
      totalCount.value = response.total !== undefined ? response.total : response.count
      hasMore.value = response.has_more !== undefined 
        ? response.has_more 
        : (projects.value.length < totalCount.value)
    }
  } catch (error) {
    console.error('Failed to load simulation history:', error)
    if (reset) {
      projects.value = []
      totalCount.value = 0
      hasMore.value = false
    }
  } finally {
    loading.value = false
    loadingMore.value = false
  }
}

// 刷新历史
const refreshHistory = () => {
  loadHistory(true)
}

// 加载更多
const loadMore = () => {
  if (!loadingMore.value && hasMore.value) {
    loadHistory(false)
  }
}

// 筛选切换
const setFilter = (filterKey) => {
  if (activeFilter.value === filterKey) return
  activeFilter.value = filterKey
  loadHistory(true)
}

// 清除搜索
const clearSearch = () => {
  if (!searchQuery.value) return
  searchQuery.value = ''
  loadHistory(true)
}

// 重置所有筛选
const resetAllFilters = () => {
  searchQuery.value = ''
  activeFilter.value = 'all'
  loadHistory(true)
}

// 监听搜索框输入防抖
watch(searchQuery, () => {
  if (searchDebounceTimer) {
    clearTimeout(searchDebounceTimer)
  }
  searchDebounceTimer = setTimeout(() => {
    loadHistory(true)
  }, 300)
})

// 复制 Simulation ID
const copySimulationId = (simId) => {
  if (!simId) return
  if (navigator?.clipboard?.writeText) {
    navigator.clipboard.writeText(simId)
    copiedId.value = simId
    setTimeout(() => {
      if (copiedId.value === simId) {
        copiedId.value = ''
      }
    }, 1500)
  }
}

// 路由监听：返回主页重新加载
watch(() => route.path, (newPath) => {
  if (newPath === '/') {
    loadHistory(true)
  }
})

onMounted(() => {
  loadHistory(true)
})

// 详情弹窗导航
const navigateToProject = (simulation) => {
  selectedProject.value = simulation
}

const closeModal = () => {
  selectedProject.value = null
}

const goToProject = () => {
  if (selectedProject.value?.project_id) {
    router.push({
      name: 'Process',
      params: { projectId: selectedProject.value.project_id }
    })
    closeModal()
  }
}

const goToSimulation = () => {
  if (selectedProject.value?.simulation_id) {
    router.push({
      name: 'Simulation',
      params: { simulationId: selectedProject.value.simulation_id }
    })
    closeModal()
  }
}

const goToReport = () => {
  if (selectedProject.value?.report_id) {
    router.push({
      name: 'Report',
      params: { reportId: selectedProject.value.report_id }
    })
    closeModal()
  }
}

const goToReportDirect = (reportId) => {
  if (reportId) {
    router.push({
      name: 'Report',
      params: { reportId }
    })
  }
}

// 样式与辅助函数
const getProgressClass = (simulation) => {
  const current = simulation.current_round || 0
  const total = simulation.total_rounds || 0
  const status = simulation.status || simulation.runner_status || ''
  
  if (status === 'completed' || (total > 0 && current >= total)) {
    return 'completed'
  } else if (status === 'running' || status === 'in_progress' || (current > 0 && current < total)) {
    return 'in-progress'
  } else {
    return 'not-started'
  }
}

const truncateText = (text, maxLength) => {
  if (!text) return ''
  return text.length > maxLength ? text.slice(0, maxLength) + '...' : text
}

const getSimulationTitle = (requirement) => {
  if (!requirement) return t('history.untitledSimulation')
  const title = requirement.replace(/[\r\n]+/g, ' ').slice(0, 28)
  return requirement.length > 28 ? title + '...' : title
}

const formatSimulationId = (simulationId) => {
  if (!simulationId) return 'SIM_UNKNOWN'
  const prefix = simulationId.replace('sim_', '').slice(0, 6)
  return `SIM_${prefix.toUpperCase()}`
}

const formatRounds = (simulation) => {
  const current = simulation.current_round || 0
  const total = simulation.total_rounds || 0
  const status = simulation.status || simulation.runner_status || ''
  if (status === 'completed') {
    return total > 0 ? `${total}/${total} rounds` : 'Completed'
  }
  if (total === 0) return t('history.notStarted')
  return t('history.roundsProgress', { current, total })
}

const getFileType = (filename) => {
  if (!filename) return 'other'
  const ext = filename.split('.').pop()?.toLowerCase()
  const typeMap = {
    'pdf': 'pdf',
    'doc': 'doc', 'docx': 'doc',
    'xls': 'xls', 'xlsx': 'xls', 'csv': 'xls',
    'ppt': 'ppt', 'pptx': 'ppt',
    'txt': 'txt', 'md': 'txt', 'json': 'code',
    'jpg': 'img', 'jpeg': 'img', 'png': 'img', 'gif': 'img',
    'zip': 'zip', 'rar': 'zip', '7z': 'zip'
  }
  return typeMap[ext] || 'other'
}

const getFileTypeLabel = (filename) => {
  if (!filename) return 'FILE'
  const ext = filename.split('.').pop()?.toUpperCase()
  return ext || 'FILE'
}

const truncateFilename = (filename, maxLength) => {
  if (!filename) return t('history.unknownFile')
  if (filename.length <= maxLength) return filename
  const ext = filename.includes('.') ? '.' + filename.split('.').pop() : ''
  const nameWithoutExt = filename.slice(0, filename.length - ext.length)
  const truncatedName = nameWithoutExt.slice(0, maxLength - ext.length - 3) + '...'
  return truncatedName + ext
}
</script>

<style scoped>
/* 容器 */
.history-database {
  position: relative;
  width: 100%;
  min-height: 280px;
  margin-top: 50px;
  padding: 40px 0 60px;
  overflow: visible;
}

/* 技术网格背景 */
.tech-grid-bg {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  overflow: hidden;
  pointer-events: none;
}

.grid-pattern {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-image: 
    linear-gradient(to right, rgba(0, 0, 0, 0.04) 1px, transparent 1px),
    linear-gradient(to bottom, rgba(0, 0, 0, 0.04) 1px, transparent 1px);
  background-size: 50px 50px;
  background-position: top left;
}

.gradient-overlay {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: 
    linear-gradient(to right, rgba(255, 255, 255, 0.95) 0%, transparent 12%, transparent 88%, rgba(255, 255, 255, 0.95) 100%),
    linear-gradient(to bottom, rgba(255, 255, 255, 0.85) 0%, transparent 15%, transparent 85%, rgba(255, 255, 255, 0.9) 100%);
  pointer-events: none;
}

/* 标题区域 */
.section-header {
  position: relative;
  z-index: 10;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 24px;
  margin-bottom: 24px;
  padding: 0 40px;
  font-family: 'JetBrains Mono', 'SF Mono', monospace;
}

.section-line {
  flex: 1;
  height: 1px;
  background: linear-gradient(90deg, transparent, #E5E7EB, transparent);
  max-width: 320px;
}

.section-title-wrap {
  display: flex;
  align-items: center;
  gap: 10px;
}

.section-title {
  font-size: 0.85rem;
  font-weight: 600;
  color: #6B7280;
  letter-spacing: 3px;
  text-transform: uppercase;
}

.total-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 2px 7px;
  font-size: 0.7rem;
  font-weight: 600;
  color: #374151;
  background: #F3F4F6;
  border: 1px solid #E5E7EB;
  border-radius: 10px;
}

/* 控制栏：搜索、筛选与刷新 */
.history-controls {
  position: relative;
  z-index: 10;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  max-width: 1240px;
  margin: 0 auto 30px;
  padding: 0 40px;
}

.search-input-wrapper {
  position: relative;
  display: flex;
  align-items: center;
  flex: 1;
  min-width: 240px;
  max-width: 420px;
  background: #FFFFFF;
  border: 1px solid #E5E7EB;
  transition: all 0.2s ease;
}

.search-input-wrapper:focus-within {
  border-color: #111827;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.05);
}

.search-icon {
  padding-left: 12px;
  font-size: 1.1rem;
  color: #9CA3AF;
  line-height: 1;
}

.search-input {
  width: 100%;
  padding: 8px 10px;
  font-family: 'JetBrains Mono', 'SF Mono', monospace;
  font-size: 0.8rem;
  color: #111827;
  background: transparent;
  border: none;
  outline: none;
}

.clear-search-btn {
  padding: 0 10px;
  font-size: 1.1rem;
  color: #9CA3AF;
  background: none;
  border: none;
  cursor: pointer;
  line-height: 1;
}

.clear-search-btn:hover {
  color: #111827;
}

/* 筛选胶囊 */
.status-filters {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.filter-pill {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  font-family: 'JetBrains Mono', 'SF Mono', monospace;
  font-size: 0.72rem;
  font-weight: 500;
  color: #6B7280;
  background: #FFFFFF;
  border: 1px solid #E5E7EB;
  cursor: pointer;
  transition: all 0.2s ease;
}

.filter-pill:hover {
  border-color: #9CA3AF;
  color: #111827;
}

.filter-pill.active {
  background: #111827;
  color: #FFFFFF;
  border-color: #111827;
}

.pill-dot {
  font-size: 0.55rem;
}

.dot-completed { color: #10B981; }
.dot-in-progress { color: #F59E0B; }
.dot-report { color: #3B82F6; }

.filter-pill.active .pill-dot {
  color: #FFFFFF;
}

/* 刷新按钮 */
.refresh-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 34px;
  height: 34px;
  background: #FFFFFF;
  border: 1px solid #E5E7EB;
  color: #6B7280;
  font-size: 1.1rem;
  cursor: pointer;
  transition: all 0.2s ease;
}

.refresh-btn:hover {
  color: #111827;
  border-color: #111827;
}

.refresh-btn.spinning .refresh-icon {
  display: inline-block;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  100% { transform: rotate(360deg); }
}

/* 网格容器 */
.cards-grid-wrapper {
  position: relative;
  z-index: 10;
  max-width: 1240px;
  margin: 0 auto;
  padding: 0 40px;
}

.cards-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(270px, 1fr));
  gap: 20px;
}

/* 项目卡片 */
.project-card {
  position: relative;
  display: flex;
  flex-direction: column;
  background: #FFFFFF;
  border: 1px solid #E5E7EB;
  padding: 16px;
  cursor: pointer;
  box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.04);
  transition: transform 0.2s ease, box-shadow 0.2s ease, border-color 0.2s ease;
}

.project-card:hover {
  transform: translateY(-3px);
  box-shadow: 0 10px 20px -3px rgba(0, 0, 0, 0.08), 0 4px 6px -2px rgba(0, 0, 0, 0.04);
  border-color: #111827;
}

/* 角落取景框装饰 */
.corner-mark {
  position: absolute;
  width: 7px;
  height: 7px;
  pointer-events: none;
  z-index: 2;
}

.corner-mark.top-left {
  top: 5px;
  left: 5px;
  border-top: 1.5px solid rgba(0, 0, 0, 0.35);
  border-left: 1.5px solid rgba(0, 0, 0, 0.35);
}

.corner-mark.bottom-right {
  bottom: 5px;
  right: 5px;
  border-bottom: 1.5px solid rgba(0, 0, 0, 0.35);
  border-right: 1.5px solid rgba(0, 0, 0, 0.35);
}

/* 卡片头部 */
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
  padding-bottom: 10px;
  border-bottom: 1px solid #F3F4F6;
  font-family: 'JetBrains Mono', 'SF Mono', monospace;
  font-size: 0.72rem;
}

.card-id-wrap {
  display: flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
  padding: 2px 4px;
  border-radius: 2px;
  transition: background 0.15s ease;
}

.card-id-wrap:hover {
  background: #F3F4F6;
}

.card-id {
  color: #374151;
  letter-spacing: 0.5px;
  font-weight: 600;
}

.copy-icon {
  font-size: 0.75rem;
  color: #9CA3AF;
}

.card-id-wrap:hover .copy-icon {
  color: #111827;
}

/* 状态指示器 */
.card-status-icons {
  display: flex;
  align-items: center;
  gap: 6px;
}

.status-icon {
  font-size: 0.75rem;
  opacity: 0.3;
  color: #D1D5DB;
}

.status-icon.available {
  opacity: 1;
}

.status-icon:nth-child(1).available { color: #3B82F6; }
.status-icon:nth-child(2).available { color: #F59E0B; }
.status-icon:nth-child(3).available { color: #10B981; }

/* 文件列表 */
.card-files-wrapper {
  min-height: 44px;
  margin-bottom: 12px;
  padding: 6px 8px;
  background: #F9FAFB;
  border: 1px solid #F3F4F6;
}

.files-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.file-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 2px 4px;
  background: #FFFFFF;
  border: 1px solid #E5E7EB;
}

.file-tag {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  height: 15px;
  padding: 0 4px;
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.55rem;
  font-weight: 600;
  text-transform: uppercase;
  flex-shrink: 0;
  min-width: 24px;
}

.file-tag.pdf { background: #FEE2E2; color: #991B1B; }
.file-tag.doc { background: #DBEAFE; color: #1E40AF; }
.file-tag.xls { background: #D1FAE5; color: #065F46; }
.file-tag.ppt { background: #FEF3C7; color: #92400E; }
.file-tag.txt { background: #F3F4F6; color: #374151; }
.file-tag.code { background: #EDE9FE; color: #5B21B6; }
.file-tag.img { background: #E0E7FF; color: #3730A3; }
.file-tag.other { background: #F3F4F6; color: #6B7280; }

.file-name {
  font-family: 'Inter', sans-serif;
  font-size: 0.68rem;
  color: #4B5563;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.files-more {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.6rem;
  color: #6B7280;
  text-align: center;
  padding-top: 2px;
}

.files-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  height: 38px;
  color: #9CA3AF;
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.68rem;
}

/* 项目名标签 */
.card-project-name {
  display: flex;
  align-items: center;
  gap: 5px;
  margin-bottom: 6px;
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.65rem;
  color: #4B5563;
}

.project-tag-icon {
  font-size: 0.7rem;
}

/* 卡片标题 & 描述 */
.card-title {
  font-family: 'Inter', -apple-system, sans-serif;
  font-size: 0.88rem;
  font-weight: 600;
  color: #111827;
  margin: 0 0 6px 0;
  line-height: 1.35;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.card-desc {
  font-family: 'Inter', sans-serif;
  font-size: 0.75rem;
  color: #6B7280;
  line-height: 1.45;
  margin: 0 0 16px 0;
  flex: 1;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

/* 卡片底部 */
.card-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding-top: 10px;
  border-top: 1px solid #F3F4F6;
  font-family: 'JetBrains Mono', 'SF Mono', monospace;
}

.card-datetime {
  display: flex;
  flex-direction: column;
  gap: 2px;
  font-size: 0.65rem;
  color: #9CA3AF;
}

.footer-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.direct-report-pill {
  display: inline-flex;
  align-items: center;
  padding: 3px 6px;
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.62rem;
  font-weight: 600;
  color: #065F46;
  background: #D1FAE5;
  border: 1px solid #A7F3D0;
  border-radius: 2px;
  cursor: pointer;
  transition: all 0.15s ease;
}

.direct-report-pill:hover {
  background: #10B981;
  color: #FFFFFF;
  border-color: #10B981;
}

.card-progress {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 0.65rem;
  font-weight: 600;
}

.status-dot {
  font-size: 0.5rem;
}

.card-progress.completed { color: #10B981; }
.card-progress.in-progress { color: #F59E0B; }
.card-progress.not-started { color: #9CA3AF; }

.card-bottom-line {
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  height: 2px;
  background: transparent;
  transition: background 0.2s ease;
}

.project-card:hover .card-bottom-line {
  background: #111827;
}

/* 加载更多 */
.load-more-section {
  display: flex;
  justify-content: center;
  margin-top: 36px;
}

.load-more-btn {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 10px 24px;
  font-family: 'JetBrains Mono', 'SF Mono', monospace;
  font-size: 0.78rem;
  font-weight: 600;
  color: #111827;
  background: #FFFFFF;
  border: 1px solid #E5E7EB;
  cursor: pointer;
  transition: all 0.2s ease;
}

.load-more-btn:hover:not(:disabled) {
  background: #111827;
  color: #FFFFFF;
  border-color: #111827;
}

.load-more-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.count-hint {
  font-size: 0.7rem;
  opacity: 0.7;
}

.loading-spinner-sm {
  width: 14px;
  height: 14px;
  border: 2px solid #D1D5DB;
  border-top-color: #111827;
  border-radius: 50%;
  animation: spin 0.7s linear infinite;
}

/* 空状态 */
.empty-results {
  position: relative;
  z-index: 10;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 60px 20px;
  text-align: center;
}

.empty-icon {
  font-size: 2rem;
  color: #D1D5DB;
  margin-bottom: 12px;
}

.empty-title {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.85rem;
  color: #6B7280;
  margin-bottom: 16px;
}

.reset-filters-btn {
  padding: 8px 18px;
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.75rem;
  color: #111827;
  background: #FFFFFF;
  border: 1px solid #111827;
  cursor: pointer;
  transition: all 0.2s ease;
}

.reset-filters-btn:hover {
  background: #111827;
  color: #FFFFFF;
}

/* 加载状态 */
.loading-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 60px 0;
  color: #6B7280;
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.8rem;
}

.loading-spinner {
  width: 24px;
  height: 24px;
  border: 2px solid #E5E7EB;
  border-top-color: #111827;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

/* 弹窗样式 */
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.4);
  backdrop-filter: blur(4px);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 2000;
  padding: 20px;
}

.modal-content {
  width: 100%;
  max-width: 580px;
  max-height: 90vh;
  background: #FFFFFF;
  border: 1px solid #E5E7EB;
  box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.25);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  border-bottom: 1px solid #E5E7EB;
  background: #F9FAFB;
}

.modal-title-section {
  display: flex;
  align-items: center;
  gap: 12px;
  font-family: 'JetBrains Mono', monospace;
}

.modal-id {
  font-size: 0.95rem;
  font-weight: 700;
  color: #111827;
}

.modal-create-time {
  font-size: 0.72rem;
  color: #9CA3AF;
}

.modal-close {
  background: none;
  border: none;
  font-size: 1.4rem;
  color: #9CA3AF;
  cursor: pointer;
  line-height: 1;
}

.modal-close:hover {
  color: #111827;
}

.modal-body {
  padding: 20px;
  overflow-y: auto;
  flex: 1;
}

.modal-section {
  margin-bottom: 20px;
}

.modal-section:last-child {
  margin-bottom: 0;
}

.modal-label {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.7rem;
  font-weight: 600;
  color: #6B7280;
  letter-spacing: 1px;
  text-transform: uppercase;
  margin-bottom: 8px;
}

.modal-project-name {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.85rem;
  font-weight: 600;
  color: #111827;
}

.modal-requirement {
  font-family: 'Inter', sans-serif;
  font-size: 0.85rem;
  line-height: 1.55;
  color: #1F2937;
  padding: 12px 14px;
  background: #F9FAFB;
  border: 1px solid #E5E7EB;
  white-space: pre-wrap;
  max-height: 200px;
  overflow-y: auto;
}

.modal-files {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.modal-file-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  background: #F9FAFB;
  border: 1px solid #E5E7EB;
}

.modal-file-name {
  font-family: 'Inter', sans-serif;
  font-size: 0.8rem;
  color: #374151;
}

.modal-empty {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.75rem;
  color: #9CA3AF;
  font-style: italic;
}

.modal-divider {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 0 20px;
  margin: 10px 0;
  font-family: 'JetBrains Mono', monospace;
}

.divider-line {
  flex: 1;
  height: 1px;
  background: #E5E7EB;
}

.divider-text {
  font-size: 0.68rem;
  font-weight: 600;
  color: #9CA3AF;
  letter-spacing: 2px;
  text-transform: uppercase;
}

.modal-actions {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 10px;
  padding: 16px 20px;
  background: #FAFAFA;
  border-top: 1px solid #E5E7EB;
}

.modal-btn {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 4px;
  padding: 12px 8px;
  background: #FFFFFF;
  border: 1px solid #E5E7EB;
  cursor: pointer;
  transition: all 0.2s ease;
  font-family: 'JetBrains Mono', monospace;
}

.modal-btn:hover:not(:disabled) {
  border-color: #111827;
  transform: translateY(-2px);
  box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);
}

.modal-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.btn-step {
  font-size: 0.6rem;
  color: #9CA3AF;
  letter-spacing: 0.5px;
}

.btn-icon {
  font-size: 1.1rem;
}

.btn-project .btn-icon { color: #3B82F6; }
.btn-simulation .btn-icon { color: #F59E0B; }
.btn-report .btn-icon { color: #10B981; }

.btn-text {
  font-size: 0.72rem;
  font-weight: 600;
  color: #111827;
}

.modal-playback-hint {
  padding: 8px 20px 14px;
  background: #FAFAFA;
  text-align: center;
}

.hint-text {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.62rem;
  color: #9CA3AF;
}

/* Modal 动画 */
.modal-enter-active,
.modal-leave-active {
  transition: opacity 0.2s ease;
}

.modal-enter-from,
.modal-leave-to {
  opacity: 0;
}

.modal-enter-active .modal-content,
.modal-leave-active .modal-content {
  transition: transform 0.2s ease;
}

.modal-enter-from .modal-content,
.modal-leave-to .modal-content {
  transform: scale(0.96);
}

/* 响应式适配 */
@media (max-width: 768px) {
  .history-controls {
    flex-direction: column;
    align-items: stretch;
    padding: 0 20px;
  }

  .search-input-wrapper {
    max-width: none;
  }

  .cards-grid-wrapper {
    padding: 0 20px;
  }

  .cards-grid {
    grid-template-columns: 1fr;
  }

  .modal-actions {
    grid-template-columns: 1fr;
  }
}
</style>
