import assert from 'node:assert/strict';
import test from 'node:test';
import {AuthState, FACTORS, PASSWORD, FINGERPRINT, TREZOR, isMarker} from '../state.js';
test('second factor result cannot complete the password stage', () => {
    const s = new AuthState();
    assert.equal(s.complete(), false);
    assert.equal(s.stage, 'password');
});
test('password marker resets a partially completed or failed attempt', () => {
    const s = new AuthState();
    s.marker(FINGERPRINT);
    s.rejectSecond();
    s.marker(PASSWORD);
    assert.equal(s.stage, 'password');
    assert.equal(s.attempts, 0);
    assert.equal(s.complete(), false);
});
test('three rejected second factors reset the attempt', () => {
    const s = new AuthState();
    s.marker(FINGERPRINT);
    for (let i = 0; i < 3; i++) s.rejectSecond();
    assert.equal(s.stage, 'password');
    assert.match(s.message, /Too many attempts/);
});
test('unknown or out of order marker never advances a completed attempt', () => {
    const s = new AuthState();
    assert.equal(s.marker('garbage'), false);
    s.marker(FINGERPRINT);
    assert.equal(s.complete(), true);
    assert.equal(s.marker(FINGERPRINT), false);
    assert.equal(s.stage, 'complete');
});
test('each factor only advances on its own marker', () => {
    const trezor = new AuthState('trezor');
    assert.equal(trezor.marker(FINGERPRINT), false);
    assert.equal(trezor.stage, 'password');
    assert.equal(trezor.marker(TREZOR), true);
    assert.equal(trezor.message, FACTORS.trezor.prompt);
    const fingerprint = new AuthState('fingerprint');
    assert.equal(fingerprint.marker(TREZOR), false);
});
test('unknown factor is rejected', () => {
    assert.throws(() => new AuthState('sms'), /Unknown second factor/);
});
test('messages go through the injected translation', () => {
    const s = new AuthState('trezor', text => `[${text}]`);
    assert.equal(s.message, '[Enter your password]');
    s.marker(TREZOR);
    assert.equal(s.message, '[Connect your Trezor and confirm on the device]');
    s.fail();
    assert.equal(s.message, '[Try again. Enter your password.]');
});
test('isMarker accepts exactly the protocol markers', () => {
    for (const marker of [PASSWORD, FINGERPRINT, TREZOR])
        assert.equal(isMarker(marker), true);
    for (const other of ['', 'THINKPAD_AUTH_V1:', 'Please touch the device.'])
        assert.equal(isMarker(other), false);
});
