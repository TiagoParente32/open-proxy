<script setup>
import { ref } from 'vue'
import { syncProxyIgnoreHosts } from '../store.js'

const emit = defineEmits(['done'])

const step     = ref(1)   // 1 = choose mode, 2 = add hosts
const selected = ref(null)
const draft    = ref('')

// ── URL / hostname normalization ──────────────────────────────────────────────
// Accepts: plain hostname, URL with protocol, and existing regex — returns regex-ready pattern
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

const prettifyPattern = (pattern) => {
  if (pattern.startsWith('(.+\\.)?')) {
    const rest      = pattern.slice('(.+\\.)?'.length)
    const unescaped = rest.replace(/\\\./g, '.')
    if (!/[\\()|+?[\]^${}*]/.test(unescaped)) return '*.' + unescaped
  }
  const unescaped = pattern.replace(/\\\./g, '.')
  if (!/[\\()|+?[\]^${}*]/.test(unescaped)) return unescaped
  return pattern
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

const goNext = () => {
  if (!selected.value) return
  step.value = 2
}

const goBack = () => { step.value = 1 }

const finish = () => {
  const raw   = draft.value.split('\n').map(l => l.trim()).filter(Boolean)
  const hosts = raw.map(normalizeEntry).filter(Boolean)
  syncProxyIgnoreHosts(hosts, selected.value)
  localStorage.setItem('openproxyOnboardingDone', '1')
  emit('done')
}

const skip = () => {
  syncProxyIgnoreHosts([], selected.value)
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
          <div class="ob-step" :class="{ active: step === 1, done: step > 1 }">1</div>
          <div class="ob-step-line" :class="{ done: step > 1 }"></div>
          <div class="ob-step" :class="{ active: step === 2 }">2</div>
        </div>

        <!-- ── STEP 1: Choose mode ── -->
        <template v-if="step === 1">
          <img src="/icon.png" alt="OpenProxy" class="ob-icon" />
          <h1 class="ob-title">Welcome to OpenProxy</h1>
          <p class="ob-subtitle">How would you like to intercept traffic?</p>

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

          <button class="ob-btn" :disabled="!selected" @click="goNext">
            Next →
          </button>
        </template>

        <!-- ── STEP 2: Add hosts ── -->
        <template v-else>
          <div class="ob-step2-header">
            <div v-if="selected === 'allow'">
              <h2 class="ob-title" style="font-size:18px">Add hosts to intercept</h2>
              <p class="ob-subtitle">Only these hosts will be intercepted. Add the apps you want to debug.</p>
            </div>
            <div v-else>
              <h2 class="ob-title" style="font-size:18px">Any hosts to skip? <span style="font-weight:400;font-size:14px;color:var(--fg-muted)">(optional)</span></h2>
              <p class="ob-subtitle">These hosts will pass through without interception — useful for apps with strict certificate pinning.</p>
            </div>
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
            :placeholder="selected === 'allow'
              ? 'api.example.com\nhttps://app.myservice.com\n*.mycompany.com'
              : 'api.example.com\nhttps://app.myservice.com\n*.googleapis.com'"
            spellcheck="false"
          />
          <p class="ob-hint">
            Enter hostnames, URLs, or use <code>*.example.com</code> to match all subdomains.
          </p>

          <div class="ob-footer">
            <button class="ob-btn-back" @click="goBack">← Back</button>
            <div style="flex:1"/>
            <button v-if="selected === 'ignore'" class="ob-btn-skip" @click="skip">Skip</button>
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
  font-size: 12px; font-weight: 700;
  background: var(--bg-deepest); border: 2px solid var(--border);
  color: var(--fg-muted); transition: all 0.2s;
}
.ob-step.active { background: var(--accent); border-color: var(--accent); color: #fff; }
.ob-step.done   { background: var(--accent); border-color: var(--accent); color: #fff; opacity: 0.5; }
.ob-step-line { width: 40px; height: 2px; background: var(--border); transition: background 0.2s; }
.ob-step-line.done { background: var(--accent); opacity: 0.5; }

.ob-icon { width: 56px; height: 56px; border-radius: 14px; margin-bottom: 4px; }

.ob-title { font-size: 20px; font-weight: 700; color: var(--fg-primary); margin: 0; text-align: center; }
.ob-subtitle { font-size: 13px; color: var(--fg-muted); margin: 0; text-align: center; line-height: 1.5; }

.ob-cards { display: flex; gap: 14px; width: 100%; }
.ob-card {
  flex: 1; background: var(--bg-deepest); border: 2px solid var(--border);
  border-radius: 10px; padding: 16px 14px; cursor: pointer; position: relative;
  transition: border-color 0.15s, box-shadow 0.15s;
  display: flex; flex-direction: column; gap: 8px;
}
.ob-card:hover { border-color: var(--accent); }
.ob-card.selected { border-color: var(--accent); box-shadow: 0 0 0 3px rgba(88,166,255,0.15); }
.ob-card-icon { font-size: 24px; }
.ob-card-title { font-size: 13px; font-weight: 600; color: var(--fg-primary); }
.ob-card-desc { font-size: 11.5px; color: var(--fg-muted); line-height: 1.5; }
.ob-card-pros { list-style: none; margin: 4px 0 0; padding: 0; display: flex; flex-direction: column; gap: 4px; }
.ob-card-pros li { font-size: 11px; color: var(--fg-secondary); }
.ob-card-check { position: absolute; top: 10px; right: 12px; color: var(--accent); font-weight: 700; font-size: 15px; }

.ob-note { font-size: 12px; color: var(--fg-muted); text-align: center; margin: 0; }
.ob-note strong { color: var(--fg-secondary); }

/* Step 2 */
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
  width: 100%; min-height: 120px; resize: vertical;
  background: var(--bg-deepest); border: 1px solid var(--border);
  color: var(--fg-secondary); border-radius: 6px; padding: 10px 12px;
  font-family: 'Consolas', 'Monaco', monospace; font-size: 12px; line-height: 1.6;
  outline: none; box-sizing: border-box; transition: border-color 0.15s;
}
.ob-textarea:focus { border-color: var(--accent); }
.ob-hint { font-size: 11px; color: var(--fg-muted); margin: 0; width: 100%; }
.ob-hint code {
  background: var(--bg-deepest); border: 1px solid var(--border);
  padding: 1px 5px; border-radius: 3px; font-size: 10px;
}

.ob-footer { display: flex; align-items: center; gap: 8px; width: 100%; margin-top: 4px; }
.ob-btn-back {
  font-size: 12px; background: transparent; border: 1px solid var(--border);
  color: var(--fg-muted); padding: 8px 14px; border-radius: 6px; cursor: pointer; transition: all 0.15s;
}
.ob-btn-back:hover { color: var(--fg-primary); border-color: var(--fg-muted); }
.ob-btn-skip {
  font-size: 12px; background: transparent; border: none;
  color: var(--fg-muted); padding: 8px 14px; border-radius: 6px; cursor: pointer; transition: color 0.15s;
}
.ob-btn-skip:hover { color: var(--fg-secondary); }
.ob-btn {
  background: var(--accent); color: #fff; border: none;
  border-radius: 8px; padding: 9px 28px; font-size: 13px;
  font-weight: 600; cursor: pointer; transition: background 0.15s, opacity 0.15s;
}
.ob-btn:hover:not(:disabled) { background: var(--accent-hover, #1a7fd6); }
.ob-btn:disabled { opacity: 0.4; cursor: not-allowed; }
</style>
