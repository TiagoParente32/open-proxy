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

// --- TWO-WAY URL & PARAMS SYNCING ---
const queryParams = ref([{ key: '', value: '' }])

// 1. URL -> Grid (Runs when you type in the URL bar, or when the modal opens)
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

// 2. Grid -> URL (Runs when you type in the Params grid)
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

// Auto-fill the grid whenever the modal is opened (perfect for Edit Mode!)
watch(() => showComposeModal.value, (isOpen) => {
  if (isOpen) {
    syncUrlToParams();
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
  syncParamsToUrl() // Update URL when a row is deleted
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
              <div class="pm-param-header">
                <div class="pm-param-col">Key</div>
                <div class="pm-param-col">Value</div>
                <div class="pm-param-action"></div>
              </div>
              <div class="pm-param-row" v-for="(param, index) in queryParams" :key="index">
                <input type="text" v-model="param.key" placeholder="Key" class="pm-param-input"
                  @input="syncParamsToUrl(); checkParamRow(index)" />
                <input type="text" v-model="param.value" placeholder="Value" class="pm-param-input"
                  @input="syncParamsToUrl()" />
                <button class="pm-param-del" @click="removeParamRow(index)" title="Remove Row">✕</button>
              </div>
            </div>
          </div>

          <div v-if="activeTab === 'Headers'" class="pm-editor-wrapper">
            <div class="pm-helper-text">Format as JSON (e.g., { "Content-Type": "application/json" })</div>
            <CodeMirrorEditor v-model="composeData.req_headers" :extensions="extensions" class="pm-codemirror" />
          </div>


        </div>

      </div>
    </div>
  </Teleport>
</template>

<style scoped>
/* OVERLAY & MODAL */
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
  backdrop-filter: blur(4px);
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

/* HEADER */
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

/* OMNIBAR */
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

/* CUSTOM METHOD DROPDOWN */
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

/* THE MAGIC OVERLAY THAT FIXES THE DROPDOWN */
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

/* Method Colors */
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

/* TABS */
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

/* EDITOR AREA */
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

/* PARAMS GRID */
.pm-params-container {
  padding: 16px 24px;
  overflow-y: auto;
  flex: 1;
}

.pm-param-header {
  display: flex;
  font-size: 11px;
  color: var(--fg-muted);
  font-weight: 600;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--border);
  margin-bottom: 8px;
}

.pm-param-col {
  flex: 1;
  padding: 0 8px;
}

.pm-param-action {
  width: 32px;
}

.pm-param-row {
  display: flex;
  gap: 8px;
  margin-bottom: 8px;
  align-items: center;
}

.pm-param-input {
  flex: 1;
  background: transparent;
  border: 1px solid var(--border);
  color: var(--fg-secondary);
  padding: 6px 10px;
  font-size: 13px;
  font-family: 'Consolas', monospace;
  border-radius: 4px;
  outline: none;
  transition: border 0.2s;
}

.pm-param-input:focus {
  border-color: var(--accent);
  background: var(--bg-sidebar);
}

.pm-param-del {
  background: transparent;
  border: none;
  color: var(--fg-placeholder);
  cursor: pointer;
  width: 32px;
  font-size: 14px;
  transition: color 0.2s;
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
}

.pm-param-del:hover {
  color: var(--error);
}
</style>