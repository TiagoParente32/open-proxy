<script setup>
import { ref, onMounted, onUnmounted } from 'vue'

const isMac     = () => window.electronAPI?.platform === 'darwin'
const isWindows = () => window.electronAPI?.platform === 'win32'
const eAPI      = () => window.electronAPI

const minimize = () => eAPI()?.minimize()
const close    = () => eAPI()?.close()
const zoom     = () => eAPI()?.zoom()

// ── Menu structure ────────────────────────────────────────────────────────────
const op = () => window.__op

const MENUS = [
  {
    label: 'Proxy',
    items: [
      { label: 'Record / Pause',  action: () => op()?.toggleRecording() },
      { label: 'Compose Request', action: () => op()?.openComposeNew() },
      { label: 'Clear Traffic',   action: () => op()?.clearTraffic() },
      { type: 'separator' },
      { label: 'Bust Cache',      action: () => op()?.bustCache() },
    ],
  },
  {
    label: 'Tools',
    items: [
      { label: 'VPN Mode',    action: () => op()?.openVpnMode() },
      { label: 'Breakpoints', action: () => op()?.openBreakpoints() },
      { type: 'separator' },
      { label: 'Map Local',   action: () => op()?.openMapLocal() },
      { label: 'Map Remote',  action: () => op()?.openMapRemote() },
      { label: 'Highlight',   action: () => op()?.openHighlight() },
      { type: 'separator' },
      {
        label: 'Certificate Setup',
        submenu: [
          { label: 'Android Emulator',  action: () => op()?.openCertSetup('android_emulator') },
          { label: 'Android Device',    action: () => op()?.openCertSetup('android_device') },
          { type: 'separator' },
          { label: 'iOS Simulator',     action: () => op()?.openCertSetup('ios_simulator') },
          { label: 'iOS Device',        action: () => op()?.openCertSetup('ios_device') },
          { type: 'separator' },
          { label: 'Browser / Desktop', action: () => op()?.openCertSetup('browser') },
        ],
      },
      { type: 'separator' },
      {
        label: 'Throttle',
        submenu: [
          { label: 'No Throttling', action: () => op()?.setThrottle('None') },
          { label: 'Fast 3G',       action: () => op()?.setThrottle('Fast 3G') },
          { label: 'Slow 3G',       action: () => op()?.setThrottle('Slow 3G') },
        ],
      },
    ],
  },
]

// ── Menu state ────────────────────────────────────────────────────────────────
const openMenu    = ref(null)   // index of top-level open menu
const openSubmenu = ref(null)   // label of the item whose submenu is open

const toggleMenu = (i) => {
  openMenu.value    = openMenu.value === i ? null : i
  openSubmenu.value = null
}

const hoverMenu = (i) => {
  // If a menu is already open, switch on hover (like a real menu bar)
  if (openMenu.value !== null) {
    openMenu.value    = i
    openSubmenu.value = null
  }
}

const closeAll = () => {
  openMenu.value    = null
  openSubmenu.value = null
}

const clickItem = (item) => {
  if (item.submenu) return           // submenu items are handled by hover
  if (item.action) item.action()
  closeAll()
}

const handleOutsideClick = (e) => {
  if (!e.target.closest('.win-menubar')) closeAll()
}

onMounted(()  => document.addEventListener('mousedown', handleOutsideClick))
onUnmounted(() => document.removeEventListener('mousedown', handleOutsideClick))
</script>

<template>
  <!-- macOS: drag strip only — native traffic lights (hiddenInset) sit on top -->
  <div v-if="isMac()" class="titlebar-mac" />

  <!-- Windows / Linux: app name + menu bar + drag region + window controls -->
  <div v-else class="titlebar-win">

    <!-- App name (non-draggable left side) -->
    <span class="win-app-name" @dblclick.stop>OpenProxy</span>

    <!-- Menu bar -->
    <nav class="win-menubar" @dblclick.stop>
      <div
        v-for="(menu, mi) in MENUS"
        :key="menu.label"
        class="win-menu-root"
        :class="{ 'is-open': openMenu === mi }"
        @click="toggleMenu(mi)"
        @mouseenter="hoverMenu(mi)"
      >
        {{ menu.label }}

        <!-- Dropdown -->
        <ul v-if="openMenu === mi" class="win-dropdown">
          <template v-for="(item, ii) in menu.items" :key="ii">
            <li v-if="item.type === 'separator'" class="win-sep" />
            <li
              v-else-if="item.submenu"
              class="win-item win-item--sub"
              :class="{ 'is-open': openSubmenu === item.label }"
              @mouseenter="openSubmenu = item.label"
              @mouseleave="openSubmenu = null"
            >
              {{ item.label }}
              <svg class="win-arrow" width="5" height="8" viewBox="0 0 5 8" fill="none">
                <path d="M1 1l3 3-3 3" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/>
              </svg>
              <!-- Submenu -->
              <ul v-if="openSubmenu === item.label" class="win-dropdown win-subdropdown">
                <template v-for="(sub, si) in item.submenu" :key="si">
                  <li v-if="sub.type === 'separator'" class="win-sep" />
                  <li v-else class="win-item" @click.stop="clickItem(sub)">{{ sub.label }}</li>
                </template>
              </ul>
            </li>
            <li v-else class="win-item" @click.stop="clickItem(item)">{{ item.label }}</li>
          </template>
        </ul>
      </div>
    </nav>

    <!-- Drag region fills remaining space -->
    <div class="win-drag" />

    <!-- Window controls — Linux only; Windows uses native OS overlay buttons -->
    <div v-if="!isWindows()" class="win-controls" @dblclick.stop>
      <button class="win-btn" @click="minimize" title="Minimise">
        <svg viewBox="0 0 10 10">
          <line x1="1" y1="5" x2="9" y2="5"
                stroke="currentColor"
                stroke-width="1"
                stroke-linecap="square"/>
        </svg>
      </button>

      <button class="win-btn" @click="zoom" title="Maximise / Restore">
        <svg viewBox="0 0 10 10">
          <rect x="1" y="1" width="8" height="8"
                stroke="currentColor"
                stroke-width="1"
                fill="none"/>
        </svg>
      </button>

      <button class="win-btn win-close" @click="close" title="Close (hides to tray)">
        <svg viewBox="0 0 10 10">
          <line x1="2" y1="2" x2="8" y2="8"
                stroke="currentColor"
                stroke-width="1"
                stroke-linecap="square"/>
          <line x1="8" y1="2" x2="2" y2="8"
                stroke="currentColor"
                stroke-width="1"
                stroke-linecap="square"/>
        </svg>
      </button>
    </div>
  </div>
</template>

<style scoped>
/* ── macOS drag strip ──────────────────────────────────────────────────────── */
.titlebar-mac {
  height: 38px;
  background: var(--bg-sidebar);
  flex-shrink: 0;
  user-select: none;
  -webkit-app-region: drag;
}

/* ── Windows titlebar shell ───────────────────────────────────────────────── */
.titlebar-win {
  display: flex;
  align-items: center;
  height: 38px;
  background: var(--bg-sidebar);
  flex-shrink: 0;
  user-select: none;
  -webkit-app-region: drag;   /* overridden on interactive children */
}

/* ── App name ─────────────────────────────────────────────────────────────── */
.win-app-name {
  padding: 0 8px 0 12px;
  font-size: 12px;
  font-weight: 600;
  color: #cdd9e5;
  letter-spacing: 0.02em;
  white-space: nowrap;
  -webkit-app-region: no-drag;
}

/* ── Menu bar ─────────────────────────────────────────────────────────────── */
.win-menubar {
  display: flex;
  align-items: stretch;
  height: 100%;
  -webkit-app-region: no-drag;
}

.win-menu-root {
  position: relative;
  display: flex;
  align-items: center;
  padding: 0 10px;
  font-size: 12px;
  color: #8b949e;
  cursor: default;
  border-radius: 4px;
  transition: background 0.1s, color 0.1s;
}
.win-menu-root:hover,
.win-menu-root.is-open {
  background: rgba(255,255,255,0.08);
  color: #cdd9e5;
}

/* ── Dropdown ─────────────────────────────────────────────────────────────── */
.win-dropdown {
  position: absolute;
  top: 100%;
  left: 0;
  min-width: 180px;
  background: #1e2228;
  border: 1px solid rgba(255,255,255,0.12);
  border-radius: 4px;
  box-shadow: 0 8px 24px rgba(0,0,0,0.5);
  list-style: none;
  margin: 2px 0 0;
  padding: 4px 0;
  z-index: 9999;
}

.win-item--sub {
  position: relative;
}

.win-subdropdown {
  top: -4px;   /* account for dropdown's top padding so row aligns flush */
  left: 100%;
  margin: 0;   /* no gap — mouse can slide directly across */
}

.win-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 5px 14px;
  font-size: 12px;
  color: #cdd9e5;
  cursor: default;
  white-space: nowrap;
  border-radius: 2px;
  transition: background 0.1s;
}
.win-item:hover,
.win-item--sub.is-open {
  background: rgba(255,255,255,0.1);
}

.win-sep {
  height: 1px;
  background: rgba(255,255,255,0.1);
  margin: 3px 0;
}

.win-arrow {
  margin-left: 12px;
  opacity: 0.6;
  flex-shrink: 0;
}

/* ── Drag spacer ──────────────────────────────────────────────────────────── */
.win-drag {
  flex: 1;
  height: 100%;
  -webkit-app-region: drag;
}

/* ── Window controls ──────────────────────────────────────────────────────── */
.win-controls {
  display: flex;
  align-items: stretch;
  height: 100%;
  -webkit-app-region: no-drag;
}
.win-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 46px;
  height: 100%;
  background: transparent;
  border: none;
  color: #8b949e;
  cursor: pointer;
  transition: background 0.15s, color 0.15s;
}

/* FIXED ICON SIZE */
.win-btn svg {
  width: 10px;
  height: 10px;
  flex-shrink: 0;
}

.win-btn:hover {
  background: rgba(255,255,255,0.1);
  color: #fff;
}

.win-close:hover {
  background: #e81123;
  color: #fff;
}
</style>

