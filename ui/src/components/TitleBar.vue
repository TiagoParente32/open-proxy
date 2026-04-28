<script setup>
const isMac  = () => window.electronAPI?.platform === 'darwin'
const eAPI   = () => window.electronAPI

// Win/Linux only — macOS uses fully native window controls
const isZoomed = { value: false }

const minimize   = () => eAPI()?.minimize()
const fullscreen = () => eAPI()?.toggleFullscreen()
const close      = () => eAPI()?.close()

const zoom = () => {
  eAPI()?.zoom()
  isZoomed.value = !isZoomed.value
}
</script>

<template>
  <!-- macOS: drag strip only — native traffic lights (hiddenInset) sit on top -->
  <div v-if="isMac()" class="titlebar-mac" />

  <!-- Windows / Linux: full custom bar with window controls -->
  <div v-else class="titlebar-win" @dblclick="zoom">
    <div class="win-controls" @dblclick.stop>
      <button class="win-btn"           @click="minimize"    title="Minimise">
        <svg width="10" height="1" viewBox="0 0 10 1"><rect width="10" height="1" fill="currentColor"/></svg>
      </button>
      <button class="win-btn"           @click="zoom"        title="Maximise / Restore">
        <svg width="9" height="9" viewBox="0 0 9 9" fill="none"><rect x="0.5" y="0.5" width="8" height="8" stroke="currentColor"/></svg>
      </button>
      <button class="win-btn win-close" @click="close"       title="Close (hides to tray)">
        <svg width="10" height="10" viewBox="0 0 10 10" fill="none">
          <line x1="1" y1="1" x2="9" y2="9" stroke="currentColor" stroke-width="1.3"/>
          <line x1="9" y1="1" x2="1" y2="9" stroke="currentColor" stroke-width="1.3"/>
        </svg>
      </button>
    </div>
  </div>
</template>

<style scoped>
/* macOS: drag strip — Electron hiddenInset puts traffic lights over this */
.titlebar-mac {
  height: 38px;
  background: var(--bg-sidebar);
  flex-shrink: 0;
  user-select: none;
  cursor: default;
  -webkit-app-region: drag;
}

/* Windows / Linux: full custom bar */
.titlebar-win {
  display: flex;
  align-items: center;
  height: 38px;
  background: var(--bg-sidebar);
  flex-shrink: 0;
  user-select: none;
  cursor: default;
  -webkit-app-region: drag;
}

.win-controls {
  margin-left: auto;
  display: flex;
  align-items: stretch;
  height: 100%;
}
.win-btn {
  display: flex; align-items: center; justify-content: center;
  width: 42px; height: 100%;
  background: transparent; border: none;
  color: #8b949e;
  cursor: pointer;
  transition: background 0.15s, color 0.15s;
}
.win-btn:hover  { background: rgba(255,255,255,0.08); color: #fff; }
.win-close:hover { background: #e81123; color: #fff; }
</style>

