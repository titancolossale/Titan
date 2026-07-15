/**
 * Titan Speech Output — streaming TTS with interruption (Phase 17.8)
 *
 * Browser Speech Synthesis provider today; swappable for server-side audio.
 */
(function (global) {
  "use strict";

  var VoiceEvents = global.TitanVoiceEvents;
  var EVENTS = VoiceEvents.EVENTS;

  function BrowserSpeechOutputProvider(options) {
    this.locale = (options && options.locale) || "fr-FR";
    this.rate = options && options.rate !== undefined ? options.rate : 0.95;
    this.pitch = options && options.pitch !== undefined ? options.pitch : 1;
    this.voice = null;
    this._speaking = false;
    this._callbacks = {};
    this._queue = [];
    this._currentUtterance = null;
    this._spokenLength = 0;
    this._resolvePickVoice();
  }

  BrowserSpeechOutputProvider.prototype.isSupported = function () {
    return typeof global.speechSynthesis !== "undefined";
  };

  BrowserSpeechOutputProvider.prototype._resolvePickVoice = function () {
    if (!this.isSupported()) {
      return;
    }
    var voices = global.speechSynthesis.getVoices();
    if (!voices || voices.length === 0) {
      return;
    }
    var localePrefix = this.locale.split("-")[0];
    for (var i = 0; i < voices.length; i++) {
      if (voices[i].lang && voices[i].lang.indexOf(localePrefix) === 0) {
        this.voice = voices[i];
        return;
      }
    }
  };

  BrowserSpeechOutputProvider.prototype._applyVoice = function (utterance) {
    if (this.voice) {
      utterance.voice = this.voice;
    }
    utterance.lang = this.locale;
    utterance.rate = this.rate;
    utterance.pitch = this.pitch;
  };

  BrowserSpeechOutputProvider.prototype.speak = function (text, callbacks) {
    if (!this.isSupported() || !text) {
      if (callbacks && callbacks.onComplete) {
        callbacks.onComplete();
      }
      return false;
    }

    this._callbacks = callbacks || {};
    this._queue = [text];
    this._spokenLength = 0;
    this._speaking = true;
    this._drainQueue();
    return true;
  };

  BrowserSpeechOutputProvider.prototype.enqueue = function (text) {
    if (!text || !this._speaking) {
      return;
    }
    this._queue.push(text);
    if (!this._currentUtterance) {
      this._drainQueue();
    }
  };

  BrowserSpeechOutputProvider.prototype._drainQueue = function () {
    if (!this.isSupported() || this._queue.length === 0) {
      this._finishSpeaking();
      return;
    }

    var text = this._queue.shift();
    var self = this;
    var utterance = new SpeechSynthesisUtterance(text);
    this._applyVoice(utterance);
    this._currentUtterance = utterance;

    utterance.onstart = function () {
      if (self._callbacks.onStart) {
        self._callbacks.onStart(text);
      }
    };

    utterance.onboundary = function (event) {
      if (event.name === "word" && self._callbacks.onWord) {
        self._callbacks.onWord({
          charIndex: event.charIndex,
          charLength: event.charLength,
          text: text,
        });
      }
    };

    utterance.onend = function () {
      self._spokenLength += text.length;
      self._currentUtterance = null;
      if (self._callbacks.onChunk) {
        self._callbacks.onChunk(text);
      }
      self._drainQueue();
    };

    utterance.onerror = function () {
      self._currentUtterance = null;
      self._drainQueue();
    };

    global.speechSynthesis.speak(utterance);
  };

  BrowserSpeechOutputProvider.prototype._finishSpeaking = function () {
    this._speaking = false;
    this._currentUtterance = null;
    if (this._callbacks.onComplete) {
      this._callbacks.onComplete(this._spokenLength);
    }
  };

  BrowserSpeechOutputProvider.prototype.cancel = function () {
    if (!this.isSupported()) {
      return;
    }
    this._queue = [];
    this._currentUtterance = null;
    this._speaking = false;
    global.speechSynthesis.cancel();
  };

  BrowserSpeechOutputProvider.prototype.isSpeaking = function () {
    return this._speaking || (this.isSupported() && global.speechSynthesis.speaking);
  };

  function SpeechOutput(options) {
    this.bus = options.bus;
    this.locale = options.locale || "fr-FR";
    this.rate = options.rate !== undefined ? options.rate : 0.95;
    this.pitch = options.pitch !== undefined ? options.pitch : 1;

    this.provider = options.provider || new BrowserSpeechOutputProvider({
      locale: this.locale,
      rate: this.rate,
      pitch: this.pitch,
    });

    this._speaking = false;
    this._pendingBuffer = "";
    this._lastSpokenIndex = 0;
    this._fullText = "";
    this._chunkMinWords = options.chunkMinWords || 6;
  }

  SpeechOutput.prototype.isSupported = function () {
    return this.provider.isSupported();
  };

  SpeechOutput.prototype.beginStream = function (initialText) {
    this.cancel();
    this._speaking = true;
    this._pendingBuffer = "";
    this._lastSpokenIndex = 0;
    this._fullText = initialText || "";

    if (this.bus) {
      this.bus.emit(EVENTS.SPEAK_START, {});
    }

    if (initialText) {
      this.syncToText(initialText);
    }
  };

  SpeechOutput.prototype.syncToText = function (fullText) {
    if (!this._speaking || !fullText) {
      return;
    }

    this._fullText = fullText;
    var delta = fullText.slice(this._lastSpokenIndex);
    if (!delta.trim()) {
      return;
    }

    this._pendingBuffer += delta;
    this._lastSpokenIndex = fullText.length;

    var chunks = this._extractSpeakableChunks();
    for (var i = 0; i < chunks.length; i++) {
      this._speakChunk(chunks[i]);
    }
  };

  SpeechOutput.prototype.finishStream = function (finalText) {
    if (finalText !== undefined) {
      this.syncToText(finalText);
    }

    var remainder = this._pendingBuffer.trim();
    if (remainder) {
      this._speakChunk(remainder);
      this._pendingBuffer = "";
    }

    var self = this;
    var waitForProvider = function () {
      if (self.provider.isSpeaking()) {
        setTimeout(waitForProvider, 80);
        return;
      }
      self._speaking = false;
      if (self.bus) {
        self.bus.emit(EVENTS.SPEAK_END, { text: self._fullText });
      }
    };
    waitForProvider();
  };

  SpeechOutput.prototype._extractSpeakableChunks = function () {
    var chunks = [];
    var buffer = this._pendingBuffer;

    while (buffer.length > 0) {
      var sentenceMatch = buffer.match(/^[\s\S]*?[.!?…](?:\s+|$)/);
      if (sentenceMatch) {
        chunks.push(sentenceMatch[0].trim());
        buffer = buffer.slice(sentenceMatch[0].length);
        continue;
      }

      var words = buffer.trim().split(/\s+/);
      if (words.length >= this._chunkMinWords) {
        var chunkWords = words.slice(0, this._chunkMinWords);
        var chunk = chunkWords.join(" ");
        chunks.push(chunk);
        buffer = buffer.slice(buffer.indexOf(chunk) + chunk.length);
        continue;
      }
      break;
    }

    this._pendingBuffer = buffer;
    return chunks;
  };

  SpeechOutput.prototype._speakChunk = function (text) {
    var self = this;
    if (!this.provider._speaking && !this.provider._currentUtterance) {
      this.provider.speak(text, {
        onStart: function (chunk) {
          if (self.bus) {
            self.bus.emit(EVENTS.SPEAK_CHUNK, { text: chunk });
          }
        },
        onWord: function (info) {
          if (self.bus) {
            self.bus.emit(EVENTS.SPEAK_WORD, info);
          }
        },
        onChunk: function (chunk) {
          if (self.bus) {
            self.bus.emit(EVENTS.SPEAK_CHUNK, { text: chunk, completed: true });
          }
        },
        onComplete: function () {
          /* queue drained — finishStream handles SPEAK_END */
        },
      });
      this.provider._speaking = true;
    } else {
      this.provider.enqueue(text);
    }
  };

  SpeechOutput.prototype.cancel = function () {
    var wasSpeaking = this._speaking || this.provider.isSpeaking();
    this.provider.cancel();
    this._speaking = false;
    this._pendingBuffer = "";
    this._lastSpokenIndex = 0;
    this._fullText = "";

    if (wasSpeaking && this.bus) {
      this.bus.emit(EVENTS.SPEAK_INTERRUPTED, {});
    }
  };

  SpeechOutput.prototype.isSpeaking = function () {
    return this._speaking || this.provider.isSpeaking();
  };

  global.TitanSpeechOutput = {
    SpeechOutput: SpeechOutput,
    BrowserSpeechOutputProvider: BrowserSpeechOutputProvider,
  };
})(window);
