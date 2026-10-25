# Bear voice studio

The root dashboard is the Cal bear and a text box. You operate the whole studio by talking to the bear: every former button, toggle, dropdown and per-object card action has a spoken equivalent that runs the same handler.

## How a request flows

1. **Listen.** Click the bear (or **Start listening**). The browser streams 16 kHz PCM to Cartesia Realtime STT (`wss://api.cartesia.ai/stt/turns/websocket`, model `ink-2`), which detects when you have finished a turn. The browser authenticates with a short-lived, STT-only token from `POST /api/voice/token`; the API key never leaves the server.
2. **Understand.** `POST /api/assistant/step` sends the conversation and a live app-state snapshot to ASI:One with the tool list in `vision/assistant.py`. Tool names and arguments are validated server-side before the browser sees them.
3. **Act.** `vision/web/assistant.js` runs each tool against the existing studio code (`start()`, `assignInput()`, `activateMorph()`, card actions, …), then checks the result (camera running, control created, output armed…) and returns `ok` or the real error. Mappings are validated with the same Morph rules via `POST /api/morph/validate`.
4. **Reply.** Only after the tool results come back does the model write a one or two sentence reply, spoken by Cartesia Sonic (`/api/voice/utterance`). The bear's jaw follows the audio envelope.

The conversation history (with tool results) lets follow-ups such as "actually turn it back on" or "make that one a slider" resolve correctly. Vague requests get one short question; the bear never invents the change.

## Talking to it

- Interrupt by speaking while the bear talks; it stops and listens. "Stop", "cancel" or "never mind" drops the current request.
- "Stop all output" / "emergency stop" stops keys immediately without waiting for the model. Escape does the same from the keyboard.
- After two quiet minutes the microphone turns off; click the bear to resume.
- Without `ASI1_API_KEY`, simple commands still work through the original local command list (`routeStudioCommand`). Without `CARTESIA_API_KEY`, type instead of talking; replies stay on screen.

## What stays on screen

The bear (state glow: white while listening, gold while thinking), status chips (listening state, cameras, control count, whether output is armed), what you said, the reply, the last verified actions (✓/✗), the **Start listening** / **Mute bear voice** buttons, and one result panel the bear opens on request: camera view (with a 1–9 grid for sticker buttons), 3D map, controls list, scroll test area, keyboard test field or available actions.

## The bear

`vision/web/bear-face.js` draws `cal-bear-talking.png`: the jaw drops along the smile line, the pupils follow the pointer and blink, and the head turns toward where the bear looks. Reduced-motion mode removes blinks, breathing and the idle lean.

## Configure and run

Add `CARTESIA_API_KEY=...` and `ASI1_API_KEY=...` to the ignored `.env`. Start `.venv/bin/python -m vision.live` (add `--detector motion` without the model), open the printed localhost URL, click the bear and allow the microphone. The camera needs its own permission when first started. macOS Accessibility permission is needed for real key output.

## Tests

`tests/test_assistant.py` covers the tool schemas, the UI-inventory-to-tool mapping, history and argument validation, ASI:One parsing, the STT token and the new routes. A real end-to-end run (simulated microphone hardware, real Cartesia STT, ASI:One, studio handlers and Sonic) passed: two settings changed by one sentence, a follow-up correction, a mid-request "stop", and a clarifying question for "Red Bull should be like".
