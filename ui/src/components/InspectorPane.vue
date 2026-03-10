<script setup>
import { Splitpanes, Pane } from 'splitpanes'
import { Codemirror } from 'vue-codemirror'
import { json } from '@codemirror/lang-json'
import { python } from '@codemirror/lang-python'
import { javascript } from '@codemirror/lang-javascript'
import { go } from '@codemirror/lang-go'
import { rust } from '@codemirror/lang-rust'
import { oneDark } from '@codemirror/theme-one-dark'
import { EditorView, keymap } from '@codemirror/view'
import { search, searchKeymap } from '@codemirror/search'
import { EditorState } from '@codemirror/state' // <-- NEW: Imported EditorState

import { selectedRequest, activeReqTab, activeResTab } from '../store.js'
import { computed, ref, onMounted, onUnmounted } from 'vue' // <-- NEW: Added hooks
import WebSocketInspector from './WebSocketInspector.vue'

const blockGlobalSearch = (e) => {
  if ((e.ctrlKey || e.metaKey) && e.key === 'f') {
    if (!e.defaultPrevented) {
      e.preventDefault(); 
    }
  }
}
onMounted(() => window.addEventListener('keydown', blockGlobalSearch))
onUnmounted(() => window.removeEventListener('keydown', blockGlobalSearch))

const isWebSocket = computed(() => {
  if (!selectedRequest.value) return false;
  return selectedRequest.value.status === 101 || 
         selectedRequest.value.url.startsWith('ws://') || 
         selectedRequest.value.url.startsWith('wss://');
})

const extensions = [
  json(), 
  oneDark, 
  EditorView.lineWrapping, 
  search({ top: true }),
  keymap.of(searchKeymap),
  EditorState.readOnly.of(true) // <-- NEW: Makes it read-only but still focusable!
]

const formatJson = (str) => {
  if (!str) return '// No body data'
  try { return JSON.stringify(JSON.parse(str), null, 2) } catch (e) { return str }
}

const getMethodColor = (method) => {
  const colors = { GET: '#3b82f6', POST: '#10b981', PUT: '#f59e0b', DELETE: '#ef4444', OPTIONS: '#8b5cf6' }
  return colors[method] || '#8b949e'
}

// --- CODE GENERATION ENGINE ---
const activeCodeLang = ref('cURL')
const codeLangs = ['cURL', 'Python', 'Node.js', 'Go', 'Rust']
const copyLabel = ref('Copy')

const dynamicCodeExtensions = computed(() => {
  const base = [
    oneDark, 
    EditorView.lineWrapping, 
    search({ top: true }),
    keymap.of(searchKeymap),
    EditorState.readOnly.of(true) // <-- NEW: Makes it read-only but still focusable!
  ]
  if (activeCodeLang.value === 'Python') return [...base, python()]
  if (activeCodeLang.value === 'Node.js') return [...base, javascript()]
  if (activeCodeLang.value === 'Go') return [...base, go()]
  if (activeCodeLang.value === 'Rust') return [...base, rust()]
  return base 
})

const generatedCode = computed(() => {
  const req = selectedRequest.value;
  if (!req) return '';

  const method = req.method.toUpperCase();
  const url = req.url;
  const headers = req.req_headers || {};
  
  let body = req.req_body || '';
  const hasValidBody = body && !req.req_is_image && !body.startsWith('// [');

  if (activeCodeLang.value === 'cURL') {
    let cmd = `curl -X ${method} "${url}"`;
    for (const [k, v] of Object.entries(headers)) {
      const safeVal = String(v).replace(/"/g, '\\"');
      cmd += ` \\\n  -H "${k}: ${safeVal}"`;
    }
    if (hasValidBody) {
      const safeBody = body.replace(/'/g, "'\\''");
      cmd += ` \\\n  -d '${safeBody}'`;
    }
    return cmd;
  }

  if (activeCodeLang.value === 'Python') {
    let code = `import requests\n\nurl = "${url}"\n\n`;
    if (hasValidBody) {
      code += `payload = """${body.replace(/"""/g, '\\"\\"\\"')}"""\n\n`;
    }
    code += `headers = ${JSON.stringify(headers, null, 2)}\n\n`;
    code += `response = requests.request("${method}", url, headers=headers${hasValidBody ? ', data=payload' : ''})\n\n`;
    code += `print(response.text)`;
    return code;
  }

  if (activeCodeLang.value === 'Node.js') {
    let code = `const options = {\n  method: '${method}',\n  headers: ${JSON.stringify(headers, null, 2)}`;
    if (hasValidBody) {
       code += `,\n  body: \`${body.replace(/`/g, '\\`')}\``;
    }
    code += `\n};\n\n`;
    code += `fetch("${url}", options)\n  .then(res => res.text())\n  .then(text => console.log(text))\n  .catch(err => console.error(err));`;
    return code;
  }

  if (activeCodeLang.value === 'Go') {
    let code = `package main\n\nimport (\n\t"fmt"\n\t"io"\n\t"net/http"\n\t"strings"\n)\n\nfunc main() {\n\turl := "${url}"\n\tmethod := "${method}"\n\n`;
    if (hasValidBody) {
      const safeBody = body.replace(/`/g, '` + "`" + `');
      code += `\tpayload := strings.NewReader(\`${safeBody}\`)\n\n`;
    } else {
      code += `\tvar payload io.Reader = nil\n\n`;
    }
    code += `\tclient := &http.Client {}\n\treq, err := http.NewRequest(method, url, payload)\n\n\tif err != nil {\n\t\tfmt.Println(err)\n\t\treturn\n\t}\n`;
    for (const [k, v] of Object.entries(headers)) {
      const safeVal = String(v).replace(/"/g, '\\"');
      code += `\treq.Header.Add("${k}", "${safeVal}")\n`;
    }
    code += `\n\tres, err := client.Do(req)\n\tif err != nil {\n\t\tfmt.Println(err)\n\t\treturn\n\t}\n\tdefer res.Body.Close()\n\n\tresBody, err := io.ReadAll(res.Body)\n\tfmt.Println(string(resBody))\n}\n`;
    return code;
  }

  if (activeCodeLang.value === 'Rust') {
    let code = `use reqwest::Client;\n\n#[tokio::main]\nasync fn main() -> Result<(), Box<dyn std::error::Error>> {\n    let client = Client::new();\n`;
    code += `    let res = client.request(reqwest::Method::${method}, "${url}")\n`;
    for (const [k, v] of Object.entries(headers)) {
      const safeVal = String(v).replace(/"/g, '\\"');
      code += `        .header("${k}", "${safeVal}")\n`;
    }
    if (hasValidBody) {
       let hashes = "#";
       while (body.includes(`"${hashes}`)) { hashes += "#"; }
       code += `        .body(r${hashes}"${body}"${hashes})\n`;
    }
    code += `        .send()\n        .await?;\n\n    let text = res.text().await?;\n    println!("{}", text);\n    Ok(())\n}\n`;
    return code;
  }

  return '';
})

const copyCode = () => {
  navigator.clipboard.writeText(generatedCode.value)
  copyLabel.value = 'Copied!'
  setTimeout(() => { copyLabel.value = 'Copy' }, 2000)
}

// --- STRUCTURED HEX GENERATOR ---
const getHexRows = (req, type) => {
  if (!req) return { rows: [], truncated: false, total: 0 };
  
  const body = type === 'req' ? req.req_body : req.res_body;
  const isImage = type === 'req' ? req.req_is_image : req.res_is_image;
  const isBinary = type === 'req' ? req.req_is_binary : req.res_is_binary;

  if (!body || body.startsWith('// [')) return { rows: [], truncated: false, total: 0 };

  let buffer;
  if (isImage) {
    const b64 = body.split(',')[1];
    if (!b64) return { rows: [], truncated: false, total: 0 };
    const binStr = atob(b64);
    buffer = Uint8Array.from(binStr, (m) => m.codePointAt(0));
  } else if (isBinary) {
    const binStr = atob(body);
    buffer = Uint8Array.from(binStr, (m) => m.codePointAt(0));
  } else {
    buffer = new TextEncoder().encode(body);
  }

  const MAX_BYTES = 10240; // 10KB UI limit
  const length = Math.min(buffer.length, MAX_BYTES);
  const rows = [];

  for (let i = 0; i < length; i += 16) {
    let offset = i.toString(16).padStart(8, '0').toUpperCase();
    let bytes = [];
    let ascii = '';

    for (let j = 0; j < 16; j++) {
      if (i + j < length) {
        let b = buffer[i + j];
        bytes.push(b.toString(16).padStart(2, '0').toUpperCase());
        ascii += (b >= 32 && b <= 126) ? String.fromCharCode(b) : '.';
      } else {
        bytes.push('');
        ascii += ' ';
      }
    }
    rows.push({ offset, bytes, ascii });
  }

  return { rows, truncated: buffer.length > MAX_BYTES, total: buffer.length };
}

</script>

<template>
  <div class="detail-container">
    
    <div v-if="selectedRequest" style="height: 100%; display: flex; flex-direction: column;">
      
      <div class="inspector-url-bar">
        <span class="method-badge" :style="{ backgroundColor: getMethodColor(selectedRequest.method) + '20', color: getMethodColor(selectedRequest.method) }">
          {{ selectedRequest.method }}
        </span>
        <span class="url-text" :title="selectedRequest.url">{{ selectedRequest.url }}</span>
      </div>

      <div style="flex: 1; overflow: hidden; display: flex; flex-direction: column;">
        
        <WebSocketInspector v-if="isWebSocket" style="flex: 1;" />
        
        <splitpanes v-else class="custom-theme">
          <pane size="50">
            <div class="inspector-panel">
              <div class="inspector-toolbar">
                <span class="panel-title">Request</span>
                <div class="panel-tabs"><span v-for="tab in ['Header', 'Body', 'Code', 'Hex']" :key="tab" @click="activeReqTab = tab" class="panel-tab" :class="{ active: activeReqTab === tab }">{{ tab }}</span></div>
              </div>
              <div class="inspector-content">
                <table v-if="activeReqTab === 'Header'" class="kv-table"><tr v-for="(value, key) in selectedRequest.req_headers" :key="key"><td class="kv-key">{{ key }}</td><td class="kv-value">{{ value }}</td></tr></table>
                
                <div v-if="activeReqTab === 'Body'" style="height: 100%; display: flex; justify-content: center; align-items: center; background: #111;">
                  <img v-if="selectedRequest.req_is_image" :src="selectedRequest.req_body" style="max-width: 100%; max-height: 100%; object-fit: contain; padding: 16px; box-sizing: border-box;" />
                  <codemirror v-else :model-value="formatJson(selectedRequest.req_body)" :style="{ height: '100%', width: '100%' }" :extensions="extensions" />
                </div>

                <div v-if="activeReqTab === 'Code'" class="code-tab-container">
                  <div class="code-toolbar">
                    <div class="lang-pills">
                      <button 
                        v-for="lang in codeLangs" :key="lang" 
                        class="lang-pill" :class="{active: activeCodeLang === lang}" 
                        @click="activeCodeLang = lang"
                      >
                        {{ lang }}
                      </button>
                    </div>
                    <button class="copy-btn" @click="copyCode">{{ copyLabel }}</button>
                  </div>
                  <div style="flex: 1; overflow: hidden; background: #111;">
                     <codemirror :model-value="generatedCode" :style="{ height: '100%', width: '100%' }" :extensions="dynamicCodeExtensions" />
                  </div>
                </div>
                
                <div v-if="activeReqTab === 'Hex'" class="hex-viewer">
                  <div class="hex-header">
                    <div class="hex-offset">Offset</div>
                    <div class="hex-bytes">
                      <span v-for="n in 16" :key="n">{{ (n-1).toString(16).padStart(2, '0').toUpperCase() }}</span>
                    </div>
                    <div class="hex-ascii">Decoded</div>
                  </div>
                  
                  <div class="hex-body">
                    <div v-if="getHexRows(selectedRequest, 'req').truncated" class="hex-warning">
                      Showing first 10KB (Total: {{ getHexRows(selectedRequest, 'req').total }} bytes)
                    </div>
                    
                    <div class="hex-row" v-for="row in getHexRows(selectedRequest, 'req').rows" :key="row.offset">
                      <div class="hex-offset">{{ row.offset }}</div>
                      <div class="hex-bytes">
                        <span v-for="(byte, i) in row.bytes" :key="i" :class="{'empty': !byte}">{{ byte || '--' }}</span>
                      </div>
                      <div class="hex-ascii">{{ row.ascii }}</div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </pane>
          
          <pane size="50">
            <div class="inspector-panel">
              <div class="inspector-toolbar">
                <span class="panel-title" :class="{'text-green': selectedRequest.status < 400, 'text-red': selectedRequest.status >= 400}">Response {{ selectedRequest.status !== '...' ? `(${selectedRequest.status})` : '' }}</span>
                <div class="panel-tabs"><span v-for="tab in ['Header', 'Body', 'Hex']" :key="tab" @click="activeResTab = tab" class="panel-tab" :class="{ active: activeResTab === tab }">{{ tab }}</span></div>
              </div>
              <div class="inspector-content">
                <table v-if="activeResTab === 'Header'" class="kv-table"><tr v-for="(value, key) in selectedRequest.res_headers" :key="key"><td class="kv-key">{{ key }}</td><td class="kv-value">{{ value }}</td></tr></table>
                
                <div v-if="activeResTab === 'Body'" style="height: 100%; display: flex; justify-content: center; align-items: center; background: #111;">
                  <img v-if="selectedRequest.res_is_image" :src="selectedRequest.res_body" style="max-width: 100%; max-height: 100%; object-fit: contain; padding: 16px; box-sizing: border-box;" />
                  <codemirror v-else :model-value="formatJson(selectedRequest.res_body)" :style="{ height: '100%', width: '100%' }" :extensions="extensions" />
                </div>

                <div v-if="activeResTab === 'Hex'" class="hex-viewer">
                  <div class="hex-header">
                    <div class="hex-offset">Offset</div>
                    <div class="hex-bytes">
                      <span v-for="n in 16" :key="n">{{ (n-1).toString(16).padStart(2, '0').toUpperCase() }}</span>
                    </div>
                    <div class="hex-ascii">Decoded</div>
                  </div>
                  
                  <div class="hex-body">
                    <div v-if="getHexRows(selectedRequest, 'res').truncated" class="hex-warning">
                      Showing first 10KB (Total: {{ getHexRows(selectedRequest, 'res').total }} bytes)
                    </div>
                    
                    <div class="hex-row" v-for="row in getHexRows(selectedRequest, 'res').rows" :key="row.offset">
                      <div class="hex-offset">{{ row.offset }}</div>
                      <div class="hex-bytes">
                        <span v-for="(byte, i) in row.bytes" :key="i" :class="{'empty': !byte}">{{ byte || '--' }}</span>
                      </div>
                      <div class="hex-ascii">{{ row.ascii }}</div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </pane>
        </splitpanes>

      </div>
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

.inspector-url-bar {
  display: flex; align-items: center; gap: 12px;
  padding: 8px 16px; background: var(--bg-sidebar);
  border-bottom: 1px solid var(--border); flex-shrink: 0;
}
.url-text { 
  font-family: monospace; 
  font-size: 12px; 
  color: #ccc; 
  user-select: text;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis; 
  flex: 1;
  min-width: 0;
  text-align: left;
}
.method-badge { padding: 2px 6px; border-radius: 4px; font-weight: 700; font-size: 10px; }

/* --- Code Tab Styles --- */
.code-tab-container { height: 100%; display: flex; flex-direction: column; }
.code-toolbar { display: flex; justify-content: space-between; align-items: center; padding: 6px 12px; background: #1e1e1f; border-bottom: 1px solid var(--border); flex-shrink: 0; }
.lang-pills { display: flex; gap: 6px; overflow-x: auto; }
.lang-pills::-webkit-scrollbar { display: none; }
.lang-pill { background: transparent; border: 1px solid transparent; color: #8b949e; padding: 4px 10px; border-radius: 4px; font-size: 11px; font-weight: 500; cursor: pointer; transition: all 0.2s; white-space: nowrap;}
.lang-pill:hover { color: #ccc; background: rgba(255, 255, 255, 0.05); }
.lang-pill.active { background: #2a2d2e; color: #fff; border-color: #444; }
.copy-btn { background: #3b82f6; color: white; border: none; padding: 4px 12px; border-radius: 4px; font-size: 11px; font-weight: bold; cursor: pointer; transition: background 0.2s; min-width: 60px; text-align: center; flex-shrink: 0; }
.copy-btn:hover { background: #2563eb; }



/* ==========================================================
   PREMIUM HEX VIEWER UI
   ========================================================== */
.hex-viewer {
  display: flex;
  flex-direction: column;
  height: 100%;
  background-color: #0d0d0e;
  font-family: 'Consolas', monospace;
  font-size: 11px;
}

.hex-header {
  display: flex;
  padding: 6px 16px;
  background-color: #1a1a1b;
  border-bottom: 1px solid #333;
  color: #8b949e;
  font-weight: bold;
  position: sticky;
  top: 0;
  z-index: 10;
}

.hex-body {
  flex: 1;
  overflow-y: auto;
  padding: 8px 0;
}

.hex-row {
  display: flex;
  padding: 2px 16px;
  cursor: crosshair;
}
.hex-row:hover {
  background-color: rgba(255, 255, 255, 0.05);
}

/* Column 1: Offset */
.hex-offset {
  width: 70px;
  color: #6e7681;
  flex-shrink: 0;
}

/* Column 2: The Bytes */
.hex-bytes {
  display: flex;
  gap: 6px;
  flex: 1;
  color: #e1e4e8;
}
.hex-bytes span {
  width: 16px;
  text-align: center;
}
.hex-bytes span.empty {
  color: #333; /* Faded out dashed lines for empty bytes */
}
/* Creates the classic 8-byte visual gap in the middle */
.hex-bytes span:nth-child(8) {
  margin-right: 8px;
}

/* Column 3: Decoded ASCII */
.hex-ascii {
  width: 130px;
  color: #a1aab3;
  white-space: pre;
  flex-shrink: 0;
  text-align: right;
  letter-spacing: 1px;
}

/* Truncation Warning Banner */
.hex-warning {
  background: rgba(245, 158, 11, 0.1);
  color: #f59e0b;
  padding: 6px 16px;
  border-bottom: 1px solid rgba(245, 158, 11, 0.2);
  margin-bottom: 8px;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  font-size: 11px;
  font-weight: 500;
  text-align: center;
}

/* ==========================================================
   ULTRA-SLEEK CODEMIRROR SEARCH PANEL (MATCHES APP DESIGN)
   ========================================================== */

/* The Main Toolbar Container */
:deep(.cm-panel.cm-search) {
  background-color: var(--bg-sidebar) !important;
  border-bottom: 1px solid var(--border) !important;
  padding: 5px 12px !important;
  display: flex !important;
  align-items: center !important;
  gap: 8px !important;
  font-family: inherit !important;
  flex-wrap: nowrap !important;
  color: #ccc !important;
}

/* The Search Input Field */
:deep(.cm-panel.cm-search .cm-textfield) {
  background-color: #111 !important;
  border: 1px solid var(--border) !important;
  color: #fff !important;
  border-radius: 4px !important;
  padding: 0 8px !important;
  height: 22px !important; /* Exact same height as your toolbar pills! */
  font-size: 11px !important;
  font-family: 'Consolas', monospace !important;
  outline: none !important;
  min-width: 160px !important;
  box-shadow: inset 0 1px 2px rgba(0,0,0,0.3) !important;
  transition: all 0.2s ease !important;
}
:deep(.cm-panel.cm-search .cm-textfield:focus) {
  border-color: #3b82f6 !important;
  box-shadow: 0 0 0 1px rgba(59, 130, 246, 0.3), inset 0 1px 2px rgba(0,0,0,0.3) !important;
}

/* The Next / Prev / All Buttons (Mimicking .secondary-pill) */
:deep(.cm-panel.cm-search .cm-button) {
  display: inline-flex !important;
  align-items: center !important;
  justify-content: center !important;
  height: 22px !important;
  padding: 0 10px !important;
  background: #212324 !important;
  border: 1px solid #303335 !important;
  color: #a1aab3 !important;
  border-radius: 4px !important;
  cursor: pointer !important;
  font-size: 10px !important;
  font-weight: 500 !important;
  transition: all 0.15s ease !important;
  text-transform: capitalize !important;
  background-image: none !important; /* Kills default CM6 gradient */
}
:deep(.cm-panel.cm-search .cm-button:hover) {
  background: #2a2d2e !important;
  color: #fff !important;
  border-color: #404446 !important;
}
:deep(.cm-panel.cm-search .cm-button:active) {
  background: #1a1c1d !important;
}

/* The Checkboxes (Match Case, Regex) */
:deep(.cm-panel.cm-search label) {
  display: inline-flex !important;
  align-items: center !important;
  gap: 4px !important;
  font-size: 10px !important;
  color: #888 !important;
  cursor: pointer !important;
  margin-left: 4px !important;
}
:deep(.cm-panel.cm-search label:hover) {
  color: #ccc !important;
}
:deep(.cm-panel.cm-search input[type="checkbox"]) {
  margin: 0 !important;
  accent-color: #3b82f6 !important;
  cursor: pointer !important;
  width: 12px !important;
  height: 12px !important;
}

/* The Close Button (X) */
:deep(.cm-panel.cm-search button[name="close"]) {
  margin-left: auto !important; /* Pushes it completely to the right */
  background: transparent !important;
  border: none !important;
  color: #666 !important;
  font-size: 16px !important;
  padding: 0 4px !important;
  cursor: pointer !important;
  display: flex !important;
  align-items: center !important;
  justify-content: center !important;
}
:deep(.cm-panel.cm-search button[name="close"]:hover) {
  color: #ef4444 !important;
  background: transparent !important;
  border-color: transparent !important;
}
</style>