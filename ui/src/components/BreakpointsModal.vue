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
  <Teleport to="body">
    <div v-if="showBreakpointModal" class="modal-overlay" @mousedown.self="saveAndApplyRules">
      
      <div class="pm-split-modal">
        
        <div class="pm-sidebar">
          
          <div class="pm-sidebar-header">
            <strong style="color: #e0e0e0; font-size: 13px;">Breakpoint Rules</strong>
            <button class="pm-add-btn" @click="addNewRule">+ Add</button>
          </div>
          
          <div class="pm-rule-list">
            <div v-for="rule in breakpointRules" :key="rule.id" 
                 class="pm-rule-item" 
                 :class="{ active: selectedBreakpointId === rule.id }" 
                 @click="selectedBreakpointId = rule.id">
              
              <label class="pm-checkbox-container" @click.stop>
                <input type="checkbox" v-model="rule.active" />
                <span class="pm-checkmark"></span>
              </label>

              <div class="pm-rule-text-stack">
                <span class="pm-rule-pattern" :title="rule.pattern">{{ rule.pattern || 'New Rule' }}</span>
                <div class="pm-rule-badges">
                  <span v-if="rule.is_request" class="pm-badge req">Req</span>
                  <span v-if="rule.is_response" class="pm-badge res">Res</span>
                  <span v-if="!rule.is_request && !rule.is_response" class="pm-badge none">Inactive</span>
                </div>
              </div>

              <button class="pm-rule-del" @click.stop="deleteRule(rule.id)" title="Delete Rule">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <polyline points="3 6 5 6 21 6"></polyline>
                  <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
                  <line x1="10" y1="11" x2="10" y2="17"></line>
                  <line x1="14" y1="11" x2="14" y2="17"></line>
                </svg>
              </button>

            </div>
            
            <div v-if="breakpointRules.length === 0" class="pm-empty-sidebar">
              No rules yet. Click + Add to start pausing traffic.
            </div>
          </div>

          <div class="pm-sidebar-footer">
            <div class="toggle" @click="breakpointsEnabled = !breakpointsEnabled" :class="{ active: breakpointsEnabled }">
              <span class="toggle-label">Enable Breakpoints</span>
              <div class="switch"></div>
            </div>
            
            <div class="pm-divider-horizontal"></div>
            
            <div style="display: flex; gap: 8px;">
              <button class="ghost-btn" style="flex: 1; justify-content: center;" @click="exportRules(breakpointRules, 'OpenProxy_Breakpoints')">Export</button>
              <label class="ghost-btn" style="flex: 1; justify-content: center; cursor: pointer; margin: 0;">
                Import
                <input type="file" accept=".json" style="display: none;" @change="(e) => importRules(e, breakpointRules)" />
              </label>
            </div>
          </div>
        </div>

        <div class="pm-main-area">
          
          <div v-if="activeRule" style="display: flex; flex-direction: column; height: 100%;">
            
            <div class="pm-header">
              <strong class="pm-title text-amber">Breakpoint Configuration</strong>
              <button class="pm-close-btn" @click="saveAndApplyRules">✕</button>
            </div>

            <div class="pm-editor-area">
              
              <div class="pm-routing-box">
                <div class="pm-routing-header">Intercept Target</div>
                <div class="pm-routing-body">
                  <span class="pm-routing-label">MATCH URL OR REGEX</span>
                  <input type="text" v-model="activeRule.pattern" class="pm-routing-input" placeholder="e.g., api\.example\.com/users/.*" />
                  <div class="pm-routing-helper">Any traffic matching this string or regex will trigger the breakpoint.</div>
                </div>
              </div>

              <div class="pm-routing-arrow">
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#f59e0b" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <line x1="12" y1="5" x2="12" y2="19"></line>
                  <polyline points="19 12 12 19 5 12"></polyline>
                </svg>
              </div>

              <div class="pm-routing-box target">
                <div class="pm-routing-header target-header">Trigger Phases</div>
                <div class="pm-routing-body-generous">
                  <span class="pm-routing-label">PAUSE TRAFFIC ON</span>
                  
                  <div class="pm-phase-options">
                    <label class="pm-custom-checkbox-large">
                      <input type="checkbox" v-model="activeRule.is_request" />
                      <div class="pm-large-box"></div>
                      <div class="pm-large-text">
                        <strong>Request</strong>
                        <span>Pause before sending data to the server</span>
                      </div>
                    </label>

                    <label class="pm-custom-checkbox-large">
                      <input type="checkbox" v-model="activeRule.is_response" />
                      <div class="pm-large-box"></div>
                      <div class="pm-large-text">
                        <strong>Response</strong>
                        <span>Pause before sending data back to the client</span>
                      </div>
                    </label>
                  </div>
                </div>
              </div>

            </div>

            <div class="pm-footer">
              <button class="pm-btn-cancel" @click="showBreakpointModal = false">Cancel</button>
              <button class="pm-btn-execute" @click="saveAndApplyRules">Save & Apply</button>
            </div>

          </div>
          
          <div v-else class="pm-main-empty">
            Select or create a rule to configure breakpoints.
          </div>

        </div>

      </div>
    </div>
  </Teleport>
</template>

<style scoped>
/* OVERLAY & MODAL */
.modal-overlay { position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0, 0, 0, 0.7); z-index: 99999; display: flex; justify-content: center; align-items: center; backdrop-filter: blur(4px); }
.pm-split-modal { background: #1e1e1e; border-radius: 8px; border: 1px solid #333; width: 1000px; height: 650px; display: flex; flex-direction: row; box-shadow: 0 20px 50px rgba(0,0,0,0.5); overflow: hidden; }

/* SIDEBAR STYLES */
.pm-sidebar { width: 300px; background: #1a1a1b; border-right: 1px solid #333; display: flex; flex-direction: column; flex-shrink: 0; }
.pm-sidebar-header { padding: 16px; border-bottom: 1px solid #333; display: flex; justify-content: space-between; align-items: center; background: #222;}
.pm-add-btn { background: rgba(245, 158, 11, 0.1); color: #f59e0b; border: 1px solid rgba(245, 158, 11, 0.3); padding: 4px 10px; border-radius: 4px; font-size: 11px; font-weight: 600; cursor: pointer; transition: all 0.2s; }
.pm-add-btn:hover { background: #f59e0b; color: white; border-color: #f59e0b; }

.pm-rule-list { flex: 1; overflow-y: auto; }
.pm-rule-item { height: 46px; padding: 0 16px; border-bottom: 1px solid #2a2a2b; display: flex; align-items: center; gap: 12px; cursor: pointer; transition: background 0.2s; box-sizing: border-box; }
.pm-rule-item:hover { background: #222; }
.pm-rule-item.active { background: rgba(245, 158, 11, 0.08); border-left: 3px solid #f59e0b; padding-left: 13px; }

/* Sleek Checkbox */
.pm-checkbox-container { display: flex; align-items: center; justify-content: center; position: relative; cursor: pointer; user-select: none; width: 16px; height: 16px; flex-shrink: 0; margin: 0; }
.pm-checkbox-container input { position: absolute; opacity: 0; cursor: pointer; height: 0; width: 0; }
.pm-checkmark { position: absolute; top: 0; left: 0; height: 16px; width: 16px; background-color: #111; border: 1px solid #555; border-radius: 4px; transition: border-color 0.2s, background-color 0.2s; box-sizing: border-box; }
.pm-checkbox-container:hover input ~ .pm-checkmark { border-color: #f59e0b; }
.pm-checkbox-container input:checked ~ .pm-checkmark { background-color: #f59e0b; border-color: #f59e0b; }
.pm-checkmark:after { content: ""; position: absolute; display: none; }
.pm-checkbox-container input:checked ~ .pm-checkmark:after { display: block; }
.pm-checkbox-container .pm-checkmark:after { left: 50%; top: 45%; width: 4px; height: 9px; border: solid white; border-width: 0 2px 2px 0; transform: translate(-50%, -50%) rotate(45deg); }

/* Stacked Rule Text & Badges */
.pm-rule-text-stack { flex: 1; display: flex; flex-direction: column; min-width: 0; justify-content: center; gap: 4px;}
.pm-rule-pattern { font-family: 'Consolas', monospace; font-size: 11px; color: #ccc; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; line-height: 1; }
.pm-rule-item.active .pm-rule-pattern { color: #fff; font-weight: bold; }
.pm-rule-badges { display: flex; gap: 4px; }
.pm-badge { font-size: 9px; font-weight: 700; text-transform: uppercase; padding: 2px 6px; border-radius: 4px; border: 1px solid transparent; }
.pm-badge.req { color: #3b82f6; background: rgba(59, 130, 246, 0.15); border-color: rgba(59, 130, 246, 0.3); }
.pm-badge.res { color: #10b981; background: rgba(16, 185, 129, 0.15); border-color: rgba(16, 185, 129, 0.3); }
.pm-badge.none { color: #666; background: #222; border-color: #444; }

/* Trashcan */
.pm-rule-del { background: transparent; border: 1px solid transparent; color: #666; cursor: pointer; padding: 5px; border-radius: 6px; display: flex; align-items: center; justify-content: center; transition: all 0.2s; }
.pm-rule-item:hover .pm-rule-del { background: #2a2d2e; border-color: #333; color: #888; }
.pm-rule-del:hover { background: rgba(239, 68, 68, 0.15) !important; border-color: rgba(239, 68, 68, 0.4) !important; color: #ef4444 !important; }

.pm-empty-sidebar { padding: 40px 20px; text-align: center; color: #666; font-size: 12px; line-height: 1.5; }

/* Sidebar Footer & Toggles */
.pm-sidebar-footer { padding: 16px; background: #151515; border-top: 1px solid #333; display: flex; flex-direction: column; gap: 12px;}
.toggle { display: flex; align-items: center; justify-content: space-between; cursor: pointer; color: #888; font-weight: 600; transition: color 0.2s; }
.toggle.active { color: #f59e0b; }
.toggle:hover { color: #ccc; }
.toggle-label { font-size: 12px; }
.switch { width: 32px; height: 18px; background: #111; border: 1px solid #444; border-radius: 14px; position: relative; transition: all 0.3s; box-sizing: border-box;}
.switch::after { content: ''; position: absolute; top: 1px; left: 1px; width: 14px; height: 14px; background: #888; border-radius: 50%; transition: transform 0.3s, background 0.3s; }
.toggle.active .switch { background: rgba(245, 158, 11, 0.15); border-color: #f59e0b; }
.toggle.active .switch::after { transform: translateX(14px); background: #f59e0b; }
.pm-divider-horizontal { width: 100%; height: 1px; background: #333; }
.ghost-btn { display: flex; align-items: center; gap: 4px; height: 26px; padding: 0 8px; background: transparent; border: 1px solid #444; color: #aaa; border-radius: 4px; cursor: pointer; font-size: 11px; font-weight: 500; transition: all 0.2s; }
.ghost-btn:hover { background: rgba(255, 255, 255, 0.08); color: #fff; border-color: #666;}

/* MAIN EDITOR STYLES */
.pm-main-area { flex: 1; display: flex; flex-direction: column; background: #1e1e1e; min-width: 0; }
.pm-main-empty { flex: 1; display: flex; justify-content: center; align-items: center; color: #555; font-size: 13px; }
.pm-header { display: flex; justify-content: space-between; align-items: center; padding: 12px 20px; background: #252525; border-bottom: 1px solid #333; flex-shrink: 0; }
.pm-title { font-size: 13px; font-weight: 700; }
.text-amber { color: #f59e0b !important; }
.pm-close-btn { background: transparent; border: none; color: #888; font-size: 16px; cursor: pointer; transition: color 0.2s; }
.pm-close-btn:hover { color: #ef4444; }

.pm-editor-area { flex: 1; padding: 24px; display: flex; flex-direction: column; overflow-y: auto; }

/* Custom Configuration UI */
.pm-routing-box { background: #1a1a1b; border: 1px solid #333; border-radius: 8px; overflow: hidden; flex-shrink: 0; }
.pm-routing-header { background: #222; padding: 10px 16px; font-size: 12px; font-weight: 700; color: #ccc; border-bottom: 1px solid #333; }
.pm-routing-header.target-header { background: rgba(245, 158, 11, 0.1); color: #fbbf24; border-bottom-color: rgba(245, 158, 11, 0.2); }
.pm-routing-box.target { border-color: rgba(245, 158, 11, 0.3); }

.pm-routing-body { padding: 16px; display: flex; flex-direction: column; gap: 8px; }
/* THIS FIXES THE BOTTOM EDGE CLIPPING */
.pm-routing-body-generous { padding: 16px 16px 24px 16px; display: flex; flex-direction: column; gap: 8px; }

.pm-routing-label { font-size: 11px; font-weight: 600; color: #888; letter-spacing: 0.5px; }
.pm-routing-input { width: 100%; background: #111; border: 1px solid #444; color: #fff; padding: 12px 16px; border-radius: 6px; font-size: 14px; font-family: 'Consolas', monospace; outline: none; transition: border-color 0.2s, box-shadow 0.2s; box-sizing: border-box; }
.pm-routing-input:focus { border-color: #3b82f6; box-shadow: 0 0 0 1px #3b82f6; }
.pm-routing-helper { font-size: 11px; color: #666; margin-top: 4px; }
.pm-routing-arrow { display: flex; justify-content: center; align-items: center; padding: 16px 0; flex-shrink: 0; }

/* Phase Checkboxes */
.pm-phase-options { display: flex; flex-direction: column; gap: 12px; margin-top: 8px; }
.pm-custom-checkbox-large { 
  display: flex; 
  align-items: flex-start; 
  gap: 12px; 
  cursor: pointer; 
  padding: 14px 16px; /* Enhanced internal breathing room */
  background: #222; 
  border: 1px solid #333; 
  border-radius: 6px; 
  transition: all 0.2s; 
  user-select: none; 
}
.pm-custom-checkbox-large:hover { border-color: #555; background: #252526; }
.pm-custom-checkbox-large input { display: none; }
.pm-large-box { width: 18px; height: 18px; border: 1px solid #666; border-radius: 4px; display: flex; align-items: center; justify-content: center; transition: all 0.2s; background: #111; flex-shrink: 0; margin-top: 2px;}
.pm-custom-checkbox-large input:checked + .pm-large-box { background: #f59e0b; border-color: #f59e0b; }
.pm-custom-checkbox-large input:checked + .pm-large-box::after { content: '✓'; color: white; font-size: 13px; font-weight: bold; }
.pm-large-text { display: flex; flex-direction: column; gap: 4px; }
.pm-large-text strong { font-size: 13px; color: #e0e0e0; line-height: 1.2; }
.pm-large-text span { font-size: 11px; color: #888; line-height: 1.4; display: block; }
.pm-custom-checkbox-large input:checked ~ .pm-large-text strong { color: #f59e0b; }

.pm-footer { display: flex; justify-content: flex-end; gap: 12px; padding: 16px 20px; background: #1a1a1b; border-top: 1px solid #333; flex-shrink: 0; }
.pm-btn-cancel { background: transparent; color: #ccc; border: 1px solid #444; border-radius: 6px; padding: 8px 24px; font-weight: 600; font-size: 13px; cursor: pointer; transition: all 0.2s; }
.pm-btn-cancel:hover { background: #333; color: white; border-color: #555; }
.pm-btn-execute { background: #f59e0b; color: white; border: none; border-radius: 6px; padding: 8px 32px; font-weight: 600; font-size: 13px; cursor: pointer; transition: background 0.2s; }
.pm-btn-execute:hover { background: #d97706; }
</style>