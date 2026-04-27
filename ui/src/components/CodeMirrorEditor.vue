<script setup>
import { ref, computed, watch, nextTick, onMounted, onUnmounted } from 'vue'
import { Codemirror } from 'vue-codemirror'
import {
  search, setSearchQuery, SearchQuery,
  findNext as cmFindNext, findPrevious as cmFindPrev,
  replaceNext as cmReplaceNext, replaceAll as cmReplaceAll,
} from '@codemirror/search'

const props = defineProps({
  modelValue: { type: String, default: '' },
  extensions: { type: Array, default: () => [] },
  readonly: { type: Boolean, default: false },
})

const emit = defineEmits(['update:modelValue', 'ready'])

// ── Editor instance ──────────────────────────────────────────────────────────
const editorView = ref(null)
const onReady = (payload) => {
  editorView.value = payload.view
  emit('ready', payload)
}

// ── Search / Replace state ────────────────────────────────────────────────────
const searchVisible = ref(false)
const replaceVisible = ref(false)
const searchQuery = ref('')
const replaceQuery = ref('')
const caseSensitive = ref(false)
const useRegex = ref(false)
const searchInputEl = ref(null)
const replaceInputEl = ref(null)
const matchCount = ref(0)

// Suppress CM's built-in search panel but keep the state field active
// so findNext / findPrevious / replaceNext / replaceAll work correctly.
const hiddenPanel = () => {
  const dom = document.createElement('div')
  dom.style.cssText = 'display:none;height:0;overflow:hidden;'
  return { dom, top: false }
}

const allExtensions = computed(() => [
  ...props.extensions,
  search({ createPanel: hiddenPanel }),
])

// ── Open / close ──────────────────────────────────────────────────────────────
const openSearch = () => {
  searchVisible.value = true
  nextTick(() => { searchInputEl.value?.focus(); searchInputEl.value?.select() })
}

const closeSearch = () => {
  searchVisible.value = false
  replaceVisible.value = false
  searchQuery.value = ''
  replaceQuery.value = ''
  if (editorView.value) {
    editorView.value.dispatch({ effects: setSearchQuery.of(new SearchQuery({ search: '' })) })
  }
  editorView.value?.focus()
}

const toggleSearch = () => searchVisible.value ? closeSearch() : openSearch()

const toggleReplace = () => {
  if (!searchVisible.value) openSearch()
  replaceVisible.value = !replaceVisible.value
  if (replaceVisible.value) nextTick(() => replaceInputEl.value?.focus())
}

// ── Sync query to CM ──────────────────────────────────────────────────────────
watch([searchQuery, replaceQuery, caseSensitive, useRegex], () => {
  if (!editorView.value) return
  if (!searchQuery.value) {
    editorView.value.dispatch({ effects: setSearchQuery.of(new SearchQuery({ search: '' })) })
    matchCount.value = 0
    return
  }
  const q = new SearchQuery({
    search: searchQuery.value,
    replace: replaceQuery.value,
    caseSensitive: caseSensitive.value,
    regexp: useRegex.value,
  })
  if (!q.valid) { matchCount.value = 0; return }
  editorView.value.dispatch({ effects: setSearchQuery.of(q) })
  // Count all matches
  let count = 0
  const cursor = q.getCursor(editorView.value.state.doc)
  while (!cursor.next().done) count++
  matchCount.value = count
})

// ── Navigate / Replace ────────────────────────────────────────────────────────
const findNext    = () => { if (editorView.value && searchQuery.value) cmFindNext(editorView.value) }
const findPrev    = () => { if (editorView.value && searchQuery.value) cmFindPrev(editorView.value) }
const replaceNext = () => { if (editorView.value && searchQuery.value) cmReplaceNext(editorView.value) }
const replaceAll  = () => { if (editorView.value && searchQuery.value) cmReplaceAll(editorView.value) }

const handleSearchKeydown = (e) => {
  if (e.key === 'Enter') { e.preventDefault(); e.shiftKey ? findPrev() : findNext() }
  else if (e.key === 'Escape') { e.preventDefault(); closeSearch() }
}
const handleReplaceKeydown = (e) => {
  if (e.key === 'Enter') { e.preventDefault(); replaceNext() }
  else if (e.key === 'Escape') { e.preventDefault(); closeSearch() }
}

// ── Keyboard shortcuts on the wrapper ────────────────────────────────────────
const wrapperRef = ref(null)
const handleWrapperKeydown = (e) => {
  const mod = e.metaKey || e.ctrlKey
  if (mod && e.key === 'f') { e.preventDefault(); e.stopPropagation(); openSearch() }
  if (mod && e.key === 'h' && !props.readonly) { e.preventDefault(); e.stopPropagation(); toggleReplace() }
}
onMounted(() => wrapperRef.value?.addEventListener('keydown', handleWrapperKeydown))
onUnmounted(() => wrapperRef.value?.removeEventListener('keydown', handleWrapperKeydown))

// ── Beautify ──────────────────────────────────────────────────────────────────
const beautifyDone = ref(false)
const beautify = () => {
  if (!props.modelValue) return
  let result
  try { result = JSON.stringify(JSON.parse(props.modelValue), null, 2) } catch { return }
  if (result === props.modelValue) return
  emit('update:modelValue', result)
  beautifyDone.value = true
  setTimeout(() => { beautifyDone.value = false }, 1400)
}
</script>

<template>
  <div ref="wrapperRef" class="cme-wrapper">

    <!-- ── Search / Replace panel ──────────────────────────────────── -->
    <Transition name="cme-slide">
      <div v-if="searchVisible" class="cme-panel" @click.stop>

        <!-- Row 1: Search -------------------------------------------------- -->
        <div class="cme-row">

          <!-- Toggle replace (chevron) -->
          <button
            v-if="!readonly"
            class="cme-expand-btn"
            :class="{ open: replaceVisible }"
            @click="replaceVisible = !replaceVisible"
            title="Toggle Replace (⌘H)"
          >
            <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round">
              <polyline points="9 18 15 12 9 6"/>
            </svg>
          </button>
          <div v-else class="cme-expand-spacer" />

          <!-- Input -->
          <div class="cme-input-wrap">
            <svg class="cme-field-icon" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="#4a5160" stroke-width="2" stroke-linecap="round">
              <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
            </svg>
            <input
              ref="searchInputEl"
              v-model="searchQuery"
              placeholder="Find…"
              class="cme-input"
              @keydown="handleSearchKeydown"
              spellcheck="false"
              autocorrect="off"
              autocapitalize="off"
            />
          </div>

          <!-- Match count -->
          <span class="cme-count" :class="{ zero: searchQuery && matchCount === 0 }">
            {{ searchQuery ? `${matchCount} match${matchCount !== 1 ? 'es' : ''}` : '' }}
          </span>

          <!-- Prev / Next -->
          <div class="cme-btn-group">
            <button class="cme-icon-btn" @click="findPrev" title="Previous (Shift+Enter)">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><polyline points="18 15 12 9 6 15"/></svg>
            </button>
            <button class="cme-icon-btn" @click="findNext" title="Next (Enter)">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><polyline points="6 9 12 15 18 9"/></svg>
            </button>
          </div>

          <div class="cme-sep" />

          <!-- Toggles -->
          <button class="cme-toggle" :class="{ active: caseSensitive }" @click="caseSensitive = !caseSensitive" title="Match Case">Aa</button>
          <button class="cme-toggle" :class="{ active: useRegex }" @click="useRegex = !useRegex" title="Use Regex">.*</button>

          <div class="cme-sep" />

          <!-- Close -->
          <button class="cme-icon-btn cme-close-btn" @click="closeSearch" title="Close (Esc)">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round">
              <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
            </svg>
          </button>

        </div>

        <!-- Row 2: Replace (only when toggled and not readonly) ------------- -->
        <div v-if="replaceVisible && !readonly" class="cme-row cme-replace-row">
          <div class="cme-expand-spacer" />

          <div class="cme-input-wrap">
            <svg class="cme-field-icon" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="#4a5160" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M17 10H3"/><path d="M21 6H3"/><path d="M21 14H3"/><path d="M17 18H3"/>
            </svg>
            <input
              ref="replaceInputEl"
              v-model="replaceQuery"
              placeholder="Replace with…"
              class="cme-input"
              @keydown="handleReplaceKeydown"
              spellcheck="false"
              autocorrect="off"
              autocapitalize="off"
            />
          </div>

          <div class="cme-btn-group">
            <button class="cme-text-btn" @click="replaceNext" title="Replace (Enter)">Replace</button>
            <button class="cme-text-btn" @click="replaceAll" title="Replace All">Replace All</button>
          </div>

        </div>

      </div>
    </Transition>

    <!-- ── Floating action buttons ────────────────────────────────── -->
    <div class="cme-actions">
      <button class="cme-action-btn" :class="{ active: searchVisible }" @click="toggleSearch" title="Find (⌘F)">
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
          <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
        </svg>
        Find
      </button>
      <button v-if="!readonly" class="cme-action-btn" :class="{ done: beautifyDone }" @click="beautify" title="Beautify JSON">
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/>
        </svg>
        {{ beautifyDone ? 'Done!' : 'Beautify' }}
      </button>
    </div>

    <!-- ── Editor ────────────────────────────────────────────────── -->
    <div class="cme-editor-host">
      <codemirror
        :model-value="modelValue"
        @update:model-value="emit('update:modelValue', $event)"
        :extensions="allExtensions"
        :style="{ height: '100%', width: '100%' }"
        @ready="onReady"
      />
    </div>

  </div>
</template>

<style scoped>
/* ── Wrapper ────────────────────────────────────────────── */
.cme-wrapper {
  position: relative;
  display: flex;
  flex-direction: column;
  height: 100%;
  width: 100%;
  overflow: hidden;
}

/* ── Editor host ────────────────────────────────────────── */
.cme-editor-host { flex: 1; min-height: 0; overflow: hidden; }
.cme-editor-host :deep(.cm-editor) { height: 100% !important; }

/* ── Panel container ────────────────────────────────────── */
.cme-panel {
  flex-shrink: 0;
  background: #131415;
  border-bottom: 1px solid #252729;
  z-index: 10;
}

/* ── Row ────────────────────────────────────────────────── */
.cme-row {
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 6px 10px;
}
.cme-replace-row { padding-top: 2px; padding-bottom: 8px; }

/* ── Expand / spacer ────────────────────────────────────── */
.cme-expand-btn {
  display: flex; align-items: center; justify-content: center;
  width: 20px; height: 20px; padding: 0;
  background: none; border: none; border-radius: 4px;
  color: #4a5160; cursor: pointer; flex-shrink: 0;
  transition: color 0.12s, background 0.12s;
}
.cme-expand-btn:hover { color: #aaa; background: rgba(255,255,255,0.06); }
.cme-expand-btn svg { transition: transform 0.15s ease; }
.cme-expand-btn.open svg { transform: rotate(90deg); }
.cme-expand-spacer { width: 20px; flex-shrink: 0; }

/* ── Input wrapper ──────────────────────────────────────── */
.cme-input-wrap {
  flex: 1; min-width: 0;
  position: relative; display: flex; align-items: center;
}
.cme-field-icon { position: absolute; left: 8px; pointer-events: none; flex-shrink: 0; }
.cme-input {
  width: 100%;
  background: #0d0e0f;
  border: 1px solid #252729;
  color: #d0d4d8;
  border-radius: 5px;
  padding: 0 8px 0 27px;
  height: 26px;
  font-size: 12px;
  font-family: 'Menlo', 'Consolas', monospace;
  outline: none;
  transition: border-color 0.15s, box-shadow 0.15s;
}
.cme-input:focus { border-color: #3b82f6; box-shadow: 0 0 0 2px rgba(59,130,246,0.12); }

/* ── Match count ────────────────────────────────────────── */
.cme-count {
  font-size: 11px; color: #4a5160;
  white-space: nowrap; flex-shrink: 0; min-width: 76px; text-align: right;
}
.cme-count.zero { color: #f87171; }

/* ── Separator ──────────────────────────────────────────── */
.cme-sep { width: 1px; height: 14px; background: #252729; flex-shrink: 0; margin: 0 1px; }

/* ── Button group ───────────────────────────────────────── */
.cme-btn-group { display: flex; align-items: center; gap: 1px; flex-shrink: 0; }

/* ── Icon-only buttons (↑ ↓ ✕) ─────────────────────────── */
.cme-icon-btn {
  display: flex; align-items: center; justify-content: center;
  width: 26px; height: 26px; padding: 0;
  background: none; border: 1px solid transparent; border-radius: 4px;
  color: #4a5160; cursor: pointer;
  transition: background 0.12s, color 0.12s, border-color 0.12s; flex-shrink: 0;
}
.cme-icon-btn:hover { background: rgba(255,255,255,0.07); color: #ccc; border-color: #2e3133; }
.cme-close-btn:hover { color: #f87171 !important; }

/* ── Toggle buttons (Aa, .*) ────────────────────────────── */
.cme-toggle {
  display: flex; align-items: center; justify-content: center;
  height: 26px; padding: 0 8px;
  background: none; border: 1px solid transparent; border-radius: 4px;
  color: #4a5160; cursor: pointer;
  font-family: inherit; font-size: 11px; font-weight: 700; letter-spacing: 0.02em;
  transition: background 0.12s, color 0.12s, border-color 0.12s; flex-shrink: 0;
}
.cme-toggle:hover { background: rgba(255,255,255,0.07); color: #aaa; border-color: #2e3133; }
.cme-toggle.active { background: rgba(59,130,246,0.15); color: #60a5fa; border-color: rgba(59,130,246,0.3); }

/* ── Text action buttons (Replace, Replace All) ─────────── */
.cme-text-btn {
  display: flex; align-items: center;
  height: 26px; padding: 0 12px;
  background: #1e2022; border: 1px solid #2e3133; border-radius: 4px;
  color: #9aa3ad; cursor: pointer;
  font-family: inherit; font-size: 11px; font-weight: 500;
  transition: background 0.12s, color 0.12s, border-color 0.12s; flex-shrink: 0;
}
.cme-text-btn:hover { background: #272b2e; color: #e5e7eb; border-color: #3d4144; }

/* ── Floating action buttons ────────────────────────────── */
.cme-actions {
  position: absolute; top: 7px; right: 10px; z-index: 5;
  display: flex; align-items: center; gap: 4px;
  opacity: 0; transition: opacity 0.15s; pointer-events: none;
}
.cme-wrapper:hover .cme-actions,
.cme-wrapper:focus-within .cme-actions { opacity: 1; pointer-events: auto; }

.cme-action-btn {
  display: flex; align-items: center; gap: 5px;
  height: 26px; padding: 0 10px;
  background: #1a1c1e; border: 1px solid #2e3133; border-radius: 6px;
  color: #8a9199; cursor: pointer;
  font-family: inherit; font-size: 11.5px; font-weight: 500;
  backdrop-filter: blur(6px);
  transition: background 0.12s, color 0.12s, border-color 0.12s;
  white-space: nowrap; box-shadow: 0 1px 4px rgba(0,0,0,0.4);
}
.cme-action-btn:hover { background: #232629; color: #e5e7eb; border-color: #3d4144; }
.cme-action-btn.active { background: rgba(59,130,246,0.14); color: #60a5fa; border-color: rgba(59,130,246,0.35); }
.cme-action-btn.done { background: rgba(52,211,153,0.12); color: #34d399; border-color: rgba(52,211,153,0.3); }

/* ── Slide transition ───────────────────────────────────── */
.cme-slide-enter-active,
.cme-slide-leave-active { transition: transform 0.14s ease, opacity 0.14s ease; }
.cme-slide-enter-from,
.cme-slide-leave-to { transform: translateY(-100%); opacity: 0; }
</style>
