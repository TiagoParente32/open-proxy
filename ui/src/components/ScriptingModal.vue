<script setup>
import { ref, computed, watch } from 'vue'
import { Codemirror } from 'vue-codemirror'
import { python } from '@codemirror/lang-python'
import { EditorView } from '@codemirror/view'
import { cmTheme } from '../composables/useTheme'
import {
  showScriptingModal,
  scripts,
  selectedScriptId,
  wsConnection,
} from '../store.js'

// ── Local draft for the selected script ──────────────────────────────────────
const draftContent = ref('')
const draftName    = ref('')
const draftEnabled = ref(false)
const saving       = ref(false)
const renaming     = ref(false)

const selectedScript = computed(() => scripts.value.find(s => s.id === selectedScriptId.value) ?? null)

// Sync draft when selection changes or scripts list updates from backend
watch(selectedScript, (s) => {
  if (!s) return
  draftContent.value = s.content
  draftName.value    = s.name
  draftEnabled.value = s.enabled
}, { immediate: true })

// If backend auto-disables a script due to error, reflect that in the draft
watch(
  () => selectedScript.value?.enabled,
  (v) => { if (v === false && draftEnabled.value) draftEnabled.value = false }
)

const hasUnsavedChanges = computed(() =>
  selectedScript.value && draftContent.value !== selectedScript.value.content
)

const extensions = computed(() => [
  python(),
  ...cmTheme.value,
  EditorView.lineWrapping,
])

// ── WS helpers ────────────────────────────────────────────────────────────────
const send = (msg) => {
  if (wsConnection?.readyState === WebSocket.OPEN)
    wsConnection.send(JSON.stringify(msg))
}

const openApiDocs = () =>
  window.electronAPI?.openExternal('https://docs.mitmproxy.org/stable/api/mitmproxy/http.html')

// ── Actions ───────────────────────────────────────────────────────────────────
const save = () => {
  if (!selectedScript.value) return
  saving.value = true
  send({
    type:    'SCRIPT_SAVE',
    id:      selectedScript.value.id,
    name:    draftName.value,
    content: draftContent.value,
    enabled: draftEnabled.value,
  })
  setTimeout(() => { saving.value = false }, 600)
}

const toggleEnabled = () => {
  if (!selectedScript.value) return
  draftEnabled.value = !draftEnabled.value
  // If content matches saved, we can toggle live without a full save
  if (!hasUnsavedChanges.value) {
    send({ type: 'SCRIPT_TOGGLE', id: selectedScript.value.id, enabled: draftEnabled.value })
  }
}

const addScript = () => {
  send({ type: 'SCRIPT_NEW', name: 'New Script' })
}

const deleteScript = (id) => {
  send({ type: 'SCRIPT_DELETE', id })
}

const toggleScriptEnabled = (id, enabled) => {
  // If the currently selected script is being toggled and content matches saved,
  // reflect in draft too
  if (id === selectedScriptId.value) draftEnabled.value = enabled
  send({ type: 'SCRIPT_TOGGLE', id, enabled })
}

const selectScript = (id) => {
  selectedScriptId.value = id
}

const submitRename = (id, newName) => {
  if (!newName.trim()) return
  send({ type: 'SCRIPT_RENAME', id, name: newName.trim() })
  renaming.value = false
}

// ── Python formatter (PEP 8 basics, no external deps) ─────────────────────────
const formatting = ref(false)

const formatCode = () => {
  if (!draftContent.value) return
  formatting.value = true

  let lines = draftContent.value.split('\n')

  // Tabs → 4 spaces, strip trailing whitespace
  lines = lines.map(l => l.replace(/\t/g, '    ').trimEnd())

  // Collapse runs of more than 2 consecutive blank lines
  const collapsed = []
  let blanks = 0
  for (const line of lines) {
    if (line.trim() === '') {
      blanks++
      if (blanks <= 2) collapsed.push(line)
    } else {
      blanks = 0
      collapsed.push(line)
    }
  }

  // Ensure 2 blank lines before top-level def / class / async def
  const result = []
  for (let i = 0; i < collapsed.length; i++) {
    const line = collapsed[i]
    const stripped = line.trimStart()
    const indent = line.length - stripped.length
    const isTopLevel = indent === 0 &&
      (stripped.startsWith('def ') || stripped.startsWith('class ') || stripped.startsWith('async def '))

    if (isTopLevel) {
      let trailingBlanks = 0
      let j = result.length - 1
      while (j >= 0 && result[j].trim() === '') { trailingBlanks++; j-- }
      // Only add blanks if there's actual content above
      if (j >= 0) {
        while (trailingBlanks < 2) { result.push(''); trailingBlanks++ }
      }
    }
    result.push(line)
  }

  // Strip leading blank lines and ensure exactly one trailing newline
  while (result.length > 0 && result[0].trim() === '') result.shift()
  while (result.length > 0 && result[result.length - 1].trim() === '') result.pop()

  draftContent.value = result.join('\n') + '\n'
  setTimeout(() => { formatting.value = false }, 500)
}
</script>

<template>
  <div v-if="showScriptingModal" class="modal-overlay" @mousedown.self="showScriptingModal = false"
       @keydown.shift.alt.f.prevent="formatCode">
    <div class="modal-content">

      <!-- Header -->
      <div class="modal-header">
        <div class="header-left">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
            <polyline points="16 18 22 12 16 6"/>
            <polyline points="8 6 2 12 8 18"/>
          </svg>
          <strong>Scripts</strong>
          <span class="scripts-count">{{ scripts.length }} script{{ scripts.length !== 1 ? 's' : '' }}</span>
        </div>
        <button class="close-btn" @click="showScriptingModal = false">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
            <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
          </svg>
        </button>
      </div>

      <!-- Body: sidebar + editor -->
      <div class="modal-body">

        <!-- Sidebar -->
        <div class="sidebar">
          <div class="sidebar-list">
            <div
              v-for="s in scripts"
              :key="s.id"
              class="script-row"
              :class="{ active: s.id === selectedScriptId, errored: !!s.error }"
              @click="selectScript(s.id)"
            >
              <label class="script-checkbox" @click.stop title="Enable / disable script">
                <input type="checkbox" :checked="s.enabled" @change="toggleScriptEnabled(s.id, $event.target.checked)" />
                <span class="script-checkmark"></span>
              </label>
              <span class="script-name">{{ s.name }}</span>
              <button
                class="script-del"
                @click.stop="deleteScript(s.id)"
                title="Delete script"
              >
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <polyline points="3 6 5 6 21 6"/>
                  <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
                  <line x1="10" y1="11" x2="10" y2="17"/>
                  <line x1="14" y1="11" x2="14" y2="17"/>
                </svg>
              </button>
            </div>
            <div v-if="scripts.length === 0" class="sidebar-empty">
              No scripts yet.<br>Click Add Script to create one.
            </div>
          </div>
          <button class="add-btn" @click="addScript">
            <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round">
              <line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>
            </svg>
            Add Script
          </button>
        </div>

        <!-- Editor panel -->
        <div class="editor-panel" v-if="selectedScript">

          <!-- Editor toolbar -->
          <div class="editor-toolbar">
            <input
              class="name-input"
              v-model="draftName"
              @blur="submitRename(selectedScript.id, draftName)"
              @keydown.enter.prevent="$event.target.blur()"
              placeholder="Script name"
              spellcheck="false"
            />
            <div class="toolbar-right">
              <label class="toggle-row">
                <button class="toggle-btn" :class="{ active: draftEnabled }" @click="toggleEnabled">
                  <span class="toggle-track"><span class="toggle-thumb"/></span>
                  <span class="toggle-text">{{ draftEnabled ? 'On' : 'Off' }}</span>
                </button>
              </label>
              <span v-if="hasUnsavedChanges" class="unsaved-badge">Unsaved</span>
              <button class="format-btn" :class="{ done: formatting }" @click="formatCode" title="Format code (PEP 8) — Shift+Alt+F">
                <svg v-if="!formatting" width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                  <line x1="21" y1="10" x2="7" y2="10"/><line x1="21" y1="6" x2="3" y2="6"/><line x1="21" y1="14" x2="3" y2="14"/><line x1="21" y1="18" x2="7" y2="18"/>
                </svg>
                <svg v-else width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="var(--setup-success)" stroke-width="2.5" stroke-linecap="round">
                  <polyline points="20 6 9 17 4 12"/>
                </svg>
                {{ formatting ? 'Formatted' : 'Format' }}
              </button>
              <button class="save-btn" :class="{ saved: saving }" @click="save">
                <svg v-if="!saving" width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round">
                  <path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/>
                  <polyline points="17 21 17 13 7 13 7 21"/>
                  <polyline points="7 3 7 8 15 8"/>
                </svg>
                <svg v-else width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="var(--setup-success)" stroke-width="2.5" stroke-linecap="round">
                  <polyline points="20 6 9 17 4 12"/>
                </svg>
                {{ saving ? 'Saved' : 'Save' }}
              </button>
            </div>
          </div>

          <!-- CodeMirror -->
          <div class="editor-wrap">
            <Codemirror
              v-model="draftContent"
              :extensions="extensions"
              :autofocus="true"
              style="height: 100%; font-size: 12.5px;"
            />
          </div>

          <!-- Error panel -->
          <div v-if="selectedScript.error" class="error-panel">
            <div class="error-panel-header">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="flex-shrink:0;margin-top:1px">
                <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>
              </svg>
              Script error — auto-disabled
            </div>
            <pre class="error-pre">{{ selectedScript.error }}</pre>
          </div>

        </div>

        <div v-else class="editor-panel empty-panel">
          <p>No script selected</p>
        </div>

      </div>

      <!-- Footer hint -->
      <div class="modal-footer-hint">
        Hooks: <code>request(flow)</code> · <code>response(flow)</code> · <code>websocket_message(flow)</code> · <code>error(flow)</code>
        &nbsp;·&nbsp;
        <a href="#" @click.prevent="openApiDocs">mitmproxy flow API ↗</a>
      </div>

    </div>
  </div>
</template>

<style scoped>
.modal-overlay {
  position: fixed; inset: 0;
  background: var(--overlay);
  display: flex; align-items: center; justify-content: center;
  z-index: 1000;
}
.modal-content {
  background: var(--bg-modal);
  border: 1px solid var(--border);
  border-radius: 10px;
  width: 860px;
  max-width: calc(100vw - 20px);
  height: 560px;
  max-height: calc(100vh - 40px);
  min-width: 500px;
  min-height: 380px;
  display: flex;
  flex-direction: column;
  box-shadow: var(--shadow-lg);
  overflow: hidden;
  resize: both;
}

/* Header */
.modal-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 11px 14px 10px;
  border-bottom: 1px solid var(--border-subtle);
  flex-shrink: 0;
}
.header-left { display: flex; align-items: center; gap: 8px; }
.modal-header strong { font-size: 13px; color: var(--fg-primary); }
.scripts-count { font-size: 11px; color: var(--fg-muted); background: var(--bg-active); border: 1px solid var(--border); border-radius: 4px; padding: 1px 6px; }
.close-btn {
  background: none; border: none; cursor: pointer;
  color: var(--fg-muted); padding: 4px; border-radius: 4px;
  display: flex; align-items: center; justify-content: center;
  transition: background 0.12s, color 0.12s;
}
.close-btn:hover { background: var(--surface-hover-strong); color: var(--fg-primary); }

/* Body layout */
.modal-body {
  display: flex;
  flex: 1;
  overflow: hidden;
}

/* Sidebar */
.sidebar {
  width: 180px;
  flex-shrink: 0;
  border-right: 1px solid var(--border-subtle);
  display: flex;
  flex-direction: column;
  background: var(--bg-sidebar);
}
.sidebar-list { flex: 1; overflow-y: auto; padding: 6px 0; }
.sidebar-empty {
  padding: 30px 14px;
  text-align: center;
  font-size: 11.5px;
  color: var(--fg-placeholder);
  line-height: 1.6;
}
.script-row {
  display: flex; align-items: center; gap: 7px;
  padding: 0 10px;
  height: 36px;
  cursor: pointer;
  font-size: 12.5px; color: var(--fg-secondary);
  transition: background 0.1s;
  position: relative;
  box-sizing: border-box;
}
.script-row:hover { background: var(--surface-hover); }
.script-row.active { background: var(--bg-active); color: var(--fg-primary); }
.script-row.errored .script-name { color: var(--setup-error); }

/* Checkbox */
.script-checkbox {
  display: flex; align-items: center; justify-content: center;
  position: relative; cursor: pointer; user-select: none;
  width: 15px; height: 15px; flex-shrink: 0;
}
.script-checkbox input { position: absolute; opacity: 0; cursor: pointer; height: 0; width: 0; }
.script-checkmark {
  position: absolute; top: 0; left: 0;
  height: 15px; width: 15px;
  background-color: var(--bg-deepest);
  border: 1px solid var(--fg-muted); border-radius: 3px;
  transition: border-color 0.15s, background-color 0.15s;
  box-sizing: border-box;
}
.script-checkbox:hover input ~ .script-checkmark { border-color: var(--accent); }
.script-checkbox input:checked ~ .script-checkmark { background-color: var(--accent); border-color: var(--accent); }
.script-checkmark:after { content: ""; position: absolute; display: none; }
.script-checkbox input:checked ~ .script-checkmark:after { display: block; }
.script-checkbox .script-checkmark:after {
  left: 50%; top: 45%; width: 3px; height: 7px;
  border: solid white; border-width: 0 2px 2px 0;
  transform: translate(-50%, -50%) rotate(45deg);
}

.script-name { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

/* Trashcan */
.script-del {
  background: transparent; border: 1px solid transparent;
  cursor: pointer; color: var(--fg-muted); padding: 3px;
  border-radius: 4px; display: flex; align-items: center; justify-content: center;
  transition: all 0.15s; flex-shrink: 0;
}
.script-del:hover { background: var(--error-muted) !important; border-color: rgba(239,68,68,.3) !important; color: var(--error) !important; }

.add-btn {
  display: flex; align-items: center; gap: 6px;
  margin: 6px 8px;
  padding: 6px 10px;
  font-size: 12px; color: var(--fg-muted);
  background: none; border: 1px dashed var(--border);
  border-radius: 5px; cursor: pointer;
  transition: background 0.12s, color 0.12s, border-color 0.12s;
}
.add-btn:hover { background: var(--surface-hover); color: var(--fg-primary); border-color: var(--fg-muted); }

/* Editor panel */
.editor-panel {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.empty-panel {
  align-items: center; justify-content: center;
  color: var(--fg-placeholder); font-size: 13px;
}

/* Editor toolbar */
.editor-toolbar {
  display: flex; align-items: center; justify-content: space-between;
  padding: 7px 12px;
  border-bottom: 1px solid var(--border-subtle);
  flex-shrink: 0; gap: 10px;
}
.name-input {
  background: none; border: none; outline: none;
  font-size: 12.5px; font-weight: 600; color: var(--fg-primary);
  flex: 1; min-width: 0;
  padding: 2px 4px; border-radius: 3px;
  transition: background 0.1s;
}
.name-input:hover { background: var(--surface-hover); }
.name-input:focus { background: var(--bg-input); box-shadow: 0 0 0 1px var(--border-focus); }

.toolbar-right { display: flex; align-items: center; gap: 8px; }
.toggle-row { display: flex; align-items: center; }
.toggle-btn {
  display: flex; align-items: center; gap: 5px;
  background: none; border: none; cursor: pointer; padding: 0;
}
.toggle-track {
  width: 26px; height: 15px; border-radius: 8px;
  background: var(--bg-active); border: 1px solid var(--border);
  position: relative; transition: background 0.15s, border-color 0.15s;
  display: flex; align-items: center;
}
.toggle-btn.active .toggle-track { background: var(--accent); border-color: var(--accent); }
.toggle-thumb {
  width: 11px; height: 11px; border-radius: 50%;
  background: var(--fg-muted); position: absolute; left: 1px;
  transition: transform 0.15s, background 0.15s;
}
.toggle-btn.active .toggle-thumb { transform: translateX(11px); background: #fff; }
.toggle-text { font-size: 11px; color: var(--fg-muted); min-width: 16px; }

.unsaved-badge {
  font-size: 10.5px; color: var(--fg-muted);
  background: var(--bg-active); border: 1px solid var(--border);
  border-radius: 4px; padding: 2px 6px;
}
.save-btn {
  display: flex; align-items: center; gap: 5px;
  padding: 4px 10px; font-size: 12px; font-weight: 500;
  background: var(--accent); color: #fff;
  border: none; border-radius: 5px; cursor: pointer;
  transition: background 0.12s;
}
.save-btn:hover { background: var(--accent-hover); }
.save-btn.saved { background: rgba(16,185,129,.8); }

.format-btn {
  display: flex; align-items: center; gap: 5px;
  padding: 4px 9px; font-size: 12px; font-weight: 500;
  background: var(--bg-active); color: var(--fg-muted);
  border: 1px solid var(--border); border-radius: 5px; cursor: pointer;
  transition: all 0.12s;
}
.format-btn:hover { background: var(--surface-hover); color: var(--fg-primary); border-color: var(--fg-muted); }
.format-btn.done { color: var(--setup-success); border-color: rgba(16,185,129,.4); }

/* Editor */
.editor-wrap {
  flex: 1; overflow: hidden;
}
.editor-wrap :deep(.cm-editor) { height: 100%; }
.editor-wrap :deep(.cm-scroller) { overflow: auto; }

/* Error panel */
.error-panel {
  flex-shrink: 0;
  background: rgba(239,68,68,.07);
  border-top: 1px solid rgba(239,68,68,.2);
  padding: 9px 12px;
  max-height: 130px; overflow: auto;
}
.error-panel-header {
  display: flex; align-items: center; gap: 6px;
  font-size: 11.5px; font-weight: 600; color: var(--setup-error);
  margin-bottom: 5px;
}
.error-pre {
  font-size: 11px; color: var(--setup-error);
  white-space: pre-wrap; word-break: break-all;
  margin: 0; font-family: 'Menlo', 'Consolas', monospace; line-height: 1.5;
}

/* Footer */
.modal-footer-hint {
  flex-shrink: 0;
  padding: 7px 14px;
  font-size: 11px; color: var(--fg-placeholder);
  border-top: 1px solid var(--border-subtle);
}
.modal-footer-hint code {
  background: var(--bg-active); border-radius: 3px; padding: 1px 4px;
  font-size: 10.5px; color: var(--fg-muted);
}
.modal-footer-hint a { color: var(--accent); text-decoration: none; }
.modal-footer-hint a:hover { text-decoration: underline; }
</style>
