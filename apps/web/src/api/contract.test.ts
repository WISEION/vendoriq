import { readFileSync, readdirSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

/**
 * Guards the one promise the generated client makes: every path a wrapper calls is a real
 * operation in `docs/openapi.yaml`, as captured by `src/api/schema.d.ts` (`npm run
 * generate:api`). A contract change that removes or renames a path now fails `npm run test`
 * instead of shipping a 404 to production.
 */

const apiDir = dirname(fileURLToPath(import.meta.url));

const NON_WRAPPER_FILES = new Set([
  'client.ts',
  'http.ts',
  'schema.d.ts',
  'contract.test.ts',
]);

function wrapperFiles(): string[] {
  return readdirSync(apiDir).filter(
    (name) => name.endsWith('.ts') && !name.endsWith('.test.ts') && !NON_WRAPPER_FILES.has(name),
  );
}

/** Path keys of the generated `paths` interface, e.g. `/vendors/{vendor_id}`. */
function schemaPaths(): Set<string> {
  const schema = readFileSync(join(apiDir, 'schema.d.ts'), 'utf-8');
  const start = schema.indexOf('export interface paths {');
  const end = schema.indexOf('\nexport interface components {');
  if (start === -1 || end === -1) {
    throw new Error('schema.d.ts does not look like an openapi-typescript output — regenerate it.');
  }
  const body = schema.slice(start, end);
  const paths = new Set<string>();
  for (const match of body.matchAll(/^ {4}"(\/[^"]*)": \{$/gm)) {
    const path = match[1];
    if (path) paths.add(path);
  }
  return paths;
}

/** Every `call(...)` / `callBinary(...)` / `callMultipart(...)` literal path argument in a wrapper file. */
function calledPaths(source: string): string[] {
  const paths: string[] = [];
  for (const match of source.matchAll(/\bcall(?:Binary|Multipart)?<[^>]+>\(\s*'[a-z]+'\s*,\s*'([^']+)'/g)) {
    const path = match[1];
    if (path) paths.push(path);
  }
  return paths;
}

describe('generated API contract', () => {
  const paths = schemaPaths();
  const files = wrapperFiles();

  it('found operation wrapper files to check', () => {
    expect(files.length).toBeGreaterThan(0);
  });

  it('has at least one known path in the generated schema', () => {
    expect(paths.has('/health')).toBe(true);
    expect(paths.has('/auth/me')).toBe(true);
  });

  it.each(files)('every path %s calls exists in schema.d.ts', (file) => {
    const source = readFileSync(join(apiDir, file), 'utf-8');
    const used = calledPaths(source);
    expect(used.length, `${file} calls no operation`).toBeGreaterThan(0);
    for (const path of used) {
      expect(paths.has(path), `${file} calls "${path}", which is not a path in schema.d.ts`).toBe(
        true,
      );
    }
  });
});
