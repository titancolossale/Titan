/** Titan Frontend V2 — Central state store (Phase E1 wiring). */

/** @typedef {"idle"|"listening"|"thinking"|"streaming"|"speaking"|"working"|"planning"|"error"} PresenceState */

/** @typedef {"chat"|"projects"|"memory"|"obsidian"|"browser"|"trading"|"calendar"|"tools"|"voice"|"settings"} RouteKey */

/**
 * @typedef {Object} AppState
 * @property {RouteKey} route
 * @property {PresenceState} presence
 * @property {string} cognitiveState
 * @property {boolean} settingsOpen
 * @property {boolean} orchestratorDrawerOpen
 * @property {boolean} sidebarDrawerOpen
 * @property {boolean} sidebarPinned
 * @property {boolean} contextPanelOpen
 * @property {number} contextPanelWidth
 * @property {string} activeWorkspace
 * @property {string} activeProject
 * @property {number} notificationCount
 * @property {boolean} reducedMotion
 * @property {boolean} highContrast
 * @property {100|112|125} fontScale
 * @property {string} viewportMode
 * @property {boolean} bootComplete
 * @property {string | null} activePanelId
 * @property {number} activeToolCount
 * @property {string[]} activeToolIds
 * @property {string | null} dominantToolId
 * @property {string} toolStatusLine
 * @property {string} memoryStatusLine
 * @property {boolean} recallActive
 * @property {number} activeMemoryCount
 * @property {string | null} memoryEventType
 * @property {boolean} conversationActive
 * @property {string | null} conversationStage
 * @property {string | null} conversationEventType
 * @property {string} conversationStatusLine
 * @property {string} conversationThinkingLine
 * @property {string} conversationReasoningLine
 * @property {string[]} conversationPlanSteps
 * @property {string | null} pipelineStage
 * @property {string} pipelineLabel
 * @property {boolean} pipelineThinking
 * @property {string | null} systemVersion
 * @property {number} presenceLevel
 * @property {string | null} conversationId
 * @property {string | null} lastRequestId
 * @property {string | null} detectedIntent
 * @property {number | null} orchestrationConfidence
 * @property {object | null} systemsUsed
 * @property {string} reasoningSummary
 * @property {number | null} orchestrationDuration
 * @property {boolean} approvalRequired
 * @property {string | null} approvalId
 * @property {string | null} approvalSummary
 * @property {boolean} devMetadataOpen
 * @property {boolean} showFpsOverlay
 * @property {"auto"|"performance"|"balanced"|"cinematic"} visualQuality
 * @property {string | null} lastError
 * @property {string} connectionState
 * @property {string[] | null} runtimeStages
 * @property {boolean | null} runtimeMemoryUsed
 * @property {string[] | null} runtimeToolsUsed
 * @property {string | null} runtimeModel
 * @property {number | null} clientFps
 * @property {number | null} clientFrameMs
 * @property {boolean} chatPending
 * @property {number | null} chatElapsedMs
 * @property {string | null} chatStage
 * @property {number | null} lastHttpStatus
 * @property {number | null} providerDurationMs
 */

/** @type {AppState} */
const DEFAULT_STATE = Object.freeze({
  route: "chat",
  presence: "idle",
  cognitiveState: "idle",
  settingsOpen: false,
  orchestratorDrawerOpen: false,
  sidebarDrawerOpen: false,
  sidebarPinned: true,
  contextPanelOpen: false,
  contextPanelWidth: 340,
  activeWorkspace: "Titan OS",
  activeProject: "Titan",
  notificationCount: 0,
  reducedMotion: false,
  highContrast: false,
  fontScale: 100,
  viewportMode: "desktop",
  bootComplete: false,
  activePanelId: "chat",
  activeToolCount: 0,
  activeToolIds: [],
  dominantToolId: null,
  toolStatusLine: "Outils — aucune activité",
  memoryStatusLine: "Mémoire — en veille",
  recallActive: false,
  activeMemoryCount: 0,
  memoryEventType: null,
  conversationActive: false,
  conversationStage: null,
  conversationEventType: null,
  conversationStatusLine: "Conversation — en veille",
  conversationThinkingLine: "",
  conversationReasoningLine: "",
  conversationPlanSteps: [],
  pipelineStage: null,
  pipelineLabel: "",
  pipelineThinking: false,
  systemVersion: null,
  presenceLevel: 42,
  conversationId: null,
  lastRequestId: null,
  detectedIntent: null,
  orchestrationConfidence: null,
  systemsUsed: null,
  reasoningSummary: "",
  orchestrationDuration: null,
  approvalRequired: false,
  approvalId: null,
  approvalSummary: null,
  devMetadataOpen: false,
  showFpsOverlay: false,
  visualQuality: "auto",
  lastError: null,
  connectionState: "disconnected",
  runtimeStages: null,
  runtimeMemoryUsed: null,
  runtimeToolsUsed: null,
  runtimeModel: null,
  clientFps: null,
  clientFrameMs: null,
  chatPending: false,
  chatElapsedMs: null,
  chatStage: null,
  lastHttpStatus: null,
  providerDurationMs: null,
});

export class StateStore {
  constructor(initial = {}) {
    /** @type {AppState} */
    this._state = { ...DEFAULT_STATE, ...initial };
    /** @type {Map<string, Set<(state: AppState, patch: Partial<AppState>) => void>>} */
    this._listeners = new Map();
  }

  /** @returns {Readonly<AppState>} */
  getState() {
    return this._state;
  }

  /** @param {Partial<AppState>} patch */
  setState(patch) {
    const prev = this._state;
    this._state = { ...prev, ...patch };
    this._emit(prev, patch);
  }

  /** @param {(state: AppState) => Partial<AppState>} updater */
  update(updater) {
    this.setState(updater(this._state));
  }

  /**
   * Subscribe to state changes.
   * @param {(state: AppState, patch: Partial<AppState>) => void} listener
   * @param {string} [key="*"]
   * @returns {() => void}
   */
  subscribe(listener, key = "*") {
    if (!this._listeners.has(key)) {
      this._listeners.set(key, new Set());
    }
    this._listeners.get(key).add(listener);
    return () => {
      this._listeners.get(key)?.delete(listener);
    };
  }

  /** @param {AppState} prev @param {Partial<AppState>} patch */
  _emit(prev, patch) {
    for (const listener of this._listeners.get("*") ?? []) {
      listener(this._state, patch);
    }

    for (const field of Object.keys(patch)) {
      for (const listener of this._listeners.get(field) ?? []) {
        listener(this._state, patch);
      }
    }
  }
}

export { DEFAULT_STATE };
