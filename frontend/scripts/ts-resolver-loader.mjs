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
  // Only remap relative .js imports to .ts if the .ts file exists
  if (
    specifier.endsWith('.js') &&
    (specifier.startsWith('./') || specifier.startsWith('../')) &&
    context.parentURL?.startsWith('file://')
  ) {
    const parentPath = fileURLToPath(context.parentURL);
    const parentDir = dirname(parentPath);
    const tsPath = pathResolve(parentDir, specifier.slice(0, -3) + '.ts');

    if (existsSync(tsPath)) {
      return nextResolve(pathToFileURL(tsPath).href, context);
    }
  }
  return nextResolve(specifier, context);
}
