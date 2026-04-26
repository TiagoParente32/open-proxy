import { createApp } from 'vue'
import './style.css'
import App from './App.vue'

// Disable macOS autocorrect/spellcheck/autocapitalize on all inputs and textareas
const disableAutocorrect = (el) => {
  el.setAttribute('spellcheck', 'false')
  el.setAttribute('autocorrect', 'off')
  el.setAttribute('autocapitalize', 'off')
  el.setAttribute('autocomplete', 'off')
}
const applyToInputs = (root) =>
  root.querySelectorAll('input, textarea').forEach(disableAutocorrect)

applyToInputs(document)
new MutationObserver((mutations) => {
  for (const m of mutations) {
    for (const node of m.addedNodes) {
      if (node.nodeType !== 1) continue
      if (node.matches?.('input, textarea')) disableAutocorrect(node)
      else applyToInputs(node)
    }
  }
}).observe(document.body, { childList: true, subtree: true })

createApp(App).mount('#app')
