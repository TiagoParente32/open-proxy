<script setup>
import { computed, ref, watch } from 'vue'
import { Codemirror } from 'vue-codemirror'
import { json } from '@codemirror/lang-json'
import { cmTheme } from '../composables/useTheme'
import { EditorView } from '@codemirror/view'
import CodeMirrorEditor from './CodeMirrorEditor.vue'
import { useEdgeResize } from '../composables/useEdgeResize'

import {
  showMapModal,
  mapLocalRules,
  selectedRuleId,
  syncMapLocalRules,
  enableMapLocal,
  importRules,
  exportRules
} from '../store.js'

// --- 1. CORE REFS & COMPUTEDS ---
const modalRef = ref(null)
const { modalStyle, startResize } = useEdgeResize(modalRef, { minW: 600, minH: 420 })
const extensions = computed(() => [json(), ...cmTheme.value, EditorView.lineWrapping])
const activeRule = computed(() => mapLocalRules.value.find(r => r.id === selectedRuleId.value))
const activeTab = ref('Body')
const queryParams = ref([{ key: '', value: '' }])
const responseHeaders = ref([{ key: '', value: '' }])
const reqHeadersMod = ref([{ key: '', value: '' }])
const showMethodMenu = ref(false)

const selectMethod = (m) => {
  if (activeRule.value) activeRule.value.method = m
  showMethodMenu.value = false
  syncMapLocalRules()
}

// --- 2. PARAMETER SYNC LOGIC (Defined first to avoid init errors) ---

// URL/PATTERN -> GRID
const syncPatternToParams = () => {
  if (!activeRule.value) return

  const url = activeRule.value.pattern || ''
  const parts = url.split('?')
  const newParams = []

  if (parts.length > 1 && parts[1]) {
    const pairs = parts[1].split('&')

    pairs.forEach(pair => {
      // Hardened split: only splits on the first '=' to protect base64 values
      const eqIndex = pair.indexOf('=')
      
      if (eqIndex !== -1) {
        const k = pair.slice(0, eqIndex)
        const v = pair.slice(eqIndex + 1)
        newParams.push({
          key: decodeURIComponent(k),
          value: decodeURIComponent(v)
        })
      } else if (pair) {
        newParams.push({
          key: decodeURIComponent(pair),
          value: ''
        })
      }
    })
  }

  // Always keep one empty row at the bottom for easy typing
  newParams.push({ key: '', value: '' })
  queryParams.value = newParams
}

// GRID -> URL/PATTERN
const syncParamsToPattern = () => {
  if (!activeRule.value) return

  let base = activeRule.value.pattern.split('?')[0] || ''
  const params = []

  queryParams.value.forEach(p => {
    if (p.key) {
      params.push(`${encodeURIComponent(p.key)}=${encodeURIComponent(p.value)}`)
    }
  })

  if (params.length > 0) {
    activeRule.value.pattern = `${base}?${params.join('&')}`
  } else {
    activeRule.value.pattern = base
  }
}

const checkParamRow = (index) => {
  if (index === queryParams.value.length - 1 && queryParams.value[index].key !== '') {
    queryParams.value.push({ key: '', value: '' })
  }
}

const removeParamRow = (index) => {
  queryParams.value.splice(index, 1)

  if (queryParams.value.length === 0) {
    queryParams.value.push({ key: '', value: '' })
  }

  syncParamsToPattern()
}

// HEADERS JSON -> GRID
const syncRuleToHeaders = () => {
  if (!activeRule.value) return

  const newHeaders = []
  try {
    const parsed = JSON.parse(activeRule.value.headers || '{}')
    for (const [k, v] of Object.entries(parsed)) {
      newHeaders.push({ key: k, value: String(v) })
    }
  } catch (e) {
    // If JSON is invalid, keep current grid as-is
  }

  newHeaders.push({ key: '', value: '' })
  responseHeaders.value = newHeaders
}

// GRID -> HEADERS JSON
const syncHeadersToRule = () => {
  if (!activeRule.value) return

  const obj = {}
  responseHeaders.value.forEach(h => {
    if (h.key.trim()) obj[h.key.trim()] = h.value
  })
  activeRule.value.headers = JSON.stringify(obj, null, 2)
}

const checkHeaderRow = (index) => {
  if (index === responseHeaders.value.length - 1 && responseHeaders.value[index].key !== '') {
    responseHeaders.value.push({ key: '', value: '' })
  }
}

const removeHeaderRow = (index) => {
  responseHeaders.value.splice(index, 1)

  if (responseHeaders.value.length === 0) {
    responseHeaders.value.push({ key: '', value: '' })
  }

  syncHeadersToRule()
}

// REQ_HEADERS_MOD OBJECT -> GRID
const syncRuleToReqHeaders = () => {
  if (!activeRule.value) return

  const newHeaders = []
  const mod = activeRule.value.req_headers_mod
  if (mod && typeof mod === 'object') {
    for (const [k, v] of Object.entries(mod)) {
      newHeaders.push({ key: k, value: String(v) })
    }
  }

  newHeaders.push({ key: '', value: '' })
  reqHeadersMod.value = newHeaders
}

// GRID -> REQ_HEADERS_MOD OBJECT
const syncReqHeadersToRule = () => {
  if (!activeRule.value) return

  const obj = {}
  reqHeadersMod.value.forEach(h => {
    if (h.key.trim()) obj[h.key.trim()] = h.value
  })
  activeRule.value.req_headers_mod = obj
}

const checkReqHeaderRow = (index) => {
  if (index === reqHeadersMod.value.length - 1 && reqHeadersMod.value[index].key !== '') {
    reqHeadersMod.value.push({ key: '', value: '' })
  }
}

const removeReqHeaderRow = (index) => {
  reqHeadersMod.value.splice(index, 1)

  if (reqHeadersMod.value.length === 0) {
    reqHeadersMod.value.push({ key: '', value: '' })
  }

  syncReqHeadersToRule()
}

// --- 3. WATCHERS ---

// Auto-select the first rule if nothing is selected but rules exist
watch(mapLocalRules, (newRules) => {
  if (newRules.length > 0 && !selectedRuleId.value) {
    selectedRuleId.value = newRules[0].id
  }
}, { immediate: true, deep: true })

// Sync params and headers when the active rule changes (e.g. clicking a different rule in the sidebar)
watch(activeRule, (rule) => {
  if (rule) {
    syncPatternToParams()
    syncRuleToHeaders()
    syncRuleToReqHeaders()
  }
}, { immediate: true })

// Sync params and headers when the modal opens (e.g. intercepted request triggered it)
watch(showMapModal, (isOpen) => {
  if (isOpen && activeRule.value) {
    syncPatternToParams()
    syncRuleToHeaders()
    syncRuleToReqHeaders()
  }
})

// --- 4. STATUS AUTOCOMPLETE ---

const HTTP_STATUS_CODES = [
  { code: 100, label: 'Continue' },
  { code: 101, label: 'Switching Protocols' },
  { code: 200, label: 'OK' },
  { code: 201, label: 'Created' },
  { code: 202, label: 'Accepted' },
  { code: 204, label: 'No Content' },
  { code: 206, label: 'Partial Content' },
  { code: 301, label: 'Moved Permanently' },
  { code: 302, label: 'Found' },
  { code: 304, label: 'Not Modified' },
  { code: 307, label: 'Temporary Redirect' },
  { code: 308, label: 'Permanent Redirect' },
  { code: 400, label: 'Bad Request' },
  { code: 401, label: 'Unauthorized' },
  { code: 403, label: 'Forbidden' },
  { code: 404, label: 'Not Found' },
  { code: 405, label: 'Method Not Allowed' },
  { code: 408, label: 'Request Timeout' },
  { code: 409, label: 'Conflict' },
  { code: 410, label: 'Gone' },
  { code: 422, label: 'Unprocessable Entity' },
  { code: 429, label: 'Too Many Requests' },
  { code: 500, label: 'Internal Server Error' },
  { code: 501, label: 'Not Implemented' },
  { code: 502, label: 'Bad Gateway' },
  { code: 503, label: 'Service Unavailable' },
  { code: 504, label: 'Gateway Timeout' },
]

const statusInputValue = ref('')
const statusDropdownOpen = ref(false)
const statusHighlightIndex = ref(-1)

const statusSuggestions = computed(() => {
  const q = statusInputValue.value.trim()
  if (!q) return HTTP_STATUS_CODES
  return HTTP_STATUS_CODES.filter(s =>
    String(s.code).startsWith(q) || s.label.toLowerCase().includes(q.toLowerCase())
  )
})

const onStatusInput = (e) => {
  statusInputValue.value = e.target.value
  statusDropdownOpen.value = true
  statusHighlightIndex.value = -1
  const num = parseInt(e.target.value)
  if (!isNaN(num) && activeRule.value) activeRule.value.status = num
}

const onStatusFocus = () => {
  statusInputValue.value = String(activeRule.value?.status ?? 200)
  statusDropdownOpen.value = true
  statusHighlightIndex.value = -1
}

const onStatusBlur = () => {
  setTimeout(() => { statusDropdownOpen.value = false }, 150)
}

const selectStatus = (code) => {
  if (activeRule.value) activeRule.value.status = code
  statusInputValue.value = String(code)
  statusDropdownOpen.value = false
}

const getStatusClass = (code) => {
  if (code >= 100 && code < 200) return 'status-1xx'
  if (code >= 200 && code < 300) return 'status-2xx'
  if (code >= 300 && code < 400) return 'status-3xx'
  if (code >= 400 && code < 500) return 'status-4xx'
  if (code >= 500 && code < 600) return 'status-5xx'
  return ''
}

const statusInputClass = computed(() => getStatusClass(activeRule.value?.status ?? 200))

const onStatusKeydown = (e) => {
  if (!statusDropdownOpen.value) return
  const list = statusSuggestions.value
  if (e.key === 'ArrowDown') {
    e.preventDefault()
    statusHighlightIndex.value = Math.min(statusHighlightIndex.value + 1, list.length - 1)
  } else if (e.key === 'ArrowUp') {
    e.preventDefault()
    statusHighlightIndex.value = Math.max(statusHighlightIndex.value - 1, 0)
  } else if (e.key === 'Enter' && statusHighlightIndex.value >= 0) {
    e.preventDefault()
    selectStatus(list[statusHighlightIndex.value].code)
  } else if (e.key === 'Escape') {
    statusDropdownOpen.value = false
  }
}

watch(activeRule, (rule) => {
  if (rule) statusInputValue.value = String(rule.status ?? 200)
}, { immediate: true })

// --- 5. RULE MANAGEMENT ---

const addNewRule = () => {
  const newRule = {
    id: Date.now(),
    active: true,
    label: '',
    method: 'ANY',
    pattern: 'api.example.com/*',
    status: 200,
    headers: '{\n  "Content-Type": "application/json"\n}',
    body: '',
    body_source: 'inline',
    file_path: '',
  }
  mapLocalRules.value.unshift(newRule)
  selectedRuleId.value = newRule.id
}

const deleteRule = (id) => {
  mapLocalRules.value = mapLocalRules.value.filter(r => r.id !== id)
  if (selectedRuleId.value === id) {
    selectedRuleId.value = mapLocalRules.value.length ? mapLocalRules.value[0].id : null
  }
}

const saveAndApplyRules = () => {
  syncMapLocalRules()
  showMapModal.value = false
}

const browseFile = async () => {
  if (!activeRule.value) return
  const filePath = await window.electronAPI?.selectFile()
  if (filePath) {
    activeRule.value.file_path = filePath
    activeRule.value.body_source = 'file'
  }
}
</script>

<template>
  <Teleport to="body">
    <div v-if="showMapModal" class="modal-overlay" @mousedown.self="saveAndApplyRules">

      <div class="pm-split-modal" ref="modalRef" :style="modalStyle">
        <span class="resize-edge resize-n"  @mousedown.prevent.stop="startResize('n',  $event)"></span>
        <span class="resize-edge resize-ne" @mousedown.prevent.stop="startResize('ne', $event)"></span>
        <span class="resize-edge resize-e"  @mousedown.prevent.stop="startResize('e',  $event)"></span>
        <span class="resize-edge resize-se" @mousedown.prevent.stop="startResize('se', $event)"></span>
        <span class="resize-edge resize-s"  @mousedown.prevent.stop="startResize('s',  $event)"></span>
        <span class="resize-edge resize-sw" @mousedown.prevent.stop="startResize('sw', $event)"></span>
        <span class="resize-edge resize-w"  @mousedown.prevent.stop="startResize('w',  $event)"></span>
        <span class="resize-edge resize-nw" @mousedown.prevent.stop="startResize('nw', $event)"></span>

        <div class="pm-sidebar">
          <div class="pm-sidebar-header">
            <strong style="color: var(--fg-secondary); font-size: 13px;">Map Local Rules</strong>
            <button class="pm-add-btn" @click="addNewRule">+ Add</button>
          </div>

          <div class="pm-rule-list">
            <div v-for="rule in mapLocalRules" :key="rule.id" class="pm-rule-item"
              :class="{ active: selectedRuleId === rule.id }" @click="selectedRuleId = rule.id">

              <label class="pm-checkbox-container" @click.stop>
                <input type="checkbox" v-model="rule.active" />
                <span class="pm-checkmark"></span>
              </label>

              <div class="pm-rule-text-stack">
                <span class="pm-rule-pattern" :title="rule.label || rule.pattern">
                  {{ rule.label || rule.pattern || 'New Rule' }}
                </span>
                <span class="pm-rule-subtext">
                  <span class="pm-method-badge" :class="`method-${(rule.method||'ANY').toLowerCase()}`">{{ rule.method || 'ANY' }}</span>
                  <span v-if="rule.label">{{ rule.pattern }}</span>
                </span>
              </div>

              <button class="pm-rule-del" @click.stop="deleteRule(rule.id)" title="Delete Rule">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
                  stroke-linecap="round" stroke-linejoin="round">
                  <polyline points="3 6 5 6 21 6"></polyline>
                  <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
                  <line x1="10" y1="11" x2="10" y2="17"></line>
                  <line x1="14" y1="11" x2="14" y2="17"></line>
                </svg>
              </button>
            </div>

            <div v-if="mapLocalRules.length === 0" class="empty-state">
              No rules yet. Click + to create your first Map Local rule.
            </div>
          </div>

          <div class="pm-sidebar-footer">
            <div class="toggle" @click="enableMapLocal = !enableMapLocal" :class="{ active: enableMapLocal }">
              <span class="toggle-label">Enable Map Local</span>
              <div class="switch"></div>
            </div>
            <div class="pm-divider-horizontal"></div>
            <div style="display: flex; gap: 8px;">
              <button class="ghost-btn" style="flex: 1; justify-content: center;"
                @click="exportRules(mapLocalRules, 'OpenProxy_MapLocal')">Export</button>
              <div class="ghost-btn" style="position: relative; overflow: hidden; flex: 1; justify-content: center;">
                Import
                <input type="file" accept=".json" 
                  style="position: absolute; top: 0; left: 0; width: 100%; height: 100%; opacity: 0; cursor: pointer;"
                  @change="(e) => importRules(e, mapLocalRules)" />
              </div>
            </div>
          </div>
        </div>

        <div class="pm-main-area">
          <div v-if="activeRule" style="display: flex; flex-direction: column; height: 100%;">
            <div class="pm-header">
              <strong class="pm-title">Mock Response Editor</strong>
              <button class="pm-close-btn" @click="saveAndApplyRules">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round">
                  <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
                </svg>
              </button>
            </div>

            <div style="padding: 16px 20px 0 20px;">
              <div class="pm-label-container">
                <span class="pm-routing-label">Rule Name (Optional)</span>
                <input type="text" v-model="activeRule.label" class="pm-routing-input"
                  placeholder="e.g., Get User Profile Mock" />
              </div>
            </div>

            <div class="pm-omnibar-container">
              <div class="pm-omnibar">
                <div class="pm-method-wrapper" style="position: relative;">
                  <div class="pm-method-display" :class="(activeRule.method||'ANY').toLowerCase()"
                    @click="showMethodMenu = !showMethodMenu">
                    {{ activeRule.method || 'ANY' }}
                    <svg class="pm-chevron" viewBox="0 0 24 24" width="12" height="12">
                      <path d="M7 10l5 5 5-5z" fill="currentColor"/>
                    </svg>
                  </div>
                  <div v-if="showMethodMenu" class="pm-dropdown-overlay" @click.stop="showMethodMenu = false"></div>
                  <div v-if="showMethodMenu" class="pm-method-dropdown">
                    <div v-for="m in ['ANY', 'GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'HEAD', 'OPTIONS']" :key="m"
                      class="pm-method-option" :class="m.toLowerCase()" @click="selectMethod(m)">
                      {{ m }}
                    </div>
                  </div>
                </div>
                <div class="pm-divider"></div>
                <input type="text" v-model="activeRule.pattern" class="pm-url-input"
                  placeholder="e.g., api.example.com/*" @input="syncPatternToParams" />
                <div class="pm-divider"></div>
                <div class="pm-status-wrapper" style="position: relative;">
                  <span class="pm-status-label">Status</span>
                  <input
                    type="text"
                    class="pm-status-input"
                    :class="statusInputClass"
                    :value="statusInputValue"
                    @input="onStatusInput"
                    @focus="onStatusFocus"
                    @blur="onStatusBlur"
                    @keydown="onStatusKeydown"
                    autocomplete="off"
                  />
                  <div v-if="statusDropdownOpen && statusSuggestions.length" class="pm-status-dropdown">
                    <div
                      v-for="(s, i) in statusSuggestions"
                      :key="s.code"
                      class="pm-status-option"
                      :class="{ highlighted: i === statusHighlightIndex }"
                      @mousedown.prevent="selectStatus(s.code)"
                    >
                      <span class="pm-status-code" :class="getStatusClass(s.code)">{{ s.code }}</span>
                      <span class="pm-status-desc">{{ s.label }}</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            <div class="pm-tabs">

              <span class="pm-tab" :class="{ active: activeTab === 'Body' }" @click="activeTab = 'Body'">Body</span>
              <span class="pm-tab" :class="{ active: activeTab === 'Params' }"
                @click="activeTab = 'Params'">Params</span>
              <span class="pm-tab" :class="{ active: activeTab === 'Req Headers' }"
                @click="activeTab = 'Req Headers'">Request Headers</span>
              <span class="pm-tab" :class="{ active: activeTab === 'Res Headers' }"
                @click="activeTab = 'Res Headers'">Response Headers</span>
            </div>

            <div class="pm-editor-area">
              <div v-if="activeTab === 'Body'" class="pm-editor-wrapper">
                <div class="pm-body-source-bar">
                  <span class="pm-helper-text" style="margin: 0;">Response Body</span>
                  <div class="pm-source-toggle">
                    <button
                      class="pm-source-btn"
                      :class="{ active: (activeRule.body_source || 'inline') === 'inline' }"
                      @click="activeRule.body_source = 'inline'; activeRule.file_path = ''"
                    >Inline</button>
                    <button
                      class="pm-source-btn"
                      :class="{ active: activeRule.body_source === 'file' }"
                      @click="activeRule.body_source = 'file'"
                    >File</button>
                  </div>
                </div>

                <div v-if="(activeRule.body_source || 'inline') === 'inline'" style="flex:1; display:flex; flex-direction:column; overflow:hidden;">
                  <CodeMirrorEditor v-model="activeRule.body" :extensions="extensions" class="pm-codemirror" />
                </div>

                <div v-else class="pm-file-picker">
                  <div class="pm-file-row">
                    <input
                      type="text"
                      class="pm-file-input"
                      v-model="activeRule.file_path"
                      placeholder="No file selected…"
                      readonly
                    />
                    <button class="pm-browse-btn" @click="browseFile">Browse…</button>
                  </div>
                  <p class="pm-file-hint">
                    Select any file on disk (.json, .png, .jpg, .html, …). The Content-Type will be
                    detected automatically from the file extension unless you override it in the Headers tab.
                  </p>
                  <p v-if="activeRule.file_path" class="pm-file-path-display">
                    {{ activeRule.file_path }}
                  </p>
                </div>
              </div>
              <div v-if="activeTab === 'Params'" class="pm-editor-wrapper">
                <div class="pm-helper-text">Query Parameters</div>

                <div class="pm-params-container">

                  <div class="pm-param-header">
                    <div class="pm-param-col">Key</div>
                    <div class="pm-param-col">Value</div>
                    <div class="pm-param-action"></div>
                  </div>

                  <div class="pm-param-row" v-for="(param, index) in queryParams" :key="index">
                    <input type="text" v-model="param.key" placeholder="Key" class="pm-param-input"
                      @input="syncParamsToPattern(); checkParamRow(index)" />

                    <input type="text" v-model="param.value" placeholder="Value" class="pm-param-input"
                      @input="syncParamsToPattern()" />

                    <button class="pm-param-del" @click="removeParamRow(index)" title="Remove Row">
                      ✕
                    </button>
                  </div>

                </div>
              </div>
              <div v-if="activeTab === 'Res Headers'" class="pm-editor-wrapper">
                <div class="pm-helper-text">Response Headers — sent back in the mock response</div>

                <div class="pm-params-container">

                  <div class="pm-param-header">
                    <div class="pm-param-col">Header Name</div>
                    <div class="pm-param-col">Value</div>
                    <div class="pm-param-action"></div>
                  </div>

                  <div class="pm-param-row" v-for="(header, index) in responseHeaders" :key="index">
                    <input type="text" v-model="header.key" placeholder="e.g. Content-Type" class="pm-param-input"
                      @input="syncHeadersToRule(); checkHeaderRow(index)" />

                    <input type="text" v-model="header.value" placeholder="e.g. application/json" class="pm-param-input"
                      @input="syncHeadersToRule()" />

                    <button class="pm-param-del" @click="removeHeaderRow(index)" title="Remove Header">
                      ✕
                    </button>
                  </div>

                </div>
              </div>
              <div v-if="activeTab === 'Req Headers'" class="pm-editor-wrapper">
                <div class="pm-helper-text">Request Headers — override headers on the intercepted request</div>

                <div class="pm-params-container">

                  <div class="pm-param-header">
                    <div class="pm-param-col">Header Name</div>
                    <div class="pm-param-col">Value</div>
                    <div class="pm-param-action"></div>
                  </div>

                  <div class="pm-param-row" v-for="(header, index) in reqHeadersMod" :key="index">
                    <input type="text" v-model="header.key" placeholder="e.g. os" class="pm-param-input"
                      @input="syncReqHeadersToRule(); checkReqHeaderRow(index)" />
                    <input type="text" v-model="header.value" placeholder="e.g. android" class="pm-param-input"
                      @input="syncReqHeadersToRule()" />
                    <button class="pm-param-del" @click="removeReqHeaderRow(index)" title="Remove Header">
                      ✕
                    </button>
                  </div>

                </div>
              </div>
            </div>

            <div class="pm-footer">
              <button class="pm-btn-cancel" @click="showMapModal = false">Cancel</button>
              <button class="pm-btn-execute" @click="saveAndApplyRules">Save & Apply</button>
            </div>
          </div>
          <div v-else class="pm-main-empty">
            Select or create a rule to edit.
          </div>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.modal-overlay {
  position: fixed; top: 0; left: 0; right: 0; bottom: 0;
  background: var(--overlay); z-index: 99999;
  display: flex; justify-content: center; align-items: center;
}

.pm-split-modal {
  background: var(--bg-main); border-radius: 10px; border: 1px solid var(--border);
  width: 1000px; height: 650px; min-width: 600px; min-height: 420px;
  max-width: calc(100vw - 20px); max-height: calc(100vh - 40px);
  display: flex; flex-direction: row; box-shadow: var(--shadow-lg);
  overflow: hidden; position: relative;
}

.resize-edge { position: absolute; z-index: 10; }
.resize-n, .resize-s { left: 8px; right: 8px; height: 6px; cursor: ns-resize; }
.resize-e, .resize-w { top: 8px; bottom: 8px; width: 6px; cursor: ew-resize; }
.resize-n  { top: 0; }
.resize-s  { bottom: 0; }
.resize-e  { right: 0; }
.resize-w  { left: 0; }
.resize-ne, .resize-nw, .resize-se, .resize-sw { width: 12px; height: 12px; }
.resize-ne { top: 0; right: 0; cursor: nesw-resize; }
.resize-nw { top: 0; left: 0; cursor: nwse-resize; }
.resize-se { bottom: 0; right: 0; cursor: nwse-resize; }
.resize-sw { bottom: 0; left: 0; cursor: nesw-resize; }

.pm-sidebar {
  width: 280px; background: var(--bg-sidebar); border-right: 1px solid var(--border);
  display: flex; flex-direction: column; flex-shrink: 0;
}

.pm-sidebar-header {
  padding: 12px 16px; border-bottom: 1px solid var(--border);
  display: flex; justify-content: space-between; align-items: center;
  background: var(--bg-sidebar);
}

.pm-add-btn {
  background: var(--accent-muted); color: var(--accent);
  border: 1px solid var(--accent-border); padding: 4px 10px;
  border-radius: 5px; font-size: 11px; font-weight: 600;
  cursor: pointer; transition: all 0.15s;
}
.pm-add-btn:hover { background: var(--accent); color: #fff; border-color: var(--accent); }

.pm-rule-list { flex: 1; overflow-y: auto; }
.pm-rule-item {
  height: 44px; padding: 0 14px; border-bottom: 1px solid var(--border-subtle);
  display: flex; align-items: center; gap: 10px;
  cursor: pointer; transition: background 0.15s; box-sizing: border-box;
}
.pm-rule-item:hover { background: var(--bg-active); }
.pm-rule-item.active { background: var(--accent-muted); border-left: 3px solid var(--accent); padding-left: 11px; }

.empty-state {
  padding: 40px 20px; text-align: center;
  color: var(--fg-placeholder); font-size: 12px; line-height: 1.6;
}

.pm-main-empty {
  flex: 1; display: flex; justify-content: center; align-items: center;
  color: var(--fg-muted); font-style: italic; font-size: 12px;
}

/* Text Stack */
.pm-rule-text-stack { flex: 1; display: flex; flex-direction: column; min-width: 0; }
.pm-rule-pattern { font-family: 'Consolas', monospace; font-size: 11px; color: var(--fg-secondary); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; line-height: 1.2; }
.pm-rule-subtext { font-size: 9px; color: var(--fg-muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; margin-top: 2px; }

/* Checkbox */
.pm-checkbox-container { display: flex; align-items: center; justify-content: center; position: relative; width: 16px; height: 16px; flex-shrink: 0; cursor: pointer; }
.pm-checkbox-container input { position: absolute; opacity: 0; }
.pm-checkmark { position: absolute; top: 0; left: 0; height: 16px; width: 16px; background-color: var(--bg-deepest); border: 1px solid var(--fg-muted); border-radius: 4px; transition: border-color 0.2s, background-color 0.2s; box-sizing: border-box; }
.pm-checkbox-container:hover input ~ .pm-checkmark { border-color: var(--accent); }
.pm-checkbox-container input:checked ~ .pm-checkmark { background-color: var(--accent); border-color: var(--accent); }
.pm-checkmark:after { content: ""; position: absolute; display: none; left: 50%; top: 45%; width: 4px; height: 9px; border: solid white; border-width: 0 2px 2px 0; transform: translate(-50%, -50%) rotate(45deg); }
.pm-checkbox-container input:checked ~ .pm-checkmark:after { display: block; }

/* Delete button */
.pm-rule-del { background: transparent; border: 1px solid transparent; color: var(--fg-muted); cursor: pointer; padding: 4px; border-radius: 5px; display: flex; align-items: center; justify-content: center; transition: all 0.15s; flex-shrink: 0; }
.pm-rule-del:hover { background: var(--error-muted) !important; border-color: rgba(239,68,68,.3) !important; color: var(--error) !important; }

/* Sidebar footer */
.pm-sidebar-footer { padding: 14px 16px; background: var(--bg-modal); border-top: 1px solid var(--border); display: flex; flex-direction: column; gap: 10px; }
.toggle { display: flex; align-items: center; justify-content: space-between; cursor: pointer; color: var(--fg-muted); font-weight: 600; font-size: 12px; }
.toggle.active { color: var(--accent); }
.switch { width: 32px; height: 18px; background: var(--bg-input); border: 1px solid var(--border); border-radius: 14px; position: relative; transition: all 0.3s; box-sizing: border-box; }
.switch::after { content: ''; position: absolute; top: 1px; left: 1px; width: 14px; height: 14px; background: var(--fg-muted); border-radius: 50%; transition: transform 0.3s, background 0.3s; }
.toggle.active .switch { background: var(--accent-muted); border-color: var(--accent); }
.toggle.active .switch::after { transform: translateX(14px); background: var(--accent); }
.pm-divider-horizontal { width: 100%; height: 1px; background: var(--border); }
.ghost-btn { display: flex; align-items: center; gap: 4px; height: 26px; padding: 0 10px; background: transparent; border: 1px solid var(--border); color: var(--fg-muted); border-radius: 5px; cursor: pointer; font-size: 11px; font-weight: 500; transition: all 0.15s; }
.ghost-btn:hover { background: var(--surface-hover-strong); color: var(--fg-primary); border-color: var(--fg-muted); }

/* MAIN EDITOR */
.pm-main-area { flex: 1; display: flex; flex-direction: column; background: var(--bg-main); min-width: 0; }
.pm-header { display: flex; justify-content: space-between; align-items: center; padding: 0 16px; height: 44px; background: var(--bg-sidebar); border-bottom: 1px solid var(--border); flex-shrink: 0; }
.pm-title { font-size: 13px; font-weight: 600; color: var(--fg-primary); }
.pm-close-btn { background: none; border: none; cursor: pointer; color: var(--fg-muted); padding: 4px; border-radius: 4px; display: flex; align-items: center; justify-content: center; transition: background 0.12s, color 0.12s; }
.pm-close-btn:hover { background: var(--surface-hover-strong); color: var(--fg-primary); }

.pm-label-container { display: flex; flex-direction: column; gap: 6px; }
.pm-routing-label { font-size: 11px; font-weight: 600; color: var(--fg-muted); text-transform: uppercase; letter-spacing: 0.5px; }
.pm-routing-input { background: var(--bg-deepest); border: 1px solid var(--border); color: var(--fg-primary); padding: 10px 12px; border-radius: 6px; font-size: 13px; outline: none; transition: border-color 0.2s; }
.pm-routing-input:focus { border-color: var(--accent); }

.pm-omnibar-container { padding: 12px 20px; }
.pm-omnibar { display: flex; align-items: center; background: var(--bg-deepest); border: 1px solid var(--border); border-radius: 6px; }
.pm-url-input { flex: 1; background: transparent; border: none; color: var(--fg-secondary); padding: 10px 12px; font-size: 13px; outline: none; font-family: 'Consolas', monospace; }
.pm-divider { width: 1px; height: 24px; background: var(--border); }
.pm-method-wrapper { position: relative; }
.pm-method-display {
  padding: 10px 14px; font-weight: 700; font-size: 11px; cursor: pointer;
  color: var(--fg-muted); min-width: 78px; display: flex; align-items: center; gap: 4px;
  user-select: none;
}
.pm-method-display.get    { color: #4ade80; }
.pm-method-display.post   { color: #60a5fa; }
.pm-method-display.put    { color: #f59e0b; }
.pm-method-display.patch  { color: #a78bfa; }
.pm-method-display.delete { color: #f87171; }
.pm-dropdown-overlay {
  position: fixed; top: 0; left: 0; right: 0; bottom: 0; z-index: 99; cursor: default;
}
.pm-method-dropdown {
  position: absolute; top: 100%; left: 0; margin-top: 4px;
  background: var(--bg-card); border: 1px solid var(--border); border-radius: 6px;
  box-shadow: var(--shadow-lg); z-index: 100; min-width: 120px; padding: 4px 0;
}
.pm-method-option {
  padding: 8px 16px; font-size: 12px; font-weight: 700; cursor: pointer; transition: background 0.1s;
  color: var(--fg-muted);
}
.pm-method-option:hover { background: var(--surface-hover-strong); }
.pm-method-option.get    { color: #4ade80; }
.pm-method-option.post   { color: #60a5fa; }
.pm-method-option.put    { color: #f59e0b; }
.pm-method-option.patch  { color: #a78bfa; }
.pm-method-option.delete { color: #f87171; }
.pm-method-badge {
  display: inline-block; font-size: 9px; font-weight: 700; font-family: 'Consolas', monospace;
  padding: 1px 5px; border-radius: 3px; background: rgba(255,255,255,0.06);
  color: var(--fg-muted); letter-spacing: 0.03em; margin-right: 5px;
}
.pm-method-badge.method-get    { color: #4ade80; background: rgba(74,222,128,0.1); }
.pm-method-badge.method-post   { color: #60a5fa; background: rgba(96,165,250,0.1); }
.pm-method-badge.method-put    { color: #f59e0b; background: rgba(245,158,11,0.1); }
.pm-method-badge.method-patch  { color: #a78bfa; background: rgba(167,139,250,0.1); }
.pm-method-badge.method-delete { color: #f87171; background: rgba(248,113,113,0.1); }
.pm-status-wrapper { display: flex; align-items: center; padding: 0 12px; gap: 8px; }
.pm-status-input { background: var(--bg-deepest); border: 1px solid var(--border); color: var(--fg-secondary); padding: 4px 8px; border-radius: 4px; font-size: 13px; font-weight: bold; width: 60px; text-align: center; }
.pm-status-dropdown { position: absolute; top: calc(100% + 4px); right: 0; background: var(--bg-card); border: 1px solid var(--border); border-radius: 6px; box-shadow: 0 8px 24px rgba(0,0,0,0.3); z-index: 9999; min-width: 200px; max-height: 220px; overflow-y: auto; }
.pm-status-option { display: flex; align-items: center; gap: 10px; padding: 6px 12px; cursor: pointer; font-size: 12px; }
.pm-status-option:hover, .pm-status-option.highlighted { background: var(--surface-hover-strong); }
.pm-status-code { font-weight: 700; font-family: 'Consolas', monospace; min-width: 32px; }
.pm-status-desc { color: var(--fg-muted); }
.status-1xx { color: var(--accent); }
.status-2xx { color: var(--success); }
.status-3xx { color: var(--warning); }
.status-4xx { color: var(--color-orange); }
.status-5xx { color: var(--error); }

.pm-tabs { display: flex; gap: 24px; padding: 0 24px; border-bottom: 1px solid var(--border); }
.pm-tab { color: var(--fg-muted); font-size: 13px; padding: 10px 0; cursor: pointer; border-bottom: 2px solid transparent; }
.pm-tab.active { color: var(--fg-secondary); border-bottom-color: var(--accent); }

.pm-editor-area { flex: 1; display: flex; flex-direction: column; background: var(--bg-deepest); overflow: hidden; }
.pm-editor-wrapper { display: flex; flex-direction: column; height: 100%; }
.pm-helper-text { font-size: 11px; color: var(--fg-muted); padding: 8px 24px; background: var(--bg-card); }
.pm-codemirror { flex: 1; overflow: hidden; font-size: 13px; }
.pm-codemirror :deep(.cm-editor) { height: 100% !important; }

.pm-footer { display: flex; justify-content: flex-end; gap: 10px; padding: 12px 16px; background: var(--bg-sidebar); border-top: 1px solid var(--border); flex-shrink: 0; }
.pm-btn-cancel { background: transparent; border: 1px solid var(--border); color: var(--fg-secondary); padding: 6px 20px; border-radius: 6px; font-weight: 500; font-size: 12px; cursor: pointer; transition: all 0.15s; }
.pm-btn-cancel:hover { background: var(--surface-hover-strong); color: var(--fg-primary); border-color: var(--fg-muted); }
.pm-btn-execute { background: var(--accent); border: none; color: #fff; padding: 6px 24px; border-radius: 6px; cursor: pointer; font-weight: 500; font-size: 12px; transition: background 0.15s; }
.pm-btn-execute:hover { background: var(--accent-hover); }

.pm-params-container { padding: 16px 24px; overflow-y: auto; flex: 1; }
.pm-param-header { display: flex; font-size: 11px; color: var(--fg-muted); font-weight: 600; padding-bottom: 8px; border-bottom: 1px solid var(--border); margin-bottom: 8px; }
.pm-param-col { flex: 1; padding: 0 8px; }
.pm-param-action { width: 32px; }
.pm-param-row { display: flex; gap: 8px; margin-bottom: 8px; align-items: center; }
.pm-param-input { flex: 1; background: transparent; border: 1px solid var(--border); color: var(--fg-secondary); padding: 6px 10px; font-size: 13px; font-family: 'Consolas', monospace; border-radius: 4px; outline: none; }
.pm-param-input:focus { border-color: var(--accent); background: var(--bg-sidebar); }
.pm-param-del { background: transparent; border: none; color: var(--fg-placeholder); cursor: pointer; width: 32px; font-size: 14px; }
.pm-param-del:hover { color: var(--error); }

/* Request headers override section */
.pm-req-headers-label { border-top: 1px solid var(--border); margin-top: 0; flex-shrink: 0; }

/* Body source toggle */
.pm-body-source-bar {
  display: flex; align-items: center; justify-content: space-between;
  padding: 6px 24px; background: var(--bg-card); border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}
.pm-source-toggle { display: flex; background: var(--bg-deepest); border: 1px solid var(--border); border-radius: 6px; overflow: hidden; }
.pm-source-btn { background: transparent; border: none; color: var(--fg-muted); padding: 4px 14px; font-size: 11px; font-weight: 600; cursor: pointer; transition: all 0.15s; }
.pm-source-btn.active { background: var(--accent); color: #fff; }

/* File picker */
.pm-file-picker { display: flex; flex-direction: column; gap: 12px; padding: 20px 24px; }
.pm-file-row { display: flex; gap: 8px; align-items: center; }
.pm-file-input {
  flex: 1; background: var(--bg-deepest); border: 1px solid var(--border);
  color: var(--fg-secondary); padding: 8px 12px; border-radius: 6px;
  font-size: 12px; font-family: 'Consolas', monospace; outline: none;
  cursor: default;
}
.pm-browse-btn {
  background: var(--accent-muted); color: var(--accent); border: 1px solid var(--accent-border);
  padding: 8px 16px; border-radius: 6px; font-size: 12px; font-weight: 600;
  cursor: pointer; white-space: nowrap; transition: all 0.15s; flex-shrink: 0;
}
.pm-browse-btn:hover { background: var(--accent); color: #fff; border-color: var(--accent); }
.pm-file-hint { font-size: 11px; color: var(--fg-muted); line-height: 1.5; margin: 0; }
.pm-file-path-display {
  font-size: 11px; color: var(--fg-secondary); font-family: 'Consolas', monospace;
  word-break: break-all; background: var(--bg-card); border: 1px solid var(--border);
  border-radius: 4px; padding: 8px 12px; margin: 0;
}
</style>