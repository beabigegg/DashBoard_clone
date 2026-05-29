/// <reference types="node" />
import { describe, it, expect } from 'vitest';
import { readFileSync } from 'fs';
import { fileURLToPath } from 'url';
import { dirname, join } from 'path';

// ESM-compatible __dirname replacement for vitest
const __filename_local = fileURLToPath(import.meta.url);
const __dirname_local = dirname(__filename_local);
const CSS_FILE = join(__dirname_local, '..', 'style.css');

/**
 * CSS scope test — verifies that all top-level rules in style.css are prefixed
 * with .theme-downtime-analysis.
 *
 * Rule: portal-shell permanently caches each feature's CSS in <head>.
 * Unscoped rules bleed into all subsequent pages. Enforced by npm run css:check Rule 6.
 */
function findUnscopedTopLevelRules(content: string): Array<{ lineNo: number; selector: string }> {
  const offences: Array<{ lineNo: number; selector: string }> = [];
  let i = 0;
  const n = content.length;
  let depth = 0;
  const atStack: Array<'scope' | 'keyframes' | 'other'> = [];

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
      i++; continue;
    }

    const isScopable = depth === 0 || (
      atStack.length > 0 && atStack[atStack.length - 1] === 'scope' && depth === atStack.length
    );
    if (!isScopable) { i++; continue; }

    // Skip whitespace
    while (i < n && /\s/.test(content[i])) i++;
    // Skip comments
    if (content[i] === '/' && content[i + 1] === '*') {
      const k = content.indexOf('*/', i + 2);
      i = k === -1 ? n : k + 2;
      continue;
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

    // Read selector
    const selectorStart = i;
    let j = i;
    while (j < n && content[j] !== '{' && content[j] !== '}' && content[j] !== ';') {
      if (content[j] === '/' && content[j + 1] === '*') {
        const k = content.indexOf('*/', j + 2);
        j = k === -1 ? n : k + 2; continue;
      }
      j++;
    }
    if (j >= n || content[j] !== '{') { i = j; continue; }

    const selectorBlock = content.slice(selectorStart, j).trim();
    const insideKeyframes = atStack.length > 0 && atStack[atStack.length - 1] === 'keyframes' && depth === atStack.length;

    if (!insideKeyframes && selectorBlock) {
      const parts: string[] = [];
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

describe('downtime-analysis/style.css CSS scope (Rule 6)', () => {
  let cssContent: string;

  try {
    cssContent = readFileSync(CSS_FILE, 'utf8');
  } catch {
    cssContent = '';
  }

  it('style.css file exists and is non-empty', () => {
    expect(cssContent.length).toBeGreaterThan(0);
  });

  it('all top-level rules are prefixed with .theme-downtime-analysis', () => {
    const offences = findUnscopedTopLevelRules(cssContent);
    if (offences.length > 0) {
      const messages = offences.map(
        (o) => `  Line ${o.lineNo}: selector "${o.selector}" is not scoped under .theme-downtime-analysis`,
      );
      throw new Error(
        `Found ${offences.length} unscoped top-level rule(s) in style.css:\n${messages.join('\n')}`,
      );
    }
    expect(offences).toHaveLength(0);
  });

  it('contains .theme-downtime-analysis rules (sanity check)', () => {
    expect(cssContent).toContain('.theme-downtime-analysis');
  });
});
