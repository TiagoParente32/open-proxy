<script setup>
import { ref, onMounted, onUnmounted } from 'vue'

import { 
  isRecording, 
  toggleRecording, 
  proxyHost, 
  requests, 
  showMapModal, 
  setupAndroidEmulator, 
  showBreakpointModal,
  disableCache,
  showMapRemoteModal,
  throttleProfile,
  showHighlightModal,
  wsMessages,
  showDeviceSetupModal,
  deviceSetupType
} from '../store.js'

// Add the state for the new dropdown
const showCertMenu = ref(false)

const openDeviceSetup = (type) => {
  deviceSetupType.value = type
  showDeviceSetupModal.value = true
  showCertMenu.value = false
}

const toggleCache = () => {
  disableCache.value = !disableCache.value
}

const clearTraffic = () => {
  requests.value.length = 0; 
  wsMessages.value = {};
}

// --- NEW: Custom Dropdown Logic ---
const showThrottleMenu = ref(false)
const throttleOptions = ['None', 'Fast 3G', 'Slow 3G']

const selectThrottle = (option) => {
  throttleProfile.value = option
  showThrottleMenu.value = false
}

const closeDropdown = (e) => {
  if (!e.target.closest('.throttle-wrapper')) showThrottleMenu.value = false
  if (!e.target.closest('.cert-wrapper')) showCertMenu.value = false
}


onMounted(() => document.addEventListener('click', closeDropdown))
onUnmounted(() => document.removeEventListener('click', closeDropdown))
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
      <button class="secondary-pill" @click="showHighlightModal = true" title="Highlight Rules">
        Highlight
      </button>
      <div class="cert-wrapper" style="position: relative;">
        <button 
          class="secondary-pill" 
          @click="showCertMenu = !showCertMenu"
          title="Install Certificates"
          style="padding-right: 4px; gap: 3px;"
        >
          Certificate
          <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="margin-left: 1px;">
            <polyline points="6 9 12 15 18 9"></polyline>
          </svg>
        </button>

        <div v-if="showCertMenu" class="custom-dropdown-menu">
          <div class="dropdown-item" @click="openDeviceSetup('emulator')">Android Emulator</div>
          <div class="dropdown-item" @click="openDeviceSetup('device')">Android Device</div>
        </div>
      </div>

      <div class="throttle-wrapper" style="position: relative;">
        <button 
          class="secondary-pill" 
          :class="{ 'active-throttle': throttleProfile !== 'None' }"
          @click="showThrottleMenu = !showThrottleMenu"
          title="Network Throttling"
          style="padding-right: 4px; gap: 3px;"
        >
          <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M5 12.55a11 11 0 0 1 14.08 0"></path><path d="M1.42 9a16 16 0 0 1 21.16 0"></path><path d="M8.53 16.11a6 6 0 0 1 6.95 0"></path><line x1="12" y1="20" x2="12.01" y2="20"></line>
          </svg>
          
          {{ throttleProfile === 'None' ? 'No Throttling' : throttleProfile }}
          
          <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="margin-left: 1px;">
            <polyline points="6 9 12 15 18 9"></polyline>
          </svg>
        </button>

        <div v-if="showThrottleMenu" class="custom-dropdown-menu">
          <div 
            v-for="opt in throttleOptions" 
            :key="opt" 
            class="dropdown-item"
            :class="{ 'selected': throttleProfile === opt }"
            @click="selectThrottle(opt)"
          >
            <span style="width: 12px; display: inline-block;">
              <svg v-if="throttleProfile === opt" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#10b981" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"></polyline></svg>
            </span>
            {{ opt }}
          </div>
        </div>
      </div>
      
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
  height: 22px; /* Dropped from 24px */
  padding: 0 8px; 
  border-radius: 4px; 
  cursor: pointer; 
  font-size: 10px; /* Dropped from 11px */
  font-weight: 600;
  border: 1px solid transparent;
  transition: all 0.2s; 
  outline: none;
  letter-spacing: 0.2px;
  box-shadow: 0 2px 4px rgba(0,0,0,0.15); 
  white-space: nowrap;
}
.action-btn:active { transform: translateY(1px); box-shadow: none; }

.action-btn.pause-action { background: rgba(239, 68, 68, 0.15); color: #ef4444; border-color: rgba(239, 68, 68, 0.3); }
.action-btn.pause-action:hover { background: rgba(239, 68, 68, 0.25); }
.action-btn.record-action { background: rgba(16, 185, 129, 0.15); color: #10b981; border-color: rgba(16, 185, 129, 0.3); }
.action-btn.record-action:hover { background: rgba(16, 185, 129, 0.25); }

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
  height: 22px; /* Dropped from 24px */
  padding: 0 6px; /* Tightened padding */
  background: #212324; 
  border: 1px solid #303335; 
  color: #a1aab3; 
  border-radius: 4px; 
  cursor: pointer; 
  font-size: 10px; /* Dropped from 11px */
  letter-spacing: -0.2px; /* Pulls letters slightly closer to fit more */
  font-weight: 500;
  transition: all 0.15s ease;
  outline: none;
  white-space: nowrap; /* Prevents text from breaking lines */
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
.divider { width: 1px; height: 14px; background: #444; margin: 0 2px; }

.toggle { display: flex; align-items: center; gap: 4px; cursor: pointer; color: #888; font-weight: 500; transition: color 0.2s; height: 22px; }
.toggle.active { color: #f59e0b; }
.toggle:hover { color: #ccc; }
.toggle-label { font-size: 10px; letter-spacing: -0.2px; white-space: nowrap; }

/* Shrunk the toggle switch slightly */
.switch { width: 22px; height: 12px; background: #111; border: 1px solid #444; border-radius: 14px; position: relative; transition: all 0.3s; box-sizing: border-box;}
.switch::after { content: ''; position: absolute; top: 1px; left: 1px; width: 8px; height: 8px; background: #888; border-radius: 50%; transition: transform 0.3s, background 0.3s; }
.toggle.active .switch { background: rgba(245, 158, 11, 0.15); border-color: #f59e0b; }
.toggle.active .switch::after { transform: translateX(10px); background: #f59e0b; }

/* --- Custom Dropdown Styles --- */
.secondary-pill.active-throttle {
  color: #f59e0b;
  background: rgba(245, 158, 11, 0.15);
  border-color: rgba(245, 158, 11, 0.3);
}
.secondary-pill.active-throttle:hover {
  background: rgba(245, 158, 11, 0.25);
  border-color: rgba(245, 158, 11, 0.4);
}

.custom-dropdown-menu {
  position: absolute;
  top: calc(100% + 4px);
  right: 0;
  width: 130px;
  background: #1a1a1b;
  border: 1px solid #333;
  border-radius: 6px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.5);
  z-index: 1000;
  padding: 4px;
  display: flex;
  flex-direction: column;
}

.dropdown-item {
  padding: 6px 8px;
  font-size: 11px;
  color: #ccc;
  cursor: pointer;
  border-radius: 4px;
  display: flex;
  align-items: center;
  gap: 6px;
  transition: background 0.15s, color 0.15s;
}

.dropdown-item:hover {
  background: #2a2d2e;
  color: #fff;
}

.dropdown-item.selected {
  color: #10b981;
  background: rgba(16, 185, 129, 0.1);
}
</style>