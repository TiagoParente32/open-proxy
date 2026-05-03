<script setup>
import { computed, ref, watch } from 'vue'
import { 
  showHighlightModal, 
  highlightRules, 
  highlightsEnabled,
  importRules, 
  exportRules,
} from '../store.js'

const selectedRuleId = ref(null)

const activeRule = computed(() => highlightRules.value.find(r => r.id === selectedRuleId.value))

watch(highlightRules, (newRules) => {
  if (newRules.length > 0 && !newRules.find(r => r.id === selectedRuleId.value)) {
    selectedRuleId.value = newRules[0].id
  }
}, { immediate: true, deep: true })

const showTypeMenu = ref(false)
const typeGroups = [
  {
    label: 'URL',
    options: [
      { value: 'url',       label: 'URL Contains' },
      { value: 'url_regex', label: 'URL Regex' },
    ]
  },
  {
    label: 'Status & Method',
    options: [
      { value: 'status',       label: 'Status Code' },
      { value: 'status_range', label: 'Status Range (e.g. 4xx)' },
      { value: 'method',       label: 'HTTP Method' },
    ]
  },
  {
    label: 'Headers',
    options: [
      { value: 'req_header', label: 'Request Header' },
      { value: 'res_header', label: 'Response Header' },
    ]
  },
  {
    label: 'Body',
    options: [
      { value: 'req_body', label: 'Request Body' },
      { value: 'res_body', label: 'Response Body' },
    ]
  },
]

const allTypeOptions = typeGroups.flatMap(g => g.options)

const getTypeLabel = (val) => allTypeOptions.find(o => o.value === val)?.label ?? 'Select Condition'

const selectType = (val) => {
  if (activeRule.value) activeRule.value.type = val
  showTypeMenu.value = false
}

const COLORS = ['red', 'orange', 'yellow', 'green', 'blue', 'purple']

const addNewRule = () => {
  const newRule = { id: Date.now(), active: true, name: '', type: 'url', pattern: '', color: 'blue' }
  highlightRules.value.unshift(newRule)
  selectedRuleId.value = newRule.id
}

const duplicateRule = (rule) => {
  const copy = { ...rule, id: Date.now(), name: rule.name ? `${rule.name} (copy)` : '' }
  const idx = highlightRules.value.findIndex(r => r.id === rule.id)
  highlightRules.value.splice(idx + 1, 0, copy)
  selectedRuleId.value = copy.id
}

const deleteRule = (id) => {
  highlightRules.value = highlightRules.value.filter(r => r.id !== id)
  if (selectedRuleId.value === id) {
    selectedRuleId.value = highlightRules.value.length ? highlightRules.value[0].id : null
  }
}
</script>

<template>
  <Teleport to="body">
    <div v-if="showHighlightModal" class="modal-overlay" @mousedown.self="showHighlightModal = false">
      
      <div class="pm-split-modal">
        
        <!-- Sidebar -->
        <div class="pm-sidebar">
          
          <div class="pm-sidebar-header">
            <strong style="color: var(--fg-secondary); font-size: 13px;">Highlight Rules</strong>
            <button class="pm-add-btn" @click="addNewRule">+ Add</button>
          </div>

          <div class="pm-rule-list">
            <div v-for="rule in highlightRules" :key="rule.id" 
                 class="pm-rule-item" 
                 :class="{ active: selectedRuleId === rule.id, disabled: !rule.active }" 
                 :style="{ borderLeft: `3px solid var(--color-${rule.color})` }"
                 @click="selectedRuleId = rule.id">
              
              <label class="pm-checkbox-container" @click.stop>
                <input type="checkbox" v-model="rule.active" />
                <span class="pm-checkmark"></span>
              </label>

              <div class="pm-rule-text-stack">
                <span class="pm-rule-name" :title="rule.name || rule.pattern">
                  {{ rule.name || rule.pattern || 'Untitled Rule' }}
                </span>
                <span class="pm-rule-target">{{ getTypeLabel(rule.type) }}
                  <span v-if="rule.pattern" class="pm-rule-pattern-inline"> · {{ rule.pattern }}</span>
                </span>
              </div>

              <button class="pm-rule-action" @click.stop="duplicateRule(rule)" title="Duplicate">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
              </button>
              <button class="pm-rule-del" @click.stop="deleteRule(rule.id)" title="Delete">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
              </button>

            </div>
            
            <div v-if="highlightRules.length === 0" class="pm-empty-sidebar">
              No highlight rules yet.<br>Click <strong>+ Add</strong> to start coloring traffic.
            </div>
          </div>

          <div class="pm-sidebar-footer">
            <div class="toggle" @click="highlightsEnabled = !highlightsEnabled" :class="{ active: highlightsEnabled }">
              <span class="toggle-label">Enable Highlights</span>
              <div class="switch"></div>
            </div>
            <div class="pm-divider-horizontal"></div>
            <div style="display: flex; gap: 8px;">
              <button class="ghost-btn" style="flex: 1; justify-content: center;" @click="exportRules(highlightRules, 'OpenProxy_Highlights')">Export</button>
              <label class="ghost-btn" style="flex: 1; justify-content: center; cursor: pointer; margin: 0;">
                Import
                <input type="file" accept=".json" style="display: none;" @change="(e) => importRules(e, highlightRules)" />
              </label>
            </div>
          </div>
        </div>

        <!-- Main editor -->
        <div class="pm-main-area">
          
          <div v-if="activeRule" style="display: flex; flex-direction: column; height: 100%;">
            
            <div class="pm-header">
              <strong class="pm-title text-blue">
                {{ activeRule.name || 'Highlight Rule' }}
              </strong>
              <button class="pm-close-btn" @click="showHighlightModal = false">✕</button>
            </div>

            <div class="pm-editor-area">

              <!-- Rule name -->
              <div class="pm-field-group">
                <span class="pm-routing-label">RULE NAME <span style="color:var(--fg-placeholder); font-weight:400;">(optional)</span></span>
                <input type="text" v-model="activeRule.name" class="pm-routing-input" placeholder="e.g. Flag errors, Auth calls…" />
              </div>

              <div class="pm-routing-box">
                <div class="pm-routing-header">Match Condition</div>
                <div class="pm-routing-body">
                  
                  <span class="pm-routing-label">CONDITION TYPE</span>
                  <div class="pm-custom-select-wrapper">
                    <div class="pm-custom-select-display" @click="showTypeMenu = !showTypeMenu">
                      {{ getTypeLabel(activeRule.type) }}
                      <svg class="pm-chevron" viewBox="0 0 24 24"><path d="M7 10l5 5 5-5z"/></svg>
                    </div>
                    <div v-if="showTypeMenu" class="pm-dropdown-overlay" @click.stop="showTypeMenu = false"></div>
                    <div v-if="showTypeMenu" class="pm-custom-select-dropdown">
                      <template v-for="(group, gi) in typeGroups" :key="gi">
                        <div v-if="gi > 0" class="pm-select-separator" />
                        <div class="pm-select-group-label">{{ group.label }}</div>
                        <div v-for="opt in group.options" :key="opt.value"
                             class="pm-custom-select-option"
                             :class="{ selected: activeRule.type === opt.value }"
                             @click="selectType(opt.value)">
                          {{ opt.label }}
                        </div>
                      </template>
                    </div>
                  </div>

                  <span class="pm-routing-label" style="margin-top: 8px;">MATCH VALUE</span>
                  <input type="text" v-model="activeRule.pattern" class="pm-routing-input"
                    :placeholder="activeRule.type === 'status_range' ? 'e.g. 4xx, 5xx, 2xx' : activeRule.type === 'url_regex' ? 'e.g. /api/.*' : activeRule.type === 'method' ? 'e.g. POST' : 'e.g. /api/graphql'" />
                  
                </div>
              </div>

              <div class="pm-routing-arrow">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" stroke-width="2" stroke-linecap="round">
                  <line x1="12" y1="4" x2="12" y2="20"/><polyline points="18 14 12 20 6 14"/>
                </svg>
              </div>

              <div class="pm-routing-box target">
                <div class="pm-routing-header target-header">Appearance</div>
                <div class="pm-routing-body">
                  <span class="pm-routing-label">ROW COLOR</span>
                  <div class="pm-color-picker">
                    <div v-for="c in COLORS" :key="c"
                         class="pm-color-dot" :class="[c, { active: activeRule.color === c }]"
                         @click="activeRule.color = c"
                         :title="c.charAt(0).toUpperCase() + c.slice(1)">
                    </div>
                  </div>
                </div>
              </div>

            </div>

            <div class="pm-footer">
              <button class="pm-btn-execute" @click="showHighlightModal = false">Done</button>
            </div>

          </div>
          
          <div v-else class="pm-main-empty">
            Select or create a rule to configure highlights.
          </div>

        </div>

      </div>
    </div>
  </Teleport>
</template>

<style scoped>
/* OVERLAY & MODAL */
.modal-overlay { position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: var(--overlay); z-index: 99999; display: flex; justify-content: center; align-items: center; backdrop-filter: blur(4px); }
.pm-split-modal { background: var(--bg-main); border-radius: 8px; border: 1px solid var(--border); width: 900px; height: 620px; display: flex; flex-direction: row; box-shadow: var(--shadow-lg); overflow: hidden; }

/* Color custom properties */
.pm-split-modal {
  --color-red: #ef4444;
  --color-orange: #f97316;
  --color-yellow: #f59e0b;
  --color-green: #10b981;
  --color-blue: #3b82f6;
  --color-purple: #8b5cf6;
}

/* SIDEBAR */
.pm-sidebar { width: 280px; background: var(--bg-sidebar); border-right: 1px solid var(--border); display: flex; flex-direction: column; flex-shrink: 0; }
.pm-sidebar-header { padding: 14px 16px; border-bottom: 1px solid var(--border); display: flex; justify-content: space-between; align-items: center; background: var(--bg-active); }
.pm-add-btn { background: var(--accent-muted); color: var(--accent); border: 1px solid var(--accent-border); padding: 4px 10px; border-radius: 4px; font-size: 11px; font-weight: 600; cursor: pointer; transition: all 0.2s; }
.pm-add-btn:hover { background: var(--accent); color: var(--fg-primary); border-color: var(--accent); }

/* Sidebar list */

.pm-rule-list { flex: 1; overflow-y: auto; }
.pm-rule-item { 
  min-height: 50px; padding: 0 12px 0 0;
  border-bottom: 1px solid var(--bg-main);
  display: flex; align-items: center; gap: 8px;
  cursor: pointer; transition: background 0.15s;
  box-sizing: border-box;
}
.pm-rule-item:hover { background: var(--bg-active); }
.pm-rule-item.active { background: var(--accent-muted); }
.pm-rule-item.disabled { opacity: 0.5; }

/* Checkbox */
.pm-checkbox-container { display: flex; align-items: center; justify-content: center; position: relative; cursor: pointer; user-select: none; width: 16px; height: 16px; flex-shrink: 0; margin: 0 0 0 10px; }
.pm-checkbox-container input { position: absolute; opacity: 0; cursor: pointer; height: 0; width: 0; }
.pm-checkmark { position: absolute; top: 0; left: 0; height: 16px; width: 16px; background: var(--bg-deepest); border: 1px solid var(--fg-muted); border-radius: 4px; transition: all 0.2s; box-sizing: border-box; }
.pm-checkbox-container:hover input ~ .pm-checkmark { border-color: var(--accent); }
.pm-checkbox-container input:checked ~ .pm-checkmark { background-color: var(--accent); border-color: var(--accent); }
.pm-checkmark:after { content: ""; position: absolute; display: none; }
.pm-checkbox-container input:checked ~ .pm-checkmark:after { display: block; }
.pm-checkbox-container .pm-checkmark:after { left: 50%; top: 45%; width: 4px; height: 9px; border: solid white; border-width: 0 2px 2px 0; transform: translate(-50%,-50%) rotate(45deg); }

/* Rule text */
.pm-rule-text-stack { flex: 1; display: flex; flex-direction: column; min-width: 0; justify-content: center; gap: 3px; padding: 8px 0; }
.pm-rule-name { font-size: 12px; color: var(--fg-secondary); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; line-height: 1.2; }
.pm-rule-item.active .pm-rule-name { color: var(--fg-primary); font-weight: 600; }
.pm-rule-target { font-size: 10.5px; color: var(--fg-placeholder); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.pm-rule-item.active .pm-rule-target { color: var(--fg-muted); }
.pm-rule-pattern-inline { color: var(--accent); }

/* Rule action buttons */
.pm-rule-action, .pm-rule-del {
  background: transparent; border: 1px solid transparent; color: var(--border);
  cursor: pointer; padding: 4px; border-radius: 5px;
  display: flex; align-items: center; justify-content: center;
  flex-shrink: 0; transition: all 0.15s; opacity: 0;
}
.pm-rule-item:hover .pm-rule-action,
.pm-rule-item:hover .pm-rule-del { opacity: 1; color: var(--fg-muted); }
.pm-rule-action:hover { background: var(--surface-hover); color: var(--fg-muted) !important; }
.pm-rule-del:hover { background: var(--error-muted) !important; color: var(--error) !important; }

.pm-empty-sidebar { padding: 40px 20px; text-align: center; color: var(--fg-placeholder); font-size: 12px; line-height: 1.8; }

/* Sidebar footer */
.pm-sidebar-footer { padding: 14px 16px; background: var(--bg-modal); border-top: 1px solid var(--border); display: flex; flex-direction: column; gap: 12px; }
.toggle { display: flex; align-items: center; justify-content: space-between; cursor: pointer; color: var(--fg-muted); font-weight: 600; font-size: 12px; }
.toggle.active { color: var(--success); }
.switch { width: 32px; height: 18px; background: var(--bg-input); border: 1px solid var(--border); border-radius: 14px; position: relative; }
.switch::after { content: ''; position: absolute; top: 1px; left: 1px; width: 14px; height: 14px; background: var(--fg-muted); border-radius: 50%; transition: transform 0.3s; }
.toggle.active .switch::after { transform: translateX(14px); background: var(--success); }
.pm-divider-horizontal { width: 100%; height: 1px; background: var(--border-subtle); }
.ghost-btn { display: flex; align-items: center; gap: 4px; height: 26px; padding: 0 8px; background: transparent; border: 1px solid var(--border); color: var(--fg-muted); border-radius: 4px; cursor: pointer; font-size: 11px; font-weight: 500; transition: all 0.2s; }
.ghost-btn:hover { background: var(--surface-hover-strong); color: var(--fg-primary); border-color: var(--fg-muted); }

/* MAIN AREA */
.pm-main-area { flex: 1; display: flex; flex-direction: column; background: var(--bg-main); min-width: 0; }
.pm-main-empty { flex: 1; display: flex; justify-content: center; align-items: center; color: var(--fg-placeholder); font-size: 13px; }
.pm-header { display: flex; justify-content: space-between; align-items: center; padding: 12px 20px; background: var(--bg-card); border-bottom: 1px solid var(--border); flex-shrink: 0; }
.pm-title { font-size: 13px; font-weight: 700; }
.text-blue { color: var(--accent) !important; }
.pm-close-btn { background: transparent; border: none; color: var(--fg-muted); font-size: 16px; cursor: pointer; transition: color 0.2s; }
.pm-close-btn:hover { color: var(--error); }

.pm-editor-area { flex: 1; padding: 16px 24px; display: flex; flex-direction: column; gap: 10px; overflow-y: auto; }

.pm-field-group { display: flex; flex-direction: column; gap: 5px; }

.pm-routing-box { background: var(--bg-sidebar); border: 1px solid var(--border); border-radius: 8px; overflow: visible !important; flex-shrink: 0; position: relative; }
.pm-routing-box:first-child { z-index: 10; }
.pm-routing-header { background: var(--bg-active); padding: 8px 16px; font-size: 12px; font-weight: 700; color: var(--fg-secondary); border-bottom: 1px solid var(--border); border-top-left-radius: 8px; border-top-right-radius: 8px; }
.pm-routing-header.target-header { background: var(--accent-muted); color: var(--accent); border-bottom-color: rgba(59,130,246,0.2); }
.pm-routing-box.target { border-color: var(--accent-border); }
.pm-routing-body { padding: 12px 16px; display: flex; flex-direction: column; gap: 6px; }
.pm-routing-label { font-size: 11px; font-weight: 600; color: var(--fg-muted); letter-spacing: 0.5px; }
.pm-routing-input { width: 100%; background: var(--bg-deepest); border: 1px solid var(--border); color: var(--fg-primary); padding: 9px 12px; border-radius: 6px; font-size: 13px; font-family: 'Consolas', monospace; outline: none; transition: border-color 0.2s, box-shadow 0.2s; box-sizing: border-box; }
.pm-routing-input:focus { border-color: var(--accent); box-shadow: var(--focus-ring); }

/* Custom select */
.pm-custom-select-wrapper { position: relative; width: 100%; user-select: none; }
.pm-custom-select-display { width: 100%; background: var(--bg-deepest); border: 1px solid var(--border); color: var(--fg-primary); padding: 9px 12px; border-radius: 6px; font-size: 13px; font-family: 'Consolas', monospace; display: flex; justify-content: space-between; align-items: center; cursor: pointer; transition: border-color 0.2s; box-sizing: border-box; }
.pm-custom-select-display:hover { border-color: var(--fg-muted); }
.pm-chevron { width: 16px; height: 16px; fill: currentColor; opacity: 0.6; }
.pm-dropdown-overlay { position: fixed; top: 0; left: 0; right: 0; bottom: 0; z-index: 99; cursor: default; }
.pm-custom-select-dropdown { position: absolute; top: 100%; left: 0; right: 0; margin-top: 4px; background: var(--bg-card); border: 1px solid var(--border); border-radius: 6px; box-shadow: var(--shadow-lg); z-index: 9999; padding: 4px 0; }
.pm-select-separator { height: 1px; background: var(--border); margin: 3px 0; }
.pm-select-group-label { padding: 5px 12px 2px; font-size: 10px; font-weight: 700; color: var(--fg-placeholder); letter-spacing: 0.5px; text-transform: uppercase; }
.pm-custom-select-option { padding: 8px 12px; font-size: 12.5px; color: var(--fg-secondary); cursor: pointer; transition: background 0.1s; }
.pm-custom-select-option:hover { background: var(--surface-hover-strong); color: var(--fg-primary); }
.pm-custom-select-option.selected { background: var(--accent-muted); color: var(--accent); font-weight: 600; }

.pm-routing-arrow { display: flex; justify-content: center; align-items: center; padding: 2px 0; flex-shrink: 0; }

/* Color picker — now with 6 colors */
.pm-color-picker { display: flex; gap: 12px; margin-top: 4px; padding: 4px 0; flex-wrap: wrap; }
.pm-color-dot { width: 28px; height: 28px; border-radius: 50%; cursor: pointer; border: 3px solid transparent; transition: transform 0.2s, border-color 0.2s, box-shadow 0.2s; }
.pm-color-dot:hover { transform: scale(1.1); }
.pm-color-dot.active { border-color: white; transform: scale(1.18); box-shadow: 0 0 10px rgba(255,255,255,0.2); }
.pm-color-dot.red    { background: #ef4444; }
.pm-color-dot.orange { background: #f97316; }
.pm-color-dot.yellow { background: #f59e0b; }
.pm-color-dot.green  { background: #10b981; }
.pm-color-dot.blue   { background: #3b82f6; }
.pm-color-dot.purple { background: #8b5cf6; }

.pm-footer { display: flex; justify-content: flex-end; gap: 12px; padding: 14px 20px; background: var(--bg-sidebar); border-top: 1px solid var(--border); flex-shrink: 0; }
.pm-btn-execute { background: var(--accent); color: var(--fg-primary); border: none; border-radius: 6px; padding: 8px 32px; font-weight: 600; font-size: 13px; cursor: pointer; transition: background 0.2s; }
.pm-btn-execute:hover { background: var(--accent-hover); }
</style>
