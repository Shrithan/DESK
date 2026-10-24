# Cartesia voice feedback

The live dashboard has opt-in **Voice feedback** and **Test voice** controls. It announces camera connection/stop, joystick/slider readiness, sustained tracking loss and recovery. It does not listen to the microphone or interpret spoken commands yet.

## Configure

Open the ignored repository-root `.env` and fill in `CARTESIA_API_KEY` from https://play.cartesia.ai/keys. Never paste credentials into chat, put them in frontend code or commit them. `.env.example` documents optional voice/model settings. The server reloads these settings on voice requests, so editing a key does not require restarting cameras.

Run the normal live server:

```sh
.venv/bin/python -m vision.live
```

Open http://localhost:8765, click **Test voice**, then enable **Voice feedback**. If the browser blocks audio, click the button again. Disabling voice cancels pending generation/playback. Missing credentials or provider errors appear in the voice panel; tracking keeps running. The static demo does not synthesize simulated tracking announcements.

## Implementation and limits

`vision/voice.py` uses Cartesia's documented `POST https://api.cartesia.ai/tts/bytes`, API version `2026-08-14`, default model `sonic-3.6`, and a public voice from the official API example. Output is WAV / signed 16-bit PCM / 44100 Hz. See https://docs.cartesia.ai/api-reference/tts/bytes.

Only seven fixed status phrases are eligible for synthesis. No frames, object names, coordinates, or microphone audio are sent. Key stays server-side. Audio is cached in memory per phrase/configuration; requests have bounded timeouts, response size and rate. HTTP speech requests use their own lock outside camera session/model locks. The frontend limits announcements, debounces losses for 750 ms and avoids narrating frame changes or brief occlusions.

Text captions remain available without credentials. They are not presented as a working Cartesia voice demo. Automated provider tests use explicit fixture bytes, not real generated speech. A real authenticated test is still required before claiming sponsor integration is demonstrated; track eligibility has not been verified.

## Validation

```sh
.venv/bin/python -m pytest tests/test_voice.py tests/test_live.py -q
node tests/test_voice.cjs
```

Tests cover the current request schema, credential isolation, no-key behavior, caching/rate limits, sanitized provider errors, malformed audio, independent camera locks, origin rejection and debounced event transitions.
