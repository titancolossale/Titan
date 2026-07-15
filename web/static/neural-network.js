/**
 * Titan Neural Network — Phase 17.4 compatibility facade
 * Phase 21.0 — exposes brain.setState() cognitive visualization hooks.
 */
(function (global) {
  "use strict";

  function TitanNeuralNetwork(canvas, options) {
    this._engine = new NeuralBrainEngine(canvas, options);
    this.canvas = canvas;
    this._engine.init();
  }

  TitanNeuralNetwork.prototype.setMode = function (mode) {
    this._engine.setMode(mode);
  };

  TitanNeuralNetwork.prototype.setState = function (stateName) {
    if (this._engine.setState) {
      return this._engine.setState(stateName);
    }
    this.setMode(stateName === "thinking" ? "thinking" : "idle");
    return "idle";
  };

  TitanNeuralNetwork.prototype.getCognitiveState = function () {
    if (this._engine.getCognitiveState) {
      return this._engine.getCognitiveState();
    }
    return this._engine.getState().mode;
  };

  TitanNeuralNetwork.prototype.destroy = function () {
    this._engine.destroy();
  };

  TitanNeuralNetwork.prototype.resize = function () {
    this._engine.resize();
  };

  TitanNeuralNetwork.prototype.getEngine = function () {
    return this._engine;
  };

  TitanNeuralNetwork.prototype.setPresenceProfile = function (profile) {
    if (this._engine && this._engine.setPresenceProfile) {
      this._engine.setPresenceProfile(profile);
    }
  };

  TitanNeuralNetwork.prototype.on = function (hookName, callback) {
    this._engine.on(hookName, callback);
  };

  TitanNeuralNetwork.prototype.trigger = function (hookName, payload) {
    this._engine.trigger(hookName, payload);
  };

  TitanNeuralNetwork.prototype.getDepthField = function () {
    var engine = this._engine;
    return engine && engine.getDepthField ? engine.getDepthField() : null;
  };

  global.TitanNeuralNetwork = TitanNeuralNetwork;
})(window);
