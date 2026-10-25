"""Conversational action engine for the bear: ASI:One tool calls over the studio's real handlers.

The browser owns cameras, tracks and controls, so it executes every tool against the existing
handlers and reports the verified result. This module only defines the tool schemas, validates
the conversation and tool arguments, and asks ASI:One for the next step. Keys stay server-side.
"""
import json
import re
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from vision.voice import configuration, VoiceError

OBJECT = dict(type='string', maxLength=80, description='Object or control: an id from state, "#2", "disk 2", "can", or "it"/"that" for the one last discussed.')
ROLE = dict(type='string', enum=['overhead', 'side'])
STICKER_KEYS = ['space', 'enter', 'escape', 'tab', 'up', 'down', 'left', 'right', *'abcdefghijklmnopqrstuvwxyz', *'0123456789']


def tool(name, description, properties=None, required=()):
    return dict(name=name, description=description, parameters=dict(
        type='object', properties=properties or {}, required=list(required), additionalProperties=False))


TOOLS = [
    # Cameras and tracking session
    tool('start_cameras', 'Start (or reconnect) the cameras. Optionally choose overhead-only or two-camera mode first.',
         dict(mode=dict(type='string', enum=['overhead_only', 'two_cameras']))),
    tool('stop_cameras', 'Stop all cameras. Also stops real keyboard and desktop output.'),
    tool('set_camera_mode', 'Choose overhead-only joystick mode (one webcam, no iPhone) or two-camera mode (side + overhead).',
         dict(mode=dict(type='string', enum=['overhead_only', 'two_cameras'])), ['mode']),
    tool('list_cameras', 'Refresh and list the available camera sources and which one each role uses.'),
    tool('choose_camera', 'Choose which camera source feeds a role. Restarts running cameras so it takes effect.',
         dict(role=ROLE, device=dict(type='string', maxLength=120, description='Camera name or part of it, as listed.')), ['role', 'device']),
    tool('set_camera_orientation', 'Set a camera view orientation.',
         dict(role=ROLE, orientation=dict(type='string', enum=['auto', 'original', 'clockwise', 'counterclockwise'])), ['role', 'orientation']),
    tool('reset_camera_zoom', 'Reset a camera to its widest zoom. Clears the workspace origin.', dict(role=ROLE), ['role']),
    tool('set_camera_exposure', 'Lock exposure and colour, or return them to automatic.',
         dict(role=ROLE, locked=dict(type='boolean')), ['role', 'locked']),
    tool('set_iphone_usb_required', 'Require a USB cable for an iPhone camera, or allow wireless.',
         dict(required=dict(type='boolean')), ['required']),
    tool('reverse_axis', 'Reverse or restore an axis direction: x and y are overhead, z is the side camera.',
         dict(axis=dict(type='string', enum=['x', 'y', 'z']), reversed=dict(type='boolean')), ['axis', 'reversed']),
    tool('set_motion_prediction', 'Turn fast motion prediction on or off.', dict(enabled=dict(type='boolean')), ['enabled']),
    tool('set_demo_preview', 'Show or exit the simulated demo controls (only when cameras are off).',
         dict(enabled=dict(type='boolean')), ['enabled']),
    tool('zero_workspace', 'Set the current positions of spatial objects as zero.'),
    tool('reset_all_tracks', 'Forget all tracked objects, pairs and controls and start tracking fresh.'),
    tool('pair_objects', 'Pair a side-camera object with an overhead object as the same physical object.',
         dict(side_object=OBJECT, overhead_object=OBJECT), ['side_object', 'overhead_object']),
    tool('unpair_object', 'Unpair a spatial (two-camera) object.', dict(object=OBJECT), ['object']),
    # Physical controls
    tool('assign_control', 'Make a visible object a joystick, horizontal slider, vertical slider or cover button (0/1 input).',
         dict(object=OBJECT, kind=dict(type='string', enum=['joystick', 'horizontal_slider', 'vertical_slider', 'button'])), ['object', 'kind']),
    tool('use_can_as_joystick', 'Wait for a can under the overhead camera and make it the joystick.'),
    tool('calibrate_joystick', 'Calibrate a can joystick: upright neutral (hold still 1 s), then learn forward (W), then learn right (D).',
         dict(object=OBJECT, step=dict(type='string', enum=['upright', 'learn_forward', 'learn_right'])), ['object', 'step']),
    tool('center_joystick', 'Center a joystick at its current position and zero its rotation.', dict(object=OBJECT), ['object']),
    tool('use_pivot_mode', 'Switch a joystick to pivot / WASD mode around its saved base.', dict(object=OBJECT), ['object']),
    tool('set_slider_end', 'Set a slider\'s 0% or 100% end at the object\'s current position.',
         dict(object=OBJECT, end=dict(type='integer', enum=[0, 100])), ['object', 'end']),
    tool('swap_slider_axis', 'Switch a slider between horizontal and vertical.', dict(object=OBJECT), ['object']),
    tool('remove_control', 'Remove a joystick, slider or button.', dict(object=OBJECT), ['object']),
    tool('relearn_button', 'Reconnect a cover button to its object, or re-arm it to learn the uncovered view.', dict(object=OBJECT), ['object']),
    # Mapping physical inputs to desktop actions and real output
    tool('map_to_action', 'Bind a visible object to an action target and arm it. Joystick→keys; sliders→keys, scroll, brightness or volume; '
         'cover_button→a key or opening an app. Omit bindings for defaults (joystick WASD; slider_y up increases).',
         dict(object=OBJECT, controller=dict(type='string', enum=['joystick', 'slider_x', 'slider_y', 'cover_button']),
              output=dict(type='string', maxLength=200, description='Target id: keyboard, desktop.scroll, display.brightness, audio.volume or app.open.<bundle> from find_actions.'),
              bindings=dict(type='object', additionalProperties=dict(type='string', maxLength=40),
                            description='joystick: up/down/left/right→key; sliders: negative/positive; cover_button: press→key or "open".'),
              mode=dict(type='string', enum=['game', 'typing']), deadzone=dict(type='number', minimum=.08, maximum=.6)),
         ['object', 'controller', 'output']),
    tool('find_actions', 'Search the available action targets, including installed apps that a button can open.',
         dict(query=dict(type='string', maxLength=80))),
    tool('undo_mapping', 'Restore the previous action mapping.'),
    tool('set_output_control', 'Choose which mapped joystick or control drives real output.', dict(object=OBJECT), ['object']),
    tool('set_output_mode', 'Game mode holds keys; document (typing) mode repeats letters. Disarms output until re-armed.',
         dict(mode=dict(type='string', enum=['game', 'typing'])), ['mode']),
    tool('arm_output', 'Arm real keyboard / desktop output for the selected (or named) mapped control.', dict(object=OBJECT)),
    tool('stop_output', 'Stop all real keyboard and desktop output immediately.'),
    tool('request_keyboard_permission', 'Ask macOS for the Accessibility permission real keys need.'),
    tool('open_accessibility_settings', 'Open macOS Accessibility settings so the user can allow keyboard output.'),
    tool('test_keyboard', 'Send a local W A S D test into the on-screen test field and check it arrived.'),
    tool('add_sticker_button', 'Register a fixed sticker under the overhead camera as a cover button that presses a key. '
         'The sticker\'s location is a cell 1-9 of the 3x3 grid shown over the overhead view (1 top-left, 9 bottom-right).',
         dict(key=dict(type='string', enum=STICKER_KEYS), grid_cell=dict(type='integer', minimum=1, maximum=9)), ['key', 'grid_cell']),
    # Voice and display
    tool('set_voice_feedback', 'Turn spoken status announcements (cameras ready, tracking lost...) on or off.',
         dict(enabled=dict(type='boolean')), ['enabled']),
    tool('test_voice', 'Play the Cartesia voice test phrase.'),
    tool('set_bear_voice', 'Mute or unmute the bear\'s spoken replies (captions remain).', dict(muted=dict(type='boolean')), ['muted']),
    tool('set_voice_target', 'Pin the object that "this" refers to for mappings, or "auto" to use the one visible or moving object.',
         dict(object=OBJECT), ['object']),
    tool('show_view', 'Show a visual panel next to the bear: the camera view, the 3D map, the controls list, '
         'the scroll test area, the keyboard test field, the action list, or none.',
         dict(view=dict(type='string', enum=['none', 'camera', 'map', 'controls', 'scroll_test', 'keyboard_test', 'actions'])), ['view']),
    tool('filter_controls', 'Filter the controls list by type.',
         dict(type=dict(type='string', enum=['all', 'joystick', 'slider', 'object', 'button'])), ['type']),
    tool('adjust_map_view', 'Rotate, tilt, zoom or reset the 3D map view.',
         dict(action=dict(type='string', enum=['rotate_left', 'rotate_right', 'tilt_up', 'tilt_down', 'zoom_in', 'zoom_out', 'reset']),
              amount=dict(type='number', minimum=.1, maximum=4, description='Multiplier for the default step.')), ['action']),
    tool('stop_listening', 'Turn the microphone off and end the conversation.'),
    tool('open_single_camera_page', 'Leave the studio for the separate single-webcam page.'),
    tool('get_status', 'Read the full live app state.'),
]
TOOL_NAMES = {t['name'] for t in TOOLS}
SCHEMAS = {t['name']: t['parameters'] for t in TOOLS}

SYSTEM = '''You are the Cal bear, the voice of DESK Phantom: a studio that turns everyday objects seen by webcams into joysticks, sliders and buttons that drive real keyboard keys, scrolling, brightness, volume or app launches. The user talks to you instead of using any buttons, so you operate the app ONLY through the tools.

Rules:
- Every change happens through a tool. Never say something happened unless a tool result in this conversation returned ok:true for it. If a tool fails, say briefly what failed and the next step, and offer to do it.
- The "Live app state" message is current and authoritative. Use it, the tool results and the conversation to resolve references like "it", "that one", "the other one", "make it bigger" or "actually use X instead". Corrections may mean undoing or redoing an earlier action.
- If a request is ambiguous or is missing what to change, ask ONE short targeted question, offering the relevant options from the state (e.g. "Red Bull should be like..." -> ask whether the can should be a joystick, slider or button, mentioning what it is now). Never invent the intended change, an object, a key or an app. Users may call a can by its brand.
- Do several requested actions in order in one turn. Prerequisites (cameras running, an object visible) can be done for the user when they clearly want the end result.
- Arming real output sends keys to other apps: only arm when asked, or as part of a mapping the user requested.
- If the user cancels or changes their mind about a question you asked, drop it.
- Mention settings only when relevant; do not read out every option.
- Replies are spoken: one or two short, friendly sentences, plain words, no lists, markdown, emoji or ids. Numbers as words are fine.'''

MAX_MESSAGES = 40
MAX_CONTENT = 4000


def validate_arguments(schema, value, path='arguments'):
    """Small JSON-schema subset used by TOOLS: object/string/boolean/number/integer, enum, ranges."""
    kind = schema.get('type')
    if kind == 'object':
        if not isinstance(value, dict):raise ValueError(f'{path} must be an object')
        props = schema.get('properties', {})
        for name in schema.get('required', []):
            if name not in value:raise ValueError(f'{path}.{name} is required')
        extra = schema.get('additionalProperties', True)
        if len(value) > 24:raise ValueError(f'{path} has too many fields')
        for name, item in value.items():
            if name in props:validate_arguments(props[name], item, f'{path}.{name}')
            elif extra is False:raise ValueError(f'{path}.{name} is not allowed')
            elif isinstance(extra, dict):validate_arguments(extra, item, f'{path}.{name}')
    elif kind == 'string':
        if not isinstance(value, str):raise ValueError(f'{path} must be text')
        if len(value) > schema.get('maxLength', 200):raise ValueError(f'{path} is too long')
    elif kind == 'boolean':
        if type(value) is not bool:raise ValueError(f'{path} must be true or false')
    elif kind in ('number', 'integer'):
        if type(value) not in (int, float) or (kind == 'integer' and int(value) != value) or value != value:raise ValueError(f'{path} must be a {kind}')
        if 'minimum' in schema and value < schema['minimum']:raise ValueError(f'{path} must be at least {schema["minimum"]}')
        if 'maximum' in schema and value > schema['maximum']:raise ValueError(f'{path} must be at most {schema["maximum"]}')
    if 'enum' in schema and value not in schema['enum']:raise ValueError(f'{path} must be one of {schema["enum"]}')
    return value


def sanitize_history(messages):
    """Accept only user/assistant/tool turns with known tools, and pair every tool result with its call."""
    if not isinstance(messages, list) or not 1 <= len(messages) <= MAX_MESSAGES:
        raise ValueError(f'Conversation must have 1 to {MAX_MESSAGES} messages.')
    clean, open_calls = [], set()
    for m in messages:
        if not isinstance(m, dict) or m.get('role') not in ('user', 'assistant', 'tool'):raise ValueError('Invalid conversation message.')
        content = m.get('content') or ''
        if not isinstance(content, str) or len(content) > MAX_CONTENT:raise ValueError('Conversation message is too long.')
        if m['role'] == 'user':
            if open_calls:raise ValueError('A tool call is missing its result.')
            if not content.strip():raise ValueError('Empty user message.')
            clean.append(dict(role='user', content=content))
        elif m['role'] == 'assistant':
            if open_calls:raise ValueError('A tool call is missing its result.')
            calls = m.get('tool_calls') or []
            if not isinstance(calls, list) or len(calls) > 8:raise ValueError('Invalid tool calls.')
            out = []
            for c in calls:
                if not isinstance(c, dict) or c.get('name') not in TOOL_NAMES or not isinstance(c.get('id'), str) or not 1 <= len(c['id']) <= 80:
                    raise ValueError('Invalid tool call in conversation.')
                args = c.get('arguments', {})
                if not isinstance(args, dict):raise ValueError('Invalid tool call arguments.')
                out.append(dict(id=c['id'], type='function', function=dict(name=c['name'], arguments=json.dumps(args))))
                open_calls.add(c['id'])
            if not out and not content.strip():raise ValueError('Empty assistant message.')
            clean.append(dict(role='assistant', content=content, **({'tool_calls': out} if out else {})))
        else:
            if m.get('tool_call_id') not in open_calls:raise ValueError('Tool result without a matching call.')
            open_calls.discard(m['tool_call_id'])
            clean.append(dict(role='tool', tool_call_id=m['tool_call_id'], content=content))
    if open_calls:raise ValueError('A tool call is missing its result.')
    if clean[0]['role'] != 'user':raise ValueError('Conversation must start with the user.')
    return clean


class Assistant:
    def __init__(self, config=configuration, transport=urlopen):
        self.config, self.transport = config, transport

    def status(self):
        c = self.config()
        return dict(provider='asi-one', configured=bool(c.get('ASI1_API_KEY') or c.get('ASI_ONE_API_KEY')),
                    model=c.get('ASI1_MODEL') or 'asi1', tools=TOOLS)

    def step(self, messages, state):
        """One reasoning step: either a final spoken reply or validated tool calls for the browser to run."""
        history = sanitize_history(messages)
        if not isinstance(state, dict):raise ValueError('Missing live app state.')
        state_text = json.dumps(state, separators=(',', ':'))
        if len(state_text) > 24000:raise ValueError('App state is too large.')
        c = self.config();key = c.get('ASI1_API_KEY') or c.get('ASI_ONE_API_KEY')
        if not key:raise VoiceError('Add ASI1_API_KEY to the local .env so the bear can understand requests.')
        body = json.dumps(dict(model=c.get('ASI1_MODEL') or 'asi1', temperature=0, stream=False, max_tokens=1200,
            tools=[dict(type='function', function=t) for t in TOOLS],
            messages=[dict(role='system', content=SYSTEM), dict(role='system', content='Live app state: ' + state_text), *history])).encode()
        request = Request('https://api.asi1.ai/v1/chat/completions', data=body, method='POST',
                          headers={'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json'})
        try:
            with self.transport(request, timeout=30) as response:raw = response.read(262145)
            if len(raw) > 262144:raise ValueError('response too large')
            message = json.loads(raw)['choices'][0]['message']
        except HTTPError as exc:raise VoiceError('ASI:One rejected the request (HTTP %s). Check the key, model and quota.' % exc.code, 502) from None
        except (URLError, TimeoutError, OSError):raise VoiceError('ASI:One is unavailable or timed out. Nothing was changed.', 502) from None
        except (KeyError, IndexError, TypeError, ValueError):raise VoiceError('ASI:One returned an unreadable reply. Nothing was changed.', 502) from None
        calls = []
        for i, call in enumerate((message.get('tool_calls') or [])[:8]):
            fn = call.get('function') or {}
            entry = dict(id=str(call.get('id') or f'call_{i}')[:80], name=fn.get('name'), arguments={})
            try:
                if entry['name'] not in TOOL_NAMES:raise ValueError(f'unknown tool {entry["name"]!r}')
                raw_args = fn.get('arguments') or '{}'
                args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
                entry['arguments'] = validate_arguments(SCHEMAS[entry['name']], args if args is not None else {})
            except (ValueError, TypeError) as exc:
                # Returned so the browser reports it back and the model can correct itself; never executed.
                entry['error'] = 'Invalid tool call: ' + str(exc)
                if entry['name'] not in TOOL_NAMES:entry['name'] = 'get_status'
            calls.append(entry)
        content = message.get('content') or ''
        content = re.sub(r'\s+', ' ', re.sub(r'[*_`#>]+', '', content)).strip()[:800]
        if not calls and not content:raise VoiceError('ASI:One returned an empty reply.', 502)
        return dict(content=content, tool_calls=calls)
