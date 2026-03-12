<script setup>
import { computed, ref } from 'vue'
import { 
  showHighlightModal, 
  highlightRules, 
  importRules, 
  exportRules,
  applyAllHighlightRules,
} from '../store.js'

const selectedRuleId = ref(null)

const activeRule = computed(() => highlightRules.value.find(r => r.id === selectedRuleId.value))

// --- Custom Dropdown State ---
const showTypeMenu = ref(false)
const typeOptions = [
  { value: 'url', label: 'URL Contains' },
  { value: 'status', label: 'Status Code Equals' },
  { value: 'method', label: 'HTTP Method Equals' }
]

const getTypeLabel = (val) => {
  const opt = typeOptions.find(o => o.value === val)
  return opt ? opt.label : 'Select Condition'
}

const selectType = (val) => {
  if (activeRule.value) activeRule.value.type = val
  showTypeMenu.value = false
}
// -----------------------------

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
  <Teleport to="body">
    <div v-if="showHighlightModal" class="modal-overlay" @mousedown.self="applyAllHighlightRules(); showHighlightModal = false;">
      
      <div class="pm-split-modal">
        
        <div class="pm-sidebar">
          
          <div class="pm-sidebar-header">
            <strong style="color: #e0e0e0; font-size: 13px;">Auto-Highlight Rules</strong>
            <button class="pm-add-btn" @click="addNewRule">+ Add</button>
          </div>
          
          <div class="pm-rule-list">
            <div v-for="rule in highlightRules" :key="rule.id" 
                 class="pm-rule-item" 
                 :class="{ active: selectedRuleId === rule.id }" 
                 @click="selectedRuleId = rule.id">
              
              <label class="pm-checkbox-container" @click.stop>
                <input type="checkbox" v-model="rule.active" />
                <span class="pm-checkmark"></span>
              </label>

              <div class="pm-rule-text-stack">
                <span class="pm-rule-pattern" :title="rule.pattern">{{ rule.pattern || 'Empty Rule' }}</span>
                <span class="pm-rule-target">{{ rule.type.toUpperCase() }} MATCH</span>
              </div>

              <div class="pm-color-indicator" :class="rule.color"></div>

              <button class="pm-rule-del" @click.stop="deleteRule(rule.id)" title="Delete Rule">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <polyline points="3 6 5 6 21 6"></polyline>
                  <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
                  <line x1="10" y1="11" x2="10" y2="17"></line>
                  <line x1="14" y1="11" x2="14" y2="17"></line>
                </svg>
              </button>

            </div>
            
            <div v-if="highlightRules.length === 0" class="pm-empty-sidebar">
              No highlight rules set. Click + Add to start coloring traffic.
            </div>
          </div>

          <div class="pm-sidebar-footer" style="margin-top: auto;">
            <div style="display: flex; gap: 8px;">
              <button class="ghost-btn" style="flex: 1; justify-content: center;" @click="exportRules(highlightRules, 'OpenProxy_Highlights')">Export</button>
              <label class="ghost-btn" style="flex: 1; justify-content: center; cursor: pointer; margin: 0;">
                 Import
                <input type="file" accept=".json" style="display: none;" @change="(e) => importRules(e, highlightRules)" />
              </label>
            </div>
          </div>
        </div>

        <div class="pm-main-area">
          
          <div v-if="activeRule" style="display: flex; flex-direction: column; height: 100%;">
            
            <div class="pm-header">
              <strong class="pm-title text-blue">Highlight Configuration</strong>
              <button class="pm-close-btn" @click="applyAllHighlightRules(); showHighlightModal = false;">✕</button>
            </div>

            <div class="pm-editor-area">
              
              <div class="pm-routing-box">
                <div class="pm-routing-header">Match Condition</div>
                <div class="pm-routing-body">
                  
                  <span class="pm-routing-label">CONDITION TYPE</span>
                  
                  <div class="pm-custom-select-wrapper">
                    <div class="pm-custom-select-display" @click="showTypeMenu = !showTypeMenu">
                      {{ getTypeLabel(activeRule.type) }}
                      <svg class="pm-chevron" viewBox="0 0 24 24"><path d="M7 10l5 5 5-5z"/></svg>
                    </div>
                    
                    <div v-if="showTypeMenu" class="pm-dropdown-overlay" @click.stop="showTypeMenu = false"></div>
                    
                    <div v-if="showTypeMenu" class="pm-custom-select-dropdown">
                      <div v-for="opt in typeOptions" :key="opt.value"
                           class="pm-custom-select-option"
                           :class="{ selected: activeRule.type === opt.value }"
                           @click="selectType(opt.value)">
                        {{ opt.label }}
                      </div>
                    </div>
                  </div>

                  <span class="pm-routing-label" style="margin-top: 8px;">MATCH VALUE</span>
                  <input type="text" v-model="activeRule.pattern" class="pm-routing-input" placeholder="e.g., /api/graphql or 404" />
                  <div class="pm-routing-helper">Any incoming request matching this condition will be colored automatically.</div>
                  
                </div>
              </div>

              <div class="pm-routing-arrow">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#3b82f6" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <line x1="12" y1="4" x2="12" y2="20"></line>
                  <polyline points="18 14 12 20 6 14"></polyline>
                </svg>
              </div>

              <div class="pm-routing-box target">
                <div class="pm-routing-header target-header">Appearance</div>
                <div class="pm-routing-body">
                  <span class="pm-routing-label">TABLE ROW COLOR</span>
                  
                  <div class="pm-color-picker">
                    <div class="pm-color-dot red" :class="{ active: activeRule.color === 'red' }" @click="activeRule.color = 'red'"></div>
                    <div class="pm-color-dot yellow" :class="{ active: activeRule.color === 'yellow' }" @click="activeRule.color = 'yellow'"></div>
                    <div class="pm-color-dot green" :class="{ active: activeRule.color === 'green' }" @click="activeRule.color = 'green'"></div>
                    <div class="pm-color-dot blue" :class="{ active: activeRule.color === 'blue' }" @click="activeRule.color = 'blue'"></div>
                  </div>
                  <div class="pm-routing-helper" style="margin-top: 4px;">Select the color applied to the traffic table when this rule triggers.</div>

                </div>
              </div>

            </div>

            <div class="pm-footer">
              <button class="pm-btn-cancel" @click="showHighlightModal = false">Cancel</button>
              <button class="pm-btn-execute" @click="applyAllHighlightRules(); showHighlightModal = false;">Save & Apply</button>
            </div>

          </div>
          
          <div v-else class="pm-main-empty">
            Select or create a rule to configure highlights.
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
.pm-add-btn { background: rgba(59, 130, 246, 0.1); color: #3b82f6; border: 1px solid rgba(59, 130, 246, 0.3); padding: 4px 10px; border-radius: 4px; font-size: 11px; font-weight: 600; cursor: pointer; transition: all 0.2s; }
.pm-add-btn:hover { background: #3b82f6; color: white; border-color: #3b82f6; }

.pm-rule-list { flex: 1; overflow-y: auto; }
.pm-rule-item { height: 46px; padding: 0 16px; border-bottom: 1px solid #2a2a2b; display: flex; align-items: center; gap: 12px; cursor: pointer; transition: background 0.2s; box-sizing: border-box; }
.pm-rule-item:hover { background: #222; }
.pm-rule-item.active { background: rgba(59, 130, 246, 0.08); border-left: 3px solid #3b82f6; padding-left: 13px; }

/* Sleek Checkbox - Blue Theme */
.pm-checkbox-container { display: flex; align-items: center; justify-content: center; position: relative; cursor: pointer; user-select: none; width: 16px; height: 16px; flex-shrink: 0; margin: 0; }
.pm-checkbox-container input { position: absolute; opacity: 0; cursor: pointer; height: 0; width: 0; }
.pm-checkmark { position: absolute; top: 0; left: 0; height: 16px; width: 16px; background: #111; border: 1px solid #555; border-radius: 4px; transition: all 0.2s; box-sizing: border-box; }
.pm-checkbox-container:hover input ~ .pm-checkmark { border-color: #3b82f6; }
.pm-checkbox-container input:checked ~ .pm-checkmark { background-color: #3b82f6; border-color: #3b82f6; }
.pm-checkmark:after { content: ""; position: absolute; display: none; }
.pm-checkbox-container input:checked ~ .pm-checkmark:after { display: block; }
.pm-checkbox-container .pm-checkmark:after { left: 50%; top: 45%; width: 4px; height: 9px; border: solid white; border-width: 0 2px 2px 0; transform: translate(-50%, -50%) rotate(45deg); }

/* Stacked Rule Text */
.pm-rule-text-stack { flex: 1; display: flex; flex-direction: column; min-width: 0; justify-content: center; gap: 2px;}
.pm-rule-pattern { font-family: 'Consolas', monospace; font-size: 11px; color: #ccc; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; line-height: 1; }
.pm-rule-target { font-family: 'Consolas', monospace; font-size: 10px; color: #666; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; line-height: 1.2; }
.pm-rule-item.active .pm-rule-pattern { color: #fff; font-weight: bold; }
.pm-rule-item.active .pm-rule-target { color: #93c5fd; }

/* Sidebar Color Indicator */
.pm-color-indicator { width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0; margin-right: 4px; }

/* Trashcan */
.pm-rule-del { background: transparent; border: 1px solid transparent; color: #666; cursor: pointer; padding: 5px; border-radius: 6px; display: flex; align-items: center; justify-content: center; transition: all 0.2s; }
.pm-rule-item:hover .pm-rule-del { background: #2a2d2e; border-color: #333; color: #888; }
.pm-rule-del:hover { background: rgba(239, 68, 68, 0.15) !important; border-color: rgba(239, 68, 68, 0.4) !important; color: #ef4444 !important; }

.pm-empty-sidebar { padding: 40px 20px; text-align: center; color: #666; font-size: 12px; line-height: 1.5; }

/* Sidebar Footer & Buttons */
.pm-sidebar-footer { padding: 16px; background: #151515; border-top: 1px solid #333; display: flex; flex-direction: column; gap: 12px;}
.ghost-btn { display: flex; align-items: center; gap: 4px; height: 26px; padding: 0 8px; background: transparent; border: 1px solid #444; color: #aaa; border-radius: 4px; cursor: pointer; font-size: 11px; font-weight: 500; transition: all 0.2s; }
.ghost-btn:hover { background: rgba(255, 255, 255, 0.08); color: #fff; border-color: #666;}

/* MAIN EDITOR STYLES */
.pm-main-area { flex: 1; display: flex; flex-direction: column; background: #1e1e1e; min-width: 0; }
.pm-main-empty { flex: 1; display: flex; justify-content: center; align-items: center; color: #555; font-size: 13px; }
.pm-header { display: flex; justify-content: space-between; align-items: center; padding: 12px 20px; background: #252525; border-bottom: 1px solid #333; flex-shrink: 0; }
.pm-title { font-size: 13px; font-weight: 700; }
.text-blue { color: #3b82f6 !important; }
.pm-close-btn { background: transparent; border: none; color: #888; font-size: 16px; cursor: pointer; transition: color 0.2s; }
.pm-close-btn:hover { color: #ef4444; }

.pm-editor-area { 
  flex: 1; 
  padding: 16px 24px; 
  display: flex; 
  flex-direction: column; 
  gap: 12px; 
  /* Changed from hidden to visible */
  overflow: visible !important; 
}

/* Custom Configuration UI */
.pm-routing-box { 
  background: #1a1a1b; 
  border: 1px solid #333; 
  border-radius: 8px; 
  /* Changed from hidden to visible */
  overflow: visible !important; 
  flex-shrink: 0; 
  position: relative;
}

/* 2. Lift the top box higher than the bottom box so the menu overlaps correctly */
.pm-routing-box:first-child {
  z-index: 10;
}

.pm-routing-header { 
  background: #222; 
  padding: 8px 16px; 
  font-size: 12px; 
  font-weight: 700; 
  color: #ccc; 
  border-bottom: 1px solid #333;
  border-top-left-radius: 8px;
  border-top-right-radius: 8px;
}
.pm-routing-header.target-header { background: rgba(59, 130, 246, 0.1); color: #60a5fa; border-bottom-color: rgba(59, 130, 246, 0.2); }
.pm-routing-box.target { border-color: rgba(59, 130, 246, 0.3); }

.pm-routing-body { padding: 12px 16px; display: flex; flex-direction: column; gap: 6px; }

.pm-routing-label { font-size: 11px; font-weight: 600; color: #888; letter-spacing: 0.5px; }
.pm-routing-input { width: 100%; background: #111; border: 1px solid #444; color: #fff; padding: 10px 12px; border-radius: 6px; font-size: 13px; font-family: 'Consolas', monospace; outline: none; transition: border-color 0.2s, box-shadow 0.2s; box-sizing: border-box; }
.pm-routing-input:focus { border-color: #3b82f6; box-shadow: 0 0 0 1px #3b82f6; }
.pm-routing-helper { font-size: 11px; color: #666; line-height: 1.4; }

/* --- NEW CUSTOM SELECT DROP DOWN --- */
.pm-custom-select-wrapper { position: relative; width: 100%; user-select: none; }
.pm-custom-select-display { width: 100%; background: #111; border: 1px solid #444; color: #fff; padding: 10px 12px; border-radius: 6px; font-size: 13px; font-family: 'Consolas', monospace; display: flex; justify-content: space-between; align-items: center; cursor: pointer; transition: border-color 0.2s, box-shadow 0.2s; box-sizing: border-box; }
.pm-custom-select-display:hover { border-color: #555; }
.pm-chevron { width: 16px; height: 16px; fill: currentColor; opacity: 0.6; }

.pm-dropdown-overlay { position: fixed; top: 0; left: 0; right: 0; bottom: 0; z-index: 99; cursor: default; }

.pm-custom-select-dropdown { 
  position: absolute; 
  top: 100%; 
  left: 0; 
  right: 0; 
  margin-top: 4px; 
  background: #252525; 
  border: 1px solid #444; 
  border-radius: 6px; 
  box-shadow: 0 10px 30px rgba(0,0,0,0.8); 
  z-index: 9999; /* Super high z-index */
  padding: 4px 0; 
}
.pm-custom-select-option { padding: 10px 12px; font-size: 13px; font-family: 'Consolas', monospace; color: #ccc; cursor: pointer; transition: background 0.1s; }
.pm-custom-select-option:hover { background: #333; color: #fff; }
.pm-custom-select-option.selected { background: rgba(59, 130, 246, 0.15); color: #3b82f6; font-weight: bold; }

/* Compacted Arrow */
.pm-routing-arrow { display: flex; justify-content: center; align-items: center; padding: 4px 0; flex-shrink: 0; }

/* Color Picker UI */
.pm-color-picker { display: flex; gap: 16px; margin-top: 2px; padding: 4px 0; }
.pm-color-dot { width: 32px; height: 32px; border-radius: 50%; cursor: pointer; border: 3px solid transparent; transition: transform 0.2s, border-color 0.2s, box-shadow 0.2s; }
.pm-color-dot:hover { transform: scale(1.1); }
.pm-color-dot.active { border-color: white; transform: scale(1.15); box-shadow: 0 0 12px rgba(255,255,255,0.2); }

/* Unified Colors */
.pm-color-dot.red, .pm-color-indicator.red { background: #ef4444; }
.pm-color-dot.yellow, .pm-color-indicator.yellow { background: #f59e0b; }
.pm-color-dot.green, .pm-color-indicator.green { background: #10b981; }
.pm-color-dot.blue, .pm-color-indicator.blue { background: #3b82f6; }

.pm-footer { display: flex; justify-content: flex-end; gap: 12px; padding: 16px 20px; background: #1a1a1b; border-top: 1px solid #333; flex-shrink: 0; }
.pm-btn-cancel { background: transparent; color: #ccc; border: 1px solid #444; border-radius: 6px; padding: 8px 24px; font-weight: 600; font-size: 13px; cursor: pointer; transition: all 0.2s; }
.pm-btn-cancel:hover { background: #333; color: white; border-color: #555; }
.pm-btn-execute { background: #3b82f6; color: white; border: none; border-radius: 6px; padding: 8px 32px; font-weight: 600; font-size: 13px; cursor: pointer; transition: background 0.2s; }
.pm-btn-execute:hover { background: #2563eb; }
</style>