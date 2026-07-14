// Copies src/.htaccess into every built output folder.
//
// The esbuild-based Angular `application` builder does not copy dotfiles via the
// `assets` config, so we do it here as a postbuild step. This drops the SPA
// rewrite rule (unknown path -> index.html) next to each index.html, which is
// what Apache/LiteSpeed hosts like Hostinger need for HTML5 client-side routing
// to survive refreshes and deep links.
//
// It scans dist/ for any folder that directly contains an index.html and writes
// .htaccess there, so it works for every portal config (dist/pulse-q/browser,
// dist/admin/browser, dist/patient/browser, ...) in one pass.

import { readFileSync, writeFileSync, existsSync, readdirSync, statSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const frontendRoot = join(here, '..');
const source = join(frontendRoot, 'src', '.htaccess');
const distRoot = join(frontendRoot, 'dist');

if (!existsSync(source)) {
  console.error(`[copy-htaccess] Source not found: ${source}`);
  process.exit(1);
}
if (!existsSync(distRoot)) {
  console.warn('[copy-htaccess] No dist/ folder — run a build first. Skipping.');
  process.exit(0);
}

const contents = readFileSync(source);
const targets = [];

function walk(dir) {
  let entries;
  try {
    entries = readdirSync(dir);
  } catch {
    return;
  }
  if (entries.includes('index.html')) {
    targets.push(dir);
  }
  for (const entry of entries) {
    const full = join(dir, entry);
    let s;
    try {
      s = statSync(full);
    } catch {
      continue;
    }
    if (s.isDirectory()) walk(full);
  }
}

walk(distRoot);

if (targets.length === 0) {
  console.warn('[copy-htaccess] No index.html folders found under dist/. Nothing copied.');
  process.exit(0);
}

for (const dir of targets) {
  writeFileSync(join(dir, '.htaccess'), contents);
  console.log(`[copy-htaccess] wrote ${join(dir, '.htaccess')}`);
}
