<script setup>
import { 
  isRecording, 
  toggleRecording, 
  proxyHost, 
  requests, 
  showMapModal, 
  setupAndroidEmulator, 
  showBreakpointModal,
  disableCache,
  showMapRemoteModal
} from '../store.js'

const toggleCache = () => {
  disableCache.value = !disableCache.value
}

const clearTraffic = () => {
  requests.value.length = 0; 
}
</script>

<template>
  <header class="toolbar">
    
    <div class="toolbar-group left">
      <button
        class="action-btn"
        :class="isRecording ? 'pause-action' : 'record-action'"
        @click="toggleRecording"
        :title="isRecording ? 'Pause Intercepting' : 'Start Intercepting'"
      >
        {{ isRecording ? "Pause" : "Record" }}
      </button>

      <button class="icon-btn danger" @click="clearTraffic" title="Clear All Traffic">
        <svg style="min-width: 14px; min-height: 14px; stroke: #a1aab3; fill: none;" width="14" height="14" viewBox="0 0 24 24" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <polyline points="3 6 5 6 21 6"></polyline>
          <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
          <line x1="10" y1="11" x2="10" y2="17"></line>
          <line x1="14" y1="11" x2="14" y2="17"></line>
        </svg>
      </button>
    </div>

    <div class="toolbar-center">
      <div class="app-badge">
        <span class="status-pulse" :class="isRecording ? 'active' : 'inactive'"></span>
        <span class="title">OpenProxy</span>
        <span class="divider-dot">•</span>
        <span class="host">{{ proxyHost }}</span>
      </div>
    </div>

    <div class="toolbar-group right">
      
      <button class="secondary-pill" @click="showBreakpointModal = true" title="Manage Breakpoints">
        Breakpoints
      </button>
      <button class="secondary-pill" @click="showMapModal = true" title="Map Local Rules">
        Map Local
      </button>
      <button class="secondary-pill" @click="showMapRemoteModal = true" title="Map Remote Rules">
        Map Remote
      </button>
      <button class="secondary-pill" @click="setupAndroidEmulator" title="Setup Android Emulator">
        Emulator
      </button>

      <div class="divider"></div>

      <div
        class="toggle"
        @click="toggleCache"
        :class="{ active: disableCache }"
        title="Disable caching for all requests"
      >
        <span class="toggle-label">Bust Cache</span>
        <div class="switch"></div>
      </div>
    </div>

  </header>
</template>

<style scoped>
/* --- Ultra-Compact Layout --- */
.toolbar { 
  display: flex; justify-content: space-between; align-items: center; 
  padding: 6px 16px; 
  background-color: var(--bg-sidebar); 
  border-bottom: 1px solid var(--border); 
  font-size: 11px; 
  user-select: none;
}
.toolbar-group { display: flex; align-items: center; gap: 6px; flex: 1; } 
.toolbar-group.right { justify-content: flex-end; }
.toolbar-center { display: flex; align-items: center; justify-content: center; flex: 0 1 auto; }

/* --- Pure Text Action Button (Play/Pause) --- */
.action-btn { 
  display: flex; align-items: center; justify-content: center; 
  height: 24px; 
  padding: 0 12px; 
  border-radius: 4px; 
  cursor: pointer; 
  font-size: 11px; 
  font-weight: 600;
  border: 1px solid transparent;
  transition: all 0.2s; 
  outline: none;
  letter-spacing: 0.3px;
  box-shadow: 0 2px 4px rgba(0,0,0,0.15); 
}
.action-btn:active { transform: translateY(1px); box-shadow: none; }

.action-btn.pause-action { background: rgba(239, 68, 68, 0.15); color: #ef4444; border-color: rgba(239, 68, 68, 0.3); }
.action-btn.pause-action:hover { background: rgba(239, 68, 68, 0.25); }
.action-btn.record-action { background: rgba(16, 185, 129, 0.15); color: #10b981; border-color: rgba(16, 185, 129, 0.3); }
.action-btn.record-action:hover { background: rgba(16, 185, 129, 0.25); }

/* --- Pure Icon Utility Button (Trashcan) --- */
/* --- Pure Icon Utility Button (Trashcan) --- */
.icon-btn {
  display: flex; align-items: center; justify-content: center;
  height: 24px; width: 26px;
  background: transparent; 
  border: 1px solid transparent; 
  border-radius: 4px; 
  cursor: pointer; 
  transition: all 0.2s;
}
.icon-btn svg { transition: stroke 0.2s; }
.icon-btn:hover { background: rgba(255, 255, 255, 0.08); }
.icon-btn:hover svg { stroke: #ccc !important; }
.icon-btn.danger:hover { background: rgba(239, 68, 68, 0.1); }
.icon-btn.danger:hover svg { stroke: #ef4444 !important; }

/* --- Pure Text Pill Buttons (The Tools) --- */
.secondary-pill {
  display: flex; align-items: center; justify-content: center;
  height: 24px; 
  padding: 0 10px;
  background: #212324; /* Solid subtle background */
  border: 1px solid #303335; /* Sharp distinct border */
  color: #a1aab3; 
  border-radius: 4px; 
  cursor: pointer; 
  font-size: 11px; 
  font-weight: 500;
  transition: all 0.15s ease;
  outline: none;
}
.secondary-pill:hover { 
  background: #2a2d2e; 
  color: #fff; 
  border-color: #404446;
}
.secondary-pill:active {
  background: #1a1c1d;
}

/* --- Center: Sleek App Badge --- */
.app-badge {
  display: flex; align-items: center; gap: 6px;
  height: 24px; 
  background: #111; 
  padding: 0 12px; 
  border-radius: 12px;
  border: 1px solid #2a2a2a; 
  box-shadow: inset 0 1px 3px rgba(0,0,0,0.3);
}
.status-pulse { width: 6px; height: 6px; border-radius: 50%; }
.status-pulse.active { background-color: #10b981; box-shadow: 0 0 6px rgba(16, 185, 129, 0.5); }
.status-pulse.inactive { background-color: #ef4444; }
.title { font-weight: 700; color: #ffffff; letter-spacing: 0.5px; font-size: 11px; }
.divider-dot { color: #555; font-size: 9px; }
.host { color: #8b949e; font-family: 'Consolas', monospace; font-size: 10px; }

/* --- Right: Toggles --- */
.divider { width: 1px; height: 14px; background: #444; margin: 0 4px; }

.toggle { display: flex; align-items: center; gap: 6px; cursor: pointer; color: #888; font-weight: 500; transition: color 0.2s; height: 24px; }
.toggle.active { color: #f59e0b; }
.toggle:hover { color: #ccc; }
.toggle-label { font-size: 11px; }

.switch { width: 26px; height: 14px; background: #111; border: 1px solid #444; border-radius: 14px; position: relative; transition: all 0.3s; box-sizing: border-box;}
.switch::after { content: ''; position: absolute; top: 1px; left: 1px; width: 10px; height: 10px; background: #888; border-radius: 50%; transition: transform 0.3s, background 0.3s; }
.toggle.active .switch { background: rgba(245, 158, 11, 0.15); border-color: #f59e0b; }
.toggle.active .switch::after { transform: translateX(12px); background: #f59e0b; }
</style>