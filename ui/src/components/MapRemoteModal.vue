<script setup>
import { computed } from 'vue'
import { 
  showMapRemoteModal, 
  mapRemoteRules, 
  selectedMapRemoteId, 
  syncMapRemoteRules,
  enableMapRemote,
  importRules,
  exportRules
} from '../store.js'

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
</script>

<template>
  <div v-if="showMapRemoteModal" class="modal-overlay" @mousedown.self="syncMapRemoteRules(); showMapRemoteModal = false;">
    <div class="modal-content large" style="display: flex;">      
      <div class="modal-sidebar" style="width: 280px; background: var(--bg-sidebar); border-right: 1px solid var(--border); display: flex; flex-direction: column;">
        <div style="padding: 16px; border-bottom: 1px solid var(--border); display: flex; justify-content: space-between; align-items: center;">
          <strong style="color: white; font-size: 13px;">Map Remote</strong>
          <button class="action-btn" style="padding: 4px 10px;" @click="addNewRule">+ Add</button>
        </div>
        
        <div style="flex: 1; overflow-y: auto;">
          <div v-for="rule in mapRemoteRules" :key="rule.id" class="rule-item" :class="{ active: selectedMapRemoteId === rule.id }" @click="selectedMapRemoteId = rule.id">
            <input type="checkbox" v-model="rule.active" @click.stop />
            <div style="flex: 1; overflow: hidden; padding-left: 8px;">
              <div class="truncate" style="font-family: monospace; font-size: 12px; color: #ccc;">{{ rule.pattern || 'New Rule' }}</div>
              <div class="truncate" style="font-size: 10px; color: #8b5cf6; margin-top: 2px;">→ {{ rule.target }}</div>
            </div>
            <span style="color: #ef4444; cursor: pointer; padding: 0 4px; font-weight: bold;" @click.stop="deleteRule(rule.id)">×</span>
          </div>
          <div v-if="mapRemoteRules.length === 0" style="padding: 40px; text-align: center; color: #666; font-style: italic; font-size: 12px;">No rules set.</div>
        </div>

        <div class="sidebar-footer">
          <div class="toggle" @click="enableMapRemote = !enableMapRemote" :class="{ active: enableMapRemote }">
            <span class="toggle-label">Enable Map Remote</span>
            <div class="switch"></div>
          </div>
          
          <div class="divider" style="width: 100%; height: 1px; background: var(--border); margin: 8px 0;"></div>
          
          <div style="display: flex; gap: 8px;">
            <button class="ghost-btn" style="flex: 1; justify-content: center;" @click="exportRules(mapRemoteRules, 'OpenProxy_MapRemote')">⬇️ Export</button>
            <label class="ghost-btn" style="flex: 1; justify-content: center; cursor: pointer; margin: 0;">
              ⬆️ Import
              <input type="file" accept=".json" style="display: none;" @change="(e) => importRules(e, mapRemoteRules)" />
            </label>
          </div>
        </div>
      </div>

      <div style="flex: 1; display: flex; flex-direction: column; background: var(--bg-main);">
        <div v-if="activeRule" style="display: flex; flex-direction: column; height: 100%;">
          
          <div style="padding: 24px; flex: 1; overflow-y: auto; display: flex; flex-direction: column; gap: 24px;">
            <div class="form-group">
              <label class="modal-label">Map From (Regex / URL Part)</label>
              <input type="text" v-model="activeRule.pattern" class="modal-input" placeholder="e.g., api\.production\.com/v1" style="font-family: monospace;" />
              <span style="font-size: 11px; color: #666; margin-top: 6px;">Any URL matching this will be rewritten.</span>
            </div>

            <div class="form-group">
              <label class="modal-label" style="color: #8b5cf6;">Map To (Target)</label>
              <input type="text" v-model="activeRule.target" class="modal-input" placeholder="e.g., localhost:8080/v2" style="font-family: monospace; border-color: #8b5cf6;" />
              <span style="font-size: 11px; color: #666; margin-top: 6px;">The matched portion will be replaced with this string.</span>
            </div>
          </div>
          
          <div style="padding: 16px 24px; border-top: 1px solid var(--border); display: flex; justify-content: flex-end; gap: 10px; background: var(--bg-sidebar);">
            <button class="action-btn" @click="showMapRemoteModal = false">Cancel</button>
            <button class="action-btn" style="background: #8b5cf6; color: white; border-color: #8b5cf6; padding: 6px 16px; font-weight: bold;" @click="syncMapRemoteRules(); showMapRemoteModal = false;">Save & Apply</button>
          </div>
          
        </div>
        <div v-else style="display: flex; justify-content: center; align-items: center; height: 100%; color: #666; font-style: italic; font-size: 12px;">Select or create a rule.</div>
      </div>
      
    </div>
  </div>
</template>

<style scoped>
/* Base Modal Styles */
.modal-overlay { position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0, 0, 0, 0.7); z-index: 99999; display: flex; justify-content: center; align-items: center; backdrop-filter: blur(2px); }
.modal-content { background: var(--bg-main); border: 1px solid var(--border); border-radius: 8px; box-shadow: 0 10px 40px rgba(0,0,0,0.6); resize: both; overflow: hidden; }
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
.rule-item.active { background: rgba(139, 92, 246, 0.15); border-left: 3px solid #8b5cf6; padding-left: 9px; }

.form-group { display: flex; flex-direction: column; text-align: left; }
.modal-label { font-size: 12px; color: #aaa; margin-bottom: 8px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px;}
.modal-input { width: 100%; background: #111; border: 1px solid #444; color: #ccc; padding: 10px 12px; border-radius: 6px; font-size: 13px; box-sizing: border-box; outline: none; transition: border-color 0.2s; }
.modal-input:focus { border-color: #8b5cf6; }
.truncate { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

/* Buttons & Footer (Consistent across all modals) */
.action-btn { background: #2a2d2e; border: 1px solid #444; color: #ccc; border-radius: 4px; padding: 6px 12px; font-size: 12px; cursor: pointer; transition: all 0.2s; }
.action-btn:hover { background: #333; color: white; border-color: #555; }

.sidebar-footer { padding: 16px; background: #1a1b1c; border-top: 1px solid var(--border); display: flex; flex-direction: column; }

.ghost-btn { display: flex; align-items: center; gap: 4px; height: 26px; padding: 0 8px; background: transparent; border: 1px solid #444; color: #aaa; border-radius: 4px; cursor: pointer; font-size: 11px; font-weight: 500; transition: all 0.2s; }
.ghost-btn:hover { background: rgba(255, 255, 255, 0.08); color: #fff; border-color: #666;}

.toggle { display: flex; align-items: center; justify-content: space-between; cursor: pointer; color: #888; font-weight: 600; transition: color 0.2s; }
.toggle.active { color: #8b5cf6; } /* Map Remote Purple */
.toggle:hover { color: #ccc; }
.toggle-label { font-size: 12px; }

.switch { width: 32px; height: 18px; background: #111; border: 1px solid #444; border-radius: 14px; position: relative; transition: all 0.3s; box-sizing: border-box;}
.switch::after { content: ''; position: absolute; top: 1px; left: 1px; width: 14px; height: 14px; background: #888; border-radius: 50%; transition: transform 0.3s, background 0.3s; }
.toggle.active .switch { background: rgba(139, 92, 246, 0.15); border-color: #8b5cf6; }
.toggle.active .switch::after { transform: translateX(14px); background: #8b5cf6; }
</style>