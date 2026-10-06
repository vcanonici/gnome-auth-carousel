import {AuthState, MESSAGES} from '../state.js';
import {parsePo} from './po.js';

const dialog = document.querySelector('.dialog');
const factorSelect = document.querySelector('#factor');
const languageSelect = document.querySelector('#language');
let state;
let translate = text => text;

function render() {
    const second = state.stage !== 'password';
    dialog.classList.toggle('digital', second);
    dialog.classList.toggle('complete', state.stage === 'complete');
    document.querySelector('#instruction').textContent = state.message;
    document.querySelector('#password-row').hidden = second;
    document.querySelector('#waiting').hidden = state.stage !== 'second';
    document.querySelector('#result').textContent = state.stage === 'complete' ? 'Simulação concluída — os dois fatores foram aceitos.' : '';
    document.querySelector('#password-label').textContent = translate(MESSAGES.passwordLabel);
    document.querySelector('#factor-label').textContent = translate(state.factor.label);
    // The hidden attribute does not apply to inline <svg>; toggle display instead.
    document.querySelector('#icon-fingerprint').style.display = factorSelect.value === 'fingerprint' ? '' : 'none';
    document.querySelector('#icon-trezor').style.display = factorSelect.value === 'trezor' ? '' : 'none';
    document.body.dataset.stage = state.stage;
}

function restart() {
    state = new AuthState(factorSelect.value, translate);
    render();
}

function action(value) {
    switch (value) {
    case 'password-ok': state.marker(state.factor.marker); break;
    case 'password-fail': state.fail(); break;
    case 'second-ok': state.complete(); break;
    case 'second-fail': state.rejectSecond(); break;
    case 'timeout': state.fail(); break;
    default: state.reset();
    }
    render();
}

async function selectLanguage(lang) {
    if (!lang) {
        translate = text => text;
    } else {
        const response = await fetch(`../po/${lang}.po`);
        if (!response.ok)
            throw new Error(`Catalog ${lang}: HTTP ${response.status}`);
        const catalog = parsePo(await response.text());
        translate = text => catalog[text] || text;
    }
    restart();
}

async function listLanguages() {
    const response = await fetch('../po/LINGUAS');
    for (const lang of (await response.text()).split(/\s+/).filter(Boolean))
        languageSelect.append(new Option(lang, lang));
    // Mirror the shell: follow the system (browser) language when a catalog exists.
    const preferred = navigator.language.replace('-', '_');
    const match = [...languageSelect.options].find(o => o.value && (o.value === preferred || o.value === preferred.split('_')[0]));
    languageSelect.value = match?.value ?? '';
}

for (const button of document.querySelectorAll('[data-action]'))
    button.addEventListener('click', () => action(button.dataset.action));
document.querySelector('#cancel').addEventListener('click', () => action('reset'));
factorSelect.addEventListener('change', restart);
languageSelect.addEventListener('change', () => selectLanguage(languageSelect.value));
await listLanguages().catch(() => {});
await selectLanguage(languageSelect.value);
