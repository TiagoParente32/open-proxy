<script setup>
// IMPORT proxyHost from the store!
import { showDeviceSetupModal, deviceSetupType, injectEmulatorCert, proxyHost } from '../store.js'

const triggerInjection = () => {
  injectEmulatorCert()
  showDeviceSetupModal.value = false // Close modal so they can see the alerts
}
</script>

<template>
  <div v-if="showDeviceSetupModal" class="modal-overlay" @mousedown.self="showDeviceSetupModal = false">
    <div class="modal-content" style="width: 500px; max-width: 90vw; display: flex; flex-direction: column;">
      
      <div style="padding: 16px; border-bottom: 1px solid var(--border); background: var(--bg-sidebar); text-align: left;">
        <strong style="color: white; font-size: 14px;">
          {{ deviceSetupType === 'emulator' ? '📱 Android Emulator Setup' : '📲 Physical Device Setup' }}
        </strong>
      </div>
      
      <div v-if="deviceSetupType === 'emulator'" class="modal-body">
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

      <div v-if="deviceSetupType === 'device'" class="modal-body">
        <p style="margin-bottom: 16px;">To intercept traffic from a physical Android device, you must manually configure your Wi-Fi and install the certificate.</p>
        
        <ol class="instruction-list numbered">
          <li>Ensure your phone and computer are on the <strong>same Wi-Fi network</strong>.</li>
          <li>On your Android device, go to <strong>Settings > Wi-Fi</strong>, tap the gear icon next to your network, and edit the <strong>Proxy</strong> settings.</li>
          <li>Set the proxy to <strong>Manual</strong>.</li>
          <li>Enter your Proxy IP and Port: <code class="inline-code highlighted">{{ proxyHost }}</code></li>
          <li>Open your mobile browser and navigate to <code class="inline-code">http://mitm.it</code> to download and install the OpenProxy certificate.</li>
        </ol>
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

/* Enforced text-align: left here so everything reads cleanly left-to-right */
.modal-body { padding: 24px; background: var(--bg-main); font-size: 13px; color: #ccc; line-height: 1.5; text-align: left; }
.modal-footer { padding: 16px; border-top: 1px solid var(--border); display: flex; justify-content: flex-end; background: var(--bg-sidebar); }

.instruction-list { margin-left: 20px; margin-bottom: 20px; color: #aaa; display: flex; flex-direction: column; gap: 8px; text-align: left; }
.instruction-list.numbered { list-style-type: decimal; }

.inline-code { background: #222; padding: 2px 6px; border-radius: 4px; font-family: monospace; color: #e5e7eb; border: 1px solid #333; }
.inline-code.highlighted { background: rgba(59, 130, 246, 0.15); color: #60a5fa; border-color: rgba(59, 130, 246, 0.3); font-weight: bold; font-size: 14px; }

.warning-text { color: #f59e0b; font-size: 12px; margin-bottom: 20px; background: rgba(245, 158, 11, 0.1); padding: 10px; border-radius: 6px; border: 1px solid rgba(245, 158, 11, 0.2); text-align: left; }

.inject-btn { background: #3b82f6; color: white; border: 1px solid #3b82f6; border-radius: 6px; padding: 10px 16px; font-weight: bold; width: 100%; display: flex; justify-content: center; align-items: center; gap: 8px; cursor: pointer; transition: background 0.2s; font-size: 13px; }
.inject-btn:hover { background: #2563eb; }

.action-btn { background: #2a2d2e; border: 1px solid #444; color: #ccc; border-radius: 4px; padding: 6px 16px; font-size: 12px; cursor: pointer; transition: all 0.2s; }
.action-btn:hover { background: #333; color: white; border-color: #555; }
</style>