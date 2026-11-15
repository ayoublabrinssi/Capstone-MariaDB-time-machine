// Makes the icons used in the README and docs/details.md, in the colours of the page
// (app/style.css). The icons come from Kubai Icons (MIT, see icons/LICENSE).
//
//   git clone https://github.com/kubai087/kubai-icons ~/.claude/skills/kubai-icons
//   node design/make_icons.mjs            (KUBAI=<path> if it is cloned somewhere else)
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const K = process.env.KUBAI || path.join(process.env.HOME, '.claude/skills/kubai-icons');
const out = path.join(path.dirname(fileURLToPath(import.meta.url)), 'icons');
const { renderSVG } = await import(pathToFileURL(path.join(K, 'packages/core/src/render.js')).href);

const MAJORELLE = '#4436C8', SAFFRON = '#C98A12', RED = '#B03E33', GREEN = '#23775A';
const icons = {
  'book-stack': MAJORELLE, clock: MAJORELLE, history: MAJORELLE, terminal: MAJORELLE, search: MAJORELLE, 'book-open': MAJORELLE,
  notebook: MAJORELLE, inbox: MAJORELLE, send: MAJORELLE, bot: MAJORELLE, layers: MAJORELLE,
  monitor: MAJORELLE, scale: MAJORELLE, calendar: MAJORELLE, folder: MAJORELLE,
  ruler: SAFFRON, lightbulb: SAFFRON, wrench: SAFFRON, truck: SAFFRON, broom: SAFFRON,
  bug: RED, 'triangle-alert': RED, 'brick-wall': RED,
  'circle-check': GREEN, 'test-tube': GREEN,
};
for (const [name, accent] of Object.entries(icons)) {
  const def = (await import(pathToFileURL(path.join(K, 'icons', `${name}.js`)).href)).default;
  fs.writeFileSync(path.join(out, `${name}.svg`), renderSVG(def, { size: 28, accent }) + '\n');
}
console.log(`${Object.keys(icons).length} icons written to ${out}`);
