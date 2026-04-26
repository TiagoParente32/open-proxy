<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { nextTick } from 'vue'
import { 
  filteredRequests, requests, selectedRequest, isFocusMode, pinnedSources, 
  formatUrl, contextMenu, searchQuery, searchScope, searchMatchType,
  sortKey, sortOrder, toggleSort, formatTime, formatBytes 
} from '../store.js'

// Grouped: null = separator
const SCOPES = [
  { label: 'All',             key: 'All'             },
  null,
  { label: 'URL',             key: 'URL'             },
  { label: 'Query String',    key: 'Query String'    },
  null,
  { label: 'Request Header',  key: 'Request Header'  },
  { label: 'Response Header', key: 'Response Header' },
  null,
  { label: 'Request Body',    key: 'Request Body'    },
  { label: 'Response Body',   key: 'Response Body'   },
  null,
  { label: 'Method',          key: 'Method'          },
  { label: 'Status Code',     key: 'Status Code'     },
]

const MATCH_TYPES = [
  { label: 'Contains',        key: 'Contains'        },
  { label: 'Not Contains',    key: 'Not Contains'    },
  null,
  { label: 'Starts With',     key: 'Starts With'     },
  { label: 'Ends With',       key: 'Ends With'       },
  null,
  { label: 'Equals',          key: 'Equals'          },
  { label: 'Not Equals',      key: 'Not Equals'      },
  null,
  { label: 'Match Regex',     key: 'Match Regex'     },
  { label: 'Not Match Regex', key: 'Not Match Regex' },
]

const showScopeMenu = ref(false)
const showMatchMenu = ref(false)
const searchInput = ref(null)
const scopeTriggerRef = ref(null)
const matchTriggerRef = ref(null)
const scopeDropdownStyle = ref({})
const matchDropdownStyle = ref({})

const calcPos = (triggerRef) => {
  const rect = triggerRef.value?.getBoundingClientRect()
  return rect ? { position: 'fixed', top: `${rect.bottom + 5}px`, left: `${rect.left}px` } : {}
}

const openScopeMenu = () => {
  showMatchMenu.value = false
  scopeDropdownStyle.value = calcPos(scopeTriggerRef)
  showScopeMenu.value = !showScopeMenu.value
}

const openMatchMenu = () => {
  showScopeMenu.value = false
  matchDropdownStyle.value = calcPos(matchTriggerRef)
  showMatchMenu.value = !showMatchMenu.value
}

const selectScope = (key) => {
  searchScope.value = key
  showScopeMenu.value = false
  searchInput.value?.focus()
}

const selectMatch = (key) => {
  searchMatchType.value = key
  showMatchMenu.value = false
  searchInput.value?.focus()
}

const clearSearch = () => {
  searchQuery.value = ''
  searchInput.value?.focus()
}

const closeAllMenus = (e) => {
  if (!e.target.closest('.search-scope-wrapper') && !e.target.closest('.scope-dropdown-portal')) {
    showScopeMenu.value = false
    showMatchMenu.value = false
  }
}

const getMethodColor = (method) => {
  const colors = { GET: '#3b82f6', POST: '#10b981', PUT: '#f59e0b', DELETE: '#ef4444', OPTIONS: '#8b5cf6' }
  return colors[method] || '#8b949e'
}

const openContextMenu = (e, req) => {
  selectedRequest.value = req
  contextMenu.value = { show: true, x: e.clientX, y: e.clientY, request: req }
}

const sortIcon = (key) => {
  if (sortKey.value !== key) return ''
  return sortOrder.value === 'asc' ? ' ↑' : ' ↓'
}

const handleKeyDown = async (e) => {
  if (['INPUT', 'TEXTAREA'].includes(document.activeElement.tagName)) return
  if ((showScopeMenu.value || showMatchMenu.value) && e.key === 'Escape') {
    showScopeMenu.value = false; showMatchMenu.value = false; return
  }
  if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
    e.preventDefault()
    if (filteredRequests.value.length === 0) return
    if (!selectedRequest.value) { selectedRequest.value = filteredRequests.value[0]; return }
    const idx = filteredRequests.value.findIndex(r => r.id === selectedRequest.value.id)
    if (idx === -1) return
    if (e.key === 'ArrowDown' && idx < filteredRequests.value.length - 1)
      selectedRequest.value = filteredRequests.value[idx + 1]
    else if (e.key === 'ArrowUp' && idx > 0)
      selectedRequest.value = filteredRequests.value[idx - 1]
    await nextTick()
    document.querySelector('tr.selected')?.scrollIntoView({ block: 'nearest' })
  }
}

onMounted(() => {
  window.addEventListener('keydown', handleKeyDown)
  document.addEventListener('click', closeAllMenus)
})
onUnmounted(() => {
  window.removeEventListener('keydown', handleKeyDown)
  document.removeEventListener('click', closeAllMenus)
})
</script>

<template>
  <div class="traffic-layout">
    <div class="table-toolbar">
      <div class="search-scope-wrapper">

        <!-- Scope pill -->
        <button ref="scopeTriggerRef" class="scope-trigger" @click.stop="openScopeMenu">
          <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="opacity:.6">
            <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
          </svg>
          <span class="scope-label">{{ searchScope }}</span>
          <svg width="9" height="9" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" class="chevron" :class="{ open: showScopeMenu }">
            <polyline points="6 9 12 15 18 9"/>
          </svg>
        </button>

        <div class="scope-divider" />

        <!-- Match type pill -->
        <button ref="matchTriggerRef" class="match-trigger" @click.stop="openMatchMenu">
          <span class="scope-label">{{ searchMatchType }}</span>
          <svg width="9" height="9" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" class="chevron" :class="{ open: showMatchMenu }">
            <polyline points="6 9 12 15 18 9"/>
          </svg>
        </button>

        <div class="scope-divider" />

        <!-- Text input -->
        <input
          ref="searchInput"
          type="text"
          v-model="searchQuery"
          placeholder="Search…"
          class="search-input"
          @keydown.escape="clearSearch"
        />

        <!-- Clear button -->
        <button v-if="searchQuery" class="clear-btn" @click="clearSearch" title="Clear (Esc)">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#aaa" stroke-width="2.5" stroke-linecap="round">
            <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
          </svg>
        </button>

        <!-- Scope dropdown -->
        <Teleport to="body">
          <div v-if="showScopeMenu" class="scope-dropdown-portal" :style="scopeDropdownStyle">
            <template v-for="(s, i) in SCOPES" :key="i">
              <div v-if="s === null" class="dropdown-separator" />
              <div
                v-else
                class="scope-option" :class="{ active: searchScope === s.key }"
                @click="selectScope(s.key)"
              >
                <svg v-if="searchScope === s.key" width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="#3b82f6" stroke-width="3" stroke-linecap="round">
                  <polyline points="20 6 9 17 4 12"/>
                </svg>
                <span v-else class="scope-option-gap" />
                <span class="scope-option-label">{{ s.label }}</span>
              </div>
            </template>
          </div>
        </Teleport>

        <!-- Match type dropdown -->
        <Teleport to="body">
          <div v-if="showMatchMenu" class="scope-dropdown-portal" :style="matchDropdownStyle">
            <template v-for="(m, i) in MATCH_TYPES" :key="i">
              <div v-if="m === null" class="dropdown-separator" />
              <div
                v-else
                class="scope-option" :class="{ active: searchMatchType === m.key }"
                @click="selectMatch(m.key)"
              >
                <svg v-if="searchMatchType === m.key" width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="#3b82f6" stroke-width="3" stroke-linecap="round">
                  <polyline points="20 6 9 17 4 12"/>
                </svg>
                <span v-else class="scope-option-gap" />
                <span class="scope-option-label">{{ m.label }}</span>
              </div>
            </template>
          </div>
        </Teleport>
      </div>
    </div>

    <div class="table-container">
      <table class="traffic-table">
        <thead>
          <tr>
            <th><div class="resize-handle" style="width: 60px;" @click="toggleSort('id')">ID{{ sortIcon('id') }}</div></th>
            <th><div class="resize-handle" style="width: 75px;" @click="toggleSort('method')">Method{{ sortIcon('method') }}</div></th>
            <th><div class="resize-handle" style="width: 65px;" @click="toggleSort('status')">Status{{ sortIcon('status') }}</div></th>
            <th><div class="resize-handle" style="width: 450px;" @click="toggleSort('url')">URL{{ sortIcon('url') }}</div></th>
            <th><div class="resize-handle" style="width: 85px;" @click="toggleSort('time')">Time{{ sortIcon('time') }}</div></th>
            <th><div class="resize-handle" style="width: 90px;" @click="toggleSort('duration')">Time (ms){{ sortIcon('duration') }}</div></th>
            <th><div class="resize-handle" style="width: 85px;" @click="toggleSort('req_bytes')">Req Size{{ sortIcon('req_bytes') }}</div></th>
            <th><div class="resize-handle" style="width: 85px;" @click="toggleSort('res_bytes')">Res Size{{ sortIcon('res_bytes') }}</div></th>
            <th style="width: 100%;"></th>
          </tr>
        </thead>
        <tbody>
          <tr 
            v-for="req in filteredRequests" 
            :key="req.id" 
            @click="selectedRequest = req" 
            @contextmenu.prevent="openContextMenu($event, req)" 
            :class="[
              { selected: selectedRequest?.id === req.id },
              req.color ? `row-${req.color}` : ''
            ]"
          >
            <td class="text-muted text-id">
              <span v-if="req.starred" style="margin-right: 4px; font-size: 10px;">⭐</span>
              {{ req.id.substring(0, 5) }}
            </td>
            <td><span class="method-badge" :style="{ backgroundColor: getMethodColor(req.method) + '20', color: getMethodColor(req.method) }">{{ req.method }}</span></td>
            <td>
              <span v-if="req.status === '...'" class="text-muted">...</span>
              <span v-else class="status-badge" :class="{'text-green': req.status < 400, 'text-red': req.status >= 400}">{{ req.status }}</span>
            </td>
            <td class="font-semibold truncate" :title="req.url" style="font-family: monospace; font-size: 10.5px; letter-spacing: -0.2px;">{{ req.url }}</td>
            <td class="text-muted">{{ formatTime(req.time) }}</td>
            <td class="text-muted">{{ req.duration ? req.duration + ' ms' : '...' }}</td>
            <td class="text-muted">{{ formatBytes(req.req_bytes) }}</td>
            <td class="text-muted">{{ formatBytes(req.res_bytes) }}</td>
            <td></td>
          </tr>
        </tbody>
      </table>
      <div v-if="filteredRequests.length === 0" class="global-empty">
        <span v-if="searchQuery.trim()">No requests match "{{ searchQuery.trim() }}"</span>
        <span v-else-if="isFocusMode && pinnedSources.length === 0">Add a Pinned Source to see traffic.</span>
        <span v-else>Waiting for traffic…</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.traffic-layout { display: flex; flex-direction: column; height: 100%; background: var(--bg-main); }

/* ── Search bar ───────────────────────────────────── */
.table-toolbar {
  padding: 6px 12px;
  border-bottom: 1px solid var(--border);
  background: var(--bg-main);
  flex-shrink: 0;
}

.search-scope-wrapper {
  position: relative;
  display: flex;
  align-items: center;
  background: #111213;
  border: 1px solid #2e3133;
  border-radius: 7px;
  transition: border-color 0.15s;
  height: 30px;
}
.search-scope-wrapper:focus-within { border-color: #3b82f6; }

.scope-trigger {
  display: flex; align-items: center; gap: 5px;
  padding: 0 10px;
  background: none; border: none; cursor: pointer;
  color: #7a8390; font-size: 11.5px; font-weight: 600;
  white-space: nowrap; flex-shrink: 0;
  height: 100%;
  border-radius: 6px 0 0 6px;
  transition: color 0.15s, background 0.15s;
}
.scope-trigger:hover { color: #c0c8d0; background: rgba(255,255,255,0.04); }

.match-trigger {
  display: flex; align-items: center; gap: 5px;
  padding: 0 9px;
  background: none; border: none; cursor: pointer;
  color: #7a8390; font-size: 11.5px; font-weight: 500;
  white-space: nowrap; flex-shrink: 0;
  height: 100%;
  transition: color 0.15s, background 0.15s;
}
.match-trigger:hover { color: #c0c8d0; background: rgba(255,255,255,0.04); }

.scope-label { max-width: 110px; overflow: hidden; text-overflow: ellipsis; }

.chevron { transition: transform 0.15s; }
.chevron.open { transform: rotate(180deg); }

.scope-divider {
  width: 1px; height: 16px;
  background: #2e3133; flex-shrink: 0;
}

.search-input {
  flex: 1;
  background: none; border: none; outline: none;
  color: #d0d4d8; font-size: 12px;
  padding: 0 8px;
  min-width: 0;
}
.search-input::placeholder { color: #3e4347; }

.clear-btn {
  display: flex; align-items: center; justify-content: center;
  width: 22px; height: 22px; margin-right: 4px; padding: 0;
  background: rgba(255,255,255,0.06); border: none; border-radius: 4px;
  color: #aaa; cursor: pointer; flex-shrink: 0;
  transition: background 0.15s, color 0.15s;
}
.clear-btn:hover { background: rgba(255,255,255,0.12); color: #eee; border-color: transparent; }

/* ── Scope dropdown (teleported to body) ──────────── */
/* dropdown styles moved to non-scoped block below */

/* ── Table ────────────────────────────────────────── */
.table-container { flex: 1; overflow: auto; display: flex; flex-direction: column; }

.traffic-table {
  width: max-content;
  min-width: 100%;
  border-collapse: collapse;
  table-layout: fixed;
  font-size: 12px;
}
.traffic-table th {
  padding: 0;
  background-color: var(--bg-sidebar);
  border-bottom: 1px solid var(--border);
  position: sticky;
  top: 0;
  z-index: 1;
  text-align: left;
}

.resize-handle {
  display: flex; align-items: center;
  padding: 6px 10px;
  color: #888; font-weight: 500;
  cursor: pointer;
  resize: horizontal; overflow: hidden;
  box-sizing: border-box;
  transition: color 0.2s;
}
.resize-handle:hover { color: #ccc; }

.traffic-table td {
  padding: 4px 10px;
  border-bottom: 1px solid #282829;
  white-space: nowrap;
  text-align: left;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 0;
}

.traffic-table tbody tr { scroll-margin-top: 30px; }
.traffic-table tbody tr:hover { background-color: var(--bg-active); cursor: pointer; }
.traffic-table tbody tr.selected { background-color: #1e3a5f !important; color: #fff; }
.traffic-table tbody tr.row-red    { background-color: rgba(239, 68, 68,  0.15); }
.traffic-table tbody tr.row-orange { background-color: rgba(249, 115, 22, 0.15); }
.traffic-table tbody tr.row-yellow { background-color: rgba(245, 158, 11, 0.15); }
.traffic-table tbody tr.row-green  { background-color: rgba(16,  185, 129, 0.15); }
.traffic-table tbody tr.row-blue   { background-color: rgba(59,  130, 246, 0.15); }
.traffic-table tbody tr.row-purple { background-color: rgba(139, 92,  246, 0.15); }

.text-id { font-family: monospace; font-size: 11px; }
.method-badge { padding: 2px 6px; border-radius: 4px; font-weight: 700; font-size: 10px; }
.status-badge { padding: 2px 6px; border-radius: 4px; background: #333; font-size: 10px; font-weight: bold; border: 1px solid #444; }
</style>

<!-- Non-scoped: styles for teleported dropdown (rendered at body level) -->
<style>
.scope-dropdown-portal {
  min-width: 220px;
  background: #1c1e21;
  border: 1px solid #2e3133;
  border-radius: 8px;
  box-shadow: 0 8px 24px rgba(0,0,0,0.55);
  padding: 4px;
  z-index: 99999;
}

.scope-dropdown-portal .scope-option {
  display: flex; align-items: center; gap: 8px;
  padding: 6px 10px;
  border-radius: 5px;
  cursor: pointer;
  font-size: 12px;
  color: #9aa3ad;
  transition: background 0.1s, color 0.1s;
}
.scope-dropdown-portal .scope-option:hover { background: rgba(59,130,246,0.1); color: #d0d4d8; }
.scope-dropdown-portal .scope-option.active .scope-option-label { color: #3b82f6; font-weight: 600; }

.scope-dropdown-portal .scope-option-gap { display: inline-block; width: 11px; flex-shrink: 0; }
.scope-dropdown-portal .scope-option-label { flex: 1; }

.dropdown-separator {
  height: 1px;
  background: #2a2d30;
  margin: 3px 6px;
}
</style>