<script setup>
import { ref } from 'vue'
import { themes, currentThemeId, applyTheme } from '../composables/useTheme'

const open = ref(false)
const toggle = () => open.value = !open.value

const selectTheme = (id) => {
  applyTheme(id)
  open.value = false
}
</script>

<template>
  <div class="theme-selector">
    <div v-if="open" class="ts-backdrop" @click="open = false"></div>

    <button class="ts-btn" @click="toggle" :title="'Theme: ' + currentThemeId" :class="{ active: open }">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <circle cx="13.5" cy="6.5" r=".5" fill="currentColor"/>
        <circle cx="17.5" cy="10.5" r=".5" fill="currentColor"/>
        <circle cx="8.5" cy="7.5" r=".5" fill="currentColor"/>
        <circle cx="6.5" cy="12.5" r=".5" fill="currentColor"/>
        <path d="M12 2C6.5 2 2 6.5 2 12s4.5 10 10 10c.926 0 1.648-.746 1.648-1.688 0-.437-.18-.835-.437-1.125-.29-.289-.438-.652-.438-1.125a1.64 1.64 0 0 1 1.668-1.668h1.996c3.051 0 5.555-2.503 5.555-5.554C21.965 6.012 17.461 2 12 2z"/>
      </svg>
    </button>

    <Transition name="ts-pop">
      <div v-if="open" class="ts-popover">
        <div class="ts-list">
          <button
            v-for="theme in themes"
            :key="theme.id"
            class="ts-item"
            :class="{ active: currentThemeId === theme.id }"
            @click="selectTheme(theme.id)"
          >
            <div class="ts-swatches">
              <span class="ts-swatch" :style="{ background: theme.preview.bg }"></span>
              <span class="ts-swatch" :style="{ background: theme.preview.sidebar }"></span>
              <span class="ts-swatch ts-swatch--accent" :style="{ background: theme.preview.accent }"></span>
            </div>
            <span class="ts-name">{{ theme.name }}</span>
            <svg v-if="currentThemeId === theme.id" class="ts-check" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>
          </button>
        </div>
      </div>
    </Transition>
  </div>
</template>

<style scoped>
.theme-selector { position: relative; }

.ts-backdrop { position: fixed; inset: 0; z-index: 999; }

.ts-btn {
  display: flex; align-items: center; justify-content: center;
  width: 28px; height: 22px; padding: 0;
  background: transparent; border: none; border-radius: 5px;
  color: var(--fg-muted); cursor: pointer;
  transition: background 0.12s, color 0.12s;
}
.ts-btn:hover { background: var(--surface-hover-strong); color: var(--fg-secondary); }
.ts-btn.active { background: var(--accent-muted); color: var(--accent); }

.ts-popover {
  position: absolute;
  bottom: calc(100% + 8px);
  right: 0;
  background: var(--bg-modal);
  border: 1px solid var(--border);
  border-radius: 10px;
  box-shadow: var(--shadow-lg);
  padding: 6px;
  min-width: 160px;
  z-index: 1000;
}

.ts-list { display: flex; flex-direction: column; gap: 2px; }

.ts-item {
  display: flex; align-items: center; gap: 10px;
  width: 100%; padding: 7px 10px;
  background: none; border: none; border-radius: 7px;
  cursor: pointer; text-align: left;
  color: var(--fg-secondary);
  transition: background 0.1s, color 0.1s;
}
.ts-item:hover { background: var(--surface-hover-strong); color: var(--fg-primary); }
.ts-item.active { background: var(--accent-muted); color: var(--accent); }

.ts-swatches { display: flex; gap: 3px; flex-shrink: 0; }
.ts-swatch {
  width: 12px; height: 12px; border-radius: 50%;
  border: 1px solid var(--border);
  flex-shrink: 0;
}
.ts-swatch--accent { border-radius: 3px; }

.ts-name { flex: 1; font-size: 12.5px; font-weight: 500; }
.ts-check { color: var(--accent); flex-shrink: 0; }

.ts-pop-enter-active, .ts-pop-leave-active { transition: opacity 0.12s, transform 0.12s; }
.ts-pop-enter-from, .ts-pop-leave-to { opacity: 0; transform: translateY(4px) scale(0.97); }
</style>
