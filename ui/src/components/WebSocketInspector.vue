<script setup>
import { computed, ref, watch, nextTick } from 'vue'
import { selectedRequest, wsMessages } from '../store.js'

const searchQuery = ref('')
const scrollContainer = ref(null)
const isAutoScrollPaused = ref(false)

const baseMessages = computed(() => {
  if (!selectedRequest.value) return []
  const reqId = String(selectedRequest.value.id)
  return wsMessages.value[reqId] || []
})

// Supports a leading "!" to invert the search and exclude matching terms
const filteredMessages = computed(() => {
  let msgs = baseMessages.value
  if (!searchQuery.value.trim()) return msgs
  
  const query = searchQuery.value.trim().toLowerCase()
  const invert = query.startsWith('!')
  const term = invert ? query.slice(1).trim() : query

  if (!term) return msgs

  return msgs.filter(msg => {
    const hasTerm = msg.content.toLowerCase().includes(term)
    return invert ? !hasTerm : hasTerm
  })
})

const formatTime = (unixTime) => {
  const d = new Date(unixTime * 1000)
  return d.toISOString().split('T')[1].substring(0, 12) // HH:MM:SS.mmm
}

const formatBytes = (bytes) => {
  if (bytes < 1024) return bytes + ' B'
  return (bytes / 1024).toFixed(1) + ' KB'
}

const handleScroll = () => {
  if (!scrollContainer.value) return
  const { scrollTop, scrollHeight, clientHeight } = scrollContainer.value
  const distanceToBottom = scrollHeight - scrollTop - clientHeight
  isAutoScrollPaused.value = distanceToBottom > 20
}

const scrollToBottom = () => {
  if (!scrollContainer.value) return
  scrollContainer.value.scrollTop = scrollContainer.value.scrollHeight
  isAutoScrollPaused.value = false
}

// Watch filteredMessages so it auto-scrolls when a *relevant* message arrives
watch(() => filteredMessages.value.length, async () => {
  if (isAutoScrollPaused.value) return
  await nextTick()
  scrollToBottom()
})

const copiedIndex = ref(null)

const formatPayload = (content) => {
  if (!content || typeof content !== 'string') return content
  const trimmed = content.trim()

  if ((trimmed.startsWith('{') && trimmed.endsWith('}')) || (trimmed.startsWith('[') && trimmed.endsWith(']'))) {
    try { return JSON.stringify(JSON.parse(trimmed), null, 2) } catch (e) {}
  }

  // Socket.IO format, e.g. '42["message", {"key":"value"}]' — numeric prefix + JSON payload
  const match = trimmed.match(/^(\d+)(.*)/)
  if (match && match[2]) {
    const prefix = match[1]
    const possibleJson = match[2].trim()

    if ((possibleJson.startsWith('{') && possibleJson.endsWith('}')) || (possibleJson.startsWith('[') && possibleJson.endsWith(']'))) {
      try {
        const parsed = JSON.parse(possibleJson)
        return prefix + "\n" + JSON.stringify(parsed, null, 2)
      } catch (e) {}
    }
  }

  return content
}

const copyPayload = async (content, idx) => {
  try {
    const formatted = formatPayload(content)
    await navigator.clipboard.writeText(formatted)
    copiedIndex.value = idx
    setTimeout(() => { copiedIndex.value = null }, 2000)
  } catch (err) {
    console.error('Failed to copy text: ', err)
  }
}

// Lightweight JSON syntax highlighter (OneDark theme)
const syntaxHighlight = (jsonStr) => {
  // Escape HTML first to prevent injection via WS frame content rendered with v-html
  let safeJson = jsonStr.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

  return safeJson.replace(/("(\\u[a-zA-Z0-9]{4}|\\[^u]|[^\\"])*"(\s*:)?|\b(true|false|null)\b|-?\d+(?:\.\d*)?(?:[eE][+\-]?\d+)?)/g, (match) => {
    let cls = 'cm-number';
    if (/^"/.test(match)) {
      if (/:$/.test(match)) {
        cls = 'cm-key';
      } else {
        cls = 'cm-string';
      }
    } else if (/true|false/.test(match)) {
      cls = 'cm-boolean';
    } else if (/null/.test(match)) {
      cls = 'cm-null';
    }
    return `<span class="${cls}">${match}</span>`;
  });
}

const getHighlightedPayload = (content) => {
  const formattedText = formatPayload(content);

  if (formattedText.includes('\n') || formattedText.startsWith('{') || formattedText.startsWith('[')) {
    // Socket.IO frames: split the numeric prefix from the JSON so only the JSON gets highlighted
    const match = formattedText.match(/^(\d+)\n([\s\S]*)/);
    if (match) {
      return `<span class="cm-prefix">${match[1]}</span>\n${syntaxHighlight(match[2])}`;
    }
    return syntaxHighlight(formattedText);
  }

  return formattedText.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}
</script>

<template>
  <div class="ws-inspector">
    <div class="ws-header">
      <div class="header-title">
        <strong>WebSocket Frames</strong>
        <span class="badge">{{ filteredMessages.length }} / {{ baseMessages.length }}</span>
      </div>
      <input 
        type="text" 
        v-model="searchQuery" 
        class="ws-search" 
        placeholder="Search (use ! to exclude, e.g. !heartbeat)" 
      />
    </div>

    <div class="ws-messages" ref="scrollContainer" @scroll="handleScroll">
      <div v-if="filteredMessages.length === 0" class="empty-state">
        <span v-if="baseMessages.length > 0">All messages filtered out.</span>
        <span v-else>Waiting for WebSocket frames...</span>
      </div>

      <div 
        v-for="(msg, idx) in filteredMessages" 
        :key="idx"
        class="ws-frame"
        :class="msg.is_client ? 'client-frame' : 'server-frame'"
      >
        <div class="frame-meta">
          <span class="direction-icon">{{ msg.is_client ? '⬆️' : '⬇️' }}</span>
          <span class="meta-text">{{ msg.is_client ? 'Client Message' : 'Server Message' }}</span>
          <span class="meta-divider">•</span>
          <span class="meta-text">{{ formatTime(msg.time) }}</span>
          <span class="meta-divider">•</span>
          <span class="meta-text size">{{ formatBytes(msg.size) }}</span>
        </div>
        <div class="frame-payload-wrapper">
          <button class="copy-payload-btn" @click="copyPayload(msg.content, idx)">
            {{ copiedIndex === idx ? 'Copied!' : 'Copy' }}
          </button>
          <div class="frame-payload" v-html="getHighlightedPayload(msg.content)"></div>
        </div>
      </div>
    </div>

    <button 
      v-if="isAutoScrollPaused" 
      class="jump-bottom-btn" 
      @click="scrollToBottom"
    >
      ↓ More messages below
    </button>
  </div>
</template>

<style scoped>
.ws-inspector { 
  display: flex; 
  flex-direction: column; 
  height: 100%; 
  overflow: hidden; 
  background: var(--bg-main); 
  font-size: 12px; 
  position: relative; /* For the absolute jump button */
}

.ws-header {
  padding: 8px 12px; 
  border-bottom: 1px solid var(--border); 
  background: var(--bg-sidebar); 
  display: flex; 
  justify-content: space-between; 
  align-items: center; 
  color: var(--fg-secondary);
  gap: 12px;
}
.header-title {
  display: flex;
  align-items: center;
  gap: 8px;
  white-space: nowrap;
}
.badge { background: var(--border); padding: 2px 8px; border-radius: 12px; font-size: 10px; font-weight: bold; }

.ws-search {
  flex: 1;
  max-width: 300px;
  background: var(--bg-deepest);
  border: 1px solid var(--border);
  color: var(--fg-secondary);
  padding: 4px 10px;
  border-radius: 4px;
  font-size: 11px;
  font-family: 'Consolas', monospace;
  outline: none;
  transition: border-color 0.2s;
}
.ws-search:focus { border-color: var(--accent); }

.ws-messages { 
  flex: 1; 
  overflow-y: auto; 
  padding: 12px; 
  display: flex; 
  flex-direction: column; 
  gap: 8px; 
  min-height: 0; 
  padding-bottom: 40px; /* Space for the jump button */
}

.empty-state { color: var(--fg-muted); font-style: italic; text-align: center; margin-top: 20px; }

.ws-frame { border: 1px solid var(--border); border-radius: 6px; overflow: hidden; background: var(--bg-card); flex-shrink: 0; }
.frame-meta { padding: 4px 8px; border-bottom: 1px solid var(--border); display: flex; align-items: center; gap: 6px; font-size: 11px; }
.meta-divider { color: var(--fg-placeholder); }
.meta-text { color: var(--fg-muted); }
.meta-text.size { color: var(--fg-muted); font-family: monospace; }
.direction-icon { font-size: 10px; }

.client-frame { border-left: 3px solid var(--accent); } 
.client-frame .frame-meta { background: var(--accent-muted); }

.server-frame { border-left: 3px solid var(--success); } 
.server-frame .frame-meta { background: var(--success-muted); }

.frame-payload { 
  padding: 12px; 
  color: var(--fg-secondary); 
  font-family: 'Consolas', monospace; 
  white-space: pre-wrap; 
  word-break: break-all; 
  user-select: text; 
  -webkit-user-select: text;
  font-size: 11px;
  line-height: 1.4;
  text-align: left;
  margin: 0;
}
.jump-bottom-btn {
  position: absolute;
  bottom: 16px;
  left: 50%;
  transform: translateX(-50%);
  background-color: rgba(59,130,246,0.9);
  color: white;
  border: 1px solid var(--accent-hover);
  padding: 6px 16px;
  border-radius: 20px;
  font-size: 11px;
  font-weight: 600;
  cursor: pointer;
  box-shadow: var(--shadow-lg);
  backdrop-filter: blur(4px);
  z-index: 10;
  transition: all 0.2s ease;
}
.jump-bottom-btn:hover {
  background-color: var(--accent);
  transform: translateX(-50%) translateY(-2px);
}

/* Container for the payload so we can absolutely position the copy button */
.frame-payload-wrapper {
  position: relative;
  background: var(--bg-deepest);
  border-top: 1px solid var(--border-subtle);
}

.frame-payload {
  padding: 12px;
  color: var(--fg-secondary);
  font-family: 'Consolas', monospace;
  white-space: pre-wrap;
  word-break: break-all;
  user-select: text;
  -webkit-user-select: text;
  font-size: 11px;
  line-height: 1.4;
}

.copy-payload-btn {
  position: absolute;
  top: 6px;
  right: 6px;
  background: var(--bg-active);
  color: var(--fg-muted);
  border: 1px solid var(--border);
  padding: 4px 10px;
  border-radius: 4px;
  font-size: 10px;
  font-weight: bold;
  cursor: pointer;
  opacity: 0;
  transition: all 0.2s ease;
  z-index: 5;
}

.ws-frame:hover .copy-payload-btn {
  opacity: 1;
}

.copy-payload-btn:hover {
  background: var(--accent);
  color: white;
  border-color: var(--accent-hover);
}

:deep(.cm-key) {
  color: var(--syntax-red);
}
:deep(.cm-string) {
  color: var(--syntax-green);
}
:deep(.cm-number) {
  color: var(--syntax-orange);
}
:deep(.cm-boolean) {
  color: var(--syntax-cyan);
}
:deep(.cm-null) {
  color: var(--syntax-purple);
}
:deep(.cm-prefix) {
  color: var(--syntax-blue); /* Blue for the Socket.IO routing prefix */
  font-weight: bold;
}
</style>