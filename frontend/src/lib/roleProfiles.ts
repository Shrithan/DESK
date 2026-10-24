export type HeldKey = "w" | "a" | "s" | "d" | "space";

export interface DirectionalBinding {
  /** Unique within a profile, e.g. "steer-right". */
  id: string;
  axis: "x" | "y" | "z";
  /** Which sign of (position - center) on that axis engages this binding. */
  sign: 1 | -1;
  key: HeldKey;
  /** Displacement (meters) past which the key engages. */
  onThresholdM: number;
  /** Displacement below which the key releases. Must be < onThresholdM (hysteresis). */
  offThresholdM: number;
}

export interface RoleProfile {
  id: string;
  label: string;
  description: string;
  /** Lowercase substrings matched against the voice transcript. */
  matchPhrases: string[];
  bindings: DirectionalBinding[];
}

const ON = 0.08;
const OFF = 0.04;

export const ROLE_PROFILES: RoleProfile[] = [
  {
    id: "steering_wheel",
    label: "Steering wheel",
    description: "Lean left/right of center to hold A/D.",
    matchPhrases: ["steering wheel", "steering", "wheel"],
    bindings: [
      { id: "steer-right", axis: "x", sign: 1, key: "d", onThresholdM: ON, offThresholdM: OFF },
      { id: "steer-left", axis: "x", sign: -1, key: "a", onThresholdM: ON, offThresholdM: OFF },
    ],
  },
  {
    id: "gas_pedal",
    label: "Gas pedal",
    description: "Push away from you to hold W.",
    matchPhrases: ["gas pedal", "accelerator", "throttle", "gas"],
    bindings: [{ id: "accelerate", axis: "y", sign: 1, key: "w", onThresholdM: ON, offThresholdM: OFF }],
  },
  {
    id: "brake",
    label: "Brake",
    description: "Pull toward you to hold S.",
    matchPhrases: ["brake pedal", "brake"],
    bindings: [{ id: "brake", axis: "y", sign: -1, key: "s", onThresholdM: ON, offThresholdM: OFF }],
  },
  {
    id: "jump_button",
    label: "Jump button",
    description: "Lift up to hold Space.",
    matchPhrases: ["jump button", "jump", "horn", "button"],
    bindings: [{ id: "jump", axis: "z", sign: 1, key: "space", onThresholdM: ON, offThresholdM: OFF }],
  },
];

/**
 * Keyword matching, not a language model — a transcript like "this is a
 * steering wheel for this game" matches on the substring "steering wheel".
 * Longer/more specific phrases are checked first so "gas pedal" doesn't
 * fall through to a shorter unrelated match.
 */
export function matchRoleProfile(transcript: string): RoleProfile | null {
  const lower = transcript.toLowerCase();
  const candidates = ROLE_PROFILES.flatMap((profile) =>
    profile.matchPhrases.map((phrase) => ({ profile, phrase })),
  ).sort((a, b) => b.phrase.length - a.phrase.length);

  for (const { profile, phrase } of candidates) {
    if (lower.includes(phrase)) return profile;
  }
  return null;
}
