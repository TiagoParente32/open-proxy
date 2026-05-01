<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { disableCache } from '../store.js'
import { currentThemeId, applyTheme } from '../composables/useTheme.js'

const isMac   = () => window.electronAPI?.platform === 'darwin'
const isLinux = () => window.electronAPI?.platform === 'linux'

const eAPI = window.electronAPI
const isMaximized = ref(false)
onMounted(() => eAPI?.onMaximizeChange?.(v => isMaximized.value = v))

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
      { label: 'Bust Cache', action: () => op()?.bustCache(), checked: () => disableCache.value },
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
  {
    label: 'View',
    items: [
      {
        label: 'Theme',
        submenu: [
          { label: 'Dark',     action: () => applyTheme('dark'),     checked: () => currentThemeId.value === 'dark' },
          { label: 'Midnight', action: () => applyTheme('midnight'), checked: () => currentThemeId.value === 'midnight' },
          { label: 'Ocean',    action: () => applyTheme('ocean'),    checked: () => currentThemeId.value === 'ocean' },
          { label: 'Crimson',  action: () => applyTheme('crimson'),  checked: () => currentThemeId.value === 'crimson' },
          { label: 'Light',    action: () => applyTheme('light'),    checked: () => currentThemeId.value === 'light' },
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
  <!-- Windows / Linux only: app name + menu bar + drag region + window controls -->
  <!-- macOS uses AppToolbar as the titlebar (traffic lights + drag region handled there) -->
  <div v-if="!isMac()" class="titlebar-win">

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
              <span class="win-item-check" />
              {{ item.label }}
              <svg class="win-arrow" width="5" height="8" viewBox="0 0 5 8" fill="none">
                <path d="M1 1l3 3-3 3" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/>
              </svg>
              <!-- Submenu -->
              <ul v-if="openSubmenu === item.label" class="win-dropdown win-subdropdown">
                <template v-for="(sub, si) in item.submenu" :key="si">
                  <li v-if="sub.type === 'separator'" class="win-sep" />
                  <li v-else class="win-item" @click.stop="clickItem(sub)">
                    <span class="win-item-check">{{ sub.checked?.() ? '✓' : '' }}</span>
                    {{ sub.label }}
                  </li>
                </template>
              </ul>
            </li>
            <li v-else class="win-item" @click.stop="clickItem(item)">
              <span class="win-item-check">{{ item.checked?.() ? '✓' : '' }}</span>
              {{ item.label }}
            </li>
          </template>
        </ul>
      </div>
    </nav>

    <!-- Drag region -->
    <div class="win-drag" />

    <!-- Linux custom window controls -->
    <div v-if="isLinux()" class="linux-controls">
      <button class="lx-btn" @click="eAPI?.minimize()" title="Minimize">
        <svg width="10" height="10" viewBox="0 0 10 10" fill="none">
          <line x1="1" y1="5" x2="9" y2="5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
        </svg>
      </button>
      <button class="lx-btn" @click="eAPI?.zoom()" :title="isMaximized ? 'Restore' : 'Maximize'">
        <!-- Restore: two overlapping squares -->
        <svg v-if="isMaximized" width="10" height="10" viewBox="0 0 10 10" fill="none">
          <rect x="3" y="1" width="6" height="6" rx="0.8" stroke="currentColor" stroke-width="1.4"/>
          <path d="M1 3.5V8.2A0.8 0.8 0 0 0 1.8 9H6.5" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/>
        </svg>
        <!-- Maximize: single square -->
        <svg v-else width="10" height="10" viewBox="0 0 10 10" fill="none">
          <rect x="1.5" y="1.5" width="7" height="7" rx="0.8" stroke="currentColor" stroke-width="1.4"/>
        </svg>
      </button>
      <button class="lx-btn lx-close" @click="eAPI?.close()" title="Close">
        <svg width="10" height="10" viewBox="0 0 10 10" fill="none">
          <line x1="1.5" y1="1.5" x2="8.5" y2="8.5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
          <line x1="8.5" y1="1.5" x2="1.5" y2="8.5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
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
  height: 30px;
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
  color: var(--fg-secondary);
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
  color: var(--fg-muted);
  cursor: default;
  border-radius: 4px;
  transition: background 0.1s, color 0.1s;
}
.win-menu-root:hover,
.win-menu-root.is-open {
  background: var(--surface-hover-strong);
  color: var(--fg-secondary);
}

/* ── Dropdown ─────────────────────────────────────────────────────────────── */
.win-dropdown {
  position: absolute;
  top: 100%;
  left: 0;
  min-width: 180px;
  background: var(--bg-card);
  border: 1px solid var(--border-subtle);
  border-radius: 4px;
  box-shadow: var(--shadow-lg);
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
  gap: 6px;
  padding: 5px 14px 5px 6px;
  font-size: 12px;
  color: var(--fg-secondary);
  cursor: default;
  white-space: nowrap;
  border-radius: 2px;
  transition: background 0.1s;
}
.win-item:hover,
.win-item--sub.is-open {
  background: var(--surface-hover-strong);
}

.win-sep {
  height: 1px;
  background: var(--border-subtle);
  margin: 3px 0;
}

.win-arrow {
  margin-left: auto;
  opacity: 0.6;
  flex-shrink: 0;
}

.win-item-check {
  width: 12px;
  font-size: 11px;
  color: var(--fg-secondary);
  flex-shrink: 0;
  text-align: center;
}

/* ── Drag spacer ──────────────────────────────────────────────────────────── */
.win-drag {
  flex: 1;
  height: 100%;
  -webkit-app-region: drag;
}

/* ── Linux custom window controls ────────────────────────────────────────── */
.linux-controls {
  display: flex;
  align-items: center;
  gap: 2px;
  padding: 0 8px;
  -webkit-app-region: no-drag;
  flex-shrink: 0;
}

.lx-btn {
  display: flex; align-items: center; justify-content: center;
  width: 26px; height: 26px;
  background: transparent;
  border: none;
  border-radius: 50%;
  color: var(--fg-muted);
  cursor: pointer;
  transition: background 0.12s, color 0.12s;
}
.lx-btn:hover { background: var(--surface-hover-strong); color: var(--fg-primary); }
.lx-close:hover { background: var(--error-muted); color: var(--error); }
</style>
