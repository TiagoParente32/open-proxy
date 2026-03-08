<script setup>
import { 
  isRecording, 
  toggleRecording, 
  proxyHost, 
  requests, 
  showMapModal, 
  setupAndroidEmulator, 
  showBreakpointModal,
  breakpointsEnabled,
  disableCache 
} from '../store.js'

const toggleCache = () => {
  disableCache.value = !disableCache.value
}
</script>

<template>
  <header class="toolbar">
    
    <div class="toolbar-group">
      <button
        class="record-btn"
        :class="isRecording ? 'pause' : 'record'"
        @click="toggleRecording"
        :title="isRecording ? 'Pause Intercepting' : 'Start Intercepting'"
      >
        <div class="dot"></div>
        <span>{{ isRecording ? "Recording" : "Paused" }}</span>
      </button>
    </div>

    <div class="toolbar-center">
      <span class="status-indicator" :class="isRecording ? 'active' : 'inactive'"></span>
      <span class="title">OpenProxy</span>
      <span class="host">{{ proxyHost }}</span>
    </div>

    <div class="toolbar-group right">
      <div
        class="toggle"
        @click="toggleCache"
        :class="{ active: disableCache }"
      >
        <span>Bust Cache</span>
        <div class="switch"></div>
      </div>

      <div class="divider"></div>

      <button class="tool-btn" @click="showBreakpointModal = true" title="Manage Breakpoints">
        Breakpoints
      </button>
      <button class="tool-btn" @click="setupAndroidEmulator" title="Android Emulator">
        Emulator
      </button>

      <button class="tool-btn" @click="showMapModal = true">
        Map Local
      </button>

      <button class="tool-btn danger" @click="requests = []">
        Clear
      </button>
    </div>

  </header>
</template>

<style scoped>
/* --- Layout --- */
.toolbar { 
  display: flex; justify-content: space-between; align-items: center; 
  padding: 8px 16px; background-color: var(--bg-sidebar); 
  border-bottom: 1px solid var(--border); font-size: 13px; 
}
.toolbar-group { display: flex; align-items: center; gap: 12px; width: 300px; }
.toolbar-group.right { justify-content: flex-end; width: 400px; }
.toolbar-center { display: flex; align-items: center; justify-content: center; gap: 8px; flex: 1; }

/* --- Record Button --- */
.record-btn { 
  display: flex; align-items: center; gap: 8px; background: transparent; 
  border: 1px solid #444; color: #ccc; padding: 4px 12px; 
  border-radius: 4px; cursor: pointer; font-size: 12px; outline: none; 
}
.record-btn.record { color: #10b981; border-color: rgba(16, 185, 129, 0.4); }
.record-btn.pause { color: #ef4444; border-color: rgba(239, 68, 68, 0.4); }

.dot { width: 8px; height: 8px; border-radius: 50%; }
.record-btn.record .dot { background-color: #10b981; }
.record-btn.pause .dot { background-color: #ef4444; }

/* --- Center Title --- */
.status-indicator { width: 10px; height: 10px; border-radius: 50%; }
.status-indicator.active { background-color: #10b981; box-shadow: 0 0 8px rgba(16, 185, 129, 0.6); }
.status-indicator.inactive { background-color: #ef4444; box-shadow: 0 0 8px rgba(239, 68, 68, 0.6); }
.title { font-weight: 600; color: #ffffff; }
.host { color: #888; font-family: monospace; }

/* --- Right Controls --- */
.toggle { display: flex; align-items: center; gap: 8px; cursor: pointer; color: #ccc; font-weight: 500; }
.toggle.active { color: #f59e0b; }

.switch { width: 30px; height: 16px; background: #444; border-radius: 20px; position: relative; transition: background 0.3s; }
.switch::after { content: ''; position: absolute; top: 2px; left: 2px; width: 12px; height: 12px; background: white; border-radius: 50%; transition: transform 0.3s; }
.toggle.active .switch { background: #f59e0b; }
.toggle.active .switch::after { transform: translateX(14px); }

.divider { width: 1px; height: 16px; background: #444; }

.tool-btn { 
  background: transparent; border: 1px solid #444; color: #ccc; 
  padding: 4px 12px; border-radius: 4px; cursor: pointer; 
  font-size: 12px; outline: none; transition: all 0.2s; 
}
.tool-btn:hover { background: #333; color: white; }
.tool-btn.danger:hover { background: rgba(239, 68, 68, 0.1); border-color: #ef4444; color: #ef4444; }
</style>