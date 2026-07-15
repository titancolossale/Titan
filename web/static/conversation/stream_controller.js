/**
 * Titan Stream Controller — streaming-ready response lifecycle (Phase 17.5)
 *
 * States: idle | thinking | streaming | finished | interrupted
 * Supports token streaming, interruption, and future SSE/WebSocket hooks.
 */
(function (global) {
  "use strict";

  var STATES = {
    IDLE: "idle",
    THINKING: "thinking",
    STREAMING: "streaming",
    FINISHED: "finished",
    INTERRUPTED: "interrupted",
  };

  function StreamController(options) {
    this.state = STATES.IDLE;
    this.onStateChange = options.onStateChange || null;
    this.onToken = options.onToken || null;
    this.onComplete = options.onComplete || null;
    this.onError = options.onError || null;
    this.onInterrupt = options.onInterrupt || null;

    this._streamTimer = null;
    this._abortController = null;
    this._accumulated = "";
    this._simulateStreaming = options.simulateStreaming !== false;
    this._chunkDelayMs = options.chunkDelayMs || 18;
  }

  StreamController.STATES = STATES;

  StreamController.prototype.getState = function () {
    return this.state;
  };

  StreamController.prototype.isActive = function () {
    return (
      this.state === STATES.THINKING ||
      this.state === STATES.STREAMING
    );
  };

  StreamController.prototype._setState = function (next) {
    if (this.state === next) {
      return;
    }
    this.state = next;
    if (this.onStateChange) {
      this.onStateChange(next);
    }
  };

  StreamController.prototype.startThinking = function () {
    this._clearStreamTimer();
    this._accumulated = "";
    this._abortController = new AbortController();
    this._setState(STATES.THINKING);
    return this._abortController.signal;
  };

  StreamController.prototype.beginStream = function () {
    this._accumulated = "";
    this._setState(STATES.STREAMING);
  };

  StreamController.prototype.appendToken = function (token) {
    if (this.state !== STATES.STREAMING && this.state !== STATES.THINKING) {
      return;
    }
    if (this.state === STATES.THINKING) {
      this._setState(STATES.STREAMING);
    }
    this._accumulated += token;
    if (this.onToken) {
      this.onToken(token, this._accumulated);
    }
  };

  StreamController.prototype.finishStream = function (finalText) {
    this._clearStreamTimer();
    if (finalText !== undefined) {
      this._accumulated = finalText;
    }
    this._setState(STATES.FINISHED);
    if (this.onComplete) {
      this.onComplete(this._accumulated);
    }
    this._setState(STATES.IDLE);
  };

  StreamController.prototype.failStream = function (error) {
    this._clearStreamTimer();
    this._setState(STATES.IDLE);
    if (this.onError) {
      this.onError(error);
    }
  };

  StreamController.prototype.interrupt = function () {
    if (!this.isActive()) {
      return false;
    }
    this._clearStreamTimer();
    if (this._abortController) {
      this._abortController.abort();
    }
    this._setState(STATES.INTERRUPTED);
    if (this.onInterrupt) {
      this.onInterrupt(this._accumulated);
    }
    this._setState(STATES.IDLE);
    return true;
  };

  StreamController.prototype.simulateFromText = function (text) {
    var self = this;
    this.beginStream();

    if (!this._simulateStreaming || !text) {
      this.appendToken(text || "");
      this.finishStream(text || "");
      return;
    }

    var tokens = self._tokenize(text);
    var index = 0;

    function pushNext() {
      if (self.state !== STATES.STREAMING) {
        return;
      }
      if (index >= tokens.length) {
        self.finishStream(text);
        return;
      }
      self.appendToken(tokens[index]);
      index += 1;
      self._streamTimer = setTimeout(pushNext, self._chunkDelayMs);
    }

    pushNext();
  };

  StreamController.prototype._tokenize = function (text) {
    var parts = text.match(/\S+\s*|\n|\s+/g);
    return parts || [text];
  };

  StreamController.prototype._clearStreamTimer = function () {
    if (this._streamTimer) {
      clearTimeout(this._streamTimer);
      this._streamTimer = null;
    }
  };

  /**
   * Future hook: connect to SSE or WebSocket stream source.
   * @param {function(string): void} readChunk - yields text chunks
   */
  StreamController.prototype.connectStream = function (readChunk) {
    var self = this;
    this.beginStream();
    return readChunk(function (chunk) {
      self.appendToken(chunk);
    })
      .then(function (fullText) {
        self.finishStream(fullText);
      })
      .catch(function (err) {
        if (err && err.name === "AbortError") {
          return;
        }
        self.failStream(err);
      });
  };

  global.TitanStreamController = StreamController;
})(window);
