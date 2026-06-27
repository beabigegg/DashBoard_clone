#!/usr/bin/env node
/**
 * CSS Governance Check
 * Enforces rules from contract/css_development_contract.md:
 * 1. Route-local CSS must NOT define :root tokens (use .theme-X or tailwind.config.js)
 * 2. Route-local CSS must NOT define body/html/* rules
 * 3. Vue templates must NOT have static style="..." attributes
 * 4. Hardcoded HEX colors are forbidden except chart-library exception context
 * 5. margin/padding with px is tracked as migration warning
 *
 * Usage: node scripts/css-governance-check.js
 * Exit code: 0 = pass, 1 = fail
 */

import { readFileSync, readdirSync, statSync } from 'fs';
import { join, relative } from 'path';
import { fileURLToPath } from 'url';
import { dirname } from 'path';

const __dirname = dirname(fileURLToPath(import.meta.url));
const SRC_DIR = join(__dirname, '..', 'src');

// Files/paths exempt from checks
const EXEMPT_CSS = new Set([
  'styles/tailwind.css',    // global base — allowed
  'portal-shell/style.css', // shell layer — allowed
  'portal/portal.css',      // portal entry — allowed
]);

// Files that contain ECharts hex colors by design (chart-exception context).
// These are tracked as warnings, not errors, by the chart-import heuristic.
// Listed explicitly for governance documentation.
const CHART_HEX_ALLOWED = new Set([
  'wip-shared/components/ParetoSection.vue',
  'reject-history/components/ParetoSection.vue',
  'shared-ui/components/AiChartRenderer.vue',
]);

let errors = 0;
let warnings = 0;
let hexErrors = 0;
let hexExceptionWarnings = 0;
let spacingWarnings = 0;
let scopeErrors = 0;
let dropdownScopeErrors = 0;

// Valid CSS hex only (3/4/6/8 digits). Excludes HTML entities like &#10003; via negative lookbehind.
const HEX_COLOR_RE = /(?<!&)#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})\b/;
const SPACING_PX_RE = /(margin|padding)\s*:\s*[^;]*-?\d+px\b/;
const CHART_IMPORT_RE = /(vue-echarts|from\s+['"]echarts(?:\/[^'"]+)?['"]|import\s+\*\s+as\s+echarts\s+from\s+['"]echarts(?:\/[^'"]+)?['"]|from\s+['"]d3(?:-[^'"]+)?['"])/;

// SVG/canvas chart components that legitimately use HEX for programmatic rendering
// but do not import a chart library detectable by CHART_IMPORT_RE.
const SVG_CHART_COMPONENTS = new Set([
  'shared-ui/components/TimelineChart.vue',
]);

function walk(dir, callback) {
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    const stat = statSync(full);
    if (stat.isDirectory()) {
      walk(full, callback);
    } else {
      callback(full);
    }
  }
}

function relPath(full) {
  return relative(SRC_DIR, full).replace(/\\/g, '/');
}

function isExemptCss(full) {
  const rel = relPath(full);
  return EXEMPT_CSS.has(rel);
}

function classifyHexUsage(fileType, line, hasChartImport) {
  if (!HEX_COLOR_RE.test(line)) return null;
  // Chart-library files are tracked as exception candidates by contract v1.1.
  if ((fileType === 'vue' || fileType === 'js') && hasChartImport) {
    return 'chart-exception';
  }
  return 'violation';
}

// ── CSS checks ──────────────────────────────────────────────────────────────

// Rule 6: Top-level rules in feature CSS must be scoped under .theme-<X>.
// Reason: portal-shell permanently caches every feature's CSS in <head>, so
// unscoped rules bleed across pages. See CLAUDE.md "Portal-Shell CSS
// Architecture Notes" and contract/css_development_contract.md.
//
// Returns array of {lineNo, selector} for unscoped top-level rules.
function findUnscopedTopLevelRules(content) {
  const offences = [];
  let i = 0;
  const n = content.length;
  let depth = 0;
  // Stack of open at-rules at each depth (so we can ignore @keyframes inner rules)
  const atStack = []; // values: 'scope' | 'keyframes' | 'other'

  while (i < n) {
    const ch = content[i];
    // Skip comments
    if (ch === '/' && content[i + 1] === '*') {
      const k = content.indexOf('*/', i + 2);
      i = k === -1 ? n : k + 2;
      continue;
    }
    if (ch === '{') { depth++; i++; continue; }
    if (ch === '}') {
      depth--;
      if (atStack.length && depth === atStack.length - 1) atStack.pop();
      i++;
      continue;
    }

    // We only inspect selectors at depth 0 OR inside @media/@supports (depth 1 of a scoping at-rule).
    const isScopable = depth === 0 || (
      atStack.length && atStack[atStack.length - 1] === 'scope' && depth === atStack.length
    );
    if (!isScopable) { i++; continue; }

    // Skip whitespace + leading comments
    while (i < n) {
      if (/\s/.test(content[i])) { i++; continue; }
      if (content[i] === '/' && content[i + 1] === '*') {
        const k = content.indexOf('*/', i + 2);
        i = k === -1 ? n : k + 2;
        continue;
      }
      break;
    }
    if (i >= n) break;

    // At-rule
    if (content[i] === '@') {
      const m = content.slice(i).match(/^@([\w-]+)/);
      const name = (m ? m[1] : '').toLowerCase();
      let j = i;
      while (j < n && content[j] !== ';' && content[j] !== '{') j++;
      if (j >= n) break;
      if (content[j] === ';') { i = j + 1; continue; }
      // block at-rule
      i = j + 1;
      depth++;
      if (name === 'media' || name === 'supports' || name === 'container') {
        atStack.push('scope');
      } else if (name === 'keyframes' || name.endsWith('keyframes')) {
        atStack.push('keyframes');
      } else {
        atStack.push('other');
      }
      continue;
    }

    // Read selector group until '{'
    const selectorStart = i;
    let j = i;
    while (j < n && content[j] !== '{' && content[j] !== '}' && content[j] !== ';') {
      if (content[j] === '/' && content[j + 1] === '*') {
        const k = content.indexOf('*/', j + 2);
        j = k === -1 ? n : k + 2;
        continue;
      }
      j++;
    }
    if (j >= n || content[j] !== '{') { i = j; continue; }
    const selectorBlock = content.slice(selectorStart, j).trim();
    // Inside @keyframes, "selectors" are 0%/from/to — skip.
    const insideKeyframes = atStack.length && atStack[atStack.length - 1] === 'keyframes' && depth === atStack.length;
    if (!insideKeyframes && selectorBlock) {
      // Split on commas respecting parens
      const parts = [];
      let buf = '';
      let paren = 0;
      for (const c of selectorBlock) {
        if (c === '(') paren++;
        else if (c === ')') paren--;
        if (c === ',' && paren === 0) { parts.push(buf.trim()); buf = ''; }
        else buf += c;
      }
      parts.push(buf.trim());
      for (const p of parts) {
        if (!p) continue;
        // Allowed prefixes: .theme-*, :root, ::backdrop, or :is(.theme-...)
        if (p.startsWith('.theme-')) continue;
        if (p.startsWith(':root')) continue;
        if (p.startsWith('::backdrop')) continue;
        if (/^:is\s*\(\s*\.theme-/.test(p)) continue;
        const lineNo = content.slice(0, selectorStart).split('\n').length;
        offences.push({ lineNo, selector: p });
      }
    }
    i = j;
  }
  return offences;
}

// A feature CSS is `src/<feature>/style.css` where <feature> is a top-level
// directory under src/ (not src/, not nested deeper). Shared files like
// wip-shared/styles.css are *.css too but allowed to share themes via :is().
function isFeatureCss(full) {
  const rel = relPath(full);
  // Match exactly "<feature>/style.css" — single segment, then style.css
  return /^[^/]+\/style\.css$/.test(rel);
}

function checkCssFile(full) {
  if (isExemptCss(full)) return;

  const rel = relPath(full);
  const content = readFileSync(full, 'utf8');
  const lines = content.split('\n');

  // Rule 6: feature CSS scope leakage check
  if (isFeatureCss(full)) {
    const offences = findUnscopedTopLevelRules(content);
    for (const off of offences) {
      console.error(`[FAIL] ${rel}:${off.lineNo} — Unscoped top-level rule "${off.selector}" in feature CSS. Prefix with .theme-<feature> (portal-shell caches CSS permanently; unscoped rules bleed across pages).`);
      errors++;
      scopeErrors++;
    }
  }

  lines.forEach((line, i) => {
    const lineNo = i + 1;
    const trimmed = line.trim();

    // Rule 1: No :root token declarations in route CSS
    if (/^:root\s*\{/.test(trimmed)) {
      console.error(`[FAIL] ${rel}:${lineNo} — :root token declaration forbidden in route CSS. Move to .theme-X {} or tailwind.config.js`);
      errors++;
    }

    // Rule 2: No body/html global rules in route CSS
    if (/^(html|body)\s*[{,]/.test(trimmed) || /^html\s*,\s*body/.test(trimmed)) {
      console.error(`[FAIL] ${rel}:${lineNo} — Global body/html rule forbidden in route CSS. Move to tailwind.css @layer base`);
      errors++;
    }

    // Rule 3: No bare universal reset in route CSS (*, *::before, *::after without scope)
    if (/^\*\s*\{/.test(trimmed) && !/^\.\w/.test(content.substring(0, content.indexOf(trimmed)))) {
      // Only flag if it's a top-level * rule (not inside a selector)
      // Simple heuristic: no leading indentation
      if (!line.startsWith('  ') && !line.startsWith('\t')) {
        console.warn(`[WARN] ${rel}:${lineNo} — Top-level * reset may leak globally. Consider scoping under .theme-X`);
        warnings++;
      }
    }

    // Rule 4: No hardcoded HEX in CSS (no chart exception in pure CSS files)
    if (HEX_COLOR_RE.test(line)) {
      console.error(`[FAIL] ${rel}:${lineNo} — Hardcoded HEX color in CSS. Use theme() token.`);
      errors++;
      hexErrors++;
    }

    // Rule 5: Track margin/padding px migrations
    if (SPACING_PX_RE.test(line)) {
      console.warn(`[WARN] ${rel}:${lineNo} — margin/padding uses px. Prefer tokenized spacing (theme()/utility class).`);
      warnings++;
      spacingWarnings++;
    }

    // Rule 7: Scoped .multi-select-dropdown rules are dead code after Teleport migration.
    // MultiSelect.vue teleports the dropdown panel to <body>, so any theme-scoped
    // .multi-select-dropdown selector never matches. Styles for the dropdown panel
    // must live in MultiSelect.vue's unscoped <style> block instead.
    if (/\.multi-select-dropdown/.test(trimmed) && !trimmed.startsWith('//') && !trimmed.startsWith('*')) {
      console.error(`[FAIL] ${rel}:${lineNo} — Scoped ".multi-select-dropdown" rule is dead code. MultiSelect teleports its dropdown to <body>; style it in shared-ui/components/MultiSelect.vue's global <style> block instead.`);
      errors++;
      dropdownScopeErrors++;
    }
  });
}

// ── Vue template checks ──────────────────────────────────────────────────────

function checkVueFile(full) {
  const rel = relPath(full);
  const content = readFileSync(full, 'utf8');
  const hasChartImport = CHART_IMPORT_RE.test(content) || SVG_CHART_COMPONENTS.has(rel);

  // Extract only the template section
  const templateMatch = content.match(/<template[\s\S]*?>([\s\S]*?)<\/template>/);
  if (templateMatch) {
    const template = templateMatch[1];
    const templateOffset = content.indexOf(template);
    const staticStyleRe = /(^|[\s<])style="([^"]*)"/g;
    let match;

    while ((match = staticStyleRe.exec(template)) !== null) {
      const posInTemplate = match.index;
      const globalPos = templateOffset + posInTemplate;
      const lineNo = content.substring(0, globalPos).split('\n').length;
      const styleValue = match[2];
      console.error(`[FAIL] ${rel}:${lineNo} — Static style="${styleValue}" in Vue template. Move to class or scoped style.`);
      errors++;
    }
  }

  const lines = content.split('\n');
  lines.forEach((line, i) => {
    const lineNo = i + 1;
    const hexClassification = classifyHexUsage('vue', line, hasChartImport);
    if (hexClassification === 'chart-exception') {
      console.warn(`[WARN] ${rel}:${lineNo} — HEX in chart context (exception candidate). Keep token mapping centralized.`);
      warnings++;
      hexExceptionWarnings++;
    } else if (hexClassification === 'violation') {
      console.error(`[FAIL] ${rel}:${lineNo} — Hardcoded HEX outside chart-exception context.`);
      errors++;
      hexErrors++;
    }

    if (SPACING_PX_RE.test(line)) {
      console.warn(`[WARN] ${rel}:${lineNo} — margin/padding uses px. Prefer tokenized spacing (theme()/utility class).`);
      warnings++;
      spacingWarnings++;
    }
  });
}

function checkJsFile(full) {
  const rel = relPath(full);
  const content = readFileSync(full, 'utf8');
  const hasChartImport = CHART_IMPORT_RE.test(content);
  const lines = content.split('\n');

  lines.forEach((line, i) => {
    const lineNo = i + 1;
    const hexClassification = classifyHexUsage('js', line, hasChartImport);
    if (hexClassification === 'chart-exception') {
      console.warn(`[WARN] ${rel}:${lineNo} — HEX in chart context (exception candidate). Keep token mapping centralized.`);
      warnings++;
      hexExceptionWarnings++;
    } else if (hexClassification === 'violation') {
      console.error(`[FAIL] ${rel}:${lineNo} — Hardcoded HEX outside chart-exception context.`);
      errors++;
      hexErrors++;
    }

    if (SPACING_PX_RE.test(line)) {
      console.warn(`[WARN] ${rel}:${lineNo} — margin/padding uses px. Prefer tokenized spacing (theme()/utility class).`);
      warnings++;
      spacingWarnings++;
    }
  });
}

// ── Run ──────────────────────────────────────────────────────────────────────

walk(SRC_DIR, (full) => {
  if (full.endsWith('.css')) {
    checkCssFile(full);
  } else if (full.endsWith('.vue')) {
    checkVueFile(full);
  } else if (full.endsWith('.js')) {
    checkJsFile(full);
  }
});

console.log(`\nCSS Governance Check: ${errors} error(s), ${warnings} warning(s)`);
console.log(`- HEX violations: ${hexErrors}`);
console.log(`- HEX chart-exception candidates: ${hexExceptionWarnings}`);
console.log(`- Spacing px warnings: ${spacingWarnings}`);
console.log(`- Unscoped feature-CSS rules: ${scopeErrors}`);
console.log(`- Dead scoped .multi-select-dropdown rules: ${dropdownScopeErrors}`);

if (errors > 0) {
  console.error('\nFAIL: Fix errors above before merging.');
  process.exit(1);
} else if (warnings > 0) {
  console.warn('\nPASS with warnings. Review warnings for future migration.');
} else {
  console.log('\nPASS: All governance rules satisfied.');
}
