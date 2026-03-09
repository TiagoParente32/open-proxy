import { ref, computed, watch } from 'vue'

// --- LOCAL STORAGE HELPERS ---
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

// Lowered limit so LocalStorage doesn't hit its 5MB Quota
const MAX_LIVE_REQUESTS = 2000;
const MAX_SAVED_REQUESTS = 500;

// --- 1. CORE PROXY STATE ---
export const requests = ref(loadState('requests', []))
export const connectionStatus = ref('Connecting...')
export const isRecording = ref(true)
export const proxyHost = ref('127.0.0.1:8080')
export let wsConnection = null

// --- 2. UI SELECTION STATE ---
export const selectedRequest = ref(null)
export const activeReqTab = ref('Header')
export const activeResTab = ref('Body')

// --- 3. FOCUS MODE & SOURCES STATE ---
export const isFocusMode = ref(loadState('isFocusMode', false))
export const pinnedSources = ref(loadState('pinnedSources', []))
export const activeFilter = ref({ type: 'all', value: null })
export const searchQuery = ref('')
export const sortKey = ref('time')
export const sortOrder = ref('desc')

export const showBreakpointModal = ref(false)
export const breakpointRules = ref(loadState('breakpointRules', []))
export const trappedFlows = ref([]) // <--- CHANGED TO AN ARRAY
export const selectedBreakpointId = ref(null)
export const breakpointsEnabled = ref(loadState('breakpointsEnabled', true)) // <--- MASTER TOGGLE

export const enableMapLocal = ref(loadState('enableMapLocal', true))
export const enableMapRemote = ref(loadState('enableMapRemote', true))


export const exportRules = (rules, filename) => {
    // 1. Get the actual array data
    const data = rules.value !== undefined ? rules.value : rules;

    // 2. Convert it to a formatted JSON string
    const jsonString = JSON.stringify(data, null, 2);

    // 3. Send it to Python to trigger the native OS Save Dialog
    if (wsConnection?.readyState === WebSocket.OPEN) {
        wsConnection.send(JSON.stringify({
            type: "EXPORT_FILE",
            filename: filename + ".json",
            data: jsonString
        }));
    } else {
        alert("Backend connection lost. Cannot export right now.");
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
                // Handle both Ref and unwrapped reactive arrays
                if (rulesRef.value !== undefined) {
                    rulesRef.value = [...rulesRef.value, ...importedRules];
                } else {
                    rulesRef.push(...importedRules); // Mutate in place if unwrapped
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

watch(enableMapLocal, (val) => {
    saveState('enableMapLocal', val)
    if (wsConnection?.readyState === WebSocket.OPEN) {
        wsConnection.send(JSON.stringify({ type: "TOGGLE_MAP_LOCAL", enabled: val }))
    }
})

watch(enableMapRemote, (val) => {
    saveState('enableMapRemote', val)
    if (wsConnection?.readyState === WebSocket.OPEN) {
        wsConnection.send(JSON.stringify({ type: "TOGGLE_MAP_REMOTE", enabled: val }))
    }
})


// --- CHIP FILTERS STATE ---
export const activeChips = ref(loadState('activeChips', {
    protocol: 'All',
    type: 'All',
    status: 'All',
    starred: false
}))

watch(activeChips, (newVals) => {
    saveState('activeChips', newVals)
}, { deep: true })

// --- NETWORK THROTTLING STATE ---
export const throttleProfile = ref(loadState('throttleProfile', 'None'))

watch(throttleProfile, (newVal) => {
    saveState('throttleProfile', newVal)
    if (wsConnection?.readyState === WebSocket.OPEN) {
        wsConnection.send(JSON.stringify({ type: "UPDATE_THROTTLE", profile: newVal }))
    }
})

// --- MAP REMOTE STATE ---
export const showMapRemoteModal = ref(false)
export const mapRemoteRules = ref(loadState('mapRemoteRules', []))
export const selectedMapRemoteId = ref(null)

watch(mapRemoteRules, (newVals) => {
    saveState('mapRemoteRules', newVals)
    syncMapRemoteRules()
}, { deep: true })

export const syncMapRemoteRules = () => {
    if (wsConnection?.readyState === WebSocket.OPEN) {
        wsConnection.send(JSON.stringify({ type: "UPDATE_MAP_REMOTE_RULES", rules: mapRemoteRules.value }))
    }
}

export const showComposeModal = ref(false)
export const composeData = ref(null)

export const openComposeModal = (req) => {
    // Make a copy of the request so we don't accidentally edit the one in the table!
    composeData.value = {
        method: req.method,
        url: req.url,
        // Format headers as a pretty JSON string for the editor
        req_headers: JSON.stringify(req.req_headers || {}, null, 2),
        // If it was an image, clear the body text, otherwise load it
        req_body: req.req_is_image ? '' : (req.req_body || '')
    }
    showComposeModal.value = true
}

export const sendComposedRequest = () => {
    if (wsConnection?.readyState === WebSocket.OPEN && composeData.value) {

        // Convert the stringified headers back into a real JavaScript object
        let parsedHeaders = {}
        try { parsedHeaders = JSON.parse(composeData.value.req_headers) } catch (e) { }

        // Send the EXACT same message type we used for the standard repeat!
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

        showComposeModal.value = false // Close the modal
    }
}

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

export const syncBreakpointRules = () => {
    if (wsConnection?.readyState === WebSocket.OPEN) {
        wsConnection.send(JSON.stringify({ type: "UPDATE_BREAKPOINT_RULES", rules: breakpointRules.value }))
    }
}

// --- Update resolveTrappedFlow to handle the queue ---
export const resolveTrappedFlow = (action, flowId, modifiedData = null) => {
    if (wsConnection?.readyState !== WebSocket.OPEN) return

    // Find the flow in our queue
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

    // Remove it from the queue so the UI shows the next one!
    trappedFlows.value.splice(flowIndex, 1)
}

export const toggleSort = (key) => {
    if (sortKey.value === key) {
        sortOrder.value = sortOrder.value === 'asc' ? 'desc' : 'asc'
    } else {
        sortKey.value = key
        sortOrder.value = 'asc'
    }
}

export const disableCache = ref(loadState('disableCache', false))

watch(disableCache, (newVal) => {
    saveState('disableCache', newVal)
    if (wsConnection?.readyState === WebSocket.OPEN) {
        wsConnection.send(JSON.stringify({ type: "TOGGLE_CACHE", disable_cache: newVal }))
    }
})

// --- 4. MAP LOCAL STATE ---
export const showMapModal = ref(false)
export const mapLocalRules = ref(loadState('mapLocalRules', []))
export const selectedRuleId = ref(null)

// --- 5. CONTEXT MENU STATE ---
export const contextMenu = ref({ show: false, x: 0, y: 0, request: null })

// --- NEW: AUTOSAVE WATCHERS ---
// Anytime these variables change, Vue automatically saves them to localStorage!
watch(requests, (newVals) => saveState('requests', newVals.slice(0, MAX_SAVED_REQUESTS)), { deep: true })
watch(pinnedSources, (newVals) => saveState('pinnedSources', newVals), { deep: true })
watch(isFocusMode, (newVal) => saveState('isFocusMode', newVal))
watch(mapLocalRules, (newVals) => {
    saveState('mapLocalRules', newVals)
    syncMapLocalRules() // Instantly tell Python about rule changes
}, { deep: true })


// --- HELPER: FORMATTERS ---
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

// --- COMPUTED: FILTERING LOGIC ---
export const unpinnedDomains = computed(() => {
    const domains = new Set()
    requests.value.forEach(req => {
        const host = formatUrl(req.url).host
        if (host && !pinnedSources.value.some(p => host.toLowerCase().includes(p.toLowerCase()))) {
            domains.add(host)
        }
    })
    return Array.from(domains).sort()
})

export const filteredRequests = computed(() => {
    let baseList = [...requests.value]; // Copy array so sorting doesn't mutate original state

    if (isFocusMode.value) {
        if (pinnedSources.value.length === 0) return [];
        baseList = baseList.filter(req => {
            const urlLower = req.url.toLowerCase();
            return pinnedSources.value.some(pinned => urlLower.includes(pinned.toLowerCase()));
        });
    }

    if (activeFilter.value.type !== 'all') {
        if (['pinned', 'unpinned'].includes(activeFilter.value.type)) {
            const pattern = activeFilter.value.value.toLowerCase();
            baseList = baseList.filter(req => req.url.toLowerCase().includes(pattern));
        }
    }

    if (searchQuery.value.trim() !== '') {
        const query = searchQuery.value.toLowerCase();
        baseList = baseList.filter(req => {
            return req.url.toLowerCase().includes(query) ||
                req.method.toLowerCase().includes(query) ||
                String(req.status).includes(query);
        });
    }
    // 1. PROTOCOL FILTER
    if (activeChips.value.protocol !== 'All') {
        const p = activeChips.value.protocol;
        baseList = baseList.filter(req => {
            if (p === 'HTTP') return req.url.startsWith('http://');
            if (p === 'HTTPS') return req.url.startsWith('https://');
            if (p === 'WS') return req.url.startsWith('ws://') || req.url.startsWith('wss://');
            return true;
        });
    }

    // 2. STATUS CODE FILTER
    if (activeChips.value.status !== 'All') {
        const prefix = activeChips.value.status.charAt(0); // Gets '2' from '2xx'
        baseList = baseList.filter(req => {
            if (req.status === '...') return false; // Hide pending requests when filtering by status
            return String(req.status).startsWith(prefix);
        });
    }

    // 3. CONTENT TYPE FILTER
    if (activeChips.value.type !== 'All') {
        const t = activeChips.value.type;
        baseList = baseList.filter(req => {
            // Helper to safely grab the Content-Type header (ignoring case)
            const getCT = (headers) => {
                if (!headers) return '';
                const key = Object.keys(headers).find(k => k.toLowerCase() === 'content-type');
                return key ? headers[key].toLowerCase() : '';
            };

            // Check Response headers first, fallback to Request headers
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

    if (activeChips.value.starred) {
        baseList = baseList.filter(req => req.starred);
    }

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

// --- ACTIONS: WEBSOCKET & STATE MUTATION ---
export const initWebSocket = () => {
    wsConnection = new WebSocket("ws://127.0.0.1:8765")

    wsConnection.onopen = () => {
        connectionStatus.value = '🟢 Intercepting Traffic'
        syncMapLocalRules() // Send the loaded rules to python immediately on boot!
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
            requests.value.unshift(payload.data)
            // NEW: Let the live UI hold up to 2000 requests!
            if (requests.value.length > MAX_LIVE_REQUESTS) requests.value.pop()
        } else if (payload.type === "UPDATE_REQUEST") {
            const reqIndex = requests.value.findIndex(r => r.id === payload.data.id)
            if (reqIndex !== -1) Object.assign(requests.value[reqIndex], payload.data)
        }
        else if (payload.type === "BREAKPOINT_HIT") {
            // Push it to the queue instead of overwriting!
            const newFlow = payload.data
            newFlow.headersStr = JSON.stringify(newFlow.headers, null, 2)
            trappedFlows.value.push(newFlow)
        }
    }
    wsConnection.onclose = () => { connectionStatus.value = '🔴 Disconnected' }
}

export const toggleRecording = () => {
    isRecording.value = !isRecording.value
    if (wsConnection?.readyState === WebSocket.OPEN) {
        wsConnection.send(JSON.stringify({ type: "TOGGLE_PROXY", is_recording: isRecording.value }))
    }
}

export const repeatRequest = () => {
    if (wsConnection?.readyState === WebSocket.OPEN && contextMenu.value.request) {
        wsConnection.send(JSON.stringify({
            type: "REPEAT_REQUEST",
            request: contextMenu.value.request
        }))
    }
}

export const syncMapLocalRules = () => {
    if (wsConnection?.readyState === WebSocket.OPEN) {
        wsConnection.send(JSON.stringify({ type: "UPDATE_MAP_LOCAL_RULES", rules: mapLocalRules.value }))
    }
}

export const closeContextMenu = () => {
    contextMenu.value.show = false
}

export const setupAndroidEmulator = () => {
    if (wsConnection?.readyState === WebSocket.OPEN) {
        wsConnection.send(JSON.stringify({ type: "SETUP_ANDROID" }))
    }
}