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
        class="primary-btn"
        :class="isRecording ? 'paused-state' : 'record-state'"
        @click="toggleRecording"
        :title="isRecording ? 'Pause Intercepting' : 'Start Intercepting'"
      >
        <span class="icon">{{ isRecording ? '⏸' : '▶' }}</span>
        <span>{{ isRecording ? "Pause" : "Record" }}</span>
      </button>

      <button class="ghost-btn danger" @click="clearTraffic" title="Clear All Traffic">
        🚫 Clear
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
      
      <button class="ghost-btn" @click="showBreakpointModal = true" title="Manage Breakpoints">
        🛑 Breakpoints
      </button>
      <button class="ghost-btn" @click="showMapModal = true" title="Map Local Rules">
        ⚡️ Map Local
      </button>
      <button class="ghost-btn" @click="showMapRemoteModal = true" title="Map Remote Rules">
        🔀 Map Remote
      </button>
      <button class="ghost-btn" @click="setupAndroidEmulator" title="Setup Android Emulator">
        📱 Emulator
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
/* --- Layout --- */
/* --- Layout --- */
.toolbar { 
  display: flex; justify-content: space-between; align-items: center; 
  padding: 8px 16px; 
  background-color: var(--bg-sidebar); 
  border-bottom: 1px solid var(--border); 
  font-size: 12px; 
  user-select: none;
}
/* Use flex: 1 so the sides stretch equally, keeping the center perfectly aligned! */
.toolbar-group { display: flex; align-items: center; gap: 8px; flex: 1; }
.toolbar-group.right { justify-content: flex-end; }
.toolbar-center { display: flex; align-items: center; justify-content: center; flex: 0 1 auto; }

/* --- Explicit Play/Pause Button --- */
.primary-btn { 
  display: flex; align-items: center; justify-content: center; gap: 6px; 
  height: 28px; /* Strict, small height */
  padding: 0 12px; 
  border-radius: 6px; 
  cursor: pointer; 
  font-size: 12px; 
  font-weight: 600;
  border: 1px solid transparent;
  transition: all 0.2s; 
  outline: none;
  box-shadow: 0 2px 4px rgba(0,0,0,0.2); /* Makes it pop out as a button */
}
.primary-btn:active { transform: translateY(1px); box-shadow: none; }

/* When it is currently recording, the button offers to PAUSE (Red/Warning) */
.primary-btn.paused-state { 
  background: rgba(239, 68, 68, 0.15); 
  color: #ef4444; 
  border-color: rgba(239, 68, 68, 0.4); 
}
.primary-btn.paused-state:hover { background: rgba(239, 68, 68, 0.25); }

/* When it is paused, the button offers to RECORD (Green/Go) */
.primary-btn.record-state { 
  background: rgba(16, 185, 129, 0.15); 
  color: #10b981; 
  border-color: rgba(16, 185, 129, 0.4); 
}
.primary-btn.record-state:hover { background: rgba(16, 185, 129, 0.25); }

.primary-btn .icon { font-size: 10px; }

/* --- Modern Ghost Buttons --- */
.ghost-btn {
  display: flex; align-items: center; gap: 6px;
  height: 28px; /* Matches primary button */
  padding: 0 10px;
  background: transparent; 
  border: 1px solid transparent; 
  color: #aaa; 
  border-radius: 6px; 
  cursor: pointer; 
  font-size: 12px; 
  transition: all 0.2s;
}
.ghost-btn:hover { background: rgba(255, 255, 255, 0.08); color: #fff; }
.ghost-btn.danger:hover { background: rgba(239, 68, 68, 0.1); color: #ef4444; }

/* --- Center: Sleek App Badge --- */
.app-badge {
  display: flex; align-items: center; gap: 8px;
  height: 28px; /* Matches buttons */
  background: #111; 
  padding: 0 16px; 
  border-radius: 14px;
  border: 1px solid #2a2a2a; 
  box-shadow: inset 0 1px 3px rgba(0,0,0,0.3);
}
.status-pulse { width: 8px; height: 8px; border-radius: 50%; }
.status-pulse.active { background-color: #10b981; box-shadow: 0 0 6px rgba(16, 185, 129, 0.5); }
.status-pulse.inactive { background-color: #ef4444; }
.title { font-weight: 700; color: #ffffff; letter-spacing: 0.5px; }
.divider-dot { color: #555; font-size: 10px; }
.host { color: #8b949e; font-family: 'Consolas', monospace; font-size: 11px; }

/* --- Right: Toggles --- */
.divider { width: 1px; height: 16px; background: #444; margin: 0 4px; }

.toggle { display: flex; align-items: center; gap: 8px; cursor: pointer; color: #888; font-weight: 500; transition: color 0.2s; height: 28px; }
.toggle.active { color: #f59e0b; }
.toggle:hover { color: #ccc; }
.toggle-label { font-size: 12px; }

.switch { width: 30px; height: 16px; background: #111; border: 1px solid #444; border-radius: 20px; position: relative; transition: all 0.3s; box-sizing: border-box;}
.switch::after { content: ''; position: absolute; top: 1px; left: 1px; width: 12px; height: 12px; background: #888; border-radius: 50%; transition: transform 0.3s, background 0.3s; }
.toggle.active .switch { background: rgba(245, 158, 11, 0.15); border-color: #f59e0b; }
.toggle.active .switch::after { transform: translateX(14px); background: #f59e0b; }
</style>