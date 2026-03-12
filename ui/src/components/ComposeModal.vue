<script setup>
import { Codemirror } from 'vue-codemirror'
import { json } from '@codemirror/lang-json'
import { oneDark } from '@codemirror/theme-one-dark'
import { EditorView } from '@codemirror/view'
import { showComposeModal, composeData, sendComposedRequest, isComposeEditMode } from '../store.js'
import { ref, watch } from 'vue'

const extensions = [json(), oneDark, EditorView.lineWrapping]

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
            <codemirror v-model="composeData.req_body" :extensions="extensions" class="pm-codemirror" />
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
            <codemirror v-model="composeData.req_headers" :extensions="extensions" class="pm-codemirror" />
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
  background: rgba(0, 0, 0, 0.6);
  z-index: 99999;
  display: flex;
  justify-content: center;
  align-items: center;
  backdrop-filter: blur(4px);
}

.pm-modal {
  background: #1e1e1e;
  border-radius: 8px;
  border: 1px solid #333;
  width: 850px;
  height: 650px;
  display: flex;
  flex-direction: column;
  box-shadow: 0 20px 50px rgba(0, 0, 0, 0.5);
  overflow: hidden;
}

/* HEADER */
.pm-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 20px;
  background: #252525;
  border-bottom: 1px solid #333;
  flex-shrink: 0;
}

.pm-title {
  color: #e0e0e0;
  font-size: 13px;
  font-weight: 600;
}

.pm-close-btn {
  background: transparent;
  border: none;
  color: #888;
  font-size: 16px;
  cursor: pointer;
  transition: color 0.2s;
}

.pm-close-btn:hover {
  color: #ef4444;
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
  background: #121212;
  border: 1px solid #444;
  border-radius: 6px;
  transition: border-color 0.2s;
}

.pm-omnibar:focus-within {
  border-color: #3b82f6;
}

.pm-divider {
  width: 1px;
  height: 24px;
  background: #333;
}

.pm-url-input {
  flex: 1;
  background: transparent;
  border: none;
  color: #e0e0e0;
  padding: 10px 12px;
  font-size: 13px;
  outline: none;
  font-family: 'Consolas', monospace;
}

.pm-send-btn {
  background: #3b82f6;
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
  background: #2563eb;
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
  background: rgba(255, 255, 255, 0.05);
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
  background: #252525;
  border: 1px solid #444;
  border-radius: 6px;
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.5);
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
  background: #333;
}

/* Method Colors */
.get {
  color: #3b82f6;
}

.post {
  color: #10b981;
}

.put {
  color: #f59e0b;
}

.delete {
  color: #ef4444;
}

.patch {
  color: #eab308;
}

.options,
.head {
  color: #8b5cf6;
}

/* TABS */
.pm-tabs {
  display: flex;
  gap: 24px;
  padding: 0 24px;
  border-bottom: 1px solid #333;
  flex-shrink: 0;
  margin-top: 8px;
}

.pm-tab {
  color: #888;
  font-size: 13px;
  font-weight: 500;
  padding: 10px 0;
  cursor: pointer;
  border-bottom: 2px solid transparent;
  transition: all 0.2s;
}

.pm-tab:hover {
  color: #e0e0e0;
}

.pm-tab.active {
  color: #e0e0e0;
  border-bottom-color: #f59e0b;
}

/* EDITOR AREA */
.pm-editor-area {
  flex: 1;
  display: flex;
  flex-direction: column;
  background: #111;
  overflow: hidden;
}

.pm-editor-wrapper {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.pm-helper-text {
  font-size: 11px;
  color: #666;
  padding: 8px 24px;
  border-bottom: 1px solid #222;
  background: #181818;
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
  color: #888;
  font-weight: 600;
  padding-bottom: 8px;
  border-bottom: 1px solid #333;
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
  border: 1px solid #333;
  color: #ccc;
  padding: 6px 10px;
  font-size: 13px;
  font-family: 'Consolas', monospace;
  border-radius: 4px;
  outline: none;
  transition: border 0.2s;
}

.pm-param-input:focus {
  border-color: #3b82f6;
  background: #1a1a1b;
}

.pm-param-del {
  background: transparent;
  border: none;
  color: #555;
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
  color: #ef4444;
}
</style>