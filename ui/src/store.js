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

    if (window.pywebview && window.pywebview.api) {
        window.pywebview.api.save_file(filename + '.json', jsonString)
            .then((success) => {
                if (!success) console.log("Export canceled by user.");
            })
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
export const sortKey = ref('time')
export const sortOrder = ref('desc')

export const activeChips = ref(loadState('activeChips', {
    protocol: 'All', type: 'All', status: 'All', color: 'All', starred: false
}))

export const throttleProfile = ref(loadState('throttleProfile', 'None'))
export const disableCache = ref(loadState('disableCache', false))

// Map Local
export const showMapModal = ref(false)
export const enableMapLocal = ref(loadState('enableMapLocal', true))
export const mapLocalRules = ref(loadState('mapLocalRules', []))
export const selectedRuleId = ref(null)

// Map Remote
export const showMapRemoteModal = ref(false)
export const enableMapRemote = ref(loadState('enableMapRemote', true))
export const mapRemoteRules = ref(loadState('mapRemoteRules', []))
export const selectedMapRemoteId = ref(null)

// Breakpoints
export const showBreakpointModal = ref(false)
export const breakpointsEnabled = ref(loadState('breakpointsEnabled', true))
export const breakpointRules = ref(loadState('breakpointRules', []))
export const trappedFlows = ref([])
export const selectedBreakpointId = ref(null)

// Auto-Highlights
export const showHighlightModal = ref(false)
export const highlightsEnabled = ref(loadState('highlightsEnabled', true))
export const highlightRules = ref(loadState('highlightRules', []))

// Compose
export const showComposeModal = ref(false)
export const composeData = ref(null)

// Device Setup Modal
export const showDeviceSetupModal = ref(false)
export const deviceSetupType = ref('emulator')

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
            if (rule.type === 'url' && req.url.includes(rule.pattern)) isMatch = true;
            if (rule.type === 'status' && String(req.status) === String(rule.pattern)) isMatch = true;
            if (rule.type === 'method' && req.method.toUpperCase() === rule.pattern.toUpperCase()) isMatch = true;
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
        const query = searchQuery.value.toLowerCase();
        baseList = baseList.filter(req => {
            return req.url.toLowerCase().includes(query) ||
                req.method.toLowerCase().includes(query) ||
                String(req.status).includes(query);
        });
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
watch(requests, (newVals) => saveState('requests', newVals.slice(0, MAX_SAVED_REQUESTS)), { deep: true })
watch(pinnedSources, (newVals) => saveState('pinnedSources', newVals), { deep: true })
watch(isFocusMode, (newVal) => saveState('isFocusMode', newVal))
watch(activeChips, (newVals) => saveState('activeChips', newVals), { deep: true })
watch(highlightRules, (val) => saveState('highlightRules', val), { deep: true })
watch(highlightsEnabled, (val) => saveState('highlightsEnabled', val))

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


// ============================================================================
// 7. WEBSOCKET CONNECTION
// ============================================================================
let reconnectTimeout = null;
let reconnectDelay = 1000;

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
    }

    wsConnection.onmessage = (event) => {
        const payload = JSON.parse(event.data)

        if (payload.type === "SYSTEM_INFO") {
            proxyHost.value = `${payload.data.ip}:${payload.data.port}`
        }
        else if (payload.type === "ALERT") {
            alert(payload.message)
        }
        else if (payload.type === "NEW_REQUEST") {
            applyHighlightRules(payload.data)
            requests.value.unshift(payload.data)
            if (requests.value.length > MAX_LIVE_REQUESTS) requests.value.pop()
        }
        else if (payload.type === "UPDATE_REQUEST") {
            const reqIndex = requests.value.findIndex(r => r.id === payload.data.id)
            if (reqIndex !== -1) Object.assign(requests.value[reqIndex], payload.data)
        }
        else if (payload.type === "BREAKPOINT_HIT") {
            const newFlow = payload.data
            newFlow.headersStr = JSON.stringify(newFlow.headers, null, 2)
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
            macosProxyLoading.value = false
            macosProxyActive.value = payload.active ?? false
            macosProxyServices.value = payload.services ?? []
            if (payload.error && payload.error !== 'cancelled') {
                macosProxyError.value = payload.error
            } else if (!payload.error) {
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