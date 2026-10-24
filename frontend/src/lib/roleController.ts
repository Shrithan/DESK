import type { HeldKey, RoleProfile } from "./roleProfiles";

export interface Position3 {
  x: number;
  y: number;
  z: number;
}

export interface KeyTransition {
  key: HeldKey;
  down: boolean;
}

interface Assignment {
  objectId: string;
  profile: RoleProfile;
  center: Position3;
}

/**
 * Tracks voice-assigned object->role mappings and turns live position
 * updates into held-key transitions, with per-binding hysteresis so a
 * displacement hovering near the threshold doesn't chatter the key.
 */
export class RoleController {
  private assignments = new Map<string, Assignment>();
  private activeBindings = new Set<string>(); // `${objectId}:${binding.id}`

  assign(objectId: string, profile: RoleProfile, center: Position3): KeyTransition[] {
    const released = this.unassign(objectId);
    this.assignments.set(objectId, { objectId, profile, center });
    return released;
  }

  unassign(objectId: string): KeyTransition[] {
    const assignment = this.assignments.get(objectId);
    if (!assignment) return [];
    this.assignments.delete(objectId);

    const transitions: KeyTransition[] = [];
    for (const binding of assignment.profile.bindings) {
      const activeId = `${objectId}:${binding.id}`;
      if (this.activeBindings.has(activeId)) {
        this.activeBindings.delete(activeId);
        transitions.push({ key: binding.key, down: false });
      }
    }
    return transitions;
  }

  getAssignment(objectId: string): RoleProfile | null {
    return this.assignments.get(objectId)?.profile ?? null;
  }

  assignedObjectIds(): string[] {
    return [...this.assignments.keys()];
  }

  /** Feed a live position for an assigned object; returns any key transitions this update triggers. */
  update(objectId: string, pos: Position3): KeyTransition[] {
    const assignment = this.assignments.get(objectId);
    if (!assignment) return [];

    const transitions: KeyTransition[] = [];
    for (const binding of assignment.profile.bindings) {
      const activeId = `${objectId}:${binding.id}`;
      const displacement = (pos[binding.axis] - assignment.center[binding.axis]) * binding.sign;
      const isActive = this.activeBindings.has(activeId);

      if (!isActive && displacement > binding.onThresholdM) {
        this.activeBindings.add(activeId);
        transitions.push({ key: binding.key, down: true });
      } else if (isActive && displacement < binding.offThresholdM) {
        this.activeBindings.delete(activeId);
        transitions.push({ key: binding.key, down: false });
      }
    }
    return transitions;
  }

  releaseAllFor(objectId: string): KeyTransition[] {
    return this.unassign(objectId);
  }
}
