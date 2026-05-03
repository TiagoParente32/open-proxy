<script setup>
import { setupProgress } from '../store.js'

const closeOnFail = () => {
    setupProgress.value.show = false;
}
</script>

<template>
  <div v-if="setupProgress.show" class="modal-overlay">
    <div class="progress-card">
      <h3 style="margin: 0 0 16px 0; color: white; font-size: 14px;">Android Setup in Progress</h3>
      
      <div class="steps-container">
        <div v-for="step in setupProgress.steps" :key="step.id" class="step-row" :class="step.status">
          
          <div class="icon-wrapper">
            <div v-if="step.status === 'pending'" class="dot pending"></div>
            
            <svg v-else-if="step.status === 'loading'" class="spinner" viewBox="0 0 50 50">
              <circle class="path" cx="25" cy="25" r="20" fill="none" stroke-width="5"></circle>
            </svg>
            
            <svg v-else-if="step.status === 'success'" class="icon-success" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round">
              <polyline points="20 6 9 17 4 12"></polyline>
            </svg>
            
            <svg v-else-if="step.status === 'error'" class="icon-error" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round">
              <line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line>
            </svg>
          </div>
          
          <span class="step-label">{{ step.label }}</span>
        </div>
      </div>

      <div v-if="setupProgress.error" class="error-box">
        <div style="font-weight: bold; margin-bottom: 4px;">Setup Failed</div>
        <div style="font-family: monospace; font-size: 11px;">{{ setupProgress.error }}</div>
        <button class="close-btn" @click="closeOnFail">Dismiss</button>
      </div>

    </div>
  </div>
</template>

<style scoped>
.modal-overlay { position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: var(--overlay); z-index: 999999; display: flex; justify-content: center; align-items: center; backdrop-filter: blur(3px); }

.progress-card { background: var(--bg-main); border: 1px solid var(--border); border-radius: 12px; box-shadow: var(--shadow-lg); padding: 24px; width: 340px; text-align: left; display: flex; flex-direction: column; }

.steps-container { display: flex; flex-direction: column; gap: 14px; }

.step-row { display: flex; align-items: center; gap: 12px; color: var(--fg-muted); font-size: 13px; font-weight: 500; transition: color 0.3s; }
.step-row.loading { color: var(--fg-primary); }
.step-row.success { color: var(--fg-muted); }
.step-row.error { color: var(--error); }

.icon-wrapper { width: 18px; height: 18px; display: flex; justify-content: center; align-items: center; flex-shrink: 0; }

.dot.pending { width: 6px; height: 6px; background: var(--border); border-radius: 50%; }

.icon-success { color: var(--success); width: 16px; height: 16px; }
.icon-error { color: var(--error); width: 16px; height: 16px; }

/* Beautiful SVG Spinner */
.spinner { animation: rotate 2s linear infinite; width: 18px; height: 18px; }
.spinner .path { stroke: var(--accent); stroke-linecap: round; animation: dash 1.5s ease-in-out infinite; }

@keyframes rotate { 100% { transform: rotate(360deg); } }
@keyframes dash {
  0% { stroke-dasharray: 1, 150; stroke-dashoffset: 0; }
  50% { stroke-dasharray: 90, 150; stroke-dashoffset: -35; }
  100% { stroke-dasharray: 90, 150; stroke-dashoffset: -124; }
}

.error-box { margin-top: 20px; padding: 12px; background: var(--error-muted); border: 1px solid rgba(239,68,68,0.3); border-radius: 6px; color: var(--error); }
.close-btn { margin-top: 12px; width: 100%; background: var(--bg-active); border: 1px solid var(--border); color: var(--fg-secondary); border-radius: 4px; padding: 6px 16px; font-size: 12px; cursor: pointer; transition: all 0.2s; }
.close-btn:hover { background: var(--border); color: var(--fg-primary); border-color: var(--fg-muted); }
</style>