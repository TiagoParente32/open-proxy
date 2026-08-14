<script setup>
import { Codemirror } from 'vue-codemirror'
import { json } from '@codemirror/lang-json'
import { EditorView } from '@codemirror/view'
import { showComposeModal, composeData, sendComposedRequest, isComposeEditMode } from '../store.js'
import { ref, watch, computed } from 'vue'
import CodeMirrorEditor from './CodeMirrorEditor.vue'
import { cmTheme } from '../composables/useTheme'

const extensions = computed(() => [json(), ...cmTheme.value, EditorView.lineWrapping])

const activeTab = ref('Body')
const showMethodMenu = ref(false)

const selectMethod = (method) => {
  composeData.value.method = method
  showMethodMenu.value = false
}

const queryParams = ref([{ key: '', value: '' }])

// URL -> Grid (runs when typing in the URL bar, or when the modal opens)
const syncUrlToParams = () => {
  const url = composeData.value.url || '';
  const parts = url.split('?');
  const newParams = [];

  if (parts.length > 1 && parts[1]) {
    const pairs = parts[1].split('&');
    pairs.forEach(pair => {
      const [k, v] = pair.split('=');
      if (k) {
        newParams.push({
          key: decodeURIComponent(k),
          value: v !== undefined ? decodeURIComponent(v) : ''
        });
      }
    });
  }
  newParams.push({ key: '', value: '' }); // Always keep a blank row at the bottom
  queryParams.value = newParams;
}

// Grid -> URL (runs when typing in the Params grid)
const syncParamsToUrl = () => {
  let baseUrl = composeData.value.url.split('?')[0] || '';
  const params = [];

  queryParams.value.forEach(p => {
    if (p.key) {
      params.push(`${encodeURIComponent(p.key)}=${encodeURIComponent(p.value)}`);
    }
  });

  if (params.length > 0) {
    composeData.value.url = `${baseUrl}?${params.join('&')}`;
  } else {
    composeData.value.url = baseUrl;
  }
}

const reqHeaders = ref([{ key: '', value: '' }])

const syncReqHeadersFromJson = () => {
  try {
    const parsed = JSON.parse(composeData.value.req_headers || '{}')
    const rows = Object.entries(parsed).map(([k, v]) => ({ key: k, value: String(v) }))
    rows.push({ key: '', value: '' })
    reqHeaders.value = rows
  } catch (e) {
    reqHeaders.value = [{ key: '', value: '' }]
  }
}

const syncReqHeadersToJson = () => {
  const obj = {}
  reqHeaders.value.forEach(h => { if (h.key) obj[h.key] = h.value })
  composeData.value.req_headers = JSON.stringify(obj, null, 2)
}

const checkHeaderRow = (index) => {
  if (index === reqHeaders.value.length - 1 && reqHeaders.value[index].key !== '') {
    reqHeaders.value.push({ key: '', value: '' })
  }
}

const removeHeaderRow = (index) => {
  reqHeaders.value.splice(index, 1)
  if (reqHeaders.value.length === 0) reqHeaders.value.push({ key: '', value: '' })
  syncReqHeadersToJson()
}

// Populate the params/headers grids whenever the modal opens, so Edit Mode prefills correctly
watch(() => showComposeModal.value, (isOpen) => {
  if (isOpen) {
    syncUrlToParams();
    syncReqHeadersFromJson();
  }
})

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
</script>

<template>
  <Teleport to="body">
    <div v-if="showComposeModal && composeData" class="modal-overlay" @mousedown.self="showComposeModal = false">

      <div class="pm-modal">

        <div class="pm-header">
          <strong class="pm-title">
            {{ isComposeEditMode ? '✏️ Edit & Repeat Request' : '✨ Compose New Request' }}
          </strong>
          <button class="pm-close-btn" @click="showComposeModal = false">✕</button>
        </div>

        <div class="pm-omnibar-container">
          <div class="pm-omnibar">

            <div class="pm-method-wrapper">
              <div class="pm-method-display" :class="composeData.method.toLowerCase()"
                @click="showMethodMenu = !showMethodMenu">
                {{ composeData.method }}
                <svg class="pm-chevron" viewBox="0 0 24 24">
                  <path d="M7 10l5 5 5-5z" />
                </svg>
              </div>

              <div v-if="showMethodMenu" class="pm-dropdown-overlay" @click.stop="showMethodMenu = false"></div>

              <div v-if="showMethodMenu" class="pm-method-dropdown">
                <div v-for="m in ['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS', 'HEAD']" :key="m"
                  class="pm-method-option" :class="m.toLowerCase()" @click="selectMethod(m)">
                  {{ m }}
                </div>
              </div>
            </div>

            <div class="pm-divider"></div>

            <input type="text" v-model="composeData.url" class="pm-url-input" placeholder="Enter request URL"
              @input="syncUrlToParams" />
          </div>
          <button class="pm-send-btn" @click="sendComposedRequest">Send</button>
        </div>

        <div class="pm-tabs">
          <span class="pm-tab" :class="{ active: activeTab === 'Body' }" @click="activeTab = 'Body'">Body</span>
          <span class="pm-tab" :class="{ active: activeTab === 'Params' }" @click="activeTab = 'Params'">Params</span>
          <span class="pm-tab" :class="{ active: activeTab === 'Headers' }"
            @click="activeTab = 'Headers'">Headers</span>
        </div>

        <div class="pm-editor-area">

          <div v-if="activeTab === 'Body'" class="pm-editor-wrapper">
            <div class="pm-helper-text">Raw request payload</div>
            <CodeMirrorEditor v-model="composeData.req_body" :extensions="extensions" class="pm-codemirror" />
          </div>

          <div v-if="activeTab === 'Params'" class="pm-editor-wrapper">
            <div class="pm-helper-text">Query Parameters</div>
            <div class="pm-params-container">
              <div class="pm-kv-table">
                <div class="pm-kv-head">
                  <span class="pm-kv-head-cell">Key</span>
                  <span class="pm-kv-head-cell">Value</span>
                  <span></span>
                </div>
                <div class="pm-kv-row" v-for="(param, index) in queryParams" :key="index">
                  <input type="text" v-model="param.key" placeholder="e.g. page" class="pm-kv-input"
                    @input="syncParamsToUrl(); checkParamRow(index)" />
                  <input type="text" v-model="param.value" placeholder="e.g. 1" class="pm-kv-input pm-kv-input-last"
                    @input="syncParamsToUrl()" />
                  <button class="pm-kv-del" @click="removeParamRow(index)" title="Remove Row">
                    <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
                  </button>
                </div>
              </div>
            </div>
          </div>

          <div v-if="activeTab === 'Headers'" class="pm-editor-wrapper">
            <div class="pm-helper-text">Request Headers</div>
            <div class="pm-params-container">
              <div class="pm-kv-table">
                <div class="pm-kv-head">
                  <span class="pm-kv-head-cell">Key</span>
                  <span class="pm-kv-head-cell">Value</span>
                  <span></span>
                </div>
                <div class="pm-kv-row" v-for="(header, index) in reqHeaders" :key="index">
                  <input type="text" v-model="header.key" placeholder="e.g. Content-Type" class="pm-kv-input"
                    @input="syncReqHeadersToJson(); checkHeaderRow(index)" />
                  <input type="text" v-model="header.value" placeholder="e.g. application/json" class="pm-kv-input pm-kv-input-last"
                    @input="syncReqHeadersToJson()" />
                  <button class="pm-kv-del" @click="removeHeaderRow(index)" title="Remove Row">
                    <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
                  </button>
                </div>
              </div>
            </div>
          </div>


        </div>

      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: var(--overlay-light);
  z-index: 99999;
  display: flex;
  justify-content: center;
  align-items: center;
}

.pm-modal {
  background: var(--bg-main);
  border-radius: 8px;
  border: 1px solid var(--border);
  width: 850px;
  height: 650px;
  display: flex;
  flex-direction: column;
  box-shadow: var(--shadow-lg);
  overflow: hidden;
}

.pm-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 20px;
  background: var(--bg-card);
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}

.pm-title {
  color: var(--fg-secondary);
  font-size: 13px;
  font-weight: 600;
}

.pm-close-btn {
  background: transparent;
  border: none;
  color: var(--fg-muted);
  font-size: 16px;
  cursor: pointer;
  transition: color 0.2s;
}

.pm-close-btn:hover {
  color: var(--error);
}

.pm-omnibar-container {
  display: flex;
  gap: 8px;
  padding: 16px 20px 8px 20px;
  flex-shrink: 0;
}

.pm-omnibar {
  display: flex;
  flex: 1;
  align-items: center;
  background: var(--bg-deepest);
  border: 1px solid var(--border);
  border-radius: 6px;
  transition: border-color 0.2s;
}

.pm-omnibar:focus-within {
  border-color: var(--accent);
}

.pm-divider {
  width: 1px;
  height: 24px;
  background: var(--border);
}

.pm-url-input {
  flex: 1;
  background: transparent;
  border: none;
  color: var(--fg-secondary);
  padding: 10px 12px;
  font-size: 13px;
  outline: none;
  font-family: 'Consolas', monospace;
}

.pm-send-btn {
  background: var(--accent);
  color: white;
  border: none;
  border-radius: 6px;
  padding: 0 24px;
  font-weight: 600;
  font-size: 13px;
  cursor: pointer;
  transition: background 0.2s;
}

.pm-send-btn:hover {
  background: var(--accent-hover);
}

.pm-method-wrapper {
  position: relative;
  user-select: none;
}

.pm-method-display {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  padding: 10px 16px;
  font-weight: 700;
  font-size: 13px;
  min-width: 90px;
  transition: background 0.2s;
  border-radius: 6px 0 0 6px;
  cursor: pointer;
}

.pm-method-display:hover {
  background: var(--surface-hover);
}

.pm-chevron {
  width: 16px;
  height: 16px;
  fill: currentColor;
  opacity: 0.6;
}

/* Full-screen invisible overlay so any outside click closes the dropdown */
.pm-dropdown-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  z-index: 99;
  cursor: default;
}

.pm-method-dropdown {
  position: absolute;
  top: 100%;
  left: 0;
  margin-top: 4px;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 6px;
  box-shadow: var(--shadow-lg);
  z-index: 100;
  min-width: 120px;
  padding: 4px 0;
}

.pm-method-option {
  padding: 8px 16px;
  font-size: 12px;
  font-weight: 700;
  cursor: pointer;
  transition: background 0.1s;
}

.pm-method-option:hover {
  background: var(--surface-hover-strong);
}

.get {
  color: var(--method-get);
}

.post {
  color: var(--method-post);
}

.put {
  color: var(--method-put);
}

.delete {
  color: var(--method-delete);
}

.patch {
  color: var(--method-patch);
}

.options,
.head {
  color: var(--method-other);
}

.pm-tabs {
  display: flex;
  gap: 24px;
  padding: 0 24px;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
  margin-top: 8px;
}

.pm-tab {
  color: var(--fg-muted);
  font-size: 13px;
  font-weight: 500;
  padding: 10px 0;
  cursor: pointer;
  border-bottom: 2px solid transparent;
  transition: all 0.2s;
}

.pm-tab:hover {
  color: var(--fg-secondary);
}

.pm-tab.active {
  color: var(--fg-secondary);
  border-bottom-color: var(--accent);
}

.pm-editor-area {
  flex: 1;
  display: flex;
  flex-direction: column;
  background: var(--bg-input);
  overflow: hidden;
}

.pm-editor-wrapper {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.pm-helper-text {
  font-size: 11px;
  color: var(--fg-muted);
  padding: 8px 24px;
  border-bottom: 1px solid var(--border-subtle);
  background: var(--bg-card);
}

.pm-codemirror {
  flex: 1;
  overflow: hidden;
  font-size: 13px;
}

.pm-codemirror :deep(.cm-editor) {
  height: 100% !important;
}

.pm-params-container { padding: 16px 20px; overflow-y: auto; flex: 1; }

.pm-kv-table {
  border: 1px solid var(--border);
  border-radius: 8px;
  overflow: hidden;
  background: var(--bg-deepest);
}

.pm-kv-head {
  display: grid;
  grid-template-columns: 1fr 1fr 32px;
  background: var(--bg-sidebar);
  border-bottom: 1px solid var(--border);
}
.pm-kv-head-cell {
  padding: 6px 12px;
  font-size: 10px;
  font-weight: 600;
  color: var(--fg-muted);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}
.pm-kv-head-cell + .pm-kv-head-cell { border-left: 1px solid var(--border); }

.pm-kv-row {
  display: grid;
  grid-template-columns: 1fr 1fr 32px;
  border-bottom: 1px solid var(--border-subtle);
  align-items: stretch;
  transition: background 0.1s;
}
.pm-kv-row:last-child { border-bottom: none; }
.pm-kv-row:hover { background: var(--bg-active); }

.pm-kv-input {
  background: transparent;
  border: none;
  border-right: 1px solid var(--border-subtle);
  color: var(--fg-secondary);
  padding: 8px 12px;
  font-size: 12px;
  font-family: 'Consolas', monospace;
  outline: none;
  width: 100%;
  box-sizing: border-box;
  transition: background 0.1s, color 0.1s;
}
.pm-kv-input::placeholder { color: var(--fg-placeholder); }
.pm-kv-input:focus { background: var(--accent-muted); color: var(--fg-primary); }
.pm-kv-input-last { border-right: none; }

.pm-kv-del {
  display: flex;
  align-items: center;
  justify-content: center;
  background: transparent;
  border: none;
  color: var(--fg-placeholder);
  cursor: pointer;
  transition: color 0.15s;
  padding: 0;
  width: 32px;
}
.pm-kv-del:hover { color: var(--error); }
</style>