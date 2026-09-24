<script setup>
import { computed, ref, watch } from 'vue'
import {
  agentConnected, agentClients, agentScenario, latestAgentActivity, agentActivity,
  stopAgentScenario, showMcpSetupModal, closeAllModals,
  showMapModal, showMapRemoteModal,
} from '../store.js'

const hasScenario = computed(() => !!agentScenario.value)

const clientLabel = computed(() => {
  const names = agentClients.value
  if (!names.length) return 'An agent'
  if (names.length === 1) return names[0]
  return `${names.length} agents`
})

const mocks = computed(() => agentScenario.value?.mocks || [])
const rewrites = computed(() => agentScenario.value?.rewrites || [])
const throttle = computed(() => {
  const t = agentScenario.value?.throttle
  return t && t !== 'None' ? t : null
})

// The banner names the window to look in rather than reprinting every rule.
// The rules already live in Map Local / Map Remote, and duplicating them here
// meant the one place with the full story was the one place nobody looked.
const target = computed(() => {
  if (mocks.value.length) return { label: 'Map Local', open: openMapLocal }
  if (rewrites.value.length) return { label: 'Map Remote', open: openMapRemote }
  return null
})

const openMapLocal = () => { closeAllModals(); showMapModal.value = true }
const openMapRemote = () => { closeAllModals(); showMapRemoteModal.value = true }

// What the agent is doing, in one clause. Counts, not contents.
const summary = computed(() => {
  const parts = []
  if (mocks.value.length) {
    parts.push(`mocking ${mocks.value.length} endpoint${mocks.value.length === 1 ? '' : 's'}`)
  }
  if (rewrites.value.length) {
    parts.push(`${rewrites.value.length} rewrite${rewrites.value.length === 1 ? '' : 's'}`)
  }
  if (throttle.value) parts.push(`throttled to ${throttle.value}`)
  return parts.join(' · ')
})

// Last thing it did, so idle-but-connected still tells you something.
const activityLine = computed(() => latestAgentActivity.value?.message || null)

const openActivitySurface = () => {
  const s = latestAgentActivity.value?.surface
  if (s === 'map_local') openMapLocal()
  else if (s === 'map_remote') openMapRemote()
}

// "What did it do while I was away" — the strip shows one line, the popover
// shows the last twenty, newest first.
const showHistory = ref(false)
const history = computed(() => [...agentActivity.value].reverse())
watch(agentConnected, (on) => { if (!on) showHistory.value = false })

const relTime = (at) => {
  if (!at) return ''
  const s = Math.max(0, Math.round(Date.now() / 1000 - at))
  if (s < 5) return 'just now'
  if (s < 60) return `${s}s ago`
  if (s < 3600) return `${Math.round(s / 60)}m ago`
  return `${Math.round(s / 3600)}h ago`
}
</script>

<template>
  <!--
    Two weights on purpose. An agent merely being attached is informational, so
    it gets a thin neutral strip. An agent actively altering traffic is the
    state that makes people debug problems that aren't theirs, so it gets a
    loud one that can't be dismissed while it's true.
  -->
  <Transition name="agent-slide">
    <div
      v-if="agentConnected"
      class="agent-bar"
      :class="hasScenario ? 'agent-bar--active' : 'agent-bar--idle'"
      role="status"
      aria-live="polite"
    >
      <div class="agent-row">
        <span class="agent-dot" :class="{ 'agent-dot--pulse': hasScenario }" aria-hidden="true"></span>

        <span class="agent-text">
          <template v-if="hasScenario">
            <strong>{{ clientLabel }}</strong> is {{ summary }} —
            <span class="agent-summary">check <strong>{{ target?.label }}</strong></span>
          </template>
          <template v-else>
            <strong>{{ clientLabel }}</strong> connected via MCP · not changing traffic
            <span v-if="activityLine" class="agent-summary">· {{ activityLine }}</span>
          </template>
        </span>

        <div class="agent-actions">
          <button
            v-if="agentActivity.length"
            class="agent-btn agent-btn--ghost"
            :class="{ 'agent-btn--on': showHistory }"
            title="Recent agent actions"
            @click="showHistory = !showHistory"
          >
            History
          </button>
          <button
            v-if="target"
            class="agent-btn agent-btn--ghost"
            :title="`Open ${target.label} to see and edit these rules`"
            @click="target.open()"
          >
            Show rules
          </button>
          <button
            v-else-if="latestAgentActivity?.surface"
            class="agent-btn agent-btn--ghost"
            @click="openActivitySurface"
          >
            Show
          </button>
          <button
            class="agent-btn agent-btn--ghost"
            title="How the MCP integration works"
            @click="showMcpSetupModal = true"
          >
            What's this?
          </button>
          <button
            v-if="hasScenario"
            class="agent-btn agent-btn--stop"
            title="Remove the agent's rules and restore your own"
            @click="stopAgentScenario"
          >
            Stop
          </button>
        </div>
      </div>

      <div v-if="showHistory" class="agent-history">
        <div v-for="(a, i) in history" :key="i" class="agent-history-row">
          <span class="agent-history-time">{{ relTime(a.at) }}</span>
          <span class="agent-history-msg">{{ a.message }}</span>
        </div>
      </div>
    </div>
  </Transition>
</template>

<style scoped>
.agent-bar {
  flex-shrink: 0;
  font-size: 11px;
  border-bottom: 1px solid var(--border);
  user-select: none;
}

.agent-bar--idle {
  background: var(--bg-card);
  color: var(--fg-muted);
}

.agent-bar--active {
  background: var(--warning-muted);
  color: var(--fg-primary);
  border-bottom-color: var(--warning);
}

.agent-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 5px 10px;
  min-height: 26px;
}

.agent-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--fg-muted);
  flex-shrink: 0;
}

.agent-bar--active .agent-dot {
  background: var(--warning);
}

.agent-dot--pulse {
  animation: agent-pulse 2s ease-in-out infinite;
}

@keyframes agent-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.35; }
}

/* Respect users who've asked the OS for less motion. */
@media (prefers-reduced-motion: reduce) {
  .agent-dot--pulse { animation: none; }
}

.agent-text {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.agent-summary {
  color: var(--fg-secondary);
  margin-left: 4px;
}

.agent-bar--idle .agent-summary {
  color: var(--fg-muted);
}

.agent-actions {
  display: flex;
  gap: 6px;
  flex-shrink: 0;
}

.agent-btn {
  font-size: 10px;
  font-family: inherit;
  padding: 2px 8px;
  border-radius: 4px;
  cursor: pointer;
  border: 1px solid transparent;
  background: transparent;
  color: inherit;
  white-space: nowrap;
}

.agent-btn--ghost {
  border-color: var(--border);
  color: var(--fg-secondary);
}

.agent-btn--ghost:hover {
  background: var(--bg-hover);
}

.agent-btn--on {
  background: var(--bg-active);
  color: var(--fg-primary);
}

.agent-history {
  max-height: 140px;
  overflow-y: auto;
  border-top: 1px solid var(--border-subtle);
  padding: 4px 10px 6px 25px;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.agent-history-row {
  display: flex;
  gap: 10px;
  align-items: baseline;
  font-size: 10.5px;
  color: var(--fg-secondary);
}

.agent-history-time {
  flex-shrink: 0;
  width: 56px;
  color: var(--fg-muted);
  font-variant-numeric: tabular-nums;
}

.agent-history-msg {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.agent-btn--stop {
  background: var(--warning);
  color: #1a1b1c;
  font-weight: 600;
}

.agent-btn--stop:hover {
  filter: brightness(1.1);
}

.agent-btn:focus-visible {
  outline: none;
  box-shadow: var(--focus-ring);
}

.agent-slide-enter-active,
.agent-slide-leave-active {
  transition: opacity 0.18s ease;
}

.agent-slide-enter-from,
.agent-slide-leave-to {
  opacity: 0;
}
</style>
