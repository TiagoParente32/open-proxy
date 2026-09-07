import { ref, computed, watch } from 'vue'

// ============================================================================
// 1. CONSTANTS & UTILITIES
// ============================================================================
const MAX_LIVE_REQUESTS = 2000;
const MAX_SAVED_REQUESTS = 500;

export let wsConnection = null;
let wsSaveTimeout = null;

export const isComposeEditMode = ref(false)

export const openComposeNew = () => {
    isComposeEditMode.value = false
    composeData.value = {
        method: 'GET',
        url: 'https://',
        req_headers: '{\n  "Accept": "*/*",\n  "User-Agent": "OpenProxy/1.0"\n}',
        req_body: ''
    }
    closeAllModals()
    showComposeModal.value = true
}

const loadState = (key, defaultVal) => {
    try {
        const saved = localStorage.getItem(`openproxy_${key}`)
        return saved ? JSON.parse(saved) : defaultVal
    } catch (e) {
        return defaultVal
    }
}

const saveState = (key, value) => {
    try {
        localStorage.setItem(`openproxy_${key}`, JSON.stringify(value))
    } catch (e) {
        console.warn(`Storage limit reached for ${key}. Try clearing traffic.`)
    }
}

export const formatUrl = (fullUrl) => {
    try { const u = new URL(fullUrl); return { host: u.hostname, path: u.pathname + u.search } }
    catch (e) { return { host: fullUrl, path: '' } }
}

export const formatTime = (timestamp) => {
    if (!timestamp) return ''
    const d = new Date(timestamp * 1000)
    return d.toTimeString().split(' ')[0] + '.' + String(d.getMilliseconds()).padStart(3, '0')
}

export const formatBytes = (bytes) => {
    if (bytes === 0) return '0 B'
    const k = 1024
    const sizes = ['B', 'KB', 'MB']
    const i = Math.floor(Math.log(bytes) / Math.log(k))
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i]
}

export const exportRules = (rules, filename) => {
    const data = rules.value !== undefined ? rules.value : rules;
    const jsonString = JSON.stringify(data, null, 2);

    if (window.electronAPI) {
        window.electronAPI.saveFile(filename + '.json', jsonString)
            .catch(err => console.error("Export failed:", err));
    } else {
        alert("System API not ready yet. Please wait a moment and try again.");
    }
}

export const importRules = (event, rulesRef) => {
    const file = event.target.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (e) => {
        try {
            const importedRules = JSON.parse(e.target.result);
            if (Array.isArray(importedRules)) {
                if (rulesRef.value !== undefined) {
                    rulesRef.value = [...rulesRef.value, ...importedRules];
                } else {
                    rulesRef.push(...importedRules);
                }
            } else {
                alert("Invalid file format. Expected an array of rules.");
            }
        } catch (err) {
            alert("Failed to parse JSON file.");
        }
        event.target.value = '';
    };
    reader.readAsText(file);
}


// ============================================================================
// 2. CORE PROXY STATE
// ============================================================================
export const requests = ref(loadState('requests', []))
export const connectionStatus = ref('Connecting...')
export const platform = ref('')  // 'darwin' | 'win32' | 'linux'
export const isRecording = ref(true)
export const proxyHost = ref('Detecting...')

export const proxyIP = computed(() => {
    return proxyHost.value.includes(':') ? proxyHost.value.split(':')[0] : '...'
})

export const proxyPort = computed(() => {
    return proxyHost.value.includes(':') ? proxyHost.value.split(':')[1] : '...'
})

export const selectedRequest = ref(null)
export const activeReqTab = ref('Header')
export const activeResTab = ref('Body')
export const contextMenu = ref({ show: false, x: 0, y: 0, request: null })

export const wsMessages = ref(loadState('wsMessages', {}))


// ============================================================================
// 3. FEATURE STATE (Filters, Modals, Settings)
// ============================================================================
export const isFocusMode = ref(loadState('isFocusMode', false))
export const pinnedSources = ref(loadState('pinnedSources', []))
export const activeFilter = ref({ type: 'all', value: null })
export const searchQuery = ref('')
export const searchScope = ref('All')
export const searchMatchType = ref('Contains')
export const sortKey = ref('time')
export const sortOrder = ref(loadState('sortOrder', 'desc'))

const normalizePinnedSource = (source) => String(source ?? '').trim()

const findPinnedSource = (source) => {
    const normalized = normalizePinnedSource(source).toLowerCase()
    if (!normalized) return null
    return pinnedSources.value.find(pinned => pinned.toLowerCase() === normalized) || null
}

export const isPinnedSource = (source) => !!findPinnedSource(source)

export const pinSource = (source) => {
    const normalized = normalizePinnedSource(source)
    if (!normalized) return

    const existing = findPinnedSource(normalized)
    const pinnedValue = existing || normalized

    if (!existing) {
        pinnedSources.value.push(pinnedValue)
    }

    activeFilter.value = { type: 'pinned', domain: pinnedValue }
}

export const unpinSource = (source) => {
    const existing = findPinnedSource(source)
    if (!existing) return

    pinnedSources.value = pinnedSources.value.filter(pinned => pinned.toLowerCase() !== existing.toLowerCase())
    if (activeFilter.value.type === 'pinned' && String(activeFilter.value.domain ?? '').toLowerCase() === existing.toLowerCase()) {
        activeFilter.value = { type: 'all' }
    }
}

export const activeChips = ref(loadState('activeChips', {
    protocol: 'All', type: 'All', status: 'All', color: 'All', starred: false
}))

export const throttleProfile = ref(loadState('throttleProfile', 'None'))
export const disableCache = ref(loadState('disableCache', false))

// Map Local
export const showMapModal = ref(false)
export const mapLocalRules = ref(loadState('mapLocalRules', []))
export const enableMapLocal = ref(mapLocalRules.value.length > 0 ? loadState('enableMapLocal', true) : false)
export const selectedRuleId = ref(null)

// Map Remote
export const showMapRemoteModal = ref(false)
export const mapRemoteRules = ref(loadState('mapRemoteRules', []))
export const enableMapRemote = ref(mapRemoteRules.value.length > 0 ? loadState('enableMapRemote', true) : false)
export const selectedMapRemoteId = ref(null)

// Breakpoints
export const showBreakpointModal = ref(false)
export const breakpointRules = ref(loadState('breakpointRules', []))
export const breakpointsEnabled = ref(breakpointRules.value.length > 0 ? loadState('breakpointsEnabled', true) : false)
export const trappedFlows = ref([])
export const selectedBreakpointId = ref(null)

// Auto-Highlights
export const showHighlightModal = ref(false)
export const highlightRules = ref(loadState('highlightRules', []))
export const highlightsEnabled = ref(highlightRules.value.length > 0 ? loadState('highlightsEnabled', true) : false)
export const pendingHighlightRuleId = ref(null)  // set before opening modal to auto-select a new rule

export const addDeviceHighlightRule = (ip, label) => {
    const newRule = { id: Date.now(), active: true, name: `${label} traffic`, type: 'client_ip', pattern: ip, color: 'blue' }
    highlightRules.value.unshift(newRule)
    pendingHighlightRuleId.value = newRule.id
    closeAllModals()
    showHighlightModal.value = true
}

// Compose
export const showComposeModal = ref(false)
export const composeData = ref(null)

// Device Setup Modal
export const showDeviceSetupModal = ref(false)
export const deviceSetupType = ref('emulator')

// WireGuard / VPN mode
export const wgEnabled = ref(false)
export const wgPort = ref(51820)
export const wgStatus = ref('disabled')   // 'disabled' | 'starting' | 'ready' | 'error'
export const wgClientConf = ref('')
export const wgError = ref('')

// ── User Scripting ────────────────────────────────────────────────────────────
export const showScriptingModal  = ref(false)
export const scripts             = ref([])   // [{ id, name, content, enabled, error }]
export const selectedScriptId    = ref(null)
export const anyScriptEnabled    = computed(() => scripts.value.some(s => s.enabled))

// Toolbar active-state computeds for rule-based features
export const anyMapLocalActive    = computed(() => enableMapLocal.value    && mapLocalRules.value.length > 0)
export const anyMapRemoteActive   = computed(() => enableMapRemote.value   && mapRemoteRules.value.length > 0)
export const anyBreakpointActive  = computed(() => breakpointsEnabled.value && breakpointRules.value.length > 0)
export const anyHighlightActive   = computed(() => highlightsEnabled.value && highlightRules.value.length > 0)

// ── Toolbar visibility preferences ───────────────────────────────────────────
export const toolbarVisibility = ref((() => {
  const defaults = {
    vpnMode:      true,
    breakpoints:  true,
    mapLocal:     true,
    mapRemote:    true,
    highlights:   true,
    scripts:      false,
    certificates: true,
    throttle:     true,
    bustCache:    true,
    osProxy:      true,
  }
  return { ...defaults, ...loadState('toolbarVisibility', {}) }
})())

// Show button if user wants it OR the feature is actively on (so you can't lose an active rule)
export const showVpnModeBtn     = computed(() => toolbarVisibility.value.vpnMode      || (wgEnabled.value && wgStatus.value === 'ready'))
export const showBreakpointsBtn = computed(() => toolbarVisibility.value.breakpoints  || anyBreakpointActive.value)
export const showMapLocalBtn    = computed(() => toolbarVisibility.value.mapLocal     || anyMapLocalActive.value)
export const showMapRemoteBtn   = computed(() => toolbarVisibility.value.mapRemote    || anyMapRemoteActive.value)
export const showHighlightBtn   = computed(() => toolbarVisibility.value.highlights   || anyHighlightActive.value)
export const showScriptBtn      = computed(() => toolbarVisibility.value.scripts      || anyScriptEnabled.value)
export const showCertificatesBtn = computed(() => toolbarVisibility.value.certificates)
export const showThrottleBtn    = computed(() => toolbarVisibility.value.throttle)
export const showBustCacheBtn   = computed(() => toolbarVisibility.value.bustCache)
export const showOsProxyBtn     = computed(() => toolbarVisibility.value.osProxy)

export const openVpnMode = () => {
    deviceSetupType.value = 'vpn_mode'
    closeAllModals()
    showDeviceSetupModal.value = true
}

// List of { serial, model, type, state } objects returned by the backend
export const adbDevices = ref([])
// Whether a LIST_ADB_DEVICES fetch is in-flight
export const adbDevicesLoading = ref(false)
export const adbDevicesError = ref(null)

// List of { name, running_serial } objects — every configured AVD, running or not
export const avds = ref([])
export const avdsLoading = ref(false)
export const avdsError = ref(null)
// { [avdName]: { state: 'launching'|'booting'|'error', serial?: string, error?: string } }
export const avdBootStatus = ref({})

export const setupProgress = ref({
    show: false,
    error: null,
    // 'setup' or 'revert' — controls which title/copy to show
    mode: 'setup',
    targetSerial: null,
    steps: [
        { id: 'check_adb',    label: 'Checking dependencies...',    status: 'pending' },
        { id: 'cert_prepare', label: 'Preparing certificate...',     status: 'pending' },
        { id: 'root_emu',     label: 'Rooting emulator...',          status: 'pending' },
        { id: 'push_cert',    label: 'Installing certificate...',    status: 'pending' },
        { id: 'set_proxy',    label: 'Configuring global proxy...',  status: 'pending' },
    ]
})

// Revert progress uses a simpler two-step flow
export const revertProgress = ref({
    show: false,
    error: null,
    targetSerial: null,
    steps: [
        { id: 'clear_proxy',  label: 'Clearing proxy settings...', status: 'pending' },
        { id: 'remove_cert',  label: 'Removing certificate...',    status: 'pending' },
    ]
})

// iOS Simulator state
export const iosSimulators = ref([])
export const iosSimulatorsLoading = ref(false)
export const iosSimulatorsError = ref(null)

// { [udid]: { state: 'booting'|'error', error?: string } } — per-simulator boot status
export const iosBootStatus = ref({})

export const iosSetupProgress = ref({
    show: false,
    error: null,
    targetUdid: null,
    steps: [
        { id: 'check_xcrun',  label: 'Checking Xcode tools...',   status: 'pending' },
        { id: 'find_cert',    label: 'Locating certificate...',    status: 'pending' },
        { id: 'install_cert', label: 'Installing certificate...', status: 'pending' },
    ]
})

export const iosRevertProgress = ref({
    show: false,
    error: null,
    targetUdid: null,
    steps: [
        { id: 'find_store',  label: 'Locating trust store...',  status: 'pending' },
        { id: 'remove_cert', label: 'Removing certificate...', status: 'pending' },
    ]
})

// macOS system proxy state
export const macosProxyActive       = ref(false)
export const macosProxyLoading      = ref(false)
export const macosProxyFirstTimeSetup = ref(false)   // true while the one-time sudoers install runs
export const macosProxyError        = ref(null)
export const macosProxyServices     = ref([])

// "Trust the mitmproxy CA on this machine" — checked once right after onboarding
export const showCertTrustDialog = ref(false)
export const certTrustStatus     = ref(null)   // true | false | null (unknown / not checked yet)
export const certTrustLoading    = ref(false)
export const certTrustError      = ref(null)

// Proxy engine options (persisted)
export const proxyHttp2        = ref(loadState('proxyHttp2', true))
export const proxyUpstreamCert = ref(loadState('proxyUpstreamCert', true))
export const proxyIgnoreHosts  = ref(loadState('proxyIgnoreHosts', []))
export const proxyAllowHosts   = ref(loadState('proxyAllowHosts', []))
// 'ignore' = pass listed hosts through | 'allow' = only intercept listed hosts
export const proxyHostFilterMode = ref(loadState('proxyHostFilterMode', 'allow'))

// UI modal visibility (shared so sidebar can trigger it)
export const showIgnoreHostsModal   = ref(false)
export const showOsProxyWarning     = ref(false)


export const closeAllModals = () => {
    showMapModal.value          = false
    showMapRemoteModal.value    = false
    showBreakpointModal.value   = false
    showHighlightModal.value    = false
    showComposeModal.value      = false
    showDeviceSetupModal.value  = false
    showScriptingModal.value    = false
    showIgnoreHostsModal.value  = false
}

// ============================================================================
// 4. ACTIONS & LOGIC
// ============================================================================
const applyHighlightRules = (req) => {
    if (req.manualColor) return;
    req.color = null;
    if (!highlightsEnabled.value) return;

    for (const rule of highlightRules.value) {
        if (!rule.active) continue;
        let isMatch = false;
        try {
            const url = req.url || ''
            const status = String(req.status ?? '')
            const method = (req.method || '').toUpperCase()
            const resBody = String(req.res_body ?? '')
            const reqBody = String(req.req_body ?? '')
            const resHeaders = req.res_headers && typeof req.res_headers === 'object'
                ? Object.entries(req.res_headers).map(([k,v]) => `${k}: ${v}`).join('\n') : ''
            const reqHeaders = req.req_headers && typeof req.req_headers === 'object'
                ? Object.entries(req.req_headers).map(([k,v]) => `${k}: ${v}`).join('\n') : ''
            const pat = rule.pattern || ''

            switch (rule.type) {
                case 'url':          isMatch = url.toLowerCase().includes(pat.toLowerCase()); break
                case 'url_regex':    isMatch = new RegExp(pat, 'i').test(url); break
                case 'status':       isMatch = status === String(pat); break
                case 'status_range': isMatch = pat.length === 3 && pat[1] === 'x' && pat[2] === 'x'
                                         ? status.startsWith(pat[0])
                                         : status.includes(pat); break
                case 'method':       isMatch = method === pat.toUpperCase(); break
                case 'res_body':     isMatch = resBody.toLowerCase().includes(pat.toLowerCase()); break
                case 'req_body':     isMatch = reqBody.toLowerCase().includes(pat.toLowerCase()); break
                case 'res_header':   isMatch = resHeaders.toLowerCase().includes(pat.toLowerCase()); break
                case 'req_header':   isMatch = reqHeaders.toLowerCase().includes(pat.toLowerCase()); break
                case 'client_ip':    isMatch = (req.client_ip || '127.0.0.1') === pat; break
            }
        } catch (e) { continue; }

        if (isMatch) {
            req.color = rule.color;
            break;
        }
    }
}

export const listAdbDevices = () => {
    if (wsConnection?.readyState !== WebSocket.OPEN) return
    adbDevicesLoading.value = true
    adbDevicesError.value = null
    adbDevices.value = []
    wsConnection.send(JSON.stringify({ type: "LIST_ADB_DEVICES" }))
}

/** Request the backend to list all configured AVDs (like Android Studio's Device Manager). */
export const listAvds = () => {
    if (wsConnection?.readyState !== WebSocket.OPEN) return
    avdsLoading.value = true
    avdsError.value = null
    wsConnection.send(JSON.stringify({ type: "LIST_AVDS" }))
}

/** Boot an offline AVD by name, mirroring double-clicking it in Android Studio. */
export const bootAvd = (name) => {
    if (wsConnection?.readyState !== WebSocket.OPEN) return
    avdBootStatus.value = { ...avdBootStatus.value, [name]: { state: 'launching', error: null } }
    wsConnection.send(JSON.stringify({ type: "BOOT_AVD", name }))
}

/**
 * Kick off the certificate install + proxy setup on a specific device.
 * @param {string} serial  - ADB device serial, e.g. "emulator-5554" or "R58M31XXXXX"
 * @param {string} deviceType - "emulator" | "device"
 */
export const setupAndroidDevice = (serial, deviceType) => {
    if (wsConnection?.readyState !== WebSocket.OPEN) return

    setupProgress.value.mode = 'setup'
    setupProgress.value.targetSerial = serial
    setupProgress.value.show = true
    setupProgress.value.error = null
    setupProgress.value.steps.forEach(s => s.status = 'pending')

    wsConnection.send(JSON.stringify({
        type: "SETUP_ANDROID_DEVICE",
        serial,
        device_type: deviceType
    }))
}

export const revertAndroidDevice = (serial) => {
    if (wsConnection?.readyState !== WebSocket.OPEN) return

    revertProgress.value.targetSerial = serial
    revertProgress.value.show = true
    revertProgress.value.error = null
    revertProgress.value.steps.forEach(s => s.status = 'pending')

    wsConnection.send(JSON.stringify({
        type: "REVERT_ANDROID_DEVICE",
        serial
    }))
}

// Legacy shim — kept so any existing call to injectEmulatorCert() still works
export const injectEmulatorCert = () => {
    setupAndroidDevice("emulator-5554", "emulator")
}

// Per-serial status for the "push cert to Downloads" action: { state: 'idle'|'pushing'|'success'|'error', error, path }
export const certPushStatus = ref({})

/**
 * Push the mitmproxy CA cert (.cer) directly into a device's Downloads folder via adb,
 * as an alternative to visiting http://mitm.it in the device browser.
 * @param {string} serial - ADB device serial
 */
export const pushCertToDownloads = (serial) => {
    if (!serial) {
        console.warn('[pushCertToDownloads] No serial provided, aborting')
        return
    }
    if (wsConnection?.readyState !== WebSocket.OPEN) {
        console.warn('[pushCertToDownloads] WebSocket not open, readyState=', wsConnection?.readyState)
        return
    }
    console.log('[pushCertToDownloads] Sending PUSH_CERT_TO_DOWNLOADS for serial=', serial)
    certPushStatus.value = { ...certPushStatus.value, [serial]: { state: 'pushing', error: null, logs: [] } }
    wsConnection.send(JSON.stringify({ type: "PUSH_CERT_TO_DOWNLOADS", serial }))
}

/** Request the backend to list available iOS Simulators. */
export const listIosSimulators = () => {
    if (wsConnection?.readyState !== WebSocket.OPEN) return
    iosSimulatorsLoading.value = true
    iosSimulatorsError.value = null
    iosSimulators.value = []
    wsConnection.send(JSON.stringify({ type: "LIST_IOS_SIMULATORS" }))
}

/** Boot a Shutdown iOS Simulator and bring Simulator.app to the foreground. */
export const bootIosSimulator = (udid) => {
    if (wsConnection?.readyState !== WebSocket.OPEN) return
    iosBootStatus.value = { ...iosBootStatus.value, [udid]: { state: 'booting', error: null } }
    wsConnection.send(JSON.stringify({ type: "BOOT_IOS_SIMULATOR", udid }))
}

/** Install the mitmproxy CA cert into a specific iOS Simulator. */
export const setupIosSimulator = (udid) => {
    if (wsConnection?.readyState !== WebSocket.OPEN) return
    iosSetupProgress.value.targetUdid = udid
    iosSetupProgress.value.show = true
    iosSetupProgress.value.error = null
    iosSetupProgress.value.steps.forEach(s => s.status = 'pending')
    wsConnection.send(JSON.stringify({ type: "SETUP_IOS_SIMULATOR", udid }))
}

/** Remove the mitmproxy CA cert from a specific iOS Simulator's trust store. */
export const revertIosSimulator = (udid) => {
    if (wsConnection?.readyState !== WebSocket.OPEN) return
    iosRevertProgress.value.targetUdid = udid
    iosRevertProgress.value.show = true
    iosRevertProgress.value.error = null
    iosRevertProgress.value.steps.forEach(s => s.status = 'pending')
    wsConnection.send(JSON.stringify({ type: "REVERT_IOS_SIMULATOR", udid }))
}

/** Ask the backend whether the mitmproxy CA is already trusted on this machine — if
 *  not, the CERT_TRUST_STATUS handler opens showCertTrustDialog. Only called when the
 *  OS proxy is turned on (see toggleMacProxy below) — that's the only point where
 *  OpenProxy actually knows this machine's own traffic is about to route through it.
 *  (macOS-only today, since that's the only platform with an OS-proxy toggle — a
 *  manually-configured browser proxy on any platform isn't detectable here either.) */
export const checkCertTrust = () => {
    if (wsConnection?.readyState !== WebSocket.OPEN) return
    wsConnection.send(JSON.stringify({ type: "CHECK_CERT_TRUST" }))
}

/**
 * Only these two warning-style dialogs (cert trust + unfiltered-traffic) can
 * both become relevant from the same "enable OS proxy" click, and only one
 * should ever be on screen at a time. Cert trust always wins — an untrusted
 * cert breaks HTTPS everywhere, which is more fundamental than an unfiltered
 * host list. This re-checks the condition fresh rather than caching a
 * "pending" decision, so it stays correct even if host filters changed while
 * the cert dialog was up.
 */
const maybeShowOsProxyWarning = () => {
    if (showCertTrustDialog.value) return
    if (macosProxyActive.value && proxyHostFilterMode.value === 'ignore' && proxyIgnoreHosts.value.length === 0) {
        showOsProxyWarning.value = true
    }
}

/** Close the cert-trust dialog, then let the (lower-priority) OS-proxy warning
 *  take its turn if it's still applicable. Use this instead of setting
 *  showCertTrustDialog directly so the two dialogs never overlap. */
export const dismissCertTrustDialog = () => {
    showCertTrustDialog.value = false
    maybeShowOsProxyWarning()
}

/**
 * Toggle the macOS system proxy. The backend prompts for the admin password
 * via osascript, so the user will see a native dialog before this resolves.
 */
export const toggleMacProxy = () => {
    if (macosProxyLoading.value) return
    if (wsConnection?.readyState !== WebSocket.OPEN) {
        macosProxyError.value = 'Backend not connected.'
        return
    }
    const enabling = !macosProxyActive.value
    macosProxyLoading.value = true
    macosProxyError.value = null
    wsConnection.send(JSON.stringify({
        type: enabling ? "SET_MAC_PROXY" : "UNSET_MAC_PROXY"
    }))
    // Enabling the OS proxy routes ALL Mac traffic through OpenProxy — if the cert
    // isn't trusted yet, that's the moment HTTPS everywhere would start breaking.
    if (enabling) checkCertTrust()
}

/**
 * Trust the mitmproxy CA on this machine's OS cert store (Chrome/Edge/curl on
 * macOS/Windows/Linux). May show a native admin prompt (macOS/Linux) the first
 * time; Windows writes to the per-user store so no elevation is needed there.
 */
export const trustCertOnThisMachine = () => {
    if (certTrustLoading.value) return
    if (wsConnection?.readyState !== WebSocket.OPEN) {
        certTrustError.value = 'Backend not connected.'
        return
    }
    certTrustLoading.value = true
    certTrustError.value = null
    wsConnection.send(JSON.stringify({ type: "TRUST_CERT" }))
}

// mitmproxy treats an empty allow_hosts (together with an empty ignore_hosts)
// as "no filter configured" and intercepts everything. That's the right
// default for "Intercept Everything" mode, but for "Selective Interception"
// with zero hosts added, the user expects nothing to be intercepted — so we
// send a sentinel regex that never matches any hostname, which makes
// mitmproxy's allow-list check fail for every host and pass all traffic
// through untouched.
const NEVER_MATCH_HOST = '(?!)'

const _sendProxyOptions = () => {
    if (wsConnection?.readyState === WebSocket.OPEN) {
        const mode = proxyHostFilterMode.value
        wsConnection.send(JSON.stringify({
            type: 'UPDATE_PROXY_OPTIONS',
            http2: proxyHttp2.value,
            upstream_cert: proxyUpstreamCert.value,
            ignore_hosts: mode === 'ignore' ? proxyIgnoreHosts.value : [],
            allow_hosts:  mode === 'allow'  ? (proxyAllowHosts.value.length ? proxyAllowHosts.value : [NEVER_MATCH_HOST]) : [],
        }))
    }
}

export const toggleProxyHttp2 = () => {
    proxyHttp2.value = !proxyHttp2.value
    saveState('proxyHttp2', proxyHttp2.value)
    _sendProxyOptions()
}

export const toggleProxyUpstreamCert = () => {
    proxyUpstreamCert.value = !proxyUpstreamCert.value
    saveState('proxyUpstreamCert', proxyUpstreamCert.value)
    _sendProxyOptions()
}

export const syncProxyIgnoreHosts = (hosts, mode) => {
    if (mode === 'allow') {
        proxyAllowHosts.value = hosts
        saveState('proxyAllowHosts', hosts)
    } else {
        proxyIgnoreHosts.value = hosts
        saveState('proxyIgnoreHosts', hosts)
    }
    if (mode !== undefined) {
        proxyHostFilterMode.value = mode
        saveState('proxyHostFilterMode', mode)
    }
    _sendProxyOptions()
}

export const setProxyHostFilterMode = (mode) => {
    proxyHostFilterMode.value = mode
    saveState('proxyHostFilterMode', mode)
    _sendProxyOptions()
}

export const exportHostFilter = async () => {
    const payload = {
        exportedAt: new Date().toISOString(),
        mode: proxyHostFilterMode.value,
        ignoreHosts: proxyIgnoreHosts.value,
        allowHosts: proxyAllowHosts.value,
    }
    const filename = `openproxy-host-filter-${new Date().toISOString().slice(0, 10)}.json`
    await window.electronAPI?.saveFile(filename, JSON.stringify(payload, null, 2))
}

export const importHostFilter = async () => {
    const filePath = await window.electronAPI?.selectFile({
        title: 'Import Host Filter',
        filters: [{ name: 'OpenProxy Host Filter', extensions: ['json'] }],
    })
    if (!filePath) return
    let payload
    try {
        const text = await fetch(`file://${filePath}`).then(r => r.text())
        payload = JSON.parse(text)
    } catch {
        alert('Failed to read host filter file. Make sure it is a valid OpenProxy JSON export.')
        return
    }
    if (payload.mode === 'ignore' || payload.mode === 'allow') {
        setProxyHostFilterMode(payload.mode)
    }
    if (Array.isArray(payload.ignoreHosts)) syncProxyIgnoreHosts(payload.ignoreHosts, 'ignore')
    if (Array.isArray(payload.allowHosts))  syncProxyIgnoreHosts(payload.allowHosts,  'allow')
}

export const applyAllHighlightRules = () => {
    requests.value.forEach(req => applyHighlightRules(req));
    requests.value = [...requests.value];
}

export const syncMapLocalRules = () => {
    if (wsConnection?.readyState === WebSocket.OPEN) {
        wsConnection.send(JSON.stringify({ type: "UPDATE_MAP_LOCAL_RULES", rules: mapLocalRules.value }))
    }
}

export const syncMapRemoteRules = () => {
    if (wsConnection?.readyState === WebSocket.OPEN) {
        wsConnection.send(JSON.stringify({ type: "UPDATE_MAP_REMOTE_RULES", rules: mapRemoteRules.value }))
    }
}

export const syncBreakpointRules = () => {
    if (wsConnection?.readyState === WebSocket.OPEN) {
        wsConnection.send(JSON.stringify({ type: "UPDATE_BREAKPOINT_RULES", rules: breakpointRules.value }))
    }
}

export const toggleRecording = () => {
    isRecording.value = !isRecording.value
    if (wsConnection?.readyState === WebSocket.OPEN) {
        wsConnection.send(JSON.stringify({ type: "TOGGLE_PROXY", is_recording: isRecording.value }))
    }
}

export const toggleSort = (key) => {
    if (sortKey.value === key) {
        sortOrder.value = sortOrder.value === 'asc' ? 'desc' : 'asc'
    } else {
        sortKey.value = key
        sortOrder.value = 'asc'
    }
}

export const repeatRequest = () => {
    if (wsConnection?.readyState === WebSocket.OPEN && contextMenu.value.request) {
        wsConnection.send(JSON.stringify({ type: "REPEAT_REQUEST", request: contextMenu.value.request }))
    }
}

export const openComposeModal = (req) => {
    let body = req.req_is_image ? '' : (req.req_body || '')
    if (body) {
        try { body = JSON.stringify(JSON.parse(body), null, 2) } catch (e) { /* not JSON, leave as-is */ }
    }
    composeData.value = {
        method: req.method,
        url: req.url,
        req_headers: JSON.stringify(req.req_headers || {}, null, 2),
        req_body: body
    }
    closeAllModals()
    showComposeModal.value = true
}

export const sendComposedRequest = () => {
    if (wsConnection?.readyState === WebSocket.OPEN && composeData.value) {
        let parsedHeaders = {}
        try { parsedHeaders = JSON.parse(composeData.value.req_headers) } catch (e) { }

        wsConnection.send(JSON.stringify({
            type: "REPEAT_REQUEST",
            request: {
                method: composeData.value.method,
                url: composeData.value.url,
                req_headers: parsedHeaders,
                req_body: composeData.value.req_body,
                req_is_image: false
            }
        }))
        showComposeModal.value = false
    }
}

export const resolveTrappedFlow = (action, flowId, modifiedData = null) => {
    if (wsConnection?.readyState !== WebSocket.OPEN) return
    const flowIndex = trappedFlows.value.findIndex(f => f.id === flowId)
    if (flowIndex === -1) return

    const flowToResolve = trappedFlows.value[flowIndex]
    wsConnection.send(JSON.stringify({
        type: "RESOLVE_BREAKPOINT",
        id: flowToResolve.id,
        phase: flowToResolve.phase,
        action: action,
        modified_data: modifiedData || flowToResolve
    }))
    trappedFlows.value.splice(flowIndex, 1)
}

export const closeContextMenu = () => contextMenu.value.show = false
export const setupAndroidEmulator = () => {
    if (wsConnection?.readyState === WebSocket.OPEN) wsConnection.send(JSON.stringify({ type: "SETUP_ANDROID" }))
}


// ============================================================================
// 5. COMPUTED PROPERTIES (Filtering)
// ============================================================================

// Map of ip -> resolved hostname, populated lazily via CLIENT_HOSTNAME_RESOLVED
export const clientHostnames = ref({})
// Map of ip -> user-set nickname
export const deviceNicknames = ref(loadState('deviceNicknames', {}))

function parseUserAgentDevice(ua) {
    if (!ua) return null
    if (/iPhone/i.test(ua)) return 'iPhone'
    if (/iPad/i.test(ua)) return 'iPad'
    if (/iPod/i.test(ua)) return 'iPod'
    const android = ua.match(/Android[^;]*;\s*([^)]+)\)/i)
    if (android) {
        // Try to extract device model from Android UA, e.g. "SM-G991B" or "Pixel 6"
        const model = android[1].trim()
        return model.length > 0 && model.length < 40 ? model : 'Android Device'
    }
    if (/Android/i.test(ua)) return 'Android Device'
    if (/Macintosh|Mac OS X/i.test(ua)) return 'Mac'
    if (/Windows/i.test(ua)) return 'Windows PC'
    if (/Linux/i.test(ua)) return 'Linux Device'
    return null
}

function deviceLabel(ip, uaDevice) {
    if (deviceNicknames.value[ip]) return deviceNicknames.value[ip]
    if (ip === '127.0.0.1' || ip === '::1') return 'Local System'
    const hostname = clientHostnames.value[ip]
    if (hostname) {
        return hostname.endsWith('.local') ? hostname.slice(0, -6) : hostname
    }
    if (uaDevice) return uaDevice
    return ip
}

export const deviceTrafficTree = computed(() => {
    const tree = {}         // ip -> Set of domains
    const uaMap = {}        // ip -> best UA device name found

    requests.value.forEach(req => {
        const ip = req.client_ip || 'Unknown Device'
        const domain = formatUrl(req.url).host

        if (!tree[ip]) tree[ip] = new Set()
        if (domain) tree[ip].add(domain)

        if (!uaMap[ip]) {
            const ua = req.req_headers?.['user-agent'] || req.req_headers?.['User-Agent']
            const name = parseUserAgentDevice(ua)
            if (name) uaMap[ip] = name
        }
    })

    return Object.keys(tree).sort().map(ip => ({
        ip: ip,
        label: deviceLabel(ip, uaMap[ip]),
        type: (ip === '127.0.0.1' || ip === '::1') ? 'local'
            : /^10\.\d+\.\d+\.\d+$/.test(ip) ? 'vpn'
            : 'wifi',
        domains: Array.from(tree[ip]).sort()
    }))
})

export const filteredRequests = computed(() => {
    let baseList = [...requests.value];

    if (isFocusMode.value) {
        if (pinnedSources.value.length === 0) return [];
        baseList = baseList.filter(req => {
            const urlLower = req.url.toLowerCase();
            return pinnedSources.value.some(pinned => urlLower.includes(pinned.toLowerCase()));
        });
    }

    if (activeFilter.value.type === 'device') {
        const targetIp = activeFilter.value.ip;
        baseList = baseList.filter(req => (req.client_ip || '127.0.0.1') === targetIp);
    }
    else if (activeFilter.value.type === 'device_domain') {
        const targetIp = activeFilter.value.ip;
        const targetDomain = activeFilter.value.domain;
        baseList = baseList.filter(req => {
            const reqIp = req.client_ip || '127.0.0.1';
            const reqDomain = formatUrl(req.url).host;
            return reqIp === targetIp && reqDomain === targetDomain;
        });
    }
    else if (activeFilter.value.type === 'pinned') {
        const pattern = activeFilter.value.domain.toLowerCase();
        baseList = baseList.filter(req => req.url.toLowerCase().includes(pattern));
    }

    if (searchQuery.value.trim() !== '') {
        const rawQuery = searchQuery.value.trim()
        const query = rawQuery.toLowerCase()
        const scope = searchScope.value
        const matchType = searchMatchType.value

        // Compile regex once outside the per-item loop
        let compiledRegex = null
        if (matchType === 'Match Regex' || matchType === 'Not Match Regex') {
            try { compiledRegex = new RegExp(rawQuery, 'i') } catch { compiledRegex = null }
        }

        const matchValue = (raw) => {
            const val = String(raw ?? '').toLowerCase()
            switch (matchType) {
                case 'Contains':        return val.includes(query)
                case 'Not Contains':    return !val.includes(query)
                case 'Starts With':     return val.startsWith(query)
                case 'Ends With':       return val.endsWith(query)
                case 'Equals':          return val === query
                case 'Not Equals':      return val !== query
                case 'Match Regex':     return compiledRegex ? compiledRegex.test(String(raw ?? '')) : false
                case 'Not Match Regex': return compiledRegex ? !compiledRegex.test(String(raw ?? '')) : true
                default:                return val.includes(query)
            }
        }

        const urlBase = (url) => {
            const i = url.indexOf('?')
            return i === -1 ? url : url.slice(0, i)
        }
        const queryStr = (url) => {
            const i = url.indexOf('?')
            return i === -1 ? '' : url.slice(i + 1)
        }
        const searchHeaders = (headers) => {
            if (!headers || typeof headers !== 'object') return false
            return Object.entries(headers).some(([k, v]) => matchValue(k) || matchValue(v))
        }

        baseList = baseList.filter(req => {
            switch (scope) {
                case 'URL':
                    return matchValue(urlBase(req.url))
                case 'Query String':
                    return matchValue(queryStr(req.url))
                case 'Request Header':
                    return searchHeaders(req.req_headers)
                case 'Response Header':
                    return searchHeaders(req.res_headers)
                case 'Request Body':
                    return matchValue(req.req_body)
                case 'Response Body':
                    return matchValue(req.res_body)
                case 'Method':
                    return matchValue(req.method)
                case 'Status Code':
                    return matchValue(req.status)
                default: { // 'All' — searches everything including bodies
                    const isNegative = matchType === 'Not Contains' || matchType === 'Not Equals' || matchType === 'Not Match Regex'
                    if (isNegative) {
                        return matchValue(urlBase(req.url)) &&
                            matchValue(queryStr(req.url)) &&
                            matchValue(req.method) &&
                            matchValue(req.status) &&
                            matchValue(req.req_body) &&
                            matchValue(req.res_body) &&
                            ((() => {
                                if (!req.req_headers || typeof req.req_headers !== 'object') return true
                                return Object.entries(req.req_headers).every(([k, v]) => matchValue(k) && matchValue(v))
                            })()) &&
                            ((() => {
                                if (!req.res_headers || typeof req.res_headers !== 'object') return true
                                return Object.entries(req.res_headers).every(([k, v]) => matchValue(k) && matchValue(v))
                            })())
                    }
                    return matchValue(urlBase(req.url)) ||
                        matchValue(queryStr(req.url)) ||
                        matchValue(req.method) ||
                        matchValue(req.status) ||
                        matchValue(req.req_body) ||
                        matchValue(req.res_body) ||
                        searchHeaders(req.req_headers) ||
                        searchHeaders(req.res_headers)
                }
            }
        })
    }

    if (activeChips.value.protocol !== 'All') {
        const p = activeChips.value.protocol;
        baseList = baseList.filter(req => {
            if (p === 'HTTP') return req.url.startsWith('http://');
            if (p === 'HTTPS') return req.url.startsWith('https://');
            if (p === 'WS') return req.status === 101 || req.url.startsWith('ws://') || req.url.startsWith('wss://');
            return true;
        });
    }

    if (activeChips.value.status !== 'All') {
        const prefix = activeChips.value.status.charAt(0);
        baseList = baseList.filter(req => {
            if (req.status === '...') return false;
            return String(req.status).startsWith(prefix);
        });
    }

    if (activeChips.value.type !== 'All') {
        const t = activeChips.value.type;
        baseList = baseList.filter(req => {
            const getCT = (headers) => {
                if (!headers) return '';
                const key = Object.keys(headers).find(k => k.toLowerCase() === 'content-type');
                return key ? headers[key].toLowerCase() : '';
            };
            const ct = getCT(req.res_headers) || getCT(req.req_headers);
            if (t === 'JSON') return ct.includes('json');
            if (t === 'Form') return ct.includes('form');
            if (t === 'XML') return ct.includes('xml');
            if (t === 'JS') return ct.includes('javascript');
            if (t === 'CSS') return ct.includes('css');
            if (t === 'GraphQL') return ct.includes('graphql') || req.url.toLowerCase().includes('graphql');
            if (t === 'Document') return ct.includes('html');
            if (t === 'Media') return ct.includes('image/') || ct.includes('audio/') || ct.includes('video/');
            return true;
        });
    }

    if (activeChips.value.starred) baseList = baseList.filter(req => req.starred);
    if (activeChips.value.color !== 'All') baseList = baseList.filter(req => req.color === activeChips.value.color);

    baseList.sort((a, b) => {
        let valA = a[sortKey.value]
        let valB = b[sortKey.value]
        if (typeof valA === 'string') valA = valA.toLowerCase()
        if (typeof valB === 'string') valB = valB.toLowerCase()
        if (valA < valB) return sortOrder.value === 'asc' ? -1 : 1
        if (valA > valB) return sortOrder.value === 'asc' ? 1 : -1
        return 0
    })

    return baseList;
})

// ============================================================================
// 6. WATCHERS (Auto-Saving & Python Syncing)
// ============================================================================

// Debounced: don't serialize up to 2000 requests on every tiny property change
let _saveRequestsTimer = null
watch(requests, () => {
    clearTimeout(_saveRequestsTimer)
    _saveRequestsTimer = setTimeout(() => {
        saveState('requests', requests.value.slice(0, MAX_SAVED_REQUESTS))
    }, 1500)
}, { deep: true })
watch(pinnedSources, (newVals) => saveState('pinnedSources', newVals), { deep: true })
watch(isFocusMode, (newVal) => saveState('isFocusMode', newVal))
watch(activeChips, (newVals) => saveState('activeChips', newVals), { deep: true })
watch(deviceNicknames, (val) => saveState('deviceNicknames', val), { deep: true })
watch(highlightRules, (val) => { saveState('highlightRules', val); applyAllHighlightRules() }, { deep: true })
watch(highlightsEnabled, (val) => { saveState('highlightsEnabled', val); applyAllHighlightRules() })
watch(() => highlightRules.value.length, (n, o) => {
    if (n === 1 && o === 0) highlightsEnabled.value = true
    else if (n === 0) highlightsEnabled.value = false
})

watch(wsMessages, (newVal) => {
    if (wsSaveTimeout) clearTimeout(wsSaveTimeout);
    wsSaveTimeout = setTimeout(() => {
        try {
            saveState('wsMessages', newVal);
        } catch (e) {
            console.warn("⚠️ LocalStorage is full! Could not save WS messages.");
        }
    }, 1000);
}, { deep: true })

watch(enableMapLocal, (val) => {
    saveState('enableMapLocal', val)
    if (wsConnection?.readyState === WebSocket.OPEN) {
        wsConnection.send(JSON.stringify({ type: "TOGGLE_MAP_LOCAL", enabled: val }))
    }
})

watch(() => mapLocalRules.value.length, (n, o) => {
    if (n === 1 && o === 0) enableMapLocal.value = true
    else if (n === 0) enableMapLocal.value = false
})

watch(mapLocalRules, (newVals) => {
    saveState('mapLocalRules', newVals)
    syncMapLocalRules()
}, { deep: true })

watch(enableMapRemote, (val) => {
    saveState('enableMapRemote', val)
    if (wsConnection?.readyState === WebSocket.OPEN) {
        wsConnection.send(JSON.stringify({ type: "TOGGLE_MAP_REMOTE", enabled: val }))
    }
})

watch(() => mapRemoteRules.value.length, (n, o) => {
    if (n === 1 && o === 0) enableMapRemote.value = true
    else if (n === 0) enableMapRemote.value = false
})

watch(mapRemoteRules, (newVals) => {
    saveState('mapRemoteRules', newVals)
    syncMapRemoteRules()
}, { deep: true })

watch(breakpointsEnabled, (newVal) => {
    saveState('breakpointsEnabled', newVal)
    if (wsConnection?.readyState === WebSocket.OPEN) {
        wsConnection.send(JSON.stringify({ type: "TOGGLE_BREAKPOINTS", enabled: newVal }))
    }
})

watch(() => breakpointRules.value.length, (n, o) => {
    if (n === 1 && o === 0) breakpointsEnabled.value = true
    else if (n === 0) breakpointsEnabled.value = false
})

watch(breakpointRules, (newVals) => {
    saveState('breakpointRules', newVals)
    syncBreakpointRules()
}, { deep: true })

watch(throttleProfile, (newVal) => {
    saveState('throttleProfile', newVal)
    if (wsConnection?.readyState === WebSocket.OPEN) {
        wsConnection.send(JSON.stringify({ type: "UPDATE_THROTTLE", profile: newVal }))
    }
})

watch(disableCache, (newVal) => {
    saveState('disableCache', newVal)
    if (wsConnection?.readyState === WebSocket.OPEN) {
        wsConnection.send(JSON.stringify({ type: "TOGGLE_CACHE", disable_cache: newVal }))
    }
})

watch(sortOrder, (newVal) => {
    saveState('sortOrder', newVal)
})

watch(toolbarVisibility, (val) => {
    saveState('toolbarVisibility', { ...val })
    window.electronAPI?.toolbarSyncToMain?.({ ...val })
}, { deep: true })


// ============================================================================
// 7. WEBSOCKET CONNECTION
// ============================================================================
let reconnectTimeout = null;
let reconnectDelay = 1000;

export const toggleWgMode = (enabled, port) => {
    if (wsConnection?.readyState !== WebSocket.OPEN) return
    wgEnabled.value = enabled
    wgStatus.value = 'starting'
    wsConnection.send(JSON.stringify({ type: "TOGGLE_WG_MODE", enabled, port: port || wgPort.value }))
}

export const requestWgConf = () => {
    if (wsConnection?.readyState !== WebSocket.OPEN) return
    wsConnection.send(JSON.stringify({ type: "GET_WG_CLIENT_CONF" }))
}

// Auto-update state
export const updateInfo     = ref(null)   // { version, current, download_url, release_url }
export const updateProgress = ref(null)   // 0-100 during download, null otherwise
export const updateError    = ref(null)
export const upToDate       = ref(false)  // true briefly after a check finds no update

export const checkForUpdates = () => {
    if (wsConnection?.readyState !== WebSocket.OPEN) return
    updateError.value = null
    upToDate.value = false
    wsConnection.send(JSON.stringify({ type: "CHECK_FOR_UPDATES" }))
}

export const applyUpdate = (downloadUrl) => {
    if (wsConnection?.readyState !== WebSocket.OPEN) return
    updateProgress.value = 0
    wsConnection.send(JSON.stringify({ type: "APPLY_UPDATE", download_url: downloadUrl }))
}

// ── Batched WS update flusher ─────────────────────────────────────────────────
// Collects NEW_REQUEST / UPDATE_REQUEST messages and applies them in one batch
// every 50ms max — reduces filteredRequests recomputes under heavy traffic.
let _pendingNew = []
let _pendingUpdate = []
let _batchTimer = null

function _flushBatch() {
    _batchTimer = null
    if (_pendingNew.length) {
        const toAdd = _pendingNew.reverse()   // newest-first
        _pendingNew = []
        toAdd.forEach(r => { applyHighlightRules(r); _knownRequestIds.add(String(r.id)) })
        requests.value.unshift(...toAdd)
        if (requests.value.length > MAX_LIVE_REQUESTS) requests.value.splice(MAX_LIVE_REQUESTS)
    }
    if (_pendingUpdate.length) {
        const updates = _pendingUpdate
        _pendingUpdate = []
        updates.forEach(data => {
            const idx = requests.value.findIndex(r => r.id === data.id)
            if (idx !== -1) Object.assign(requests.value[idx], data)
        })
    }
}

function _scheduleBatchFlush() {
    if (!_batchTimer) _batchTimer = setTimeout(_flushBatch, 50)
}

// Tracks every request id we've ever shown, so a WebSocket connection that's
// still streaming messages after "Clear All Traffic" doesn't get resurrected
// as a fake "[Missed Handshake]" row — only truly-never-seen ids get one.
const _knownRequestIds = new Set()

// Cancels any in-flight batched NEW_REQUEST/UPDATE_REQUEST payloads and wipes
// all traffic state. Used by the trash-icon "Clear All Traffic" action —
// mutating requests.value directly isn't enough because a batch flush
// scheduled just before the click can land right after and re-add the
// requests that were queued in that ~50ms window.
export const clearTraffic = () => {
    if (_batchTimer) { clearTimeout(_batchTimer); _batchTimer = null }
    _pendingNew = []
    _pendingUpdate = []
    requests.value = []
    wsMessages.value = {}
    selectedRequest.value = null
}

export const initWebSocket = () => {
    if (reconnectTimeout) {
        clearTimeout(reconnectTimeout);
        reconnectTimeout = null;
    }

    wsConnection = new WebSocket("ws://127.0.0.1:8765")

    wsConnection.onopen = () => {
        connectionStatus.value = '🟢 Intercepting Traffic'
        reconnectDelay = 1000;

        syncMapLocalRules()
        syncBreakpointRules()
        syncMapRemoteRules()
        wsConnection.send(JSON.stringify({ type: "UPDATE_THROTTLE", profile: throttleProfile.value }))
        wsConnection.send(JSON.stringify({ type: "TOGGLE_MAP_LOCAL", enabled: enableMapLocal.value }))
        wsConnection.send(JSON.stringify({ type: "TOGGLE_MAP_REMOTE", enabled: enableMapRemote.value }))
        wsConnection.send(JSON.stringify({ type: "TOGGLE_BREAKPOINTS", enabled: breakpointsEnabled.value }))
        wsConnection.send(JSON.stringify({ type: "TOGGLE_CACHE", disable_cache: disableCache.value }))
        _sendProxyOptions()
        if (wgEnabled.value) requestWgConf()
    }

    wsConnection.onmessage = (event) => {
        const payload = JSON.parse(event.data)

        if (payload.type === "SYSTEM_INFO") {
            proxyHost.value = `${payload.data.ip}:${payload.data.port}`
            if (payload.data.platform) platform.value = payload.data.platform
            if (typeof payload.data.mac_proxy_active === 'boolean') {
                macosProxyActive.value = payload.data.mac_proxy_active
            }
        }
        else if (payload.type === "ALERT") {
            alert(payload.message)
        }
        else if (payload.type === "NEW_REQUEST") {
            _pendingNew.push(payload.data)
            _scheduleBatchFlush()
        }
        else if (payload.type === "UPDATE_REQUEST") {
            _pendingUpdate.push(payload.data)
            _scheduleBatchFlush()
        }
        else if (payload.type === "BREAKPOINT_HIT") {
            const newFlow = payload.data
            newFlow.headersStr = JSON.stringify(newFlow.headers, null, 2)
            if (newFlow.url) newFlow.url = newFlow.url.replace(/\\\//g, '/')
            if (newFlow.body) {
                try {
                    newFlow.body = JSON.stringify(JSON.parse(newFlow.body), null, 2)
                } catch(e) {
                    newFlow.body = newFlow.body.replace(/\\\//g, '/')
                }
            }
            trappedFlows.value.push(newFlow)
        }

        else if (payload.type === "ADB_DEVICES") {
            adbDevicesLoading.value = false
            if (payload.error) {
                adbDevicesError.value = payload.error
                adbDevices.value = []
            } else {
                adbDevicesError.value = null
                adbDevices.value = payload.devices || []
            }
        }

        // ---- AVD list response (includes offline AVDs, like Android Studio) ----
        else if (payload.type === "AVD_LIST") {
            avdsLoading.value = false
            if (payload.error) {
                avdsError.value = payload.error
                avds.value = []
            } else {
                avdsError.value = null
                avds.value = payload.avds || []
            }
        }

        // ---- AVD boot progress ----
        else if (payload.type === "AVD_BOOT_PROGRESS") {
            const { name, status } = payload
            if (status === 'error') {
                avdBootStatus.value = { ...avdBootStatus.value, [name]: { state: 'error', error: payload.error } }
            } else if (status === 'success') {
                const next = { ...avdBootStatus.value }
                delete next[name]
                avdBootStatus.value = next
                listAvds()
                listAdbDevices()
            } else {
                // 'launching' | 'booting'
                avdBootStatus.value = { ...avdBootStatus.value, [name]: { state: status, error: null } }
            }
        }

        // ---- NEW: Live command log lines while pushing the cert ----
        else if (payload.type === "CERT_PUSH_LOG") {
            console.log('[CERT_PUSH_LOG]', payload)
            const prev = certPushStatus.value[payload.serial] || { state: 'pushing', error: null, logs: [] }
            certPushStatus.value = {
                ...certPushStatus.value,
                [payload.serial]: { ...prev, logs: [...(prev.logs || []), payload.message] }
            }
        }

        // ---- NEW: Result of pushing the cert to a device's Downloads folder ----
        else if (payload.type === "CERT_PUSHED") {
            console.log('[CERT_PUSHED]', payload)
            const prev = certPushStatus.value[payload.serial] || {}
            certPushStatus.value = {
                ...certPushStatus.value,
                [payload.serial]: payload.success
                    ? { state: 'success', path: payload.path, error: null, logs: payload.logs || prev.logs || [] }
                    : { state: 'error', error: payload.error || 'Push failed', logs: payload.logs || prev.logs || [] }
            }
        }

        // ---- NEW: Setup progress (now serial-scoped) ----
        else if (payload.type === "SETUP_PROGRESS") {
            if (payload.step === 'check_adb' && payload.status === 'start') {
                setupProgress.value.show = true
                setupProgress.value.error = null
                setupProgress.value.steps.forEach(s => s.status = 'pending')
            }
            if (payload.step === 'done') {
                setTimeout(() => { setupProgress.value.show = false }, 1500)
                return
            }

            // Handle skipped steps (e.g. root step for physical devices)
            if (payload.status === 'skip') {
                const step = setupProgress.value.steps.find(s => s.id === payload.step)
                if (step) step.status = 'skip'
                return
            }

            const step = setupProgress.value.steps.find(s => s.id === payload.step) ||
                setupProgress.value.steps.find(s => s.status === 'loading')

            if (step) {
                if (payload.status === 'start') step.status = 'loading'
                else if (payload.status === 'success') step.status = 'success'
                else if (payload.status === 'error') {
                    step.status = 'error'
                    setupProgress.value.error = payload.message
                }
            }
        }

        else if (payload.type === "REVERT_PROGRESS") {
            if (payload.step === 'clear_proxy' && payload.status === 'start') {
                revertProgress.value.show = true
                revertProgress.value.error = null
                revertProgress.value.steps.forEach(s => s.status = 'pending')
            }
            if (payload.step === 'done') {
                setTimeout(() => { revertProgress.value.show = false }, 1500)
                return
            }

            const step = revertProgress.value.steps.find(s => s.id === payload.step) ||
                revertProgress.value.steps.find(s => s.status === 'loading')

            if (step) {
                if (payload.status === 'start') step.status = 'loading'
                else if (payload.status === 'success') step.status = 'success'
                else if (payload.status === 'error') {
                    step.status = 'error'
                    revertProgress.value.error = payload.message
                }
            }
        }

        else if (payload.type === "IOS_SIMULATORS") {
            iosSimulatorsLoading.value = false
            if (payload.error) {
                iosSimulatorsError.value = payload.error
                iosSimulators.value = []
            } else {
                iosSimulatorsError.value = null
                iosSimulators.value = payload.simulators || []
            }
        }

        // ---- iOS Simulator: boot result ----
        else if (payload.type === "IOS_SIMULATOR_BOOTED") {
            if (payload.success) {
                iosBootStatus.value = { ...iosBootStatus.value, [payload.udid]: { state: 'success', error: null } }
                listIosSimulators()
            } else {
                iosBootStatus.value = { ...iosBootStatus.value, [payload.udid]: { state: 'error', error: payload.error } }
            }
        }

        // ---- iOS Simulator: install progress ----
        else if (payload.type === "IOS_SETUP_PROGRESS") {
            if (payload.step === 'check_xcrun' && payload.status === 'start') {
                iosSetupProgress.value.show = true
                iosSetupProgress.value.error = null
                iosSetupProgress.value.steps.forEach(s => s.status = 'pending')
            }
            if (payload.step === 'done') {
                setTimeout(() => { iosSetupProgress.value.show = false }, 1500)
                return
            }
            const iosSetupStep = iosSetupProgress.value.steps.find(s => s.id === payload.step) ||
                iosSetupProgress.value.steps.find(s => s.status === 'loading')
            if (iosSetupStep) {
                if (payload.status === 'start') iosSetupStep.status = 'loading'
                else if (payload.status === 'success') iosSetupStep.status = 'success'
                else if (payload.status === 'error') {
                    iosSetupStep.status = 'error'
                    iosSetupProgress.value.error = payload.message
                }
            }
        }

        else if (payload.type === "IOS_REVERT_PROGRESS") {
            if (payload.step === 'find_store' && payload.status === 'start') {
                iosRevertProgress.value.show = true
                iosRevertProgress.value.error = null
                iosRevertProgress.value.steps.forEach(s => s.status = 'pending')
            }
            if (payload.step === 'done') {
                setTimeout(() => { iosRevertProgress.value.show = false }, 1500)
                return
            }
            const iosRevertStep = iosRevertProgress.value.steps.find(s => s.id === payload.step) ||
                iosRevertProgress.value.steps.find(s => s.status === 'loading')
            if (iosRevertStep) {
                if (payload.status === 'start') iosRevertStep.status = 'loading'
                else if (payload.status === 'success') iosRevertStep.status = 'success'
                else if (payload.status === 'error') {
                    iosRevertStep.status = 'error'
                    iosRevertProgress.value.error = payload.message
                }
            }
        }

        else if (payload.type === "MACOS_PROXY_FIRST_TIME_SETUP") {
            macosProxyFirstTimeSetup.value = true
        }

        else if (payload.type === "MACOS_PROXY_STATUS") {
            const status = payload.data ?? payload
            macosProxyLoading.value = false
            macosProxyFirstTimeSetup.value = false
            macosProxyActive.value = status.active ?? false
            macosProxyServices.value = status.services ?? []
            if (status.error && status.error !== 'cancelled') {
                macosProxyError.value = status.error
            } else if (!status.error) {
                macosProxyError.value = null
            }
            // Warn if the OS proxy was just enabled while no host-filter is active
            // (mode is 'ignore' with an empty list means all traffic is intercepted).
            // Deferred if the cert-trust dialog is up — that's the higher-priority
            // issue (untrusted cert breaks everything, not just unfiltered traffic).
            maybeShowOsProxyWarning()
        }

        else if (payload.type === "CERT_TRUST_STATUS") {
            certTrustStatus.value = payload.trusted
            if (!payload.trusted) {
                showOsProxyWarning.value = false   // cert dialog takes priority — only one modal at a time
                showCertTrustDialog.value = true
            }
        }

        else if (payload.type === "CERT_TRUST_RESULT") {
            certTrustLoading.value = false
            certTrustStatus.value = payload.ok
            certTrustError.value = payload.ok || payload.error === 'cancelled' ? null : payload.error
            if (payload.ok) setTimeout(dismissCertTrustDialog, 1200)
        }

        else if (payload.type === 'WS_MESSAGE') {
            const reqId = String(payload.id);
            let parentReq = requests.value.find(r => String(r.id) === reqId);

            // Only fabricate a "[Missed Handshake]" placeholder the first time we
            // ever see this id. If it's already in _knownRequestIds, the parent
            // was intentionally removed (e.g. "Clear All Traffic") — don't let a
            // still-open WS connection resurrect it (or its message log) in the UI.
            if (!parentReq && _knownRequestIds.has(reqId)) {
                return;
            }

            if (!wsMessages.value[reqId]) {
                wsMessages.value[reqId] = [];
            }

            wsMessages.value[reqId].push({
                is_client: payload.is_client,
                content: payload.content,
                size: payload.size,
                time: payload.timestamp
            });

            if (!parentReq) {
                _knownRequestIds.add(reqId);
                parentReq = {
                    id: reqId,
                    method: payload.method || 'GET',
                    url: payload.url || 'wss://[Missed Handshake]',
                    status: 101,
                    time: payload.timestamp,
                    duration: 0,
                    req_bytes: 0,
                    res_bytes: 0,
                    req_headers: {},
                    res_headers: {},
                    req_body: '// Handshake intercepted mid-stream',
                    res_body: '// Handshake intercepted mid-stream',
                    req_is_image: false,
                    res_is_image: false,
                    has_ws: true,
                    ws_count: 0
                };
                requests.value.unshift(parentReq);
            }

            parentReq.has_ws = true;
            parentReq.ws_count = wsMessages.value[reqId].length;
            requests.value = [...requests.value];
        }
        else if (payload.type === 'WG_STATUS') {
            const d = payload.data
            wgStatus.value = d.status
            wgEnabled.value = d.enabled ?? wgEnabled.value
            if (d.config) wgClientConf.value = d.config
            else if (d.status === 'disabled' || d.status === 'error') wgClientConf.value = ''
            if (d.port) wgPort.value = d.port
            wgError.value = d.error || ''
        }
        else if (payload.type === 'UPDATE_AVAILABLE') {
            updateInfo.value = payload.data
            updateError.value = null
            upToDate.value = false
        }
        else if (payload.type === 'UP_TO_DATE') {
            upToDate.value = true
            setTimeout(() => { upToDate.value = false }, 4000)
        }
        else if (payload.type === 'UPDATE_CHECK_ERROR') {
            // A failed check (network error, rate limit, etc.) is NOT the
            // same as "you're up to date" — surface it so it isn't silently
            // mistaken for "no update available".
            updateError.value = payload.data?.error || 'Could not check for updates.'
            upToDate.value = false
        }
        else if (payload.type === 'UPDATE_PROGRESS') {
            updateProgress.value = payload.data.pct
        }
        else if (payload.type === 'UPDATE_READY') {
            updateProgress.value = null
            // Give the helper script a moment to start, then fully quit so it can replace the app
            setTimeout(() => window.electronAPI?.quit(), 500)
        }
        else if (payload.type === 'UPDATE_ERROR') {
            updateProgress.value = null
            updateError.value = payload.data.error
        }
        else if (payload.type === 'SCRIPTS_LIST') {
            scripts.value = payload.data.scripts ?? []
            // Auto-select first if selection is stale or empty
            const ids = scripts.value.map(s => s.id)
            if (!selectedScriptId.value || !ids.includes(selectedScriptId.value)) {
                selectedScriptId.value = ids[0] ?? null
            }
        }
        else if (payload.type === 'CLIENT_HOSTNAME_RESOLVED') {
            const { ip, hostname } = payload.data
            if (ip && hostname) {
                clientHostnames.value = { ...clientHostnames.value, [ip]: hostname }
            }
        }
    }

    wsConnection.onerror = () => {
        if (wsConnection.readyState === WebSocket.OPEN) {
            wsConnection.close();
        }
    }

    wsConnection.onclose = () => {
        connectionStatus.value = `🟡 Reconnecting in ${reconnectDelay / 1000}s...`

        reconnectTimeout = setTimeout(() => {
            initWebSocket()
        }, reconnectDelay)

        reconnectDelay = Math.min(reconnectDelay * 2, 10000)
    }
}

// ============================================================================
// 8. PREFERENCES RESET
// ============================================================================
export const resetPreferences = () => {
    Object.keys(localStorage)
        .filter(k => k.startsWith('openproxy_') || k === 'openproxy-theme')
        .forEach(k => localStorage.removeItem(k))
    localStorage.removeItem('openproxyOnboardingDone')
    localStorage.removeItem('openproxyOnboardingVersion')

    location.reload()
}

// ============================================================================
// 9. SETTINGS EXPORT / IMPORT
// ============================================================================

// Keys to skip — raw traffic data, not user configuration
const EXPORT_SKIP_KEYS = new Set(['requests', 'wsMessages'])

export const exportSettings = async () => {
    const settings = {}

    for (const storageKey of Object.keys(localStorage)) {
        if (storageKey === 'openproxy-theme') {
            settings.theme = localStorage.getItem(storageKey)
            continue
        }
        if (!storageKey.startsWith('openproxy_')) continue
        const key = storageKey.slice('openproxy_'.length)
        if (EXPORT_SKIP_KEYS.has(key)) continue
        try { settings[key] = JSON.parse(localStorage.getItem(storageKey)) }
        catch { settings[key] = localStorage.getItem(storageKey) }
    }

    // Onboarding flags use non-standard keys — handle explicitly
    if (localStorage.getItem('openproxyOnboardingDone')) settings.onboardingDone = true
    const _obv = localStorage.getItem('openproxyOnboardingVersion')
    if (_obv) settings.onboardingVersion = _obv

    // Include scripts from the backend (already loaded into reactive state)
    settings.scripts = scripts.value.map(({ id, name, content, enabled }) => ({ id, name, content, enabled }))

    const payload = {
        exportedAt: new Date().toISOString(),
        settings,
    }

    const filename = `openproxy-settings-${new Date().toISOString().slice(0, 10)}.json`
    await window.electronAPI?.saveFile(filename, JSON.stringify(payload, null, 2))
}

export const importSettings = async () => {
    const filePath = await window.electronAPI?.selectFile({
        title:   'Import Settings',
        filters: [{ name: 'OpenProxy Settings', extensions: ['json'] }],
    })
    if (!filePath) return

    let payload
    try {
        const text = await fetch(`file://${filePath}`).then(r => r.text())
        payload = JSON.parse(text)
    } catch {
        alert('Failed to read settings file. Make sure it is a valid OpenProxy JSON export.')
        return
    }

    const { settings } = payload
    if (!settings || typeof settings !== 'object') {
        alert('Invalid settings file: missing "settings" key.')
        return
    }

    const LS_KEYS = [
        'theme', 'toolbarVisibility', 'throttleProfile', 'disableCache',
        'isFocusMode', 'pinnedSources', 'activeChips', 'sortOrder',
        'mapLocalRules', 'enableMapLocal',
        'mapRemoteRules', 'enableMapRemote',
        'breakpointRules', 'breakpointsEnabled',
        'highlightRules', 'highlightsEnabled',
        'proxyIgnoreHosts', 'proxyAllowHosts', 'proxyHostFilterMode',
        'proxyHttp2', 'proxyUpstreamCert',
        'deviceNicknames',
    ]
    for (const key of LS_KEYS) {
        if (!(key in settings)) continue
        if (key === 'theme') {
            localStorage.setItem('openproxy-theme', settings.theme)
        } else {
            localStorage.setItem(`openproxy_${key}`, JSON.stringify(settings[key]))
        }
    }

    // Onboarding flag (legacy key kept for compatibility; version key takes precedence)
    if (settings.onboardingDone) localStorage.setItem('openproxyOnboardingDone', '1')
    if (settings.onboardingVersion) localStorage.setItem('openproxyOnboardingVersion', settings.onboardingVersion)

    // Restore scripts via WebSocket so the Python backend persists them
    if (Array.isArray(settings.scripts) && wsConnection?.readyState === WebSocket.OPEN) {
        wsConnection.send(JSON.stringify({ type: 'SCRIPTS_IMPORT', scripts: settings.scripts }))
    }

    location.reload()
}