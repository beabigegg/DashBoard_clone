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

let errors = 0;
let warnings = 0;
let hexErrors = 0;
let hexExceptionWarnings = 0;
let spacingWarnings = 0;

// Valid CSS hex only (3/4/6/8 digits). Excludes HTML entities like &#10003; via negative lookbehind.
const HEX_COLOR_RE = /(?<!&)#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})\b/;
const SPACING_PX_RE = /(margin|padding)\s*:\s*[^;]*-?\d+px\b/;
const CHART_IMPORT_RE = /(vue-echarts|from\s+['"]echarts(?:\/[^'"]+)?['"]|import\s+\*\s+as\s+echarts\s+from\s+['"]echarts(?:\/[^'"]+)?['"])/;

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

function checkCssFile(full) {
  if (isExemptCss(full)) return;

  const rel = relPath(full);
  const content = readFileSync(full, 'utf8');
  const lines = content.split('\n');

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
  });
}

// ── Vue template checks ──────────────────────────────────────────────────────

function checkVueFile(full) {
  const rel = relPath(full);
  const content = readFileSync(full, 'utf8');
  const hasChartImport = CHART_IMPORT_RE.test(content);

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

if (errors > 0) {
  console.error('\nFAIL: Fix errors above before merging.');
  process.exit(1);
} else if (warnings > 0) {
  console.warn('\nPASS with warnings. Review warnings for future migration.');
} else {
  console.log('\nPASS: All governance rules satisfied.');
}
