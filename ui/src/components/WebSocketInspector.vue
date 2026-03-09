<script setup>
import { computed, ref, watch, nextTick } from 'vue'
import { selectedRequest, wsMessages } from '../store.js'

// Get the messages strictly for the currently selected request
const currentMessages = computed(() => {
  if (!selectedRequest.value) return []
  const reqId = String(selectedRequest.value.id)
  return wsMessages.value[reqId] || []
})

const formatTime = (unixTime) => {
  const d = new Date(unixTime * 1000)
  return d.toISOString().split('T')[1].substring(0, 12) // HH:MM:SS.mmm
}

const formatBytes = (bytes) => {
  if (bytes < 1024) return bytes + ' B'
  return (bytes / 1024).toFixed(1) + ' KB'
}

// Auto-scroll to the bottom when new messages arrive
const scrollContainer = ref(null)
watch(currentMessages, async () => {
  await nextTick()
  if (scrollContainer.value) {
    scrollContainer.value.scrollTop = scrollContainer.value.scrollHeight
  }
}, { deep: true })
</script>

<template>
  <div class="ws-inspector">
    <div class="ws-header">
      <strong>WebSocket Frames</strong>
      <span class="badge">{{ currentMessages.length }} Messages</span>
    </div>

    <div class="ws-messages" ref="scrollContainer">
      <div v-if="currentMessages.length === 0" class="empty-state">
        Waiting for WebSocket frames...
      </div>

      <div 
        v-for="(msg, idx) in currentMessages" 
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
        <div class="frame-payload">
          {{ msg.content }}
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* ADDED: overflow: hidden and min-height: 0 to trap the layout! */
.ws-inspector { 
  display: flex; 
  flex-direction: column; 
  height: 100%; 
  overflow: hidden; 
  background: var(--bg-main); 
  font-size: 12px; 
}

.ws-header { padding: 8px 12px; border-bottom: 1px solid var(--border); background: var(--bg-sidebar); display: flex; justify-content: space-between; align-items: center; color: #ccc; }
.badge { background: #333; padding: 2px 8px; border-radius: 12px; font-size: 10px; font-weight: bold; }

/* ADDED: min-height: 0 forces flexbox to actually use the scrollbar */
.ws-messages { 
  flex: 1; 
  overflow-y: auto; 
  padding: 12px; 
  display: flex; 
  flex-direction: column; 
  gap: 8px; 
  min-height: 0; 
}

.empty-state { color: #666; font-style: italic; text-align: center; margin-top: 20px; }

.ws-frame { border: 1px solid #333; border-radius: 6px; overflow: hidden; background: #1a1b1c; flex-shrink: 0; /* Ensures frames don't squish */ }
.frame-meta { padding: 4px 8px; border-bottom: 1px solid #333; display: flex; align-items: center; gap: 6px; font-size: 11px; }
.meta-divider { color: #555; }
.meta-text { color: #888; }
.meta-text.size { color: #aaa; font-family: monospace; }
.direction-icon { font-size: 10px; }

/* Differentiate Client (Up) vs Server (Down) */
.client-frame { border-left: 3px solid #3b82f6; } 
.client-frame .frame-meta { background: rgba(59, 130, 246, 0.1); }

.server-frame { border-left: 3px solid #10b981; } 
.server-frame .frame-meta { background: rgba(16, 185, 129, 0.1); }

.frame-payload { padding: 8px; color: #d4d4d4; font-family: monospace; white-space: pre-wrap; word-break: break-all; }
</style>