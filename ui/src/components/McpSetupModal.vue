<script setup>
import { ref, computed } from 'vue'
import { showMcpSetupModal, agentConnected, agentClients, mcpCommand, platform } from '../store.js'

// Which editor's config to show. Claude Code first: it's a one-liner, so it's
// the path most people should take.
const client = ref('claude-code')

const CLIENTS = [
  { id: 'claude-code', label: 'Claude Code' },
  { id: 'desktop',     label: 'Claude Desktop' },
  { id: 'cursor',      label: 'Cursor' },
  { id: 'zed',         label: 'Zed' },
]

// The MCP server ships inside the app. On every start the backend writes a
// small launcher to ~/.openproxy/bin that runs the currently installed build,
// and reports its absolute path in SYSTEM_INFO. That path is what people
// register: it survives updates, moved installs, and AppImage remounts, so a
// config written once keeps working. Absolute on purpose — desktop agents
// start with the system PATH, not the shell's.
const isWin = computed(() => (platform.value || navigator.platform).toLowerCase().startsWith('win'))
const fallbackBin = computed(() => isWin.value
  ? '%USERPROFILE%\\.openproxy\\bin\\openproxy-mcp.cmd'
  : '~/.openproxy/bin/openproxy-mcp')
const BIN = computed(() => mcpCommand.value || fallbackBin.value)
const haveRealPath = computed(() => !!mcpCommand.value)

const snippets = computed(() => ({
  'claude-code': `claude mcp add openproxy --scope user -- "${BIN.value}"`,
  'desktop': JSON.stringify({
    mcpServers: { openproxy: { command: BIN.value } }
  }, null, 2),
  'cursor': JSON.stringify({
    mcpServers: { openproxy: { command: BIN.value } }
  }, null, 2),
  'zed': JSON.stringify({
    context_servers: { openproxy: { command: { path: BIN.value, args: [] } } }
  }, null, 2),
}))

const CONFIG_HINT = {
  'claude-code': '`--scope user` makes it available in every project. Use `--scope project` to write a .mcp.json the whole team picks up.',
  'desktop': 'Add to claude_desktop_config.json, then fully quit and reopen Claude Desktop.',
  'cursor': 'Add to ~/.cursor/mcp.json (global) or .cursor/mcp.json in the project.',
  'zed': 'Add to Zed settings.json under context_servers.',
}

const copiedKey = ref(null)
const copyFailedKey = ref(null)
const copy = async (text, key) => {
  try {
    await navigator.clipboard.writeText(text)
    copiedKey.value = key
    setTimeout(() => { if (copiedKey.value === key) copiedKey.value = null }, 1600)
  } catch {
    // Clipboard access can be denied; say so instead of pretending it worked.
    copyFailedKey.value = key
    setTimeout(() => { if (copyFailedKey.value === key) copyFailedKey.value = null }, 2000)
  }
}
const copyLabel = (key) => copiedKey.value === key ? 'Copied'
  : copyFailedKey.value === key ? 'Copy failed' : 'Copy'

const clientLabel = computed(() => {
  const names = agentClients.value
  if (!names.length) return null
  return names.length === 1 ? names[0] : `${names.length} agents`
})

// Keep in step with mcp-server/README.md.
const TOOLS = [
  ['get_proxy_status',       'Is OpenProxy running, on which port, with which scenario active'],
  ['list_requests',          'Captured requests as compact summaries (filter by URL / method / status / watermark)'],
  ['get_request',            'One flow in full — headers and bodies'],
  ['get_requests',           'Up to 20 flows in full, in one call'],
  ['search_requests',        'Find flows containing a string anywhere: URL, headers, bodies, WebSocket frames'],
  ['summarize_traffic',      'Counts by host / status / method, top endpoints, latency for a window of traffic'],
  ['get_websocket_messages', 'Frames exchanged over a captured WebSocket connection'],
  ['run_mock_scenario',      'Install a named set of mocks (with optional latency and response sequences); returns a watermark'],
  ['clear_mocks',            'Remove the active scenario'],
  ['wait_for_requests',      'Block until N matching requests complete — the assertion primitive'],
  ['replay_request',         'Re-send a captured request, optionally modified; returns the resulting flow'],
  ['send_request',           'Send a request composed from scratch through the proxy; returns the resulting flow'],
  ['clear_history',          'Drop captured history between scenarios'],
]
</script>

<template>
  <Teleport to="body">
    <div v-if="showMcpSetupModal" class="modal-overlay" @mousedown.self="showMcpSetupModal = false">
      <div class="mcp-modal">

        <div class="mcp-header">
          <strong class="mcp-title">Connect an AI agent (MCP)</strong>
          <button class="mcp-close" @click="showMcpSetupModal = false" aria-label="Close">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round">
              <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
            </svg>
          </button>
        </div>

        <div class="mcp-body">

          <!-- Live state first: the most common question when following these
               steps is "did it actually work", and the answer is right here. -->
          <div class="mcp-status" :class="agentConnected ? 'mcp-status--on' : 'mcp-status--off'">
            <span class="mcp-dot" aria-hidden="true"></span>
            <span v-if="agentConnected">
              <strong>{{ clientLabel }}</strong> is connected right now.
            </span>
            <span v-else>
              No agent connected yet. This panel updates the moment one attaches.
            </span>
          </div>

          <p class="mcp-intro">
            An agent can already <code>curl</code> an endpoint it controls. What it can't do is see
            what a <strong>mobile or native app</strong> actually sent. The MCP server bridges that:
            it gives the agent read access to captured traffic, plus the ability to mock an endpoint
            and watch how the client reacts.
          </p>

          <!-- Step 1 -->
          <div class="mcp-step">
            <div class="mcp-step-head"><span class="mcp-num">1</span> Nothing to install</div>
            <p class="mcp-note">
              The MCP server is part of OpenProxy. Each time the app starts it refreshes a small
              launcher that runs the installed build, so the path below keeps working after
              updates and if you move the app:
            </p>
            <div class="mcp-code">
              <pre>{{ BIN }}</pre>
              <button class="mcp-copy" @click="copy(BIN, 'path')">
                {{ copyLabel('path') }}
              </button>
            </div>
            <p v-if="!haveRealPath" class="mcp-note mcp-note--sub">
              Waiting for the backend to report the launcher's location — the path above is where it
              normally lives. If it never appears, the app couldn't write to that folder; check the
              backend log for a line starting with <code>[MCP]</code>.
            </p>
          </div>

          <!-- Step 2 -->
          <div class="mcp-step">
            <div class="mcp-step-head"><span class="mcp-num">2</span> Register it with your agent</div>

            <div class="mcp-tabs">
              <button v-for="c in CLIENTS" :key="c.id"
                      class="mcp-tab" :class="{ active: client === c.id }"
                      @click="client = c.id">{{ c.label }}</button>
            </div>

            <div class="mcp-code">
              <pre>{{ snippets[client] }}</pre>
              <button class="mcp-copy" @click="copy(snippets[client], 'cfg')">
                {{ copyLabel('cfg') }}
              </button>
            </div>

            <p class="mcp-note mcp-note--sub">{{ CONFIG_HINT[client] }}</p>

            <div class="mcp-warn">
              <strong>Register once, keep updating.</strong> The launcher path never changes, and the
              server it starts is always the one inside the currently installed OpenProxy. If an
              agent's MCP process was running while OpenProxy updated, restart that agent so it picks
              up the new build; the tools tell you when the two are out of step.
            </div>
          </div>

          <!-- Step 3 -->
          <div class="mcp-step">
            <div class="mcp-step-head"><span class="mcp-num">3</span> Check it</div>
            <p class="mcp-note">
              Keep OpenProxy running — the agent reaches it over a local WebSocket, and the tools
              fail while the app is closed. Then ask your agent to call
              <code>get_proxy_status</code>, or run:
            </p>
            <div class="mcp-code">
              <pre>claude mcp list</pre>
              <button class="mcp-copy" @click="copy('claude mcp list', 'verify')">
                {{ copyLabel('verify') }}
              </button>
            </div>
            <p class="mcp-note mcp-note--sub">
              &ldquo;Connected&rdquo; there only means the MCP server started. The connection to
              OpenProxy is opened lazily on the first tool call, so
              <code>get_proxy_status</code> is the real check. Developers running from a checkout
              get the same launcher, pointed at the repo venv.
            </p>
          </div>

          <!-- Reference -->
          <div class="mcp-step">
            <div class="mcp-step-head"><span class="mcp-num">&#9679;</span> What the agent can do</div>
            <table class="mcp-tools">
              <tr v-for="[name, desc] in TOOLS" :key="name">
                <td><code>{{ name }}</code></td>
                <td>{{ desc }}</td>
              </tr>
            </table>
          </div>

          <div class="mcp-step">
            <div class="mcp-step-head"><span class="mcp-num">&#9679;</span> Worth knowing</div>
            <ul class="mcp-list">
              <li><strong>Agent rules never touch yours.</strong> Mocks an agent installs are kept in a
                  separate list, matched ahead of your own, and shown tagged <span class="mcp-inline-tag">MCP</span>
                  in the Map Local and Map Remote windows. Clearing them restores your setup exactly.</li>
              <li><strong>Scenarios replace each other wholesale</strong>, so rules never leak from one
                  test into the next.</li>
              <li><strong>Mocks clear automatically if the agent disconnects</strong>, so a crash can't
                  strand you with silently mocked traffic. Its rules are copied into your own lists,
                  switched off, so the work isn't lost.</li>
              <li><strong>Your edits to an agent's rule stick.</strong> Change a mock in Map Local and
                  your values are re-applied every time the agent reinstalls that scenario. Use
                  &ldquo;Revert&rdquo; to hand it back.</li>
              <li><strong>Requests an agent sends itself</strong> (via <code>send_request</code> or
                  <code>replay_request</code>) show a paper-plane icon in the traffic table, and
                  responses it mocked show a robot icon.</li>
              <li><strong>There's no authentication</strong> on the local WebSocket — localhost-only
                  binding is the whole security model. Any local process could already drive it.</li>
            </ul>
          </div>

        </div>

        <div class="mcp-footer">
          <button class="mcp-btn" @click="showMcpSetupModal = false">Done</button>
        </div>

      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.modal-overlay { position: fixed; inset: 0; background: var(--overlay); z-index: 99999; display: flex; justify-content: center; align-items: center; }
.mcp-modal { background: var(--bg-main); border-radius: 10px; border: 1px solid var(--border); width: 680px; max-width: calc(100vw - 20px); height: 680px; max-height: calc(100vh - 40px); display: flex; flex-direction: column; box-shadow: var(--shadow-lg); overflow: hidden; }

.mcp-header { display: flex; justify-content: space-between; align-items: center; padding: 0 16px; height: 44px; background: var(--bg-sidebar); border-bottom: 1px solid var(--border); flex-shrink: 0; }
.mcp-title { font-size: 13px; font-weight: 600; color: var(--fg-primary); }
.mcp-close { background: none; border: none; cursor: pointer; color: var(--fg-muted); padding: 4px; border-radius: 4px; display: flex; align-items: center; }
.mcp-close:hover { background: var(--surface-hover-strong); color: var(--fg-primary); }

.mcp-body { flex: 1; overflow-y: auto; padding: 16px; display: flex; flex-direction: column; gap: 16px; }

.mcp-status { display: flex; align-items: center; gap: 8px; padding: 8px 12px; border-radius: 6px; font-size: 12px; border: 1px solid var(--border); }
.mcp-status--on { background: var(--success-muted); border-color: var(--success); color: var(--fg-primary); }
.mcp-status--off { background: var(--bg-card); color: var(--fg-muted); }
.mcp-dot { width: 7px; height: 7px; border-radius: 50%; background: var(--fg-muted); flex-shrink: 0; }
.mcp-status--on .mcp-dot { background: var(--success); }

.mcp-intro { font-size: 12px; line-height: 1.6; color: var(--fg-secondary); margin: 0; }

.mcp-step { display: flex; flex-direction: column; gap: 8px; }
.mcp-step-head { display: flex; align-items: center; gap: 8px; font-size: 12px; font-weight: 600; color: var(--fg-primary); }
.mcp-num { display: inline-flex; align-items: center; justify-content: center; width: 18px; height: 18px; border-radius: 50%; background: var(--accent-muted); color: var(--accent); font-size: 10px; font-weight: 700; flex-shrink: 0; }

.mcp-note { font-size: 11.5px; line-height: 1.6; color: var(--fg-secondary); margin: 0; }
.mcp-note--sub { color: var(--fg-muted); font-size: 11px; }
.mcp-note code, .mcp-intro code, .mcp-warn code, .mcp-list code { font-family: 'Consolas', monospace; background: var(--bg-deepest); padding: 1px 4px; border-radius: 3px; font-size: 10.5px; }

.mcp-code { position: relative; background: var(--bg-deepest); border: 1px solid var(--border); border-radius: 6px; }
.mcp-code pre { margin: 0; padding: 10px 62px 10px 12px; font-family: 'Consolas', monospace; font-size: 11px; line-height: 1.55; color: var(--fg-primary); white-space: pre; overflow-x: auto; }
.mcp-copy { position: absolute; top: 6px; right: 6px; font-size: 10px; font-family: inherit; padding: 2px 8px; border-radius: 4px; background: var(--bg-card); border: 1px solid var(--border); color: var(--fg-secondary); cursor: pointer; }
.mcp-copy:hover { background: var(--surface-hover-strong); color: var(--fg-primary); }

.mcp-tabs { display: flex; gap: 4px; flex-wrap: wrap; }
.mcp-tab { font-size: 11px; font-family: inherit; padding: 3px 10px; border-radius: 5px; background: transparent; border: 1px solid var(--border); color: var(--fg-muted); cursor: pointer; }
.mcp-tab:hover { background: var(--bg-active); color: var(--fg-primary); }
.mcp-tab.active { background: var(--accent-muted); border-color: var(--accent-border); color: var(--accent); font-weight: 600; }

.mcp-warn { font-size: 11px; line-height: 1.6; color: var(--fg-secondary); background: var(--warning-muted); border: 1px solid var(--warning); border-radius: 6px; padding: 8px 12px; }

.mcp-tools { width: 100%; border-collapse: collapse; font-size: 11px; }
.mcp-tools td { padding: 4px 8px 4px 0; vertical-align: top; color: var(--fg-secondary); border-bottom: 1px solid var(--border-subtle); line-height: 1.5; }
.mcp-tools td:first-child { width: 150px; white-space: nowrap; }
.mcp-tools code { font-family: 'Consolas', monospace; color: var(--accent); font-size: 10.5px; }

.mcp-list { margin: 0; padding-left: 18px; display: flex; flex-direction: column; gap: 6px; font-size: 11.5px; line-height: 1.6; color: var(--fg-secondary); }
.mcp-inline-tag { font-size: 8px; font-weight: 700; letter-spacing: 0.4px; padding: 1px 4px; border-radius: 3px; background: var(--warning); color: #1a1b1c; }

.mcp-footer { display: flex; justify-content: flex-end; padding: 12px 16px; background: var(--bg-sidebar); border-top: 1px solid var(--border); flex-shrink: 0; }
.mcp-btn { background: var(--accent); color: #fff; border: none; border-radius: 6px; padding: 6px 24px; font-weight: 500; font-size: 12px; cursor: pointer; }
.mcp-btn:hover { background: var(--accent-hover); }
</style>
