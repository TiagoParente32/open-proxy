<script setup>
import { computed } from 'vue'
import { 
  showMapRemoteModal, 
  mapRemoteRules, 
  selectedMapRemoteId, 
  syncMapRemoteRules 
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
  <div v-if="showMapRemoteModal" class="modal-overlay" @mousedown.self="showMapRemoteModal = false">
    <div class="modal-content large" style="width: 700px; height: 450px; min-width: 500px; min-height: 350px; display: flex;">
      
      <div class="modal-sidebar" style="width: 250px; background: var(--bg-sidebar); border-right: 1px solid var(--border); display: flex; flex-direction: column;">
        <div style="padding: 16px; border-bottom: 1px solid var(--border); display: flex; justify-content: space-between; align-items: center;">
          <strong style="color: white; font-size: 13px;">Map Remote</strong>
          <button class="action-btn" @click="addNewRule">+ Add</button>
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
/* Reusing standard modal styles */
.modal-overlay { position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0, 0, 0, 0.7); z-index: 99999; display: flex; justify-content: center; align-items: center; backdrop-filter: blur(2px); }
.modal-content { 
  background: var(--bg-main); /* Add background back */
  border: 1px solid var(--border); /* Standard gray border */
  border-radius: 8px; 
  box-shadow: 0 10px 40px rgba(0,0,0,0.6); /* Standard dark shadow */
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
.action-btn { background: transparent; border: 1px solid #444; color: #ccc; padding: 4px 12px; border-radius: 4px; cursor: pointer; font-size: 12px; transition: all 0.2s; }
.action-btn:hover { background: #333; color: white; }
</style>