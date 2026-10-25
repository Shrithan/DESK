# DESK — Fetch.ai Agents Handoff (Cal Hacks 13.0)

_Status as of Sat Oct 24, 2026 ~3:10 AM PT. Repo: `~/Documents/projects/DESK`, branch `agent/geometry-backend`. Mac: Apple Silicon, Python **3.14** in `.venv`, `uagents 0.26.1`, `uagents-core 0.4.12`._

## 1. What DESK is
Tilting an ordinary object (a soda can) is turned into held keyboard keys:
forward → W, back → S, left → A, right → D (or arrow keys). Two phone cameras measure the can's tilt angles; `backend/tilt_keys/` turns angles into key presses (calibration, One Euro smoothing, hysteresis ON 15° / OFF 10°, edge-triggered key down/up, release-all safety). That part is done and tested.

## 2. Fetch.ai track requirements (must hit all)
- At least one agent registered on **Agentverse**
- Implements the **Agent Chat Protocol (ACP)**
- Discoverable and usable from **ASI:One**
- Meaningful tool execution or multi-agent orchestration (not a chatbot wrapper)
- **Primary workflow completed entirely inside an ASI:One chat**
- Public GitHub repo with run instructions; README lists agent names and addresses plus the two badges:
  `![tag:innovationlab](https://img.shields.io/badge/innovationlab-3D8BD3)` and `![tag:hackathon](https://img.shields.io/badge/hackathon-5F43F1)`
- 3–5 min demo video; submit on Devpost **and** through the Cal Hacks ASI:One submission agent
- Bonus: multi-agent collaboration, ASI Interactive Cards, Payment Protocol, error recovery, real-time data, keeps running after the hackathon
- Open question for the Fetch mentors: is "configure in ASI:One chat, play with a physical can" acceptable for the "workflow entirely in ASI:One" rule?

## 3. Agent design (DESK-specific; replaces the old Phantom/Morph 5-agent idea)
| Agent | Status | Job |
|---|---|---|
| **DESK Coach** | built, live on Agentverse | Chat-protocol agent the user talks to in ASI:One. Parses intent (keywords + optional LLM), delegates to specialists, replies with text + card data |
| **Setup agent** (`desk-setup`) | built | Game profiles (racing, Subway Surfers → arrow keys), plan → confirm → apply, custom remaps, axis invert |
| **Tuning agent** (`desk-tuner`) | built | Reads real telemetry (presses, flickers, tilt p50/p90/reach), raises or lowers thresholds per axis with evidence, `verify` compares before/after |
| **Doctor agent** (`desk-doctor`) | built | Diagnoses tracking loss, calibration, frame rate, flicker; gives fixes |
| **Validator agent** | NOT built yet | After any change, watch ~20 s of play, keep the change if it helped, undo it if it got worse (use `tuning.compare`) |

The agents never sit in the tilt→keys loop; they only read telemetry and change settings through a control API.

## 4. Code layout (`agents/`)
- `coach.py` — Coach agent, chat protocol handler, `delegate()` sends `TaskRequest` to a specialist, 20 s watchdog (`SPECIALIST_TIMEOUT_S`), `on_result()` handles `TaskResult`
- `specialists.py` — `_make_agent()` / `build_specialists()`; HANDLERS map: setup {plan_setup, apply_setup, custom_setup, invert}, tuner {tune, verify}, doctor {diagnose}
- `messages.py` — `TaskRequest` / `TaskResult` models
- `intent.py`, `profiles.py`, `tuning.py` (pure logic), `doctor.py`, `cards.py`
- `desk_link.py` — `DeskLink` (real: JSON over `ws://127.0.0.1:8765/ws/control`, served by `python -m backend.tilt_keys.run --control`) and `FakeDesk` (simulated player; scenarios `twitchy`, `dark`, `calm`)
- `shared_desk.py` — one Desk per process
- **NEW** `demo_desk.py` — serves a FakeDesk over the same ws control API on :8765, so separate processes share one simulated player
- **NEW** `local_resolver.py` — `LocalFirstResolver`: sends to known local agents straight to `http://127.0.0.1:<port>/submit`, falls back to `GlobalResolver` (Almanac) for everyone else (ASI:One users)
- `run.py` — launcher (rewritten, see section 6)
- `COACH_README.md` — the Agentverse profile README

## 5. Live addresses (Mac, stable seed in `agents/.seed`)
- DESK Coach: `agent1qwtp9sexgrsgrsjqp8u39fhwyslnn7fs85lc7dxwj72zaa0jwnwujatn4vw` (mailbox connected; Agentverse shows **Active, ASI Available**)
- setup: `agent1qtczmqkg8vgyk34fe4rkwn96rla0jlnwj70n6pn3vm7dkrgcy9t8xdwsl3u`
- tuner: `agent1q0lhr74qmn5f6pkgujd9qd7e56y2ns0kg5q8q5hm0w9sqhnrpeg2khg9x8y`
- doctor: `agent1qd69tn2vkzhdee23seeyc5jhzt7zppudgtlsscrtvlh3wxt68syng6rg055`

## 6. What was changed tonight (ALL UNCOMMITTED)
1. **Python 3.14 fix**: `run.py main()` now calls `asyncio.set_event_loop(asyncio.new_event_loop())` before creating any `Agent` (3.14's `get_event_loop()` no longer auto-creates one; uagents calls it in `Agent.__init__`).
2. **Inspector doesn't support Bureaus** ("Agent Bureaus are not supported in this version of the Inspector"), so:
   - `python -m agents.run specialists` → Bureau of setup/tuner/doctor on port **8000**, endpoint `http://127.0.0.1:8000/submit`
   - `python -m agents.run coach` → Coach alone on port **8001**, `mailbox=True`, prints the Inspector link
   - `python -m agents.run` (no arg) → `run_all()` spawns subprocesses: `agents.demo_desk` (only if `DESK_DEMO_MODE=1`; the env var is then removed for the children so they use `DeskLink` to the shared fake), then specialists, then coach
3. **Direct local routing** (attempted fix for the timeout below): `build_specialists(seed_base, resolve=None)` and `build_coach(..., resolve=None)` now accept a resolver. `run.py` gives the Coach `LocalFirstResolver({specialist_addr: http://127.0.0.1:8000/submit})` and the specialists `LocalFirstResolver({coach_addr: http://127.0.0.1:8001/submit})`. The Coach address is computed with `Identity.from_seed(f"{base}-coach", 0).address` (verified equal to `Agent(seed=...).address`).
4. Test hook: env `DESK_EXTRA_LOCAL="agent1...=http://127.0.0.1:8009/submit,..."` adds entries to the Coach's local map.
5. Debug log: `delegate()` now logs `send to <role>: <status>` (the return value of `ctx.send`).
6. Also uncommitted from before tonight's session: `backend/tilt_keys/{config,controller,hysteresis,run}.py` — per-axis left/right thresholds (`lr_on_threshold_deg` / `lr_off_threshold_deg`, `config.thresholds(axis)`), used by the Tuning agent to calm steering only.

How the Mac is run now (one terminal, must stay open; laptop must not sleep):
```
cd ~/Documents/projects/DESK && source .venv/bin/activate
DESK_DEMO_MODE=1 python -m agents.run
```
The mailbox was created through `https://agentverse.ai/inspect/?uri=http%3A//127.0.0.1%3A8001&address=<coach>` → Connect → Mailbox. The log then printed "Successfully registered as mailbox agent in Agentverse." Ignore the "not enough funds to register on Almanac contract" warnings; Almanac **API** registration succeeds.

## 7. CURRENT BLOCKER
In ASI:One, chatting with DESK Coach ("set up desk for a racing game") reaches the Coach, but the reply is:
> The setup agent didn't answer in 20s. Your settings were not changed. Try again?  (Agent: setup, Task: plan_setup)

So **ASI:One → Coach works; Coach → specialist (or specialist → Coach reply) does not.** This happened before the LocalFirstResolver change. The resolver change has NOT been verified on the Mac yet.

Local repro on a Linux test VM (Python 3.10 with `tomli` / `async-timeout` shims, no internet), using a tester agent on :8009:
- The tester's ChatMessage reaches the Coach and gets an ACK.
- The Coach logs `intent ... setup ... racing` and `coach -> setup: plan_setup {...}`.
- **The Setup agent never logs `Setup agent <- plan_setup`.** The message is not arriving at the Bureau, or the Bureau isn't dispatching it.
- In a later run the new `send to setup: <status>` line never printed. Possible causes: `ctx.send` hanging (resolver fallback or DNS retries), a timing or flaky startup issue, or that run never reached delegate. Unresolved; the last test run was cancelled.

Hypotheses to check, in order:
1. Print the `ctx.send` status (`MsgStatus`: delivered / failed + detail). If it shows "failed", look at the endpoint and the HTTP response from `:8000/submit`.
2. `curl -X POST http://127.0.0.1:8000/submit` with a bad body to confirm the Bureau is listening and routing. Check whether the Bureau ASGI server accepts envelopes for each agent address (it should).
3. Protocol/model digest mismatch: `TaskRequest` is registered on specialists through `agent.on_message(model=TaskRequest, replies=TaskResult)`. Confirm the Coach sends the same model class (`agents.messages.TaskRequest`), and that the Coach has a handler for `TaskResult` (`on_result`), otherwise replies are dropped.
4. Before the resolver change, the Coach (mailbox agent) resolved specialists through the Almanac API. Fine in theory, but the Coach's mailbox endpoint meant the **specialists' replies went through Agentverse**, which may be slow or dropped. LocalFirstResolver should fix the reply path if it works.
5. **Simplest fallback if still stuck:** run all four agents in ONE process without a Bureau (or put the Coach plus specialists in one Bureau but keep a separate *standalone* mailbox Coach), or skip agent messaging for specialists entirely and call their handler functions in-process from the Coach. In that case each specialist is still a registered uAgent, but the Coach invokes the logic directly. Multi-agent messaging is a bonus criterion, so prefer fixing the messaging.

## 8. Tests
`python -m pytest -q` (on Linux 3.10 with shims): **113 passed, 3 failed, 2 skipped**
- 2 failures were only due to Python 3.10 (`asyncio.timeout`). Expected to pass on Mac 3.14; not verified.
- **1 real failure:** `tests/agents/test_agent_logic.py::test_tuning_targets_the_twitchy_axis_with_evidence`. After applying the tuning patch to the twitchy FakeDesk, A/D flickers only go 4 → 3, and the test requires a drop of more than half. Either the tuning target is too low (`max(on+5, p50*1.6+4)` capped at `0.85*reach`), the per-axis lr thresholds aren't being applied in the controller path used by FakeDesk, or the sim's wobble (13.5° sine plus ±26° turns) still crosses the new OFF threshold. Investigate with:
  ```python
  from agents.desk_link import FakeDesk; from agents.tuning import plan_tuning
  d=FakeDesk("twitchy"); tel=d.service.handle({"op":"telemetry","window_s":60})["result"]
  p=plan_tuning(tel,"less",None); print(p.patch)
  d.service.handle({"op":"set_config","patch":p.patch,"actor":"t"}); d.telemetry.reset(); d.advance(60)
  print(d.service.handle({"op":"telemetry","window_s":60})["result"]["keys"])
  ```
- No tests cover the new `run.py` launcher, `demo_desk.py` or `local_resolver.py` yet.

## 9. Next steps (priority)
1. **Fix Coach ↔ specialist messaging** (section 7). On the Mac: Ctrl+C, rerun `DESK_DEMO_MODE=1 python -m agents.run`, chat "set up desk for a racing game", and read the `send to setup:` log line.
2. Fix the tuning flicker test.
3. Add the **Validator agent** (5th agent; auto-verify and auto-undo after changes).
4. **ASI Interactive Cards** for the confirm/apply buttons (`cards.py` already builds card data; check it renders in ASI:One per the Fetch docs).
5. Connect to real camera tilt data: run `python -m backend.tilt_keys.run --control --input ws` and start the agents without `DESK_DEMO_MODE`.
6. Commit and push, top-level README (agent names, addresses, badges, run steps), demo video, Devpost and ASI:One submission.

## 10. Gotchas
- In ASI:One, make sure **To: DESK Coach** (agent1...n4vw), not your personal "DESK @desk" assistant. That one is a generic LLM and knows nothing about the project.
- The terminal running the agents must stay open; laptop sleep stops them.
- Don't use Agentverse's "Launch an Agent → choose stack" page; that needs a public endpoint. The mailbox via the Inspector is the right path.
- Never commit `.env`, `agents/.seed`, or `.venv`.
