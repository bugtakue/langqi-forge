// Build-only tooling. Generated runtime has no npm dependency or config loader.
import { build } from 'esbuild';
import { readFile, writeFile, mkdir } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
const here = path.dirname(fileURLToPath(import.meta.url));
const output = path.resolve(here, '../../factory26_harness/vendor');
await mkdir(output, {recursive: true});
const result = await build({
  absWorkingDir: here, entryPoints: ['check.mjs'], bundle: true,
  platform: 'node', format: 'cjs', target: 'node18', minify: true,
  legalComments: 'eof', metafile: true,
  outfile: path.join(output, 'javascript_scope.cjs'),
});
const packages = new Set();
for (const input of Object.keys(result.metafile.inputs)) {
  const match = input.match(/node_modules\/((?:@[^/]+\/)?[^/]+)\//);
  if (match) packages.add(match[1]);
}
const notices = ['Third-party components bundled into javascript_scope.cjs.',
  'Rebuild: cd tools/js_scope && npm ci --ignore-scripts && npm run build.'];
for (const name of [...packages].sort()) {
  const directory = path.join(here, 'node_modules', name);
  const pkg = JSON.parse(await readFile(path.join(directory, 'package.json'), 'utf8'));
  let license;
  for (const candidate of ['LICENSE', 'LICENSE.txt', 'LICENSE.md', 'LICENSE.BSD', 'license']) {
    try { license = await readFile(path.join(directory, candidate), 'utf8'); break; }
    catch (error) { if (error.code !== 'ENOENT') throw error; }
  }
  // esrecurse ships its complete BSD-2-Clause notice in the source header.
  if (!license && name === 'esrecurse') {
    const source = await readFile(path.join(directory, 'esrecurse.js'), 'utf8');
    license = source.match(/^\/\*[\s\S]*?\*\//)?.[0];
  }
  if (!license) throw new Error(`Missing license for ${name}`);
  notices.push(`\n===== ${name}@${pkg.version} (${pkg.license}) =====\n${license}`);
}
await writeFile(path.join(output, 'JAVASCRIPT_SCOPE_NOTICES.txt'), notices.join('\n'));
console.log(`Bundled static checker and ${packages.size} dependency license notices`);
