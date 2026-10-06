// Visual state only. PAM/GDM remain the authority for authentication.
export const PASSWORD = 'THINKPAD_AUTH_V1:PASSWORD';
export const FINGERPRINT = 'THINKPAD_AUTH_V1:FINGERPRINT';
export const TREZOR = 'THINKPAD_AUTH_V1:TREZOR';

// Marks msgids for xgettext without translating at definition time.
const N_ = text => text;

// Each second factor owns its PAM marker, card label and instructions.
export const FACTORS = {
    fingerprint: {
        marker: FINGERPRINT,
        label: N_('Fingerprint'),
        prompt: N_('Place your index finger on the fingerprint reader'),
        rejected: N_('Fingerprint not recognized. Place your index finger again.'),
    },
    trezor: {
        marker: TREZOR,
        // Product name: shown as is in every language.
        label: 'Trezor',
        prompt: N_('Connect your Trezor and confirm on the device'),
        rejected: N_('Trezor not confirmed. Try again.'),
    },
};

export const MESSAGES = {
    password: N_('Enter your password'),
    passwordLabel: N_('Password'),
    limit: N_('Too many attempts. Enter your password again.'),
    retry: N_('Try again. Enter your password.'),
    complete: N_('Authentication complete'),
};

export function isMarker(value) {
    return value === PASSWORD || Object.values(FACTORS).some(f => f.marker === value);
}

export class AuthState {
    // translate: gettext-like function; identity keeps the English msgids.
    constructor(factor = 'fingerprint', translate = text => text) {
        if (!FACTORS[factor])
            throw new Error(`Unknown second factor: ${factor}`);
        this.factor = FACTORS[factor];
        this._ = translate;
        this.reset();
    }

    reset() {
        this.stage = 'password';
        this.attempts = 0;
        this.message = this._(MESSAGES.password);
    }

    marker(value) {
        if (value === PASSWORD) {
            this.reset();
            return true;
        }
        if (value === this.factor.marker && this.stage === 'password') {
            this.stage = 'second';
            this.message = this._(this.factor.prompt);
            return true;
        }
        return false;
    }

    rejectSecond() {
        if (this.stage !== 'second')
            return;
        this.attempts++;
        if (this.attempts >= 3)
            this.fail(this._(MESSAGES.limit));
        else
            this.message = this._(this.factor.rejected);
    }

    fail(message = this._(MESSAGES.retry)) {
        this.reset();
        this.message = message;
    }

    complete() {
        // Only the real GDM verification-complete signal invokes this in production.
        if (this.stage !== 'second')
            return false;
        this.stage = 'complete';
        this.message = this._(MESSAGES.complete);
        return true;
    }
}
