<script setup>
import { ref, computed, watch } from 'vue'
import { agentConnected, agentClients, agentScenario, stopAgentScenario } from '../store.js'

// Collapsed by default so the strip stays out of the way; the summary line
// already names how many endpoints are affected.
const expanded = ref(false)

// Collapse when a scenario ends, so the next one doesn't arrive pre-expanded
// with rules the user never asked to see.
watch(() => agentScenario.value?.name, (name) => {
  if (!name) expanded.value = false
})

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

const summary = computed(() => {
  const parts = []
  if (mocks.value.length) {
    parts.push(`${mocks.value.length} endpoint${mocks.value.length === 1 ? '' : 's'} mocked`)
  }
  if (rewrites.value.length) {
    parts.push(`${rewrites.value.length} rewrite${rewrites.value.length === 1 ? '' : 's'}`)
  }
  if (throttle.value) parts.push(`throttled to ${throttle.value}`)
  return parts.length ? parts.join(' · ') : 'no traffic changes'
})
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
            <strong>{{ clientLabel }}</strong> is changing your traffic —
            <strong>&ldquo;{{ agentScenario.name }}&rdquo;</strong>
            <span class="agent-summary">({{ summary }})</span>
          </template>
          <template v-else>
            <strong>{{ clientLabel }}</strong> connected via MCP · not changing traffic
          </template>
        </span>

        <div class="agent-actions">
          <button
            v-if="hasScenario && (mocks.length || rewrites.length)"
            class="agent-btn agent-btn--ghost"
            :aria-expanded="expanded"
            @click="expanded = !expanded"
          >
            {{ expanded ? 'Hide' : 'Show' }} rules
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

      <div v-if="expanded && hasScenario" class="agent-rules">
        <div v-for="(m, i) in mocks" :key="`m${i}`" class="agent-rule">
          <span class="agent-tag agent-tag--mock">MOCK</span>
          <span class="agent-method">{{ m.method === 'ANY' ? '*' : m.method }}</span>
          <code class="agent-pattern">{{ m.pattern }}</code>
          <span class="agent-arrow">&rarr;</span>
          <span class="agent-status">{{ m.status }}</span>
        </div>
        <div v-for="(r, i) in rewrites" :key="`r${i}`" class="agent-rule">
          <span class="agent-tag agent-tag--rewrite">REWRITE</span>
          <code class="agent-pattern">{{ r.pattern }}</code>
          <span class="agent-arrow">&rarr;</span>
          <code class="agent-pattern">{{ r.target }}</code>
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

.agent-rules {
  padding: 2px 10px 7px 25px;
  display: flex;
  flex-direction: column;
  gap: 3px;
  max-height: 132px;
  overflow-y: auto;
}

.agent-rule {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 10px;
  min-width: 0;
}

.agent-tag {
  font-size: 8px;
  font-weight: 700;
  letter-spacing: 0.4px;
  padding: 1px 4px;
  border-radius: 3px;
  flex-shrink: 0;
}

.agent-tag--mock {
  background: var(--warning);
  color: #1a1b1c;
}

.agent-tag--rewrite {
  background: var(--accent);
  color: #ffffff;
}

.agent-method {
  color: var(--fg-muted);
  font-family: var(--font-mono, monospace);
  flex-shrink: 0;
  min-width: 30px;
}

.agent-pattern {
  font-family: var(--font-mono, monospace);
  color: var(--fg-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.agent-arrow {
  color: var(--fg-muted);
  flex-shrink: 0;
}

.agent-status {
  font-family: var(--font-mono, monospace);
  color: var(--warning);
  font-weight: 600;
  flex-shrink: 0;
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
