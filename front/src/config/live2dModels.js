const clamp = (value, min, max) => Math.min(Math.max(value, min), max);

export const LIVE2D_MODEL_REGISTRY = {
  haru: {
    code: 'haru',
    label: 'Haru',
    modelPath: '/live2d/Haru/Haru.model3.json',
    previewPath: '/live2d/Haru/Haru.2048/texture_00.png',
    fit: {
      widthRatio: 0.54,
      heightRatio: 1.18,
      xRatio: 0.5,
      yRatio: 1.08,
    },
    motionGroups: {
      idle: 'Idle',
      responding: 'TapBody',
      listening: 'Idle',
    },
    supportedParameterIds: [
      'ParamAngleX',
      'ParamAngleY',
      'ParamAngleZ',
      'ParamBodyAngleX',
      'ParamBodyAngleY',
      'ParamBodyAngleZ',
      'ParamBodyUpper',
      'ParamBreath',
      'ParamEyeLOpen',
      'ParamEyeROpen',
      'ParamEyeLSmile',
      'ParamEyeRSmile',
      'ParamEyeForm',
      'ParamEyeBallX',
      'ParamEyeBallY',
      'ParamBrowLY',
      'ParamBrowRY',
      'ParamBrowLX',
      'ParamBrowRX',
      'ParamBrowLAngle',
      'ParamBrowRAngle',
      'ParamBrowLForm',
      'ParamBrowRForm',
      'ParamMouthOpenY',
      'ParamMouthForm',
      'ParamFaceForm',
    ],
  },
  hiyori: {
    code: 'hiyori',
    label: 'Hiyori Momose',
    modelPath: '/live2d/Hiyori/hiyori_free_t08.model3.json',
    previewPath: '/live2d/Hiyori/hiyori_free_t08.2048/texture_00.png',
    fit: {
      widthRatio: 0.62,
      heightRatio: 1.2,
      xRatio: 0.5,
      yRatio: 1.06,
    },
    motionGroups: {
      idle: 'Idle',
      responding: 'Tap@Body',
      listening: 'Tap',
    },
    supportedParameterIds: [
      'ParamAngleX',
      'ParamAngleY',
      'ParamAngleZ',
      'ParamBodyAngleX',
      'ParamBodyAngleY',
      'ParamBodyAngleZ',
      'ParamBreath',
      'ParamEyeLOpen',
      'ParamEyeROpen',
      'ParamEyeLSmile',
      'ParamEyeRSmile',
      'ParamEyeBallX',
      'ParamEyeBallY',
      'ParamBrowLForm',
      'ParamBrowRForm',
      'ParamMouthOpenY',
      'ParamMouthForm',
      'ParamCheek',
    ],
    deriveParameters: (semanticValues) => {
      const smile = ((semanticValues.ParamEyeLSmile || 0) + (semanticValues.ParamEyeRSmile || 0)) * 0.5;
      const mouthSmile = Math.max(semanticValues.ParamMouthForm || 0, 0);
      return {
        ParamCheek: clamp(smile * 0.72 + mouthSmile * 0.28, 0, 1),
      };
    },
  },
};

export const normalizeLive2dModelCode = (code) => {
  const normalized = String(code || '').trim().toLowerCase();
  if (normalized && LIVE2D_MODEL_REGISTRY[normalized]) {
    return normalized;
  }
  return 'haru';
};

export const getLive2dModelConfig = (code) => LIVE2D_MODEL_REGISTRY[normalizeLive2dModelCode(code)];
