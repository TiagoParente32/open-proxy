<script setup>
import { computed } from 'vue'
import { Codemirror } from 'vue-codemirror'
import { json } from '@codemirror/lang-json'
import { oneDark } from '@codemirror/theme-one-dark'
import { EditorView } from '@codemirror/view'

import { showMapModal, mapLocalRules, selectedRuleId, syncMapLocalRules } from '../store.js'

const extensions = [json(), oneDark, EditorView.lineWrapping]
const activeRule = computed(() => mapLocalRules.value.find(r => r.id === selectedRuleId.value))

const addNewRule = () => {
  const newRule = { id: Date.now(), active: true, pattern: 'api.example.com/*', status: 200, headers: '{\n  "Content-Type": "application/json"\n}', body: '' }
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
  <div v-if="showMapModal" class="modal-overlay" @mousedown.self="showMapModal = false">
    <div class="modal-content large">
      
      <div class="modal-sidebar">
        <div style="padding: 16px; border-bottom: 1px solid var(--border); display: flex; justify-content: space-between; align-items: center;">
          <strong style="color: white; font-size: 13px;">Map Local Rules</strong>
          <button class="action-btn" @click="addNewRule">+ Add</button>
        </div>
        <div class="rule-list">
          <div v-for="rule in mapLocalRules" :key="rule.id" class="rule-item" :class="{ active: selectedRuleId === rule.id }" @click="selectedRuleId = rule.id">
            <input type="checkbox" v-model="rule.active" @click.stop />
            <span class="truncate" style="flex: 1; font-family: monospace; font-size: 11px;">{{ rule.pattern || 'New Rule' }}</span>
            <span style="color: #ef4444; cursor: pointer; padding: 0 4px; font-weight: bold;" @click.stop="deleteRule(rule.id)">×</span>
          </div>
          <div v-if="mapLocalRules.length === 0" class="empty-state" style="padding: 20px;">No rules yet.</div>
        </div>
      </div>

      <div class="modal-editor">
        <div v-if="activeRule" style="display: flex; flex-direction: column; height: 100%;">
          <div style="padding: 20px 24px; flex: 1; overflow-y: auto; display: flex; flex-direction: column; gap: 16px;">
            <div class="form-group"><label class="modal-label">URL Pattern (Regex)</label><input type="text" v-model="activeRule.pattern" class="modal-input" placeholder="api.example.com/*" /></div>
            <div class="form-group" style="max-width: 150px;"><label class="modal-label">Status Code</label><input type="number" v-model="activeRule.status" class="modal-input" /></div>
            <div class="form-group"><label class="modal-label">Response Headers (JSON)</label>
              <div class="code-editor-wrapper" style="height: 140px; flex-shrink: 0;"><codemirror v-model="activeRule.headers" placeholder="Enter headers as JSON..." :style="{ height: '100%' }" :indent-with-tab="true" :tab-size="2" :extensions="extensions" /></div>
            </div>
            <div class="form-group" style="flex: 1; display: flex; flex-direction: column;"><label class="modal-label">Response Body</label>
              <div class="code-editor-wrapper"><codemirror v-model="activeRule.body" placeholder="Enter JSON response..." :style="{ height: '100%' }" :autofocus="true" :indent-with-tab="true" :tab-size="2" :extensions="extensions" /></div>
            </div>
          </div>
          <div style="padding: 16px 24px; border-top: 1px solid var(--border); display: flex; justify-content: flex-end; gap: 10px; background: var(--bg-sidebar);">
            <button class="action-btn" @click="showMapModal = false">Cancel</button>
            <button class="action-btn" style="background: #3b82f6; color: white; border-color: #3b82f6; padding: 6px 16px;" @click="saveAndApplyRules">Save & Apply</button>
          </div>
        </div>
        <div v-else class="global-empty">Select or create a rule to edit.</div>
      </div>
      
    </div>
  </div>
</template>

<style scoped>
.modal-overlay { position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0, 0, 0, 0.7); z-index: 100; display: flex; justify-content: center; align-items: center; }
.modal-content.large { display: flex; background: var(--bg-main); border: 1px solid var(--border); border-radius: 8px; width: 1100px; height: 750px; min-width: 800px; min-height: 500px; max-width: 95vw; max-height: 95vh; box-shadow: 0 10px 40px rgba(0,0,0,0.6); resize: both; overflow: hidden; }

.modal-sidebar { width: 280px; background: var(--bg-sidebar); border-right: 1px solid var(--border); display: flex; flex-direction: column; }
.rule-list { flex: 1; overflow-y: auto; }
.rule-item { padding: 10px 16px; border-bottom: 1px solid #333; display: flex; align-items: center; gap: 10px; cursor: pointer; transition: background 0.2s; }
.rule-item:hover { background: #2a2d2e; }
.rule-item.active { background: #1e3a5f; }
.empty-state { padding: 40px; text-align: center; color: #666; font-style: italic; font-size: 12px; }

.modal-editor { flex: 1; display: flex; flex-direction: column; background: var(--bg-main); min-width: 0; }
.form-group { display: flex; flex-direction: column; text-align: left; }
.modal-label { font-size: 12px; color: #aaa; margin-bottom: 6px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px;}
.modal-input { width: 100%; background: #111; border: 1px solid #444; color: #ccc; padding: 10px 12px; border-radius: 6px; font-size: 13px; box-sizing: border-box; outline: none; transition: border-color 0.2s; }
.modal-input:focus { border-color: #3b82f6; }
.code-editor-wrapper { flex: 1; border: 1px solid #444; border-radius: 6px; overflow: hidden; font-size: 13px; min-width: 0; max-width: 100%; }
</style>