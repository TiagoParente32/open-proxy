<script setup>
import { onMounted, onUnmounted } from 'vue'
import { Splitpanes, Pane } from 'splitpanes'
import 'splitpanes/dist/splitpanes.css'

// Import our new components!
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
import ProgressOverlay from './components/ProgressOverlay.vue'
// Import just the logic needed for the top-level app overlay (WebSockets & Context Menu)
import { 
  initWebSocket, 
  closeContextMenu, 
  contextMenu, 
  formatUrl, 
  pinnedSources, 
  activeFilter, 
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
  openComposeNew,
  openVpnMode,
  showHighlightModal,
  deviceSetupType,
  showDeviceSetupModal,
  throttleProfile,
  disableCache,
} from './store.js'

onMounted(() => {
  initWebSocket()
  document.addEventListener('click', closeContextMenu)

  // Native app menu bridge — Python calls window.__op.xxx() via evaluate_js
  window.__op = {
    toggleRecording:  () => toggleRecording(),
    clearTraffic:     () => { requests.value.length = 0; wsMessages.value = {} },
    openComposeNew:   () => openComposeNew(),
    openVpnMode:      () => openVpnMode(),
    openBreakpoints:  () => { showBreakpointModal.value = true },
    openMapLocal:     () => { showMapModal.value = true },
    openMapRemote:    () => { showMapRemoteModal.value = true },
    openHighlight:    () => { showHighlightModal.value = true },
    openCertSetup:    (type) => { deviceSetupType.value = type; showDeviceSetupModal.value = true },
    setThrottle:      (profile) => { throttleProfile.value = profile },
    bustCache:        () => { disableCache.value = !disableCache.value },
  }
})

onUnmounted(() => {
  document.removeEventListener('click', closeContextMenu)
})

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
    const host = formatUrl(contextMenu.value.request.url).host;
    if (host && !pinnedSources.value.includes(host)) {
      pinnedSources.value.push(host);
      activeFilter.value = { type: 'pinned', value: host };
    }
  }
  closeContextMenu();
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
      status: realStatus, 
      headers: realHeaders, 
      body: realBody 
    };
    
    mapLocalRules.value.unshift(newRule);
    selectedRuleId.value = newRule.id;
  } else if (mapLocalRules.value.length > 0 && !selectedRuleId.value) {
    selectedRuleId.value = mapLocalRules.value[0].id;
  }
  showMapModal.value = true;
}

const openBreakpointModalFromContext = () => {
  closeContextMenu();
  if (contextMenu.value.request) {
    const req = contextMenu.value.request;
    
    // Pro-tip: Strip the query parameters (everything after '?') so the regex is cleaner
    // and escape the dots so 'google.com' doesn't accidentally match 'google-com'
    let defaultPattern = req.url.split('?')[0].replace(/\./g, '\\.');

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
  
  showBreakpointModal.value = true;
}
</script>

<template>
  <div class="app-wrapper">
    <AppToolbar />
    <FilterBar />
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

   <div v-if="contextMenu.show" class="context-menu" :style="{ top: contextMenu.y + 'px', left: contextMenu.x + 'px' }">
      
      <!-- Group: Request actions -->
      <div class="ctx-group-label">Request</div>
      <div class="context-menu-item" @click="handleRepeatFromContext">Repeat</div>
      <div class="context-menu-item" @click="handleEditAndRepeatFromContext">Edit &amp; Repeat</div>
      <div class="context-menu-item" @click="copyUrl">Copy URL</div>

      <div class="context-menu-divider"></div>

      <!-- Group: Mark -->
      <div class="ctx-group-label">Mark</div>
      <div class="context-menu-item" @click="toggleStar">
        {{ contextMenu.request?.starred ? '⭐ Unstar' : '⭐ Star' }}
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
  </div>
</template>

<style>
:root { background-color: #1a1a1b; color: #cccccc; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; --bg-main: #1e1e1f; --bg-sidebar: #222223; --bg-active: #2a2d2e; --border: #333333; }
body { margin: 0; padding: 0; }
.app-wrapper { display: flex; flex-direction: column; height: 100vh; overflow: hidden; }

/* --- SPLITPANES THEME OVERRIDES --- */
.splitpanes.custom-theme .splitpanes__pane { background-color: var(--bg-main); }
.splitpanes.custom-theme .splitpanes__splitter { background-color: var(--border); transition: background-color 0.2s; }
.splitpanes.custom-theme .splitpanes__splitter:hover { background-color: #555; }
.splitpanes.custom-theme.splitpanes--vertical > .splitpanes__splitter { width: 3px; border-left: 1px solid #111; }
.splitpanes.custom-theme.splitpanes--horizontal > .splitpanes__splitter { height: 3px; border-top: 1px solid #111; }

/* --- SHARED UTILITIES --- */
.action-btn { background: transparent; border: 1px solid #444; color: #ccc; padding: 4px 12px; border-radius: 4px; cursor: pointer; font-size: 12px; transition: all 0.2s; outline: none !important; }
.action-btn:focus { outline: none !important; box-shadow: none !important; }
.action-btn:hover { background: #333; color: white; }
.truncate { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.text-muted { color: #8b949e; }
.font-semibold { font-weight: 600; color: #e1e4e8; }
.text-green { color: #10b981 !important; }
.text-red { color: #ef4444 !important; }
.global-empty { display: flex; justify-content: center; align-items: center; height: 100%; color: #666; font-style: italic; font-size: 12px; }
.text-icon { font-size: 12px; color: #888; }

/* --- GLOBAL CONTEXT MENU --- */
.context-menu {
  position: fixed;
  background: #1e2023;
  border: 1px solid #2e3133;
  box-shadow: 0 8px 24px rgba(0,0,0,0.6);
  border-radius: 8px;
  padding: 4px;
  z-index: 9999;
  min-width: 170px;
}
.ctx-group-label {
  padding: 4px 10px 2px;
  font-size: 10px;
  font-weight: 700;
  color: #484d52;
  letter-spacing: 0.5px;
  text-transform: uppercase;
  user-select: none;
}
.context-menu-item {
  padding: 6px 10px;
  font-size: 12.5px;
  color: #c0c8d0;
  cursor: pointer;
  border-radius: 5px;
  text-align: left;
}
.context-menu-item:hover { background: #3b82f6; color: white; }
.context-menu-divider { height: 1px; background: #2a2d30; margin: 3px 4px; }

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


</style>