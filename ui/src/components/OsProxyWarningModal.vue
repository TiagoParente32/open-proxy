<script setup>
import { showOsProxyWarning, showIgnoreHostsModal, closeAllModals } from '../store.js'

const dismiss = () => { showOsProxyWarning.value = false }

const goToHostFilters = () => {
  showOsProxyWarning.value = false
  closeAllModals()
  showIgnoreHostsModal.value = true
}
</script>

<template>
  <Teleport to="body">
    <Transition name="warn-fade">
      <div v-if="showOsProxyWarning" class="warn-overlay" @click.self="dismiss">
        <div class="warn-panel" role="alertdialog" aria-modal="true" aria-labelledby="warn-title">

          <div class="warn-icon-row">
            <div class="warn-icon">⚠️</div>
          </div>

          <h2 id="warn-title" class="warn-title">All Traffic Is Being Intercepted</h2>

          <p class="warn-body">
            The OS proxy is now active but no host filters are configured,
            so <strong>every HTTPS request passes through the proxy</strong>.
            Apps that pin their certificates or use strict TLS verification
            may fail to connect.
          </p>

          <div class="warn-callout">
            <span class="warn-callout-icon">💡</span>
            <span>
              Video calls, banking apps, and services with strict certificate
              checks are common examples of things that may stop working.
            </span>
          </div>

          <p class="warn-hint">
            Use <em>Host Filters</em> to exclude domains you don't want intercepted.
          </p>

          <div class="warn-footer">
            <button class="warn-btn-dismiss" @click="dismiss">Dismiss</button>
            <button class="warn-btn-primary" @click="goToHostFilters">
              Open Host Filters →
            </button>
          </div>

        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.warn-overlay {
  position: fixed; inset: 0; z-index: 9999;
  background: rgba(0, 0, 0, 0.55);
  display: flex; align-items: center; justify-content: center;
}

.warn-panel {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 14px;
  box-shadow: 0 24px 64px rgba(0, 0, 0, 0.45);
  width: 440px; max-width: 95vw;
  padding: 28px 28px 24px;
  display: flex; flex-direction: column; gap: 14px;
}

.warn-icon-row {
  display: flex; justify-content: center;
}
.warn-icon {
  font-size: 36px; line-height: 1;
}

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

.warn-hint {
  margin: 0; text-align: center;
  font-size: 12px; color: var(--fg-muted); line-height: 1.5;
}

.warn-footer {
  display: flex; justify-content: flex-end; align-items: center;
  gap: 8px; margin-top: 4px;
}

.warn-btn-dismiss {
  font-size: 12px;
  background: transparent; border: 1px solid var(--border);
  color: var(--fg-muted); padding: 8px 16px;
  border-radius: 6px; cursor: pointer; transition: all 0.15s;
}
.warn-btn-dismiss:hover { color: var(--fg-primary); border-color: var(--fg-muted); }

.warn-btn-primary {
  background: var(--accent); color: #fff; border: none;
  border-radius: 8px; padding: 8px 18px;
  font-size: 13px; font-weight: 600;
  cursor: pointer; transition: background 0.15s;
}
.warn-btn-primary:hover { background: var(--accent-hover, #1a7fd6); }

.warn-fade-enter-active,
.warn-fade-leave-active { transition: opacity 0.2s, transform 0.2s; }
.warn-fade-enter-from,
.warn-fade-leave-to { opacity: 0; transform: scale(0.96); }
</style>
