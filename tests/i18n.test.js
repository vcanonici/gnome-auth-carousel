import assert from 'node:assert/strict';
import {readFileSync, readdirSync} from 'node:fs';
import test from 'node:test';
import {parsePo} from '../prototype/po.js';

const root = new URL('../', import.meta.url);
const read = path => readFileSync(new URL(path, root), 'utf8');
const sourceIds = [...read('state.js').matchAll(/N_\('([^']+)'\)/g)].map(m => m[1]);
const potIds = Object.keys(parsePo(read('po/gnome-auth-carousel.pot')));

test('POT matches the msgids marked in state.js', () => {
    assert.deepEqual(potIds, sourceIds);
});
test('LINGUAS lists exactly the shipped catalogs', () => {
    const linguas = read('po/LINGUAS').split(/\s+/).filter(Boolean).sort();
    const files = readdirSync(new URL('po/', root)).filter(f => f.endsWith('.po')).map(f => f.slice(0, -3)).sort();
    assert.deepEqual(linguas, files);
});
for (const file of readdirSync(new URL('po/', root)).filter(f => f.endsWith('.po'))) {
    test(`${file} translates every msgid`, () => {
        const catalog = parsePo(read(`po/${file}`));
        for (const id of potIds)
            assert.ok(catalog[id], `${file}: missing "${id}"`);
        assert.deepEqual(Object.keys(catalog).filter(id => !potIds.includes(id)), [], `${file}: obsolete msgids`);
    });
}
