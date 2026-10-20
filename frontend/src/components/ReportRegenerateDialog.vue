<template>
  <div
    v-if="open"
    class="dialog-backdrop"
    @click.self="$emit('close')"
  >
    <div
      ref="dialogElement"
      class="regenerate-dialog"
      role="dialog"
      aria-modal="true"
      :aria-labelledby="dialogTitleId"
      @keydown.esc.stop="$emit('close')"
      @keydown="trapFocus"
    >
      <header class="dialog-header">
        <h2 :id="dialogTitleId" class="dialog-title">{{ $t('step4.regenerateTitle') }}</h2>
        <button
          type="button"
          class="dialog-close"
          :aria-label="$t('step4.regenerateClose')"
          @click="$emit('close')"
        >
          <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2">
            <line x1="18" y1="6" x2="6" y2="18"></line>
            <line x1="6" y1="6" x2="18" y2="18"></line>
          </svg>
        </button>
      </header>

      <div class="dialog-body">
        <p class="dialog-intro">{{ $t('step4.regenerateIntro') }}</p>

        <fieldset class="dialog-fieldset">
          <legend class="dialog-legend">{{ $t('step4.regenerateProfileLabel') }}</legend>
          <p v-if="catalogError" class="dialog-error" role="alert">{{ catalogError }}</p>
          <p v-else-if="profiles.length === 0" class="dialog-hint">{{ $t('step4.regenerateNoProfiles') }}</p>
          <ul v-else class="profile-list">
            <li v-for="profile in profiles" :key="profile.profile_id">
              <label class="profile-option" :class="{ 'is-selected': profile.profile_id === selectedProfileId }">
                <input
                  type="radio"
                  name="report-llm-profile"
                  :value="profile.profile_id"
                  v-model="selectedProfileId"
                  :disabled="busy"
                />
                <span class="profile-body">
                  <span class="profile-top">
                    <span class="profile-id mono">{{ profile.profile_id }}</span>
                    <span v-if="profile.reasoning_effort" class="profile-effort">
                      {{ $t('step4.regenerateEffort', { effort: profile.reasoning_effort }) }}
                    </span>
                  </span>
                  <span class="profile-detail mono">{{ profile.model }} · {{ profile.provider_id }}</span>
                  <span class="profile-detail">
                    {{ $t('step4.regenerateBudget', {
                      cost: formatNumber(profile.max_total_cost_usd, { maximumFractionDigits: 2 }),
                      seconds: formatNumber(profile.max_wall_seconds)
                    }) }}
                  </span>
                </span>
              </label>
            </li>
          </ul>
        </fieldset>

        <fieldset class="dialog-fieldset">
          <legend class="dialog-legend">{{ $t('step4.regenerateModeLabel') }}</legend>
          <label class="mode-option" :class="{ 'is-selected': replayMode === 'replay_frozen' }">
            <input
              type="radio"
              name="report-replay-mode"
              value="replay_frozen"
              v-model="replayMode"
              :disabled="busy || !hasSnapshot"
            />
            <span class="mode-body">
              <span class="mode-title">{{ $t('step4.regenerateModeFrozen') }}</span>
              <span class="mode-detail">{{ $t('step4.regenerateModeFrozenHint') }}</span>
            </span>
          </label>
          <label class="mode-option" :class="{ 'is-selected': replayMode === 'live' }">
            <input
              type="radio"
              name="report-replay-mode"
              value="live"
              v-model="replayMode"
              :disabled="busy"
            />
            <span class="mode-body">
              <span class="mode-title">{{ $t('step4.regenerateModeLive') }}</span>
              <span class="mode-detail">{{ $t('step4.regenerateModeLiveHint') }}</span>
            </span>
          </label>
          <p v-if="!hasSnapshot" class="dialog-hint">{{ $t('step4.regenerateNoSnapshot') }}</p>
        </fieldset>

        <label v-if="replayMode === 'live'" class="live-confirm">
          <input type="checkbox" v-model="liveConfirmed" :disabled="busy" />
          <span>{{ $t('step4.regenerateLiveConfirm') }}</span>
        </label>

        <p v-if="error" class="dialog-error" role="alert">{{ error }}</p>
      </div>

      <footer class="dialog-footer">
        <button type="button" class="dialog-btn dialog-btn--ghost" :disabled="busy" @click="$emit('close')">
          {{ $t('common.cancel') }}
        </button>
        <button
          type="button"
          class="dialog-btn dialog-btn--primary"
          :disabled="!canSubmit"
          @click="submit"
        >
          {{ busy ? $t('step4.regenerateSubmitting') : $t('step4.regenerateSubmit') }}
        </button>
      </footer>
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRegionalFormat } from '../i18n/useRegionalFormat.js'

const props = defineProps({
  open: { type: Boolean, default: false },
  profiles: { type: Array, default: () => [] },
  catalogError: { type: String, default: '' },
  currentProfileId: { type: String, default: '' },
  hasSnapshot: { type: Boolean, default: false },
  busy: { type: Boolean, default: false },
  error: { type: String, default: '' },
})

const emit = defineEmits(['close', 'submit'])

const { t } = useI18n()
const { formatNumber } = useRegionalFormat()

const dialogTitleId = 'report-regenerate-title'
const dialogElement = ref(null)
const selectedProfileId = ref('')
const replayMode = ref('replay_frozen')
const liveConfirmed = ref(false)

const canSubmit = computed(() => {
  if (props.busy) return false
  if (!selectedProfileId.value) return false
  if (replayMode.value === 'live' && !liveConfirmed.value) return false
  return true
})

watch(
  () => props.open,
  (isOpen) => {
    if (!isOpen) {
      liveConfirmed.value = false
      return
    }
    replayMode.value = props.hasSnapshot ? 'replay_frozen' : 'live'
    liveConfirmed.value = false
    // Le profil de la version courante est présélectionné : c'est le geste
    // attendu (« régénérer ce rapport avec un autre modèle »), pas le premier
    // du catalogue — qui est alphabétique et ne correspond à aucun des deux
    // variants que le benchmark doit comparer (Story 013-5, revue BMAD du
    // 20 octobre 2026).
    const preferred = props.profiles.find(
      profile => profile.profile_id === props.currentProfileId
    )
    const fallback = props.profiles[0]
    selectedProfileId.value = preferred ? preferred.profile_id
      : (fallback ? fallback.profile_id : '')
    // Le focus entre dans la boîte de dialogue : la touche Échap doit
    // l'atteindre, et la navigation au clavier doit y rester (AC — accessibilité).
    nextTick(() => {
      const target = dialogElement.value?.querySelector(
        'input[type="radio"], input[type="checkbox"], button'
      )
      if (target) target.focus()
    })
  },
  { immediate: true },
)

watch(
  () => props.profiles,
  (list) => {
    if (list.length === 0) {
      selectedProfileId.value = ''
      return
    }
    if (!list.some(profile => profile.profile_id === selectedProfileId.value)) {
      const preferred = list.find(profile => profile.profile_id === props.currentProfileId)
      selectedProfileId.value = preferred ? preferred.profile_id : list[0].profile_id
    }
  },
)

const submit = () => {
  if (!canSubmit.value) return
  emit('submit', {
    profile_id: selectedProfileId.value,
    replay_mode: replayMode.value,
  })
}

// Piège de focus : le dialogue annonce `aria-modal="true"`, donc la
// navigation au clavier doit y rester. Sans ce renvoi cyclique, Tab sortait
// du dialogue vers la page située derrière (Story 013-5, revue BMAD du
// 20 octobre 2026).
const FOCUSABLE_SELECTOR = [
  'a[href]',
  'button:not([disabled])',
  'input:not([disabled])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(', ')

const trapFocus = (event) => {
  if (event.key !== 'Tab') return
  const container = dialogElement.value
  if (!container) return
  const focusable = Array.from(container.querySelectorAll(FOCUSABLE_SELECTOR))
  if (focusable.length === 0) return
  const first = focusable[0]
  const last = focusable[focusable.length - 1]
  const active = document.activeElement
  if (event.shiftKey) {
    if (active === first || !container.contains(active)) {
      event.preventDefault()
      last.focus()
    }
  } else if (active === last || !container.contains(active)) {
    event.preventDefault()
    first.focus()
  }
}
</script>

<style scoped>
.dialog-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(17, 24, 39, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  padding: 24px;
}

.regenerate-dialog {
  width: min(560px, 100%);
  max-height: 90vh;
  overflow-y: auto;
  background: #FFFFFF;
  border-radius: 12px;
  border: 1px solid #E5E7EB;
  box-shadow: 0 20px 45px rgba(17, 24, 39, 0.18);
  display: flex;
  flex-direction: column;
}

.dialog-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 16px 20px;
  border-bottom: 1px solid #E5E7EB;
}

.dialog-title {
  margin: 0;
  font-size: 15px;
  font-weight: 700;
  color: #111827;
}

.dialog-close {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border: none;
  background: transparent;
  border-radius: 6px;
  color: #6B7280;
  cursor: pointer;
}

.dialog-close:hover {
  background: #F3F4F6;
  color: #111827;
}

.dialog-body {
  padding: 16px 20px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.dialog-intro {
  margin: 0;
  font-size: 12px;
  line-height: 1.5;
  color: #4B5563;
}

.dialog-fieldset {
  border: 1px solid #E5E7EB;
  border-radius: 8px;
  padding: 12px;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.dialog-legend {
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: #6B7280;
  padding: 0 4px;
}

.dialog-hint {
  margin: 0;
  font-size: 11px;
  color: #6B7280;
}

.profile-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.profile-option,
.mode-option {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 8px 10px;
  border: 1px solid #E5E7EB;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s ease;
}

.profile-option.is-selected,
.mode-option.is-selected {
  border-color: #2563EB;
  background: #EFF6FF;
}

.profile-body,
.mode-body {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.profile-top {
  display: flex;
  align-items: center;
  gap: 8px;
}

.profile-id,
.mode-title {
  font-size: 12px;
  font-weight: 700;
  color: #111827;
}

.profile-effort {
  font-size: 10px;
  font-weight: 600;
  background: #EDE9FE;
  color: #5B21B6;
  border-radius: 9999px;
  padding: 1px 7px;
}

.profile-detail,
.mode-detail {
  font-size: 11px;
  color: #6B7280;
  line-height: 1.4;
}

.live-confirm {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  font-size: 11px;
  line-height: 1.5;
  color: #92400E;
  background: #FFFBEB;
  border: 1px solid #FCD34D;
  border-radius: 8px;
  padding: 8px 10px;
}

.dialog-error {
  margin: 0;
  font-size: 11px;
  color: #991B1B;
  background: #FEF2F2;
  border: 1px solid #FECACA;
  border-radius: 8px;
  padding: 8px 10px;
}

.dialog-footer {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
  padding: 14px 20px;
  border-top: 1px solid #E5E7EB;
}

.dialog-btn {
  border-radius: 8px;
  padding: 8px 16px;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s ease;
  border: 1px solid transparent;
}

.dialog-btn--ghost {
  background: #FFFFFF;
  border-color: #E5E7EB;
  color: #4B5563;
}

.dialog-btn--primary {
  background: #111827;
  color: #FFFFFF;
}

.dialog-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
