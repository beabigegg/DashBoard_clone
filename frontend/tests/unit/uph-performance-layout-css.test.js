import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

import { describe, expect, it } from 'vitest';

const srcRoot = resolve(import.meta.dirname, '../../src');
const readSource = (relativePath) => readFileSync(resolve(srcRoot, relativePath), 'utf8');

describe('UPH performance layout CSS integration', () => {
  it('loads resource-shared styles in standalone and portal-shell entry paths', () => {
    const standaloneEntry = readSource('uph-performance/main.js');
    const nativeRegistry = readSource('portal-shell/nativeModuleRegistry.js');

    expect(standaloneEntry).toContain("import '../resource-shared/styles.css'");
    expect(nativeRegistry).toMatch(
      /'\/uph-performance':[\s\S]*?import\('\.\.\/resource-shared\/styles\.css'\)/,
    );
  });

  it('includes the UPH theme in every shared selector group used by EAP-style report pages', () => {
    const sharedCss = readSource('resource-shared/styles.css');
    const reportGroups = sharedCss
      .match(/:is\([^)]*\)/g)
      ?.filter((selector) => selector.includes('.theme-eap-alarm')) ?? [];

    expect(reportGroups.length).toBeGreaterThan(0);
    for (const selector of reportGroups) {
      expect(selector).toContain('.theme-uph-performance');
    }
    expect(sharedCss).toMatch(
      /\.theme-downtime-analysis,\s*\.theme-uph-performance\s*\{/,
    );
  });

  it('fills the shell width and uses the shared border token for inputs', () => {
    const pageCss = readSource('uph-performance/style.css');

    expect(pageCss).toMatch(
      /\.theme-uph-performance \.dashboard\.page-content\s*\{[^}]*width:\s*100%;[^}]*max-width:\s*none;/s,
    );
    expect(pageCss).not.toContain('max-width: 1800px');
    expect(pageCss).toContain('border: 1px solid var(--resource-border);');
    expect(pageCss).not.toContain('var(--border)');
  });
});
