"""Game profiles the Setup agent can apply. Plain data, no I/O."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Profile:
    id: str
    name: str
    aliases: tuple[str, ...]
    keys: dict[str, str]  # slot -> key: forward, back, left, right
    on_deg: float
    off_deg: float
    lr_on_deg: float | None = None
    lr_off_deg: float | None = None
    why: str = ""

    def patch(self) -> dict:
        patch: dict = {"keys": dict(self.keys), "on_threshold_deg": self.on_deg, "off_threshold_deg": self.off_deg,
                       "lr_on_threshold_deg": self.lr_on_deg, "lr_off_threshold_deg": self.lr_off_deg}
        return patch

    def rows(self) -> list[tuple[str, str]]:
        k = self.keys
        lr_on = self.lr_on_deg if self.lr_on_deg is not None else self.on_deg
        return [
            ("Tilt forward", _label(k["forward"])),
            ("Tilt back", _label(k["back"])),
            ("Tilt left", _label(k["left"])),
            ("Tilt right", _label(k["right"])),
            ("Forward/back trigger", f"{self.on_deg:g}° (release under {self.off_deg:g}°)"),
            ("Left/right trigger", f"{lr_on:g}°"),
        ]


WASD = {"forward": "w", "back": "s", "left": "a", "right": "d"}
ARROWS = {"forward": "up", "back": "down", "left": "left", "right": "right"}

PROFILES: dict[str, Profile] = {p.id: p for p in [
    Profile("racing", "Racing game", ("racing", "race", "car", "driving", "drive", "kart"), WASD, 15, 10, 18, 13,
            why="Steering gets a slightly higher trigger than gas/brake, because small left-right wobbles are the most common accidental input when driving."),
    Profile("subway-surfers", "Subway Surfers", ("subway surfers", "subway", "endless runner", "temple run", "runner"), ARROWS, 18, 12,
            why="Each tilt is a single lane change or jump, so a higher trigger prevents double moves."),
    Profile("minecraft", "Minecraft", ("minecraft",), WASD, 15, 10,
            why="Standard WASD walking with default sensitivity."),
    Profile("pac-man", "Pac-Man", ("pac-man", "pacman", "pac man", "snake", "slither"), ARROWS, 14, 9,
            why="Maze games need quick, light turns, so the trigger is a little lower."),
    Profile("wasd", "Any WASD game", ("wasd", "default", "generic", "keyboard game"), WASD, 15, 10),
    Profile("arrows", "Any arrow-key game", ("arrow", "arrows", "arrow keys"), ARROWS, 15, 10),
]}


def find_profile(text: str | None) -> Profile | None:
    if not text:
        return None
    t = text.lower()
    if t in PROFILES:
        return PROFILES[t]
    best: tuple[int, Profile] | None = None
    for p in PROFILES.values():
        for alias in p.aliases:
            if alias in t and (best is None or len(alias) > best[0]):
                best = (len(alias), p)
    return best[1] if best else None


def custom_profile(key_style: str, sensitivity: str) -> Profile:
    keys = ARROWS if "arrow" in (key_style or "").lower() else WASD
    on, off = {"low": (22.0, 16.0), "high": (11.0, 7.0)}.get((sensitivity or "").lower(), (15.0, 10.0))
    return Profile("custom", "Custom setup", (), keys, on, off, why=f"{'Arrow keys' if keys is ARROWS else 'WASD'}, {sensitivity or 'normal'} sensitivity.")


def _label(key: str) -> str:
    return {"up": "↑ Up arrow", "down": "↓ Down arrow", "left": "← Left arrow", "right": "→ Right arrow",
            "space": "Space"}.get(key, key.upper())
