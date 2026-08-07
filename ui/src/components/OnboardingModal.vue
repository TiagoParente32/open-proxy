<script setup>
import { ref, computed, watch } from 'vue'
import { syncProxyIgnoreHosts, sortOrder, disableCache, proxyHostFilterMode, proxyIgnoreHosts, proxyAllowHosts } from '../store.js'
import { themes, applyTheme, currentThemeId } from '../composables/useTheme.js'

const props = defineProps({ appVersion: String, prefill: Boolean })
const emit = defineEmits(['done'])

const TOTAL_STEPS = 4
const step = ref(1)

// Step 1 – theme
const selectedTheme = ref(currentThemeId.value)
const pickTheme = (id) => { selectedTheme.value = id; applyTheme(id) }

// Step 2 – intercept mode
const selected = ref(props.prefill ? proxyHostFilterMode.value : null)

// Step 3 – add hosts (Selective Interception only — "Intercept Everything" skips this step,
// but the underlying ignore-list draft still tracks any existing exclusions so finishing
// onboarding without touching this step doesn't silently wipe them out).
const draft = ref(props.prefill
  ? (proxyHostFilterMode.value === 'allow' ? proxyAllowHosts.value : proxyIgnoreHosts.value).join('\n')
  : '')
// Keep the draft in sync with whichever host list belongs to the newly chosen
// mode, so switching between modes on step 2 never mixes up or silently
// discards previously-saved hosts.
watch(selected, (mode) => {
  if (!props.prefill) { draft.value = ''; return }
  draft.value = (mode === 'allow' ? proxyAllowHosts.value : proxyIgnoreHosts.value).join('\n')
})
const normalizeEntry = (input) => {
  const s = input.trim()
  if (!s) return null
  if (/[\\()|+?[\]^${}]/.test(s)) return s
  if (s.startsWith('*.')) {
    const host = s.slice(2).replace(/^https?:\/\//i, '').split('/')[0].split(':')[0].trim()
    return '(.+\\.)?' + host.replace(/\./g, '\\.')
  }
  let host = s.replace(/^https?:\/\//i, '').replace(/^\/\//, '')
  host = host.split('/')[0].split('?')[0].split('#')[0].split(':')[0].trim()
  if (!host) return null
  return host.replace(/\./g, '\\.')
}
const PRESETS = [
  { label: 'Google APIs',       value: '*.googleapis.com' },
  { label: 'Google Play Store', value: '*.play.google.com' },
  { label: 'Firebase',          value: '*.firebaseio.com' },
  { label: 'Apple Push (APNS)', value: '*.push.apple.com' },
  { label: 'Crashlytics',       value: '*.crashlytics.com' },
]
const addPreset = (value) => {
  const lines = draft.value.split('\n').map(l => l.trim()).filter(Boolean)
  if (!lines.includes(value)) lines.push(value)
  draft.value = lines.join('\n')
}
const draftHosts = computed(() => draft.value.split('\n').map(l => l.trim()).filter(Boolean))
// Selective Interception only intercepts listed hosts, so it needs at least
// one — otherwise nothing would ever be intercepted, which isn't a state a
// user would knowingly want to finish onboarding in.
const needsHost = computed(() => selected.value === 'allow' && draftHosts.value.length === 0)

// Step 4 – quick settings
const selectedSortOrder = ref(props.prefill ? sortOrder.value : 'desc')
const enableNoCache = ref(props.prefill ? disableCache.value : false)

// Navigation
const canProceed = computed(() => {
  if (step.value === 2) return selected.value !== null
  if (step.value === 3) return !needsHost.value
  return true
})
// "Intercept Everything" has nothing to configure on step 3 (no hosts
// required), so jump straight from step 2 to step 4 for that mode.
const goNext = () => {
  if (!canProceed.value) return
  if (step.value === 2 && selected.value === 'ignore') { step.value = 4; return }
  if (step.value < TOTAL_STEPS) step.value++
}
const goBack = () => {
  if (step.value === 4 && selected.value === 'ignore') { step.value = 2; return }
  if (step.value > 1) step.value--
}

const finish = () => {
  sortOrder.value = selectedSortOrder.value
  disableCache.value = enableNoCache.value
  const raw   = draft.value.split('\n').map(l => l.trim()).filter(Boolean)
  const hosts = raw.map(normalizeEntry).filter(Boolean)
  syncProxyIgnoreHosts(hosts, selected.value || 'ignore')
  localStorage.setItem('openproxyOnboardingVersion', props.appVersion)
  localStorage.setItem('openproxyOnboardingDone', '1')
  emit('done')
}
</script>

<template>
  <Teleport to="body">
    <div class="ob-overlay">
      <div class="ob-modal">

        <!-- Step indicator -->
        <div class="ob-steps">
          <div class="ob-step" :class="{ active: step === 1, done: step > 1 }">{{ step > 1 ? '✓' : '1' }}</div>
          <div class="ob-step-line" :class="{ done: step > 1 }"></div>
          <div class="ob-step" :class="{ active: step === 2, done: step > 2 }">{{ step > 2 ? '✓' : '2' }}</div>
          <div class="ob-step-line" :class="{ done: step > 2 }"></div>
          <div class="ob-step" :class="{ active: step === 3, done: step > 3 }">{{ step > 3 ? '✓' : '3' }}</div>
          <div class="ob-step-line" :class="{ done: step > 3 }"></div>
          <div class="ob-step" :class="{ active: step === 4 }">4</div>
        </div>

        <!-- ── STEP 1: Choose theme ── -->
        <template v-if="step === 1">
          <img src="/icon.png" alt="OpenProxy" class="ob-icon" />
          <h1 class="ob-title">Welcome to OpenProxy</h1>
          <p class="ob-subtitle">Start by picking a theme. You can always change it later.</p>

          <div class="ob-theme-grid">
            <div
              v-for="theme in themes"
              :key="theme.id"
              class="ob-theme-card"
              :class="{ selected: selectedTheme === theme.id }"
              @click="pickTheme(theme.id)"
            >
              <div class="ob-theme-swatches">
                <span class="ob-swatch" :style="{ background: theme.preview.bg }"></span>
                <span class="ob-swatch" :style="{ background: theme.preview.sidebar }"></span>
                <span class="ob-swatch ob-swatch--accent" :style="{ background: theme.preview.accent }"></span>
              </div>
              <span class="ob-theme-name">{{ theme.name }}</span>
              <div v-if="selectedTheme === theme.id" class="ob-card-check">✓</div>
            </div>
          </div>

          <button class="ob-btn" @click="goNext">Next →</button>
        </template>

        <!-- ── STEP 2: Intercept mode ── -->
        <template v-else-if="step === 2">
          <p class="ob-subtitle" style="margin-top:4px">How would you like to intercept traffic?</p>

          <div class="ob-cards">
            <div class="ob-card" :class="{ selected: selected === 'ignore' }" @click="selected = 'ignore'">
              <div class="ob-card-icon">🌐</div>
              <div class="ob-card-title">Intercept Everything</div>
              <div class="ob-card-desc">All traffic goes through the proxy. Apps that don't trust the certificate may fail to connect.</div>
              <ul class="ob-card-pros">
                <li>✓ See all requests from all apps</li>
                <li>✓ Best for full traffic inspection</li>
                <li>⚠ Some apps may break</li>
              </ul>
              <div v-if="selected === 'ignore'" class="ob-card-check">✓</div>
            </div>

            <div class="ob-card" :class="{ selected: selected === 'allow' }" @click="selected = 'allow'">
              <div class="ob-card-icon">🎯</div>
              <div class="ob-card-title">Selective Interception</div>
              <div class="ob-card-desc">Only hosts you add are intercepted. Everything else passes through untouched.</div>
              <ul class="ob-card-pros">
                <li>✓ Other apps keep working normally</li>
                <li>✓ Best for debugging specific apps</li>
                <li>✓ No global cert trust needed</li>
              </ul>
              <div v-if="selected === 'allow'" class="ob-card-check">✓</div>
            </div>
          </div>

          <p class="ob-note">You can change this any time from <strong>Proxy → Host Filtering…</strong> in the menu.</p>

          <div class="ob-footer">
            <button class="ob-btn-back" @click="goBack">← Back</button>
            <div style="flex:1"/>
            <button class="ob-btn" :disabled="!canProceed" @click="goNext">Next →</button>
          </div>
        </template>

        <!-- ── STEP 3: Add hosts (Selective Interception only) ── -->
        <template v-else-if="step === 3">
          <div class="ob-step2-header">
            <h2 class="ob-title" style="font-size:18px">Add hosts to intercept</h2>
            <p class="ob-subtitle">Only these hosts will be intercepted. Add the apps you want to debug.</p>
          </div>

          <div class="ob-presets-label">Quick add</div>
          <div class="ob-presets">
            <button v-for="p in PRESETS" :key="p.value" class="ob-preset-btn" @click="addPreset(p.value)">
              + {{ p.label }}
            </button>
          </div>

          <textarea
            v-model="draft"
            class="ob-textarea"
            placeholder="api.example.com&#10;https://app.myservice.com&#10;*.mycompany.com"
            spellcheck="false"
          />
          <p class="ob-hint">
            Enter hostnames, URLs, or use <code>*.example.com</code> to match all subdomains.
          </p>
          <p v-if="needsHost" class="ob-hint ob-hint-warn">
            Add at least one host — Selective Interception only intercepts hosts you list here.
          </p>

          <div class="ob-footer">
            <button class="ob-btn-back" @click="goBack">← Back</button>
            <div style="flex:1"/>
            <button class="ob-btn" :disabled="needsHost" @click="goNext">Next →</button>
          </div>
        </template>

        <!-- ── STEP 4: Quick settings ── -->
        <template v-else>
          <h2 class="ob-title" style="font-size:18px">Quick settings</h2>
          <p class="ob-subtitle">Set your defaults — all of these can be changed later from the toolbar.</p>

          <!-- Sort order -->
          <div class="ob-setting-section">
            <div class="ob-setting-label">Request order</div>
            <div class="ob-cards" style="gap:10px">
              <div
                class="ob-card ob-card--sm"
                :class="{ selected: selectedSortOrder === 'desc' }"
                @click="selectedSortOrder = 'desc'"
              >
                <div class="ob-card-icon" style="font-size:18px">🆕</div>
                <div class="ob-card-title">Newest First</div>
                <div class="ob-card-desc">Latest requests appear at the top.</div>
                <div v-if="selectedSortOrder === 'desc'" class="ob-card-check">✓</div>
              </div>
              <div
                class="ob-card ob-card--sm"
                :class="{ selected: selectedSortOrder === 'asc' }"
                @click="selectedSortOrder = 'asc'"
              >
                <div class="ob-card-icon" style="font-size:18px">📜</div>
                <div class="ob-card-title">Oldest First</div>
                <div class="ob-card-desc">Requests build up from the top down.</div>
                <div v-if="selectedSortOrder === 'asc'" class="ob-card-check">✓</div>
              </div>
            </div>
          </div>

          <!-- No Cache toggle -->
          <div class="ob-setting-section">
            <div class="ob-setting-label">No Cache</div>
            <div
              class="ob-toggle-row"
              :class="{ active: enableNoCache }"
              @click="enableNoCache = !enableNoCache"
            >
              <div class="ob-toggle-text">
                <div class="ob-toggle-title">Disable caching</div>
                <div class="ob-toggle-desc">Forces every request to bypass the browser and server cache. Useful for always seeing the latest responses during testing.</div>
              </div>
              <div class="ob-switch" :class="{ on: enableNoCache }">
                <div class="ob-switch-thumb"></div>
              </div>
            </div>
          </div>

          <div class="ob-footer">
            <button class="ob-btn-back" @click="goBack">← Back</button>
            <div style="flex:1"/>
            <button class="ob-btn" @click="finish">Get Started</button>
          </div>
        </template>

      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.ob-overlay {
  position: fixed; inset: 0; z-index: 10000;
  background: rgba(0,0,0,0.7);
  display: flex; align-items: center; justify-content: center;
}
.ob-modal {
  background: var(--bg-card); border: 1px solid var(--border);
  border-radius: 14px; box-shadow: 0 24px 64px rgba(0,0,0,0.4);
  width: 580px; max-width: 95vw; padding: 28px 28px 24px;
  display: flex; flex-direction: column; align-items: center; gap: 14px;
  max-height: 95vh; overflow-y: auto;
}

/* Step indicator */
.ob-steps { display: flex; align-items: center; gap: 0; margin-bottom: 4px; }
.ob-step {
  width: 28px; height: 28px; border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  font-size: 11px; font-weight: 700;
  background: var(--bg-deepest); border: 2px solid var(--border);
  color: var(--fg-muted); transition: all 0.2s;
}
.ob-step.active { background: var(--accent); border-color: var(--accent); color: #fff; }
.ob-step.done   { background: var(--accent); border-color: var(--accent); color: #fff; opacity: 0.5; }
.ob-step-line { width: 32px; height: 2px; background: var(--border); transition: background 0.2s; }
.ob-step-line.done { background: var(--accent); opacity: 0.5; }

.ob-icon { width: 56px; height: 56px; border-radius: 14px; margin-bottom: 4px; }
.ob-title { font-size: 20px; font-weight: 700; color: var(--fg-primary); margin: 0; text-align: center; }
.ob-subtitle { font-size: 13px; color: var(--fg-muted); margin: 0; text-align: center; line-height: 1.5; }

/* Theme grid */
.ob-theme-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; width: 100%; }
.ob-theme-card {
  position: relative; cursor: pointer;
  background: var(--bg-deepest); border: 2px solid var(--border);
  border-radius: 10px; padding: 12px 12px 10px;
  display: flex; flex-direction: column; align-items: flex-start; gap: 8px;
  transition: border-color 0.15s, box-shadow 0.15s;
}
.ob-theme-card:hover { border-color: var(--accent); }
.ob-theme-card.selected { border-color: var(--accent); box-shadow: 0 0 0 3px rgba(88,166,255,0.15); }
.ob-theme-swatches { display: flex; gap: 4px; }
.ob-swatch {
  width: 16px; height: 16px; border-radius: 50%;
  border: 1px solid var(--border); flex-shrink: 0;
}
.ob-swatch--accent { border-radius: 4px; }
.ob-theme-name { font-size: 12px; font-weight: 600; color: var(--fg-primary); }

/* Intercept mode cards */
.ob-cards { display: flex; gap: 14px; width: 100%; }
.ob-card {
  flex: 1; background: var(--bg-deepest); border: 2px solid var(--border);
  border-radius: 10px; padding: 16px 14px; cursor: pointer; position: relative;
  transition: border-color 0.15s, box-shadow 0.15s;
  display: flex; flex-direction: column; gap: 8px;
}
.ob-card:hover { border-color: var(--accent); }
.ob-card.selected { border-color: var(--accent); box-shadow: 0 0 0 3px rgba(88,166,255,0.15); }
.ob-card--sm { padding: 12px 12px; }
.ob-card--sm .ob-card-desc { font-size: 11px; }
.ob-card-icon { font-size: 24px; }
.ob-card-title { font-size: 13px; font-weight: 600; color: var(--fg-primary); }
.ob-card-desc { font-size: 11.5px; color: var(--fg-muted); line-height: 1.5; }
.ob-card-pros { list-style: none; margin: 4px 0 0; padding: 0; display: flex; flex-direction: column; gap: 4px; }
.ob-card-pros li { font-size: 11px; color: var(--fg-secondary); }
.ob-card-check { position: absolute; top: 10px; right: 12px; color: var(--accent); font-weight: 700; font-size: 15px; }

.ob-note { font-size: 12px; color: var(--fg-muted); text-align: center; margin: 0; }
.ob-note strong { color: var(--fg-secondary); }

/* Step 3 – hosts */
.ob-step2-header { width: 100%; text-align: center; }
.ob-presets-label {
  width: 100%; font-size: 10px; font-weight: 600; color: var(--fg-muted);
  text-transform: uppercase; letter-spacing: 0.06em;
}
.ob-presets { display: flex; flex-wrap: wrap; gap: 6px; width: 100%; }
.ob-preset-btn {
  font-size: 11px; padding: 4px 10px; border-radius: 5px;
  background: var(--bg-deepest); border: 1px solid var(--border);
  color: var(--fg-secondary); cursor: pointer; transition: all 0.15s;
}
.ob-preset-btn:hover { border-color: var(--accent); color: var(--accent); }
.ob-textarea {
  width: 100%; min-height: 100px; resize: vertical;
  background: var(--bg-deepest); border: 1px solid var(--border);
  color: var(--fg-secondary); border-radius: 6px; padding: 10px 12px;
  font-family: 'Consolas', 'Monaco', monospace; font-size: 12px; line-height: 1.6;
  outline: none; box-sizing: border-box; transition: border-color 0.15s;
}
.ob-textarea:focus { border-color: var(--accent); }
.ob-hint { font-size: 11px; color: var(--fg-muted); margin: 0; width: 100%; }
.ob-hint-warn { color: var(--warning, #d29922); margin-top: -4px; }
.ob-hint code {
  background: var(--bg-deepest); border: 1px solid var(--border);
  padding: 1px 5px; border-radius: 3px; font-size: 10px;
}

/* Step 4 – quick settings */
.ob-setting-section { width: 100%; display: flex; flex-direction: column; gap: 8px; }
.ob-setting-label {
  font-size: 10px; font-weight: 600; color: var(--fg-muted);
  text-transform: uppercase; letter-spacing: 0.06em;
}
.ob-toggle-row {
  display: flex; align-items: center; gap: 14px;
  background: var(--bg-deepest); border: 2px solid var(--border);
  border-radius: 10px; padding: 14px 16px; cursor: pointer;
  transition: border-color 0.15s, box-shadow 0.15s;
}
.ob-toggle-row:hover { border-color: var(--accent); }
.ob-toggle-row.active { border-color: var(--accent); box-shadow: 0 0 0 3px rgba(88,166,255,0.15); }
.ob-toggle-text { flex: 1; }
.ob-toggle-title { font-size: 13px; font-weight: 600; color: var(--fg-primary); margin-bottom: 4px; }
.ob-toggle-desc { font-size: 11.5px; color: var(--fg-muted); line-height: 1.5; }
.ob-switch {
  width: 36px; height: 20px; border-radius: 10px; flex-shrink: 0;
  background: var(--border); position: relative; transition: background 0.2s;
}
.ob-switch.on { background: var(--accent); }
.ob-switch-thumb {
  position: absolute; top: 3px; left: 3px;
  width: 14px; height: 14px; border-radius: 50%;
  background: #fff; transition: transform 0.2s;
  box-shadow: 0 1px 3px rgba(0,0,0,0.3);
}
.ob-switch.on .ob-switch-thumb { transform: translateX(16px); }

/* Footer / navigation */
.ob-footer { display: flex; align-items: center; gap: 8px; width: 100%; margin-top: 4px; }
.ob-btn-back {
  font-size: 12px; background: transparent; border: 1px solid var(--border);
  color: var(--fg-muted); padding: 8px 14px; border-radius: 6px; cursor: pointer; transition: all 0.15s;
}
.ob-btn-back:hover { color: var(--fg-primary); border-color: var(--fg-muted); }
.ob-btn {
  background: var(--accent); color: #fff; border: none;
  border-radius: 8px; padding: 9px 28px; font-size: 13px;
  font-weight: 600; cursor: pointer; transition: background 0.15s, opacity 0.15s;
}
.ob-btn:hover:not(:disabled) { background: var(--accent-hover, #1a7fd6); }
.ob-btn:disabled { opacity: 0.4; cursor: not-allowed; }
</style>
