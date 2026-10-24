# DESK Coach

![tag:innovationlab](https://img.shields.io/badge/innovationlab-3D8BD3)
![tag:hackathon](https://img.shields.io/badge/hackathon-5F43F1)

DESK turns tilt-angle input from an ordinary object into keyboard keys. DESK holds W/A/S/D or the arrow keys. It runs on the live overhead-camera can joystick (`python -m tilt_joystick --control`), or on a simulated player for demos.

**DESK Coach** sets up, tunes and repairs DESK from chat, using live data from the player's computer.

## What you can ask
- "Set up DESK for a racing game" / "for Subway Surfers": picks keys and sensitivity, shows the plan, applies it after you approve.
- "The steering is too twitchy" / "it's not responding": reads the last 60 seconds of real tilt data, retunes the triggers, shows the evidence, and can measure afterwards whether it helped.
- "It keeps stopping" / "what's wrong?": health check for camera tracking, calibration, frame rate and flicker, with concrete fixes.
- "Recalibrate", "pause", "resume", "undo", "show my settings".

## How it works
DESK Coach coordinates four specialist agents: **Setup** (game profiles and key remaps), **Tuner** (data-driven sensitivity), **Doctor** (diagnosis), and **Validator** (20-second post-change checks with conditional rollback). Each reply shows which agent did the work and the steps it took. Settings changes are checked against safe limits, held keys are released during changes, and changes can be undone.
