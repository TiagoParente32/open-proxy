<script setup>
import { platform } from '../store.js'

const isMac = () => platform.value === 'darwin'
const api   = () => window.pywebview?.api

const minimize   = () => api()?.minimize_window()
const fullscreen = () => api()?.toggle_maximize_window()   // green = fullscreen
const close      = () => api()?.close_window()
const zoom       = () => api()?.zoom_window()              // dblclick = zoom/maximize
</script>

<template>
  <div class="titlebar pywebview-drag-region" @dblclick="zoom">

    <!-- macOS traffic lights -->
    <div v-if="isMac()" class="macos-controls" @dblclick.stop>
      <span class="tb-btn tb-close"    @click="close"       title="Close">✕</span>
      <span class="tb-btn tb-minimize" @click="minimize"    title="Minimise">−</span>
      <span class="tb-btn tb-zoom"     @click="fullscreen"  title="Full Screen">⤢</span>
    </div>

    <!-- Windows / Linux controls -->
    <div v-if="!isMac()" class="win-controls" @dblclick.stop>
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
.titlebar {
  display: flex;
  align-items: center;
  height: 28px;
  background: var(--bg-sidebar);
  border-bottom: none;  /* seamless with toolbar below */
  flex-shrink: 0;
  user-select: none;
  cursor: default;
}

/* ── macOS traffic lights ── */
.macos-controls {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 0 8px 0 14px;
  height: 100%;
}
.tb-btn {
  width: 14px; height: 14px;
  border-radius: 50%;
  cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  font-size: 0;           /* icons hidden until hover */
  font-weight: 900;
  line-height: 1;
  flex-shrink: 0;
  transition: filter 0.1s;
}
/* reveal icons when hovering the whole control group */
.macos-controls:hover .tb-btn { font-size: 9px; }
.tb-btn:hover { filter: brightness(0.82); }
.tb-close    { background: #ff5f57; color: #7a0002; }
.tb-minimize { background: #febc2e; color: #7a4800; }
.tb-zoom     { background: #28c840; color: #006200; }

/* ── Windows / Linux controls ── */
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
