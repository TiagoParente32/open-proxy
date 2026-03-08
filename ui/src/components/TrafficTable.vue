<script setup>
import { onMounted, onUnmounted } from 'vue'
import { 
  filteredRequests, selectedRequest, isFocusMode, pinnedSources, 
  formatUrl, contextMenu, searchQuery, 
  sortKey, sortOrder, toggleSort, formatTime, formatBytes 
} from '../store.js'

const getMethodColor = (method) => {
  const colors = { GET: '#3b82f6', POST: '#10b981', PUT: '#f59e0b', DELETE: '#ef4444', OPTIONS: '#8b5cf6' }
  return colors[method] || '#8b949e'
}

const openContextMenu = (e, req) => {
  selectedRequest.value = req; 
  contextMenu.value = { show: true, x: e.clientX, y: e.clientY, request: req }
}

const sortIcon = (key) => {
  if (sortKey.value !== key) return ''
  return sortOrder.value === 'asc' ? ' ↑' : ' ↓'
}

// NEW: Keyboard Navigation Logic
const handleKeyDown = (e) => {
  // Ignore keypresses if the user is typing in an input (like the search bar)
  if (['INPUT', 'TEXTAREA'].includes(document.activeElement.tagName)) return;

  if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
    e.preventDefault(); // Stop the whole page from scrolling

    if (filteredRequests.value.length === 0) return;

    // If nothing is selected, select the first one
    if (!selectedRequest.value) {
      selectedRequest.value = filteredRequests.value[0];
      return;
    }

    const currentIndex = filteredRequests.value.findIndex(r => r.id === selectedRequest.value.id);
    if (currentIndex === -1) return;

    if (e.key === 'ArrowDown' && currentIndex < filteredRequests.value.length - 1) {
      selectedRequest.value = filteredRequests.value[currentIndex + 1];
    } else if (e.key === 'ArrowUp' && currentIndex > 0) {
      selectedRequest.value = filteredRequests.value[currentIndex - 1];
    }
  }
}

onMounted(() => window.addEventListener('keydown', handleKeyDown))
onUnmounted(() => window.removeEventListener('keydown', handleKeyDown))
</script>

<template>
  <div class="traffic-layout">
    <div class="table-toolbar">
      <input type="text" v-model="searchQuery" placeholder="🔍 Filter URL, method, status..." class="table-search-input" />
    </div>

    <div class="table-container">
      <table class="traffic-table">
        <thead>
          <tr>
            <th><div class="resize-handle" style="width: 60px;" @click="toggleSort('id')">ID{{ sortIcon('id') }}</div></th>
            <th><div class="resize-handle" style="width: 85px;" @click="toggleSort('time')">Time{{ sortIcon('time') }}</div></th>
            <th><div class="resize-handle" style="width: 75px;" @click="toggleSort('method')">Method{{ sortIcon('method') }}</div></th>
            <th><div class="resize-handle" style="width: 65px;" @click="toggleSort('status')">Status{{ sortIcon('status') }}</div></th>
            <th><div class="resize-handle" style="width: 180px;" @click="toggleSort('url')">Host{{ sortIcon('url') }}</div></th>
            <th><div class="resize-handle" style="width: 250px;">Path</div></th>
            <th><div class="resize-handle" style="width: 90px;" @click="toggleSort('duration')">Time (ms){{ sortIcon('duration') }}</div></th>
            <th><div class="resize-handle" style="width: 85px;" @click="toggleSort('req_bytes')">Req Size{{ sortIcon('req_bytes') }}</div></th>
            <th><div class="resize-handle" style="width: 85px;" @click="toggleSort('res_bytes')">Res Size{{ sortIcon('res_bytes') }}</div></th>
            
            <th style="width: 100%;"></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="req in filteredRequests" :key="req.id" @click="selectedRequest = req" @contextmenu.prevent="openContextMenu($event, req)" :class="{ selected: selectedRequest?.id === req.id }">
            <td class="text-muted text-id">{{ req.id.substring(0, 5) }}</td>
            <td class="text-muted">{{ formatTime(req.time) }}</td>
            <td><span class="method-badge" :style="{ backgroundColor: getMethodColor(req.method) + '20', color: getMethodColor(req.method) }">{{ req.method }}</span></td>
            <td>
              <span v-if="req.status === '...'" class="text-muted">...</span>
              <span v-else class="status-badge" :class="{'text-green': req.status < 400, 'text-red': req.status >= 400}">{{ req.status }}</span>
            </td>
            <td class="font-semibold truncate">{{ formatUrl(req.url).host }}</td>
            <td class="text-muted truncate">{{ formatUrl(req.url).path }}</td>
            <td class="text-muted">{{ req.duration ? req.duration + ' ms' : '...' }}</td>
            <td class="text-muted">{{ formatBytes(req.req_bytes) }}</td>
            <td class="text-muted">{{ formatBytes(req.res_bytes) }}</td>
            
            <td></td>
          </tr>
        </tbody>
      </table>
      <div v-if="filteredRequests.length === 0" class="global-empty">
        <span v-if="isFocusMode && pinnedSources.length === 0">Add a Pinned Source to see traffic.</span>
        <span v-else>Waiting for traffic...</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.traffic-layout { display: flex; flex-direction: column; height: 100%; background: var(--bg-main); }

.table-toolbar { padding: 6px 12px; border-bottom: 1px solid var(--border); background: var(--bg-main); flex-shrink: 0; }
.table-search-input { width: 100%; background: #111; border: 1px solid #444; color: #ccc; padding: 6px 12px; border-radius: 6px; font-size: 12px; outline: none; transition: border-color 0.2s; box-sizing: border-box; }
.table-search-input:focus { border-color: #3b82f6; }

.table-container { flex: 1; overflow: auto; display: flex; flex-direction: column; }

/* The Table Layout Fixes */
.traffic-table { 
  width: max-content; /* Let the table grow beyond the screen if columns get huge */
  min-width: 100%;    /* But make sure it fills the screen by default */
  border-collapse: collapse; 
  table-layout: fixed; 
  font-size: 12px; 
}
.traffic-table th { 
  padding: 0; /* Remove padding from th so the resizable div can take up all the space */
  background-color: var(--bg-sidebar); 
  border-bottom: 1px solid var(--border); 
  position: sticky; 
  top: 0; 
  z-index: 1; 
  text-align: left;
}

/* The Resizable Inner Wrapper */
.resize-handle { 
  display: flex; 
  align-items: center;
  padding: 6px 10px; 
  color: #888; 
  font-weight: 500; 
  cursor: pointer; 
  resize: horizontal; 
  overflow: hidden; 
  box-sizing: border-box;
  transition: color 0.2s;
}
.resize-handle:hover { color: #ccc; }

.traffic-table td { 
  padding: 4px 10px; 
  border-bottom: 1px solid #282829; 
  white-space: nowrap; 
  text-align: left; 
  overflow: hidden; 
  text-overflow: ellipsis; 
  max-width: 0; /* <--- THE MAGIC FIX */
}

.traffic-table tbody tr:hover { background-color: var(--bg-active); cursor: pointer; }
.traffic-table tbody tr.selected { background-color: #1e3a5f; color: #fff; }

.text-id { font-family: monospace; font-size: 11px; }
.method-badge { padding: 2px 6px; border-radius: 4px; font-weight: 700; font-size: 10px; }
.status-badge { padding: 2px 6px; border-radius: 4px; background: #333; font-size: 10px; font-weight: bold; border: 1px solid #444; }
</style>