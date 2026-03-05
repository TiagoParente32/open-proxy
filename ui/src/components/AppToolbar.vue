<script setup>
import { isRecording, toggleRecording, proxyHost, requests, showMapModal, setupAndroidEmulator, disableCache } from '../store.js'

// NEW: A safe function to toggle the imported variable!
const toggleCache = () => {
  disableCache.value = !disableCache.value
}
</script>

<template>
  <header class="toolbar">
    <div class="actions" style="width: 200px;">
      <button class="action-btn icon-btn" :class="isRecording ? 'btn-pause' : 'btn-record'" @click="toggleRecording" :title="isRecording ? 'Pause Intercepting' : 'Resume Intercepting'">
        <svg v-if="isRecording" xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
          <rect x="6" y="4" width="4" height="16"></rect><rect x="14" y="4" width="4" height="16"></rect>
        </svg>
        <svg v-else xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
          <polygon points="5 3 19 12 5 21 5 3"></polygon>
        </svg>
      </button>
    </div>

    <div class="title" style="display: flex; align-items: center; gap: 8px; justify-content: center; flex: 1;">
      <span class="status-indicator" :class="isRecording ? 'active' : 'inactive'"></span>
      OpenProxy running on {{ proxyHost }}
    </div>

    <div class="actions" style="display: flex; justify-content: flex-end; align-items: center; gap: 16px; width: 380px;">
      
      <div class="toolbar-toggle" @click="toggleCache" :class="{ 'active': disableCache }" title="Force 200 OKs instead of 304s">
        <span class="toggle-label">Bust Cache</span>
        <div class="switch"></div>
      </div>

      <div style="width: 1px; height: 16px; background: var(--border);"></div>

      <button class="action-btn" style="color: #10b981; border-color: rgba(16, 185, 129, 0.4);" @click="setupAndroidEmulator">📱 Emulator</button>
      <button class="action-btn" @click="showMapModal = true">⚡️ Map Local</button>
      <button class="action-btn" @click="requests = []">🚫 Clear</button>
    </div>
  </header>
</template>

<style scoped>
.toolbar { display: flex; justify-content: space-between; align-items: center; padding: 8px 16px; background-color: var(--bg-sidebar); border-bottom: 1px solid var(--border); font-size: 13px; }
.toolbar .title { font-weight: 600; color: #ffffff; }
/* Toolbar Toggle Switch */
.toolbar-toggle { display: flex; align-items: center; gap: 8px; cursor: pointer; padding: 4px 8px; border-radius: 6px; transition: background 0.2s; }
.toolbar-toggle:hover { background: #2a2d2e; }
.toggle-label { font-size: 11px; font-weight: 600; color: #888; text-transform: uppercase; letter-spacing: 0.5px; transition: color 0.3s; }
.toolbar-toggle.active .toggle-label { color: #f59e0b; }

.switch { width: 30px; height: 16px; background: #444; border-radius: 20px; position: relative; transition: background 0.3s; }
.switch::after { content: ''; position: absolute; top: 2px; left: 2px; width: 12px; height: 12px; background: white; border-radius: 50%; transition: transform 0.3s; }
.toolbar-toggle.active .switch { background: #f59e0b; }
.toolbar-toggle.active .switch::after { transform: translateX(14px); }

.icon-btn { display: flex; align-items: center; justify-content: center; padding: 4px 8px; height: 26px; width: 32px; }
.btn-pause { color: #ef4444; border-color: rgba(239, 68, 68, 0.4); }
.btn-pause:hover { background: rgba(239, 68, 68, 0.1); border-color: #ef4444; }
.btn-record { color: #10b981; border-color: rgba(16, 185, 129, 0.4); }
.btn-record:hover { background: rgba(16, 185, 129, 0.1); border-color: #10b981; }

.status-indicator { width: 10px; height: 10px; border-radius: 50%; display: inline-block; transition: all 0.3s ease; }
.status-indicator.active { background-color: #10b981; box-shadow: 0 0 8px #10b981; }
.status-indicator.inactive { background-color: #ef4444; box-shadow: 0 0 8px #ef4444; }
</style>