"""Low-rate Cartesia speech adapter; never receives frames or holds tracking locks."""
import json
import os
from pathlib import Path
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

PHRASES = {
    'command_example': 'Map this can to a joystick.',
    'mapping_joystick': 'Mapped as a joystick. Keep it upright to calibrate. Arm real keys when you are ready.',
    'mapping_ambiguous': 'I see more than one possible object. Choose the voice target, then try again.',
    'mapping_unknown': 'Please say: map this can to a joystick, or stop keyboard control.',
    'keys_armed': 'Real keyboard control is armed. Switch to your game or document.',
    'keys_stopped': 'Keyboard control stopped.',
    'test': 'Phantom voice is ready. Turn everyday objects into controls.',
    'cameras_ready': 'Both cameras are connected. Move an object to get started.',
    'cameras_stopped': 'Cameras stopped.',
    'joystick_ready': 'Your joystick is ready.',
    'slider_ready': 'Your slider is ready.',
    'tracking_lost': 'Control tracking lost. Move the object back into view.',
    'tracking_recovered': 'Tracking restored. Your controls are ready.',
}
ENV_KEYS = ('CARTESIA_API_KEY', 'CARTESIA_VOICE_ID', 'CARTESIA_MODEL_ID', 'ASI1_API_KEY', 'ASI_ONE_API_KEY', 'ASI1_MODEL')


class VoiceError(Exception):
    def __init__(self, message, status=503):
        super().__init__(message)
        self.status = status


def configuration():
    # A tiny literal-only loader: no shell execution or environment expansion.
    values = {}
    path = Path(__file__).resolve().parent.parent / '.env'
    if path.is_file():
        for line in path.read_text().splitlines():
            key, sep, value = line.strip().partition('=')
            if sep and key in ENV_KEYS:
                values[key] = value.strip().strip('\"\'')
    for key in ENV_KEYS:
        if os.environ.get(key):
            values[key] = os.environ[key]
    return values


class CartesiaVoice:
    def __init__(self, config=configuration, transport=urlopen, clock=time.monotonic):
        self.config, self.transport, self.clock = config, transport, clock
        self.lock = threading.Lock()
        self.cache = {}
        self.last_request = -float('inf')

    def status(self):
        config = self.config()
        return dict(provider='cartesia', configured=bool(config.get('CARTESIA_API_KEY')),
                    model=config.get('CARTESIA_MODEL_ID') or 'sonic-3.6',
                    sends='Status phrases and the bear\'s replies for speech; live microphone audio only while the user has the bear listening. No camera frames.',speech_input_model='ink-2',
                    phrases=list(PHRASES.values()))

    def speak(self, event):
        if not isinstance(event, str) or event not in PHRASES:
            raise VoiceError('Unknown voice event', 400)
        config = self.config()
        key = config.get('CARTESIA_API_KEY')
        if not key:
            raise VoiceError('Add CARTESIA_API_KEY to the local .env file to enable Cartesia.')
        model = config.get('CARTESIA_MODEL_ID') or 'sonic-3.6'
        voice = config.get('CARTESIA_VOICE_ID') or '47c38ca4-5f35-497b-b1a3-415245fb35e1'
        cache_key = (key, model, voice, event)
        if not self.lock.acquire(blocking=False):
            raise VoiceError('Voice is busy; tracking continues.', 429)
        try:
            if cache_key in self.cache:
                return self.cache[cache_key]
            if self.clock() - self.last_request < 2:
                raise VoiceError('Please wait a moment before another voice request.', 429)
            self.last_request = self.clock()
            payload = dict(model_id=model, transcript=PHRASES[event], voice=voice,
                           output_format=dict(container='wav', encoding='pcm_s16le', sample_rate=44100),
                           language='en')
            request = Request('https://api.cartesia.ai/tts/bytes', data=json.dumps(payload).encode(),
                              headers={'Authorization': f'Bearer {key}', 'Cartesia-Version': '2026-08-14',
                                       'Content-Type': 'application/json'}, method='POST')
            try:
                with self.transport(request, timeout=8) as response:
                    audio = response.read(4_000_001)
            except HTTPError as exc:
                message = 'Cartesia rejected the API key.' if exc.code in (401, 403) else 'Cartesia could not generate speech. Check the account and model settings.'
                raise VoiceError(message, 502) from None
            except (URLError, TimeoutError, OSError):
                raise VoiceError('Cartesia is unavailable. Tracking continues.', 502) from None
            if len(audio) > 4_000_000 or not (audio[:4] == b'RIFF' and audio[8:12] == b'WAVE'):
                raise VoiceError('Cartesia returned an invalid audio response.', 502)
            if len(self.cache) >= len(PHRASES):
                self.cache.clear()
            self.cache[cache_key] = audio
            return audio
        finally:
            self.lock.release()
