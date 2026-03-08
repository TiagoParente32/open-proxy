<script setup>
import { computed } from 'vue'
import { Codemirror } from 'vue-codemirror'
import { json } from '@codemirror/lang-json'
import { oneDark } from '@codemirror/theme-one-dark'
import { EditorView } from '@codemirror/view'
import { trappedFlows, resolveTrappedFlow } from '../store.js'

const extensions = [json(), oneDark, EditorView.lineWrapping]

// Always look at the first item in the queue
const currentFlow = computed(() => trappedFlows.value[0])
const queueCount = computed(() => trappedFlows.value.length)

const execute = () => {
  if (!currentFlow.value) return
  let parsedHeaders = {}
  try { parsedHeaders = JSON.parse(currentFlow.value.headersStr) } catch(e) {}
  
  resolveTrappedFlow('execute', currentFlow.value.id, {
    ...currentFlow.value,
    headers: parsedHeaders
  })
}

const drop = () => {
  if (!currentFlow.value) return
  resolveTrappedFlow('drop', currentFlow.value.id)
}
</script>

<template>
  <div v-if="currentFlow" class="modal-overlay" style="z-index: 9999;">
    <div class="modal-content large" style="border-color: #f59e0b; box-shadow: 0 0 40px rgba(245, 158, 11, 0.2); width: 800px; height: 600px; display: flex; flex-direction: column; resize: both; overflow: hidden; min-width: 500px; min-height: 400px;">
      
      <div style="padding: 16px 24px; background: #2a2d2e; border-bottom: 1px solid var(--border); display: flex; justify-content: space-between; align-items: center; flex-shrink: 0;">
        <div style="min-width: 0; flex: 1; padding-right: 16px;">
          <strong style="color: #f59e0b; font-size: 14px;">⚡ Breakpoint Hit: {{ currentFlow.phase.toUpperCase() }}</strong>
          <div class="truncate" style="font-family: monospace; font-size: 11px; margin-top: 4px; color: #aaa;" :title="currentFlow.url">{{ currentFlow.url }}</div>
        </div>
        
        <div v-if="queueCount > 1" style="background: rgba(245, 158, 11, 0.2); color: #f59e0b; padding: 4px 10px; border-radius: 12px; font-size: 11px; font-weight: bold; flex-shrink: 0; border: 1px solid rgba(245, 158, 11, 0.4);">
          1 of {{ queueCount }} in Queue
        </div>
      </div>

      <div style="padding: 20px 24px; flex: 1; overflow-y: auto; display: flex; flex-direction: column; gap: 16px;">
        
        <div v-if="currentFlow.phase === 'request'" style="display: flex; gap: 10px;">
           <div class="form-group" style="width: 100px; flex-shrink: 0;">
             <label class="modal-label">Method</label>
             <input type="text" v-model="currentFlow.method" class="modal-input" />
           </div>
           <div class="form-group" style="flex: 1;">
             <label class="modal-label">URL</label>
             <input type="text" v-model="currentFlow.url" class="modal-input" />
           </div>
        </div>

        <div v-if="currentFlow.phase === 'response'" class="form-group" style="width: 150px; flex-shrink: 0;">
             <label class="modal-label">Status Code</label>
             <input type="number" v-model="currentFlow.status" class="modal-input" />
        </div>

        <div class="form-group" style="flex-shrink: 0;">
          <label class="modal-label">Headers (JSON)</label>
          <div class="code-editor-wrapper" style="height: 140px;">
            <codemirror v-model="currentFlow.headersStr" :extensions="extensions" :style="{ height: '100%' }" />
          </div>
        </div>

        <div class="form-group">
          <label class="modal-label">Body</label>
          <div class="code-editor-wrapper auto-expand">
            <codemirror v-model="currentFlow.body" :extensions="extensions" />
          </div>
        </div>
      </div>

      <div style="padding: 16px 24px; border-top: 1px solid var(--border); display: flex; justify-content: flex-end; gap: 10px; background: var(--bg-sidebar); flex-shrink: 0;">
        <button class="action-btn" style="color: #ef4444; border-color: rgba(239, 68, 68, 0.4);" @click="drop">Drop</button>
        <button class="action-btn" style="background: #10b981; color: white; border-color: #10b981; padding: 6px 24px;" @click="execute">Execute</button>
      </div>

    </div>
  </div>
</template>

<style scoped>
/* 1. This makes the dark background take over the whole screen */
.modal-overlay { 
  position: fixed; 
  top: 0; 
  left: 0; 
  right: 0; 
  bottom: 0; 
  background: rgba(0, 0, 0, 0.7); /* Dark semi-transparent backdrop */
  z-index: 9999; /* Forces it above splitpanes and context menus */
  display: flex; 
  justify-content: center; 
  align-items: center; 
  backdrop-filter: blur(2px); /* Optional: adds a nice blur to the app behind it */
}

/* 2. This formats the actual window */
.modal-content { 
  background: var(--bg-main); 
  border-radius: 8px; 
}

/* 3. Inputs and Forms inside the Breakpoint UI */
.form-group { display: flex; flex-direction: column; text-align: left; }
.modal-label { font-size: 12px; color: #aaa; margin-bottom: 6px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px;}
.modal-input { width: 100%; background: #111; border: 1px solid #444; color: #ccc; padding: 10px 12px; border-radius: 6px; font-size: 13px; box-sizing: border-box; outline: none; transition: border-color 0.2s; }
.modal-input:focus { border-color: #f59e0b; }

/* Ensure the inner wrapper of the code editor actually stretches */
.code-editor-wrapper { flex: 1; border: 1px solid #444; border-radius: 6px; overflow: hidden; font-size: 13px; min-width: 0; max-width: 100%; }
.code-editor-wrapper :deep(.cm-editor) { height: 100% !important; }
</style>