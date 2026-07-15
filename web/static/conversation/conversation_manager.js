/**
 * Titan Conversation Manager — premium chat experience orchestrator (Phase 17.5)
 *
 * Coordinates storage, rendering, streaming, neural brain hooks, and composer UX.
 * Future hooks: voice, browser, calendar, trading — memory wired in Phase 17.9.
 */
(function (global) {
  "use strict";

  var StreamStates = TitanStreamController.STATES;

  function ConversationManager(options) {
    this.messagesEl = options.messagesEl;
    this.inputEl = options.inputEl;
    this.sendBtn = options.sendBtn;
    this.stopBtn = options.stopBtn;
    this.thinkingEl = options.thinkingEl;
    this.zoneEl = options.zoneEl;

    this.apiFetch = options.apiFetch;
    this.getPresenceController = options.getPresenceController || function () {
      return null;
    };
    this.getToolActivityManager = options.getToolActivityManager || function () {
      return null;
    };
    this.getMemoryActivityManager = options.getMemoryActivityManager || function () {
      return null;
    };
    this.onActivity = options.onActivity || null;
    this.onResponseComplete = options.onResponseComplete || null;
    this.onOrchestratorProgress = options.onOrchestratorProgress || null;
    this.validateBeforeSend = options.validateBeforeSend || null;

    this.storage = new TitanChatStorage(options.storageOptions || {});
    this.renderer = new TitanMessageRenderer({ container: this.messagesEl });
    this.stream = new TitanStreamController({
      simulateStreaming: options.simulateStreaming !== false,
      chunkDelayMs: options.chunkDelayMs || 18,
      onStateChange: this._onStreamStateChange.bind(this),
      onToken: this._onStreamToken.bind(this),
      onComplete: this._onStreamComplete.bind(this),
      onError: this._onStreamError.bind(this),
      onInterrupt: this._onStreamInterrupt.bind(this),
    });

    this._activeTitanMessageId = null;
    this._activeTitanElement = null;
    this._voiceHooks = null;
    this._composerMaxHeight = options.composerMaxHeight || 160;

    this._bindComposer();
    this._restoreSession();
  }

  ConversationManager.prototype._restoreSession = function () {
    var messages = this.storage.getMessages();
    if (messages.length === 0) {
      return;
    }
    this.renderer.renderAll(messages);
    this.renderer.scrollToBottom(false);
  };

  ConversationManager.prototype._bindComposer = function () {
    var self = this;

    if (this.sendBtn) {
      this.sendBtn.addEventListener("click", function () {
        self.send();
      });
    }

    if (this.stopBtn) {
      this.stopBtn.addEventListener("click", function () {
        self.interrupt();
      });
    }

    if (this.inputEl) {
      this.inputEl.addEventListener("keydown", function (event) {
        if (event.key === "Enter" && !event.shiftKey) {
          event.preventDefault();
          self.send();
        }
      });

      this.inputEl.addEventListener("input", function () {
        self._autoGrowInput();
      });
    }
  };

  ConversationManager.prototype._autoGrowInput = function () {
    if (!this.inputEl) {
      return;
    }
    this.inputEl.style.height = "auto";
    var next = Math.min(this.inputEl.scrollHeight, this._composerMaxHeight);
    this.inputEl.style.height = next + "px";
  };

  ConversationManager.prototype._resetInput = function () {
    if (!this.inputEl) {
      return;
    }
    this.inputEl.value = "";
    this.inputEl.style.height = "auto";
  };

  ConversationManager.prototype._setInputEnabled = function (enabled) {
    if (this.inputEl) {
      this.inputEl.disabled = !enabled;
      this.zoneEl.classList.toggle("tdl-conversation--disabled", !enabled);
    }
    if (this.sendBtn) {
      this.sendBtn.disabled = !enabled;
    }
  };

  ConversationManager.prototype._setThinkingVisible = function (visible) {
    if (this.thinkingEl) {
      this.thinkingEl.hidden = !visible;
      this.thinkingEl.classList.toggle("tdl-conversation__thinking--visible", visible);
    }
  };

  ConversationManager.prototype._onStreamStateChange = function (state) {
    var thinking =
      state === StreamStates.THINKING || state === StreamStates.STREAMING;
    this._setInputEnabled(!thinking);

    if (this.stopBtn) {
      this.stopBtn.hidden = state !== StreamStates.STREAMING;
    }

    var presence = this.getPresenceController();
    if (this._voiceHooks && state === StreamStates.STREAMING && presence && presence.engine) {
      if (presence.engine.setSpeaking) {
        presence.engine.setSpeaking({ source: "voice", streamPhase: "streaming" });
      }
      return;
    }
    if (
      this._voiceHooks &&
      (state === StreamStates.FINISHED || state === StreamStates.IDLE)
    ) {
      return;
    }
    if (presence && presence.handleStreamState) {
      presence.handleStreamState(state);
    } else {
      this._setThinkingVisible(state === StreamStates.THINKING);
    }
  };

  ConversationManager.prototype._onStreamToken = function (_token, accumulated) {
    if (!this._activeTitanMessageId) {
      return;
    }
    this.storage.updateMessage(this._activeTitanMessageId, {
      content: accumulated,
      status: "streaming",
    });
    if (this._activeTitanElement) {
      this.renderer.updateMessageContent(
        this._activeTitanElement,
        accumulated,
        "titan"
      );
      this.renderer.setStreamingState(this._activeTitanElement, true);
      this.renderer.scrollToBottom(true);
    }
    if (this._voiceHooks && this._voiceHooks.onStreamToken) {
      this._voiceHooks.onStreamToken(_token, accumulated);
    }
  };

  ConversationManager.prototype._onStreamComplete = function (finalText) {
    if (!this._activeTitanMessageId) {
      return;
    }
    this.storage.updateMessage(this._activeTitanMessageId, {
      content: finalText,
      status: "complete",
    });
    if (this._activeTitanElement) {
      this.renderer.updateMessageContent(
        this._activeTitanElement,
        finalText,
        "titan"
      );
      this.renderer.setStreamingState(this._activeTitanElement, false);
      this.renderer.scrollToBottom(true);
    }

    var presence = this.getPresenceController();
    if (presence && presence.notifyResponseComplete) {
      presence.notifyResponseComplete();
    }

    var toolActivity = this.getToolActivityManager();
    if (toolActivity) {
      toolActivity.endTurn();
    }

    var memoryActivity = this.getMemoryActivityManager();
    if (memoryActivity) {
      memoryActivity.endTurn();
    }

    if (this.onResponseComplete) {
      this.onResponseComplete(finalText);
    }

    if (this._voiceHooks && this._voiceHooks.onStreamComplete) {
      this._voiceHooks.onStreamComplete(finalText);
    }
    this._voiceHooks = null;

    this._activeTitanMessageId = null;
    this._activeTitanElement = null;
  };

  ConversationManager.prototype._onStreamError = function (error) {
    this._appendTitanSystemMessage(
      "Erreur : " + (error && error.message ? error.message : String(error))
    );
    this._activeTitanMessageId = null;
    this._activeTitanElement = null;
    this._voiceHooks = null;
  };

  ConversationManager.prototype._onStreamInterrupt = function (partial) {
    if (this._activeTitanMessageId) {
      var content = partial || "…";
      this.storage.updateMessage(this._activeTitanMessageId, {
        content: content,
        status: "interrupted",
      });
      if (this._activeTitanElement) {
        this.renderer.updateMessageContent(
          this._activeTitanElement,
          content,
          "titan"
        );
        this.renderer.setStreamingState(this._activeTitanElement, false);
        this._activeTitanElement.classList.add("tdl-msg--interrupted");
      }
    }
    if (this._voiceHooks && this._voiceHooks.onStreamInterrupt) {
      this._voiceHooks.onStreamInterrupt(partial);
    }
    this._activeTitanMessageId = null;
    this._activeTitanElement = null;
    this._voiceHooks = null;
  };

  ConversationManager.prototype._appendUserMessage = function (text) {
    var entry = this.storage.addMessage({
      role: "user",
      content: text,
      status: "complete",
    });
    this.renderer.append(entry);
    this.renderer.scrollToBottom(true);
    return entry;
  };

  ConversationManager.prototype._beginTitanMessage = function () {
    var entry = this.storage.addMessage({
      role: "titan",
      content: "",
      status: "streaming",
    });
    this._activeTitanMessageId = entry.id;
    this._activeTitanElement = this.renderer.append(entry);
    this.renderer.scrollToBottom(true);
    return entry;
  };

  ConversationManager.prototype._appendTitanSystemMessage = function (text) {
    var entry = this.storage.addMessage({
      role: "titan",
      content: text,
      status: "complete",
    });
    this.renderer.append(entry);
    this.renderer.scrollToBottom(true);
    return entry;
  };

  ConversationManager.prototype.send = async function () {
    if (!this.inputEl || this.stream.isActive()) {
      return;
    }

    if (this.validateBeforeSend && !this.validateBeforeSend()) {
      this._appendTitanSystemMessage(
        "Configure ta clé secrète dans Paramètres avant d'envoyer un message."
      );
      return;
    }

    var message = this.inputEl.value.trim();
    if (!message) {
      return;
    }

    this._resetInput();
    await this._dispatchMessage(message);
  };

  ConversationManager.prototype.sendFromVoice = async function (message, voiceHooks) {
    if (!message || this.stream.isActive()) {
      return;
    }

    if (this.validateBeforeSend && !this.validateBeforeSend()) {
      return;
    }

    this._voiceHooks = voiceHooks || null;
    await this._dispatchMessage(message, { source: "voice" });
  };

  ConversationManager.prototype._dispatchMessage = async function (message, meta) {
    var source = (meta && meta.source) || "text";
    this._appendUserMessage(message);

    var toolActivity = this.getToolActivityManager();
    var turnId = toolActivity ? toolActivity.beginTurn() : null;

    var memoryActivity = this.getMemoryActivityManager();
    if (memoryActivity) {
      memoryActivity.beginTurn(turnId);
      memoryActivity.beginRecall({ source: "long_term" });
    }

    if (this.onActivity) {
      this.onActivity(source === "voice" ? "Message vocal envoyé" : "Message envoyé");
    }

    var presence = this.getPresenceController();
    if (presence && presence.notifyChatRequest) {
      presence.notifyChatRequest();
    }

    if (this.onOrchestratorProgress) {
      this.onOrchestratorProgress(null, { phase: "thinking" });
    }

    var signal = this.stream.startThinking();

    try {
      var result = await this.apiFetch("/chat", {
        method: "POST",
        body: JSON.stringify({ message: message }),
        signal: signal,
      });

      var responseText = (result && result.response) || "(réponse vide)";
      var activities = (result && result.tool_activity) || [];
      var memoryActivities = (result && result.memory_activity) || [];
      var orchestratorProgress = (result && result.orchestrator_progress) || [];

      if (this.onOrchestratorProgress) {
        this.onOrchestratorProgress(orchestratorProgress, { phase: "complete" });
      }

      this._beginTitanMessage();

      if (memoryActivity && memoryActivities.length > 0) {
        await memoryActivity.ingestAnimated(memoryActivities, { stepDelayMs: 140 });
      }

      if (toolActivity && activities.length > 0) {
        toolActivity.ingestAnimated(activities, { stepDelayMs: 90 });
      }

      if (source === "voice" && presence && presence.engine) {
        if (presence.engine.setSpeaking) {
          presence.engine.setSpeaking({ source: "voice" });
        } else if (presence.notifyStreamPhase) {
          presence.notifyStreamPhase("speaking");
        }
      }

      this.stream.simulateFromText(responseText);

      if (this.onActivity) {
        this.onActivity("Titan a répondu");
      }
    } catch (err) {
      if (toolActivity && turnId) {
        toolActivity.endTurn();
      }
      var memoryActivity = this.getMemoryActivityManager();
      if (memoryActivity) {
        memoryActivity.endTurn();
      }
      if (err && err.name === "AbortError") {
        return;
      }
      this.stream.failStream(err);
      if (this._activeTitanMessageId) {
        this.storage.updateMessage(this._activeTitanMessageId, {
          content: "Erreur : " + err.message,
          status: "error",
        });
        if (this._activeTitanElement) {
          this.renderer.updateMessageContent(
            this._activeTitanElement,
            "Erreur : " + err.message,
            "titan"
          );
        }
      } else {
        this._appendTitanSystemMessage("Erreur : " + err.message);
      }
      this._activeTitanMessageId = null;
      this._activeTitanElement = null;
      this._voiceHooks = null;
    }
  };

  ConversationManager.prototype.interrupt = function () {
    this.stream.interrupt();
  };

  ConversationManager.prototype.clearSession = function () {
    this.storage.clear();
    if (this.messagesEl) {
      this.messagesEl.innerHTML = "";
    }
  };

  /* --- Future capability hooks (Phase 18+) --- */

  ConversationManager.prototype.hookVoice = function (payload) {
    var presence = this.getPresenceController();
    if (presence && presence.hookVoice) {
      presence.hookVoice(payload);
    }
  };

  ConversationManager.prototype.hookBrowser = function (payload) {
    var presence = this.getPresenceController();
    if (presence && presence.hookBrowser) {
      presence.hookBrowser(payload);
    }
  };

  ConversationManager.prototype.hookCalendar = function (payload) {
    var presence = this.getPresenceController();
    if (presence && presence.hookCalendar) {
      presence.hookCalendar(payload);
    }
  };

  ConversationManager.prototype.hookTrading = function (payload) {
    var presence = this.getPresenceController();
    if (presence && presence.hookTrading) {
      presence.hookTrading(payload);
    }
  };

  ConversationManager.prototype.hookMemoryRetrieval = function (payload) {
    var memoryActivity = this.getMemoryActivityManager();
    if (memoryActivity) {
      memoryActivity.beginRecall(payload || { source: "long_term" });
      return;
    }
    var presence = this.getPresenceController();
    if (presence && presence.hookMemoryRetrieval) {
      presence.hookMemoryRetrieval(payload);
    }
  };

  global.TitanConversationManager = ConversationManager;
})(window);
