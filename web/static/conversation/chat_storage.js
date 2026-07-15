/**
 * Titan Chat Storage — local session persistence (Phase 17.5)
 * Messages survive page refresh via localStorage.
 */
(function (global) {
  "use strict";

  var STORAGE_KEY = "titan_chat_session";
  var SCHEMA_VERSION = 1;
  var MAX_MESSAGES = 500;

  function generateId() {
    return "msg_" + Date.now().toString(36) + "_" + Math.random().toString(36).slice(2, 8);
  }

  function defaultSession() {
    return {
      version: SCHEMA_VERSION,
      sessionId: "sess_" + Date.now().toString(36),
      messages: [],
      updatedAt: null,
    };
  }

  function ChatStorage(options) {
    this.storageKey = (options && options.storageKey) || STORAGE_KEY;
    this._session = null;
  }

  ChatStorage.prototype.load = function () {
    try {
      var raw = localStorage.getItem(this.storageKey);
      if (!raw) {
        this._session = defaultSession();
        return this._session;
      }
      var parsed = JSON.parse(raw);
      if (!parsed || !Array.isArray(parsed.messages)) {
        this._session = defaultSession();
        return this._session;
      }
      this._session = {
        version: parsed.version || SCHEMA_VERSION,
        sessionId: parsed.sessionId || defaultSession().sessionId,
        messages: parsed.messages.slice(-MAX_MESSAGES),
        updatedAt: parsed.updatedAt || null,
      };
      return this._session;
    } catch (_err) {
      this._session = defaultSession();
      return this._session;
    }
  };

  ChatStorage.prototype.getSession = function () {
    if (!this._session) {
      this.load();
    }
    return this._session;
  };

  ChatStorage.prototype.getMessages = function () {
    return this.getSession().messages.slice();
  };

  ChatStorage.prototype.save = function () {
    if (!this._session) {
      return;
    }
    this._session.updatedAt = new Date().toISOString();
    try {
      localStorage.setItem(this.storageKey, JSON.stringify(this._session));
    } catch (_err) {
      /* quota or privacy mode — degrade silently */
    }
  };

  ChatStorage.prototype.addMessage = function (message) {
    var session = this.getSession();
    var entry = {
      id: message.id || generateId(),
      role: message.role,
      content: message.content || "",
      timestamp: message.timestamp || new Date().toISOString(),
      status: message.status || "complete",
    };
    session.messages.push(entry);
    if (session.messages.length > MAX_MESSAGES) {
      session.messages = session.messages.slice(-MAX_MESSAGES);
    }
    this.save();
    return entry;
  };

  ChatStorage.prototype.updateMessage = function (id, patch) {
    var session = this.getSession();
    var msg = session.messages.find(function (m) {
      return m.id === id;
    });
    if (!msg) {
      return null;
    }
    if (patch.content !== undefined) {
      msg.content = patch.content;
    }
    if (patch.status !== undefined) {
      msg.status = patch.status;
    }
    if (patch.timestamp !== undefined) {
      msg.timestamp = patch.timestamp;
    }
    this.save();
    return msg;
  };

  ChatStorage.prototype.clear = function () {
    this._session = defaultSession();
    this.save();
  };

  ChatStorage.prototype.newSession = function () {
    this._session = defaultSession();
    this.save();
    return this._session;
  };

  global.TitanChatStorage = ChatStorage;
})(window);
