<script setup>
import { ref, computed, watch } from 'vue'
import { proxyIgnoreHosts, proxyAllowHosts, proxyHostFilterMode, syncProxyIgnoreHosts, setProxyHostFilterMode, exportHostFilter, importHostFilter } from '../store.js'

const props = defineProps({ show: Boolean })
const emit  = defineEmits(['close'])

const draftMode   = ref('ignore')
const draftIgnore = ref('')
const draftAllow  = ref('')

// Computed v-model — textarea always shows the active tab's list
const draft = computed({
  get: () => draftMode.value === 'ignore' ? draftIgnore.value : draftAllow.value,
  set: (val) => draftMode.value === 'ignore' ? (draftIgnore.value = val) : (draftAllow.value = val),
})

// Normalize: plain URLs/hostnames/wildcards → regex for mitmproxy
const normalizeEntry = (input) => {
  const s = input.trim()
  if (!s) return null
  if (/[\\()|+?[\]^${}]/.test(s)) return s   // already a regex — leave as-is
  // *.example.com → (.+\.)?example\.com
  if (s.startsWith('*.')) {
    const host = s.slice(2).replace(/^https?:\/\//i, '').split('/')[0].split(':')[0].trim()
    return '(.+\\.)?' + host.replace(/\./g, '\\.')
  }
  let host = s.replace(/^https?:\/\//i, '').replace(/^\/\//, '')
  host = host.split('/')[0].split('?')[0].split('#')[0].split(':')[0].trim()
  if (!host) return null
  return host.replace(/\./g, '\\.')
}

// Prettify: convert stored regex back to user-friendly display
const prettifyPattern = (pattern) => {
  // (.+\.)?example\.com → *.example.com
  if (pattern.startsWith('(.+\\.)?')) {
    const rest      = pattern.slice('(.+\\.)?'.length)
    const unescaped = rest.replace(/\\\./g, '.')
    if (!/[\\()|+?[\]^${}*]/.test(unescaped)) return '*.' + unescaped
  }
  // api\.example\.com → api.example.com
  const unescaped = pattern.replace(/\\\./g, '.')
  if (!/[\\()|+?[\]^${}*]/.test(unescaped)) return unescaped
  return pattern
}

const PRESETS = [
  { label: 'Google APIs',        value: '*.googleapis.com' },
  { label: 'Google Play Store',  value: '*.play.google.com' },
  { label: 'Apple Push (APNS)',  value: '*.push.apple.com' },
  { label: 'Firebase',           value: '*.firebaseio.com' },
  { label: 'Crashlytics',        value: '*.crashlytics.com' },
  { label: 'Apple CDN',          value: '*.apple.com' },
]

// Load both lists (prettified) when modal opens
watch(() => props.show, (open) => {
  if (open) {
    draftIgnore.value = proxyIgnoreHosts.value.map(prettifyPattern).join('\n')
    draftAllow.value  = proxyAllowHosts.value.map(prettifyPattern).join('\n')
    draftMode.value   = proxyHostFilterMode.value
  }
})

// Auto-save each list independently (debounced)
let _timerIgnore = null, _timerAllow = null
watch(draftIgnore, () => {
  clearTimeout(_timerIgnore)
  _timerIgnore = setTimeout(() => {
    syncProxyIgnoreHosts(draftIgnore.value.split('\n').map(normalizeEntry).filter(Boolean), 'ignore')
  }, 500)
})
watch(draftAllow, () => {
  clearTimeout(_timerAllow)
  _timerAllow = setTimeout(() => {
    syncProxyIgnoreHosts(draftAllow.value.split('\n').map(normalizeEntry).filter(Boolean), 'allow')
  }, 500)
})

// Mode tab switch: update active mode immediately (no list data change)
watch(draftMode, (mode) => setProxyHostFilterMode(mode))

const addPreset = (value) => {
  const lines = draft.value.split('\n').map(l => l.trim()).filter(Boolean)
  if (!lines.includes(value)) lines.push(value)
  draft.value = lines.join('\n')
}

const clear = () => { draft.value = '' }

const importFilter = async () => {
  await importHostFilter()
  // Reload drafts to reflect the newly imported data
  draftIgnore.value = proxyIgnoreHosts.value.map(prettifyPattern).join('\n')
  draftAllow.value  = proxyAllowHosts.value.map(prettifyPattern).join('\n')
  draftMode.value   = proxyHostFilterMode.value
}
</script>

<template>
  <Teleport to="body">
    <Transition name="modal-fade">
      <div v-if="show" class="ih-overlay" @mousedown.self="emit('close')">
        <div class="ih-modal">

          <div class="ih-header">
            <button class="ih-close" @click="emit('close')">
              <svg width="12" height="12" viewBox="0 0 14 14" fill="none"><path d="M1 1l12 12M13 1L1 13" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>
            </button>
          </div>

          <div class="ih-body">
            <!-- Mode selection: explicit "pick one" radio cards, not a subtle tab switcher -->
            <div class="ih-mode-select-label">Filter Mode — choose one</div>
            <div class="ih-mode-select">
              <button
                class="ih-mode-card"
                :class="{ active: draftMode === 'allow' }"
                @click="draftMode = 'allow'"
              >
                <span class="ih-mode-radio"><span class="ih-mode-radio-dot" /></span>
                <span class="ih-mode-icon">
                  <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>
                </span>
                <span class="ih-mode-text">
                  <span class="ih-mode-title">Allow Mode</span>
                  <span class="ih-mode-sub"><strong>Only</strong> the hosts listed below are intercepted</span>
                </span>
              </button>
              <button
                class="ih-mode-card"
                :class="{ active: draftMode === 'ignore' }"
                @click="draftMode = 'ignore'"
              >
                <span class="ih-mode-radio"><span class="ih-mode-radio-dot" /></span>
                <span class="ih-mode-icon">
                  <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="4.93" y1="4.93" x2="19.07" y2="19.07"/></svg>
                </span>
                <span class="ih-mode-text">
                  <span class="ih-mode-title">Ignore Mode</span>
                  <span class="ih-mode-sub">Intercept everything <strong>except</strong> the hosts listed below</span>
                </span>
              </button>
            </div>

            <p class="ih-desc" v-if="draftMode === 'ignore'">
              Everything is intercepted <strong>except</strong> hosts matching these patterns. Use this to let specific apps through untouched (cert pinning, proprietary protocols, etc.).
            </p>
            <p class="ih-desc" v-else>
              <strong>Only</strong> hosts matching these patterns are intercepted — all other traffic passes through silently. Great for focusing on one app while everything else works normally.
            </p>

            <div class="ih-presets-label">Quick add</div>
            <div class="ih-presets">
              <button v-for="p in PRESETS" :key="p.value" class="ih-preset-btn" @click="addPreset(p.value)">
                + {{ p.label }}
              </button>
            </div>

            <div class="ih-editor-label">Patterns</div>
            <textarea
              v-model="draft"
              class="ih-textarea"
              placeholder="api.example.com&#10;https://app.myservice.com&#10;(.+\.)?googleapis\.com"
              spellcheck="false"
            />
            <p class="ih-hint">Enter hostnames, URLs, or use <code>*.example.com</code> to match all subdomains.</p>
          </div>

          <div class="ih-footer">
            <button class="ih-btn-clear" @click="clear">Clear all</button>
            <div style="flex:1"/>
            <button class="ih-btn-secondary" @click="exportHostFilter">Export</button>
            <button class="ih-btn-secondary" @click="importFilter">Import</button>
            <button class="ih-btn-save" @click="emit('close')">Done</button>
          </div>

        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.ih-overlay {
  position: fixed; inset: 0; z-index: 9999;
  background: var(--overlay, rgba(0,0,0,0.55));
  display: flex; align-items: center; justify-content: center;
}
.ih-modal {
  background: var(--bg-card); border: 1px solid var(--border);
  border-radius: 10px; box-shadow: var(--shadow-lg);
  width: 520px; max-width: 95vw; display: flex; flex-direction: column;
  max-height: 80vh;
}
.ih-header {
  display: flex; align-items: center; justify-content: flex-end;
  padding: 10px 14px 8px; border-bottom: 1px solid var(--border);
}
.ih-close {
  background: none; border: none; color: var(--fg-muted);
  cursor: pointer; padding: 4px; border-radius: 4px; display: flex;
  transition: color 0.15s;
}
.ih-close:hover { color: var(--fg-primary); }

.ih-body { padding: 16px 18px; overflow-y: auto; display: flex; flex-direction: column; gap: 12px; }

.ih-mode-select-label {
  font-size: 10px; font-weight: 600; color: var(--fg-muted);
  text-transform: uppercase; letter-spacing: 0.06em;
}
.ih-mode-select { display: flex; gap: 10px; }
.ih-mode-card {
  flex: 1; display: flex; align-items: flex-start; gap: 10px;
  text-align: left; padding: 12px; border-radius: 10px;
  background: var(--bg-deepest); border: 1.5px solid var(--border);
  cursor: pointer; transition: all 0.15s;
}
.ih-mode-card:hover { border-color: var(--fg-placeholder); }
.ih-mode-card.active {
  background: var(--accent-muted); border-color: var(--accent);
}
.ih-mode-radio {
  width: 16px; height: 16px; border-radius: 50%; flex-shrink: 0; margin-top: 1px;
  border: 1.5px solid var(--fg-placeholder); background: var(--bg-card);
  display: flex; align-items: center; justify-content: center;
  transition: all 0.15s;
}
.ih-mode-radio-dot { width: 8px; height: 8px; border-radius: 50%; background: transparent; transition: background 0.15s; }
.ih-mode-card.active .ih-mode-radio { border-color: var(--accent); background: var(--bg-card); }
.ih-mode-card.active .ih-mode-radio-dot { background: var(--accent); }
.ih-mode-icon {
  display: flex; align-items: center; justify-content: center;
  width: 26px; height: 26px; border-radius: 7px; flex-shrink: 0; margin-top: 1px;
  color: var(--fg-muted); background: var(--bg-card); border: 1px solid var(--border);
  transition: all 0.15s;
}
.ih-mode-card.active .ih-mode-icon {
  color: var(--accent); background: var(--accent-muted); border-color: var(--accent-border);
}
.ih-mode-text { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.ih-mode-title { font-size: 12.5px; font-weight: 700; color: var(--fg-primary); }
.ih-mode-card.active .ih-mode-title { color: var(--accent); }
.ih-mode-sub { font-size: 11px; color: var(--fg-muted); line-height: 1.4; }
.ih-mode-sub strong { color: var(--fg-secondary); }
.ih-desc { font-size: 12px; color: var(--fg-muted); line-height: 1.55; margin: 0; }
.ih-desc strong { color: var(--fg-secondary); }

.ih-presets-label, .ih-editor-label {
  font-size: 10px; font-weight: 600; color: var(--fg-muted);
  text-transform: uppercase; letter-spacing: 0.06em;
}
.ih-presets { display: flex; flex-wrap: wrap; gap: 6px; }
.ih-preset-btn {
  font-size: 11px; padding: 4px 10px; border-radius: 5px;
  background: var(--bg-deepest); border: 1px solid var(--border);
  color: var(--fg-secondary); cursor: pointer; transition: all 0.15s;
}
.ih-preset-btn:hover { border-color: var(--accent); color: var(--accent); background: var(--accent-muted); }

.ih-textarea {
  width: 100%; min-height: 140px; resize: vertical;
  background: var(--bg-deepest); border: 1px solid var(--border);
  color: var(--fg-secondary); border-radius: 6px; padding: 10px 12px;
  font-family: 'Consolas', 'Monaco', monospace; font-size: 12px; line-height: 1.6;
  outline: none; box-sizing: border-box; transition: border-color 0.15s;
}
.ih-textarea:focus { border-color: var(--accent); }
.ih-hint { font-size: 11px; color: var(--fg-muted); margin: 0; }
.ih-hint code {
  background: var(--bg-deepest); border: 1px solid var(--border);
  padding: 1px 5px; border-radius: 3px; font-size: 10px;
}

.ih-footer {
  display: flex; align-items: center; gap: 8px;
  padding: 12px 18px; border-top: 1px solid var(--border);
}
.ih-btn-clear {
  font-size: 12px; background: none; border: none;
  color: var(--fg-muted); cursor: pointer; padding: 6px 8px; border-radius: 5px;
  transition: color 0.15s;
}
.ih-btn-clear:hover { color: var(--error); }
.ih-btn-secondary {
  font-size: 12px; font-weight: 600; background: var(--surface-hover-strong); border: none;
  color: var(--fg-secondary); padding: 6px 16px; border-radius: 6px; cursor: pointer;
  transition: background 0.15s;
}
.ih-btn-secondary:hover { background: var(--border); }
.ih-btn-save {
  font-size: 12px; background: var(--accent); border: none;
  color: #fff; padding: 6px 22px; border-radius: 6px; cursor: pointer;
  font-weight: 600; transition: background 0.15s;
}
.ih-btn-save:hover { background: var(--accent-hover); }

.modal-fade-enter-active, .modal-fade-leave-active { transition: opacity 0.18s; }
.modal-fade-enter-from, .modal-fade-leave-to { opacity: 0; }
</style>
