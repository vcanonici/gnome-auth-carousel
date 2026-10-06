// Minimal .po reader for the preview and tests: msgid/msgstr pairs with
// continuation lines; no plurals or contexts (the carousel uses neither).
function unquote(line) {
    return JSON.parse(line.trim());
}

export function parsePo(text) {
    const catalog = {};
    let msgid = null, msgstr = null, field = null;
    const flush = () => {
        if (msgid)
            catalog[msgid] = msgstr ?? '';
        msgid = msgstr = field = null;
    };
    for (const line of text.split('\n')) {
        if (line.startsWith('msgid ')) {
            flush();
            msgid = unquote(line.slice(6));
            field = 'msgid';
        } else if (line.startsWith('msgstr ')) {
            msgstr = unquote(line.slice(7));
            field = 'msgstr';
        } else if (line.startsWith('"') && field === 'msgid') {
            msgid += unquote(line);
        } else if (line.startsWith('"') && field === 'msgstr') {
            msgstr += unquote(line);
        }
    }
    flush();
    return catalog;
}
