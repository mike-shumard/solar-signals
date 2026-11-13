// Bounded smoke test for this known public site's calculator, not a customer-code sandbox.
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import assert from 'node:assert/strict';

const root = process.argv[2];
if (!root) throw Error('Usage: node check_site.mjs /restored/project');
const html = fs.readFileSync(path.join(root, 'index.html'), 'utf8');
const nodes = new Map();
for (const m of html.matchAll(/\bid="([^"]+)"/g)) {
  nodes.set(m[1], {value: '', textContent: '', innerHTML: '', hidden: false, style: {},
    addEventListener() {}, setAttribute() {}, click() {}, scrollIntoView() {}});
}
for (const m of html.matchAll(/<input\b[^>]*>/g)) {
  const id = m[0].match(/\bid="([^"]+)"/)?.[1];
  if (id) nodes.get(id).value = m[0].match(/\bvalue="([^"]*)"/)?.[1] ?? '';
}
for (const m of html.matchAll(/<select\b[^>]*id="([^"]+)"[^>]*>([\s\S]*?)<\/select>/g)) {
  const options = [...m[2].matchAll(/<option\b([^>]*)>/g)];
  const chosen = options.find(o => /\bselected\b/.test(o[1])) ?? options[0];
  nodes.get(m[1]).value = chosen?.[1].match(/\bvalue="([^"]*)"/)?.[1] ?? '';
}
const scripts = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)];
assert.equal(scripts.length, 1, 'one known calculator script');
const context = vm.createContext({
  document: {
    getElementById(id) { assert(nodes.has(id), `Missing DOM element ${id}`); return nodes.get(id); },
    querySelectorAll() { return []; },
  },
  matchMedia() { return {matches: false}; },
});
vm.runInContext(scripts[0][1], context, {timeout: 1000});
assert.equal(nodes.get('err').textContent, '');
assert.equal(nodes.get('up').textContent, '$12,232');
assert(!/NaN|Infinity/.test(nodes.get('y1').textContent));
const initial = nodes.get('up').textContent;
nodes.get('kitCost').value = '19232';
vm.runInContext('run()', context, {timeout: 1000});
assert.notEqual(nodes.get('up').textContent, initial, 'changed input changes result');
nodes.get('panelKw').value = '-1';
vm.runInContext('run()', context, {timeout: 1000});
assert(nodes.get('err').textContent.length > 0, 'invalid input raises a visible error');
nodes.get('panelKw').value = '5.4';
vm.runInContext('scen = 2; run()', context, {timeout: 1000});
assert.equal(nodes.get('err').textContent, '');
assert.equal(nodes.get('power').hidden, false);
for (const asset of ['media/be-the-future.mp4', 'media/poster.jpg']) {
  assert(fs.statSync(path.join(root, asset)).size > 0, `${asset} restored and nonempty`);
}
console.log('PASS: restored calculator initializes, responds to input, rejects invalid input, switches scenario; media present.');
