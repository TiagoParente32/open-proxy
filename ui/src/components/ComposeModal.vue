<script setup>
import { Codemirror } from 'vue-codemirror'
import { json } from '@codemirror/lang-json'
import { oneDark } from '@codemirror/theme-one-dark'
import { EditorView } from '@codemirror/view'
import { showComposeModal, composeData, sendComposedRequest } from '../store.js'

const extensions = [json(), oneDark, EditorView.lineWrapping]
</script>

<template>
  <Teleport to="body">
    <div v-if="showComposeModal && composeData" class="modal-overlay">
      
      <div class="modal-content large" style="border-color: #3b82f6; box-shadow: 0 0 40px rgba(59, 130, 246, 0.2); width: 800px; height: 600px; display: flex; flex-direction: column; resize: both; overflow: hidden; min-width: 500px; min-height: 400px;">
        
        <div style="padding: 16px 24px; background: #2a2d2e; border-bottom: 1px solid var(--border); display: flex; justify-content: space-between; align-items: center; flex-shrink: 0;">
          <strong style="color: #3b82f6; font-size: 14px;">✏️ Edit & Repeat Request</strong>
        </div>

        <div style="padding: 20px 24px; flex: 1; overflow-y: auto; display: flex; flex-direction: column; gap: 16px;">
          
          <div style="display: flex; gap: 10px;">
             <div class="form-group" style="width: 100px; flex-shrink: 0;">
               <label class="modal-label">Method</label>
               <input type="text" v-model="composeData.method" class="modal-input" />
             </div>
             <div class="form-group" style="flex: 1;">
               <label class="modal-label">URL</label>
               <input type="text" v-model="composeData.url" class="modal-input" />
             </div>
          </div>

          <div class="form-group" style="flex-shrink: 0;">
            <label class="modal-label">Headers (JSON)</label>
            <div class="code-editor-wrapper" style="height: 140px;">
              <codemirror v-model="composeData.req_headers" :extensions="extensions" :style="{ height: '100%' }" />
            </div>
          </div>

          <div class="form-group" style="flex: 1; display: flex; flex-direction: column; min-height: 150px;">
            <label class="modal-label">Body</label>
            <div class="code-editor-wrapper auto-expand" style="flex: 1;">
              <codemirror v-model="composeData.req_body" :extensions="extensions" />
            </div>
          </div>
        </div>

        <div style="padding: 16px 24px; border-top: 1px solid var(--border); display: flex; justify-content: flex-end; gap: 10px; background: var(--bg-sidebar); flex-shrink: 0;">
          <button class="action-btn" @click="showComposeModal = false">Cancel</button>
          <button class="action-btn" style="background: #3b82f6; color: white; border-color: #3b82f6; padding: 6px 24px;" @click="sendComposedRequest">Send Request</button>
        </div>

      </div>
    </div>
  </Teleport>
</template>

<style scoped>
/* Reusing your rock-solid Teleport/Modal CSS from BreakpointHit */
.modal-overlay { position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0, 0, 0, 0.75); z-index: 99999; display: flex; justify-content: center; align-items: center; backdrop-filter: blur(2px); }
.modal-content { background: var(--bg-main); border-radius: 8px; border: 1px solid var(--border); }
.form-group { display: flex; flex-direction: column; text-align: left; }
.modal-label { font-size: 12px; color: #aaa; margin-bottom: 6px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px;}
.modal-input { width: 100%; background: #111; border: 1px solid #444; color: #ccc; padding: 10px 12px; border-radius: 6px; font-size: 13px; box-sizing: border-box; outline: none; transition: border-color 0.2s; }
.modal-input:focus { border-color: #3b82f6; }
.code-editor-wrapper { flex: 1; border: 1px solid #444; border-radius: 6px; overflow: hidden; font-size: 13px; min-width: 0; max-width: 100%; }
.code-editor-wrapper :deep(.cm-editor) { height: 100% !important; }

/* Auto-expanding CodeMirror fix */
.auto-expand { height: auto !important; min-height: 150px; }
.auto-expand :deep(.cm-editor) { height: auto !important; }
.auto-expand :deep(.cm-scroller) { overflow: visible !important; }
</style>