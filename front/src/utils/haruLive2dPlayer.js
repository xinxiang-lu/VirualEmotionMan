import { getLive2dModelConfig, normalizeLive2dModelCode } from '@/config/live2dModels';

const CUBISM_CORE_PATH = '/live2d-sdk/core/live2dcubismcore.v4.2.2.min.js';
const PIXI_RUNTIME_PATH = '/vendor/pixi/pixi.min.js';
const LIVE2D_RUNTIME_PATH = '/vendor/pixi-live2d-display/cubism4.min.js';

let pixiRuntimePromise = null;
let cubismCorePromise = null;
let live2dRuntimePromise = null;

const clamp = (value, min, max) => Math.min(Math.max(value, min), max);

const loadScriptOnce = (src, marker) => {
  if (typeof window === 'undefined') {
    return Promise.reject(new Error('Live2D runtime requires a browser environment.'));
  }

  const existing = document.querySelector(`script[data-runtime="${marker}"]`);
  if (existing) {
    return new Promise((resolve, reject) => {
      if (existing.dataset.loaded === 'true') {
        resolve();
        return;
      }
      existing.addEventListener('load', () => resolve(), { once: true });
      existing.addEventListener('error', () => reject(new Error(`Failed to load script: ${src}`)), { once: true });
    });
  }

  return new Promise((resolve, reject) => {
    const script = document.createElement('script');
    script.src = src;
    script.async = true;
    script.dataset.runtime = marker;
    script.onload = () => {
      script.dataset.loaded = 'true';
      resolve();
    };
    script.onerror = () => reject(new Error(`Failed to load script: ${src}`));
    document.head.appendChild(script);
  });
};

const ensurePixiRuntime = () => {
  if (typeof window === 'undefined') {
    return Promise.reject(new Error('Live2D runtime requires a browser environment.'));
  }

  if (window.PIXI?.Application && window.PIXI?.live2d?.Live2DModel) {
    return Promise.resolve(window.PIXI);
  }

  if (!pixiRuntimePromise) {
    pixiRuntimePromise = loadScriptOnce(PIXI_RUNTIME_PATH, 'pixi6').then(() => {
      if (!window.PIXI?.Application) {
        throw new Error('Pixi runtime did not initialize correctly.');
      }
      return window.PIXI;
    });
  }

  return pixiRuntimePromise;
};

export const ensureCubismCore = () => {
  if (typeof window === 'undefined') {
    return Promise.reject(new Error('Live2D runtime requires a browser environment.'));
  }

  if (window.Live2DCubismCore) {
    return Promise.resolve(window.Live2DCubismCore);
  }

  if (!cubismCorePromise) {
    cubismCorePromise = loadScriptOnce(CUBISM_CORE_PATH, 'cubism4-core').then(() => {
      if (!window.Live2DCubismCore) {
        throw new Error('Live2D Cubism Core did not initialize correctly.');
      }
      return window.Live2DCubismCore;
    });
  }

  return cubismCorePromise;
};

const ensureLive2DRuntime = async () => {
  await ensurePixiRuntime();
  await ensureCubismCore();

  if (window.PIXI?.live2d?.Live2DModel) {
    return window.PIXI.live2d.Live2DModel;
  }

  if (!live2dRuntimePromise) {
    live2dRuntimePromise = loadScriptOnce(LIVE2D_RUNTIME_PATH, 'pixi-live2d-cubism4').then(() => {
      const Live2DModel = window.PIXI?.live2d?.Live2DModel;
      if (!Live2DModel) {
        throw new Error('pixi-live2d-display runtime did not initialize correctly.');
      }
      return Live2DModel;
    });
  }

  return live2dRuntimePromise;
};

const fitModelToStage = (model, width, height, fit = {}) => {
  if (!model || width <= 0 || height <= 0) return;

  const bounds = model.getLocalBounds();
  if (!bounds.width || !bounds.height) return;

  const widthRatio = fit.widthRatio ?? 0.36;
  const heightRatio = fit.heightRatio ?? 0.94;
  const xRatio = fit.xRatio ?? 0.5;
  const yRatio = fit.yRatio ?? 0.98;

  model.anchor.set(0.5, 1);
  const scale = Math.min((width * widthRatio) / bounds.width, (height * heightRatio) / bounds.height);
  model.scale.set(scale);
  model.x = width * xRatio;
  model.y = height * yRatio;
};

const buildSemanticValueMap = (payload, frameIndex) => {
  const parameterIds = payload?.parameter_ids || [];
  const parameterFrames = payload?.parameter_frames || [];
  const frame = parameterFrames[frameIndex];
  if (!frame || !Array.isArray(frame.values)) {
    return {};
  }

  return parameterIds.reduce((result, parameterId, index) => {
    result[parameterId] = Number(frame.values[index] ?? 0);
    return result;
  }, {});
};

export class Live2DPlayer {
  constructor(container, options = {}) {
    this.container = container;
    this.modelCode = normalizeLive2dModelCode(options.modelCode);
    this.modelConfig = getLive2dModelConfig(this.modelCode);
    this.app = null;
    this.model = null;
    this.payload = null;
    this.replySync = null;
    this.presentationMode = options.presentationMode || 'idle';
    this.currentFrameIndex = 0;
    this.sequenceStartAt = 0;
    this.frameDuration = 1000 / 25;
    this.lastRenderAt = 0;
    this.animationFrameId = 0;
    this.lastMotionAt = 0;
    this.disposed = false;
    this.animate = this.animate.bind(this);
  }

  async init() {
    const Live2DModel = await ensureLive2DRuntime();

    if (!this.container) {
      throw new Error('Missing Live2D mount container.');
    }

    this.disposed = false;

    const PIXI = window.PIXI;
    const canvas = document.createElement('canvas');

    this.app = new PIXI.Application({
      view: canvas,
      width: this.container.clientWidth || 480,
      height: this.container.clientHeight || 360,
      autoDensity: true,
      antialias: true,
      resolution: window.devicePixelRatio || 1,
      backgroundAlpha: 0,
      autoStart: false,
      preserveDrawingBuffer: true,
    });

    this.container.replaceChildren(canvas);
    this.model = await Live2DModel.from(this.modelConfig.modelPath, { autoInteract: false });
    this.model.interactive = false;
    this.model.buttonMode = false;
    this.model.autoUpdate = false;
    this.app.stage.addChild(this.model);

    const width = Math.max(this.container.clientWidth || 480, 320);
    const height = Math.max(this.container.clientHeight || 360, 320);
    fitModelToStage(this.model, width, height, this.modelConfig.fit);

    this.container.dataset.haruFrame = '0';
    this.lastRenderAt = performance.now();
    this._triggerMotion(true);
    this.animationFrameId = window.requestAnimationFrame(this.animate);
  }

  setPayload(payload) {
    this.payload = payload;
    this.currentFrameIndex = 0;
    this.sequenceStartAt = performance.now();
    this.frameDuration = 1000 / Math.max(Number(payload?.fps || 25), 1);
    this.container.dataset.haruFrame = '0';
    if (payload?.parameter_frames?.length && this.presentationMode === 'idle') {
      this.presentationMode = 'responding';
    }
    this._triggerMotion(true);
  }

  setReplySync(replySync) {
    this.replySync = replySync || null;
  }

  clearPayload() {
    this.payload = null;
    this.currentFrameIndex = 0;
    this.container.dataset.haruFrame = '0';
    this._triggerMotion(true);
  }

  setMode(mode) {
    const nextMode = mode || 'idle';
    if (nextMode === this.presentationMode) {
      return;
    }
    this.presentationMode = nextMode;
    this._triggerMotion(true);
  }

  animate(now) {
    if (this.disposed || !this.app || !this.model) return;

    const deltaMS = this.lastRenderAt ? Math.max(now - this.lastRenderAt, 0) : this.frameDuration;
    this.lastRenderAt = now;

    this._maybeTriggerMotion(now);

    const frameCount = this.payload?.parameter_frames?.length || 0;
    if (frameCount && this.presentationMode === 'responding') {
      const replyCurrentTime = Number(this.replySync?.currentTime);
      if (Number.isFinite(replyCurrentTime) && this.replySync?.active) {
        this.currentFrameIndex = clamp(Math.floor(replyCurrentTime * Math.max(Number(this.payload?.fps || 25), 1)), 0, frameCount - 1);
        this.container.dataset.haruFrame = String(this.currentFrameIndex);
      } else {
        const duration = this.frameDuration * frameCount;
        if (duration > 0) {
          const elapsed = (now - this.sequenceStartAt) % duration;
          this.currentFrameIndex = Math.min(frameCount - 1, Math.floor(elapsed / this.frameDuration));
          this.container.dataset.haruFrame = String(this.currentFrameIndex);
        }
      }
    } else {
      this.currentFrameIndex = 0;
      this.container.dataset.haruFrame = '0';
    }

    this.model.update(deltaMS);

    if (frameCount && this.presentationMode === 'responding') {
      this.applyCurrentFrame(now);
    } else if (this.presentationMode === 'responding') {
      this.applyReplyFrame(now);
    } else {
      this.applyIdleFrame(now);
    }

    this.app.renderer.render(this.app.stage);
    this.animationFrameId = window.requestAnimationFrame(this.animate);
  }

  applyCurrentFrame(now) {
    const semanticValues = buildSemanticValueMap(this.payload, this.currentFrameIndex);
    if (this.presentationMode === 'responding') {
      const phaseSeconds =
        Number.isFinite(Number(this.replySync?.currentTime)) && this.replySync?.active
          ? Number(this.replySync.currentTime)
          : now / 1000;
      const hasLiveMouthLevel = Number.isFinite(Number(this.replySync?.mouthLevel)) && this.replySync?.active;
      const liveMouthLevel = hasLiveMouthLevel ? clamp(Number(this.replySync.mouthLevel), 0, 1) : 0;
      const speechCycle = hasLiveMouthLevel ? liveMouthLevel : 0.5 + 0.5 * Math.sin(phaseSeconds * 8.2);
      const emphasisCycle = 0.5 + 0.5 * Math.sin(phaseSeconds * 2.3 + 0.8);
      semanticValues.ParamMouthOpenY = clamp((semanticValues.ParamMouthOpenY || 0) + 0.05 + speechCycle * 0.34, 0, 1);
      semanticValues.ParamMouthForm = clamp((semanticValues.ParamMouthForm || 0) + (speechCycle - 0.5) * 0.24, -2, 1);
      semanticValues.ParamBrowLY = clamp((semanticValues.ParamBrowLY || 0) + 0.02 + emphasisCycle * 0.05, -1, 1);
      semanticValues.ParamBrowRY = clamp((semanticValues.ParamBrowRY || 0) + 0.02 + emphasisCycle * 0.05, -1, 1);
      semanticValues.ParamBrowLAngle = clamp((semanticValues.ParamBrowLAngle || 0) + 0.01 + emphasisCycle * 0.04, -1, 1);
      semanticValues.ParamBrowRAngle = clamp((semanticValues.ParamBrowRAngle || 0) + 0.01 + emphasisCycle * 0.04, -1, 1);
      semanticValues.ParamAngleX = clamp((semanticValues.ParamAngleX || 0) + Math.sin(phaseSeconds * 2.1) * 1.8, -30, 30);
      semanticValues.ParamAngleY = clamp((semanticValues.ParamAngleY || 0) + Math.cos(phaseSeconds * 1.8) * 1.4, -30, 30);
      semanticValues.ParamBodyAngleX = clamp((semanticValues.ParamBodyAngleX || 0) + Math.sin(phaseSeconds * 1.7) * 0.8, -10, 10);
    }
    const values = this._normalizeForModel(semanticValues, { enhanceForResponse: true });
    this._applyValueMap(values);
  }

  applyReplyFrame(now) {
    const phaseSeconds =
      Number.isFinite(Number(this.replySync?.currentTime)) && this.replySync?.active
        ? Number(this.replySync.currentTime)
        : now / 1000;
    const profile = this.replySync?.profile || {};
    const smileBias = clamp(Number(profile.smileBias ?? 0.24), 0, 1);
    const concernBias = clamp(Number(profile.concernBias ?? 0.16), 0, 1);
    const arousal = clamp(Number(profile.arousal ?? 0.24), 0, 1);
    const softness = clamp(Number(profile.softness ?? 0.56), 0, 1);
    const mouthLevel = clamp(Number(this.replySync?.mouthLevel ?? 0), 0, 1);
    const emphasis = 0.5 + 0.5 * Math.sin(phaseSeconds * (2 + arousal * 1.8));
    const replyValues = {
      ParamAngleX: Math.sin(phaseSeconds * 2.1) * (2.1 + arousal * 1.5),
      ParamAngleY: Math.cos(phaseSeconds * 1.7) * (1.4 + softness),
      ParamAngleZ: Math.sin(phaseSeconds * 1.35) * 1.4,
      ParamBodyAngleX: Math.sin(phaseSeconds * 1.4) * (0.8 + arousal * 0.8),
      ParamBodyAngleY: Math.cos(phaseSeconds * 0.9) * 0.45,
      ParamBodyAngleZ: Math.sin(phaseSeconds * 0.75) * 0.55,
      ParamBodyUpper: 0.12 + emphasis * 0.05,
      ParamBreath: clamp(0.36 + Math.sin(phaseSeconds * 1.6) * 0.08, 0, 1),
      ParamEyeLOpen: clamp(0.78 + softness * 0.12 - concernBias * 0.04, 0, 1),
      ParamEyeROpen: clamp(0.78 + softness * 0.12 - concernBias * 0.04, 0, 1),
      ParamEyeLSmile: clamp(smileBias * 0.7, 0, 1),
      ParamEyeRSmile: clamp(smileBias * 0.7, 0, 1),
      ParamEyeForm: clamp(smileBias * 0.16 - concernBias * 0.08, -1, 1),
      ParamEyeBallX: Math.sin(phaseSeconds * 0.7) * 0.12,
      ParamEyeBallY: Math.cos(phaseSeconds * 0.55) * 0.08,
      ParamBrowLY: clamp(0.08 + concernBias * 0.16 + emphasis * 0.04, -1, 1),
      ParamBrowRY: clamp(0.08 + concernBias * 0.16 + emphasis * 0.04, -1, 1),
      ParamBrowLX: 0,
      ParamBrowRX: 0,
      ParamBrowLAngle: clamp(0.04 + concernBias * 0.14 + emphasis * 0.04, -1, 1),
      ParamBrowRAngle: clamp(0.04 + concernBias * 0.14 + emphasis * 0.04, -1, 1),
      ParamBrowLForm: clamp(smileBias * 0.04 - concernBias * 0.05, -1, 1),
      ParamBrowRForm: clamp(smileBias * 0.04 - concernBias * 0.05, -1, 1),
      ParamMouthOpenY: clamp(0.04 + mouthLevel * 0.74, 0, 1),
      ParamMouthForm: clamp(-0.12 + smileBias * 0.62 - concernBias * 0.16 + (mouthLevel - 0.5) * 0.16, -2, 1),
      ParamFaceForm: clamp(smileBias * 0.06 - concernBias * 0.04, -1, 1),
    };

    const values = this._normalizeForModel(replyValues, { enhanceForResponse: true });
    this._applyValueMap(values);
  }

  applyIdleFrame(now) {
    const phase = now / 1000;
    const isListening = this.presentationMode === 'listening';
    const idleValues = {
      ParamAngleX: Math.sin(phase * 0.8) * (isListening ? 2.8 : 1.6),
      ParamAngleY: Math.cos(phase * 0.55) * (isListening ? 2.2 : 1.1),
      ParamAngleZ: Math.sin(phase * 0.7) * (isListening ? 1.8 : 0.9),
      ParamBodyAngleX: Math.sin(phase * 0.45) * (isListening ? 1.5 : 0.9),
      ParamBodyAngleY: Math.cos(phase * 0.35) * (isListening ? 0.9 : 0.45),
      ParamBodyAngleZ: Math.sin(phase * 0.4) * (isListening ? 1.2 : 0.7),
      ParamBodyUpper: isListening ? 0.16 : 0.07,
      ParamBreath: clamp(0.34 + Math.sin(phase * 1.6) * 0.08, 0, 1),
      ParamEyeLOpen: isListening ? 0.86 : 0.8,
      ParamEyeROpen: isListening ? 0.86 : 0.8,
      ParamEyeLSmile: isListening ? 0.05 : 0.015,
      ParamEyeRSmile: isListening ? 0.05 : 0.015,
      ParamEyeForm: isListening ? 0.08 : 0.02,
      ParamEyeBallX: Math.sin(phase * 0.6) * 0.12,
      ParamEyeBallY: Math.cos(phase * 0.55) * 0.08,
      ParamBrowLY: isListening ? 0.11 : 0.04,
      ParamBrowRY: isListening ? 0.11 : 0.04,
      ParamBrowLX: 0,
      ParamBrowRX: 0,
      ParamBrowLAngle: isListening ? 0.08 : 0.02,
      ParamBrowRAngle: isListening ? 0.08 : 0.02,
      ParamBrowLForm: isListening ? 0.05 : 0.01,
      ParamBrowRForm: isListening ? 0.05 : 0.01,
      ParamMouthOpenY: isListening ? 0.045 : 0.02,
      ParamMouthForm: isListening ? 0.08 : 0.02,
      ParamFaceForm: 0,
    };

    const values = this._normalizeForModel(idleValues, { enhanceForResponse: false });
    this._applyValueMap(values);
  }

  _applyValueMap(values) {
    const coreModel = this.model?.internalModel?.coreModel;
    if (!coreModel || !values) {
      return;
    }

    Object.entries(values).forEach(([parameterId, value]) => {
      coreModel.setParameterValueById(parameterId, Number(value ?? 0), 1);
    });
  }

  _normalizeForModel(semanticValues, { enhanceForResponse = false } = {}) {
    const values = { ...(semanticValues || {}) };

    if (enhanceForResponse) {
      values.ParamAngleX = clamp((values.ParamAngleX || 0) * 1.1, -30, 30);
      values.ParamAngleY = clamp((values.ParamAngleY || 0) * 1.1, -30, 30);
      values.ParamAngleZ = clamp((values.ParamAngleZ || 0) * 1.08, -30, 30);
      values.ParamBrowLY = clamp((values.ParamBrowLY || 0) * 1.32 + 0.03, -1, 1);
      values.ParamBrowRY = clamp((values.ParamBrowRY || 0) * 1.32 + 0.03, -1, 1);
      values.ParamBrowLAngle = clamp((values.ParamBrowLAngle || 0) * 1.24, -1, 1);
      values.ParamBrowRAngle = clamp((values.ParamBrowRAngle || 0) * 1.24, -1, 1);
      values.ParamBrowLForm = clamp((values.ParamBrowLForm || 0) * 1.18, -1, 1);
      values.ParamBrowRForm = clamp((values.ParamBrowRForm || 0) * 1.18, -1, 1);
      values.ParamMouthOpenY = clamp((values.ParamMouthOpenY || 0) * 1.34 + 0.05, 0, 1);
      values.ParamMouthForm = clamp((values.ParamMouthForm || 0) * 1.18, -2, 1);
      values.ParamEyeLSmile = clamp((values.ParamEyeLSmile || 0) * 1.14, 0, 1);
      values.ParamEyeRSmile = clamp((values.ParamEyeRSmile || 0) * 1.14, 0, 1);
      values.ParamBodyUpper = clamp((values.ParamBodyUpper || 0) + 0.04, -1, 1);
    }

    const modelValues = {};
    this.modelConfig.supportedParameterIds.forEach((parameterId) => {
      if (Object.prototype.hasOwnProperty.call(values, parameterId)) {
        modelValues[parameterId] = values[parameterId];
      }
    });

    if (typeof this.modelConfig.deriveParameters === 'function') {
      Object.assign(modelValues, this.modelConfig.deriveParameters(values));
    }

    return modelValues;
  }

  _currentMotionGroup() {
    const groups = this.modelConfig.motionGroups || {};
    if (this.presentationMode === 'responding') {
      return groups.responding || groups.idle || '';
    }
    if (this.presentationMode === 'listening') {
      return groups.listening || groups.idle || '';
    }
    return groups.idle || '';
  }

  _maybeTriggerMotion(now) {
    const motionManager = this.model?.internalModel?.motionManager;
    const finished = typeof motionManager?.isFinished === 'function' ? motionManager.isFinished() : true;
    if (!finished) {
      return;
    }
    if (now - this.lastMotionAt < this._currentMotionIntervalMs()) {
      return;
    }
    this._triggerMotion();
  }

  _triggerMotion(force = false) {
    const group = this._currentMotionGroup();
    if (!group || !this.model?.motion) {
      return;
    }

    const now = performance.now();
    if (!force && now - this.lastMotionAt < this._currentMotionIntervalMs()) {
      return;
    }

    try {
      this.model.motion(group);
      this.lastMotionAt = now;
    } catch (error) {
      console.warn(`Failed to start Live2D motion group "${group}" for ${this.modelCode}:`, error);
    }
  }

  _currentMotionIntervalMs() {
    if (this.presentationMode === 'responding') {
      return 2600;
    }
    if (this.presentationMode === 'listening') {
      return 3400;
    }
    return 4200;
  }

  destroy() {
    this.disposed = true;
    if (this.animationFrameId) {
      window.cancelAnimationFrame(this.animationFrameId);
      this.animationFrameId = 0;
    }

    if (this.app) {
      this.app.destroy(true, { children: true, texture: false, baseTexture: false });
    }

    if (this.container) {
      this.container.replaceChildren();
      this.container.dataset.haruFrame = '0';
    }

    this.model = null;
    this.app = null;
    this.payload = null;
    this.replySync = null;
    this.currentFrameIndex = 0;
    this.lastRenderAt = 0;
    this.lastMotionAt = 0;
  }
}

export class HaruLive2DPlayer extends Live2DPlayer {}
