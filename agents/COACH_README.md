# DESK Coach

![tag:innovationlab](https://img.shields.io/badge/innovationlab-3D8BD3)
![tag:hackathon](https://img.shields.io/badge/hackathon-5F43F1)

DESK turns tilting an ordinary object (a soda can, a mug) into keyboard keys, so you can play any game with whatever is on your desk. Two phone cameras measure the tilt; DESK holds W/A/S/D or the arrow keys.

**DESK Coach** sets up, tunes and repairs DESK from chat, using live data from the player's computer.

## What you can ask
- "Set up DESK for a racing game" / "for Subway Surfers": picks keys and sensitivity, shows the plan, applies it after you approve.
- "The steering is too twitchy" / "it's not responding": reads the last 60 seconds of real tilt data, retunes the triggers, shows the evidence, and can measure afterwards whether it helped.
- "It keeps stopping" / "what's wrong?": health check for camera tracking, calibration, frame rate and flicker, with concrete fixes.
- "Recalibrate", "pause", "resume", "undo", "show my settings".

## How it works
DESK Coach coordinates three specialist agents: the **Setup agent** (game profiles, key remaps), the **Tuning agent** (data-driven sensitivity) and the **Doctor agent** (diagnosis). Each reply shows which agent did the work and the steps it took. Every change is validated against safe limits, released keys are guaranteed during changes, and every change can be undone.
