// Native GNOME presentation. Never verifies credentials or unlocks a session.
import Clutter from 'gi://Clutter';
import GLib from 'gi://GLib';
import GObject from 'gi://GObject';
import Graphene from 'gi://Graphene';
import St from 'gi://St';
import * as UserWidget from '../ui/userWidget.js';
import {AuthState, PASSWORD, FINGERPRINT} from './thinkpadAuthState.js';

export {PASSWORD, FINGERPRINT};

export function enabledFor(userName) {
    if (!userName)
        return false;
    try {
        const config = new GLib.KeyFile();
        config.load_from_file('/etc/security/thinkpad-auth/ui.conf', GLib.KeyFileFlags.NONE);
        return config.get_boolean('UI', 'Enabled') &&
            config.get_string_list('UI', 'Users').includes(userName);
    } catch {
        return false;
    }
}

export const Carousel = GObject.registerClass(
class ThinkpadCarousel extends St.BoxLayout {
    _init(user) {
        super._init({vertical: true, x_align: Clutter.ActorAlign.CENTER});
        this.state = new AuthState();
        const scale = St.ThemeContext.get_for_stage(global.stage).scaleFactor;
        this._scale = scale;
        this._well = new St.Widget({width: 330 * scale, height: 148 * scale});
        this.add_child(this._well);
        this._avatar = new St.BoxLayout({vertical: true, width: 96 * scale,
            x: 117 * scale, y: 4 * scale, pivot_point: new Graphene.Point({x: 0.5, y: 0.5})});
        const photo = new UserWidget.Avatar(user, {iconSize: 96});
        photo.update();
        user?.connectObject('changed', () => photo.update(), this);
        this._avatar.add_child(photo);
        this._avatar.add_child(new St.Label({text: 'Senha', x_align: Clutter.ActorAlign.CENTER,
            style: 'font-size: 13px; margin-top: 8px;'}));
        this._well.add_child(this._avatar);
        this._finger = new St.BoxLayout({vertical: true, width: 96 * scale,
            x: 117 * scale, y: 4 * scale, pivot_point: new Graphene.Point({x: 0.5, y: 0.5})});
        this._finger.add_child(new St.Icon({icon_name: 'auth-fingerprint-symbolic', icon_size: 96}));
        this._finger.add_child(new St.Label({text: 'Digital', x_align: Clutter.ActorAlign.CENTER,
            style: 'font-size: 13px; margin-top: 8px;'}));
        this._well.add_child(this._finger);
        this.add_child(new St.Label({text: user?.get_real_name() || user?.get_user_name() || '',
            x_align: Clutter.ActorAlign.CENTER, style: 'font-size: 23px; margin-bottom: 16px;'}));
        this._instruction = new St.Label({text: this.state.message,
            x_align: Clutter.ActorAlign.CENTER, style: 'font-size: 17px; margin-bottom: 20px;'});
        this._instruction.clutter_text.line_wrap = true;
        this.add_child(this._instruction);
        this.render(false);
    }

    marker(value) {
        if (!this.state.marker(value))
            return;
        this.render(true);
    }

    fail() {
        this.state.fail();
        this.render(false);
    }

    complete() {
        this.state.complete();
        this.render(false);
    }

    render(animate) {
        const digital = this.state.stage !== 'password';
        const duration = animate && St.Settings.get().enable_animations ? 250 : 0;
        this._instruction.text = this.state.message;
        for (const [actor, active, offset, angle] of [
            [this._avatar, !digital, digital ? -112 : 0, digital ? 18 : 0],
            [this._finger, digital, digital ? 0 : 112, digital ? 0 : -18],
        ]) {
            actor.remove_all_transitions();
            actor.ease({translation_x: offset * this._scale,
                rotation_angle_y: angle, scale_x: active ? 1 : 0.72,
                scale_y: active ? 1 : 0.72, opacity: active ? 255 : 115,
                duration, mode: Clutter.AnimationMode.EASE_OUT_QUAD});
        }
    }
});
