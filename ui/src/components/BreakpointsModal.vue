<script setup>
import { computed } from 'vue'
import { 
  showBreakpointModal, 
  breakpointRules, 
  selectedBreakpointId, 
  syncBreakpointRules, 
  breakpointsEnabled,
  importRules,
  exportRules 
} from '../store.js'

const activeRule = computed(() => breakpointRules.value.find(r => r.id === selectedBreakpointId.value))

const addNewRule = () => {
  const newRule = { 
    id: Date.now(), 
    active: true, 
    pattern: 'api.example.com/*', 
    is_request: true, 
    is_response: false 
  }
  breakpointRules.value.unshift(newRule)
  selectedBreakpointId.value = newRule.id
}

const deleteRule = (id) => {
  breakpointRules.value = breakpointRules.value.filter(r => r.id !== id)
  if (selectedBreakpointId.value === id) {
    selectedBreakpointId.value = breakpointRules.value.length ? breakpointRules.value[0].id : null
  }
}

const saveAndApplyRules = () => {
  syncBreakpointRules()
  showBreakpointModal.value = false
}
</script>

<template>
  <div v-if="showBreakpointModal" class="modal-overlay" @mousedown.self="showBreakpointModal = false">
    <div class="modal-content large" style="display: flex;">      
      <div class="modal-sidebar" style="width: 280px; background: var(--bg-sidebar); border-right: 1px solid var(--border); display: flex; flex-direction: column;">
        
        <div style="padding: 16px; border-bottom: 1px solid var(--border); display: flex; justify-content: space-between; align-items: center;">
          <strong style="color: white; font-size: 13px;">Breakpoints</strong>
          <button class="action-btn" style="padding: 4px 10px;" @click="addNewRule">+ Add</button>
        </div>
        
        <div class="rule-list" style="flex: 1; overflow-y: auto;">
          <div v-for="rule in breakpointRules" :key="rule.id" class="rule-item" :class="{ active: selectedBreakpointId === rule.id }" @click="selectedBreakpointId = rule.id">
            <input type="checkbox" v-model="rule.active" @click.stop />
            <div style="flex: 1; display: flex; flex-direction: column; overflow: hidden; padding-left: 8px;">
              <span class="truncate" style="font-family: monospace; font-size: 12px; color: #ccc;">{{ rule.pattern || 'New Rule' }}</span>
              <span style="font-size: 10px; color: #888; margin-top: 2px;">
                {{ rule.is_request ? 'Req' : '' }} {{ rule.is_request && rule.is_response ? '&' : '' }} {{ rule.is_response ? 'Res' : '' }}
              </span>
            </div>
            <span style="color: #ef4444; cursor: pointer; padding: 0 4px; font-weight: bold; font-size: 16px;" @click.stop="deleteRule(rule.id)">×</span>
          </div>
          <div v-if="breakpointRules.length === 0" class="empty-state">No breakpoints set.</div>
        </div>

        <div class="sidebar-footer">
          <div class="toggle" @click="breakpointsEnabled = !breakpointsEnabled" :class="{ active: breakpointsEnabled }">
            <span class="toggle-label">Enable Breakpoints</span>
            <div class="switch"></div>
          </div>
          
          <div class="divider" style="width: 100%; height: 1px; background: var(--border); margin: 8px 0;"></div>
          
          <div style="display: flex; gap: 8px;">
            <button class="ghost-btn" style="flex: 1; justify-content: center;" @click="exportRules(breakpointRules, 'OpenProxy_Breakpoints')">⬇️ Export</button>
            <label class="ghost-btn" style="flex: 1; justify-content: center; cursor: pointer; margin: 0;">
              ⬆️ Import
              <input type="file" accept=".json" style="display: none;" @change="(e) => importRules(e, breakpointRules)" />
            </label>
          </div>
        </div>
      </div>

      <div class="modal-editor" style="flex: 1; display: flex; flex-direction: column; background: var(--bg-main); min-width: 0;">
        <div v-if="activeRule" style="display: flex; flex-direction: column; height: 100%;">
          
          <div style="padding: 24px; flex: 1; overflow-y: auto; display: flex; flex-direction: column; gap: 24px;">
            
            <div class="form-group">
              <label class="modal-label">Matching URL Pattern (Regex)</label>
              <input type="text" v-model="activeRule.pattern" class="modal-input" placeholder="e.g., api\.example\.com/users/.*" style="font-family: monospace;" />
              <span style="font-size: 11px; color: #666; margin-top: 6px;">Traffic matching this regex will be paused.</span>
            </div>

            <div class="form-group">
              <label class="modal-label">Pause On</label>
              <div class="checkbox-group">
                <label class="custom-checkbox">
                  <input type="checkbox" v-model="activeRule.is_request" />
                  <div class="checkbox-box"></div>
                  <span>Request (Before sending to server)</span>
                </label>
                
                <label class="custom-checkbox">
                  <input type="checkbox" v-model="activeRule.is_response" />
                  <div class="checkbox-box"></div>
                  <span>Response (Before sending to client)</span>
                </label>
              </div>
            </div>

          </div>
          
          <div style="padding: 16px 24px; border-top: 1px solid var(--border); display: flex; justify-content: flex-end; gap: 10px; background: var(--bg-sidebar);">
            <button class="action-btn" @click="showBreakpointModal = false">Cancel</button>
            <button class="action-btn" style="background: #f59e0b; color: white; border-color: #f59e0b; padding: 6px 16px; font-weight: bold;" @click="saveAndApplyRules">Save & Apply</button>
          </div>
          
        </div>
        
        <div v-else class="global-empty" style="display: flex; justify-content: center; align-items: center; height: 100%; color: #666; font-style: italic; font-size: 12px;">Select or create a breakpoint rule.</div>
      </div>
      
    </div>
  </div>
</template>

<style scoped>
/* Base Modal Styles */
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

.rule-item { padding: 10px 12px; border-bottom: 1px solid #333; display: flex; align-items: center; cursor: pointer; transition: background 0.2s; }
.rule-item:hover { background: #2a2d2e; }
.rule-item.active { background: rgba(245, 158, 11, 0.15); border-left: 3px solid #f59e0b; padding-left: 9px; }
.empty-state { padding: 40px; text-align: center; color: #666; font-style: italic; font-size: 12px; }

.form-group { display: flex; flex-direction: column; text-align: left; }
.modal-label { font-size: 12px; color: #aaa; margin-bottom: 8px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px;}
.modal-input { width: 100%; background: #111; border: 1px solid #444; color: #ccc; padding: 10px 12px; border-radius: 6px; font-size: 13px; box-sizing: border-box; outline: none; transition: border-color 0.2s; }
.modal-input:focus { border-color: #f59e0b; }
.truncate { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

/* Custom Checkboxes for the Breakpoint rules */
.checkbox-group { display: flex; flex-direction: column; gap: 12px; background: #1a1a1b; padding: 16px; border-radius: 6px; border: 1px solid #333; }
.custom-checkbox { display: flex; align-items: center; gap: 10px; cursor: pointer; font-size: 13px; color: #ccc; user-select: none; }
.custom-checkbox input { display: none; }
.checkbox-box { width: 18px; height: 18px; border: 1px solid #555; border-radius: 4px; display: flex; align-items: center; justify-content: center; transition: all 0.2s; background: #222; }
.custom-checkbox input:checked + .checkbox-box { background: #f59e0b; border-color: #f59e0b; }
.custom-checkbox input:checked + .checkbox-box::after { content: '✓'; color: white; font-size: 12px; font-weight: bold; }
.custom-checkbox:hover .checkbox-box { border-color: #888; }

/* Buttons & Footer (Consistent across all modals) */
.action-btn { background: #2a2d2e; border: 1px solid #444; color: #ccc; border-radius: 4px; padding: 6px 12px; font-size: 12px; cursor: pointer; transition: all 0.2s; }
.action-btn:hover { background: #333; color: white; border-color: #555; }

.sidebar-footer { padding: 16px; background: #1a1b1c; border-top: 1px solid var(--border); display: flex; flex-direction: column; }

.ghost-btn { display: flex; align-items: center; gap: 4px; height: 26px; padding: 0 8px; background: transparent; border: 1px solid #444; color: #aaa; border-radius: 4px; cursor: pointer; font-size: 11px; font-weight: 500; transition: all 0.2s; }
.ghost-btn:hover { background: rgba(255, 255, 255, 0.08); color: #fff; border-color: #666;}

.toggle { display: flex; align-items: center; justify-content: space-between; cursor: pointer; color: #888; font-weight: 600; transition: color 0.2s; }
.toggle.active { color: #f59e0b; } /* Breakpoint Orange */
.toggle:hover { color: #ccc; }
.toggle-label { font-size: 12px; }

.switch { width: 32px; height: 18px; background: #111; border: 1px solid #444; border-radius: 14px; position: relative; transition: all 0.3s; box-sizing: border-box;}
.switch::after { content: ''; position: absolute; top: 1px; left: 1px; width: 14px; height: 14px; background: #888; border-radius: 50%; transition: transform 0.3s, background 0.3s; }
.toggle.active .switch { background: rgba(245, 158, 11, 0.15); border-color: #f59e0b; }
.toggle.active .switch::after { transform: translateX(14px); background: #f59e0b; }
</style>