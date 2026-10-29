import { ref } from 'vue'

/**
 * Search box and draggable width for the rule list in the split rule modals
 * (Map Local, Map Remote).
 *
 * Usage:
 *   const { ruleSearch, matchesSearch, sidebarWidth, startSidebarResize } =
 *     useRuleSidebar(modalRef, { storageKey: 'mapLocalSidebarWidth', fields: r => [r.label, r.pattern] })
 *
 * The width is a per-viewer layout preference, so it goes straight to
 * localStorage rather than through the store.
 */
export function useRuleSidebar(modalRef, { storageKey, fields, minW = 200, editorMinW = 320, defaultW = 280 }) {
  const fullKey = `openproxy_${storageKey}`

  const ruleSearch = ref('')
  const matchesSearch = (rule) => {
    const q = ruleSearch.value.trim().toLowerCase()
    if (!q) return true
    return fields(rule).some(v => v != null && String(v).toLowerCase().includes(q))
  }

  const sidebarWidth = ref((() => {
    try { return Number(localStorage.getItem(fullKey)) || defaultW } catch { return defaultW }
  })())

  const startSidebarResize = (e) => {
    const startX = e.clientX
    const startW = sidebarWidth.value
    const maxW = (modalRef.value?.getBoundingClientRect().width ?? 1000) - editorMinW
    document.body.style.cursor = 'col-resize'

    const onMove = (ev) => {
      sidebarWidth.value = Math.min(maxW, Math.max(minW, startW + ev.clientX - startX))
    }
    const onUp = () => {
      document.body.style.cursor = ''
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup', onUp)
      try { localStorage.setItem(fullKey, String(sidebarWidth.value)) } catch {}
    }
    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onUp)
  }

  return { ruleSearch, matchesSearch, sidebarWidth, startSidebarResize }
}
