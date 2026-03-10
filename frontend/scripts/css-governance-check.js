#!/usr/bin/env node
/**
 * CSS Governance Check
 * Enforces rules from contract/css_development_contract.md:
 * 1. Route-local CSS must NOT define :root tokens (use .theme-X or tailwind.config.js)
 * 2. Route-local CSS must NOT define body/html/* rules
 * 3. Vue templates must NOT have static style="..." attributes
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
  });
}

// ── Vue template checks ──────────────────────────────────────────────────────

function checkVueFile(full) {
  const rel = relPath(full);
  const content = readFileSync(full, 'utf8');

  // Extract only the template section
  const templateMatch = content.match(/<template[\s\S]*?>([\s\S]*?)<\/template>/);
  if (!templateMatch) return;

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

// ── Run ──────────────────────────────────────────────────────────────────────

walk(SRC_DIR, (full) => {
  if (full.endsWith('.css')) {
    checkCssFile(full);
  } else if (full.endsWith('.vue')) {
    checkVueFile(full);
  }
});

console.log(`\nCSS Governance Check: ${errors} error(s), ${warnings} warning(s)`);

if (errors > 0) {
  console.error('\nFAIL: Fix errors above before merging.');
  process.exit(1);
} else if (warnings > 0) {
  console.warn('\nPASS with warnings. Review warnings for future migration.');
} else {
  console.log('\nPASS: All governance rules satisfied.');
}
