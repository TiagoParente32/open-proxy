<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { 
  isRecording, 
  toggleRecording, 
  proxyHost, 
  requests, 
  showMapModal, 
  showBreakpointModal,
  disableCache,
  showMapRemoteModal,
  throttleProfile,
  showHighlightModal,
  wsMessages,
  showDeviceSetupModal,
  deviceSetupType,
  openComposeNew,
  openVpnMode,
  wgEnabled,
  wgStatus,
} from '../store.js'

const isMac = () => window.electronAPI?.platform === 'darwin'

const copied = ref(false)
const copyHost = () => {
  navigator.clipboard.writeText(proxyHost.value)
  copied.value = true
  setTimeout(() => copied.value = false, 1500)
}

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
  requests.value.length = 0
  wsMessages.value = {}
}

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
  <header class="toolbar" :class="{ 'is-mac': isMac() }">

    <!-- macOS: drag spacer for native traffic lights (hiddenInset) -->
    <div v-if="isMac()" class="mac-spacer" />

    <div class="toolbar-group left">
      <button
        class="action-btn"
        :class="isRecording ? 'pause-action' : 'record-action'"
        @click="toggleRecording"
        :title="isRecording ? 'Pause Intercepting' : 'Start Intercepting'"
      >
        <!-- Pause icon -->
        <svg v-if="isRecording" style="min-width: 11px; min-height: 11px; fill: currentColor; stroke: none;" width="11" height="11" viewBox="0 0 24 24">
          <rect x="5" y="3" width="4" height="18" rx="1"/>
          <rect x="15" y="3" width="4" height="18" rx="1"/>
        </svg>
        <!-- Play icon -->
        <svg v-else style="min-width: 11px; min-height: 11px; fill: currentColor; stroke: none;" width="11" height="11" viewBox="0 0 24 24">
          <polygon points="5,3 19,12 5,21"/>
        </svg>
      </button>

      <button class="icon-btn" @click="openComposeNew" title="Compose New Request">
        <svg style="min-width: 14px; min-height: 14px; stroke: currentColor; fill: none;" width="14" height="14" viewBox="0 0 24 24" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M12 20h9"></path>
          <path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"></path>
        </svg>
      </button>

      <button class="icon-btn danger" @click="clearTraffic" title="Clear All Traffic">
        <svg style="min-width: 14px; min-height: 14px; stroke: currentColor; fill: none;" width="14" height="14" viewBox="0 0 24 24" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <polyline points="3 6 5 6 21 6"></polyline>
          <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
          <line x1="10" y1="11" x2="10" y2="17"></line>
          <line x1="14" y1="11" x2="14" y2="17"></line>
        </svg>
      </button>
    </div>

    <div class="toolbar-center">
      <div class="app-badge" :class="{ copied }" @click="copyHost" title="Click to copy address">
        <span class="status-pulse" :class="isRecording ? 'active' : 'inactive'"></span>
        <span class="title">OpenProxy</span>
        <span class="divider-dot">•</span>
        <span class="host">{{ copied ? 'Copied!' : proxyHost }}</span>
      </div>
    </div>

    <div class="toolbar-group right">
      <button
        class="secondary-pill"
        :class="{ 'wg-active': wgEnabled && wgStatus === 'ready', 'wg-loading': wgStatus === 'starting' }"
        @click="openVpnMode()"
        title="VPN Mode — connect without proxy setup"
      >
        VPN Mode
      </button>
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

      <div class="cert-wrapper">
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
          <div class="dropdown-item" @click="openDeviceSetup('android_emulator')">Android Emulator</div>
          <div class="dropdown-item" @click="openDeviceSetup('android_device')">Android Device</div>
          <div class="dropdown-sep"></div>
          <div class="dropdown-item" @click="openDeviceSetup('ios_simulator')">iOS Simulator</div>
          <div class="dropdown-item" @click="openDeviceSetup('ios_device')">iOS Device</div>
          <div class="dropdown-sep"></div>
          <div class="dropdown-item" @click="openDeviceSetup('browser')">Browser / Desktop</div>
        </div>
      </div>

      <div class="throttle-wrapper">
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
          {{ throttleProfile === 'None' ? 'No Throttle' : throttleProfile }}
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
              <svg v-if="throttleProfile === opt" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="var(--success)" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"></polyline></svg>
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

    <!-- Linux window controls handled by TitleBar.vue -->

  </header>
</template>

<style scoped>
.toolbar {
  display: flex;
  align-items: center;
  height: 38px;
  box-sizing: border-box;
  padding: 0 12px;
  background-color: var(--bg-sidebar);
  border-bottom: 1px solid var(--border);
  font-size: 11px;
  user-select: none;
  gap: 6px;
}

/* macOS: toolbar doubles as the titlebar (no TitleBar.vue above it) */
.toolbar.is-mac {
  -webkit-app-region: drag;
  padding-left: 0; /* mac-spacer handles the traffic light offset */
}

/* Opt all interactive zones out of window-drag (macOS only, but harmless elsewhere) */
button,
.toggle,
.app-badge,
.throttle-wrapper,
.cert-wrapper,
.custom-dropdown-menu {
  -webkit-app-region: no-drag;
}

/* macOS traffic light spacer — stays draggable */
.mac-spacer {
  width: 76px;
  flex-shrink: 0;
  height: 100%;
  -webkit-app-region: drag;
}

.toolbar-group      { display: flex; align-items: center; gap: 5px; flex: 1; }
.toolbar-group.right { justify-content: flex-end; }
.toolbar-center     { display: flex; align-items: center; justify-content: center; flex: 0 1 auto; }

/* --- Record / Pause --- */
.action-btn {
  display: flex; align-items: center; justify-content: center;
  height: 22px; width: 22px;
  border-radius: 5px;
  cursor: pointer;
  border: 1px solid transparent;
  transition: all 0.2s;
  outline: none;
  box-shadow: 0 1px 3px rgba(0,0,0,0.15);
  flex-shrink: 0;
}
.action-btn:active { transform: translateY(1px); box-shadow: none; }
.action-btn.pause-action  { background: rgba(239,68,68,.15);  color: var(--error); border-color: rgba(239,68,68,.3); }
.action-btn.pause-action:hover  { background: rgba(239,68,68,.25); }
.action-btn.record-action { background: rgba(16,185,129,.15); color: var(--success); border-color: rgba(16,185,129,.3); }
.action-btn.record-action:hover { background: rgba(16,185,129,.25); }

/* --- Icon buttons (Compose, Clear) --- */
.icon-btn {
  display: flex; align-items: center; justify-content: center;
  height: 22px; width: 24px;
  background: transparent;
  border: 1px solid transparent;
  border-radius: 4px;
  cursor: pointer;
  transition: all 0.2s;
}
.icon-btn svg { transition: stroke 0.2s; }
.icon-btn:hover { background: rgba(255,255,255,.08); }
.icon-btn:hover svg { stroke: var(--fg-secondary) !important; }
.icon-btn.danger:hover { background: rgba(239,68,68,.1); }
.icon-btn.danger:hover svg { stroke: var(--error) !important; }

/* --- Center badge --- */
.app-badge {
  display: flex; align-items: center; gap: 6px;
  height: 22px;
  background: var(--bg-deepest);
  padding: 0 12px;
  border-radius: 11px;
  border: 1px solid var(--border);
  box-shadow: inset 0 1px 3px rgba(0,0,0,0.3);
  cursor: pointer;
  transition: border-color 0.15s, background 0.15s;
  -webkit-app-region: no-drag;
}
.app-badge:hover { border-color: var(--fg-placeholder); }
.app-badge.copied { border-color: var(--success); background: var(--success-muted); }
.status-pulse { width: 6px; height: 6px; border-radius: 50%; flex-shrink: 0; }
.status-pulse.active   { background-color: #10b981; box-shadow: 0 0 6px rgba(16,185,129,.5); }
.status-pulse.inactive { background-color: var(--error); }
.title      { font-weight: 700; color: var(--fg-primary); letter-spacing: 0.5px; font-size: 11px; }
.divider-dot { color: var(--fg-placeholder); font-size: 9px; }
.host       { color: var(--fg-muted); font-family: 'Consolas', monospace; font-size: 10px; }

/* --- Pill buttons --- */
.secondary-pill {
  display: flex; align-items: center; justify-content: center;
  height: 20px;
  padding: 0 5px;
  background: var(--bg-active);
  border: 1px solid var(--border);
  color: var(--fg-muted);
  border-radius: 4px;
  cursor: pointer;
  font-size: 10px;
  letter-spacing: -0.2px;
  font-weight: 500;
  transition: all 0.15s ease;
  outline: none;
  white-space: nowrap;
}
.secondary-pill:hover  { background: var(--bg-active); color: var(--fg-primary); border-color: var(--fg-muted); }
.secondary-pill:active { background: var(--bg-card); }

.secondary-pill.wg-active {
  border-color: rgba(16,185,129,.5);
  color: var(--setup-success);
  background: rgba(16,185,129,.08);
}
.secondary-pill.wg-loading {
  border-color: rgba(251,191,36,.4);
  color: var(--color-breakpoint);
  animation: wg-pulse 1s ease-in-out infinite;
}
@keyframes wg-pulse {
  0%, 100% { opacity: 1; }
  50%       { opacity: 0.55; }
}
.secondary-pill.active-throttle {
  color: var(--method-put);
  background: rgba(245,158,11,.15);
  border-color: rgba(245,158,11,.3);
}
.secondary-pill.active-throttle:hover {
  background: rgba(245,158,11,.25);
  border-color: rgba(245,158,11,.4);
}

/* --- Cert / Throttle wrappers --- */
.cert-wrapper,
.throttle-wrapper { position: relative; }

/* --- Dropdown --- */
.custom-dropdown-menu {
  position: absolute;
  top: calc(100% + 4px);
  right: 0;
  width: 150px;
  background: var(--bg-modal);
  border: 1px solid var(--border);
  border-radius: 6px;
  box-shadow: var(--shadow-md);
  z-index: 1000;
  padding: 4px;
  display: flex;
  flex-direction: column;
}
.dropdown-item {
  padding: 5px 8px;
  font-size: 11px;
  color: var(--fg-secondary);
  cursor: pointer;
  border-radius: 4px;
  display: flex; align-items: center; gap: 6px;
  transition: background 0.15s, color 0.15s;
}
.dropdown-item:hover  { background: var(--bg-active); color: var(--fg-primary); }
.dropdown-item.selected { color: #10b981; background: rgba(16,185,129,.1); }
.dropdown-sep { height: 1px; background: var(--border); margin: 4px 0; }

/* --- Bust Cache toggle --- */
.divider { width: 1px; height: 14px; background: var(--border); margin: 0 2px; flex-shrink: 0; }
.toggle {
  display: flex; align-items: center; gap: 4px;
  cursor: pointer; color: var(--fg-muted); font-weight: 500;
  transition: color 0.2s; height: 20px;
  -webkit-app-region: no-drag;
}
.toggle.active { color: var(--method-put); }
.toggle:hover  { color: var(--fg-secondary); }
.toggle-label  { font-size: 10px; letter-spacing: -0.2px; white-space: nowrap; }
.switch {
  width: 22px; height: 12px;
  background: var(--bg-deepest); border: 1px solid var(--border); border-radius: 14px;
  position: relative; transition: all 0.3s; box-sizing: border-box;
}
.switch::after {
  content: ''; position: absolute; top: 1px; left: 1px;
  width: 8px; height: 8px; background: var(--fg-muted); border-radius: 50%;
  transition: transform 0.3s, background 0.3s;
}
.toggle.active .switch { background: rgba(245,158,11,.15); border-color: #f59e0b; }
.toggle.active .switch::after { transform: translateX(10px); background: var(--method-put); }
</style>