# Cal presentation assets

Artwork and face animation reused from
[Shrithan/DESK, claude/bear-voice-studio](https://github.com/Shrithan/DESK/tree/claude/bear-voice-studio).
`cal-bear-talking.webp` encodes the original portrait. `face.js` retains the original
canvas jaw, gaze, blink, and reduced-motion behavior, loading the bundled portrait.

`interface.js` is a presentation adapter for this checkout's existing voice and
studio controls. It does not import the branch's tool agent, streaming STT, backend,
models, or mapping runtime. Audio uses the existing decoded Cartesia buffer and
speaker destination; its waveform animates the mouth.

Run `python scripts/build_bear_ui.py` after editing these sources. It bundles the
UI/art into the existing `/module-agent.js` and `/fusion.css` assets, so no server
routes or backend changes are needed. Generated sections have a `BEGIN CAL BEAR
PRESENTATION BUNDLE` marker and are replaced idempotently.
