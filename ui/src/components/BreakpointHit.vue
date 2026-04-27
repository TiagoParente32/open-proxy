<script setup>
import { computed, ref, watch } from 'vue'
import { Codemirror } from 'vue-codemirror'
import { json } from '@codemirror/lang-json'
import { oneDark } from '@codemirror/theme-one-dark'
import { EditorView } from '@codemirror/view'
import CodeMirrorEditor from './CodeMirrorEditor.vue'
import { trappedFlows, resolveTrappedFlow } from '../store.js'

const extensions = [json(), oneDark, EditorView.lineWrapping]

const currentFlow = computed(() => trappedFlows.value[0])
const queueCount = computed(() => trappedFlows.value.length)

const activeTab = ref('Headers') 
const showMethodMenu = ref(false)
const queryParams = ref([{ key: '', value: '' }])

watch(currentFlow, (newFlow) => {
  if (newFlow) {
    if (newFlow.phase === 'request') {
      activeTab.value = 'Params'
      syncUrlToParams()
    } else {
      activeTab.value = 'Headers' 
    }
  }
}, { immediate: true })

const selectMethod = (method) => {
  if (currentFlow.value) currentFlow.value.method = method
  showMethodMenu.value = false
}

// --- TWO-WAY URL SYNCING ---
const syncUrlToParams = () => {
  if (!currentFlow.value) return
  const url = currentFlow.value.url || '';
  const parts = url.split('?');
  const newParams = [];
  
  if (parts.length > 1 && parts[1]) {
    const pairs = parts[1].split('&');
    pairs.forEach(pair => {
      const [k, v] = pair.split('=');
      if (k) newParams.push({ key: decodeURIComponent(k), value: v !== undefined ? decodeURIComponent(v) : '' });
    });
  }
  newParams.push({ key: '', value: '' });
  queryParams.value = newParams;
}

const syncParamsToUrl = () => {
  if (!currentFlow.value) return
  let baseUrl = currentFlow.value.url.split('?')[0] || '';
  const params = [];
  
  queryParams.value.forEach(p => {
    if (p.key) params.push(`${encodeURIComponent(p.key)}=${encodeURIComponent(p.value)}`);
  });
  
  currentFlow.value.url = params.length > 0 ? `${baseUrl}?${params.join('&')}` : baseUrl;
}

const checkParamRow = (index) => {
  if (index === queryParams.value.length - 1 && queryParams.value[index].key !== '') {
    queryParams.value.push({ key: '', value: '' })
  }
}
const removeParamRow = (index) => {
  queryParams.value.splice(index, 1)
  if (queryParams.value.length === 0) queryParams.value.push({ key: '', value: '' })
  syncParamsToUrl()
}

// --- ACTIONS ---
const execute = () => {
  if (!currentFlow.value) return
  
  let parsedHeaders = {}
  try { 
    // This was the silent killer! Now it will loudly warn you.
    parsedHeaders = JSON.parse(currentFlow.value.headersStr) 
  } catch(e) {
    alert("⚠️ Invalid JSON in Headers! Please remove trailing commas or fix quotes before executing.");
    return; // Stops the UI from freezing the request!
  }
  
  resolveTrappedFlow('execute', currentFlow.value.id, {
    ...currentFlow.value,
    // Safely enforce Integer types for status codes so Python doesn't crash
    status: currentFlow.value.status ? parseInt(currentFlow.value.status) : undefined,
    headers: parsedHeaders
  })
}

const drop = () => {
  if (!currentFlow.value) return
  resolveTrappedFlow('drop', currentFlow.value.id)
}
</script>

<template>
  <Teleport to="body">
    <div v-if="currentFlow" class="modal-overlay">
      
      <div class="pm-modal breakpoint-glow">
        
        <div class="pm-header">
          <strong class="pm-title text-amber">
            ⚡ Breakpoint Hit: {{ currentFlow.phase.toUpperCase() }}
          </strong>
          
          <div v-if="queueCount > 1" class="pm-queue-badge">
            1 of {{ queueCount }} in Queue
          </div>
        </div>

        <div class="pm-omnibar-container">
          
          <div v-if="currentFlow.phase === 'request'" class="pm-omnibar">
            <div class="pm-method-wrapper">
              <div class="pm-method-display" :class="(currentFlow.method || 'GET').toLowerCase()" @click="showMethodMenu = !showMethodMenu">
                {{ currentFlow.method || 'GET' }}
                <svg class="pm-chevron" viewBox="0 0 24 24"><path d="M7 10l5 5 5-5z"/></svg>
              </div>
              <div v-if="showMethodMenu" class="pm-dropdown-overlay" @click.stop="showMethodMenu = false"></div>
              <div v-if="showMethodMenu" class="pm-method-dropdown">
                <div v-for="m in ['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS', 'HEAD']" 
                     :key="m" class="pm-method-option" :class="m.toLowerCase()" @click="selectMethod(m)">
                  {{ m }}
                </div>
              </div>
            </div>
            <div class="pm-divider"></div>
            <input type="text" v-model="currentFlow.url" class="pm-url-input" @input="syncUrlToParams" />
          </div>

          <div v-else class="pm-omnibar read-only-bar">
            <div class="pm-method-display read-only" :class="(currentFlow.method || 'GET').toLowerCase()">
              {{ currentFlow.method || 'GET' }}
            </div>
            <div class="pm-divider"></div>
            <div class="pm-url-input read-only-url" :title="currentFlow.url">{{ currentFlow.url }}</div>
            <div class="pm-divider"></div>
            <div class="pm-status-wrapper">
              <span class="pm-status-label">Status</span>
              <input type="number" v-model.number="currentFlow.status" class="pm-status-input" />
            </div>
          </div>

        </div>

        <div class="pm-tabs">
          <span v-if="currentFlow.phase === 'request'" class="pm-tab" :class="{ active: activeTab === 'Params' }" @click="activeTab = 'Params'">Params</span>
          <span class="pm-tab" :class="{ active: activeTab === 'Headers' }" @click="activeTab = 'Headers'">Headers</span>
          <span class="pm-tab" :class="{ active: activeTab === 'Body' }" @click="activeTab = 'Body'">Body</span>
        </div>

        <div class="pm-editor-area">
          
          <div v-if="activeTab === 'Params' && currentFlow.phase === 'request'" class="pm-editor-wrapper">
            <div class="pm-helper-text">Query Parameters</div>
            <div class="pm-params-container">
              <div class="pm-param-header">
                <div class="pm-param-col">Key</div>
                <div class="pm-param-col">Value</div>
                <div class="pm-param-action"></div>
              </div>
              <div class="pm-param-row" v-for="(param, index) in queryParams" :key="index">
                <input type="text" v-model="param.key" placeholder="Key" class="pm-param-input" @input="syncParamsToUrl(); checkParamRow(index)"/>
                <input type="text" v-model="param.value" placeholder="Value" class="pm-param-input" @input="syncParamsToUrl()" />
                <button class="pm-param-del" @click="removeParamRow(index)">✕</button>
              </div>
            </div>
          </div>

          <div v-if="activeTab === 'Headers'" class="pm-editor-wrapper">
            <div class="pm-helper-text">Format as JSON (e.g., { "Content-Type": "application/json" })</div>
            <CodeMirrorEditor v-model="currentFlow.headersStr" :extensions="extensions" class="pm-codemirror" />
          </div>

          <div v-if="activeTab === 'Body'" class="pm-editor-wrapper">
            <div class="pm-helper-text">Intercepted Payload</div>
            <CodeMirrorEditor v-model="currentFlow.body" :extensions="extensions" class="pm-codemirror" />
          </div>

        </div>

        <div class="pm-footer">
          <button class="pm-btn-drop" @click="drop">Drop {{ currentFlow.phase }}</button>
          <button class="pm-btn-execute" @click="execute">Execute</button>
        </div>

      </div>
    </div>
  </Teleport>
</template>

<style scoped>
/* OVERLAY & MODAL */
.modal-overlay { position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0, 0, 0, 0.7); z-index: 99999; display: flex; justify-content: center; align-items: center; backdrop-filter: blur(4px); }
.pm-modal { background: #1e1e1e; border-radius: 8px; width: 850px; height: 650px; display: flex; flex-direction: column; overflow: hidden; }

/* BREAKPOINT SPECIFIC GLOW */
.breakpoint-glow { border: 1px solid #f59e0b; box-shadow: 0 10px 40px rgba(245, 158, 11, 0.15); }
.text-amber { color: #f59e0b !important; }

/* HEADER */
.pm-header { display: flex; justify-content: space-between; align-items: center; padding: 12px 20px; background: #252525; border-bottom: 1px solid #333; flex-shrink: 0; }
.pm-title { font-size: 13px; font-weight: 700; }
.pm-queue-badge { background: rgba(245, 158, 11, 0.2); color: #f59e0b; padding: 4px 10px; border-radius: 12px; font-size: 11px; font-weight: bold; border: 1px solid rgba(245, 158, 11, 0.4); }

/* OMNIBAR */
.pm-omnibar-container { display: flex; gap: 8px; padding: 16px 20px 8px 20px; flex-shrink: 0; }
.pm-omnibar { display: flex; flex: 1; align-items: center; background: #121212; border: 1px solid #444; border-radius: 6px; transition: border-color 0.2s; }
.pm-omnibar:focus-within { border-color: #f59e0b; }
.pm-divider { width: 1px; height: 24px; background: #333; }
.pm-url-input { flex: 1; background: transparent; border: none; color: #e0e0e0; padding: 10px 12px; font-size: 13px; outline: none; font-family: 'Consolas', monospace; }

/* RESPONSE OMNIBAR STYLES */
.read-only-bar { background: #1a1a1b; border-color: #333; }
.read-only-url { flex: 1; color: #888; padding: 10px 12px; font-size: 13px; font-family: 'Consolas', monospace; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.pm-status-wrapper { display: flex; align-items: center; padding: 0 12px; gap: 8px; }
.pm-status-label { font-size: 11px; color: #888; font-weight: 600; text-transform: uppercase; }
.pm-status-input { background: #111; border: 1px solid #444; color: #10b981; padding: 4px 8px; border-radius: 4px; font-size: 13px; font-weight: bold; width: 60px; text-align: center; outline: none; transition: border 0.2s; }
.pm-status-input:focus { border-color: #10b981; }

/* CUSTOM METHOD DROPDOWN */
.pm-method-wrapper { position: relative; user-select: none; }
.pm-method-display { display: flex; align-items: center; justify-content: center; gap: 4px; padding: 10px 16px; font-weight: 700; font-size: 13px; min-width: 90px; transition: background 0.2s; border-radius: 6px 0 0 6px; cursor: pointer; }
.pm-method-display:hover { background: rgba(255,255,255,0.05); }
.pm-method-display.read-only { cursor: default; }
.pm-method-display.read-only:hover { background: transparent; }
.pm-chevron { width: 16px; height: 16px; fill: currentColor; opacity: 0.6; }
.pm-dropdown-overlay { position: fixed; top: 0; left: 0; right: 0; bottom: 0; z-index: 99; cursor: default; }
.pm-method-dropdown { position: absolute; top: 100%; left: 0; margin-top: 4px; background: #252525; border: 1px solid #444; border-radius: 6px; box-shadow: 0 10px 30px rgba(0,0,0,0.5); z-index: 100; min-width: 120px; padding: 4px 0; }
.pm-method-option { padding: 8px 16px; font-size: 12px; font-weight: 700; cursor: pointer; transition: background 0.1s; }
.pm-method-option:hover { background: #333; }

/* Method Colors */
.get { color: #3b82f6; }
.post { color: #10b981; }
.put { color: #f59e0b; }
.delete { color: #ef4444; }
.patch { color: #eab308; }
.options, .head { color: #8b5cf6; }

/* TABS */
.pm-tabs { display: flex; gap: 24px; padding: 0 24px; border-bottom: 1px solid #333; flex-shrink: 0; margin-top: 8px; }
.pm-tab { color: #888; font-size: 13px; font-weight: 500; padding: 10px 0; cursor: pointer; border-bottom: 2px solid transparent; transition: all 0.2s; }
.pm-tab:hover { color: #e0e0e0; }
.pm-tab.active { color: #e0e0e0; border-bottom-color: #f59e0b; }

/* EDITOR AREA */
.pm-editor-area { flex: 1; display: flex; flex-direction: column; background: #111; overflow: hidden; }
.pm-editor-wrapper { display: flex; flex-direction: column; height: 100%; }
.pm-helper-text { font-size: 11px; color: #666; padding: 8px 24px; border-bottom: 1px solid #222; background: #181818; }
.pm-codemirror { flex: 1; overflow: hidden; font-size: 13px; }
.pm-codemirror :deep(.cm-editor) { height: 100% !important; }

/* PARAMS GRID */
.pm-params-container { padding: 16px 24px; overflow-y: auto; flex: 1; }
.pm-param-header { display: flex; font-size: 11px; color: #888; font-weight: 600; padding-bottom: 8px; border-bottom: 1px solid #333; margin-bottom: 8px; }
.pm-param-col { flex: 1; padding: 0 8px; }
.pm-param-action { width: 32px; }
.pm-param-row { display: flex; gap: 8px; margin-bottom: 8px; align-items: center; }
.pm-param-input { flex: 1; background: transparent; border: 1px solid #333; color: #ccc; padding: 6px 10px; font-size: 13px; font-family: 'Consolas', monospace; border-radius: 4px; outline: none; transition: border 0.2s; }
.pm-param-input:focus { border-color: #f59e0b; background: #1a1a1b; }
.pm-param-del { background: transparent; border: none; color: #555; cursor: pointer; width: 32px; font-size: 14px; transition: color 0.2s; display: flex; align-items: center; justify-content: center; height: 100%; }
.pm-param-del:hover { color: #ef4444; }

/* FOOTER ACTIONS */
.pm-footer { display: flex; justify-content: flex-end; gap: 12px; padding: 16px 20px; background: #1a1a1b; border-top: 1px solid #333; flex-shrink: 0; }
.pm-btn-drop { background: transparent; color: #ef4444; border: 1px solid rgba(239, 68, 68, 0.4); border-radius: 6px; padding: 8px 24px; font-weight: 600; font-size: 13px; cursor: pointer; transition: all 0.2s; }
.pm-btn-drop:hover { background: rgba(239, 68, 68, 0.1); border-color: #ef4444; }
.pm-btn-execute { background: #10b981; color: white; border: none; border-radius: 6px; padding: 8px 32px; font-weight: 600; font-size: 13px; cursor: pointer; transition: background 0.2s; }
.pm-btn-execute:hover { background: #059669; }
</style>