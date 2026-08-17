<script setup>
import { ref, computed } from 'vue'
import {
  showCertTrustDialog,
  certTrustLoading,
  certTrustError,
  certTrustStatus,
  trustCertOnThisMachine,
  dismissCertTrustDialog,
  platform,
} from '../store.js'

const showManualSteps = ref(false)

const deviceLabel = computed(() => ({
  darwin: 'Mac',
  win32:  'Windows PC',
  linux:  'Linux machine',
}[platform.value] || 'machine')
)

// Same paths main.py generates the cert to — see MACOS_CERT_PATH / WINDOWS_CERT_PATH / LINUX_CERT_PATH
const certPath = computed(() => {
  const home = window.electronAPI?.homeDir || ''
  if (platform.value === 'win32') return `${home}\\.mitmproxy\\mitmproxy-ca-cert.cer`
  return `${home}/.mitmproxy/mitmproxy-ca-cert.pem`
})

const revealLabel = computed(() => ({
  darwin: 'Show certificate in Finder',
  win32:  'Show certificate in Explorer',
  linux:  'Show certificate in file manager',
}[platform.value] || 'Show certificate file')
)

const revealCertFile = () => {
  if (typeof window.electronAPI?.showItemInFolder !== 'function') {
    console.warn('[CertTrustModal] electronAPI.showItemInFolder is unavailable — ' +
      'if you just edited electron/preload.js, fully restart the app (not just reload the page).')
    return
  }
  window.electronAPI.showItemInFolder(certPath.value)
}

const dismiss = () => dismissCertTrustDialog()
</script>

<template>
  <Teleport to="body">
    <Transition name="warn-fade">
      <div v-if="showCertTrustDialog" class="warn-overlay" @click.self="dismiss">
        <div class="warn-panel" role="alertdialog" aria-modal="true" aria-labelledby="ct-title">

          <div class="warn-icon-row">
            <div class="warn-icon">🔒</div>
          </div>

          <h2 id="ct-title" class="warn-title">Certificate Not Installed</h2>

          <p class="warn-body">
            OpenProxy generates a certificate to decrypt HTTPS traffic for inspection.
            It isn't trusted on this {{ deviceLabel }} yet, so
            <strong>browsers on this machine</strong> (not the devices you're proxying)
            may show security warnings or fail to load HTTPS sites while routed through OpenProxy.
          </p>

          <div v-if="certTrustStatus === true" class="ct-success">
            <span>✓</span> Certificate trusted on this {{ deviceLabel }}.
          </div>

          <div v-if="certTrustError" class="warn-callout ct-error">
            <span class="warn-callout-icon">⚠️</span>
            <span>{{ certTrustError }}</span>
          </div>

          <button class="ct-manual-toggle" @click="showManualSteps = !showManualSteps">
            {{ showManualSteps ? 'Hide manual steps' : 'Prefer to do it manually?' }}
          </button>

          <div v-if="showManualSteps" class="ct-manual-steps">
            <button class="ct-reveal-btn" @click="revealCertFile">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
              </svg>
              {{ revealLabel }}
            </button>
            <template v-if="platform === 'darwin'">
              <ol>
                <li>Double-click the certificate file to open it in Keychain Access.</li>
                <li>Find <strong>mitmproxy</strong>, double-click it, expand <strong>Trust</strong>, and set to <strong>Always Trust</strong>.</li>
              </ol>
            </template>
            <template v-else-if="platform === 'win32'">
              <ol>
                <li>Double-click the <code>.cer</code> file, click <strong>Install Certificate</strong>.</li>
                <li>Choose <strong>Current User</strong>, then <strong>Place all certificates in the following store</strong> → <strong>Trusted Root Certification Authorities</strong>.</li>
              </ol>
            </template>
            <template v-else>
              <ol>
                <li>Copy it into your distro's trust anchors (e.g. <code>/usr/local/share/ca-certificates/</code> on Debian/Ubuntu, or <code>/etc/pki/ca-trust/source/anchors/</code> on Fedora/RHEL).</li>
                <li>Run <code>update-ca-certificates</code> (or <code>update-ca-trust extract</code>).</li>
                <li>Firefox keeps its own separate certificate store — import it there too via <strong>Settings → Privacy &amp; Security → Certificates → View Certificates → Import</strong>.</li>
              </ol>
            </template>
          </div>

          <div class="warn-footer">
            <button class="warn-btn-dismiss" @click="dismiss">Not now</button>
            <button class="warn-btn-primary" :disabled="certTrustLoading || certTrustStatus === true" @click="trustCertOnThisMachine()">
              {{ certTrustLoading ? 'Installing…' : certTrustStatus === true ? 'Installed' : 'Install automatically' }}
            </button>
          </div>

        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.warn-overlay {
  position: fixed; inset: 0; z-index: 99999;
  background: rgba(0, 0, 0, 0.55);
  display: flex; align-items: center; justify-content: center;
}

.warn-panel {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 14px;
  box-shadow: 0 24px 64px rgba(0, 0, 0, 0.45);
  width: 460px; max-width: 95vw;
  padding: 28px 28px 24px;
  display: flex; flex-direction: column; gap: 14px;
}

.warn-icon-row { display: flex; justify-content: center; }
.warn-icon { font-size: 36px; line-height: 1; }

.warn-title {
  margin: 0; text-align: center;
  font-size: 17px; font-weight: 700;
  color: var(--fg-primary);
}

.warn-body {
  margin: 0;
  font-size: 13px; color: var(--fg-secondary); line-height: 1.55;
  text-align: center;
}

.ct-success {
  display: flex; align-items: center; justify-content: center; gap: 6px;
  font-size: 13px; font-weight: 600; color: #34d399;
}

.warn-callout {
  display: flex; align-items: flex-start; gap: 10px;
  background: var(--bg-deepest);
  border: 1px solid var(--border);
  border-left: 3px solid #e3a008;
  border-radius: 8px;
  padding: 12px 14px;
  font-size: 12.5px; color: var(--fg-secondary); line-height: 1.5;
}
.warn-callout-icon { font-size: 16px; flex-shrink: 0; margin-top: 1px; }
.ct-error { border-left-color: var(--setup-error, #ef4444); }

.ct-manual-toggle {
  align-self: center;
  background: none; border: none; cursor: pointer;
  font-size: 12px; color: var(--accent);
  padding: 0;
}
.ct-manual-toggle:hover { text-decoration: underline; }

.ct-manual-steps {
  background: var(--bg-deepest);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 12px 14px;
  font-size: 12px; color: var(--fg-secondary); line-height: 1.6;
}
.ct-manual-steps ol { margin: 0; padding-left: 18px; }

.ct-reveal-btn {
  display: inline-flex; align-items: center; gap: 6px;
  background: var(--bg-card); border: 1px solid var(--border);
  color: var(--fg-secondary); font-size: 11.5px; font-weight: 600;
  padding: 6px 10px; border-radius: 6px; cursor: pointer;
  margin-bottom: 10px; transition: all 0.15s;
}
.ct-reveal-btn:hover { color: var(--fg-primary); border-color: var(--fg-muted); }
.ct-manual-steps code {
  background: var(--bg-card); border: 1px solid var(--border);
  border-radius: 4px; padding: 1px 5px; font-size: 11px;
}

.warn-hint {
  margin: 0; text-align: center;
  font-size: 12px; color: var(--fg-muted); line-height: 1.5;
}

.warn-footer {
  display: flex; align-items: center;
  gap: 8px; margin-top: 4px;
}

.warn-btn-dismiss {
  flex: 1; text-align: center;
  font-size: 12px;
  background: transparent; border: 1px solid var(--border);
  color: var(--fg-muted); padding: 8px 16px;
  border-radius: 6px; cursor: pointer; transition: all 0.15s;
}
.warn-btn-dismiss:hover { color: var(--fg-primary); border-color: var(--fg-muted); }

.warn-btn-primary {
  flex: 1; text-align: center;
  background: var(--accent); color: #fff; border: none;
  border-radius: 8px; padding: 8px 18px;
  font-size: 13px; font-weight: 600;
  cursor: pointer; transition: background 0.15s;
}
.warn-btn-primary:hover { background: var(--accent-hover, #1a7fd6); }
.warn-btn-primary:disabled { opacity: 0.6; cursor: not-allowed; }

.warn-fade-enter-active,
.warn-fade-leave-active { transition: opacity 0.2s, transform 0.2s; }
.warn-fade-enter-from,
.warn-fade-leave-to { opacity: 0; transform: scale(0.96); }
</style>
