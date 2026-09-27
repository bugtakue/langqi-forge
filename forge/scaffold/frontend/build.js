'use strict';
// Copies src/ to dist/ and generates dist/pages/_index.js that imports every page module.
const fs = require('fs');
const path = require('path');

const SRC = path.join(__dirname, 'src');
const DIST = path.join(__dirname, 'dist');

function copyDir(from, to) {
  fs.mkdirSync(to, { recursive: true });
  for (const entry of fs.readdirSync(from, { withFileTypes: true })) {
    const a = path.join(from, entry.name);
    const b = path.join(to, entry.name);
    if (entry.isDirectory()) copyDir(a, b);
    else fs.copyFileSync(a, b);
  }
}

function listPages(dir, prefix = '') {
  if (!fs.existsSync(dir)) return [];
  let out = [];
  for (const entry of fs.readdirSync(dir, { withFileTypes: true }).sort((x, y) => x.name.localeCompare(y.name))) {
    if (entry.name.startsWith('_')) continue;
    if (entry.isDirectory()) out = out.concat(listPages(path.join(dir, entry.name), prefix + entry.name + '/'));
    else if (entry.name.endsWith('.js')) out.push(prefix + entry.name);
  }
  return out;
}

fs.rmSync(DIST, { recursive: true, force: true });
copyDir(SRC, DIST);
const pages = listPages(path.join(SRC, 'pages'));
const lines = pages.map((p, i) => `import * as m${i} from './${p}';`);
lines.push(`export default [${pages.map((_, i) => `m${i}`).join(', ')}];`);
fs.mkdirSync(path.join(DIST, 'pages'), { recursive: true });
fs.writeFileSync(path.join(DIST, 'pages', '_index.js'), lines.join('\n') + '\n');
console.log(`built ${pages.length} page modules into dist/`);
