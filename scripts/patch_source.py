#!/usr/bin/env python3
"""Aplica alteracoes delimitadas sobre a fonte Ubuntu exata, fora do host ativo."""
import argparse
from pathlib import Path
import shutil

HERE = Path(__file__).resolve().parent


def replace_once(source, old, new):
    if source.count(old) != 1:
        raise ValueError(f'Fonte inesperada: {old[:100]!r}')
    return source.replace(old, new, 1)


def patch(root):
    changelog = root / 'debian/changelog'
    previous = changelog.read_text()
    version = previous.splitlines()[0].split('(')[1].split(')')[0]
    if version != '46.0-0ubuntu6~24.04.14':
        raise ValueError('Versao Ubuntu inesperada.')
    util = root / 'js/gdm/util.js'
    prompt = root / 'js/gdm/authPrompt.js'
    resource = root / 'js/js-resources.gresource.xml'
    u, p, r = util.read_text(), prompt.read_text(), resource.read_text()
    u = replace_once(u, "import * as Const from './const.js';", "import * as Const from './const.js';\nimport * as ThinkpadAuth from './thinkpadAuth.js';")
    u = replace_once(u, '        this._userName = userName;', '        this._userName = userName;\n        this._thinkpadActive = false;')
    u = replace_once(u, '    _getForegroundService() {', '    _getForegroundService() {\n        if (ThinkpadAuth.enabledFor(this._userName))\n            return PASSWORD_SERVICE_NAME;')
    # Fix the wrong proxy name in both update and destroy paths.
    u = u.replace('this._fingerprintManager', 'this._fprintManager')
    u = replace_once(u, '    async _maybeStartFingerprintVerification() {', '''    async _maybeStartFingerprintVerification() {
        if (!this._settings.get_boolean(FINGERPRINT_AUTHENTICATION_KEY) ||
            ThinkpadAuth.enabledFor(this._userName))
            return;''')
    u = replace_once(u, '    _startBackgroundServices() {', '''    _startBackgroundServices() {
        if (ThinkpadAuth.enabledFor(this._userName))
            return;''')
    u = replace_once(u, '''    _onInfo(client, serviceName, info) {
        this.emit(`service-request::${serviceName}`);''', '''    _onInfo(client, serviceName, info) {
        this.emit(`service-request::${serviceName}`);
        if (serviceName === PASSWORD_SERVICE_NAME && ThinkpadAuth.enabledFor(this._userName)) {
            const marker = info.trim();
            if (ThinkpadAuth.isMarker(marker)) {
                this._thinkpadActive = true;
                this.emit('thinkpad-step', marker);
                return;
            }
            if (this._thinkpadActive) {
                // Persistent UI replaces informational messages without a read timer.
                return;
            }
        }''')
    u = replace_once(u, '''    _onProblem(client, serviceName, problem) {
        this.emit(`service-request::${serviceName}`);''', '''    _onProblem(client, serviceName, problem) {
        this.emit(`service-request::${serviceName}`);
        if (this._thinkpadActive && serviceName === PASSWORD_SERVICE_NAME) {
            this.emit('show-message', serviceName, problem, MessageType.ERROR);
            return;
        }''')
    p = replace_once(p, "import * as UserWidget from '../ui/userWidget.js';", "import * as UserWidget from '../ui/userWidget.js';\nimport * as ThinkpadAuth from './thinkpadAuth.js';")
    p = replace_once(p, "        this._userVerifier.connect('ask-question', this._onAskQuestion.bind(this));", "        this._userVerifier.connect('thinkpad-step', this._onThinkpadStep.bind(this));\n        this._userVerifier.connect('ask-question', this._onAskQuestion.bind(this));")
    p = replace_once(p, '    _onAskQuestion(verifier, serviceName, question, secret) {', '''    _onThinkpadStep(_verifier, marker) {
        this._thinkpadCarousel?.marker(marker);
        if (marker !== ThinkpadAuth.PASSWORD) {
            // Second factor: the password entry stays hidden until PAM restarts.
            this._entry.text = '';
            this._entry.visible = false;
            this._capsLockWarningLabel.visible = false;
        }
    }

    _onAskQuestion(verifier, serviceName, question, secret) {''')
    p = replace_once(p, '    _onVerificationFailed(userVerifier, serviceName, canRetry) {', '''    _onVerificationFailed(userVerifier, serviceName, canRetry) {
        this._thinkpadCarousel?.fail();''')
    p = replace_once(p, '    _onVerificationComplete() {', '''    _onVerificationComplete() {
        this._thinkpadCarousel?.complete();''')
    p = replace_once(p, '''        let userWidget = new UserWidget.UserWidget(user, Clutter.Orientation.VERTICAL);
        this._userWell.set_child(userWidget);''', '''        this._thinkpadCarousel = null;
        let userWidget;
        if (ThinkpadAuth.enabledFor(user?.get_user_name())) {
            userWidget = new ThinkpadAuth.Carousel(user);
            this._thinkpadCarousel = userWidget;
        } else {
            userWidget = new UserWidget.UserWidget(user, Clutter.Orientation.VERTICAL);
        }
        this._userWell.set_child(userWidget);''')
    r = replace_once(r, '    <file>gdm/util.js</file>', '    <file>gdm/util.js</file>\n    <file>gdm/thinkpadAuth.js</file>\n    <file>gdm/thinkpadAuthState.js</file>')
    # All validation above precedes writes; never accept a partially different source.
    util.write_text(u)
    prompt.write_text(p)
    resource.write_text(r)
    shutil.copyfile(HERE / 'thinkpadAuth.js', root / 'js/gdm/thinkpadAuth.js')
    shutil.copyfile(HERE / 'state.js', root / 'js/gdm/thinkpadAuthState.js')
    changelog.write_text('''gnome-shell (46.0-0ubuntu6~24.04.14+thinkpad2) noble; urgency=medium

  * Add sequential password/second-factor carousel; keep PAM authoritative.
  * Second factor selectable: fingerprint (fprintd) or Trezor (pam_u2f).
  * Translate carousel texts through the gnome-auth-carousel gettext domain.
  * Correct cached fingerprint proxy and avoid parallel conversation.

 -- ThinkPad Maintenance <root@localhost>  Tue, 06 Oct 2026 12:00:00 +0000

''' + previous)
    print('FONTE_PATCH_APLICADO 46.0-0ubuntu6~24.04.14+thinkpad2')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    patch(parser.parse_args().source.resolve(strict=True))
