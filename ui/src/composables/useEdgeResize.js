import { ref, computed } from 'vue'

/**
 * Adds resizable behaviour (all 8 edges/corners) to a modal element.
 *
 * Usage:
 *   const modalRef = ref(null)
 *   const { modalStyle, startResize } = useEdgeResize(modalRef, { minW: 600, minH: 420 })
 *
 * In the template:
 *   <div ref="modalRef" class="pm-split-modal" :style="modalStyle">
 *     <span class="resize-edge resize-n"  @mousedown.prevent.stop="startResize('n',  $event)"></span>
 *     <span class="resize-edge resize-ne" @mousedown.prevent.stop="startResize('ne', $event)"></span>
 *     <span class="resize-edge resize-e"  @mousedown.prevent.stop="startResize('e',  $event)"></span>
 *     <span class="resize-edge resize-se" @mousedown.prevent.stop="startResize('se', $event)"></span>
 *     <span class="resize-edge resize-s"  @mousedown.prevent.stop="startResize('s',  $event)"></span>
 *     <span class="resize-edge resize-sw" @mousedown.prevent.stop="startResize('sw', $event)"></span>
 *     <span class="resize-edge resize-w"  @mousedown.prevent.stop="startResize('w',  $event)"></span>
 *     <span class="resize-edge resize-nw" @mousedown.prevent.stop="startResize('nw', $event)"></span>
 *     ...modal content...
 *   </div>
 *
 * Add these shared styles (scoped or global):
 *   .resize-edge { position: absolute; z-index: 10; }
 *   .resize-n,  .resize-s  { left: 6px; right: 6px; height: 6px; cursor: ns-resize; }
 *   .resize-e,  .resize-w  { top: 6px; bottom: 6px; width: 6px; cursor: ew-resize; }
 *   .resize-n  { top: 0; }
 *   .resize-s  { bottom: 0; }
 *   .resize-e  { right: 0; }
 *   .resize-w  { left: 0; }
 *   .resize-ne, .resize-nw, .resize-se, .resize-sw { width: 12px; height: 12px; cursor: ...; }
 *   .resize-ne { top: 0; right: 0; cursor: nesw-resize; }
 *   .resize-nw { top: 0; left: 0; cursor: nwse-resize; }
 *   .resize-se { bottom: 0; right: 0; cursor: nwse-resize; }
 *   .resize-sw { bottom: 0; left: 0; cursor: nesw-resize; }
 */
export function useEdgeResize(elRef, { minW = 400, minH = 300 } = {}) {
  const width = ref(null)
  const height = ref(null)

  const modalStyle = computed(() => ({
    ...(width.value != null ? { width: width.value + 'px' } : {}),
    ...(height.value != null ? { height: height.value + 'px' } : {}),
  }))

  const startResize = (dir, e) => {
    e.preventDefault()
    e.stopPropagation()
    const startX = e.clientX
    const startY = e.clientY
    const rect = elRef.value.getBoundingClientRect()
    const startW = rect.width
    const startH = rect.height
    width.value = startW
    height.value = startH

    const onMove = (e) => {
      const dx = e.clientX - startX
      const dy = e.clientY - startY
      if (dir.includes('e')) width.value  = Math.max(minW, startW + dx)
      if (dir.includes('w')) width.value  = Math.max(minW, startW - dx)
      if (dir.includes('s')) height.value = Math.max(minH, startH + dy)
      if (dir.includes('n')) height.value = Math.max(minH, startH - dy)
    }

    const onUp = () => {
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup', onUp)
    }

    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onUp)
  }

  return { modalStyle, startResize }
}
