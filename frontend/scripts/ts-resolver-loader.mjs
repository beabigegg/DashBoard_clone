/**
 * Node.js ESM loader hook: resolves `.js` imports to `.ts` files when the
 * `.ts` file exists.  Used by `npm run test:legacy` so that Node's native
 * test runner can import from `src/core/*.ts` files while test files continue
 * to use the original `.js` import paths (unchanged per migration spec).
 *
 * Usage: node --experimental-loader ./scripts/ts-resolver-loader.mjs <file>
 *
 * Combined with --experimental-strip-types to transpile TypeScript syntax.
 */

import { existsSync } from 'node:fs';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { resolve as pathResolve, dirname } from 'node:path';

export async function resolve(specifier, context, nextResolve) {
  if (
    (specifier.startsWith('./') || specifier.startsWith('../')) &&
    context.parentURL?.startsWith('file://')
  ) {
    const parentPath = fileURLToPath(context.parentURL);
    const parentDir = dirname(parentPath);

    // Case 1: explicit `.js` specifier → swap to `.ts` if the .ts file exists.
    if (specifier.endsWith('.js')) {
      const tsPath = pathResolve(parentDir, specifier.slice(0, -3) + '.ts');
      if (existsSync(tsPath)) {
        return nextResolve(pathToFileURL(tsPath).href, context);
      }
    }

    // Case 2: extensionless specifier (TS-style) → try .ts then .js then index.
    const hasExt = /\.[a-zA-Z0-9]+$/.test(specifier);
    if (!hasExt) {
      const base = pathResolve(parentDir, specifier);
      const candidates = [
        `${base}.ts`,
        `${base}.js`,
        pathResolve(base, 'index.ts'),
        pathResolve(base, 'index.js'),
      ];
      for (const candidate of candidates) {
        if (existsSync(candidate)) {
          return nextResolve(pathToFileURL(candidate).href, context);
        }
      }
    }
  }
  return nextResolve(specifier, context);
}
