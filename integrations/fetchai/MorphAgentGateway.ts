import type { WorldState } from "../../shared/contracts/types";

export interface AgentStatus {
  agentId: string;
  online: boolean;
  lastHeartbeatMs: number | null;
}

export interface InterfaceConfig {
  showTrails: boolean;
  narrationEnabled: boolean;
}

/**
 * Seam for a future Fetch.ai (Agentverse/uAgents/ASI:One) integration.
 * Entirely mocked right now — no registration, no discoverability, no real
 * protocol. A dedicated Morph agent owner should take this over for sponsor
 * eligibility; a generic LLM call is explicitly NOT equivalent to that and
 * must not be presented as such.
 */
export interface MorphAgentGateway {
  readonly mode: "mock" | "live";
  getWorldState(sessionId: string): Promise<WorldState | null>;
  requestInterfaceConfig(sessionId: string): Promise<InterfaceConfig>;
  getAgentStatus(): Promise<AgentStatus>;
  applyInterfaceConfig(sessionId: string, config: InterfaceConfig): Promise<void>;
}

export class MockMorphAgentGateway implements MorphAgentGateway {
  readonly mode = "mock" as const;
  private config: InterfaceConfig = { showTrails: true, narrationEnabled: true };

  async getWorldState(): Promise<WorldState | null> {
    return null; // Real world state flows over /ws/world, not through this gateway.
  }

  async requestInterfaceConfig(): Promise<InterfaceConfig> {
    return this.config;
  }

  async getAgentStatus(): Promise<AgentStatus> {
    return { agentId: "mock-morph-agent", online: false, lastHeartbeatMs: null };
  }

  async applyInterfaceConfig(_sessionId: string, config: InterfaceConfig): Promise<void> {
    this.config = config;
  }
}

export function createMorphAgentGateway(): MorphAgentGateway {
  return new MockMorphAgentGateway();
}
