import assert from 'node:assert/strict';
import test from 'node:test';
import {AuthState, PASSWORD, FINGERPRINT} from '../state.js';
test('fingerprint result cannot complete the password stage', () => {
    const s = new AuthState();
    assert.equal(s.complete(), false);
    assert.equal(s.stage, 'password');
});
test('password marker resets a partially completed or failed attempt', () => {
    const s = new AuthState();
    s.marker(FINGERPRINT);
    s.rejectFingerprint();
    s.marker(PASSWORD);
    assert.equal(s.stage, 'password');
    assert.equal(s.attempts, 0);
    assert.equal(s.complete(), false);
});
test('three rejected fingerprints reset the attempt', () => {
    const s = new AuthState();
    s.marker(FINGERPRINT);
    for (let i = 0; i < 3; i++) s.rejectFingerprint();
    assert.equal(s.stage, 'password');
    assert.match(s.message, /Limite/);
});
test('unknown or out of order marker never advances a completed attempt', () => {
    const s = new AuthState();
    assert.equal(s.marker('garbage'), false);
    s.marker(FINGERPRINT);
    assert.equal(s.complete(), true);
    assert.equal(s.marker(FINGERPRINT), false);
    assert.equal(s.stage, 'complete');
});
