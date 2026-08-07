<script setup>
import { onMounted, onUnmounted, watch, computed, ref, nextTick } from 'vue'
import { version as appVersion } from '../../package.json'
import { initTheme } from './composables/useTheme'
initTheme()
import { Splitpanes, Pane } from 'splitpanes'
import 'splitpanes/dist/splitpanes.css'

// Import our new components!
import TitleBar from './components/TitleBar.vue'
import AppToolbar from './components/AppToolbar.vue'
import AppSidebar from './components/AppSidebar.vue'
import TrafficTable from './components/TrafficTable.vue'
import InspectorPane from './components/InspectorPane.vue'
import MapLocalModal from './components/MapLocalModal.vue'
import BreakpointHit from './components/BreakpointHit.vue'
import BreakpointsModal from './components/BreakpointsModal.vue'
import ComposeModal from './components/ComposeModal.vue'
import MapRemoteModal from './components/MapRemoteModal.vue'
import FilterBar from './components/FilterBar.vue'
import HighlightModal from './components/HighlightModal.vue'
import DeviceSetupModal from './components/DeviceSetupModal.vue'
import ScriptingModal from './components/ScriptingModal.vue'
import ProgressOverlay from './components/ProgressOverlay.vue'
import IgnoreHostsModal from './components/IgnoreHostsModal.vue'
import OnboardingModal from './components/OnboardingModal.vue'
import KeyboardShortcutsModal from './components/KeyboardShortcutsModal.vue'
import OsProxyWarningModal from './components/OsProxyWarningModal.vue'
// Import just the logic needed for the top-level app overlay (WebSockets & Context Menu)
import { 
  initWebSocket, 
  closeContextMenu, 
  contextMenu, 
  formatUrl, 
  showMapModal, 
  mapLocalRules, 
  selectedRuleId,
  showBreakpointModal,
  breakpointRules,
  selectedBreakpointId,
  repeatRequest,
  openComposeModal,
  showMapRemoteModal,
  mapRemoteRules,
  selectedMapRemoteId,
  toggleRecording,
  requests,
  wsMessages,
  selectedRequest,
  openComposeNew,
  openVpnMode,
  showHighlightModal,
  showScriptingModal,
  deviceSetupType,
  showDeviceSetupModal,
  throttleProfile,
  disableCache,
  updateInfo,
  updateProgress,
  updateError,
  upToDate,
  checkForUpdates,
  applyUpdate,
  toolbarVisibility,
  macosProxyActive,
  toggleMacProxy,
  proxyHttp2,
  proxyUpstreamCert,
  proxyHostFilterMode,
  toggleProxyHttp2,
  toggleProxyUpstreamCert,
  showIgnoreHostsModal,
  resetPreferences,
  exportSettings,
  importSettings,
  exportHostFilter,
  importHostFilter,
  showComposeModal,
  pinSource,
  closeAllModals,
} from './store.js'

onMounted(() => {
  initWebSocket()
  document.addEventListener('click', closeContextMenu)

  // Sync bust cache state with the native macOS menu (keeps checkmark accurate)
  window.electronAPI?.bustCacheSync(disableCache.value)
  watch(disableCache, val => window.electronAPI?.bustCacheSync(val))

  // Same dance for the macOS system proxy toggle so the Tools menu checkmark tracks state
  window.electronAPI?.macosProxySync?.(macosProxyActive.value)
  watch(macosProxyActive, val => window.electronAPI?.macosProxySync?.(val))

  // Sync proxy compat options with native menu checkmarks
  window.electronAPI?.proxyHttp2Sync?.(proxyHttp2.value)
  window.electronAPI?.proxyUpstreamCertSync?.(proxyUpstreamCert.value)
  window.electronAPI?.proxyHostFilterModeSync?.(proxyHostFilterMode.value)
  watch(proxyHttp2,         val  => window.electronAPI?.proxyHttp2Sync?.(val))
  watch(proxyUpstreamCert,  val  => window.electronAPI?.proxyUpstreamCertSync?.(val))
  watch(proxyHostFilterMode, mode => window.electronAPI?.proxyHostFilterModeSync?.(mode))

  // Sync toolbar visibility with native menu on startup (main process always starts fresh)
  window.electronAPI?.toolbarSyncToMain?.({ ...toolbarVisibility.value })
  // When native menu toggles a toolbar item, main pushes the new state here
  window.electronAPI?.onToolbarSet?.((vis) => {
    Object.assign(toolbarVisibility.value, vis)
  })

  // Native app menu bridge — Python calls window.__op.xxx() via evaluate_js
  window.__op = {
    toggleRecording:  () => toggleRecording(),
    clearTraffic:     () => { requests.value.length = 0; wsMessages.value = {}; selectedRequest.value = null },
    openComposeNew:   () => openComposeNew(),
    openVpnMode:      () => openVpnMode(),
    openBreakpoints:  () => { closeAllModals(); showBreakpointModal.value = true },
    openMapLocal:     () => { closeAllModals(); showMapModal.value = true },
    openMapRemote:    () => { closeAllModals(); showMapRemoteModal.value = true },
    openHighlight:    () => { closeAllModals(); showHighlightModal.value = true },
    openScripting:    () => { closeAllModals(); showScriptingModal.value = true },
    openCertSetup:    (type) => { deviceSetupType.value = type; closeAllModals(); showDeviceSetupModal.value = true },
    setThrottle:      (profile) => { throttleProfile.value = profile },
    bustCache:        () => { disableCache.value = !disableCache.value },
    toggleMacProxy:   () => toggleMacProxy(),
    toggleProxyHttp2:       () => toggleProxyHttp2(),
    toggleProxyUpstreamCert: () => toggleProxyUpstreamCert(),
    openIgnoreHosts:  () => { closeAllModals(); showIgnoreHostsModal.value = true },
    checkForUpdates:  () => checkForUpdates(),
    toggleToolbarVisibility: (tool) => { toolbarVisibility.value[tool] = !toolbarVisibility.value[tool] },
    showAbout:        () => { showAboutModal.value = true },
    resetPreferences: () => resetPreferences(),
    exportSettings:   () => exportSettings(),
    importSettings:   () => importSettings(),
    exportHostFilter: () => exportHostFilter(),
    importHostFilter: () => importHostFilter(),
    focusSearch:      () => document.dispatchEvent(new CustomEvent('openproxy:focus-search')),
    openShortcuts:    () => { showShortcutsModal.value = true },
    showOnboarding:   () => { closeAllModals(); showOnboardingModal.value = true },
  }

  // ── Global keyboard shortcuts ────────────────────────────────────────────
  const handleGlobalKey = (e) => {
    const tag = document.activeElement?.tagName
    const isEditing = tag === 'INPUT' || tag === 'TEXTAREA' || document.activeElement?.isContentEditable
    const cmd   = e.metaKey || e.ctrlKey
    const shift = e.shiftKey
    if (cmd && shift && e.code === 'KeyR') { e.preventDefault(); toggleRecording() }
    else if (cmd && !shift && e.code === 'KeyK') { e.preventDefault(); requests.value.length = 0; wsMessages.value = {}; selectedRequest.value = null }
    else if (cmd && !shift && e.code === 'KeyN' && !isEditing) { e.preventDefault(); openComposeNew() }
    else if (cmd && !shift && e.code === 'KeyF') { e.preventDefault(); document.dispatchEvent(new CustomEvent('openproxy:focus-search')) }
    else if (cmd && shift && e.code === 'KeyM') { e.preventDefault(); closeAllModals(); showMapModal.value = true }
    else if (cmd && shift && e.code === 'KeyE') { e.preventDefault(); closeAllModals(); showMapRemoteModal.value = true }
    else if (cmd && shift && e.code === 'KeyB') { e.preventDefault(); closeAllModals(); showBreakpointModal.value = true }
    else if (cmd && shift && e.code === 'KeyH') { e.preventDefault(); closeAllModals(); showHighlightModal.value = true }
    else if (cmd && shift && e.code === 'KeyS') { e.preventDefault(); closeAllModals(); showScriptingModal.value = true }
    else if (cmd && shift && e.code === 'KeyV') { e.preventDefault(); openVpnMode() }
    else if (cmd && shift && e.code === 'Slash') { e.preventDefault(); showShortcutsModal.value = true }
    else if (e.key === 'Escape') {
      // Close the topmost open modal first
      if      (showShortcutsModal.value)    showShortcutsModal.value    = false
      else if (showOnboardingModal.value)   showOnboardingModal.value   = false
      else if (showIgnoreHostsModal.value)  showIgnoreHostsModal.value  = false
      else if (showScriptingModal.value)    showScriptingModal.value    = false
      else if (showDeviceSetupModal.value)  showDeviceSetupModal.value  = false
      else if (showComposeModal.value)      showComposeModal.value      = false
      else if (showBreakpointModal.value)   showBreakpointModal.value   = false
      else if (showHighlightModal.value)    showHighlightModal.value    = false
      else if (showMapRemoteModal.value)    showMapRemoteModal.value    = false
      else if (showMapModal.value)          showMapModal.value          = false
    }
  }
  window.addEventListener('keydown', handleGlobalKey)
  onUnmounted(() => window.removeEventListener('keydown', handleGlobalKey))

  window.electronAPI?.onResetPreferences?.(() => resetPreferences())
})

onUnmounted(() => {
  document.removeEventListener('click', closeContextMenu)
})

const isLinux = window.electronAPI?.platform === 'linux'

const showUpdateModal = computed(() =>
  !!(updateInfo.value || updateProgress.value !== null || updateError.value || upToDate.value)
)

const showAboutModal  = ref(false)
const showShortcutsModal = ref(false)

// The onboarding flow was introduced in this app version. It should appear:
//  1. On a brand-new install (no local data at all), or
//  2. When updating from an older version that predates onboarding
//     (app data/settings exist, but the onboarding flag was never set).
// Once a user completes onboarding, `openproxyOnboardingDone` persists across
// updates and it must never be shown again automatically.
const ONBOARDING_INTRODUCED_VERSION = '1.0.5'

const compareVersions = (a, b) => {
  const pa = String(a).split('.').map(Number)
  const pb = String(b).split('.').map(Number)
  for (let i = 0; i < Math.max(pa.length, pb.length); i++) {
    const diff = (pa[i] || 0) - (pb[i] || 0)
    if (diff !== 0) return diff
  }
  return 0
}

const hasOnboarded = !!localStorage.getItem('openproxyOnboardingDone')
const onboardedVersion = localStorage.getItem('openproxyOnboardingVersion')
// Any pre-existing openproxy_* setting means this isn't a fresh install.
const hasPriorInstallData = Object.keys(localStorage).some(k => k.startsWith('openproxy_') || k === 'openproxy-theme')

const needsOnboarding = !hasOnboarded && (
  !hasPriorInstallData || // fresh install
  !onboardedVersion || compareVersions(onboardedVersion, ONBOARDING_INTRODUCED_VERSION) < 0 // updated from a version without onboarding
)

const showOnboardingModal = ref(needsOnboarding)
// Whether there is pre-existing user data to prefill the onboarding steps with
// (vs. a truly blank/fresh install where defaults make more sense).
const onboardingPrefill = hasPriorInstallData

const contextMenuEl = ref(null)
watch(() => [contextMenu.value.x, contextMenu.value.y, contextMenu.value.show], ([,, visible]) => {
  if (!visible) return
  nextTick(() => {
    const el = contextMenuEl.value
    if (!el) return
    const rect = el.getBoundingClientRect()
    if (rect.bottom > window.innerHeight) {
      contextMenu.value.y = Math.max(0, contextMenu.value.y - rect.height)
    }
    if (rect.right > window.innerWidth) {
      contextMenu.value.x = Math.max(0, contextMenu.value.x - rect.width)
    }
  })
})

const openReleaseNotes = () => {
  if (updateInfo.value?.release_url) window.electronAPI?.openExternal(updateInfo.value.release_url)
}

const openGitHub = () => {
  window.electronAPI?.openExternal('https://github.com/TiagoParente32/open-proxy')
}

const openReleasesManually = () => {
  window.electronAPI?.openExternal('https://github.com/TiagoParente32/open-proxy/releases/latest')
}

const startUpdate = () => {
  if (updateInfo.value?.download_url) applyUpdate(updateInfo.value.download_url)
}

const dismissUpdate = () => {
  updateInfo.value    = null
  updateError.value   = null
  updateProgress.value = null
  upToDate.value      = false
}

const handleEditAndRepeatFromContext = () => {
  if (contextMenu.value.request) {
    openComposeModal(contextMenu.value.request);
  }
  closeContextMenu();
}

const handleRepeatFromContext = () => {
  repeatRequest();
  closeContextMenu();
}


// --- COLOR & STAR LOGIC ---
const toggleStar = () => {
  if (contextMenu.value.request) {
    // Flip the boolean
    contextMenu.value.request.starred = !contextMenu.value.request.starred;
  }
  closeContextMenu();
}

const setRowColor = (colorClass) => {
  if (contextMenu.value.request) {
    contextMenu.value.request.color = colorClass;
    contextMenu.value.request.manualColor = colorClass !== null;
  }
  closeContextMenu()
}

const copyUrl = () => {
  if (contextMenu.value.request?.url) {
    navigator.clipboard.writeText(contextMenu.value.request.url)
  }
  closeContextMenu()
}

const pinFromContextMenu = () => {
  if (contextMenu.value.request) {
    const host = formatUrl(contextMenu.value.request.url).host
    if (host) pinSource(host)
  }
  closeContextMenu()
}

const openMapRemoteModalFromContext = () => {
  closeContextMenu();
  if (contextMenu.value.request) {
    const req = contextMenu.value.request;
    
    // Strip query params and escape dots for a safe regex pattern
    let defaultPattern = req.url.split('?')[0].replace(/\./g, '\\.');

    const newRule = { 
      id: Date.now(), 
      active: true, 
      pattern: defaultPattern, 
      target: 'http://localhost:8080' // Default target for dev servers
    };
    
    mapRemoteRules.value.unshift(newRule);
    selectedMapRemoteId.value = newRule.id;
  } else if (mapRemoteRules.value.length > 0 && !selectedMapRemoteId.value) {
    selectedMapRemoteId.value = mapRemoteRules.value[0].id;
  }
  
  closeAllModals()
  showMapRemoteModal.value = true;
}

const openMapLocalModalFromContext = () => {
  closeContextMenu();
  if (contextMenu.value.request) {
    const req = contextMenu.value.request;
    const realStatus = req.status !== '...' ? Number(req.status) : 200;
    
    const realHeaders = req.res_headers && Object.keys(req.res_headers).length > 0 
      ? JSON.stringify(req.res_headers, null, 2) 
      : '{\n  "Content-Type": "application/json"\n}';
      
    let realBody = req.res_body || '';
    try { 
      if (realBody) realBody = JSON.stringify(JSON.parse(realBody), null, 2); 
    } catch (e) {}

    const newRule = { 
      id: Date.now(), 
      active: true, 
      // Keep the FULL URL so the Map Local grid can parse the parameters
      pattern: req.url, 
      method: req.method || 'ANY',
      status: realStatus, 
      headers: realHeaders, 
      body: realBody,
      req_headers_mod: req.req_headers || {}
    };
    
    mapLocalRules.value.unshift(newRule);
    selectedRuleId.value = newRule.id;
  } else if (mapLocalRules.value.length > 0 && !selectedRuleId.value) {
    selectedRuleId.value = mapLocalRules.value[0].id;
  }
  closeAllModals()
  showMapModal.value = true;
}

const openBreakpointModalFromContext = () => {
  closeContextMenu();
  if (contextMenu.value.request) {
    const req = contextMenu.value.request;
    
    let defaultPattern = decodeURIComponent(req.url.split('?')[0]);

    const newRule = { 
      id: Date.now(), 
      active: true, 
      pattern: defaultPattern, 
      is_request: true, 
      is_response: false 
    };
    
    breakpointRules.value.unshift(newRule);
    selectedBreakpointId.value = newRule.id;
  } else if (breakpointRules.value.length > 0 && !selectedBreakpointId.value) {
    selectedBreakpointId.value = breakpointRules.value[0].id;
  }
  
  closeAllModals()
  showBreakpointModal.value = true;
}
</script>

<template>
  <div class="app-wrapper">
    <TitleBar />
    <AppToolbar />
    <FilterBar />

    <!-- Update Modal -->
    <Teleport to="body">
      <Transition name="update-modal">
        <div v-if="showUpdateModal" class="update-modal-overlay"
             @mousedown.self="updateProgress === null && dismissUpdate()">
          <div class="update-modal">

            <!-- ── Available ── -->
            <template v-if="updateInfo && updateProgress === null && !updateError">
              <button class="update-modal-close" @click="dismissUpdate" title="Dismiss">
                <svg width="12" height="12" viewBox="0 0 14 14" fill="none"><path d="M1 1l12 12M13 1L1 13" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>
              </button>

              <div class="update-modal-icon">
                <svg width="36" height="36" viewBox="0 0 24 24" fill="none">
                  <circle cx="12" cy="12" r="9.5" stroke="var(--accent)" stroke-width="1.5"/>
                  <path d="M12 15.5V8.5M9 11.5l3-3 3 3" stroke="var(--accent)" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
                </svg>
              </div>

              <h3 class="update-modal-title">Update Available</h3>

              <div class="update-version-row">
                <span class="update-version-badge current">{{ updateInfo.current }}</span>
                <svg width="18" height="10" viewBox="0 0 18 10" fill="none" class="update-arrow-svg">
                  <path d="M1 5h16M12 1l5 4-5 4" stroke="var(--fg-muted)" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
                </svg>
                <span class="update-version-badge latest">{{ updateInfo.version }}</span>
              </div>

              <button v-if="updateInfo.release_url" class="update-release-link" @click="openReleaseNotes">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none">
                  <path d="M18 13v6a2 2 0 01-2 2H5a2 2 0 01-2-2V8a2 2 0 012-2h6M15 3h6v6M10 14L21 3" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                </svg>
                View release notes
              </button>

              <div class="update-modal-actions">
                <button class="update-btn-skip" @click="dismissUpdate">Skip</button>
                <button class="update-btn-install" :disabled="!updateInfo.download_url" @click="startUpdate">
                  {{ updateInfo.download_url ? 'Update Now' : 'Not available for this platform' }}
                </button>
              </div>
            </template>

            <!-- ── Downloading ── -->
            <template v-else-if="updateProgress !== null">
              <div class="update-modal-icon">
                <svg width="36" height="36" viewBox="0 0 24 24" fill="none">
                  <circle cx="12" cy="12" r="9.5" stroke="var(--accent)" stroke-width="1.5"/>
                  <path d="M12 8.5v7M9 12.5l3 3 3-3" stroke="var(--accent)" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
                </svg>
              </div>
              <h3 class="update-modal-title">Downloading Update</h3>
              <p class="update-modal-sub">Installing {{ updateInfo?.version }}…</p>
              <div class="update-progress-track">
                <div class="update-progress-fill" :style="{ width: updateProgress + '%' }"></div>
              </div>
              <span class="update-progress-pct">{{ updateProgress }}%</span>
              <p class="update-modal-hint">
                {{ isLinux
                  ? 'The app will close — please relaunch it manually when done.'
                  : 'The app will restart automatically when done.' }}
              </p>
            </template>

            <!-- ── Error ── -->
            <template v-else-if="updateError">
              <button class="update-modal-close" @click="dismissUpdate" title="Dismiss">
                <svg width="12" height="12" viewBox="0 0 14 14" fill="none"><path d="M1 1l12 12M13 1L1 13" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>
              </button>
              <div class="update-modal-icon error">
                <svg width="36" height="36" viewBox="0 0 24 24" fill="none">
                  <path d="M12 9v4M12 16.5h.01" stroke="var(--error)" stroke-width="1.8" stroke-linecap="round"/>
                  <path d="M10.61 4.42l-8.19 14A1.5 1.5 0 003.69 20.5h16.62a1.5 1.5 0 001.27-2.08l-8.19-14a1.5 1.5 0 00-2.78 0z" stroke="var(--error)" stroke-width="1.5" stroke-linejoin="round"/>
                </svg>
              </div>
              <h3 class="update-modal-title">Update Failed</h3>
              <p class="update-modal-error-msg">{{ updateError }}</p>
              <p class="update-modal-hint">
                If this keeps happening, you can download and install the latest
                version manually from GitHub.
              </p>
              <div class="update-modal-actions">
                <button class="update-btn-skip" @click="openReleasesManually">Download Manually</button>
                <button class="update-btn-install" @click="dismissUpdate">Dismiss</button>
              </div>
            </template>

            <!-- ── Up to date ── -->
            <template v-else-if="upToDate">
              <button class="update-modal-close" @click="dismissUpdate" title="Dismiss">
                <svg width="12" height="12" viewBox="0 0 14 14" fill="none"><path d="M1 1l12 12M13 1L1 13" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>
              </button>
              <div class="update-modal-icon">
                <svg width="36" height="36" viewBox="0 0 24 24" fill="none">
                  <circle cx="12" cy="12" r="9.5" stroke="var(--accent)" stroke-width="1.5"/>
                  <path d="M8 12.5l3 3 5-5" stroke="var(--accent)" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
                </svg>
              </div>
              <h3 class="update-modal-title">You're up to date</h3>
              <p class="update-modal-sub">v{{ appVersion }} is the latest version.</p>
            </template>

          </div>
        </div>
      </Transition>
    </Teleport>

    <!-- About Modal -->
    <Teleport to="body">
      <Transition name="update-modal">
        <div v-if="showAboutModal" class="update-modal-overlay" @mousedown.self="showAboutModal = false">
          <div class="update-modal">
            <button class="update-modal-close" @click="showAboutModal = false" title="Close">
              <svg width="12" height="12" viewBox="0 0 14 14" fill="none"><path d="M1 1l12 12M13 1L1 13" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>
            </button>
            <img src="../../icon.png" style="width:52px;height:52px;border-radius:12px;margin-bottom:14px;" alt="OpenProxy icon" />
            <h3 class="update-modal-title" style="margin-bottom:4px;">OpenProxy</h3>
            <span class="update-version-badge latest" style="margin-bottom:16px;">v{{ appVersion }}</span>
            <p class="update-modal-hint" style="opacity:1;margin-bottom:20px;max-width:220px;text-align:center;line-height:1.6;">
              A powerful HTTP/HTTPS proxy tool for developers.
            </p>
            <button class="update-release-link" @click="openGitHub">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none">
                <path d="M18 13v6a2 2 0 01-2 2H5a2 2 0 01-2-2V8a2 2 0 012-2h6M15 3h6v6M10 14L21 3" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
              </svg>
              GitHub
            </button>
          </div>
        </div>
      </Transition>
    </Teleport>

    <splitpanes class="default-theme custom-theme" style="flex: 1; overflow: hidden;">
      
      <pane min-size="15" size="20">
        <AppSidebar />
      </pane>

      <pane size="80">
        <splitpanes horizontal class="custom-theme">
          
          <pane min-size="20" size="45">
            <TrafficTable />
          </pane>

          <pane size="55">
            <InspectorPane />
          </pane>

        </splitpanes>
      </pane>

    </splitpanes>

   <div v-if="contextMenu.show" ref="contextMenuEl" class="context-menu" :style="{ top: contextMenu.y + 'px', left: contextMenu.x + 'px' }">
      
      <!-- Group: Request actions -->
      <div class="ctx-group-label">Request</div>
      <div class="context-menu-item" @click="handleRepeatFromContext">Repeat</div>
      <div class="context-menu-item" @click="handleEditAndRepeatFromContext">Edit &amp; Repeat</div>
      <div class="context-menu-item" @click="copyUrl">Copy URL</div>

      <div class="context-menu-divider"></div>

      <!-- Group: Mark -->
      <div class="ctx-group-label">Mark</div>
      <div class="context-menu-item ctx-star-item" @click="toggleStar">
        <svg width="13" height="13" viewBox="0 0 24 24" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"
          :fill="contextMenu.request?.starred ? 'var(--warning)' : 'none'"
          :stroke="contextMenu.request?.starred ? 'var(--warning)' : 'currentColor'">
          <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/>
        </svg>
        {{ contextMenu.request?.starred ? 'Unstar' : 'Star' }}
      </div>
      <div class="context-menu-colors">
        <div class="color-dot red"    @click="setRowColor('red')"    title="Red"></div>
        <div class="color-dot orange" @click="setRowColor('orange')" title="Orange"></div>
        <div class="color-dot yellow" @click="setRowColor('yellow')" title="Yellow"></div>
        <div class="color-dot green"  @click="setRowColor('green')"  title="Green"></div>
        <div class="color-dot blue"   @click="setRowColor('blue')"   title="Blue"></div>
        <div class="color-dot purple" @click="setRowColor('purple')" title="Purple"></div>
        <div class="color-dot clear"  @click="setRowColor(null)"     title="Clear"></div>
      </div>

      <div class="context-menu-divider"></div>

      <!-- Group: Tools -->
      <div class="ctx-group-label">Tools</div>
      <div class="context-menu-item" @click="pinFromContextMenu">Pin Domain</div>
      <div class="context-menu-item" @click="openMapLocalModalFromContext">Map Local</div>
      <div class="context-menu-item" @click="openMapRemoteModalFromContext">Map Remote</div>
      <div class="context-menu-item" @click="openBreakpointModalFromContext">Add Breakpoint</div>
    </div>

    <MapLocalModal />
    <MapRemoteModal />
    <BreakpointHit />
    <BreakpointsModal />
    <ComposeModal />
    <HighlightModal />
    <DeviceSetupModal />
    <ScriptingModal />
    <IgnoreHostsModal :show="showIgnoreHostsModal" @close="showIgnoreHostsModal = false" />
    <OnboardingModal v-if="showOnboardingModal" :app-version="appVersion" :prefill="onboardingPrefill" @done="showOnboardingModal = false" />
    <KeyboardShortcutsModal v-if="showShortcutsModal" @close="showShortcutsModal = false" />
    <OsProxyWarningModal />
  </div>
</template>

<style>
:root { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
body { margin: 0; padding: 0; }
.app-wrapper { display: flex; flex-direction: column; height: 100vh; overflow: hidden; }

/* --- SPLITPANES THEME OVERRIDES --- */
.splitpanes.custom-theme .splitpanes__pane { background-color: var(--bg-main); }
.splitpanes.custom-theme .splitpanes__splitter { background-color: var(--border); transition: background-color 0.2s; }
.splitpanes.custom-theme .splitpanes__splitter:hover { background-color: var(--fg-muted); }
.splitpanes.custom-theme.splitpanes--vertical > .splitpanes__splitter { width: 3px; border-left: 1px solid var(--bg-deepest); }
.splitpanes.custom-theme.splitpanes--horizontal > .splitpanes__splitter { height: 3px; border-top: 1px solid var(--bg-deepest); }

/* --- SHARED UTILITIES --- */
.action-btn { background: transparent; border: 1px solid var(--border); color: var(--fg-muted); padding: 4px 12px; border-radius: 4px; cursor: pointer; font-size: 12px; transition: all 0.2s; outline: none !important; }
.action-btn:focus { outline: none !important; box-shadow: none !important; }
.action-btn:hover { background: var(--surface-hover-strong); color: var(--fg-primary); }
.truncate { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.text-muted { color: var(--fg-muted); }
.font-semibold { font-weight: 600; color: var(--fg-secondary); }
.text-green { color: var(--success) !important; }
.text-red { color: var(--error) !important; }
.global-empty { display: flex; justify-content: center; align-items: center; height: 100%; color: var(--fg-muted); font-style: italic; font-size: 12px; }
.text-icon { font-size: 12px; color: var(--fg-muted); }

/* --- GLOBAL CONTEXT MENU --- */
.context-menu {
  position: fixed;
  background: var(--bg-card);
  border: 1px solid var(--border);
  box-shadow: var(--shadow-lg);
  border-radius: 8px;
  padding: 4px;
  z-index: 9999;
  min-width: 170px;
  max-height: calc(100vh - 16px);
  overflow-y: auto;
}
.ctx-group-label {
  padding: 4px 10px 2px;
  font-size: 10px;
  font-weight: 700;
  color: var(--fg-muted);
  letter-spacing: 0.5px;
  text-transform: uppercase;
  user-select: none;
}
.context-menu-item {
  padding: 6px 10px;
  font-size: 12.5px;
  color: var(--fg-secondary);
  cursor: pointer;
  border-radius: 5px;
  text-align: left;
}
.ctx-star-item { display: flex; align-items: center; gap: 7px; }
.context-menu-item:hover { background: var(--accent); color: var(--fg-primary); }
.context-menu-divider { height: 1px; background: var(--border); margin: 3px 4px; }

.context-menu-colors {
  display: flex;
  align-items: center;
  justify-content: flex-start;
  padding: 5px 10px 6px;
  gap: 7px;
}
.color-dot {
  width: 15px; height: 15px; border-radius: 50%; cursor: pointer;
  transition: transform 0.12s, box-shadow 0.12s;
  flex-shrink: 0;
}
.color-dot:hover { transform: scale(1.25); box-shadow: 0 0 0 2px rgba(255,255,255,0.25); }
.color-dot.red    { background: #ef4444; }
.color-dot.orange { background: #f97316; }
.color-dot.yellow { background: #f59e0b; }
.color-dot.green  { background: #10b981; }
.color-dot.blue   { background: #3b82f6; }
.color-dot.purple { background: #8b5cf6; }
.color-dot.clear  { background: transparent; border: 1.5px dashed #555; position: relative; }
.color-dot.clear::after { content: ''; position: absolute; top: 50%; left: 50%; width: 130%; height: 1.5px; background: #666; transform: translate(-50%,-50%) rotate(45deg); }

/* --- CODEMIRROR GLOBAL FIXES --- */
.cm-editor { height: 100% !important; outline: none !important; text-align: left !important; }
.cm-scroller { align-items: flex-start !important; justify-content: flex-start !important; }
.cm-content { padding: 12px 0 !important; }

/* --- TEXT SELECTION FIXES --- */
.traffic-table, .inspector-content, .modal-editor, .cm-editor, .cm-content { -webkit-user-select: text !important; user-select: text !important; cursor: text; }
.toolbar, .sidebar, .action-btn, .panel-tabs, .sidebar-header, .splitpanes__splitter { -webkit-user-select: none !important; user-select: none !important; }

/* --- UPDATE MODAL --- */
.update-modal-overlay {
  position: fixed;
  inset: 0;
  background: var(--overlay);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 9000;
}
.update-modal {
  position: relative;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 12px;
  box-shadow: var(--shadow-lg);
  padding: 32px 28px 24px;
  width: 340px;
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  gap: 0;
}
.update-modal-close {
  position: absolute;
  top: 12px;
  right: 12px;
  background: none;
  border: none;
  color: var(--fg-muted);
  cursor: pointer;
  padding: 5px;
  border-radius: 5px;
  line-height: 0;
  transition: color 0.15s, background 0.15s;
}
.update-modal-close:hover { color: var(--fg-secondary); background: var(--surface-hover); }
.update-modal-icon { margin-bottom: 14px; line-height: 0; }
.update-modal-title {
  margin: 0 0 16px;
  font-size: 15px;
  font-weight: 600;
  color: var(--fg-primary);
}
.update-modal-sub {
  margin: -10px 0 16px;
  font-size: 12px;
  color: var(--fg-muted);
}
.update-version-row {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 14px;
}
.update-version-badge {
  font-size: 12px;
  font-weight: 600;
  padding: 3px 11px;
  border-radius: 20px;
  font-variant-numeric: tabular-nums;
  letter-spacing: 0.02em;
}
.update-version-badge.current {
  background: var(--surface-hover-strong);
  color: var(--fg-muted);
}
.update-version-badge.latest {
  background: var(--accent-muted);
  color: var(--accent);
  border: 1px solid var(--accent-border);
}
.update-arrow-svg { flex-shrink: 0; }
.update-release-link {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 12px;
  color: var(--fg-muted);
  background: none;
  border: none;
  cursor: pointer;
  padding: 0;
  margin-bottom: 22px;
  transition: color 0.15s;
}
.update-release-link:hover { color: var(--accent); }
.update-modal-actions { display: flex; gap: 8px; width: 100%; }
.update-btn-skip {
  flex: 1;
  padding: 8px;
  background: none;
  border: 1px solid var(--border);
  color: var(--fg-muted);
  border-radius: 7px;
  font-size: 13px;
  cursor: pointer;
  transition: background 0.15s, color 0.15s;
}
.update-btn-skip:hover { background: var(--surface-hover); color: var(--fg-secondary); }
.update-btn-install {
  flex: 2;
  padding: 8px;
  background: var(--accent);
  color: #fff;
  border: none;
  border-radius: 7px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.15s;
}
.update-btn-install:hover:not(:disabled) { background: var(--accent-hover); }
.update-btn-install:disabled { opacity: 0.45; cursor: default; }
.update-progress-track {
  width: 100%;
  height: 4px;
  background: var(--border);
  border-radius: 2px;
  overflow: hidden;
  margin-bottom: 8px;
}
.update-progress-fill {
  height: 100%;
  background: var(--accent);
  border-radius: 2px;
  transition: width 0.3s ease;
}
.update-progress-pct {
  font-size: 11px;
  color: var(--fg-muted);
  margin-bottom: 14px;
  font-variant-numeric: tabular-nums;
}
.update-modal-hint {
  font-size: 11px;
  color: var(--fg-muted);
  margin: 0;
  opacity: 0.65;
}
.update-modal-error-msg {
  font-size: 12px;
  color: var(--fg-muted);
  line-height: 1.55;
  margin: 0 0 20px;
}
.update-modal-enter-active { transition: opacity 0.2s ease, transform 0.2s ease; }
.update-modal-leave-active { transition: opacity 0.15s ease, transform 0.15s ease; }
.update-modal-enter-from, .update-modal-leave-to { opacity: 0; transform: scale(0.97) translateY(4px); }
.update-modal-enter-to, .update-modal-leave-from { opacity: 1; transform: scale(1) translateY(0); }


</style>