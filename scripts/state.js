// Visual state only. PAM/GDM remain the authority for authentication.
export const PASSWORD = 'THINKPAD_AUTH_V1:PASSWORD';
export const FINGERPRINT = 'THINKPAD_AUTH_V1:FINGERPRINT';

export class AuthState {
    constructor() {
        this.reset();
    }

    reset() {
        this.stage = 'password';
        this.attempts = 0;
        this.message = 'Digite sua senha';
    }

    marker(value) {
        if (value === PASSWORD) {
            this.reset();
            return true;
        }
        if (value === FINGERPRINT && this.stage === 'password') {
            this.stage = 'fingerprint';
            this.message = 'Coloque o indicador no leitor de impressão digital';
            return true;
        }
        return false;
    }

    rejectFingerprint() {
        if (this.stage !== 'fingerprint')
            return;
        this.attempts++;
        if (this.attempts >= 3)
            this.fail('Limite de tentativas. Digite sua senha novamente.');
        else
            this.message = 'Digital não reconhecida. Coloque o indicador novamente.';
    }

    fail(message = 'Tente novamente. Digite sua senha.') {
        this.reset();
        this.message = message;
    }

    complete() {
        // Only the real GDM verification-complete signal invokes this in production.
        if (this.stage !== 'fingerprint')
            return false;
        this.stage = 'complete';
        this.message = 'Autenticação concluída';
        return true;
    }
}
