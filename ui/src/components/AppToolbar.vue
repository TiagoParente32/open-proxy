<script setup>
import { isRecording, toggleRecording, proxyHost, requests, showMapModal } from '../store.js'
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

    <div class="actions" style="display: flex; justify-content: flex-end; gap: 10px; width: 200px;">
      <button class="action-btn" @click="showMapModal = true">⚡️ Map Local</button>
      <button class="action-btn" @click="requests = []">🚫 Clear</button>
    </div>
  </header>
</template>

<style scoped>
.toolbar { display: flex; justify-content: space-between; align-items: center; padding: 8px 16px; background-color: var(--bg-sidebar); border-bottom: 1px solid var(--border); font-size: 13px; }
.toolbar .title { font-weight: 600; color: #ffffff; }

.icon-btn { display: flex; align-items: center; justify-content: center; padding: 4px 8px; height: 26px; width: 32px; }
.btn-pause { color: #ef4444; border-color: rgba(239, 68, 68, 0.4); }
.btn-pause:hover { background: rgba(239, 68, 68, 0.1); border-color: #ef4444; }
.btn-record { color: #10b981; border-color: rgba(16, 185, 129, 0.4); }
.btn-record:hover { background: rgba(16, 185, 129, 0.1); border-color: #10b981; }

.status-indicator { width: 10px; height: 10px; border-radius: 50%; display: inline-block; transition: all 0.3s ease; }
.status-indicator.active { background-color: #10b981; box-shadow: 0 0 8px #10b981; }
.status-indicator.inactive { background-color: #ef4444; box-shadow: 0 0 8px #ef4444; }
</style>