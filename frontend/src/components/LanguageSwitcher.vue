<template>
  <label class="language-switcher">
    <span class="visually-hidden">{{ $t('ui.language') }}</span>
    <select v-model="locale" class="switcher-select" :aria-label="$t('ui.language')">
      <option v-for="loc in availableLocales" :key="loc.key" :value="loc.key">
        {{ loc.label }}
      </option>
    </select>
  </label>
</template>

<script setup>
import { useI18n } from 'vue-i18n'
import { availableLocales } from '@/i18n/index.js'

// Native select provides keyboard navigation, selection and dismissal.
const { locale } = useI18n({ useScope: 'global' })
</script>

<style scoped>
.language-switcher {
  display: inline-flex;
  align-items: center;
  min-width: 0;
}

.switcher-select {
  max-width: 100%;
  background: #fff;
  color: #333;
  border: 1px solid #ccc;
  border-radius: 0;
  padding: 6px 8px;
  font: 0.8rem 'JetBrains Mono', monospace;
  cursor: pointer;
}

.switcher-select:hover { border-color: #999; }
.switcher-select:focus-visible { outline: 2px solid #ff4500; outline-offset: 2px; }

.visually-hidden {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  overflow: hidden;
  clip-path: inset(50%);
  white-space: nowrap;
}
</style>
