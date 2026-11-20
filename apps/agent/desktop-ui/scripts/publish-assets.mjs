import { cp, mkdir, readFile, readdir, lstat, unlink, writeFile } from 'node:fs/promises';
import { dirname, isAbsolute, relative, resolve, sep } from 'node:path';
import { fileURLToPath } from 'node:url';

const projectRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const buildRoot = resolve(projectRoot, 'dist');
const agentRoot = resolve(projectRoot, '../src/autojobs_agent');
const targetRoot = resolve(agentRoot, 'desktop_assets');
if (relative(agentRoot, targetRoot) !== 'desktop_assets') throw new Error('Invalid asset directory');
await mkdir(targetRoot, { recursive: true });
if ((await lstat(targetRoot)).isSymbolicLink()) throw new Error('Asset directory cannot be a link');

const manifestPath = resolve(targetRoot, 'asset-manifest.json');
let previousFiles = [];
try {
  previousFiles = JSON.parse(await readFile(manifestPath, 'utf8'));
} catch (error) {
  if (error.code !== 'ENOENT') throw error;
}
if (!Array.isArray(previousFiles)) throw new Error('Invalid asset manifest');

async function enumerate(directory, prefix = '') {
  const files = [];
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    if (entry.isSymbolicLink()) throw new Error('Build contains a link');
    const name = `${prefix}${entry.name}`;
    if (entry.isDirectory()) files.push(...await enumerate(resolve(directory, entry.name), `${name}/`));
    else if (entry.isFile()) files.push(name);
  }
  return files;
}
const currentFiles = await enumerate(buildRoot);
await cp(buildRoot, targetRoot, { recursive: true, force: true });
for (const name of previousFiles) {
  if (typeof name !== 'string') throw new Error('Invalid asset name');
  const target = resolve(targetRoot, name);
  const inside = relative(targetRoot, target);
  if (!inside || inside.startsWith(`..${sep}`) || inside === '..' || isAbsolute(inside)) {
    throw new Error('Asset path escapes target directory');
  }
  if (!currentFiles.includes(name)) await unlink(target);
}
await writeFile(manifestPath, `${JSON.stringify(currentFiles, null, 2)}\n`);
process.stdout.write(`Published ${currentFiles.length} offline assets to ${targetRoot}\n`);
