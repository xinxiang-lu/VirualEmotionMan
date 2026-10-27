const clamp = (value, min, max) => Math.min(Math.max(value, min), max);

export const ASSISTANT_PARAMETER_ORDER = [
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
];

const roundFrameValue = (value) => Math.round(value * 10000) / 10000;

const containsAny = (text, keywords) => keywords.some((keyword) => text.includes(keyword));

export const estimateReplyDuration = (text = '') => {
  const cleanLength = String(text || '').replace(/\s+/g, '').length;
  return clamp(1.8 + cleanLength * 0.085, 2.2, 14);
};

export const inferAssistantReplyProfile = (text = '') => {
  const source = String(text || '').toLowerCase();
  const encouragement = containsAny(source, ['没关系', '可以', '一起', '慢慢', '我会', '陪你', '别急', '没事']);
  const concern = containsAny(source, ['风险', '预警', '注意', '失眠', '痛苦', '难受', '撑不住', '焦虑', '害怕']);
  const upbeat = containsAny(source, ['很好', '不错', '相信', '可以做到', '进步', '开心', '轻松']);
  const reflective = containsAny(source, ['如果你愿意', '也许', '或许', '可以先', '先从']);
  const questionLike = source.includes('？') || source.includes('?');
  const exclamatory = source.includes('！') || source.includes('!');

  const smileBias = clamp(
    0.18 + (encouragement ? 0.18 : 0) + (upbeat ? 0.16 : 0) - (concern ? 0.08 : 0),
    0.08,
    0.58,
  );
  const concernBias = clamp(0.12 + (concern ? 0.26 : 0) + (reflective ? 0.08 : 0), 0.08, 0.54);
  const arousal = clamp(0.18 + (questionLike ? 0.08 : 0) + (exclamatory ? 0.12 : 0) + (upbeat ? 0.1 : 0), 0.12, 0.62);
  const softness = clamp(0.48 + (encouragement ? 0.18 : 0) + (reflective ? 0.08 : 0), 0.35, 0.82);

  return {
    smileBias,
    concernBias,
    arousal,
    softness,
    motionHint: concern ? 'supportive_focus' : upbeat ? 'gentle_positive' : 'warm_support',
  };
};

export const buildAssistantReplyPayload = ({ text = '', duration = 0, fps = 25, profile = null } = {}) => {
  const resolvedFps = Math.max(Number(fps) || 25, 1);
  const resolvedDuration = Math.max(Number(duration) || estimateReplyDuration(text), 0.8);
  const frameCount = Math.max(Math.round(resolvedDuration * resolvedFps), 12);
  const replyProfile = profile || inferAssistantReplyProfile(text);

  const parameterFrames = Array.from({ length: frameCount }, (_, frame) => {
    const progress = frameCount <= 1 ? 0 : frame / (frameCount - 1);
    const phase = progress * Math.PI * (2.4 + replyProfile.arousal * 1.6);
    const headWave = Math.sin(phase);
    const bodyWave = Math.sin(phase * 0.72 + 0.35);
    const gazeWave = Math.sin(phase * 0.54 + 1.1);
    const emphasis = 0.5 + 0.5 * Math.sin(progress * Math.PI * 3.2 + 0.4);
    const smile = clamp(replyProfile.smileBias + emphasis * 0.08, 0, 1);
    const concern = clamp(replyProfile.concernBias + (1 - emphasis) * 0.04, 0, 1);

    const values = {
      ParamAngleX: headWave * (2.4 + replyProfile.arousal * 1.8),
      ParamAngleY: Math.cos(phase * 0.82) * (1.8 + replyProfile.softness * 1.4),
      ParamAngleZ: Math.sin(phase * 0.66) * 1.8,
      ParamBodyAngleX: bodyWave * (0.8 + replyProfile.arousal * 0.7),
      ParamBodyAngleY: Math.cos(phase * 0.45) * 0.45,
      ParamBodyAngleZ: bodyWave * 0.75,
      ParamBodyUpper: 0.12 + bodyWave * 0.06,
      ParamBreath: clamp(0.34 + Math.sin(progress * Math.PI * 2.1) * 0.1, 0, 1),
      ParamEyeLOpen: clamp(0.76 + replyProfile.softness * 0.14 - concern * 0.05, 0, 1),
      ParamEyeROpen: clamp(0.76 + replyProfile.softness * 0.14 - concern * 0.05, 0, 1),
      ParamEyeLSmile: clamp(smile * 0.78, 0, 1),
      ParamEyeRSmile: clamp(smile * 0.78, 0, 1),
      ParamEyeForm: clamp(smile * 0.18 - concern * 0.08, -1, 1),
      ParamEyeBallX: gazeWave * 0.12,
      ParamEyeBallY: Math.cos(phase * 0.58) * 0.08,
      ParamBrowLY: clamp(0.1 + concern * 0.18 + emphasis * 0.05, -1, 1),
      ParamBrowRY: clamp(0.1 + concern * 0.18 + emphasis * 0.05, -1, 1),
      ParamBrowLX: clamp(-gazeWave * 0.04, -1, 1),
      ParamBrowRX: clamp(-gazeWave * 0.04, -1, 1),
      ParamBrowLAngle: clamp(0.06 + concern * 0.15 + emphasis * 0.06, -1, 1),
      ParamBrowRAngle: clamp(0.06 + concern * 0.15 + emphasis * 0.06, -1, 1),
      ParamBrowLForm: clamp(smile * 0.06 - concern * 0.06, -1, 1),
      ParamBrowRForm: clamp(smile * 0.06 - concern * 0.06, -1, 1),
      ParamMouthOpenY: clamp(0.12 + emphasis * 0.16, 0, 1),
      ParamMouthForm: clamp(-0.18 + smile * 0.72 - concern * 0.18, -2, 1),
      ParamFaceForm: clamp(smile * 0.08 - concern * 0.06, -1, 1),
    };

    return {
      frame,
      values: ASSISTANT_PARAMETER_ORDER.map((parameterId) => roundFrameValue(values[parameterId] ?? 0)),
    };
  });

  return {
    model: 'AssistantReply',
    mapping_version: 'reply_audio_sync_v1',
    fps: resolvedFps,
    frame_count: frameCount,
    parameter_ids: ASSISTANT_PARAMETER_ORDER,
    parameter_frames: parameterFrames,
    motion_hint: replyProfile.motionHint,
  };
};
