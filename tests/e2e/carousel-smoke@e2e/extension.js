// e2e container only: renders the compiled carousel from the Shell resources
// and writes screenshots of the password and second-factor stages.
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import Shell from 'gi://Shell';
import St from 'gi://St';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';
import * as ThinkpadAuth from 'resource:///org/gnome/shell/gdm/thinkpadAuth.js';

const OUT = GLib.getenv('CAROUSEL_SMOKE_OUT') ?? '/tmp';

function wait(ms) {
    return new Promise(resolve => GLib.timeout_add(GLib.PRIORITY_DEFAULT, ms, () => {
        resolve();
        return GLib.SOURCE_REMOVE;
    }));
}

async function screenshot(name) {
    const file = Gio.File.new_for_path(`${OUT}/${name}`);
    const stream = file.replace(null, false, Gio.FileCreateFlags.NONE, null);
    await new Shell.Screenshot().screenshot(false, stream);
    stream.close(null);
}

export default class CarouselSmoke extends Extension {
    enable() {
        this._run().catch(error => console.error(`CAROUSEL_SMOKE_FAIL ${error}\n${error.stack}`));
    }

    disable() {
        this._stage?.destroy();
        this._stage = null;
    }

    async _run() {
        await wait(3000);
        const [width, height] = global.display.get_size();
        this._stage = new St.Widget({style: 'background-color: #2c001e;', width, height, reactive: true});
        // No AccountsService in the container: the carousel accepts a missing user.
        const carousel = new ThinkpadAuth.Carousel(null);
        const box = new St.BoxLayout({vertical: true, width, height: 360, y: Math.round(height / 3)});
        box.add_child(carousel);
        this._stage.add_child(box);
        global.stage.add_child(this._stage);
        await wait(1000);
        const passwordMessage = carousel.state.message;
        await screenshot('carousel-password.png');
        carousel.marker('THINKPAD_AUTH_V1:TREZOR');
        await wait(1000);
        await screenshot('carousel-second.png');
        console.log(`CAROUSEL_SMOKE_OK stage=${carousel.state.stage} password="${passwordMessage}" second="${carousel.state.message}"`);
    }
}
