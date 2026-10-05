import {AuthState, FINGERPRINT} from '../state.js';
const state = new AuthState();
const dialog = document.querySelector('.dialog');
function render() {
    const digital = state.stage !== 'password';
    dialog.classList.toggle('digital', digital);
    dialog.classList.toggle('complete', state.stage === 'complete');
    document.querySelector('#instruction').textContent = state.message;
    document.querySelector('#password-row').hidden = digital;
    document.querySelector('#waiting').hidden = state.stage !== 'fingerprint';
    document.querySelector('#result').textContent = state.stage === 'complete' ? 'Simulação concluída — os dois fatores foram aceitos.' : '';
    document.body.dataset.stage = state.stage;
}
function action(value) {
    switch (value) {
    case 'password-ok': state.marker(FINGERPRINT); break;
    case 'password-fail': state.fail('Senha incorreta. Digite sua senha novamente.'); break;
    case 'finger-ok': state.complete(); break;
    case 'finger-fail': state.rejectFingerprint(); break;
    case 'timeout': state.fail('Tempo esgotado. Digite sua senha novamente.'); break;
    default: state.reset();
    }
    render();
}
for (const button of document.querySelectorAll('[data-action]'))
    button.addEventListener('click', () => action(button.dataset.action));
document.querySelector('#cancel').addEventListener('click', () => action('reset'));
render();
