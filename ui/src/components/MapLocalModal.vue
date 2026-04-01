<script setup>
import { computed, ref, watch } from 'vue'
import { Codemirror } from 'vue-codemirror'
import { json } from '@codemirror/lang-json'
import { oneDark } from '@codemirror/theme-one-dark'
import { EditorView } from '@codemirror/view'

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
const extensions = [json(), oneDark, EditorView.lineWrapping]
const activeRule = computed(() => mapLocalRules.value.find(r => r.id === selectedRuleId.value))
const activeTab = ref('Body')
const queryParams = ref([{ key: '', value: '' }])

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

// --- 3. WATCHERS ---

// Auto-select the first rule if nothing is selected but rules exist
watch(mapLocalRules, (newRules) => {
  if (newRules.length > 0 && !selectedRuleId.value) {
    selectedRuleId.value = newRules[0].id
  }
}, { immediate: true, deep: true })

// Sync params when the active rule changes (e.g. clicking a different rule in the sidebar)
watch(activeRule, (rule) => {
  if (rule) {
    syncPatternToParams()
  }
}, { immediate: true })

// Sync params when the modal opens (e.g. intercepted request triggered it)
watch(showMapModal, (isOpen) => {
  if (isOpen && activeRule.value) {
    syncPatternToParams()
  }
})

// --- 4. RULE MANAGEMENT ---

const addNewRule = () => {
  const newRule = {
    id: Date.now(),
    active: true,
    label: '',
    pattern: 'api.example.com/*',
    status: 200,
    headers: '{\n  "Content-Type": "application/json"\n}',
    body: ''
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
</script>

<template>
  <Teleport to="body">
    <div v-if="showMapModal" class="modal-overlay" @mousedown.self="saveAndApplyRules">

      <div class="pm-split-modal">

        <div class="pm-sidebar">
          <div class="pm-sidebar-header">
            <strong style="color: #e0e0e0; font-size: 13px;">Map Local Rules</strong>
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
                <span v-if="rule.label" class="pm-rule-subtext">{{ rule.pattern }}</span>
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
              <strong class="pm-title text-blue">Mock Response Editor</strong>
              <button class="pm-close-btn" @click="saveAndApplyRules">✕</button>
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
                <div class="pm-method-display read-only">URL MATCH</div>
                <div class="pm-divider"></div>
                <input type="text" v-model="activeRule.pattern" class="pm-url-input"
                  placeholder="e.g., api.example.com/*" @input="syncPatternToParams" />
                <div class="pm-divider"></div>
                <div class="pm-status-wrapper">
                  <span class="pm-status-label">Status</span>
                  <input type="number" v-model.number="activeRule.status" class="pm-status-input" />
                </div>
              </div>
            </div>

            <div class="pm-tabs">

              <span class="pm-tab" :class="{ active: activeTab === 'Body' }" @click="activeTab = 'Body'">Body</span>
              <span class="pm-tab" :class="{ active: activeTab === 'Params' }"
                @click="activeTab = 'Params'">Params</span>
              <span class="pm-tab" :class="{ active: activeTab === 'Headers' }"
                @click="activeTab = 'Headers'">Headers</span>
            </div>

            <div class="pm-editor-area">
              <div v-if="activeTab === 'Body'" class="pm-editor-wrapper">
                <div class="pm-helper-text">Response Payload (Returned to client)</div>
                <codemirror v-model="activeRule.body" :extensions="extensions" class="pm-codemirror" />
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
              <div v-if="activeTab === 'Headers'" class="pm-editor-wrapper">
                <div class="pm-helper-text">Response Headers (Format as JSON)</div>
                <codemirror v-model="activeRule.headers" :extensions="extensions" class="pm-codemirror" />
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
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.7);
  z-index: 99999;
  display: flex;
  justify-content: center;
  align-items: center;
  backdrop-filter: blur(4px);
}

.pm-split-modal {
  background: #1e1e1e;
  border-radius: 8px;
  border: 1px solid #333;
  width: 1000px;
  height: 650px;
  display: flex;
  flex-direction: row;
  box-shadow: 0 20px 50px rgba(0, 0, 0, 0.5);
  overflow: hidden;
}

.pm-sidebar {
  width: 300px;
  background: #1a1a1b;
  border-right: 1px solid #333;
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
}

.pm-sidebar-header {
  padding: 16px;
  border-bottom: 1px solid #333;
  display: flex;
  justify-content: space-between;
  align-items: center;
  background: #222;
}

.pm-add-btn {
  background: rgba(59, 130, 246, 0.1);
  color: #3b82f6;
  border: 1px solid rgba(59, 130, 246, 0.3);
  padding: 4px 10px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
}

.pm-add-btn:hover {
  background: #3b82f6;
  color: white;
  border-color: #3b82f6;
}

.pm-rule-list {
  flex: 1;
  overflow-y: auto;
}

.pm-rule-item {
  min-height: 48px;
  padding: 0 16px;
  border-bottom: 1px solid #2a2a2b;
  display: flex;
  align-items: center;
  gap: 12px;
  cursor: pointer;
  box-sizing: border-box;
}

.pm-rule-item:hover {
  background: #222;
}

.pm-rule-item.active {
  background: #252d38;
  border-left: 3px solid #3b82f6;
  padding-left: 13px;
}

/* Reverted Empty States */
.empty-state {
  padding: 40px;
  text-align: center;
  color: #666;
  font-style: italic;
  font-size: 12px;
}

.pm-main-empty {
  flex: 1;
  display: flex;
  justify-content: center;
  align-items: center;
  color: #666;
  font-style: italic;
  font-size: 12px;
}

/* Text Stack */
.pm-rule-text-stack {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.pm-rule-pattern {
  font-family: 'Consolas', monospace;
  font-size: 11px;
  color: #ccc;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  line-height: 1.2;
}

.pm-rule-subtext {
  font-size: 9px;
  color: #666;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  margin-top: 2px;
}

/* Checkbox */
.pm-checkbox-container {
  display: flex;
  align-items: center;
  justify-content: center;
  position: relative;
  width: 16px;
  height: 16px;
  flex-shrink: 0;
  cursor: pointer;
}

.pm-checkbox-container input {
  position: absolute;
  opacity: 0;
}

.pm-checkmark {
  position: absolute;
  top: 0;
  left: 0;
  height: 16px;
  width: 16px;
  background-color: #111;
  border: 1px solid #555;
  border-radius: 4px;
}

.pm-checkbox-container input:checked~.pm-checkmark {
  background-color: #3b82f6;
  border-color: #3b82f6;
}

.pm-checkmark:after {
  content: "";
  position: absolute;
  display: none;
  left: 50%;
  top: 45%;
  width: 4px;
  height: 9px;
  border: solid white;
  border-width: 0 2px 2px 0;
  transform: translate(-50%, -50%) rotate(45deg);
}

.pm-checkbox-container input:checked~.pm-checkmark:after {
  display: block;
}

/* Trashcan */
.pm-rule-del {
  background: transparent;
  border: none;
  color: #666;
  cursor: pointer;
  padding: 5px;
  border-radius: 6px;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
}

.pm-rule-item:hover .pm-rule-del {
  color: #888;
}

.pm-rule-del:hover {
  background: rgba(239, 68, 68, 0.15) !important;
  color: #ef4444 !important;
}

.pm-sidebar-footer {
  padding: 16px;
  background: #151515;
  border-top: 1px solid #333;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.toggle {
  display: flex;
  align-items: center;
  justify-content: space-between;
  cursor: pointer;
  color: #888;
  font-weight: 600;
}

.toggle.active {
  color: #10b981;
}

.switch {
  width: 32px;
  height: 18px;
  background: #111;
  border: 1px solid #444;
  border-radius: 14px;
  position: relative;
}

.switch::after {
  content: '';
  position: absolute;
  top: 1px;
  left: 1px;
  width: 14px;
  height: 14px;
  background: #888;
  border-radius: 50%;
  transition: transform 0.3s;
}

.toggle.active .switch::after {
  transform: translateX(14px);
  background: #10b981;
}

.pm-divider-horizontal {
  width: 100%;
  height: 1px;
  background: #333;
}

.ghost-btn {
  display: flex;
  align-items: center;
  gap: 4px;
  height: 26px;
  padding: 0 8px;
  background: transparent;
  border: 1px solid #444;
  color: #aaa;
  border-radius: 4px;
  cursor: pointer;
  font-size: 11px;
}

/* MAIN EDITOR */
.pm-main-area {
  flex: 1;
  display: flex;
  flex-direction: column;
  background: #1e1e1e;
  min-width: 0;
}

.pm-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 20px;
  background: #252525;
  border-bottom: 1px solid #333;
}

.pm-title {
  font-size: 13px;
  font-weight: 700;
  color: #3b82f6;
}

.pm-close-btn {
  background: transparent;
  border: none;
  color: #888;
  font-size: 16px;
  cursor: pointer;
}

.pm-label-container {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.pm-routing-label {
  font-size: 11px;
  font-weight: 600;
  color: #888;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.pm-routing-input {
  background: #111;
  border: 1px solid #444;
  color: #eee;
  padding: 10px 12px;
  border-radius: 6px;
  font-size: 13px;
  outline: none;
}

.pm-routing-input:focus {
  border-color: #3b82f6;
}

.pm-omnibar-container {
  padding: 12px 20px;
}

.pm-omnibar {
  display: flex;
  align-items: center;
  background: #121212;
  border: 1px solid #444;
  border-radius: 6px;
}

.pm-url-input {
  flex: 1;
  background: transparent;
  border: none;
  color: #e0e0e0;
  padding: 10px 12px;
  font-size: 13px;
  outline: none;
  font-family: 'Consolas', monospace;
}

.pm-divider {
  width: 1px;
  height: 24px;
  background: #333;
}

.pm-method-display.read-only {
  padding: 10px 16px;
  font-weight: 700;
  font-size: 11px;
  color: #888;
}

.pm-status-wrapper {
  display: flex;
  align-items: center;
  padding: 0 12px;
  gap: 8px;
}

.pm-status-input {
  background: #111;
  border: 1px solid #444;
  color: #10b981;
  padding: 4px 8px;
  border-radius: 4px;
  font-size: 13px;
  font-weight: bold;
  width: 60px;
  text-align: center;
}

.pm-tabs {
  display: flex;
  gap: 24px;
  padding: 0 24px;
  border-bottom: 1px solid #333;
}

.pm-tab {
  color: #888;
  font-size: 13px;
  padding: 10px 0;
  cursor: pointer;
  border-bottom: 2px solid transparent;
}

.pm-tab.active {
  color: #e0e0e0;
  border-bottom-color: #3b82f6;
}

.pm-editor-area {
  flex: 1;
  display: flex;
  flex-direction: column;
  background: #111;
  overflow: hidden;
}

.pm-editor-wrapper {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.pm-helper-text {
  font-size: 11px;
  color: #666;
  padding: 8px 24px;
  background: #181818;
}

.pm-codemirror {
  flex: 1;
  overflow: hidden;
  font-size: 13px;
}

.pm-codemirror :deep(.cm-editor) {
  height: 100% !important;
}

.pm-footer {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  padding: 16px 20px;
  background: #1a1a1b;
  border-top: 1px solid #333;
}

.pm-btn-cancel {
  background: transparent;
  border: 1px solid #444;
  color: #ccc;
  padding: 8px 24px;
  border-radius: 6px;
  cursor: pointer;
}

.pm-btn-execute {
  background: #3b82f6;
  border: none;
  color: white;
  padding: 8px 32px;
  border-radius: 6px;
  cursor: pointer;
  font-weight: 600;
}

.pm-params-container {
  padding: 16px 24px;
  overflow-y: auto;
  flex: 1;
}

.pm-param-header {
  display: flex;
  font-size: 11px;
  color: #888;
  font-weight: 600;
  padding-bottom: 8px;
  border-bottom: 1px solid #333;
  margin-bottom: 8px;
}

.pm-param-col {
  flex: 1;
  padding: 0 8px;
}

.pm-param-action {
  width: 32px;
}

.pm-param-row {
  display: flex;
  gap: 8px;
  margin-bottom: 8px;
  align-items: center;
}

.pm-param-input {
  flex: 1;
  background: transparent;
  border: 1px solid #333;
  color: #ccc;
  padding: 6px 10px;
  font-size: 13px;
  font-family: 'Consolas', monospace;
  border-radius: 4px;
  outline: none;
}

.pm-param-input:focus {
  border-color: #3b82f6;
  background: #1a1a1b;
}

.pm-param-del {
  background: transparent;
  border: none;
  color: #555;
  cursor: pointer;
  width: 32px;
  font-size: 14px;
}

.pm-param-del:hover {
  color: #ef4444;
}
</style>