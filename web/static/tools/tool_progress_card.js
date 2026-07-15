/**
 * Titan Tool Progress Card — live tool progress with collapse (Phase 17.7)
 *
 * Displays icon, title, current action, and completed state.
 * Finished tools collapse automatically; details expand on demand.
 */
(function (global) {
  "use strict";

  var Events = TitanToolActivityManager.EVENTS;

  function ToolProgressCard(options) {
    this.stackEl = options.stackEl || null;
    this.collapseDelayMs = options.collapseDelayMs || 1400;
    this._manager = options.manager || null;
    this._cards = {};
    this._boundHandlers = {};
  }

  ToolProgressCard.prototype.attach = function (manager) {
    if (!manager) {
      return;
    }
    this.detach();
    this._manager = manager;

    this._boundHandlers.toolStart = this._onToolStart.bind(this);
    this._boundHandlers.toolProgress = this._onToolProgress.bind(this);
    this._boundHandlers.toolComplete = this._onToolComplete.bind(this);
    this._boundHandlers.toolError = this._onToolError.bind(this);
    this._boundHandlers.turnEnd = this._onTurnEnd.bind(this);

    manager.on(Events.TOOL_START, this._boundHandlers.toolStart);
    manager.on(Events.TOOL_PROGRESS, this._boundHandlers.toolProgress);
    manager.on(Events.TOOL_COMPLETE, this._boundHandlers.toolComplete);
    manager.on(Events.TOOL_ERROR, this._boundHandlers.toolError);
    manager.on(Events.TURN_END, this._boundHandlers.turnEnd);
  };

  ToolProgressCard.prototype.detach = function () {
    if (!this._manager) {
      return;
    }
    var m = this._manager;
    m.off(Events.TOOL_START, this._boundHandlers.toolStart);
    m.off(Events.TOOL_PROGRESS, this._boundHandlers.toolProgress);
    m.off(Events.TOOL_COMPLETE, this._boundHandlers.toolComplete);
    m.off(Events.TOOL_ERROR, this._boundHandlers.toolError);
    m.off(Events.TURN_END, this._boundHandlers.turnEnd);
    this._manager = null;
  };

  ToolProgressCard.prototype._createCard = function (run) {
    var card = document.createElement("article");
    card.className = "tdl-tool-card";
    card.dataset.runId = run.runId;

    var header = document.createElement("button");
    header.type = "button";
    header.className = "tdl-tool-card__header";
    header.setAttribute("aria-expanded", "true");

    var icon = document.createElement("span");
    icon.className = "tdl-tool-card__icon";
    icon.textContent = run.icon || "◉";
    icon.setAttribute("aria-hidden", "true");

    var titleWrap = document.createElement("span");
    titleWrap.className = "tdl-tool-card__title-wrap";

    var title = document.createElement("span");
    title.className = "tdl-tool-card__title";
    title.textContent = run.title || "Outil";

    var action = document.createElement("span");
    action.className = "tdl-tool-card__action";
    action.textContent = run.action || "En cours…";

    titleWrap.appendChild(title);
    titleWrap.appendChild(action);

    var chevron = document.createElement("span");
    chevron.className = "tdl-tool-card__chevron";
    chevron.textContent = "▾";
    chevron.setAttribute("aria-hidden", "true");

    header.appendChild(icon);
    header.appendChild(titleWrap);
    header.appendChild(chevron);

    var body = document.createElement("div");
    body.className = "tdl-tool-card__body";

    var stepsList = document.createElement("ul");
    stepsList.className = "tdl-tool-card__steps";
    body.appendChild(stepsList);

    card.appendChild(header);
    card.appendChild(body);

    var self = this;
    header.addEventListener("click", function () {
      self._toggleCard(card);
    });

    return {
      el: card,
      header: header,
      actionEl: action,
      stepsList: stepsList,
      steps: [],
      collapsed: false,
    };
  };

  ToolProgressCard.prototype._toggleCard = function (card) {
    var collapsed = card.classList.toggle("tdl-tool-card--collapsed");
    var header = card.querySelector(".tdl-tool-card__header");
    if (header) {
      header.setAttribute("aria-expanded", collapsed ? "false" : "true");
    }
  };

  ToolProgressCard.prototype._getOrCreate = function (run) {
    var existing = this._cards[run.runId];
    if (existing) {
      return existing;
    }

    var cardState = this._createCard(run);
    this._cards[run.runId] = cardState;

    if (this.stackEl) {
      this.stackEl.appendChild(cardState.el);
      requestAnimationFrame(function () {
        cardState.el.classList.add("tdl-tool-card--visible");
      });
    }

    return cardState;
  };

  ToolProgressCard.prototype._appendStep = function (cardState, label, state) {
    if (!label || label === "Terminé.") {
      return;
    }

    var li = document.createElement("li");
    li.className = "tdl-tool-card__step";
    if (state === "active") {
      li.classList.add("tdl-tool-card__step--active");
    }
    if (state === "done") {
      li.classList.add("tdl-tool-card__step--done");
    }
    li.textContent = label;
    cardState.stepsList.appendChild(li);
    cardState.steps.push({ label: label, el: li });
  };

  ToolProgressCard.prototype._markPreviousStepsDone = function (cardState) {
    for (var i = 0; i < cardState.steps.length; i++) {
      cardState.steps[i].el.classList.remove("tdl-tool-card__step--active");
      cardState.steps[i].el.classList.add("tdl-tool-card__step--done");
    }
  };

  ToolProgressCard.prototype._onToolStart = function (event) {
    var run = event.payload;
    var cardState = this._getOrCreate(run);
    cardState.actionEl.textContent = run.action || "En cours…";
    this._markPreviousStepsDone(cardState);
    this._appendStep(cardState, run.action, "active");
  };

  ToolProgressCard.prototype._onToolProgress = function (event) {
    var run = event.payload;
    var cardState = this._getOrCreate(run);
    cardState.actionEl.textContent = run.action || "En cours…";
    this._markPreviousStepsDone(cardState);
    this._appendStep(cardState, run.action, "active");
  };

  ToolProgressCard.prototype._finishCard = function (run, success) {
    var cardState = this._cards[run.runId];
    if (!cardState) {
      cardState = this._getOrCreate(run);
    }

    this._markPreviousStepsDone(cardState);
    cardState.actionEl.textContent = success ? "Terminé." : "Interrompu.";
    cardState.el.classList.toggle("tdl-tool-card--error", !success);
    cardState.el.classList.add("tdl-tool-card--done");

    var doneStep = document.createElement("li");
    doneStep.className = "tdl-tool-card__step tdl-tool-card__step--done";
    doneStep.textContent = success ? "Terminé." : "Interrompu.";
    cardState.stepsList.appendChild(doneStep);

    var self = this;
    setTimeout(function () {
      cardState.el.classList.add("tdl-tool-card--collapsed");
      cardState.header.setAttribute("aria-expanded", "false");
      cardState.collapsed = true;
    }, self.collapseDelayMs);
  };

  ToolProgressCard.prototype._onToolComplete = function (event) {
    this._finishCard(event.payload, true);
  };

  ToolProgressCard.prototype._onToolError = function (event) {
    this._finishCard(event.payload, false);
  };

  ToolProgressCard.prototype._onTurnEnd = function () {
    var self = this;
    setTimeout(function () {
      self.clear();
    }, 4000);
  };

  ToolProgressCard.prototype.clear = function () {
    if (this.stackEl) {
      this.stackEl.innerHTML = "";
    }
    this._cards = {};
  };

  global.TitanToolProgressCard = ToolProgressCard;
})(window);
