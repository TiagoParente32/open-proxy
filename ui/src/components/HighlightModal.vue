<script setup>
import { computed, ref } from 'vue'
import { 
  showHighlightModal, 
  highlightRules, 
  importRules, 
  exportRules,
  applyAllHighlightRules,
} from '../store.js'

// We can just keep the selected ID local to the component since it doesn't need to be saved
const selectedRuleId = ref(null)

const activeRule = computed(() => highlightRules.value.find(r => r.id === selectedRuleId.value))

const addNewRule = () => {
  const newRule = { 
    id: Date.now(), 
    active: true, 
    type: 'status', 
    pattern: '500',
    color: 'red' // default color
  }
  highlightRules.value.unshift(newRule)
  selectedRuleId.value = newRule.id
}

const deleteRule = (id) => {
  highlightRules.value = highlightRules.value.filter(r => r.id !== id)
  if (selectedRuleId.value === id) {
    selectedRuleId.value = highlightRules.value.length ? highlightRules.value[0].id : null
  }
}
</script>

<template>
  <div v-if="showHighlightModal" class="modal-overlay" @mousedown.self="applyAllHighlightRules(); showHighlightModal = false;">
    <div class="modal-content large" style="display: flex;">
      
      <div class="modal-sidebar" style="width: 280px; background: var(--bg-sidebar); border-right: 1px solid var(--border); display: flex; flex-direction: column;">
        
        <div style="padding: 16px; border-bottom: 1px solid var(--border); display: flex; justify-content: space-between; align-items: center;">
          <strong style="color: white; font-size: 13px;">Auto-Highlight Rules</strong>
          <button class="action-btn" style="padding: 4px 10px;" @click="addNewRule">+ Add</button>
        </div>
        
        <div style="flex: 1; overflow-y: auto;">
          <div v-for="rule in highlightRules" :key="rule.id" class="rule-item" :class="{ active: selectedRuleId === rule.id }" @click="selectedRuleId = rule.id">
            <input type="checkbox" v-model="rule.active" @click.stop />
            
            <div style="flex: 1; overflow: hidden; padding-left: 8px;">
              <div class="truncate" style="font-family: monospace; font-size: 12px; color: #ccc;">
                {{ rule.pattern || 'Empty Rule' }}
              </div>
              <div class="truncate" style="font-size: 10px; color: #888; margin-top: 2px;">
                {{ rule.type.toUpperCase() }} MATCH
              </div>
            </div>

            <div class="color-indicator" :class="rule.color"></div>
            
            <span style="color: #ef4444; cursor: pointer; padding: 0 4px; font-weight: bold;" @click.stop="deleteRule(rule.id)">×</span>
          </div>
          <div v-if="highlightRules.length === 0" style="padding: 40px; text-align: center; color: #666; font-style: italic; font-size: 12px;">No highlight rules set.</div>
        </div>

        <div class="sidebar-footer">
          <div style="display: flex; gap: 8px;">
            <button class="ghost-btn" style="flex: 1; justify-content: center;" @click="exportRules(highlightRules, 'OpenProxy_Highlights')">⬇️ Export</button>
            <label class="ghost-btn" style="flex: 1; justify-content: center; cursor: pointer; margin: 0;">
              ⬆️ Import
              <input type="file" accept=".json" style="display: none;" @change="(e) => importRules(e, highlightRules)" />
            </label>
          </div>
        </div>
      </div>

      <div style="flex: 1; display: flex; flex-direction: column; background: var(--bg-main);">
        <div v-if="activeRule" style="display: flex; flex-direction: column; height: 100%;">
          
          <div style="padding: 24px; flex: 1; overflow-y: auto; display: flex; flex-direction: column; gap: 24px;">
            
            <div class="form-group">
              <label class="modal-label">Condition Type</label>
              <select v-model="activeRule.type" class="modal-input" style="cursor: pointer;">
                <option value="url">URL Contains</option>
                <option value="status">Status Code Equals</option>
                <option value="method">HTTP Method Equals</option>
              </select>
            </div>

            <div class="form-group">
              <label class="modal-label">Match Value</label>
              <input type="text" v-model="activeRule.pattern" class="modal-input" placeholder="e.g., /api/graphql or 404" style="font-family: monospace;" />
              <span style="font-size: 11px; color: #666; margin-top: 6px;">Any incoming request matching this will be colored automatically.</span>
            </div>

            <div class="form-group">
              <label class="modal-label">Row Color</label>
              <div class="color-picker">
                <div class="color-dot red" :class="{ active: activeRule.color === 'red' }" @click="activeRule.color = 'red'"></div>
                <div class="color-dot yellow" :class="{ active: activeRule.color === 'yellow' }" @click="activeRule.color = 'yellow'"></div>
                <div class="color-dot green" :class="{ active: activeRule.color === 'green' }" @click="activeRule.color = 'green'"></div>
                <div class="color-dot blue" :class="{ active: activeRule.color === 'blue' }" @click="activeRule.color = 'blue'"></div>
              </div>
            </div>

          </div>
          
          <div style="padding: 16px 24px; border-top: 1px solid var(--border); display: flex; justify-content: flex-end; gap: 10px; background: var(--bg-sidebar);">
            <button class="action-btn" @click="showHighlightModal = false">Close</button>
            <button class="action-btn" style="background: #3b82f6; color: white; border-color: #3b82f6; padding: 6px 16px; font-weight: bold;" 
                    @click="applyAllHighlightRules(); showHighlightModal = false;">
              Save & Apply
            </button>
          </div>
          
        </div>
        <div v-else style="display: flex; justify-content: center; align-items: center; height: 100%; color: #666; font-style: italic; font-size: 12px;">Select or create a rule.</div>
      </div>
      
    </div>
  </div>
</template>

<style scoped>
/* Base Modal Styles (Identical to MapLocal/MapRemote) */
.modal-overlay { position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0, 0, 0, 0.7); z-index: 99999; display: flex; justify-content: center; align-items: center; backdrop-filter: blur(2px); }
.modal-content { background: var(--bg-main); border: 1px solid var(--border); border-radius: 8px; box-shadow: 0 10px 40px rgba(0,0,0,0.6); resize: both; overflow: hidden; }

/* 1000x650 unified size */
.modal-content.large { width: 1000px; height: 650px; min-width: 800px; min-height: 500px; max-width: 95vw; max-height: 95vh; }

.rule-item { padding: 10px 12px; border-bottom: 1px solid #333; display: flex; align-items: center; cursor: pointer; transition: background 0.2s; gap: 8px; }
.rule-item:hover { background: #2a2d2e; }
.rule-item.active { background: rgba(59, 130, 246, 0.15); border-left: 3px solid #3b82f6; padding-left: 9px; }

.form-group { display: flex; flex-direction: column; text-align: left; }
.modal-label { font-size: 12px; color: #aaa; margin-bottom: 8px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px;}
.modal-input { width: 100%; background: #111; border: 1px solid #444; color: #ccc; padding: 10px 12px; border-radius: 6px; font-size: 13px; box-sizing: border-box; outline: none; transition: border-color 0.2s; }
.modal-input:focus { border-color: #3b82f6; }
.truncate { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

/* Color Picker Styles */
.color-picker { display: flex; gap: 12px; padding: 8px 0; }
.color-dot { width: 24px; height: 24px; border-radius: 50%; cursor: pointer; border: 2px solid transparent; transition: transform 0.1s, border-color 0.1s; }
.color-dot:hover { transform: scale(1.1); }
.color-dot.active { border-color: white; transform: scale(1.1); box-shadow: 0 0 8px rgba(255,255,255,0.3); }

.color-dot.red, .color-indicator.red { background: #ef4444; }
.color-dot.yellow, .color-indicator.yellow { background: #f59e0b; }
.color-dot.green, .color-indicator.green { background: #10b981; }
.color-dot.blue, .color-indicator.blue { background: #3b82f6; }

.color-indicator { width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0; margin-right: 4px; }

/* Buttons & Footer */
.action-btn { background: #2a2d2e; border: 1px solid #444; color: #ccc; border-radius: 4px; padding: 6px 12px; font-size: 12px; cursor: pointer; transition: all 0.2s; }
.action-btn:hover { background: #333; color: white; border-color: #555; }

.sidebar-footer { padding: 16px; background: #1a1b1c; border-top: 1px solid var(--border); display: flex; flex-direction: column; }
.ghost-btn { display: flex; align-items: center; gap: 4px; height: 26px; padding: 0 8px; background: transparent; border: 1px solid #444; color: #aaa; border-radius: 4px; cursor: pointer; font-size: 11px; font-weight: 500; transition: all 0.2s; }
.ghost-btn:hover { background: rgba(255, 255, 255, 0.08); color: #fff; border-color: #666;}
</style>