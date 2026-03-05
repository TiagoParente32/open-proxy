<script setup>
import { Splitpanes, Pane } from 'splitpanes'
import { Codemirror } from 'vue-codemirror'
import { json } from '@codemirror/lang-json'
import { oneDark } from '@codemirror/theme-one-dark'
import { EditorView } from '@codemirror/view'

import { selectedRequest, activeReqTab, activeResTab } from '../store.js'

const extensions = [json(), oneDark, EditorView.lineWrapping]

const formatJson = (str) => {
  if (!str) return '// No body data'
  try { return JSON.stringify(JSON.parse(str), null, 2) } catch (e) { return str }
}
</script>

<template>
  <div class="detail-container">
    <div v-if="selectedRequest" style="height: 100%;">
      <splitpanes class="custom-theme">
        
        <pane size="50">
          <div class="inspector-panel">
            <div class="inspector-toolbar">
              <span class="panel-title">Request</span>
              <div class="panel-tabs"><span v-for="tab in ['Header', 'Body']" :key="tab" @click="activeReqTab = tab" class="panel-tab" :class="{ active: activeReqTab === tab }">{{ tab }}</span></div>
            </div>
            <div class="inspector-content">
              <table v-if="activeReqTab === 'Header'" class="kv-table"><tr v-for="(value, key) in selectedRequest.req_headers" :key="key"><td class="kv-key">{{ key }}</td><td class="kv-value">{{ value }}</td></tr></table>
              <div v-if="activeReqTab === 'Body'" style="height: 100%;"><codemirror :model-value="formatJson(selectedRequest.req_body)" :style="{ height: '100%' }" :extensions="extensions" :disabled="true" /></div>
            </div>
          </div>
        </pane>
        
        <pane size="50">
          <div class="inspector-panel">
            <div class="inspector-toolbar">
              <span class="panel-title" :class="{'text-green': selectedRequest.status < 400, 'text-red': selectedRequest.status >= 400}">Response {{ selectedRequest.status !== '...' ? `(${selectedRequest.status})` : '' }}</span>
              <div class="panel-tabs"><span v-for="tab in ['Header', 'Body']" :key="tab" @click="activeResTab = tab" class="panel-tab" :class="{ active: activeResTab === tab }">{{ tab }}</span></div>
            </div>
            <div class="inspector-content">
              <table v-if="activeResTab === 'Header'" class="kv-table"><tr v-for="(value, key) in selectedRequest.res_headers" :key="key"><td class="kv-key">{{ key }}</td><td class="kv-value">{{ value }}</td></tr></table>
              <div v-if="activeResTab === 'Body'" style="height: 100%;"><codemirror :model-value="formatJson(selectedRequest.res_body)" :style="{ height: '100%' }" :extensions="extensions" :disabled="true" /></div>
            </div>
          </div>
        </pane>
        
      </splitpanes>
    </div>
    <div v-else class="global-empty">Select a request to view details.</div>
  </div>
</template>

<style scoped>
.detail-container { display: flex; flex-direction: column; height: 100%; overflow: hidden; }
.inspector-panel { display: flex; flex-direction: column; height: 100%; background: var(--bg-main); }
.inspector-toolbar { display: flex; align-items: center; gap: 16px; padding: 0 12px; background-color: var(--bg-sidebar); border-bottom: 1px solid var(--border); height: 32px; flex-shrink: 0; }
.panel-title { font-size: 12px; font-weight: 700; color: #ccc; }
.panel-tabs { display: flex; gap: 12px; font-size: 11px; font-weight: 500; color: #888; height: 100%; }
.panel-tab { cursor: pointer; display: flex; align-items: center; border-bottom: 2px solid transparent; transition: color 0.2s; }
.panel-tab:hover { color: #ccc; }
.panel-tab.active { color: #3b82f6; border-bottom-color: #3b82f6; }

.inspector-content { flex: 1; overflow-y: auto; display: flex; flex-direction: column; }
.kv-table { width: 100%; border-collapse: collapse; table-layout: fixed; font-size: 12px; }
.kv-table tr { border-bottom: 1px solid #222; }
.kv-table td { padding: 8px 16px !important; vertical-align: top; word-wrap: break-word; }
.kv-key { width: 30%; color: #8b949e; font-weight: 500; text-align: left; border-right: 1px solid var(--border); }
.kv-value { width: 70%; color: #e1e4e8; font-family: 'Consolas', monospace; text-align: left; }
</style>