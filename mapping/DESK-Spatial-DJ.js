/* DESK spatial sliders: MIDI SysEx float parameters, with real mixer feedback. */
var DESKDJ = {};
DESKDJ.prefix = [0xF0, 0x7D, 0x44, 0x53, 0x4B, 1];
DESKDJ.session = ''; DESKDJ.ack = 0; DESKDJ.error = '';
DESKDJ.controls = {
    'mixxx.deck1.volume': ['[Channel1]', 'volume'],
    'mixxx.deck2.volume': ['[Channel2]', 'volume'],
    'mixxx.crossfader': ['[Master]', 'crossfader'],
    'mixxx.deck1.eq.low': ['[EqualizerRack1_[Channel1]_Effect1]', 'parameter1'],
    'mixxx.deck1.eq.mid': ['[EqualizerRack1_[Channel1]_Effect1]', 'parameter2'],
    'mixxx.deck1.eq.high': ['[EqualizerRack1_[Channel1]_Effect1]', 'parameter3'],
    'mixxx.deck2.eq.low': ['[EqualizerRack1_[Channel2]_Effect1]', 'parameter1'],
    'mixxx.deck2.eq.mid': ['[EqualizerRack1_[Channel2]_Effect1]', 'parameter2'],
    'mixxx.deck2.eq.high': ['[EqualizerRack1_[Channel2]_Effect1]', 'parameter3']
};
DESKDJ.init = function () { DESKDJ.timer = engine.beginTimer(100, DESKDJ.feedback); };
DESKDJ.shutdown = function () { if (DESKDJ.timer) engine.stopTimer(DESKDJ.timer); };
DESKDJ.feedback = function () {
    if (!DESKDJ.session) return;
    var values = {}, nativeValues = {};
    Object.keys(DESKDJ.controls).forEach(function (id) {
        var c = DESKDJ.controls[id];
        values[id] = engine.getParameter(c[0], c[1]);
        nativeValues[id] = engine.getValue(c[0], c[1]);
    });
    var packet = JSON.stringify({type: 'state', protocol: 1, session: DESKDJ.session,
        ack: DESKDJ.ack, values: values, native_values: nativeValues, error: DESKDJ.error});
    var bytes = DESKDJ.prefix.slice();
    for (var i = 0; i < packet.length; i++) bytes.push(packet.charCodeAt(i));
    bytes.push(0xF7); midi.sendSysexMsg(bytes, bytes.length);
};
DESKDJ.incomingData = function (data, length) {
    if (length < 8 || length > 2048 || data[length - 1] !== 0xF7) return;
    for (var i = 0; i < DESKDJ.prefix.length; i++) if (data[i] !== DESKDJ.prefix[i]) return;
    try {
        var text = ''; for (i = DESKDJ.prefix.length; i < length - 1; i++) text += String.fromCharCode(data[i]);
        var command = JSON.parse(text);
        if (command.type === 'hello' && typeof command.session === 'string' && /^[a-f0-9]{16}$/.test(command.session)) {
            if (DESKDJ.session !== command.session) { DESKDJ.session = command.session; DESKDJ.ack = 0; }
            DESKDJ.error = ''; DESKDJ.feedback(); return;
        }
        if (command.type !== 'set' || command.session !== DESKDJ.session ||
            !Number.isInteger(command.seq) || command.seq <= DESKDJ.ack) return;
        var control = Object.prototype.hasOwnProperty.call(DESKDJ.controls, command.target) ? DESKDJ.controls[command.target] : null;
        if (!control || typeof command.value !== 'number' || !isFinite(command.value) || command.value < 0 || command.value > 1)
            throw new Error('Invalid slider target or value');
        engine.setParameter(control[0], control[1], command.value);
        DESKDJ.ack = command.seq; DESKDJ.error = ''; DESKDJ.feedback();
    } catch (err) { DESKDJ.error = String(err); DESKDJ.feedback(); }
};
