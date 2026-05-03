<script setup>
import { computed, watch } from 'vue'
import { 
  showMapRemoteModal, 
  mapRemoteRules, 
  selectedMapRemoteId, 
  syncMapRemoteRules,
  enableMapRemote,
  importRules,
  exportRules
} from '../store.js'

watch(mapRemoteRules, (newRules) => {
  if (newRules.length > 0 && !selectedMapRemoteId.value) {
    selectedMapRemoteId.value = newRules[0].id
  }
}, { immediate: true, deep: true })

const activeRule = computed(() => mapRemoteRules.value.find(r => r.id === selectedMapRemoteId.value))

const addNewRule = () => {
  const newRule = { 
    id: Date.now(), 
    active: true, 
    pattern: 'api.production.com', 
    target: 'localhost:3000' 
  }
  mapRemoteRules.value.unshift(newRule)
  selectedMapRemoteId.value = newRule.id
}

const deleteRule = (id) => {
  mapRemoteRules.value = mapRemoteRules.value.filter(r => r.id !== id)
  if (selectedMapRemoteId.value === id) {
    selectedMapRemoteId.value = mapRemoteRules.value.length ? mapRemoteRules.value[0].id : null
  }
}

const saveAndApplyRules = () => {
  syncMapRemoteRules()
  showMapRemoteModal.value = false
}
</script>

<template>
  <Teleport to="body">
    <div v-if="showMapRemoteModal" class="modal-overlay" @mousedown.self="saveAndApplyRules">
      
      <div class="pm-split-modal">
        
        <div class="pm-sidebar">
          
          <div class="pm-sidebar-header">
            <strong style="color: var(--fg-secondary); font-size: 13px;">Map Remote Rules</strong>
            <button class="pm-add-btn" @click="addNewRule">+ Add</button>
          </div>
          
          <div class="pm-rule-list">
            <div v-for="rule in mapRemoteRules" :key="rule.id" 
                 class="pm-rule-item" 
                 :class="{ active: selectedMapRemoteId === rule.id }" 
                 @click="selectedMapRemoteId = rule.id">
              
              <label class="pm-checkbox-container" @click.stop>
                <input type="checkbox" v-model="rule.active" />
                <span class="pm-checkmark"></span>
              </label>

              <div class="pm-rule-text-stack">
                <span class="pm-rule-pattern" :title="rule.pattern">{{ rule.pattern || 'New Rule' }}</span>
                <span class="pm-rule-target" :title="rule.target">→ {{ rule.target }}</span>
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
            
            <div v-if="mapRemoteRules.length === 0" class="pm-empty-sidebar">
              No rules yet. Click + Add to start routing traffic.
            </div>
          </div>

          <div class="pm-sidebar-footer">
            <div class="toggle" @click="enableMapRemote = !enableMapRemote" :class="{ active: enableMapRemote }">
              <span class="toggle-label">Enable Map Remote</span>
              <div class="switch"></div>
            </div>
            
            <div class="pm-divider-horizontal"></div>
            
            <div style="display: flex; gap: 8px;">
              <button class="ghost-btn" style="flex: 1; justify-content: center;" @click="exportRules(mapRemoteRules, 'OpenProxy_MapRemote')">Export</button>
              <label class="ghost-btn" style="flex: 1; justify-content: center; cursor: pointer; margin: 0;">
                Import
                <input type="file" accept=".json" style="display: none;" @change="(e) => importRules(e, mapRemoteRules)" />
              </label>
            </div>
          </div>
        </div>

        <div class="pm-main-area">
          
          <div v-if="activeRule" style="display: flex; flex-direction: column; height: 100%;">
            
            <div class="pm-header">
              <strong class="pm-title text-purple">Traffic Routing Editor</strong>
              <button class="pm-close-btn" @click="saveAndApplyRules">✕</button>
            </div>

            <div class="pm-editor-area" style="padding: 24px; gap: 24px; overflow-y: auto;">
              
              <div class="pm-routing-box">
                <div class="pm-routing-header">Map From (Original Request)</div>
                <div class="pm-routing-body">
                  <span class="pm-routing-label">MATCH URL OR REGEX</span>
                  <input type="text" v-model="activeRule.pattern" class="pm-routing-input" placeholder="e.g., api\.production\.com/v1" />
                  <div class="pm-routing-helper">Any outgoing request matching this pattern will be intercepted.</div>
                </div>
              </div>

              <div class="pm-routing-arrow">
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="var(--color-map-remote)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <line x1="12" y1="5" x2="12" y2="19"></line>
                  <polyline points="19 12 12 19 5 12"></polyline>
                </svg>
              </div>

              <div class="pm-routing-box target">
                <div class="pm-routing-header target-header">Map To (New Destination)</div>
                <div class="pm-routing-body">
                  <span class="pm-routing-label">FORWARD TO</span>
                  <input type="text" v-model="activeRule.target" class="pm-routing-input target-input" placeholder="e.g., localhost:8080/v2" />
                  <div class="pm-routing-helper">The intercepted request will be secretly rewritten to this address before sending.</div>
                </div>
              </div>

            </div>

            <div class="pm-footer">
              <button class="pm-btn-cancel" @click="showMapRemoteModal = false">Cancel</button>
              <button class="pm-btn-execute" @click="saveAndApplyRules">Save & Apply</button>
            </div>

          </div>
          
          <div v-else class="pm-main-empty">
            Select or create a rule to configure routing.
          </div>

        </div>

      </div>
    </div>
  </Teleport>
</template>

<style scoped>
/* OVERLAY & MODAL */
.modal-overlay { position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: var(--overlay); z-index: 99999; display: flex; justify-content: center; align-items: center; backdrop-filter: blur(4px); }
.pm-split-modal { background: var(--bg-main); border-radius: 8px; border: 1px solid var(--border); width: 1000px; height: 650px; display: flex; flex-direction: row; box-shadow: var(--shadow-lg); overflow: hidden; }

/* SIDEBAR STYLES */
.pm-sidebar { width: 300px; background: var(--bg-sidebar); border-right: 1px solid var(--border); display: flex; flex-direction: column; flex-shrink: 0; }
.pm-sidebar-header { padding: 16px; border-bottom: 1px solid var(--border); display: flex; justify-content: space-between; align-items: center; background: var(--bg-active);}
.pm-add-btn { background: var(--color-map-remote-dim); color: var(--color-map-remote); border: 1px solid rgba(139,92,246,0.3); padding: 4px 10px; border-radius: 4px; font-size: 11px; font-weight: 600; cursor: pointer; transition: all 0.2s; }
.pm-add-btn:hover { background: var(--color-map-remote); color: var(--fg-primary); border-color: var(--color-map-remote); }

.pm-rule-list { flex: 1; overflow-y: auto; }
.pm-rule-item { height: 44px; padding: 0 16px; border-bottom: 1px solid var(--border-subtle); display: flex; align-items: center; gap: 12px; cursor: pointer; transition: background 0.2s; box-sizing: border-box; }
.pm-rule-item:hover { background: var(--bg-active); }
/* PURPLE ACTIVE STATE */
.pm-rule-item.active { background: var(--color-map-remote-dim); border-left: 3px solid var(--color-map-remote); padding-left: 13px; }

/* Sleek Checkbox - Purple Theme */
.pm-checkbox-container { display: flex; align-items: center; justify-content: center; position: relative; cursor: pointer; user-select: none; width: 16px; height: 16px; flex-shrink: 0; margin: 0; }
.pm-checkbox-container input { position: absolute; opacity: 0; cursor: pointer; height: 0; width: 0; }
.pm-checkmark { position: absolute; top: 0; left: 0; height: 16px; width: 16px; background-color: var(--bg-deepest); border: 1px solid var(--fg-muted); border-radius: 4px; transition: border-color 0.2s, background-color 0.2s; box-sizing: border-box; }
.pm-checkbox-container:hover input ~ .pm-checkmark { border-color: var(--color-map-remote); }
.pm-checkbox-container input:checked ~ .pm-checkmark { background-color: var(--color-map-remote); border-color: var(--color-map-remote); }
.pm-checkmark:after { content: ""; position: absolute; display: none; }
.pm-checkbox-container input:checked ~ .pm-checkmark:after { display: block; }
.pm-checkbox-container .pm-checkmark:after { left: 50%; top: 45%; width: 4px; height: 9px; border: solid white; border-width: 0 2px 2px 0; transform: translate(-50%, -50%) rotate(45deg); }

/* Stacked Rule Text */
.pm-rule-text-stack { flex: 1; display: flex; flex-direction: column; min-width: 0; justify-content: center; }
.pm-rule-pattern { font-family: 'Consolas', monospace; font-size: 11px; color: var(--fg-secondary); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; line-height: 1.2; }
.pm-rule-target { font-family: 'Consolas', monospace; font-size: 10px; color: var(--fg-muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; line-height: 1.2; margin-top: 2px; }
.pm-rule-item.active .pm-rule-pattern { color: var(--fg-primary); font-weight: bold; }
.pm-rule-item.active .pm-rule-target { color: var(--color-map-remote); } /* Lighter purple when active */

/* The Permanent Rounded Trashcan */
.pm-rule-del { background: transparent; border: 1px solid transparent; color: var(--fg-muted); cursor: pointer; padding: 5px; border-radius: 6px; display: flex; align-items: center; justify-content: center; transition: all 0.2s; }
.pm-rule-item:hover .pm-rule-del { background: var(--bg-active); border-color: var(--border); color: var(--fg-muted); }
.pm-rule-del:hover { background: var(--error-muted) !important; border-color: rgba(239,68,68,0.4) !important; color: var(--error) !important; }

.pm-empty-sidebar { padding: 40px 20px; text-align: center; color: var(--fg-muted); font-size: 12px; line-height: 1.5; }

/* Sidebar Footer & Toggles */
.pm-sidebar-footer { padding: 16px; background: var(--bg-modal); border-top: 1px solid var(--border); display: flex; flex-direction: column; gap: 12px;}
.toggle { display: flex; align-items: center; justify-content: space-between; cursor: pointer; color: var(--fg-muted); font-weight: 600; transition: color 0.2s; }
.toggle.active { color: var(--color-map-remote); }
.toggle:hover { color: var(--fg-secondary); }
.toggle-label { font-size: 12px; }
.switch { width: 32px; height: 18px; background: var(--bg-input); border: 1px solid var(--border); border-radius: 14px; position: relative; transition: all 0.3s; box-sizing: border-box;}
.switch::after { content: ''; position: absolute; top: 1px; left: 1px; width: 14px; height: 14px; background: var(--fg-muted); border-radius: 50%; transition: transform 0.3s, background 0.3s; }
.toggle.active .switch { background: var(--color-map-remote-dim); border-color: var(--color-map-remote); }
.toggle.active .switch::after { transform: translateX(14px); background: var(--color-map-remote); }
.pm-divider-horizontal { width: 100%; height: 1px; background: var(--border); }
.ghost-btn { display: flex; align-items: center; gap: 4px; height: 26px; padding: 0 8px; background: transparent; border: 1px solid var(--border); color: var(--fg-muted); border-radius: 4px; cursor: pointer; font-size: 11px; font-weight: 500; transition: all 0.2s; }
.ghost-btn:hover { background: var(--surface-hover-strong); color: var(--fg-primary); border-color: var(--fg-muted);}

/* MAIN EDITOR STYLES */
.pm-main-area { flex: 1; display: flex; flex-direction: column; background: var(--bg-main); min-width: 0; }
.pm-main-empty { flex: 1; display: flex; justify-content: center; align-items: center; color: var(--fg-placeholder); font-size: 13px; }

.pm-header { display: flex; justify-content: space-between; align-items: center; padding: 12px 20px; background: var(--bg-card); border-bottom: 1px solid var(--border); flex-shrink: 0; }
.pm-title { font-size: 13px; font-weight: 700; }
.text-purple { color: var(--color-map-remote) !important; }
.pm-close-btn { background: transparent; border: none; color: var(--fg-muted); font-size: 16px; cursor: pointer; transition: color 0.2s; }
.pm-close-btn:hover { color: var(--error); }

.pm-editor-area { flex: 1; display: flex; flex-direction: column; background: var(--bg-deepest); overflow: hidden; }

/* Custom Map Remote Routing UI */
.pm-routing-box { background: var(--bg-sidebar); border: 1px solid var(--border); border-radius: 8px; overflow: hidden; }
.pm-routing-header { background: var(--bg-active); padding: 10px 16px; font-size: 12px; font-weight: 700; color: var(--fg-secondary); border-bottom: 1px solid var(--border); }
.pm-routing-header.target-header { background: var(--color-map-remote-dim); color: var(--color-map-remote); border-bottom-color: rgba(139,92,246,0.2); }
.pm-routing-box.target { border-color: rgba(139,92,246,0.3); }

.pm-routing-body { padding: 16px; display: flex; flex-direction: column; gap: 8px; }
.pm-routing-label { font-size: 11px; font-weight: 600; color: var(--fg-muted); letter-spacing: 0.5px; }
.pm-routing-input { width: 100%; background: var(--bg-deepest); border: 1px solid var(--border); color: var(--fg-primary); padding: 12px 16px; border-radius: 6px; font-size: 14px; font-family: 'Consolas', monospace; outline: none; transition: border-color 0.2s, box-shadow 0.2s; box-sizing: border-box; }
.pm-routing-input:focus { border-color: var(--accent); box-shadow: var(--focus-ring); }
.pm-routing-input.target-input:focus { border-color: var(--color-map-remote); box-shadow: 0 0 0 1px var(--color-map-remote); }
.pm-routing-helper { font-size: 11px; color: var(--fg-muted); }

.pm-routing-arrow { display: flex; justify-content: center; align-items: center; padding: 8px 0; }

.pm-footer { display: flex; justify-content: flex-end; gap: 12px; padding: 16px 20px; background: var(--bg-sidebar); border-top: 1px solid var(--border); flex-shrink: 0; }
.pm-btn-cancel { background: transparent; color: var(--fg-secondary); border: 1px solid var(--border); border-radius: 6px; padding: 8px 24px; font-weight: 600; font-size: 13px; cursor: pointer; transition: all 0.2s; }
.pm-btn-cancel:hover { background: var(--surface-hover-strong); color: var(--fg-primary); border-color: var(--fg-muted); }
.pm-btn-execute { background: var(--color-map-remote); color: var(--fg-primary); border: none; border-radius: 6px; padding: 8px 32px; font-weight: 600; font-size: 13px; cursor: pointer; transition: background 0.2s; }
.pm-btn-execute:hover { background: var(--color-map-remote); filter: brightness(1.1); }
</style>