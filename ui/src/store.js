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
export const sortOrder = ref('desc')

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
// OS Proxy toggle is darwin-only today; visibility flag still respected so it can be hidden when irrelevant
export const showOsProxyBtn     = computed(() => toolbarVisibility.value.osProxy && platform.value === 'darwin')

// Opens DeviceSetupModal directly on the VPN Mode view
export const openVpnMode = () => {
    deviceSetupType.value = 'vpn_mode'
    showDeviceSetupModal.value = true
}

// ---- NEW: ADB device state ----
// List of { serial, model, type, state } objects returned by the backend
export const adbDevices = ref([])
// Whether a LIST_ADB_DEVICES fetch is in-flight
export const adbDevicesLoading = ref(false)
// Any error string returned from the backend for device listing
export const adbDevicesError = ref(null)

export const setupProgress = ref({
    show: false,
    error: null,
    // 'setup' or 'revert' — controls which title/copy to show
    mode: 'setup',
    // Which device serial the current progress applies to
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
export const macosProxyActive = ref(false)
export const macosProxyLoading = ref(false)
export const macosProxyError = ref(null)
export const macosProxyServices = ref([])


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
            }
        } catch (e) { continue; }

        if (isMatch) {
            req.color = rule.color;
            break;
        }
    }
}

/** Request the backend to scan for connected ADB devices. */
export const listAdbDevices = () => {
    if (wsConnection?.readyState !== WebSocket.OPEN) return
    adbDevicesLoading.value = true
    adbDevicesError.value = null
    adbDevices.value = []
    wsConnection.send(JSON.stringify({ type: "LIST_ADB_DEVICES" }))
}

/**
 * Kick off the certificate install + proxy setup on a specific device.
 * @param {string} serial  - ADB device serial, e.g. "emulator-5554" or "R58M31XXXXX"
 * @param {string} deviceType - "emulator" | "device"
 */
export const setupAndroidDevice = (serial, deviceType) => {
    if (wsConnection?.readyState !== WebSocket.OPEN) return

    // Reset & show the progress panel
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

/**
 * Revert the proxy config and remove the cert from a specific device.
 * @param {string} serial - ADB device serial
 */
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

/** Request the backend to list available iOS Simulators. */
export const listIosSimulators = () => {
    if (wsConnection?.readyState !== WebSocket.OPEN) return
    iosSimulatorsLoading.value = true
    iosSimulatorsError.value = null
    iosSimulators.value = []
    wsConnection.send(JSON.stringify({ type: "LIST_IOS_SIMULATORS" }))
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
    macosProxyLoading.value = true
    macosProxyError.value = null
    wsConnection.send(JSON.stringify({
        type: macosProxyActive.value ? "UNSET_MAC_PROXY" : "SET_MAC_PROXY"
    }))
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
    composeData.value = {
        method: req.method,
        url: req.url,
        req_headers: JSON.stringify(req.req_headers || {}, null, 2),
        req_body: req.req_is_image ? '' : (req.req_body || '')
    }
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
export const deviceTrafficTree = computed(() => {
    const tree = {}

    requests.value.forEach(req => {
        const ip = req.client_ip || 'Unknown Device'
        const domain = formatUrl(req.url).host

        if (!tree[ip]) {
            tree[ip] = new Set()
        }
        if (domain) {
            tree[ip].add(domain)
        }
    })

    return Object.keys(tree).sort().map(ip => ({
        ip: ip,
        label: ip === '127.0.0.1' ? 'Local System' : ip,
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
        toAdd.forEach(r => applyHighlightRules(r))
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

        // ---- NEW: ADB device list response ----
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

        // ---- NEW: Revert progress ----
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

        // ---- iOS Simulator: device list ----
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

        // ---- iOS Simulator: revert progress ----
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

        else if (payload.type === "MACOS_PROXY_STATUS") {
            const status = payload.data ?? payload
            macosProxyLoading.value = false
            macosProxyActive.value = status.active ?? false
            macosProxyServices.value = status.services ?? []
            if (status.error && status.error !== 'cancelled') {
                macosProxyError.value = status.error
            } else if (!status.error) {
                macosProxyError.value = null
            }
        }

        else if (payload.type === 'WS_MESSAGE') {
            const reqId = String(payload.id);

            if (!wsMessages.value[reqId]) {
                wsMessages.value[reqId] = [];
            }

            wsMessages.value[reqId].push({
                is_client: payload.is_client,
                content: payload.content,
                size: payload.size,
                time: payload.timestamp
            });

            let parentReq = requests.value.find(r => String(r.id) === reqId);

            if (!parentReq) {
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
    // Clear all openproxy_* keys
    Object.keys(localStorage)
        .filter(k => k.startsWith('openproxy_') || k === 'openproxy-theme')
        .forEach(k => localStorage.removeItem(k))

    location.reload()
}

// ============================================================================
// 9. SETTINGS EXPORT
// ============================================================================

// Keys to skip — raw traffic data, not user configuration
const EXPORT_SKIP_KEYS = new Set(['requests', 'wsMessages'])

export const exportSettings = async () => {
    const settings = {}

    // Collect all openproxy_* keys (skip traffic)
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

    // Include scripts from the backend (already loaded into reactive state)
    settings.scripts = scripts.value.map(({ id, name, content, enabled }) => ({ id, name, content, enabled }))

    const payload = {
        exportedAt: new Date().toISOString(),
        settings,
    }

    const filename = `openproxy-settings-${new Date().toISOString().slice(0, 10)}.json`
    await window.electronAPI?.saveFile(filename, JSON.stringify(payload, null, 2))
}