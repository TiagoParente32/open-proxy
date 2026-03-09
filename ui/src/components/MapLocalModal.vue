<script setup>
import { computed } from 'vue'
import { Codemirror } from 'vue-codemirror'
import { json } from '@codemirror/lang-json'
import { oneDark } from '@codemirror/theme-one-dark'
import { EditorView } from '@codemirror/view'

// NEW: Imported enableMapLocal, importRules, exportRules from the store
import { 
  showMapModal, 
  mapLocalRules, 
  selectedRuleId, 
  syncMapLocalRules,
  enableMapLocal,
  importRules,
  exportRules
} from '../store.js'

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
    <div class="modal-content large" style="display: flex;">
      
      <div class="modal-sidebar">
        <div style="padding: 16px; border-bottom: 1px solid var(--border); display: flex; justify-content: space-between; align-items: center;">
          <strong style="color: white; font-size: 13px;">Map Local Rules</strong>
          <button class="action-btn" style="padding: 4px 10px;" @click="addNewRule">+ Add</button>
        </div>
        
        <div class="rule-list">
          <div v-for="rule in mapLocalRules" :key="rule.id" class="rule-item" :class="{ active: selectedRuleId === rule.id }" @click="selectedRuleId = rule.id">
            <input type="checkbox" v-model="rule.active" @click.stop />
            <span class="truncate" style="flex: 1; font-family: monospace; font-size: 11px;">{{ rule.pattern || 'New Rule' }}</span>
            <span style="color: #ef4444; cursor: pointer; padding: 0 4px; font-weight: bold;" @click.stop="deleteRule(rule.id)">×</span>
          </div>
          <div v-if="mapLocalRules.length === 0" class="empty-state" style="padding: 20px;">No rules yet.</div>
        </div>

        <div class="sidebar-footer">
          <div class="toggle" @click="enableMapLocal = !enableMapLocal" :class="{ active: enableMapLocal }">
            <span class="toggle-label">Enable Map Local</span>
            <div class="switch"></div>
          </div>
          
          <div class="divider" style="width: 100%; height: 1px; background: var(--border); margin: 8px 0;"></div>
          
          <div style="display: flex; gap: 8px;">
            <button class="ghost-btn" style="flex: 1; justify-content: center;" @click="exportRules(mapLocalRules, 'OpenProxy_MapLocal')">⬇️ Export</button>
            <label class="ghost-btn" style="flex: 1; justify-content: center; cursor: pointer; margin: 0;">
              ⬆️ Import
              <input type="file" accept=".json" style="display: none;" @change="(e) => importRules(e, mapLocalRules)" />
            </label>
          </div>
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
/* Existing Styles */
.modal-overlay { position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0, 0, 0, 0.7); z-index: 100; display: flex; justify-content: center; align-items: center; backdrop-filter: blur(2px);}
.modal-content.large { 
  background: var(--bg-main); 
  border: 1px solid var(--border); 
  border-radius: 8px; 
  width: 1000px;        /* Unified width */
  height: 650px;        /* Unified height */
  min-width: 800px; 
  min-height: 500px; 
  max-width: 95vw; 
  max-height: 95vh; 
  box-shadow: 0 10px 40px rgba(0,0,0,0.6); 
  resize: both; 
  overflow: hidden; 
}

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

/* --- NEW COMPONENT STYLES --- */
.action-btn { background: #2a2d2e; border: 1px solid #444; color: #ccc; border-radius: 4px; padding: 6px 12px; font-size: 12px; cursor: pointer; transition: all 0.2s; }
.action-btn:hover { background: #333; color: white; border-color: #555; }

.sidebar-footer { padding: 16px; background: #1a1b1c; border-top: 1px solid var(--border); display: flex; flex-direction: column; }

.ghost-btn { display: flex; align-items: center; gap: 4px; height: 26px; padding: 0 8px; background: transparent; border: 1px solid #444; color: #aaa; border-radius: 4px; cursor: pointer; font-size: 11px; font-weight: 500; transition: all 0.2s; }
.ghost-btn:hover { background: rgba(255, 255, 255, 0.08); color: #fff; border-color: #666;}

.toggle { display: flex; align-items: center; justify-content: space-between; cursor: pointer; color: #888; font-weight: 600; transition: color 0.2s; }
.toggle.active { color: #10b981; }
.toggle:hover { color: #ccc; }
.toggle-label { font-size: 12px; }

.switch { width: 32px; height: 18px; background: #111; border: 1px solid #444; border-radius: 14px; position: relative; transition: all 0.3s; box-sizing: border-box;}
.switch::after { content: ''; position: absolute; top: 1px; left: 1px; width: 14px; height: 14px; background: #888; border-radius: 50%; transition: transform 0.3s, background 0.3s; }
.toggle.active .switch { background: rgba(16, 185, 129, 0.15); border-color: #10b981; }
.toggle.active .switch::after { transform: translateX(14px); background: #10b981; }
</style>