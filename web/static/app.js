(function () {
  "use strict";

  var AUTH_STORAGE_KEY = "titan_web_secret_key";
  var PLACEHOLDER_VIEWS = ["calendar", "trading"];

  var secretInput = document.getElementById("secret-key");
  var authGate = document.getElementById("auth-gate");
  var authGateKey = document.getElementById("auth-gate-key");
  var authGateError = document.getElementById("auth-gate-error");
  var authGateSubmit = document.getElementById("auth-gate-submit");
  var chatInput = document.getElementById("chat-input");
  var workspace = document.getElementById("workspace");
  var chatZone = document.getElementById("chat-zone");
  var chatMessages = document.getElementById("chat-messages");
  var settingsPanel = document.getElementById("settings-panel");
  var neuralCanvas = document.getElementById("neural-canvas");
  var mainNav = document.getElementById("main-nav");

  var barThinking = document.getElementById("bar-thinking");
  var barMemory = document.getElementById("bar-memory");
  var barBrain = document.getElementById("bar-brain");
  var barSystem = document.getElementById("bar-system");
  var barUser = document.getElementById("bar-user");
  var dotThinking = document.getElementById("dot-thinking");

  var recentActivity = document.getElementById("recent-activity");
  var currentProjects = document.getElementById("current-projects");
  var statusState = document.getElementById("status-state");
  var statusMission = document.getElementById("status-mission");
  var statusTools = document.getElementById("status-tools");
  var systemVersion = document.getElementById("system-version");

  var neuralNetwork = null;
  var conversation = null;
  var presence = null;
  var voice = null;
  var toolActivity = null;
  var toolTimeline = null;
  var toolProgress = null;
  var memoryActivity = null;
  var memoryVisualizer = null;
  var memoryCards = null;
  var explorationCards = null;
  var orchestratorPanel = null;
  var referenceShell = null;
  var soundHooks = null;
  var launchSequence = null;
  var cachedUserName = "Nolan";
  var currentView = "chat";
  var statusPollTimer = null;

  function loadStoredAuth() {
    try {
      return localStorage.getItem(AUTH_STORAGE_KEY) || "";
    } catch (_err) {
      return "";
    }
  }

  function saveStoredAuth(value) {
    try {
      if (value) {
        localStorage.setItem(AUTH_STORAGE_KEY, value);
      } else {
        localStorage.removeItem(AUTH_STORAGE_KEY);
      }
    } catch (_err) {
      /* ignore storage errors */
    }
  }

  function authHeaders() {
    var key = secretInput.value.trim() || loadStoredAuth();
    if (!key) {
      return {};
    }
    return { Authorization: "Bearer " + key };
  }

  async function fetchAuthStatus() {
    var response = await fetch("/auth/status");
    if (!response.ok) {
      throw new Error("Impossible de contacter le serveur Titan.");
    }
    return response.json();
  }

  async function verifyAuthToken(token) {
    if (!token) {
      return false;
    }
    try {
      var response = await fetch("/auth/verify", {
        method: "POST",
        headers: { Authorization: "Bearer " + token },
      });
      return response.ok;
    } catch (_err) {
      return false;
    }
  }

  function showAuthGate() {
    if (!authGate) {
      return Promise.resolve();
    }
    authGate.hidden = false;
    return new Promise(function (resolve) {
      function finish() {
        authGate.hidden = true;
        resolve();
      }

      async function submit() {
        var token = authGateKey.value.trim();
        if (!token) {
          authGateError.textContent = "La clé secrète est requise.";
          authGateError.hidden = false;
          authGateKey.focus();
          return;
        }
        authGateSubmit.disabled = true;
        authGateError.hidden = true;
        var ok = await verifyAuthToken(token);
        if (!ok) {
          authGateError.textContent = "Clé secrète incorrecte.";
          authGateError.hidden = false;
          authGateSubmit.disabled = false;
          authGateKey.select();
          return;
        }
        saveStoredAuth(token);
        secretInput.value = token;
        authGateSubmit.disabled = false;
        finish();
      }

      authGateSubmit.onclick = function () {
        submit();
      };
      authGateKey.onkeydown = function (event) {
        if (event.key === "Enter") {
          event.preventDefault();
          submit();
        }
      };
      authGateKey.focus();
    });
  }

  async function ensureAuthenticated() {
    var status = await fetchAuthStatus();
    if (!status.auth_required) {
      return;
    }
    var stored = loadStoredAuth();
    if (stored && (await verifyAuthToken(stored))) {
      secretInput.value = stored;
      return;
    }
    if (stored) {
      saveStoredAuth("");
    }
    await showAuthGate();
  }

  async function apiFetch(path, options) {
    var opts = options || {};
    var response = await fetch(path, {
      method: opts.method || "GET",
      body: opts.body,
      signal: opts.signal,
      headers: {
        "Content-Type": "application/json",
        ...authHeaders(),
        ...(opts.headers ? opts.headers : {}),
      },
    });
    var text = await response.text();
    var payload = null;
    try {
      payload = text ? JSON.parse(text) : null;
    } catch (_err) {
      payload = { raw: text };
    }
    if (!response.ok) {
      var detail = payload && payload.detail ? payload.detail : response.statusText;
      throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
    }
    return payload;
  }

  function pushActivity(text) {
    var empty = recentActivity.querySelector(".tdl-context-list__item--empty");
    if (empty) {
      empty.remove();
    }
    var item = document.createElement("li");
    item.className = "tdl-context-list__item";
    item.textContent = text;
    recentActivity.insertBefore(item, recentActivity.firstChild);
    while (recentActivity.children.length > 5) {
      recentActivity.removeChild(recentActivity.lastChild);
    }
  }

  function formatMission(mission) {
    if (!mission || !mission.active) {
      return "Aucune";
    }
    var step = mission.current_step || "";
    var title = mission.title || "Mission active";
    return step ? title + " · " + step : title;
  }

  function updateContextPanels(status, toolsPayload, memoryPayload) {
    var ctx = status.context || {};
    var mission = status.mission || {};
    var state = status.state || {};

    statusState.textContent = status.status || "—";
    statusMission.textContent = formatMission(mission);
    statusTools.textContent = String((toolsPayload.tools || []).length);

    var project = ctx.active_project || state.active_project || "—";
    var goal = ctx.current_goal || "";
    var phase = ctx.current_phase || "";
    var projectText = project;
    if (goal) {
      projectText += "\n" + goal;
    }
    if (phase) {
      projectText += "\nPhase : " + phase;
    }
    currentProjects.textContent = projectText;

    barUser.textContent = status.user || "—";
    if (status.user) {
      cachedUserName = status.user;
    }

    if (orchestratorPanel) {
      orchestratorPanel.updateStatus(status, toolsPayload, memoryPayload);
    }

    if (referenceShell) {
      referenceShell.updateFromStatus(status, toolsPayload, memoryPayload);
      referenceShell.refreshConnectors();
    }

    var memoryUsers = (memoryPayload.long_term_users || []).length;
    var sessionNotes = memoryPayload.short_term_notes_count || 0;
    barMemory.textContent = memoryUsers + " profil(s) · " + sessionNotes + " note(s)";

    var lastMessages = state.last_messages || state.last_user_message;
    if (Array.isArray(lastMessages) && lastMessages.length > 0) {
      recentActivity.innerHTML = "";
      lastMessages.slice(0, 5).forEach(function (msg) {
        var item = document.createElement("li");
        item.className = "tdl-context-list__item";
        item.textContent =
          typeof msg === "string" ? msg.slice(0, 80) : JSON.stringify(msg).slice(0, 80);
        recentActivity.appendChild(item);
      });
    }
  }

  async function refreshStatus() {
    try {
      var status = await apiFetch("/status");
      var toolsPayload = await apiFetch("/tools");
      var memoryPayload = await apiFetch("/memory/status");
      updateContextPanels(status, toolsPayload, memoryPayload);
    } catch (err) {
      barMemory.textContent = "Hors ligne";
      statusState.textContent = err.message.slice(0, 40);
    }
  }

  function startStatusPolling() {
    if (statusPollTimer) {
      clearInterval(statusPollTimer);
    }
    refreshStatus();
    statusPollTimer = setInterval(refreshStatus, 30000);
  }

  async function loadHealth() {
    try {
      var health = await apiFetch("/health");
      var label = "V" + (health.version || "?");
      systemVersion.textContent = label;
      barSystem.textContent = health.web_enabled ? "Titan Online" : "Hors ligne";
      if (referenceShell) {
        referenceShell.setBrainState(health.web_enabled ? "Actif" : "Inactif");
      }
    } catch (err) {
      systemVersion.textContent = "Hors ligne";
      barSystem.textContent = "Erreur";
    }
  }

  function validateBeforeSend() {
    if (!secretInput.value.trim()) {
      switchView("settings");
      return false;
    }
    return true;
  }

  function initToolExperience() {
    if (typeof TitanToolActivityManager === "undefined") {
      return;
    }

    toolActivity = new TitanToolActivityManager({
      getPresenceController: getPresenceController,
    });

    if (typeof TitanToolTimeline !== "undefined") {
      toolTimeline = new TitanToolTimeline({
        manager: toolActivity,
        statusLineEl: document.getElementById("tool-status-line"),
        timelineEl: document.getElementById("tool-timeline"),
      });
      toolTimeline.attach(toolActivity);
    }

    if (typeof TitanToolProgressCard !== "undefined") {
      toolProgress = new TitanToolProgressCard({
        manager: toolActivity,
        stackEl: document.getElementById("tool-progress-stack"),
      });
      toolProgress.attach(toolActivity);
    }
  }

  function getToolActivityManager() {
    return toolActivity;
  }

  function initMemoryExperience() {
    if (typeof TitanMemoryActivityManager === "undefined") {
      return;
    }

    var bus =
      typeof TitanMemoryEvents !== "undefined"
        ? new TitanMemoryEvents.MemoryEventBus()
        : null;

    memoryActivity = new TitanMemoryActivityManager({
      bus: bus,
      statusLineEl: document.getElementById("memory-status-line"),
      getToolActivityManager: getToolActivityManager,
    });

    if (typeof TitanMemoryVisualizer !== "undefined") {
      memoryVisualizer = new TitanMemoryVisualizer({
        getNeuralEngine: getNeuralEngine,
        getPresenceController: getPresenceController,
      });
      memoryVisualizer.attach(bus, TitanMemoryEvents.EVENTS);
    }

    if (typeof TitanMemoryCards !== "undefined") {
      memoryCards = new TitanMemoryCards({
        layerEl: document.getElementById("memory-cards-layer"),
      });
      memoryCards.attach(bus, TitanMemoryEvents.EVENTS);
    }

    if (typeof TitanExplorationCards !== "undefined") {
      explorationCards = new TitanExplorationCards({
        layerEl: document.getElementById("memory-cards-layer"),
      });
    }
  }

  function getExplorationCards() {
    return explorationCards;
  }

  function getMemoryActivityManager() {
    return memoryActivity;
  }

  function initOrchestratorPanel() {
    if (typeof TitanOrchestratorPanel === "undefined") {
      return;
    }

    orchestratorPanel = new TitanOrchestratorPanel({
      stateBadgeEl: document.getElementById("orchestrator-state-badge"),
      stateDetailEl: document.getElementById("orchestrator-state-detail"),
      stepsEl: document.getElementById("orchestrator-steps"),
      neuralLabelEl: document.getElementById("orchestrator-neural-label"),
      cognitiveValueEl: document.getElementById("cognitive-state-value"),
      presenceValueEl: document.getElementById("presence-card-value"),
      memoryValueEl: document.getElementById("memory-float-value"),
      toolsValueEl: document.getElementById("tools-float-value"),
      neuralLabelsRoot: document.querySelector(".tdl-neural-labels"),
      referenceShell: referenceShell,
    });
    orchestratorPanel.resetIdle();
  }

  function initReferenceShell() {
    if (typeof TitanReferenceShell === "undefined") {
      return;
    }

    referenceShell = new TitanReferenceShell({
      apiFetch: apiFetch,
      getNeuralEngine: getNeuralEngine,
      getPresenceController: getPresenceController,
      getToolActivityManager: getToolActivityManager,
    });
    referenceShell.init();
    referenceShell.setBrainState("Actif");
  }

  function handleOrchestratorProgress(progress, meta) {
    if (!orchestratorPanel) {
      return;
    }

    if (meta && meta.phase === "thinking") {
      orchestratorPanel.beginThinking();
      return;
    }

    orchestratorPanel.ingestProgress(progress || []);
  }

  function initConversation() {
    if (typeof TitanConversationManager === "undefined") {
      return;
    }

    conversation = new TitanConversationManager({
      messagesEl: chatMessages,
      inputEl: chatInput,
      sendBtn: document.getElementById("send-chat"),
      stopBtn: document.getElementById("stop-generation"),
      thinkingEl: document.getElementById("thinking-indicator"),
      zoneEl: chatZone,
      apiFetch: apiFetch,
      getPresenceController: getPresenceController,
      getToolActivityManager: getToolActivityManager,
      getMemoryActivityManager: getMemoryActivityManager,
      validateBeforeSend: validateBeforeSend,
      onActivity: pushActivity,
      onOrchestratorProgress: handleOrchestratorProgress,
      onResponseComplete: function () {
        refreshStatus();
      },
    });
  }

  function initPresence() {
    if (typeof TitanPresenceController === "undefined") {
      return;
    }

    presence = new TitanPresenceController({
      body: document.body,
      ambientGlow: document.querySelector(".tdl-glow-ambient"),
      appRoot: workspace || document.querySelector(".tdl-workspace") || document.querySelector(".tdl-app"),
      thinkingEl: document.getElementById("thinking-indicator"),
      barBrain: barBrain,
      barThinking: barThinking,
      dotThinking: dotThinking,
      composerInput: chatInput,
      composerZone: document.getElementById("chat-composer"),
      neuralCanvas: neuralCanvas,
      getNeuralEngine: getNeuralEngine,
    });
  }

  function getPresenceController() {
    return presence;
  }

  function hideAllPlaceholders() {
    PLACEHOLDER_VIEWS.forEach(function (view) {
      var el = document.getElementById("placeholder-" + view);
      if (el) {
        el.hidden = true;
        el.classList.remove("tdl-view-placeholder--visible");
      }
    });
  }

  function updateOrbitFocus(view) {
    if (!workspace) {
      return;
    }

    workspace.classList.remove(
      "tdl-workspace--view-projects",
      "tdl-workspace--view-memory",
      "tdl-workspace--view-chat",
      "tdl-workspace--view-tools",
      "tdl-workspace--view-browser",
      "tdl-workspace--view-calendar",
      "tdl-workspace--view-trading"
    );

    if (view === "projects") {
      workspace.classList.add("tdl-workspace--view-projects");
    } else if (view === "memory") {
      workspace.classList.add("tdl-workspace--view-memory");
    } else if (view === "tools") {
      workspace.classList.add("tdl-workspace--view-tools");
    } else if (view === "browser") {
      workspace.classList.add("tdl-workspace--view-browser");
    } else if (view === "calendar") {
      workspace.classList.add("tdl-workspace--view-calendar");
    } else if (view === "trading") {
      workspace.classList.add("tdl-workspace--view-trading");
    } else if (view === "chat") {
      workspace.classList.add("tdl-workspace--view-chat");
    }

    workspace.querySelectorAll("[data-view-focus]").forEach(function (panel) {
      var focusView = panel.getAttribute("data-view-focus");
      var isFocused = focusView === view;
      panel.classList.toggle("tdl-orbit-panel--focused", isFocused);
      panel.classList.toggle("tdl-orbit-panel--dimmed", !isFocused && view !== "chat" && view !== "settings");
    });

    if (chatZone) {
      chatZone.classList.toggle("tdl-orbit-panel--focused", view === "chat");
      chatZone.classList.toggle(
        "tdl-orbit-panel--dimmed",
        view !== "chat" && view !== "settings" && PLACEHOLDER_VIEWS.indexOf(view) === -1 && view !== "tools"
      );
    }
  }

  function switchView(view) {
    currentView = view;
    hideAllPlaceholders();
    updateOrbitFocus(view);

    mainNav.querySelectorAll(".tdl-nav__item").forEach(function (btn) {
      btn.classList.toggle("tdl-nav__item--active", btn.dataset.view === view);
    });

    if (view === "settings") {
      settingsPanel.hidden = false;
      requestAnimationFrame(function () {
        settingsPanel.classList.add("tdl-settings-panel--visible");
      });
      return;
    }

    closeSettings();

    if (PLACEHOLDER_VIEWS.indexOf(view) !== -1) {
      var placeholder = document.getElementById("placeholder-" + view);
      if (placeholder) {
        placeholder.hidden = false;
        requestAnimationFrame(function () {
          placeholder.classList.add("tdl-view-placeholder--visible");
        });
      }
      return;
    }

    if (view === "browser") {
      var explorationView = document.getElementById("placeholder-browser");
      if (explorationView) {
        explorationView.hidden = false;
        requestAnimationFrame(function () {
          explorationView.classList.add("tdl-view-placeholder--visible");
        });
      }
      if (presence) {
        presence.handleViewChange("browser");
        presence._setCognitiveState("exploration");
      }
      return;
    }

    if (view === "memory") {
      pushActivity("Vue Mémoire — panneau mémoire");
    }
    if (view === "projects") {
      pushActivity("Vue Projets — panneau projets");
    }
    if (view === "tools") {
      pushActivity("Vue Outils — orchestrateur");
    }

    if (presence) {
      presence.handleViewChange(view);
    }
  }

  function closeSettings() {
    settingsPanel.classList.remove("tdl-settings-panel--visible");
    settingsPanel.hidden = true;
    if (currentView === "settings") {
      currentView = "chat";
      mainNav.querySelector('[data-view="chat"]').classList.add("tdl-nav__item--active");
      mainNav.querySelector('[data-view="settings"]').classList.remove("tdl-nav__item--active");
    }
  }

  function saveAuth() {
    saveStoredAuth(secretInput.value.trim());
    pushActivity("Clé d'authentification enregistrée");
    closeSettings();
    switchView("chat");
    startStatusPolling();
  }

  function logoutAuth() {
    saveStoredAuth("");
    secretInput.value = "";
    pushActivity("Clé d'authentification effacée");
    window.location.reload();
  }

  function initNeural() {
    if (typeof TitanMotion !== "undefined" && typeof TitanNeural !== "undefined") {
      TitanMotion.syncNeuralColors(TitanNeural.CONFIG);
    }
    if (typeof TitanNeuralNetwork !== "undefined" && neuralCanvas) {
      neuralNetwork = new TitanNeuralNetwork(neuralCanvas, { density: 1.72 });
      initBrainApi();
    }
  }

  function initBrainApi() {
    window.brain = {
      setState: function (stateName) {
        if (neuralNetwork && neuralNetwork.setState) {
          return neuralNetwork.setState(stateName);
        }
        return "idle";
      },
      getState: function () {
        if (neuralNetwork && neuralNetwork.getCognitiveState) {
          return neuralNetwork.getCognitiveState();
        }
        return "idle";
      },
      getEngine: getNeuralEngine,
    };
  }

  function initSoundHooks() {
    if (typeof TitanSoundHooks === "undefined") {
      return;
    }
    soundHooks = new TitanSoundHooks({ enabled: false });
  }

  function initAccessibility() {
    if (typeof TitanMotion === "undefined") {
      return;
    }

    var prefs = TitanMotion.loadPrefs();
    var reducedEl = document.getElementById("pref-reduced-motion");
    var contrastEl = document.getElementById("pref-high-contrast");
    var fontScaleEl = document.getElementById("pref-font-scale");

    if (reducedEl) {
      reducedEl.checked = !!prefs.reducedMotion;
    }
    if (contrastEl) {
      contrastEl.checked = !!prefs.highContrast;
    }
    if (fontScaleEl) {
      fontScaleEl.value = String(prefs.fontScale || 100);
    }

    TitanMotion.applyAccessibility(prefs);

    function persistAccessibility() {
      var next = {
        reducedMotion: reducedEl ? reducedEl.checked : false,
        highContrast: contrastEl ? contrastEl.checked : false,
        fontScale: fontScaleEl ? parseInt(fontScaleEl.value, 10) || 100 : 100,
      };
      TitanMotion.savePrefs(next);
      TitanMotion.applyAccessibility(next);
    }

    if (reducedEl) {
      reducedEl.addEventListener("change", persistAccessibility);
    }
    if (contrastEl) {
      contrastEl.addEventListener("change", persistAccessibility);
    }
    if (fontScaleEl) {
      fontScaleEl.addEventListener("change", persistAccessibility);
    }
  }

  function initKeyboardNav() {
    if (!mainNav) {
      return;
    }

    var items = Array.prototype.slice.call(
      mainNav.querySelectorAll(".tdl-nav__item[data-view]")
    );

    items.forEach(function (btn, index) {
      btn.setAttribute("tabindex", btn.classList.contains("tdl-nav__item--active") ? "0" : "-1");

      btn.addEventListener("keydown", function (event) {
        var nextIndex = index;

        if (event.key === "ArrowDown" || event.key === "ArrowRight") {
          event.preventDefault();
          nextIndex = (index + 1) % items.length;
        } else if (event.key === "ArrowUp" || event.key === "ArrowLeft") {
          event.preventDefault();
          nextIndex = (index - 1 + items.length) % items.length;
        } else if (event.key === "Home") {
          event.preventDefault();
          nextIndex = 0;
        } else if (event.key === "End") {
          event.preventDefault();
          nextIndex = items.length - 1;
        } else {
          return;
        }

        items.forEach(function (item, i) {
          item.setAttribute("tabindex", i === nextIndex ? "0" : "-1");
        });
        items[nextIndex].focus();
      });
    });
  }

  function runLaunchSequence(callback) {
    if (typeof TitanLaunchSequence === "undefined") {
      if (document.body) {
        document.body.classList.add("tdl-page--ready");
      }
      if (callback) {
        callback();
      }
      return;
    }

    launchSequence = new TitanLaunchSequence({
      overlay: document.getElementById("launch-overlay"),
      statusEl: document.getElementById("launch-status"),
      appRoot: workspace || document.querySelector(".tdl-workspace") || document.querySelector(".tdl-app"),
      ambientGlow: document.querySelector(".tdl-glow-ambient"),
      neuralCanvas: neuralCanvas,
      soundHooks: soundHooks,
      getUserName: function () {
        return cachedUserName;
      },
      onComplete: callback,
    });
    launchSequence.run();
  }

  function getNeuralEngine() {
    return neuralNetwork && neuralNetwork.getEngine ? neuralNetwork.getEngine() : null;
  }

  function getConversation() {
    return conversation;
  }

  function initVoice() {
    if (typeof TitanVoiceController === "undefined") {
      return;
    }

    voice = new TitanVoiceController({
      micBtn: document.getElementById("voice-mic"),
      micToggle: document.getElementById("voice-continuous"),
      neuralStage: document.getElementById("neural-stage") || document.querySelector(".tdl-neural-stage"),
      apiFetch: apiFetch,
      validateBeforeSend: validateBeforeSend,
      getConversation: getConversation,
      getPresenceController: getPresenceController,
      getNeuralEngine: getNeuralEngine,
    });
  }

  function getVoiceController() {
    return voice;
  }

  function bindEvents() {
    mainNav.addEventListener("click", function (event) {
      var btn = event.target.closest("[data-view]");
      if (btn) {
        switchView(btn.dataset.view);
        mainNav.querySelectorAll(".tdl-nav__item[data-view]").forEach(function (item) {
          item.setAttribute("tabindex", item === btn ? "0" : "-1");
        });
      }
    });

    document.getElementById("save-auth").addEventListener("click", saveAuth);
    document.getElementById("logout-auth").addEventListener("click", logoutAuth);
    document.getElementById("close-settings").addEventListener("click", function () {
      closeSettings();
      switchView("chat");
    });

    settingsPanel.addEventListener("click", function (event) {
      if (event.target === settingsPanel) {
        closeSettings();
        switchView("chat");
      }
    });
  }

  async function init() {
    secretInput.value = loadStoredAuth();
    try {
      await ensureAuthenticated();
    } catch (err) {
      console.error("[Titan] Auth check failed:", err);
    }
    initSoundHooks();
    initAccessibility();
    initNeural();
    initPresence();
    initReferenceShell();
    initOrchestratorPanel();
    initToolExperience();
    initMemoryExperience();
    initConversation();
    initVoice();
    bindEvents();
    initKeyboardNav();
    updateOrbitFocus("chat");

    runLaunchSequence(function () {
      loadHealth();
      if (secretInput.value.trim()) {
        startStatusPolling();
      } else {
        switchView("settings");
      }
    });
  }

  init();
})();
