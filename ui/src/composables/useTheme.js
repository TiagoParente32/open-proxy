import { ref, computed } from 'vue'
import { EditorView } from '@codemirror/view'
import { HighlightStyle, syntaxHighlighting } from '@codemirror/language'
import { tags as t } from '@lezer/highlight'
import darkTheme from '../themes/dark.json'
import midnightTheme from '../themes/midnight.json'
import oceanTheme from '../themes/ocean.json'
import lightTheme from '../themes/light.json'
import crimsonTheme from '../themes/crimson.json'

const THEMES = [
  { ...darkTheme,    preview: { bg: '#1e1e1f', accent: '#3b82f6', sidebar: '#222223' } },
  { ...midnightTheme,preview: { bg: '#0d1117', accent: '#58a6ff', sidebar: '#161b22' } },
  { ...oceanTheme,   preview: { bg: '#0f2035', accent: '#06b6d4', sidebar: '#132540' } },
  { ...crimsonTheme, preview: { bg: '#1a0c10', accent: '#e11d48', sidebar: '#200f13' } },
  { ...lightTheme,   preview: { bg: '#fafafa', accent: '#3b82f6', sidebar: '#f0f0f0' } },
]

export const themes = THEMES
export const currentThemeId = ref(localStorage.getItem('openproxy-theme') || 'dark')

function resolveTheme(id) {
  const entry = THEMES.find(th => th.id === id) || THEMES[0]
  const base = { ...darkTheme.variables }
  const overrides = entry.variables
  return { ...base, ...overrides }
}

// Builds a full CodeMirror theme (chrome + syntax) from the resolved token map.
// Any theme or future plugin that overrides --syntax-* vars gets custom syntax highlighting for free.
function buildCMTheme(vars, isDark) {
  const chrome = EditorView.theme({
    '&': { backgroundColor: vars['--bg-deep'], color: vars['--fg-secondary'] },
    '.cm-content': { caretColor: vars['--accent'] },
    '.cm-cursor, .cm-dropCursor': { borderLeftColor: vars['--accent'] },
    '.cm-gutters': {
      backgroundColor: vars['--bg-input'],
      color: vars['--fg-muted'],
      border: 'none',
      borderRight: `1px solid ${vars['--border']}`,
    },
    '.cm-lineNumbers .cm-gutterElement': { minWidth: '2.5em' },
    '.cm-activeLineGutter': { backgroundColor: vars['--surface-hover-strong'] },
    '.cm-activeLine': { backgroundColor: vars['--surface-hover'] },
    '&.cm-focused .cm-selectionBackground, .cm-selectionBackground, .cm-content ::selection': {
      backgroundColor: vars['--selection-bg'],
    },
    '.cm-panels': { backgroundColor: vars['--bg-input'], color: vars['--fg-secondary'] },
    '.cm-panels.cm-panels-bottom': { borderTop: `1px solid ${vars['--border']}` },
    '.cm-searchMatch': { backgroundColor: vars['--accent-muted'], outline: `1px solid ${vars['--accent-border']}` },
    '.cm-searchMatch.cm-searchMatch-selected': { backgroundColor: vars['--selection-bg'] },
    '.cm-matchingBracket, .cm-nonmatchingBracket': { backgroundColor: vars['--surface-hover-strong'] },
    '.cm-tooltip': {
      backgroundColor: vars['--bg-modal'],
      border: `1px solid ${vars['--border']}`,
      color: vars['--fg-secondary'],
    },
    '.cm-tooltip .cm-tooltip-arrow:before': { borderTopColor: vars['--border'] },
    '.cm-tooltip .cm-tooltip-arrow:after': { borderTopColor: vars['--bg-modal'] },
  }, { dark: isDark })

  const syntax = syntaxHighlighting(HighlightStyle.define([
    { tag: [t.keyword, t.modifier],                                          color: vars['--syntax-purple'] },
    { tag: [t.function(t.variableName), t.function(t.propertyName), t.labelName], color: vars['--syntax-blue'] },
    { tag: [t.typeName, t.className, t.namespace, t.self],                   color: vars['--syntax-cyan'] },
    { tag: [t.number, t.bool, t.null],                                       color: vars['--syntax-orange'] },
    { tag: [t.string, t.inserted, t.special(t.string)],                     color: vars['--syntax-green'] },
    { tag: [t.regexp, t.escape],                                             color: vars['--syntax-cyan'] },
    { tag: [t.propertyName, t.attributeName],                                color: vars['--syntax-red'] },
    { tag: [t.operator, t.punctuation, t.separator],                         color: vars['--fg-muted'] },
    { tag: [t.comment, t.lineComment, t.blockComment, t.docComment],         color: vars['--fg-muted'], fontStyle: 'italic' },
    { tag: [t.variableName, t.definition(t.variableName)],                   color: vars['--fg-secondary'] },
    { tag: t.invalid,                                                         color: vars['--error'] },
    { tag: t.strong,  fontWeight: 'bold' },
    { tag: t.emphasis, fontStyle: 'italic' },
    { tag: t.strikethrough, textDecoration: 'line-through' },
    { tag: t.link,    color: vars['--syntax-blue'], textDecoration: 'underline' },
    { tag: t.heading, fontWeight: 'bold', color: vars['--syntax-blue'] },
  ]))

  return [chrome, syntax]
}

export function applyTheme(id) {
  const root = document.documentElement
  const resolved = resolveTheme(id)
  Object.entries(resolved).forEach(([k, v]) => root.style.setProperty(k, v))
  const themeEntry = THEMES.find(th => th.id === id) || THEMES[0]
  root.style.setProperty('color-scheme', themeEntry.dark ? 'dark' : 'light')
  currentThemeId.value = id
  localStorage.setItem('openproxy-theme', id)
  window.electronAPI?.themeChanged?.(id)
}

export function initTheme() {
  const saved = localStorage.getItem('openproxy-theme') || 'dark'
  applyTheme(saved)
  // Listen for theme changes triggered from the OS menu
  window.electronAPI?.onSetTheme?.((id) => applyTheme(id))
}

// Reactive CM extension array — rebuilds whenever the theme changes.
// Components use this directly: extensions = computed(() => [json(), ...cmTheme.value])
export const cmTheme = computed(() => {
  const entry = THEMES.find(th => th.id === currentThemeId.value) || THEMES[0]
  const resolved = resolveTheme(entry.id)
  return buildCMTheme(resolved, entry.dark !== false)
})
