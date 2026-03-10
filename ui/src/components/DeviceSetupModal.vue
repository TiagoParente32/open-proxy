<script setup>
import { showDeviceSetupModal, deviceSetupType, injectEmulatorCert, proxyIP, proxyPort } from '../store.js'

const triggerInjection = () => {
  injectEmulatorCert()
  showDeviceSetupModal.value = false 
}

// Helper to get a clean title based on the state
const getTitle = () => {
  if (deviceSetupType.value === 'android_emulator') return '📱 Android Emulator Setup'
  if (deviceSetupType.value === 'android_device') return '📲 Android Device Setup'
  if (deviceSetupType.value === 'ios_simulator') return '💻 iOS Simulator Setup'
  if (deviceSetupType.value === 'ios_device') return '📱 iOS Physical Device Setup'
  return 'Device Setup'
}
</script>

<template>
  <div v-if="showDeviceSetupModal" class="modal-overlay" @mousedown.self="showDeviceSetupModal = false">
    <div class="modal-content" style="width: 550px; max-width: 90vw; display: flex; flex-direction: column;">
      
      <div style="padding: 16px; border-bottom: 1px solid var(--border); background: var(--bg-sidebar); text-align: left;">
        <strong style="color: white; font-size: 14px;">{{ getTitle() }}</strong>
      </div>
      
      <div v-if="deviceSetupType === 'android_emulator'" class="modal-body">
        <p style="margin-bottom: 12px;">To automatically inject the OpenProxy certificate and configure the proxy, your emulator must meet these requirements:</p>
        <ul class="instruction-list">
          <li>Must be an <strong>Android Emulator with Google APIs</strong> (Google Play versions block root access).</li>
          <li>The emulator must be currently running.</li>
          <li>You must have <code class="inline-code">adb</code> and <code class="inline-code">openssl</code> installed on your system.</li>
        </ul>
        <p class="warning-text">⚠️ Note: This script will restart the ADB daemon as root, push the certificate to system files, and override global proxy settings.</p>
        <button class="inject-btn" @click="triggerInjection">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="7 10 12 15 17 10"></polyline><line x1="12" y1="15" x2="12" y2="3"></line></svg>
          Inject Certificate & Set Proxy
        </button>
      </div>

      <div v-if="deviceSetupType === 'android_device'" class="modal-body">
        <ol class="instruction-list numbered">
          <li>Ensure your phone and computer are on the <strong>same Wi-Fi network</strong>.</li>
          <li>Go to <strong>Settings > Wi-Fi</strong>, tap the gear icon next to your network, and edit <strong>Proxy</strong> settings to <strong>Manual</strong>.</li>
          <li>
            Enter your Proxy details:<br>
            <div class="ip-box">
              <div style="margin-bottom: 4px;">Hostname: <code class="inline-code highlighted">{{ proxyIP }}</code></div>
              <div>Port: <code class="inline-code highlighted">{{ proxyPort }}</code></div>
            </div>
          </li>          
          <li>Open your mobile browser and go to <code class="inline-code">http://mitm.it</code> to download the certificate.</li>
          <li>Go to <strong>Settings > Security > Encryption & Credentials > Install a certificate</strong> and select the downloaded file.</li>
        </ol>
      </div>

      <div v-if="deviceSetupType === 'ios_simulator'" class="modal-body">
        <p style="margin-bottom: 12px;">iOS Simulators inherit their network connection directly from your Mac.</p>
        <ol class="instruction-list numbered">
          <li>
            Ensure your macOS <strong>System Settings > Network > Proxies</strong> is configured with:<br>
            <div class="ip-box">
              <div style="margin-bottom: 4px;">Server: <code class="inline-code highlighted">{{ proxyIP }}</code></div>
              <div>Port: <code class="inline-code highlighted">{{ proxyPort }}</code></div>
            </div>
          </li>
          <li>Boot up your iOS Simulator and open the <strong>Safari</strong> app.</li>
          <li>Navigate to <code class="inline-code">http://mitm.it</code> and download the certificate profile.</li>
          <li>Go to the Simulator's <strong>Settings > General > VPN & Device Management</strong> and install the Profile.</li>
          <li><strong>Crucial Step:</strong> Go to <strong>Settings > General > About > Certificate Trust Settings</strong> and toggle the switch ON for the mitmproxy certificate!</li>
        </ol>
        <p class="warning-text" style="margin-top: 10px; margin-bottom: 0;">⚠️ If you skip Step 5, all HTTPS traffic will fail with SSL errors.</p>
      </div>

      <div v-if="deviceSetupType === 'ios_device'" class="modal-body">
        <ol class="instruction-list numbered">
          <li>Ensure your iPhone and computer are on the <strong>same Wi-Fi network</strong>.</li>
          <li>Go to <strong>Settings > Wi-Fi</strong>, tap the <strong>(i)</strong> next to your network, scroll down to <strong>Configure Proxy</strong>, and select <strong>Manual</strong>.</li>
          <li>
            Enter your Proxy details:<br>
            <div class="ip-box">
              <div style="margin-bottom: 4px;">Server: <code class="inline-code highlighted">{{ proxyIP }}</code></div>
              <div>Port: <code class="inline-code highlighted">{{ proxyPort }}</code></div>
            </div>
          </li>
          <li>Open Safari and go to <code class="inline-code">http://mitm.it</code> to download the configuration profile.</li>
          <li>Go to <strong>Settings > General > VPN & Device Management</strong> and install the Profile.</li>
          <li><strong>Crucial Step:</strong> Go to <strong>Settings > General > About > Certificate Trust Settings</strong> and toggle the switch ON for the mitmproxy certificate!</li>
        </ol>
        <p class="warning-text" style="margin-top: 10px; margin-bottom: 0;">⚠️ If you skip Step 6, all HTTPS traffic will fail with SSL errors.</p>
      </div>

      <div class="modal-footer">
        <button class="action-btn" @click="showDeviceSetupModal = false">Close</button>
      </div>
      
    </div>
  </div>
</template>

<style scoped>
.modal-overlay { position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0, 0, 0, 0.7); z-index: 99999; display: flex; justify-content: center; align-items: center; backdrop-filter: blur(2px); }
.modal-content { background: var(--bg-main); border: 1px solid var(--border); border-radius: 8px; box-shadow: 0 10px 40px rgba(0,0,0,0.6); overflow: hidden; }

.modal-body { padding: 24px; background: var(--bg-main); font-size: 13px; color: #ccc; line-height: 1.5; text-align: left; }
.modal-footer { padding: 16px; border-top: 1px solid var(--border); display: flex; justify-content: flex-end; background: var(--bg-sidebar); }

.instruction-list { margin-left: 20px; margin-bottom: 16px; color: #aaa; display: flex; flex-direction: column; gap: 10px; text-align: left; }
.instruction-list.numbered { list-style-type: decimal; }

/* The nice dark box for IP/Port details */
.ip-box { margin-top: 6px; padding: 10px; background: rgba(0,0,0,0.25); border-radius: 6px; border: 1px solid #333; box-shadow: inset 0 2px 4px rgba(0,0,0,0.2); }

.inline-code { background: #222; padding: 2px 6px; border-radius: 4px; font-family: monospace; color: #e5e7eb; border: 1px solid #333; }
.inline-code.highlighted { background: rgba(59, 130, 246, 0.15); color: #60a5fa; border-color: rgba(59, 130, 246, 0.3); font-weight: bold; font-size: 14px; }

.warning-text { color: #f59e0b; font-size: 12px; margin-bottom: 20px; background: rgba(245, 158, 11, 0.1); padding: 10px; border-radius: 6px; border: 1px solid rgba(245, 158, 11, 0.2); text-align: left; }

.inject-btn { background: #3b82f6; color: white; border: 1px solid #3b82f6; border-radius: 6px; padding: 10px 16px; font-weight: bold; width: 100%; display: flex; justify-content: center; align-items: center; gap: 8px; cursor: pointer; transition: background 0.2s; font-size: 13px; }
.inject-btn:hover { background: #2563eb; }

.action-btn { background: #2a2d2e; border: 1px solid #444; color: #ccc; border-radius: 4px; padding: 6px 16px; font-size: 12px; cursor: pointer; transition: all 0.2s; }
.action-btn:hover { background: #333; color: white; border-color: #555; }
</style>