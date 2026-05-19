<script setup>
import { onMounted, onUnmounted } from 'vue'

const emit = defineEmits(['close'])
const isMac = window.electronAPI?.platform === 'darwin'

const mod  = isMac ? '⌘' : 'Ctrl'
const shft = isMac ? '⇧' : 'Shift'

const SECTIONS = [
  {
    title: 'Proxy',
    items: [
      { keys: [`${mod}${shft}R`],  label: 'Toggle Recording' },
      { keys: [`${mod}K`],         label: 'Clear Traffic' },
      { keys: [`${mod}N`],         label: 'Compose Request' },
      { keys: [`${mod}F`],         label: 'Focus Search' },
    ],
  },
  {
    title: 'Tools',
    items: [
      { keys: [`${mod}${shft}M`],  label: 'Map Local' },
      { keys: [`${mod}${shft}E`],  label: 'Map Remote' },
      { keys: [`${mod}${shft}B`],  label: 'Breakpoints' },
      { keys: [`${mod}${shft}H`],  label: 'Highlight' },
      { keys: [`${mod}${shft}S`],  label: 'Scripts' },
      { keys: [`${mod}${shft}V`],  label: 'VPN Mode' },
    ],
  },
  {
    title: 'Navigation',
    items: [
      { keys: ['↑', '↓'],          label: 'Navigate requests' },
      { keys: ['Esc'],             label: 'Close modal / deselect' },
      { keys: [`${mod}${shft}?`],  label: 'Show this reference' },
    ],
  },
]

const onKeyDown = (e) => {
  if (e.key === 'Escape') emit('close')
}

onMounted(()  => document.addEventListener('keydown', onKeyDown))
onUnmounted(() => document.removeEventListener('keydown', onKeyDown))
</script>

<template>
  <div class="ks-backdrop" @click.self="$emit('close')">
    <div class="ks-modal">

      <div class="ks-header">
        <span class="ks-title">Keyboard Shortcuts</span>
        <button class="ks-close" @click="$emit('close')">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round">
            <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
          </svg>
        </button>
      </div>

      <div class="ks-body">
        <div v-for="section in SECTIONS" :key="section.title" class="ks-section">
          <div class="ks-section-title">{{ section.title }}</div>
          <div v-for="item in section.items" :key="item.label" class="ks-row">
            <span class="ks-label">{{ item.label }}</span>
            <span class="ks-keys">
              <kbd v-for="k in item.keys" :key="k" class="ks-kbd">{{ k }}</kbd>
            </span>
          </div>
        </div>
      </div>

    </div>
  </div>
</template>

<style scoped>
.ks-backdrop {
  position: fixed; inset: 0; z-index: 9999;
  background: rgba(0,0,0,0.5);
  display: flex; align-items: center; justify-content: center;
}

.ks-modal {
  background: var(--bg-modal);
  border: 1px solid var(--border);
  border-radius: 10px;
  width: 400px;
  box-shadow: 0 24px 64px rgba(0,0,0,0.5);
  overflow: hidden;
}

.ks-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 14px 16px 12px;
  border-bottom: 1px solid var(--border);
}

.ks-title { font-size: 13px; font-weight: 600; color: var(--fg-primary); }

.ks-close {
  background: transparent; border: none; cursor: pointer;
  color: var(--fg-muted); padding: 2px; border-radius: 4px;
  display: flex; align-items: center; justify-content: center;
  transition: color 0.15s;
}
.ks-close:hover { color: var(--fg-primary); }

.ks-body { padding: 10px 16px 14px; display: flex; flex-direction: column; gap: 14px; }

.ks-section { display: flex; flex-direction: column; gap: 2px; }

.ks-section-title {
  font-size: 10px; font-weight: 700; letter-spacing: 0.6px;
  text-transform: uppercase; color: var(--fg-muted);
  padding: 4px 0 6px; opacity: 0.6;
}

.ks-row {
  display: flex; align-items: center; justify-content: space-between;
  padding: 5px 8px; border-radius: 6px;
  transition: background 0.1s;
}
.ks-row:hover { background: var(--bg-hover); }

.ks-label { font-size: 12.5px; color: var(--fg-secondary); }

.ks-keys { display: flex; align-items: center; gap: 4px; }

.ks-kbd {
  display: inline-flex; align-items: center; justify-content: center;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', monospace;
  font-size: 11px; font-weight: 500;
  padding: 2px 7px; min-width: 22px;
  background: var(--bg-deep);
  border: 1px solid var(--border);
  border-bottom-width: 2px;
  border-radius: 5px;
  color: var(--fg-secondary);
  white-space: nowrap;
}
</style>
