<script setup>
import {
    showDeviceSetupModal,
    deviceSetupType,
    proxyIP,
    proxyPort,
    adbDevices,
    adbDevicesLoading,
    adbDevicesError,
    setupProgress,
    revertProgress,
    listAdbDevices,
    setupAndroidDevice,
    revertAndroidDevice,
    iosSimulators,
    iosSimulatorsLoading,
    iosSimulatorsError,
    iosSetupProgress,
    iosRevertProgress,
    listIosSimulators,
    setupIosSimulator,
    revertIosSimulator,
    wgEnabled,
    wgPort,
    wgStatus,
    wgClientConf,
    wgError,
    toggleWgMode,
    requestWgConf,
} from '../store.js'
import { ref, watch, computed, nextTick } from 'vue'
import QRCode from 'qrcode'

const selectedSerial = ref(null)
const selectedUdid   = ref(null)
const activeTab  = ref('devices')
const activePane = ref('pick')
const copiedKey  = ref(null)

// ── VPN / WireGuard local state ───────────────────────────────────────────────
const qrCanvas   = ref(null)
const localPort  = ref(51820)
const wgCopied   = ref(false)

const wgStatusLabel = computed(() => ({
  disabled: { text: 'Off',       cls: 'pill-off'      },
  starting: { text: 'Starting…', cls: 'pill-starting' },
  ready:    { text: 'Active',    cls: 'pill-ready'    },
  error:    { text: 'Error',     cls: 'pill-error'    },
}[wgStatus.value] || { text: wgStatus.value, cls: '' }))

// True whenever the VPN Mode content panel is visible to the user
const isVpnVisible = computed(() =>
  showDeviceSetupModal.value && (
    deviceSetupType.value === 'vpn_mode' ||
    ((deviceSetupType.value === 'android_device' || deviceSetupType.value === 'ios_device') && activeTab.value === 'vpn')
  )
)

const onWgToggle = () => toggleWgMode(!wgEnabled.value, localPort.value)

const copyWgConf = async () => {
  if (!wgClientConf.value) return
  try {
    await navigator.clipboard.writeText(wgClientConf.value)
    wgCopied.value = true
    setTimeout(() => { wgCopied.value = false }, 2000)
  } catch {}
}

// Render QR only when VPN panel is visible, WG is ready, and we have a config
watch([isVpnVisible, wgClientConf, () => wgStatus.value], async () => {
  if (!isVpnVisible.value || wgStatus.value !== 'ready' || !wgClientConf.value) return
  await nextTick()
  if (qrCanvas.value) {
    try {
      await QRCode.toCanvas(qrCanvas.value, wgClientConf.value, {
        width: 200,
        color: { dark: '#000000', light: '#ffffff' },
        errorCorrectionLevel: 'M',
      })
    } catch (e) { console.error('[WG] QR failed:', e) }
  }
})

// Request fresh config whenever VPN panel becomes visible and WG is enabled
watch(isVpnVisible, (visible) => {
  if (visible && wgEnabled.value) requestWgConf()
})

// Keep port input in sync if backend reports a different port while panel is open
watch([isVpnVisible, wgPort], ([visible]) => {
  if (visible) localPort.value = wgPort.value
})
// ─────────────────────────────────────────────────────────────────────────────

// ── Raw code strings ──────────────────────────────────────────────────────────
const networkSecurityConfig = `<?xml version="1.0" encoding="utf-8"?>
<network-security-config>
    <debug-overrides>
        <trust-anchors>
            <!-- Trust user-added CAs (like mitmproxy) in debug builds -->
            <certificates src="user" />
            <certificates src="system" />
        </trust-anchors>
    </debug-overrides>

    <base-config cleartextTrafficPermitted="true">
        <trust-anchors>
            <certificates src="system" />
            <certificates src="user" />
        </trust-anchors>
    </base-config>
</network-security-config>`

const androidManifest = `<manifest ...>
    <application
        android:networkSecurityConfig="@xml/network_security_config"
        android:usesCleartextTraffic="true"
        ... >

        <!-- Rest of your application config -->

    </application>
</manifest>`

// ── XML syntax highlighter (no deps) ─────────────────────────────────────────
function highlightXml(code) {
    // Escape HTML first
    const escaped = code
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')

    return escaped
        // Comments  <!-- ... -->
        .replace(/(&lt;!--[\s\S]*?--&gt;)/g,
            '<span class="xt-comment">$1</span>')
        // Attribute values  ="..."
        .replace(/=(&quot;[^&]*&quot;|"[^"]*")/g,
            '=<span class="xt-attrval">$1</span>')
        // Attribute names  word=
        .replace(/\b([a-zA-Z_:][a-zA-Z0-9_:\-.]*)(?==)/g,
            '<span class="xt-attr">$1</span>')
        // Tag names  <tagName  or  </tagName  or  tagName>  or  tagName />
        .replace(/(&lt;\/?|(?<=\s))([a-zA-Z_][a-zA-Z0-9_\-.:]*)/g, (m, pre, name) => {
            if (!pre) return m
            return `${pre}<span class="xt-tag">${name}</span>`
        })
        // Punctuation  < > / ? =
        .replace(/(&lt;\/?|\/&gt;|&gt;|\?&gt;)/g,
            '<span class="xt-punct">$1</span>')
        // XML declaration  <?xml
        .replace(/(&lt;\?xml)/g,
            '<span class="xt-decl">$1</span>')
}

const nscHighlighted      = computed(() => highlightXml(networkSecurityConfig))
const manifestHighlighted = computed(() => highlightXml(androidManifest))

// ── Clipboard ─────────────────────────────────────────────────────────────────
const copyToClipboard = (text, key) => {
    navigator.clipboard.writeText(text).then(() => {
        copiedKey.value = key
        setTimeout(() => { copiedKey.value = null }, 2000)
    })
}

const copiedInfo = ref(null)
const copyInfo = (value, key) => {
    navigator.clipboard.writeText(String(value)).then(() => {
        copiedInfo.value = key
        setTimeout(() => { copiedInfo.value = null }, 1500)
    })
}

// ── Modal lifecycle ───────────────────────────────────────────────────────────
// Re-initialise modal state whenever it opens or the device type changes while open
const initModal = ([open]) => {
    if (!open) return
    selectedSerial.value = null
    selectedUdid.value   = null
    activePane.value = 'pick'
    localPort.value  = wgPort.value
    if (deviceSetupType.value === 'vpn_mode') {
        activeTab.value = 'vpn'
    } else if (deviceSetupType.value === 'android_device' || deviceSetupType.value === 'ios_device') {
        activeTab.value = 'manual'
    } else if (deviceSetupType.value === 'browser') {
        activeTab.value = 'chrome'
    } else {
        activeTab.value = 'devices'
        if (deviceSetupType.value === 'android_emulator') listAdbDevices()
        if (deviceSetupType.value === 'ios_simulator')    listIosSimulators()
    }
}
watch([showDeviceSetupModal, deviceSetupType], initModal)

// ── Android device actions ────────────────────────────────────────────────────
const selectAndSetup = (device) => {
    selectedSerial.value = device.serial
    activePane.value = 'progress'
    setupProgress.value.show  = true
    setupProgress.value.error = null
    setupProgress.value.steps.forEach(s => s.status = 'pending')
    setupAndroidDevice(device.serial, device.type)
}

const selectAndRevert = (device) => {
    selectedSerial.value = device.serial
    activePane.value = 'revert'
    revertProgress.value.show  = true
    revertProgress.value.error = null
    revertProgress.value.steps.forEach(s => s.status = 'pending')
    revertAndroidDevice(device.serial)
}

const selectedDeviceModel = () => {
    const d = adbDevices.value.find(d => d.serial === selectedSerial.value)
    return d ? d.model : selectedSerial.value
}

// ── iOS Simulator actions ─────────────────────────────────────────────────────
const selectAndSetupIos = (sim) => {
    selectedUdid.value = sim.udid
    activePane.value = 'progress'
    iosSetupProgress.value.show  = true
    iosSetupProgress.value.error = null
    iosSetupProgress.value.steps.forEach(s => s.status = 'pending')
    setupIosSimulator(sim.udid)
}

const selectAndRevertIos = (sim) => {
    selectedUdid.value = sim.udid
    activePane.value = 'revert'
    iosRevertProgress.value.show  = true
    iosRevertProgress.value.error = null
    iosRevertProgress.value.steps.forEach(s => s.status = 'pending')
    revertIosSimulator(sim.udid)
}

const selectedSimulatorName = () => {
    const s = iosSimulators.value.find(s => s.udid === selectedUdid.value)
    return s ? s.name : selectedUdid.value
}

// ── Shared helpers ────────────────────────────────────────────────────────────
const currentSetupProgress = computed(() =>
    deviceSetupType.value === 'ios_simulator' ? iosSetupProgress.value : setupProgress.value
)
const currentRevertProgress = computed(() =>
    deviceSetupType.value === 'ios_simulator' ? iosRevertProgress.value : revertProgress.value
)
const currentProgressLabel = computed(() => {
    if (deviceSetupType.value === 'ios_simulator') {
        const name = selectedSimulatorName()
        const short = selectedUdid.value ? selectedUdid.value.slice(0, 8) + '…' : ''
        return `${name} · ${short}`
    }
    return `${selectedDeviceModel()} · ${selectedSerial.value}`
})

const allStepsDone = (steps) => steps.every(s => s.status === 'success' || s.status === 'skip')
const hasError     = (steps) => steps.some(s => s.status === 'error')

const modalTitle = () => {
    if (deviceSetupType.value === 'android_emulator') return 'Android Setup'
    if (deviceSetupType.value === 'android_device')   return 'Android Device Setup'
    if (deviceSetupType.value === 'ios_simulator')    return 'iOS Simulator Setup'
    if (deviceSetupType.value === 'ios_device')       return 'iOS Physical Device Setup'
    if (deviceSetupType.value === 'vpn_mode')         return 'VPN Mode'
    if (deviceSetupType.value === 'browser')          return 'Browser Setup'
    return 'Device Setup'
}
</script>

<template>
  <div v-if="showDeviceSetupModal" class="modal-overlay" @mousedown.self="showDeviceSetupModal = false">
    <div class="modal-content">

      <!-- ── Header ──────────────────────────────────── -->
      <div class="modal-header">
        <div class="header-left">
          <!-- VPN icon for vpn_mode, Android robot icon otherwise -->
          <svg v-if="deviceSetupType === 'vpn_mode'" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--setup-success)" stroke-width="1.8">
            <rect x="3" y="11" width="18" height="11" rx="2"/>
            <path d="M7 11V7a5 5 0 0 1 10 0v4"/>
          </svg>
          <svg v-else width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" stroke-width="1.8">
            <rect x="5" y="11" width="14" height="10" rx="2"/>
            <path d="M9 11V7a3 3 0 0 1 6 0v4"/>
            <line x1="9" y1="15" x2="9" y2="17"/>
            <line x1="15" y1="15" x2="15" y2="17"/>
          </svg>
          <strong>{{ modalTitle() }}</strong>
          <span v-if="deviceSetupType === 'vpn_mode'" class="wg-status-pill" :class="wgStatusLabel.cls">{{ wgStatusLabel.text }}</span>
        </div>
        <button class="close-btn" @click="showDeviceSetupModal = false">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
            <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
          </svg>
        </button>
      </div>

      <!-- ── Tabs (android_emulator + ios_simulator) ───── -->
      <div v-if="deviceSetupType === 'android_emulator' || deviceSetupType === 'ios_simulator'" class="tab-bar">
        <button class="tab-btn" :class="{ active: activeTab === 'devices' }"
                @click="activeTab = 'devices'">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <rect x="5" y="2" width="14" height="20" rx="2"/>
            <circle cx="12" cy="17" r="1" fill="currentColor"/>
          </svg>
          Devices
        </button>
        <button v-if="deviceSetupType === 'android_emulator'" class="tab-btn" :class="{ active: activeTab === 'config' }"
                @click="activeTab = 'config'">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <polyline points="16 18 22 12 16 6"/>
            <polyline points="8 6 2 12 8 18"/>
          </svg>
          App Config
        </button>
        <button class="tab-btn" :class="{ active: activeTab === 'manual' }"
                @click="activeTab = 'manual'">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <line x1="8" y1="6" x2="21" y2="6"/><line x1="8" y1="12" x2="21" y2="12"/><line x1="8" y1="18" x2="21" y2="18"/>
            <line x1="3" y1="6" x2="3.01" y2="6"/><line x1="3" y1="12" x2="3.01" y2="12"/><line x1="3" y1="18" x2="3.01" y2="18"/>
          </svg>
          Manual
        </button>
      </div>

      <!-- ── Tabs (android_device + ios_device): Manual Proxy | VPN Mode ──── -->
      <div v-if="deviceSetupType === 'android_device' || deviceSetupType === 'ios_device'" class="tab-bar">
        <button class="tab-btn" :class="{ active: activeTab === 'manual' }"
                @click="activeTab = 'manual'">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <line x1="8" y1="6" x2="21" y2="6"/><line x1="8" y1="12" x2="21" y2="12"/><line x1="8" y1="18" x2="21" y2="18"/>
            <line x1="3" y1="6" x2="3.01" y2="6"/><line x1="3" y1="12" x2="3.01" y2="12"/><line x1="3" y1="18" x2="3.01" y2="18"/>
          </svg>
          Manual Proxy
        </button>
        <button class="tab-btn" :class="{ active: activeTab === 'vpn' }"
                @click="activeTab = 'vpn'">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <rect x="3" y="11" width="18" height="11" rx="2"/>
            <path d="M7 11V7a5 5 0 0 1 10 0v4"/>
          </svg>
          VPN Mode
          <span v-if="wgEnabled && wgStatus === 'ready'" class="tab-vpn-dot" />
        </button>
      </div>

      <!-- ══════════════════════════════════════════════
           DEVICES TAB  (emulator / simulator)
      ══════════════════════════════════════════════ -->
      <div v-if="(deviceSetupType === 'android_emulator' || deviceSetupType === 'ios_simulator') && activeTab === 'devices'"
           class="modal-body">

        <!-- Pick pane -->
        <template v-if="activePane === 'pick' && deviceSetupType === 'android_emulator'">

          <div class="picker-top">
            <p class="hint">Select a connected device to install the certificate and configure the proxy.</p>
            <button class="refresh-btn" :disabled="adbDevicesLoading" @click="listAdbDevices()" title="Refresh devices">
              <!-- Refresh / rotate-cw icon -->
              <svg :class="{ spinning: adbDevicesLoading }"
                   width="13" height="13" viewBox="0 0 24 24"
                   fill="none" stroke="currentColor" stroke-width="2.2"
                   stroke-linecap="round" stroke-linejoin="round">
                <polyline points="23 4 23 10 17 10"/>
                <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/>
              </svg>
              <span>{{ adbDevicesLoading ? 'Scanning…' : 'Refresh' }}</span>
            </button>
          </div>

          <div v-if="adbDevicesError" class="alert error">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="flex-shrink:0;margin-top:1px">
              <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>
            </svg>
            {{ adbDevicesError }}
          </div>

          <!-- Skeletons -->
          <div v-if="adbDevicesLoading && adbDevices.length === 0" class="device-list">
            <div class="device-row" v-for="n in 2" :key="n" style="pointer-events:none">
              <div class="sk" style="width:32px;height:32px;border-radius:7px;flex-shrink:0"/>
              <div style="flex:1;display:flex;flex-direction:column;gap:6px">
                <div class="sk" style="width:140px;height:11px;border-radius:3px"/>
                <div class="sk" style="width:90px;height:9px;border-radius:3px"/>
              </div>
            </div>
          </div>

          <!-- Empty state -->
          <div v-else-if="!adbDevicesLoading && adbDevices.length === 0 && !adbDevicesError"
               class="empty-state">
            <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="var(--border)" stroke-width="1.5">
              <path d="M9 3H5a2 2 0 0 0-2 2v4m6-6h10a2 2 0 0 1 2 2v4M9 3v18m0 0h10a2 2 0 0 0 2-2V9M9 21H5a2 2 0 0 1-2-2V9m0 0h18"/>
            </svg>
            <p class="empty-title">No devices detected</p>
            <p class="empty-sub">Start your emulator, then click Refresh.</p>
            <p class="empty-sub">Requires <code>adb</code> and <code>openssl</code> in PATH.</p>
          </div>

          <!-- Device rows -->
          <div v-else class="device-list">
            <div v-for="device in adbDevices" :key="device.serial" class="device-row">
              <div class="device-thumb">
                <svg v-if="device.type === 'emulator'" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8">
                  <rect x="2" y="3" width="20" height="14" rx="2"/>
                  <polyline points="8 21 12 17 16 21"/>
                  <line x1="12" y1="17" x2="12" y2="21"/>
                </svg>
                <svg v-else width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8">
                  <rect x="5" y="2" width="14" height="20" rx="2"/>
                  <circle cx="12" cy="17" r="1" fill="currentColor"/>
                </svg>
              </div>
              <div class="device-info">
                <span class="device-model">{{ device.model }}</span>
                <span class="device-serial">{{ device.serial }}</span>
              </div>
              <span class="type-badge" :class="device.type">
                {{ device.type === 'emulator' ? 'Emulator' : 'Device' }}
              </span>
              <div class="row-actions">
                <button class="pill install" @click="selectAndSetup(device)">
                  <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round">
                    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
                    <polyline points="7 10 12 15 17 10"/>
                    <line x1="12" y1="15" x2="12" y2="3"/>
                  </svg>
                  Install
                </button>
                <button class="pill revert" @click="selectAndRevert(device)">
                  <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round">
                    <polyline points="1 4 1 10 7 10"/>
                    <path d="M3.51 15a9 9 0 1 0 .49-4.95"/>
                  </svg>
                  Revert
                </button>
              </div>
            </div>
          </div>

          <div class="prereq-note">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="var(--method-put)" stroke-width="2" style="flex-shrink:0;margin-top:1px">
              <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>
              <line x1="12" y1="9" x2="12" y2="13"/>
              <line x1="12" y1="17" x2="12.01" y2="17"/>
            </svg>
            <span>Emulators must be <strong>Google APIs</strong> builds — Google Play builds block root access.</span>
          </div>
        </template>

        <!-- iOS Simulator picker pane -->
        <template v-if="activePane === 'pick' && deviceSetupType === 'ios_simulator'">

          <div class="picker-top">
            <p class="hint">Select a simulator to install the certificate. The simulator must be <strong>Booted</strong> to install.</p>
            <button class="refresh-btn" :disabled="iosSimulatorsLoading" @click="listIosSimulators()" title="Refresh simulators">
              <svg :class="{ spinning: iosSimulatorsLoading }"
                   width="13" height="13" viewBox="0 0 24 24"
                   fill="none" stroke="currentColor" stroke-width="2.2"
                   stroke-linecap="round" stroke-linejoin="round">
                <polyline points="23 4 23 10 17 10"/>
                <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/>
              </svg>
              <span>{{ iosSimulatorsLoading ? 'Scanning…' : 'Refresh' }}</span>
            </button>
          </div>

          <div v-if="iosSimulatorsError" class="alert error">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="flex-shrink:0;margin-top:1px">
              <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>
            </svg>
            {{ iosSimulatorsError }}
          </div>

          <!-- Skeletons -->
          <div v-if="iosSimulatorsLoading && iosSimulators.length === 0" class="device-list">
            <div class="device-row" v-for="n in 2" :key="n" style="pointer-events:none">
              <div class="sk" style="width:32px;height:32px;border-radius:7px;flex-shrink:0"/>
              <div style="flex:1;display:flex;flex-direction:column;gap:6px">
                <div class="sk" style="width:140px;height:11px;border-radius:3px"/>
                <div class="sk" style="width:90px;height:9px;border-radius:3px"/>
              </div>
            </div>
          </div>

          <!-- Empty state -->
          <div v-else-if="!iosSimulatorsLoading && iosSimulators.length === 0 && !iosSimulatorsError"
               class="empty-state">
            <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="var(--border)" stroke-width="1.5">
              <rect x="5" y="2" width="14" height="20" rx="2"/>
              <circle cx="12" cy="17" r="1" fill="var(--border)"/>
            </svg>
            <p class="empty-title">No iOS Simulators found</p>
            <p class="empty-sub">Open Xcode → Window → Devices and Simulators to create one.</p>
          </div>

          <!-- Simulator rows -->
          <div v-else class="device-list">
            <div v-for="sim in iosSimulators" :key="sim.udid" class="device-row">
              <div class="device-thumb">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8">
                  <rect x="5" y="2" width="14" height="20" rx="2"/>
                  <circle cx="12" cy="17" r="1" fill="currentColor"/>
                </svg>
              </div>
              <div class="device-info">
                <span class="device-model">{{ sim.name }}</span>
                <span class="device-serial">{{ sim.runtime }}</span>
              </div>
              <span class="type-badge" :class="sim.state === 'Booted' ? 'emulator' : 'offline'">
                {{ sim.state }}
              </span>
              <div class="row-actions">
                <button class="pill install" :disabled="sim.state !== 'Booted'"
                        :title="sim.state !== 'Booted' ? 'Boot the simulator first' : ''"
                        @click="selectAndSetupIos(sim)">
                  <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round">
                    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
                    <polyline points="7 10 12 15 17 10"/>
                    <line x1="12" y1="15" x2="12" y2="3"/>
                  </svg>
                  Install
                </button>
                <button class="pill revert" @click="selectAndRevertIos(sim)">
                  <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round">
                    <polyline points="1 4 1 10 7 10"/>
                    <path d="M3.51 15a9 9 0 1 0 .49-4.95"/>
                  </svg>
                  Revert
                </button>
              </div>
            </div>
          </div>
        </template>

        <!-- Install progress pane -->
        <template v-if="activePane === 'progress'">
          <div class="progress-header">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" stroke-width="1.8" style="flex-shrink:0">
              <rect x="2" y="3" width="20" height="14" rx="2"/>
              <polyline points="8 21 12 17 16 21"/>
              <line x1="12" y1="17" x2="12" y2="21"/>
            </svg>
            <div>
              <div class="progress-title">
                {{ allStepsDone(currentSetupProgress.steps) ? 'Setup Complete' : hasError(currentSetupProgress.steps) ? 'Setup Failed' : 'Installing…' }}
              </div>
              <div class="progress-sub">{{ currentProgressLabel }}</div>
            </div>
          </div>

          <div class="progress-steps">
            <div v-for="step in currentSetupProgress.steps" :key="step.id"
                 class="progress-step" :class="step.status">
              <div class="step-icon">
                <svg v-if="step.status === 'loading'" class="spinning" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" stroke-width="2.5" stroke-linecap="round"><path d="M21 12a9 9 0 1 1-6.219-8.56"/></svg>
                <svg v-else-if="step.status === 'success'" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--setup-success)" stroke-width="2.5" stroke-linecap="round"><polyline points="20 6 9 17 4 12"/></svg>
                <svg v-else-if="step.status === 'error'" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--setup-error)" stroke-width="2.5" stroke-linecap="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
                <svg v-else-if="step.status === 'skip'" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--border)" stroke-width="2" stroke-linecap="round"><polyline points="13 17 18 12 13 7"/><polyline points="6 17 11 12 6 7"/></svg>
                <svg v-else width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--border)" stroke-width="2"><circle cx="12" cy="12" r="4"/></svg>
              </div>
              <span class="step-label">{{ step.label }}</span>
            </div>
          </div>

          <div v-if="currentSetupProgress.error" class="alert error" style="margin-top:14px">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="flex-shrink:0;margin-top:1px"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
            {{ currentSetupProgress.error }}
          </div>
          <div v-if="allStepsDone(currentSetupProgress.steps)" class="alert success" style="margin-top:14px">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" style="flex-shrink:0;margin-top:1px"><polyline points="20 6 9 17 4 12"/></svg>
            <span v-if="deviceSetupType === 'ios_simulator'">
              Certificate installed. Make sure macOS System Settings → Network → Proxies is set to
              <strong>{{ proxyIP }}:{{ proxyPort }}</strong> to route traffic.
            </span>
            <span v-else>Certificate installed and proxy configured. Traffic from this device will now be intercepted.</span>
          </div>
        </template>

        <!-- Revert progress pane -->
        <template v-if="activePane === 'revert'">
          <div class="progress-header">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="var(--setup-error)" stroke-width="1.8" style="flex-shrink:0">
              <polyline points="1 4 1 10 7 10"/>
              <path d="M3.51 15a9 9 0 1 0 .49-4.95"/>
            </svg>
            <div>
              <div class="progress-title">
                {{ allStepsDone(currentRevertProgress.steps) ? 'Revert Complete' : hasError(currentRevertProgress.steps) ? 'Revert Failed' : 'Reverting…' }}
              </div>
              <div class="progress-sub">{{ currentProgressLabel }}</div>
            </div>
          </div>

          <div class="progress-steps">
            <div v-for="step in currentRevertProgress.steps" :key="step.id"
                 class="progress-step" :class="step.status">
              <div class="step-icon">
                <svg v-if="step.status === 'loading'" class="spinning" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" stroke-width="2.5" stroke-linecap="round"><path d="M21 12a9 9 0 1 1-6.219-8.56"/></svg>
                <svg v-else-if="step.status === 'success'" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--setup-success)" stroke-width="2.5" stroke-linecap="round"><polyline points="20 6 9 17 4 12"/></svg>
                <svg v-else-if="step.status === 'error'" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--setup-error)" stroke-width="2.5" stroke-linecap="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
                <svg v-else width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--border)" stroke-width="2"><circle cx="12" cy="12" r="4"/></svg>
              </div>
              <span class="step-label">{{ step.label }}</span>
            </div>
          </div>

          <div v-if="currentRevertProgress.error" class="alert error" style="margin-top:14px">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="flex-shrink:0;margin-top:1px"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
            {{ currentRevertProgress.error }}
          </div>
          <div v-if="allStepsDone(currentRevertProgress.steps)" class="alert success" style="margin-top:14px">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" style="flex-shrink:0;margin-top:1px"><polyline points="20 6 9 17 4 12"/></svg>
            <span v-if="deviceSetupType === 'ios_simulator'">Certificate removed from simulator trust store.</span>
            <span v-else>Proxy settings and certificate removed from device.</span>
          </div>
        </template>

      </div>

      <!-- ══════════════════════════════════════════════
           MANUAL PROXY TAB  (android_device / ios_device)
      ══════════════════════════════════════════════ -->
      <div v-if="(deviceSetupType === 'android_device' || deviceSetupType === 'ios_device') && activeTab === 'manual'"
           class="modal-body">

        <div v-if="deviceSetupType === 'android_device'">
          <ol class="instruction-list">
            <li>Ensure your phone and computer are on the <strong>same Wi-Fi network</strong>.</li>
            <li>Go to <strong>Settings › Wi-Fi</strong>, tap the gear next to your network, set <strong>Proxy</strong> to <strong>Manual</strong>.</li>
            <li>
              Enter your proxy details:
              <div class="info-box">
                <div class="info-row"><span class="info-label">Hostname</span><code class="info-val copyable" :class="{ copied: copiedInfo === 'and_dev_ip' }" @click="copyInfo(proxyIP, 'and_dev_ip')">{{ proxyIP }}</code></div>
                <div class="info-row"><span class="info-label">Port</span><code class="info-val copyable" :class="{ copied: copiedInfo === 'and_dev_port' }" @click="copyInfo(proxyPort, 'and_dev_port')">{{ proxyPort }}</code></div>
              </div>
            </li>
            <li>Open the browser on your phone and navigate to <code class="ic">http://mitm.it</code> — tap the <strong>Android</strong> button to download the certificate.</li>
            <li>Go to <strong>Settings › Security › Encryption &amp; Credentials › Install a certificate › CA Certificate</strong> and install the downloaded file.</li>
          </ol>
          <div class="alert warning" style="margin-top:14px">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="flex-shrink:0;margin-top:1px"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
            The <code class="ic">mitm.it</code> page only loads when the proxy is running and your phone is routing through it. Make sure OpenProxy is recording before visiting it.
          </div>
        </div>

        <div v-if="deviceSetupType === 'ios_device'">
          <ol class="instruction-list">
            <li>Ensure your iPhone and computer are on the <strong>same Wi-Fi network</strong>.</li>
            <li>Go to <strong>Settings › Wi-Fi › (i) › Configure Proxy › Manual</strong>.</li>
            <li>
              Enter your proxy details:
              <div class="info-box">
                <div class="info-row"><span class="info-label">Server</span><code class="info-val copyable" :class="{ copied: copiedInfo === 'ios_dev_ip' }" @click="copyInfo(proxyIP, 'ios_dev_ip')">{{ proxyIP }}</code></div>
                <div class="info-row"><span class="info-label">Port</span><code class="info-val copyable" :class="{ copied: copiedInfo === 'ios_dev_port' }" @click="copyInfo(proxyPort, 'ios_dev_port')">{{ proxyPort }}</code></div>
              </div>
            </li>
            <li>Open Safari on your iPhone and go to <code class="ic">http://mitm.it</code> — tap the <strong>iOS</strong> button to download the profile.</li>
            <li>Go to <strong>Settings › General › VPN &amp; Device Management</strong> and install the downloaded profile.</li>
            <li><strong>Crucial:</strong> <strong>Settings › General › About › Certificate Trust Settings</strong> — toggle mitmproxy <strong>ON</strong>.</li>
          </ol>
          <div class="alert warning" style="margin-top:14px">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="flex-shrink:0;margin-top:1px"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
            Skipping Step 6 causes SSL errors on all HTTPS traffic — the cert must be explicitly trusted after installing.
          </div>
        </div>

      </div>

      <!-- ══════════════════════════════════════════════
           VPN MODE TAB  (physical devices + toolbar shortcut)
      ══════════════════════════════════════════════ -->
      <div v-if="isVpnVisible" class="modal-body wg-body">

        <!-- Toggle row -->
        <div class="wg-toggle-row">
          <div class="wg-toggle-info">
            <span class="wg-toggle-title">WireGuard VPN Mode</span>
            <span class="wg-toggle-sub">Intercept traffic without manual proxy setup</span>
          </div>
          <button class="wg-toggle-btn" :class="{ active: wgEnabled, loading: wgStatus === 'starting' }"
          :disabled="wgStatus === 'starting'" @click="onWgToggle">
            <span class="wg-toggle-track">
              <span class="wg-toggle-thumb" />
            </span>
            <span class="wg-toggle-label">{{ wgEnabled ? 'On' : 'Off' }}</span>
          </button>
        </div>

        <!-- Port input (only when disabled) -->
        <div v-if="!wgEnabled" class="wg-port-row">
          <label class="wg-port-label">WireGuard Port</label>
          <input class="wg-port-input" type="number" v-model.number="localPort"
                 min="1024" max="65535" placeholder="51820"
                 @change="wgPort.value = localPort" />
        </div>

        <!-- Error -->
        <div v-if="wgError" class="alert error">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="flex-shrink:0;margin-top:1px">
            <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>
          </svg>
          {{ wgError }}
        </div>

        <!-- Starting spinner -->
        <div v-if="wgStatus === 'starting'" class="wg-starting">
          <svg class="spinning" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" stroke-width="2.5" stroke-linecap="round">
            <path d="M21 12a9 9 0 1 1-6.219-8.56"/>
          </svg>
          <span>Starting WireGuard…</span>
        </div>

        <!-- QR + config (ready state) -->
        <template v-if="wgEnabled && wgStatus === 'ready' && wgClientConf">
          <div class="wg-qr-section">
            <canvas ref="qrCanvas" class="wg-qr-canvas" />
            <div class="wg-qr-hint">Scan with the WireGuard app to connect</div>
          </div>

          <div class="wg-conf-header">
            <span>wireguard.conf</span>
            <button class="copy-btn" :class="{ copied: wgCopied }" @click="copyWgConf">
              <svg v-if="!wgCopied" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
                <rect x="9" y="9" width="13" height="13" rx="2"/>
                <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>
              </svg>
              <svg v-else width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="var(--setup-success)" stroke-width="2.5" stroke-linecap="round">
                <polyline points="20 6 9 17 4 12"/>
              </svg>
              {{ wgCopied ? 'Copied!' : 'Copy' }}
            </button>
          </div>
          <pre class="wg-conf-pre">{{ wgClientConf }}</pre>

          <ol class="instruction-list" style="margin-top:16px">
            <li>Install the <strong>WireGuard</strong> app on your device.</li>
            <li>Tap <strong>+</strong> → <strong>Create from QR code</strong> and scan above, <em>or</em> import the config file.</li>
            <li>Activate the tunnel — all traffic will route through this proxy.</li>
          </ol>
        </template>

        <!-- Info box -->
        <div class="alert info" style="margin-top:16px">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="flex-shrink:0;margin-top:1px">
            <circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/>
          </svg>
          <span>VPN Mode intercepts <strong>all</strong> device traffic — no manual proxy configuration needed per app.</span>
        </div>

      </div>

      <!-- ══════════════════════════════════════════════
           APP CONFIG TAB
      ══════════════════════════════════════════════ -->
      <div v-if="deviceSetupType === 'android_emulator' && activeTab === 'config'"
           class="modal-body config-body">

        <p class="config-intro">
          By default Android apps only trust <strong>system</strong> CA certificates and will reject
          your proxy's certificate with an SSL error. Add these two files to your project to allow
          interception in debug builds — release builds are unaffected.
        </p>

        <!-- Block 1 -->
        <div class="code-card">
          <div class="code-card-header">
            <div class="step-num">1</div>
            <div class="code-card-meta">
              <div class="code-card-title">Create <code class="filepath">res/xml/network_security_config.xml</code></div>
              <div class="code-card-sub">Instructs the app to trust user-installed CAs in debug builds.</div>
            </div>
            <button class="copy-btn" :class="{ copied: copiedKey === 'nsc' }"
                    @click="copyToClipboard(networkSecurityConfig, 'nsc')">
              <svg v-if="copiedKey !== 'nsc'" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
                <rect x="9" y="9" width="13" height="13" rx="2"/>
                <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>
              </svg>
              <svg v-else width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="var(--setup-success)" stroke-width="2.5" stroke-linecap="round">
                <polyline points="20 6 9 17 4 12"/>
              </svg>
              {{ copiedKey === 'nsc' ? 'Copied!' : 'Copy' }}
            </button>
          </div>
          <div class="code-scroll">
            <pre class="code-pre"><code v-html="nscHighlighted"/></pre>
          </div>
        </div>

        <!-- Block 2 -->
        <div class="code-card">
          <div class="code-card-header">
            <div class="step-num">2</div>
            <div class="code-card-meta">
              <div class="code-card-title">Update <code class="filepath">AndroidManifest.xml</code></div>
              <div class="code-card-sub">Reference the config file and allow cleartext HTTP traffic.</div>
            </div>
            <button class="copy-btn" :class="{ copied: copiedKey === 'manifest' }"
                    @click="copyToClipboard(androidManifest, 'manifest')">
              <svg v-if="copiedKey !== 'manifest'" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
                <rect x="9" y="9" width="13" height="13" rx="2"/>
                <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>
              </svg>
              <svg v-else width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="var(--setup-success)" stroke-width="2.5" stroke-linecap="round">
                <polyline points="20 6 9 17 4 12"/>
              </svg>
              {{ copiedKey === 'manifest' ? 'Copied!' : 'Copy' }}
            </button>
          </div>
          <div class="code-scroll">
            <pre class="code-pre"><code v-html="manifestHighlighted"/></pre>
          </div>
        </div>

        <!-- Notes -->
        <div class="note-card">
          <div class="note-label">React Native / Flutter / Expo</div>
          <p>Place <code class="ic">network_security_config.xml</code> in <code class="ic">android/app/src/main/res/xml/</code> and edit <code class="ic">android/app/src/main/AndroidManifest.xml</code>.</p>
        </div>
        <div class="note-card" style="margin-top:8px">
          <div class="note-label">API 24+ note</div>
          <p><code class="ic">android:usesCleartextTraffic</code> only affects plain HTTP. The <code class="ic">&lt;network-security-config&gt;</code> handles HTTPS certificate trust. Both attributes are needed for full interception.</p>
        </div>

      </div>

      <!-- ══════════════════════════════════════════════
           MANUAL TAB  (android_emulator + ios_simulator)
      ══════════════════════════════════════════════ -->
      <div v-if="(deviceSetupType === 'android_emulator' || deviceSetupType === 'ios_simulator') && activeTab === 'manual'"
           class="modal-body">

        <!-- iOS Simulator manual instructions -->
        <template v-if="deviceSetupType === 'ios_simulator'">
          <p class="hint" style="margin-bottom:14px">iOS Simulators share the Mac's network connection. Follow these steps to set up manually.</p>

          <ol class="instruction-list">
            <li>
              Go to <strong>System Settings → Network → (your interface) → Details → Proxies</strong> and enable <strong>Web Proxy (HTTP)</strong> and <strong>Secure Web Proxy (HTTPS)</strong>:
              <div class="info-box">
                <div class="info-row"><span class="info-label">Server</span><code class="info-val copyable" :class="{ copied: copiedInfo === 'sim_ip' }" @click="copyInfo(proxyIP, 'sim_ip')">{{ proxyIP }}</code></div>
                <div class="info-row"><span class="info-label">Port</span><code class="info-val copyable" :class="{ copied: copiedInfo === 'sim_port' }" @click="copyInfo(proxyPort, 'sim_port')">{{ proxyPort }}</code></div>
              </div>
            </li>
            <li>Go to <strong>Settings → General → VPN &amp; Device Management</strong> and install the downloaded profile.</li>
            <li>
              <strong>Crucial:</strong> Go to <strong>Settings → General → About → Certificate Trust Settings</strong> and toggle the mitmproxy certificate <strong>ON</strong>.
            </li>
          </ol>

          <div class="alert warning" style="margin-top:14px">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="flex-shrink:0;margin-top:1px"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
            Skipping Step 5 causes SSL errors on all HTTPS traffic — the cert must be explicitly trusted.
          </div>
        </template>

        <!-- Android Emulator manual instructions -->
        <template v-if="deviceSetupType === 'android_emulator'">
          <p class="hint" style="margin-bottom:14px">Use these steps if the automated setup doesn't work, or if you prefer to configure things manually.</p>

          <ol class="instruction-list">
            <li>
              In the emulator, go to <strong>Settings → Network &amp; Internet → Internet</strong>, long-press your Wi-Fi network and choose <strong>Modify network → Advanced options</strong>. Set <strong>Proxy</strong> to <strong>Manual</strong>:
              <div class="info-box">
                <div class="info-row"><span class="info-label">Hostname</span><code class="info-val copyable" :class="{ copied: copiedInfo === 'emu_ip' }" @click="copyInfo('10.0.2.2', 'emu_ip')">10.0.2.2</code></div>
                <div class="info-row"><span class="info-label">Port</span><code class="info-val copyable" :class="{ copied: copiedInfo === 'emu_port' }" @click="copyInfo(proxyPort, 'emu_port')">{{ proxyPort }}</code></div>
              </div>
              <em style="font-size:11px;color:var(--fg-placeholder);">The special address <code class="ic">10.0.2.2</code> routes from the emulator to your Mac's localhost.</em>
            </li>
            <li>Open the emulator browser and go to <code class="ic">http://mitm.it</code>, then tap the Android certificate download.</li>
            <li>Go to <strong>Settings → Security → Encryption &amp; Credentials → Install a certificate → CA Certificate</strong> and install the downloaded file.</li>
            <li>For app-level interception (HTTPS in your own apps), also check the <strong>App Config</strong> tab.</li>
          </ol>

          <div class="alert warning" style="margin-top:14px">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="flex-shrink:0;margin-top:1px"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
            Manual certificate install only covers <strong>user-installed CA trust</strong>. Most apps built for API 24+ ignore user CAs — you still need the App Config changes.
          </div>
        </template>

      </div>

      <!-- ══════════════════════════════════════════════
           BROWSER TABS
      ══════════════════════════════════════════════ -->
      <div v-if="deviceSetupType === 'browser'" class="tab-bar">
        <button class="tab-btn" :class="{ active: activeTab === 'chrome' }" @click="activeTab = 'chrome'">Chrome</button>
        <button class="tab-btn" :class="{ active: activeTab === 'firefox' }" @click="activeTab = 'firefox'">Firefox</button>
        <button class="tab-btn" :class="{ active: activeTab === 'safari' }" @click="activeTab = 'safari'">Safari</button>
        <button class="tab-btn" :class="{ active: activeTab === 'curl' }" @click="activeTab = 'curl'">curl / CLI</button>
      </div>

      <div v-if="deviceSetupType === 'browser'" class="modal-body">

        <!-- Chrome -->
        <template v-if="activeTab === 'chrome'">
          <p class="hint" style="margin-bottom:14px">Chrome uses the system proxy settings. Configure your OS proxy to point to OpenProxy, then Chrome will use it automatically.</p>
          <ol class="instruction-list">
            <li>
              Set your <strong>system proxy</strong> (macOS: System Settings → Network → Details → Proxies; Windows: Settings → Network → Proxy) to:
              <div class="info-box">
                <div class="info-row"><span class="info-label">Server</span><code class="info-val copyable" :class="{ copied: copiedInfo === 'br_ip' }" @click="copyInfo(proxyIP, 'br_ip')">{{ proxyIP }}</code></div>
                <div class="info-row"><span class="info-label">Port</span><code class="info-val copyable" :class="{ copied: copiedInfo === 'br_port' }" @click="copyInfo(proxyPort, 'br_port')">{{ proxyPort }}</code></div>
              </div>
            </li>
            <li>Open Chrome and navigate to <code class="ic">http://mitm.it</code>.</li>
            <li>Download and install the certificate for your OS.</li>
            <li>On <strong>macOS</strong>: open Keychain Access, find <strong>mitmproxy</strong>, double-click it and set trust to <strong>Always Trust</strong>.</li>
            <li>On <strong>Windows</strong>: double-click the downloaded <code class="ic">.p12</code> file and add it to <strong>Trusted Root Certification Authorities</strong>.</li>
          </ol>
          <div class="alert info" style="margin-top:14px">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="flex-shrink:0;margin-top:1px"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>
            <span>To bypass the proxy for specific addresses, add them to the <strong>Bypass Proxy</strong> list in your OS network settings.</span>
          </div>
        </template>

        <!-- Firefox -->
        <template v-if="activeTab === 'firefox'">
          <p class="hint" style="margin-bottom:14px">Firefox has its own independent proxy settings and certificate store — OS settings don't apply.</p>
          <ol class="instruction-list">
            <li>Open <strong>Settings → General → Network Settings → Settings…</strong> (or type <code class="ic">about:preferences#general</code> in the address bar).</li>
            <li>Select <strong>Manual proxy configuration</strong> and enter:
              <div class="info-box">
                <div class="info-row"><span class="info-label">HTTP Proxy</span><code class="info-val copyable" :class="{ copied: copiedInfo === 'ff_ip' }" @click="copyInfo(proxyIP, 'ff_ip')">{{ proxyIP }}</code></div>
                <div class="info-row"><span class="info-label">Port</span><code class="info-val copyable" :class="{ copied: copiedInfo === 'ff_port' }" @click="copyInfo(proxyPort, 'ff_port')">{{ proxyPort }}</code></div>
              </div>
              Check <strong>Also use this proxy for HTTPS</strong>.
            </li>
            <li>Navigate to <code class="ic">http://mitm.it</code> and download the Firefox/generic certificate.</li>
            <li>Go to <strong>Settings → Privacy &amp; Security → Certificates → View Certificates → Authorities → Import</strong> and import the downloaded <code class="ic">.pem</code> file.</li>
            <li>Check <strong>Trust this CA to identify websites</strong> and confirm.</li>
          </ol>
          <div class="alert warning" style="margin-top:14px">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="flex-shrink:0;margin-top:1px"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
            Firefox requires its own separate certificate import — installing it in the OS keychain is not enough.
          </div>
        </template>

        <!-- Safari -->
        <template v-if="activeTab === 'safari'">
          <p class="hint" style="margin-bottom:14px">Safari uses macOS system proxy and certificate settings.</p>
          <ol class="instruction-list">
            <li>Open <strong>System Settings → Network → (your interface) → Details → Proxies</strong>. Enable <strong>Web Proxy (HTTP)</strong> and <strong>Secure Web Proxy (HTTPS)</strong>:
              <div class="info-box">
                <div class="info-row"><span class="info-label">Server</span><code class="info-val copyable" :class="{ copied: copiedInfo === 'saf_ip' }" @click="copyInfo(proxyIP, 'saf_ip')">{{ proxyIP }}</code></div>
                <div class="info-row"><span class="info-label">Port</span><code class="info-val copyable" :class="{ copied: copiedInfo === 'saf_port' }" @click="copyInfo(proxyPort, 'saf_port')">{{ proxyPort }}</code></div>
              </div>
            </li>
            <li>Open Safari and navigate to <code class="ic">http://mitm.it</code>.</li>
            <li>Download the macOS certificate and open it — Keychain Access will open automatically.</li>
            <li>Find <strong>mitmproxy</strong> in Keychain Access, double-click it, expand <strong>Trust</strong>, and set <strong>Always Trust</strong>.</li>
          </ol>
        </template>

        <!-- curl / CLI -->
        <template v-if="activeTab === 'curl'">
          <p class="hint" style="margin-bottom:14px">Use environment variables or flags to route CLI tools through OpenProxy.</p>
          <div class="code-card" style="margin-bottom:14px">
            <div class="code-card-header">
              <div class="code-card-meta">
                <div class="code-card-title">Environment variables (shell / CI)</div>
                <div class="code-card-sub">Works for curl, wget, pip, npm, and most HTTP clients.</div>
              </div>
              <button class="copy-btn" :class="{ copied: copiedKey === 'env' }"
                      @click="copyToClipboard(`export http_proxy=http://${proxyIP}:${proxyPort}\nexport https_proxy=http://${proxyIP}:${proxyPort}`, 'env')">
                <svg v-if="copiedKey !== 'env'" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
                <svg v-else width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="var(--setup-success)" stroke-width="2.5" stroke-linecap="round"><polyline points="20 6 9 17 4 12"/></svg>
                {{ copiedKey === 'env' ? 'Copied!' : 'Copy' }}
              </button>
            </div>
            <div class="code-scroll">
              <pre class="code-pre">export http_proxy=http://{{ proxyIP }}:{{ proxyPort }}
export https_proxy=http://{{ proxyIP }}:{{ proxyPort }}</pre>
            </div>
          </div>
          <div class="code-card" style="margin-bottom:14px">
            <div class="code-card-header">
              <div class="code-card-meta">
                <div class="code-card-title">curl — single request</div>
              </div>
              <button class="copy-btn" :class="{ copied: copiedKey === 'curl' }"
                      @click="copyToClipboard(`curl -x http://${proxyIP}:${proxyPort} --cacert ~/.mitmproxy/mitmproxy-ca-cert.pem https://example.com`, 'curl')">
                <svg v-if="copiedKey !== 'curl'" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
                <svg v-else width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="var(--setup-success)" stroke-width="2.5" stroke-linecap="round"><polyline points="20 6 9 17 4 12"/></svg>
                {{ copiedKey === 'curl' ? 'Copied!' : 'Copy' }}
              </button>
            </div>
            <div class="code-scroll">
              <pre class="code-pre">curl -x http://{{ proxyIP }}:{{ proxyPort }} \
     --cacert ~/.mitmproxy/mitmproxy-ca-cert.pem \
     https://example.com</pre>
            </div>
          </div>
          <div class="alert info" style="margin-top:4px">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="flex-shrink:0;margin-top:1px"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>
            <span>The mitmproxy CA certificate is located at <code class="ic">~/.mitmproxy/mitmproxy-ca-cert.pem</code> (macOS/Linux) or <code class="ic">%USERPROFILE%\.mitmproxy\mitmproxy-ca-cert.pem</code> (Windows).</span>
          </div>
        </template>

      </div>

      <!-- ── Footer ──────────────────────────────────── -->
      <div class="modal-footer">
        <button
          v-if="(activePane === 'progress' || activePane === 'revert') && (deviceSetupType === 'android_emulator' || deviceSetupType === 'ios_simulator') && activeTab === 'devices'"
          class="footer-btn ghost" @click="activePane = 'pick'">
          <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round">
            <polyline points="15 18 9 12 15 6"/>
          </svg>
          Back
        </button>
        <button class="footer-btn" @click="showDeviceSetupModal = false">Close</button>
      </div>

    </div>
  </div>
</template>

<style scoped>
/* ── Layout shell ─────────────────────────────────── */
.modal-overlay {
  position: fixed; inset: 0; background: rgba(0,0,0,0.78);
  z-index: 99999; display: flex; justify-content: center; align-items: center;
  backdrop-filter: blur(4px);
}
.modal-content {
  background: var(--bg-main); border: 1px solid var(--border);
  border-radius: 10px; box-shadow: 0 24px 64px rgba(0,0,0,0.85);
  width: 580px; max-width: 94vw;
  display: flex; flex-direction: column;
  /* Let the modal grow with content but cap it so it fits small windows */
  max-height: min(88vh, 720px);
  overflow: hidden;
}

/* ── Header ───────────────────────────────────────── */
.modal-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 12px 16px; border-bottom: 1px solid var(--border);
  background: var(--bg-sidebar); flex-shrink: 0;
}
.header-left { display: flex; align-items: center; gap: 8px; }
.modal-header strong { color: var(--fg-secondary); font-size: 13px; font-weight: 600; }
.close-btn {
  display: flex; align-items: center; justify-content: center;
  width: 24px; height: 24px; border-radius: 5px;
  background: none; border: none; color: var(--fg-placeholder); cursor: pointer;
  transition: all 0.15s;
}
.close-btn:hover { background: rgba(255,255,255,0.07); color: var(--fg-muted); }

/* ── Tab bar ──────────────────────────────────────── */
.tab-bar {
  display: flex; padding: 6px 10px;
  border-bottom: 1px solid var(--border);
  background: var(--bg-sidebar); flex-shrink: 0; gap: 2px;
}
.tab-btn {
  display: flex; align-items: center; gap: 6px;
  padding: 5px 10px; font-size: 12px; font-weight: 500;
  color: var(--fg-muted); background: none; border: none; border-radius: 6px;
  cursor: pointer; transition: all 0.15s; white-space: nowrap;
}
.tab-btn svg { opacity: 0.6; transition: opacity 0.15s; }
.tab-btn:hover { color: var(--fg-secondary); background: rgba(255,255,255,0.04); }
.tab-btn:hover svg { opacity: 0.9; }
.tab-btn.active { color: var(--fg-primary); background: rgba(255,255,255,0.09); }
.tab-btn.active svg { opacity: 1; }

/* ── Scrollable body ──────────────────────────────── */
.modal-body {
  padding: 16px; font-size: 13px; color: var(--fg-secondary);
  line-height: 1.55; overflow-y: auto; flex: 1;
  text-align: left;
  /* Custom scrollbar */
  scrollbar-width: thin; scrollbar-color: var(--border) transparent;
}
.modal-body::-webkit-scrollbar { width: 5px; }
.modal-body::-webkit-scrollbar-track { background: transparent; }
.modal-body::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }

/* ── Picker ───────────────────────────────────────── */
.picker-top {
  display: flex; align-items: center; justify-content: space-between;
  gap: 12px; margin-bottom: 12px;
}
.hint { color: var(--fg-muted); font-size: 12px; margin: 0; text-align: left; }

.refresh-btn {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 5px 11px; border-radius: 6px; font-size: 12px; font-weight: 500;
  background: var(--bg-card); border: 1px solid var(--border); color: var(--fg-muted);
  cursor: pointer; transition: all 0.15s; flex-shrink: 0;
  white-space: nowrap;
}
.refresh-btn:hover:not(:disabled) { background: var(--bg-active); color: var(--fg-secondary); border-color: var(--border); }
.refresh-btn:disabled { opacity: 0.45; cursor: not-allowed; }

/* ── Device list ──────────────────────────────────── */
.device-list { display: flex; flex-direction: column; gap: 5px; margin-bottom: 12px; }

.device-row {
  display: flex; align-items: center; gap: 10px;
  padding: 9px 11px;
  background: rgba(255,255,255,0.022); border: 1px solid #232628;
  border-radius: 7px; transition: border-color 0.15s;
}
.device-row:hover { border-color: #363a3d; background: rgba(255,255,255,0.035); }

.device-thumb {
  width: 34px; height: 34px; border-radius: 7px;
  background: var(--accent-muted); border: 1px solid rgba(59,130,246,0.15);
  display: flex; align-items: center; justify-content: center;
  color: var(--accent); flex-shrink: 0;
}

.device-info { flex: 1; display: flex; flex-direction: column; gap: 2px; min-width: 0; text-align: left; }
.device-model { color: var(--fg-secondary); font-size: 13px; font-weight: 500; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.device-serial { color: var(--fg-muted); font-size: 11px; font-family: monospace; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

.type-badge {
  font-size: 10px; font-weight: 700; text-transform: uppercase;
  letter-spacing: 0.05em; padding: 2px 7px; border-radius: 10px; flex-shrink: 0;
}
.type-badge.emulator { background: var(--accent-muted); color: var(--accent); border: 1px solid rgba(59,130,246,0.2); }
.type-badge.device   { background: rgba(52,211,153,0.08); color: #34d399; border: 1px solid rgba(52,211,153,0.18); }
.type-badge.offline  { background: rgba(100,100,110,0.12); color: #6b7280; border: 1px solid rgba(100,100,110,0.25); }

.row-actions { display: flex; gap: 4px; flex-shrink: 0; }

.pill {
  display: inline-flex; align-items: center; gap: 4px;
  padding: 4px 9px; border-radius: 5px; font-size: 11px; font-weight: 600;
  cursor: pointer; border: 1px solid transparent; transition: all 0.15s;
}
.pill.install { background: rgba(59,130,246,0.13); color: var(--accent); border-color: rgba(59,130,246,0.22); }
.pill.install:hover { background: rgba(59,130,246,0.25); }
.pill.install:disabled { opacity: 0.35; cursor: not-allowed; }
.pill.revert  { background: rgba(239,68,68,0.09);  color: var(--setup-error); border-color: rgba(239,68,68,0.18); }
.pill.revert:hover  { background: rgba(239,68,68,0.2); }

/* ── Skeleton ─────────────────────────────────────── */
@keyframes shimmer { 0%{background-position:-400px 0} 100%{background-position:400px 0} }
.sk {
  background: linear-gradient(90deg, var(--bg-card) 25%, var(--bg-active) 50%, var(--bg-card) 75%);
  background-size: 800px 100%; animation: shimmer 1.4s infinite linear;
}

/* ── Empty state ──────────────────────────────────── */
.empty-state { text-align: center; padding: 24px 0; color: var(--fg-placeholder); display: flex; flex-direction: column; align-items: center; gap: 4px; }
.empty-title { color: var(--fg-placeholder); font-size: 13px; font-weight: 500; margin: 6px 0 0; }
.empty-sub   { font-size: 11.5px; color: var(--fg-placeholder); margin: 0; }
.empty-sub code { color: var(--fg-muted); background: var(--bg-card); padding: 1px 4px; border-radius: 3px; }

/* ── Prereq note ──────────────────────────────────── */
.prereq-note {
  display: flex; align-items: flex-start; gap: 7px;
  font-size: 11.5px; color: var(--fg-muted); line-height: 1.5;
  border-top: 1px solid var(--border-subtle); padding-top: 10px; margin-top: 6px;
  text-align: left;
}
.prereq-note strong { color: var(--fg-muted); }

/* macOS proxy toggle row */
.proxy-toggle-row {
  display: flex; align-items: center; justify-content: space-between; gap: 10px;
  border-top: 1px solid var(--border-subtle); padding-top: 10px; margin-top: 6px;
}
.proxy-toggle-info {
  display: flex; align-items: flex-start; gap: 7px;
  font-size: 11.5px; color: var(--fg-muted); line-height: 1.5; flex: 1;
}
.proxy-toggle-actions { display: flex; gap: 6px; flex-shrink: 0; }
.proxy-on  { color: var(--setup-success); }
.proxy-off { color: var(--fg-muted); }
.proxy-services { color: var(--fg-muted); font-size: 10.5px; }

/* ── Progress ─────────────────────────────────────── */
.progress-header { display: flex; align-items: center; gap: 12px; margin-bottom: 16px; }
.progress-title  { color: var(--fg-secondary); font-size: 14px; font-weight: 600; text-align: left; }
.progress-sub    { color: var(--fg-placeholder); font-size: 11px; margin-top: 2px; text-align: left; }
.progress-sub code { color: var(--fg-muted); font-family: monospace; }

.progress-steps { display: flex; flex-direction: column; gap: 5px; }

.progress-step {
  display: flex; align-items: center; gap: 10px;
  padding: 9px 12px; border-radius: 7px;
  border: 1px solid var(--border-subtle); font-size: 13px; color: var(--fg-placeholder);
  transition: all 0.22s; text-align: left;
}
.progress-step.loading { border-color: var(--accent-border); color: #e5e7eb; background: rgba(59,130,246,0.06); }
.progress-step.success { border-color: rgba(52,211,153,0.22); color: #34d399; background: rgba(52,211,153,0.05); }
.progress-step.error   { border-color: rgba(239,68,68,0.28);  color: var(--setup-error); background: rgba(239,68,68,0.06); }
.progress-step.skip    { opacity: 0.32; }

.step-icon  { width: 18px; display: flex; justify-content: center; flex-shrink: 0; }
.step-label { flex: 1; }

/* ── Alerts ───────────────────────────────────────── */
.alert {
  display: flex; align-items: flex-start; gap: 8px;
  font-size: 12px; padding: 9px 12px; border-radius: 6px;
  border: 1px solid transparent; line-height: 1.5; text-align: left;
}
.alert.error   { color: #fca5a5; background: rgba(239,68,68,0.07);  border-color: rgba(239,68,68,0.16); }
.alert.success { color: #6ee7b7; background: rgba(52,211,153,0.06); border-color: rgba(52,211,153,0.15); }
.alert.warning { color: #fcd34d; background: rgba(245,158,11,0.06); border-color: rgba(245,158,11,0.15); }

/* ── Manual instructions ──────────────────────────── */
.instruction-list {
  padding-left: 20px; display: flex; flex-direction: column;
  gap: 10px; color: var(--fg-muted); margin: 0; text-align: left;
}
.instruction-list li { padding-left: 4px; }
.instruction-list strong { color: var(--fg-secondary); }

.info-box {
  margin-top: 8px; padding: 9px 12px; background: rgba(0,0,0,0.2);
  border-radius: 6px; border: 1px solid var(--border);
  display: flex; flex-direction: column; gap: 6px;
}
.info-row { display: flex; align-items: center; gap: 8px; }
.info-label { color: var(--fg-muted); font-size: 11px; width: 60px; flex-shrink: 0; text-align: left; }
.info-val {
  background: var(--accent-muted); color: var(--accent);
  border: 1px solid rgba(59,130,246,0.2);
  padding: 2px 8px; border-radius: 4px; font-size: 13px;
  font-weight: 700; font-family: monospace;
}
.info-val.copyable { cursor: pointer; user-select: all; transition: background 0.15s, color 0.15s, border-color 0.15s; }
.info-val.copyable:hover { background: rgba(59,130,246,0.2); }
.info-val.copied { background: rgba(52,211,153,0.12) !important; color: #34d399 !important; border-color: rgba(52,211,153,0.3) !important; }
.ic {
  background: var(--bg-card); color: var(--fg-muted); padding: 1px 5px;
  border-radius: 3px; font-family: monospace; font-size: 11.5px;
  border: 1px solid var(--border-subtle);
}

/* ── Config tab ───────────────────────────────────── */
.config-body { gap: 0; }

.config-intro {
  font-size: 12.5px; color: var(--fg-muted); line-height: 1.65;
  margin: 0 0 16px; text-align: left;
}
.config-intro strong { color: var(--fg-muted); }

.code-card {
  border: 1px solid var(--border); border-radius: 8px;
  overflow: hidden; margin-bottom: 14px;
}

.code-card-header {
  display: flex; align-items: flex-start; gap: 10px;
  padding: 10px 13px;
  background: rgba(255,255,255,0.02);
  border-bottom: 1px solid var(--border);
}

.step-num {
  width: 20px; height: 20px; border-radius: 50%; flex-shrink: 0;
  background: rgba(59,130,246,0.16); color: var(--accent);
  font-size: 11px; font-weight: 700; margin-top: 1px;
  display: flex; align-items: center; justify-content: center;
}

.code-card-meta { flex: 1; min-width: 0; text-align: left; }
.code-card-title { color: var(--fg-secondary); font-size: 12.5px; font-weight: 600; margin-bottom: 2px; }
.code-card-sub   { color: var(--fg-placeholder); font-size: 11px; }

.filepath {
  font-family: monospace; font-size: 11.5px;
  background: rgba(255,255,255,0.06); padding: 1px 5px;
  border-radius: 3px; color: var(--fg-muted);
}

.copy-btn {
  display: inline-flex; align-items: center; gap: 5px; flex-shrink: 0;
  padding: 4px 10px; border-radius: 5px; font-size: 11px; font-weight: 600;
  cursor: pointer; transition: all 0.15s; white-space: nowrap;
  background: rgba(255,255,255,0.04); border: 1px solid #2a2d30; color: var(--fg-muted);
}
.copy-btn:hover { background: var(--surface-hover-strong); color: var(--fg-secondary); }
.copy-btn.copied { color: #34d399; border-color: rgba(52,211,153,0.28); background: rgba(52,211,153,0.06); }

/* Scrollable code block */
.code-scroll {
  overflow-x: auto; overflow-y: auto;
  max-height: 260px;
  scrollbar-width: thin; scrollbar-color: var(--border) transparent;
}
.code-scroll::-webkit-scrollbar { width: 5px; height: 5px; }
.code-scroll::-webkit-scrollbar-track { background: transparent; }
.code-scroll::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }

.code-pre {
  margin: 0; padding: 13px 15px;
  background: var(--bg-deepest);
  font-family: 'SF Mono', 'Fira Code', ui-monospace, 'Cascadia Code', Consolas, monospace;
  font-size: 12px; line-height: 1.7;
  white-space: pre; tab-size: 4;
  text-align: left;
  /* Don't let pre shrink — let the scroll container handle overflow */
  min-width: max-content;
}

/* XML syntax token colours */
:deep(.xt-comment) { color: var(--syntax-green); font-style: italic; }
:deep(.xt-tag)     { color: var(--syntax-cyan); }   /* light blue — tag names */
:deep(.xt-attr)    { color: var(--accent); }   /* softer blue — attribute names */
:deep(.xt-attrval) { color: var(--syntax-green); }   /* green — attribute values */
:deep(.xt-punct)   { color: var(--fg-muted); }   /* grey — < > / */
:deep(.xt-decl)    { color: var(--syntax-purple); }   /* purple — <?xml */

/* ── Note cards ───────────────────────────────────── */
.note-card {
  font-size: 12px; color: var(--fg-muted); line-height: 1.6; text-align: left;
  padding: 9px 12px; background: rgba(255,255,255,0.015);
  border: 1px solid var(--border-subtle); border-radius: 6px;
}
.note-label { font-size: 11px; font-weight: 700; color: var(--fg-muted); text-transform: uppercase; letter-spacing: 0.04em; margin-bottom: 3px; }
.note-card p { margin: 0; }
.note-card .ic { color: var(--fg-muted); }

/* ── Footer ───────────────────────────────────────── */
.modal-footer {
  padding: 10px 16px; border-top: 1px solid var(--border);
  display: flex; justify-content: flex-end; align-items: center; gap: 7px;
  background: var(--bg-sidebar); flex-shrink: 0;
}
.footer-btn {
  display: inline-flex; align-items: center; gap: 5px;
  background: var(--bg-active); border: 1px solid var(--border); color: var(--fg-secondary);
  border-radius: 5px; padding: 5px 14px; font-size: 12px;
  cursor: pointer; transition: all 0.15s;
}
.footer-btn:hover { background: var(--border); color: var(--fg-secondary); }
.footer-btn.ghost { background: transparent; border-color: var(--bg-active); color: var(--fg-muted); }
.footer-btn.ghost:hover { background: rgba(255,255,255,0.04); color: var(--fg-muted); }

/* ── Spinner ──────────────────────────────────────── */
@keyframes spin { to { transform: rotate(360deg); } }
.spinning { animation: spin 0.8s linear infinite; }

/* ── VPN Mode / WireGuard ─────────────────────────── */
.wg-body { gap: 12px; }

.wg-status-pill {
  display: inline-flex; align-items: center;
  font-size: 10px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em;
  padding: 2px 7px; border-radius: 10px; margin-left: 8px;
}
.wg-status-pill.pill-ready   { background: rgba(52,211,153,0.12); color: #34d399; border: 1px solid rgba(52,211,153,0.25); }
.wg-status-pill.pill-starting { background: rgba(96,165,250,0.12); color: var(--accent); border: 1px solid rgba(96,165,250,0.25); }
.wg-status-pill.pill-off     { background: rgba(100,110,115,0.12); color: #6b7280; border: 1px solid #2a2d30; }
.wg-status-pill.pill-error   { background: rgba(248,113,113,0.12); color: var(--setup-error); border: 1px solid rgba(248,113,113,0.25); }

.tab-vpn-dot {
  display: inline-block; width: 6px; height: 6px; border-radius: 50%;
  background: var(--setup-success); margin-left: 5px; flex-shrink: 0;
}

.wg-toggle-row {
  display: flex; align-items: center; justify-content: space-between;
  background: rgba(255,255,255,0.025); border: 1px solid #1e2124;
  border-radius: 7px; padding: 10px 13px;
}
.wg-toggle-info { display: flex; flex-direction: column; gap: 2px; }
.wg-toggle-title { font-size: 13px; font-weight: 600; color: var(--fg-secondary); }
.wg-toggle-sub   { font-size: 11px; color: var(--fg-muted); }

.wg-toggle-btn {
  display: flex; align-items: center; gap: 7px;
  background: none; border: none; cursor: pointer; padding: 0;
}
.wg-toggle-btn:disabled { opacity: 0.5; cursor: default; }
.wg-toggle-track {
  width: 34px; height: 18px; border-radius: 9px;
  background: var(--bg-active); border: 1px solid var(--border);
  position: relative; transition: background 0.2s;
  display: flex; align-items: center; padding: 2px;
}
.wg-toggle-btn.active .wg-toggle-track  { background: var(--success-muted); border-color: var(--setup-success); }
.wg-toggle-btn.loading .wg-toggle-track { background: var(--accent-muted); border-color: var(--accent); }
.wg-toggle-thumb {
  width: 12px; height: 12px; border-radius: 50%;
  background: var(--fg-muted); transition: transform 0.2s, background 0.2s;
}
.wg-toggle-btn.active  .wg-toggle-thumb { transform: translateX(16px); background: var(--setup-success); }
.wg-toggle-btn.loading .wg-toggle-thumb { transform: translateX(8px);  background: var(--accent); }
.wg-toggle-label { font-size: 12px; color: var(--fg-muted); min-width: 22px; }
.wg-toggle-btn.active .wg-toggle-label { color: var(--setup-success); }

.wg-port-row {
  display: flex; align-items: center; gap: 10px;
  padding: 8px 13px; background: rgba(255,255,255,0.02);
  border: 1px solid var(--border); border-radius: 7px;
}
.wg-port-label { font-size: 12px; color: var(--fg-muted); flex: 1; }
.wg-port-input {
  width: 80px; background: var(--bg-card); border: 1px solid var(--border);
  color: var(--fg-secondary); font-size: 12px; padding: 4px 8px; border-radius: 5px;
  text-align: center;
}
.wg-port-input:focus { outline: none; border-color: var(--accent); }

.wg-starting {
  display: flex; align-items: center; gap: 9px;
  font-size: 13px; color: var(--accent); padding: 8px 0;
}

.wg-qr-section {
  display: flex; flex-direction: column; align-items: center; gap: 8px;
  padding: 16px; background: rgba(255,255,255,0.025); border: 1px solid var(--border); border-radius: 8px;
}
.wg-qr-canvas { width: 180px; height: 180px; image-rendering: pixelated; }
.wg-qr-hint   { font-size: 11px; color: var(--fg-muted); }

.wg-conf-header {
  display: flex; align-items: center; justify-content: space-between;
  font-size: 11px; color: var(--fg-muted); font-family: monospace;
  padding: 0 2px;
}
.wg-conf-pre {
  background: var(--bg-deepest); border: 1px solid var(--border); border-radius: 6px;
  padding: 10px 12px; font-size: 11px; color: var(--setup-success); font-family: monospace;
  white-space: pre-wrap; word-break: break-all; max-height: 160px; overflow-y: auto;
  margin: 0;
}

/* ── Alert variants ───────────────────────────────── */
.alert.info {
  background: rgba(96,165,250,0.08); border: 1px solid rgba(96,165,250,0.2); color: var(--accent);
}

</style>