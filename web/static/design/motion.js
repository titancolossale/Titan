/**
 * Titan Motion — unified animation utilities (Phase 18.0)
 *
 * Single easing source for CSS and JS. Reads TDL tokens, handles reduced
 * motion, accessibility preferences, and neural color sync from CSS variables.
 */
(function (global) {
  "use strict";

  var STORAGE_KEY = "titan_a11y_prefs";
  var _motionQuery = null;
  var _changeListeners = [];

  /* Cubic-bezier easing — mirrors tokens.css curves */
  function createBezier(x1, y1, x2, y2) {
    var cx = 3 * x1;
    var bx = 3 * (x2 - x1) - cx;
    var ax = 1 - cx - bx;
    var cy = 3 * y1;
    var by = 3 * (y2 - y1) - cy;
    var ay = 1 - cy - by;

    function sampleX(t) {
      return ((ax * t + bx) * t + cx) * t;
    }

    function sampleY(t) {
      return ((ay * t + by) * t + cy) * t;
    }

    function solve(x) {
      var t = x;
      for (var i = 0; i < 6; i++) {
        var x2v = sampleX(t) - x;
        if (Math.abs(x2v) < 1e-5) {
          break;
        }
        var d = (3 * ax * t + 2 * bx) * t + cx;
        if (Math.abs(d) < 1e-6) {
          break;
        }
        t -= x2v / d;
      }
      return sampleY(Math.max(0, Math.min(1, t)));
    }

    return function (t) {
      if (t <= 0) {
        return 0;
      }
      if (t >= 1) {
        return 1;
      }
      return solve(t);
    };
  }

  var EASING = {
    standard: createBezier(0.4, 0, 0.2, 1),
    enter: createBezier(0, 0, 0.2, 1),
    exit: createBezier(0.4, 0, 1, 1),
    organic: createBezier(0.45, 0.05, 0.55, 0.95),
  };

  function readToken(name, fallback) {
    if (!global.document || !document.documentElement) {
      return fallback;
    }
    var value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
    return value || fallback;
  }

  function parseDurationMs(raw) {
    if (!raw) {
      return 350;
    }
    if (raw.indexOf("ms") !== -1) {
      return parseFloat(raw) || 350;
    }
    if (raw.indexOf("s") !== -1) {
      return (parseFloat(raw) || 0.35) * 1000;
    }
    return parseFloat(raw) || 350;
  }

  function duration(name) {
    return parseDurationMs(readToken(name, "350ms"));
  }

  function prefersReducedMotion() {
    if (_motionQuery && _motionQuery.matches) {
      return true;
    }
    if (global.document && document.documentElement.classList.contains("tdl-page--reduced-motion")) {
      return true;
    }
    return false;
  }

  function shouldAnimate() {
    return !prefersReducedMotion() && !document.hidden;
  }

  function ease(curve, t) {
    var fn = EASING[curve] || EASING.standard;
    return fn(Math.max(0, Math.min(1, t)));
  }

  function lerp(a, b, t) {
    return a + (b - a) * t;
  }

  function hexToRgba(hex, alpha) {
    var h = hex.replace("#", "");
    if (h.length === 3) {
      h = h[0] + h[0] + h[1] + h[1] + h[2] + h[2];
    }
    var r = parseInt(h.slice(0, 2), 16);
    var g = parseInt(h.slice(2, 4), 16);
    var b = parseInt(h.slice(4, 6), 16);
    return "rgba(" + r + ", " + g + ", " + b + ", " + alpha + ")";
  }

  function syncNeuralColors(config) {
    if (!config || !config.colors) {
      return config;
    }
    var redCore = readToken("--tdl-red-core", "#8b0000");
    var redGlow = readToken("--tdl-red-glow", "#b91c1c");
    var textPrimary = readToken("--tdl-text-primary", "#f5f5f5");

    config.colors.redCore = hexToRgba(redCore, "").replace(/,\s*$/, ", ");
    config.colors.redGlow = hexToRgba(redGlow, "").replace(/,\s*$/, ", ");
    config.colors.whiteDim = hexToRgba(textPrimary, "").replace(/,\s*$/, ", ");
    return config;
  }

  function loadPrefs() {
    try {
      var raw = localStorage.getItem(STORAGE_KEY);
      return raw ? JSON.parse(raw) : {};
    } catch (_err) {
      return {};
    }
  }

  function savePrefs(prefs) {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(prefs));
    } catch (_err) {
      /* ignore */
    }
  }

  function applyAccessibility(prefs) {
    if (!global.document) {
      return;
    }
    var root = document.documentElement;
    var reduced = !!(prefs.reducedMotion || prefersReducedMotion());
    root.classList.toggle("tdl-page--reduced-motion", reduced);

    root.classList.toggle("tdl-page--high-contrast", !!prefs.highContrast);

    var scale = prefs.fontScale || 100;
    root.classList.remove("tdl-page--font-scale-112", "tdl-page--font-scale-125");
    if (scale === 112) {
      root.classList.add("tdl-page--font-scale-112");
    } else if (scale === 125) {
      root.classList.add("tdl-page--font-scale-125");
    }
    root.style.setProperty("--tdl-font-scale", String(scale / 100));
  }

  function onMotionChange(callback) {
    if (typeof callback === "function") {
      _changeListeners.push(callback);
    }
  }

  function offMotionChange(callback) {
    var idx = _changeListeners.indexOf(callback);
    if (idx !== -1) {
      _changeListeners.splice(idx, 1);
    }
  }

  function _notifyChange() {
    for (var i = 0; i < _changeListeners.length; i++) {
      try {
        _changeListeners[i](prefersReducedMotion());
      } catch (_err) {
        /* listener must not break motion system */
      }
    }
  }

  function init() {
    if (!global.matchMedia) {
      return;
    }
    _motionQuery = global.matchMedia("(prefers-reduced-motion: reduce)");
    var handler = function () {
      applyAccessibility(loadPrefs());
      _notifyChange();
    };
    if (_motionQuery.addEventListener) {
      _motionQuery.addEventListener("change", handler);
    } else if (_motionQuery.addListener) {
      _motionQuery.addListener(handler);
    }
    applyAccessibility(loadPrefs());
  }

  global.TitanMotion = {
    EASING: EASING,
    readToken: readToken,
    duration: duration,
    parseDurationMs: parseDurationMs,
    prefersReducedMotion: prefersReducedMotion,
    shouldAnimate: shouldAnimate,
    ease: ease,
    lerp: lerp,
    syncNeuralColors: syncNeuralColors,
    loadPrefs: loadPrefs,
    savePrefs: savePrefs,
    applyAccessibility: applyAccessibility,
    onMotionChange: onMotionChange,
    offMotionChange: offMotionChange,
    init: init,
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})(window);
