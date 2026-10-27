<template>
  <section class="workspace">
    <aside class="left-column">
      <SidebarMenu :items="menuItems" :active-key="activeMenu" @select="handleMenuSelect" />
      <ChatSessionList
        :sessions="filteredSessions"
        :active-session-id="activeSessionId"
        @select="selectSession"
        @rename="renameSession"
        @delete="deleteSession"
      />
      <UserAvatarMenu
        :username="authStore.displayName"
        :avatar-url="profile.avatarUrl || authStore.user?.avatarUrl || ''"
        subtitle="点击展开更多功能"
        :items="avatarMenuItems"
        @select="handleAvatarAction"
      />
    </aside>

    <section class="center-column">
      <DigitalHumanPanel
        :analysis="activeDigitalHumanSummary"
        :haru-payload="activeHaruPayload"
        :haru-loading="digitalHumanAnalysisLoading"
        :settings="settings"
        :messages="activeMessages"
        :sending="isSending"
      />
      <ChatInputBox
        v-model="draft"
        :voice-active="voiceActive"
        :video-capture-active="videoCaptureActive"
        :sending="isSending"
        :audio-file-name="attachedAudioName"
        :video-file-name="attachedVideoName"
        :video-capture-status="videoCaptureStatus"
        :status-text="chatStatusText"
        @toggle-voice="toggleVoiceCapture"
        @toggle-video="toggleVideoCapture"
        @clear-audio="clearAudioSelection"
        @clear-video="clearVideoSelection"
        @send="sendMessage"
      />
    </section>

    <section class="right-column">
      <MessageList :messages="activeMessages" />
    </section>

    <ProfileModal
      :visible="showProfile"
      :profile="profile"
      :saving="profileSaving"
      @close="showProfile = false"
      @save="saveProfile"
    />
    <SettingsModal :visible="showSettings" :settings="settings" @close="showSettings = false" @save="saveSettings" />

    <div v-if="activeSupportDialog" class="dialog-mask" @click.self="activeSupportDialog = ''">
      <section class="dialog-panel card-surface">
        <h2>{{ supportActions[activeSupportDialog].title }}</h2>
        <p>{{ supportActions[activeSupportDialog].description }}</p>
        <div class="dialog-actions">
          <button class="primary-button" type="button" :disabled="transferSubmitting" @click="handleSupportConfirm">
            {{
              activeSupportDialog === 'transfer'
                ? transferSubmitting
                  ? '提交中...'
                  : '提交申请'
                : '我知道了'
            }}
          </button>
        </div>
      </section>
    </div>

    <div v-if="showAssessmentDialog" class="dialog-mask" @click.self="showAssessmentDialog = false">
      <section class="dialog-panel assessment-dialog card-surface">
        <h2>选择本次评估量表</h2>
        <p>一段评估对话只会使用一张量表，全部题项完成后才进入正式评分。</p>
        <div class="scale-list">
          <button
            v-for="scale in questionnaireScales"
            :key="scale.id"
            class="scale-option"
            type="button"
            :disabled="assessmentStarting"
            @click="startAssessment(scale.id)"
          >
            <strong>{{ scale.name }}</strong>
            <span>{{ scale.label }}</span>
            <small>{{ scale.itemCount }} 题 · {{ scale.timeWindow }}</small>
          </button>
        </div>
        <div class="dialog-actions split-actions">
          <button class="ghost-button" type="button" @click="goAssessmentHistory">查看历史评估</button>
          <button class="ghost-button" type="button" @click="showAssessmentDialog = false">取消</button>
        </div>
      </section>
    </div>
  </section>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue';
import { useRouter } from 'vue-router';
import {
  createConversation as createConversationRequest,
  deleteConversation as deleteConversationRequest,
  fetchConversationMessages,
  fetchConversations,
  fetchMessageMultimodalAnalysis,
  fetchMyProfile,
  fetchQuestionnaireScales,
  fetchQuestionnaireStatus,
  fetchMySettings,
  renameConversation as renameConversationRequest,
  requestHumanIntervention,
  sendConversationMessage,
  startQuestionnaireSession,
  updateMyProfile as updateMyProfileRequest,
  updateMySettings as updateMySettingsRequest,
} from '@/api/chat';
import ChatInputBox from '@/components/ChatInputBox.vue';
import ChatSessionList from '@/components/ChatSessionList.vue';
import DigitalHumanPanel from '@/components/DigitalHumanPanel.vue';
import MessageList from '@/components/MessageList.vue';
import ProfileModal from '@/components/ProfileModal.vue';
import SettingsModal from '@/components/SettingsModal.vue';
import SidebarMenu from '@/components/SidebarMenu.vue';
import UserAvatarMenu from '@/components/UserAvatarMenu.vue';
import { getRealtimeSocket, joinConversationRoom, leaveConversationRoom } from '@/services/realtime';
import { useAuthStore } from '@/store/auth';

const VIDEO_MIME_TYPES = [
  'video/mp4;codecs=h264,aac',
  'video/mp4',
  'video/webm;codecs=vp9,opus',
  'video/webm;codecs=vp8,opus',
  'video/webm',
];
const AUDIO_MIME_TYPES = [
  'audio/webm;codecs=opus',
  'audio/webm',
  'audio/ogg;codecs=opus',
  'audio/ogg',
];

const router = useRouter();
const authStore = useAuthStore();

const supportActions = {
  transfer: {
    title: '转人工',
    description: '提交后，管理员端人员管理列表会立即显示人工介入入口，方便尽快接管当前会话。',
  },
};

const menuItems = [
  { key: 'new-chat', label: '新聊天', description: '创建一个新的聊天会话' },
  { key: 'assessment', label: '状态评估', description: '查看近期状态评估结果' },
];

const avatarMenuItems = [
  { key: 'profile', label: '个人信息' },
  { key: 'settings', label: '个性化设置' },
  { key: 'transfer', label: '转人工' },
];

const activeMenu = ref('new-chat');
const activeSessionId = ref('');
const draft = ref('');
const voiceActive = ref(false);
const videoCaptureActive = ref(false);
const videoCaptureStatus = ref('');
const attachedAudio = ref(null);
const attachedVideo = ref(null);
const showProfile = ref(false);
const showSettings = ref(false);
const showAssessmentDialog = ref(false);
const activeSupportDialog = ref('');
const transferSubmitting = ref(false);
const assessmentStarting = ref(false);
const profile = ref({});
const sessions = ref([]);
const questionnaireScales = ref([]);
const activeQuestionnaire = ref(null);
const messagesBySession = reactive({});
const settings = reactive({
  systemPrompt: '',
  avatar: '',
  voiceSpeed: 1,
  defaultAvatarCode: '',
  availableAvatars: [],
  selectedAvatar: null,
});
const isSending = ref(false);
const profileSaving = ref(false);
const activeDigitalHumanAnalysis = ref(null);
const digitalHumanAnalysisLoading = ref(false);
const multimodalAnalysisCache = reactive({});
const digitalHumanAnalysisRequestKey = ref('');
const videoLinkedVoiceCapture = ref(false);

let videoStream = null;
let videoRecorder = null;
let videoChunks = [];
let audioStream = null;
let audioRecorder = null;
let audioChunks = [];
let realtimeSocket = null;
let joinedConversationId = '';
const handledRealtimeEventKeys = new Set();

const filteredSessions = computed(() => sessions.value);

const activeMessages = computed(() => messagesBySession[activeSessionId.value] || []);
const chatStatusText = computed(() => {
  if (isSending.value) return '消息已发送，心陪陪正在整理回复...';
  const session = activeQuestionnaire.value;
  if (session?.status === 'assessment_active') {
    return `${session.scaleName} 对话式评估进行中：${session.answeredItemCount || 0}/${session.requiredItemCount || 0} 题。请继续按当前问题回答。`;
  }
  return '';
});
const attachedAudioName = computed(() => attachedAudio.value?.name || '');
const attachedVideoName = computed(() => attachedVideo.value?.name || '');
const latestMultimodalMessage = computed(
  () => [...activeMessages.value].reverse().find((message) => message.hasMultimodalAnalysis) || null,
);
const activeDigitalHumanSummary = computed(
  () => activeDigitalHumanAnalysis.value?.summary || latestMultimodalMessage.value?.multimodalSummary || null,
);
const activeHaruPayload = computed(
  () =>
    activeDigitalHumanAnalysis.value?.prediction_result?.live2d_adapter_payload ||
    activeDigitalHumanAnalysis.value?.prediction_result?.haru_adapter_payload ||
    null,
);
const activeDigitalHumanSourceKey = computed(() => {
  const latestMessage = latestMultimodalMessage.value;
  if (!activeSessionId.value || !latestMessage?.id) {
    return `${activeSessionId.value || 'none'}:empty`;
  }
  return `${activeSessionId.value}:${latestMessage.id}:${latestMessage.multimodalSummary?.analysis_mode || ''}`;
});

const syncSettings = (payload = {}) => {
  settings.systemPrompt = payload.systemPrompt || '';
  settings.avatar = payload.avatar || '';
  settings.voiceSpeed = Number(payload.voiceSpeed || 1);
  settings.defaultAvatarCode = payload.defaultAvatarCode || '';
  settings.availableAvatars = Array.isArray(payload.availableAvatars) ? payload.availableAvatars : [];
  settings.selectedAvatar = payload.selectedAvatar || null;
};

const loadSessionMessages = async (sessionId) => {
  if (!sessionId) return;
  const data = await fetchConversationMessages(sessionId);
  messagesBySession[sessionId] = data.messages || [];
};

const upsertMessages = (sessionId, nextMessages = []) => {
  if (!sessionId) return;
  const messages = Array.isArray(nextMessages) ? nextMessages.filter(Boolean) : [nextMessages].filter(Boolean);
  if (!messages.length) return;

  const current = messagesBySession[sessionId] || [];
  const byId = new Map(current.map((message) => [String(message.id), message]));
  messages.forEach((message) => {
    byId.set(String(message.id), message);
  });

  const existingIds = new Set(current.map((message) => String(message.id)));
  const appended = messages.filter((message) => !existingIds.has(String(message.id)));
  messagesBySession[sessionId] = [
    ...current.map((message) => byId.get(String(message.id)) || message),
    ...appended,
  ];
};

const updateConversationSnapshot = (conversation) => {
  if (!conversation?.id) return;
  const index = sessions.value.findIndex((session) => session.id === conversation.id);
  if (index >= 0) {
    sessions.value.splice(index, 1, conversation);
  } else {
    sessions.value = [conversation, ...sessions.value];
  }
};

const joinActiveRealtimeConversation = () => {
  if (joinedConversationId && joinedConversationId !== activeSessionId.value) {
    leaveConversationRoom(joinedConversationId);
    joinedConversationId = '';
  }
  if (!activeSessionId.value || joinedConversationId === activeSessionId.value) return;
  joinConversationRoom(activeSessionId.value);
  joinedConversationId = activeSessionId.value;
};

const setupRealtime = () => {
  realtimeSocket = getRealtimeSocket();
  if (!realtimeSocket) return;

  realtimeSocket.off('message:new');
  realtimeSocket.off('questionnaire:updated');
  realtimeSocket.off('intervention:started');
  realtimeSocket.off('intervention:ended');

  realtimeSocket.on('message:new', (payload = {}) => {
    const sessionId = payload.conversationId;
    if (!sessionId || !payload.message) return;
    upsertMessages(sessionId, payload.message);
    updateConversationSnapshot(payload.conversation);
  });

  realtimeSocket.on('questionnaire:updated', (payload = {}) => {
    if (String(payload.conversationId) !== String(activeSessionId.value)) return;
    activeQuestionnaire.value = payload.questionnaire || null;
  });

  realtimeSocket.on('intervention:started', (payload = {}) => {
    if (String(payload.conversationId) !== String(activeSessionId.value)) return;
    activeQuestionnaire.value = activeQuestionnaire.value;
  });

  realtimeSocket.on('intervention:ended', (payload = {}) => {
    if (String(payload.conversationId) !== String(activeSessionId.value)) return;
    const eventKey = `intervention:ended:${payload.session?.id || payload.conversationId}`;
    if (handledRealtimeEventKeys.has(eventKey)) return;
    handledRealtimeEventKeys.add(eventKey);
    window.alert('本次人工介入已结束。');
  });

  joinActiveRealtimeConversation();
};

const loadQuestionnaireStatus = async (sessionId) => {
  if (!sessionId) {
    activeQuestionnaire.value = null;
    return;
  }
  try {
    const data = await fetchQuestionnaireStatus(sessionId);
    activeQuestionnaire.value = data.questionnaire || null;
  } catch (error) {
    console.error('Questionnaire status load failed:', error);
    activeQuestionnaire.value = null;
  }
};

const hydrateLatestDigitalHumanAnalysis = async () => {
  const latestMessage = latestMultimodalMessage.value;
  const conversationId = activeSessionId.value;

  if (!conversationId || !latestMessage?.id) {
    activeDigitalHumanAnalysis.value = null;
    digitalHumanAnalysisLoading.value = false;
    digitalHumanAnalysisRequestKey.value = '';
    return;
  }

  const fallbackPayload = latestMessage.multimodalSummary
    ? {
        summary: latestMessage.multimodalSummary,
        prediction_result: null,
      }
    : null;

  activeDigitalHumanAnalysis.value = fallbackPayload;

  if (latestMessage.multimodalSummary?.analysis_mode !== 'full_multimodal') {
    digitalHumanAnalysisLoading.value = false;
    digitalHumanAnalysisRequestKey.value = '';
    return;
  }

  const cacheKey = `${conversationId}:${latestMessage.id}`;
  if (multimodalAnalysisCache[cacheKey]) {
    activeDigitalHumanAnalysis.value = multimodalAnalysisCache[cacheKey];
    digitalHumanAnalysisLoading.value = false;
    digitalHumanAnalysisRequestKey.value = cacheKey;
    return;
  }

  digitalHumanAnalysisLoading.value = true;
  digitalHumanAnalysisRequestKey.value = cacheKey;

  try {
    const payload = await fetchMessageMultimodalAnalysis(conversationId, latestMessage.id);
    multimodalAnalysisCache[cacheKey] = payload;

    if (digitalHumanAnalysisRequestKey.value === cacheKey) {
      activeDigitalHumanAnalysis.value = payload;
    }
  } catch (error) {
    console.error(error);
    if (digitalHumanAnalysisRequestKey.value === cacheKey) {
      activeDigitalHumanAnalysis.value = fallbackPayload;
    }
  } finally {
    if (digitalHumanAnalysisRequestKey.value === cacheKey) {
      digitalHumanAnalysisLoading.value = false;
    }
  }
};

const syncProfile = (payload = {}) => {
  profile.value = payload;
  authStore.updateUserSnapshot({
    phone: profile.value.phone || authStore.user?.phone || '',
    nickname: profile.value.nickname || authStore.user?.nickname || '',
    avatarUrl: profile.value.avatarUrl || authStore.user?.avatarUrl || '',
  });
};

const loadProfile = async () => {
  const data = await fetchMyProfile();
  syncProfile(data.profile || {});
};

const clearAudioSelection = () => {
  attachedAudio.value = null;
};

const clearVideoSelection = () => {
  attachedVideo.value = null;
  if (!videoCaptureActive.value) {
    videoCaptureStatus.value = '';
  }
};

const selectSupportedMimeType = (candidates) => {
  if (typeof MediaRecorder === 'undefined') return '';
  return candidates.find((item) => MediaRecorder.isTypeSupported(item)) || '';
};

const extensionFromMimeType = (mimeType, kind) => {
  if (mimeType?.includes('mp4')) return 'mp4';
  if (mimeType?.includes('ogg')) return kind === 'audio' ? 'ogg' : 'ogv';
  if (mimeType?.includes('webm')) return 'webm';
  return kind === 'audio' ? 'wav' : 'mp4';
};

const encodeWav = (audioBuffer) => {
  const channelCount = audioBuffer.numberOfChannels;
  const sampleRate = audioBuffer.sampleRate;
  const samples = audioBuffer.length;
  const bytesPerSample = 2;
  const blockAlign = channelCount * bytesPerSample;
  const buffer = new ArrayBuffer(44 + samples * blockAlign);
  const view = new DataView(buffer);

  const writeString = (offset, value) => {
    for (let index = 0; index < value.length; index += 1) {
      view.setUint8(offset + index, value.charCodeAt(index));
    }
  };

  writeString(0, 'RIFF');
  view.setUint32(4, 36 + samples * blockAlign, true);
  writeString(8, 'WAVE');
  writeString(12, 'fmt ');
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, channelCount, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * blockAlign, true);
  view.setUint16(32, blockAlign, true);
  view.setUint16(34, 16, true);
  writeString(36, 'data');
  view.setUint32(40, samples * blockAlign, true);

  let offset = 44;
  for (let sampleIndex = 0; sampleIndex < samples; sampleIndex += 1) {
    for (let channelIndex = 0; channelIndex < channelCount; channelIndex += 1) {
      const sample = Math.max(-1, Math.min(1, audioBuffer.getChannelData(channelIndex)[sampleIndex]));
      view.setInt16(offset, sample < 0 ? sample * 0x8000 : sample * 0x7fff, true);
      offset += bytesPerSample;
    }
  }

  return buffer;
};

const convertAudioBlobToWavFile = async (sourceBlob, fileName) => {
  const arrayBuffer = await sourceBlob.arrayBuffer();
  const AudioContextClass = window.AudioContext || window.webkitAudioContext;
  if (!AudioContextClass) {
    throw new Error('当前浏览器不支持音频转码');
  }

  const audioContext = new AudioContextClass();
  try {
    const decoded = await audioContext.decodeAudioData(arrayBuffer.slice(0));
    const wavBuffer = encodeWav(decoded);
    return new File([wavBuffer], fileName, { type: 'audio/wav' });
  } finally {
    await audioContext.close();
  }
};

const startVideoCapture = async () => {
  videoStream = await navigator.mediaDevices.getUserMedia({ video: true, audio: false });
  const mimeType = selectSupportedMimeType(VIDEO_MIME_TYPES);
  videoChunks = [];
  videoRecorder = mimeType ? new MediaRecorder(videoStream, { mimeType }) : new MediaRecorder(videoStream);
  videoRecorder.addEventListener('dataavailable', (event) => {
    if (event.data && event.data.size > 0) {
      videoChunks.push(event.data);
    }
  });
  videoRecorder.start();
  videoCaptureActive.value = true;
  videoCaptureStatus.value = '视频接入已开启，并已同步开始语音采集，发送时会一起附带本轮音视频片段。';
};

const stopVideoCapture = ({ commit = true } = {}) =>
  new Promise((resolve, reject) => {
    if (!videoRecorder) {
      videoCaptureActive.value = false;
      if (!commit) {
        videoCaptureStatus.value = '';
      }
      resolve(attachedVideo.value);
      return;
    }

      const recorder = videoRecorder;
      const stream = videoStream;
      const chunks = videoChunks;
      videoRecorder = null;
      videoStream = null;

      recorder.addEventListener(
        'stop',
        () => {
          try {
          let nextFile = attachedVideo.value;
          if (commit && chunks.length) {
            const blob = new Blob(chunks, { type: recorder.mimeType || 'video/webm' });
            const finalType = blob.type || recorder.mimeType || 'video/webm';
            const extension = extensionFromMimeType(finalType, 'video');
            nextFile = new File([blob], `video_${Date.now()}.${extension}`, { type: finalType });
            attachedVideo.value = nextFile;
            videoCaptureStatus.value =
              extension === 'mp4'
                ? '本轮视频已整理完成，将随消息一起发送。'
                : `当前浏览器未提供原生 mp4 录制，本轮改为 ${extension} 片段发送。`;
            } else if (!commit) {
              videoCaptureStatus.value = '';
            }
            stream?.getTracks().forEach((track) => track.stop());
            videoCaptureActive.value = false;
            videoChunks = [];
            if (!voiceActive.value) {
              videoLinkedVoiceCapture.value = false;
            }
            resolve(nextFile);
          } catch (error) {
            stream?.getTracks().forEach((track) => track.stop());
            videoCaptureActive.value = false;
            videoChunks = [];
            if (!voiceActive.value) {
              videoLinkedVoiceCapture.value = false;
            }
            reject(error);
          }
        },
        { once: true },
      );

    if (recorder.state !== 'inactive') {
      recorder.stop();
      } else {
        stream?.getTracks().forEach((track) => track.stop());
        videoCaptureActive.value = false;
        videoChunks = [];
        if (!voiceActive.value) {
          videoLinkedVoiceCapture.value = false;
        }
        resolve(attachedVideo.value);
      }
    });

const toggleVideoCapture = async () => {
  if (isSending.value) return;

  if (videoCaptureActive.value) {
    try {
      await stopVideoCapture({ commit: false });
      if (videoLinkedVoiceCapture.value && voiceActive.value) {
        await stopVoiceCapture({ commit: false });
        attachedAudio.value = null;
      }
      videoLinkedVoiceCapture.value = false;
    } catch (error) {
      console.error(error);
    }
    return;
  }

  if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === 'undefined') {
    window.alert('当前浏览器不支持视频采集。');
    return;
  }

  try {
    await startVideoCapture();
    if (!voiceActive.value) {
      try {
        await startVoiceCapture();
        videoLinkedVoiceCapture.value = true;
      } catch (voiceError) {
        await stopVideoCapture({ commit: false });
        videoLinkedVoiceCapture.value = false;
        throw voiceError;
      }
    } else {
      videoLinkedVoiceCapture.value = false;
      videoCaptureStatus.value = '视频接入已开启，将与当前语音采集一起发送本轮音视频内容。';
    }
  } catch (error) {
    console.error(error);
    window.alert('视频接入开启失败，请确认摄像头和麦克风权限已允许。');
  }
};

const startVoiceCapture = async () => {
  audioStream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false });
  const mimeType = selectSupportedMimeType(AUDIO_MIME_TYPES);
  audioChunks = [];
  audioRecorder = mimeType ? new MediaRecorder(audioStream, { mimeType }) : new MediaRecorder(audioStream);
  audioRecorder.addEventListener('dataavailable', (event) => {
    if (event.data && event.data.size > 0) {
      audioChunks.push(event.data);
    }
  });
  audioRecorder.start();
  voiceActive.value = true;
};

const stopVoiceCapture = ({ commit = true } = {}) =>
  new Promise((resolve, reject) => {
    if (!audioRecorder) {
      voiceActive.value = false;
      resolve(attachedAudio.value);
      return;
    }

      const recorder = audioRecorder;
      const stream = audioStream;
      const chunks = audioChunks;
      audioRecorder = null;
      audioStream = null;

      recorder.addEventListener(
        'stop',
        async () => {
        try {
          let nextFile = attachedAudio.value;
          if (commit && chunks.length) {
            const sourceBlob = new Blob(chunks, { type: recorder.mimeType || 'audio/webm' });
            nextFile = await convertAudioBlobToWavFile(sourceBlob, `voice_${Date.now()}.wav`);
            attachedAudio.value = nextFile;
            }
            stream?.getTracks().forEach((track) => track.stop());
            voiceActive.value = false;
            audioChunks = [];
            if (!videoCaptureActive.value) {
              videoLinkedVoiceCapture.value = false;
            }
            resolve(nextFile);
          } catch (error) {
            stream?.getTracks().forEach((track) => track.stop());
            voiceActive.value = false;
            audioChunks = [];
            if (!videoCaptureActive.value) {
              videoLinkedVoiceCapture.value = false;
            }
            reject(error);
          }
        },
        { once: true },
      );

    if (recorder.state !== 'inactive') {
      recorder.stop();
      } else {
        stream?.getTracks().forEach((track) => track.stop());
        voiceActive.value = false;
        audioChunks = [];
        if (!videoCaptureActive.value) {
          videoLinkedVoiceCapture.value = false;
        }
        resolve(attachedAudio.value);
      }
    });

const toggleVoiceCapture = async () => {
  if (isSending.value) return;

  if (voiceActive.value) {
    try {
      await stopVoiceCapture({ commit: false });
      attachedAudio.value = null;
    } catch (error) {
      console.error(error);
    }
    return;
  }

  if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === 'undefined') {
    window.alert('当前浏览器不支持语音采集。');
    return;
  }

  try {
    await startVoiceCapture();
  } catch (error) {
    console.error(error);
    voiceActive.value = false;
    window.alert('语音采集开启失败，请确认麦克风权限已允许。');
  }
};

const buildPendingContent = (content, audioFile, videoFile) => {
  if (content) return content;

  const flags = [];
  if (audioFile) flags.push('[已采集语音]');
  if (videoFile) flags.push('[已采集视频]');
  return flags.join(' ');
};

const loadWorkspace = async () => {
  try {
    const [conversationData, profileData, settingsData] = await Promise.all([
      fetchConversations(),
      fetchMyProfile(),
      fetchMySettings(),
    ]);

    sessions.value = conversationData.conversations || [];
    activeSessionId.value = conversationData.active_conversation_id || sessions.value[0]?.id || '';
    syncProfile(profileData.profile || {});
    syncSettings(settingsData.settings);

    if (activeSessionId.value) {
      await loadSessionMessages(activeSessionId.value);
      await loadQuestionnaireStatus(activeSessionId.value);
      joinActiveRealtimeConversation();
    }
  } catch (error) {
    window.alert(error?.message || '工作台数据加载失败，请稍后重试。');
  }
};

const ensureQuestionnaireScales = async () => {
  if (questionnaireScales.value.length) return;
  const data = await fetchQuestionnaireScales();
  questionnaireScales.value = data.scales || [];
};

const handleMenuSelect = async (key) => {
  activeMenu.value = key;

  if (key === 'assessment') {
    try {
      await ensureQuestionnaireScales();
      showAssessmentDialog.value = true;
    } catch (error) {
      window.alert(error?.message || '量表列表加载失败，请稍后再试。');
    }
    return;
  }

  if (key === 'new-chat') {
    createConversationRequest()
      .then((data) => {
        const conversation = data.conversation;
        if (!conversation) return;
        sessions.value = [conversation, ...sessions.value];
        messagesBySession[conversation.id] = [];
        activeSessionId.value = conversation.id;
        joinActiveRealtimeConversation();
        draft.value = '';
        activeQuestionnaire.value = null;
        clearAudioSelection();
        clearVideoSelection();
      })
      .catch((error) => {
        window.alert(error?.message || '新建聊天失败，请稍后再试。');
      });
  }
};

const selectSession = async (sessionId) => {
  activeSessionId.value = sessionId;
  joinActiveRealtimeConversation();
  if (!messagesBySession[sessionId]) {
    try {
      await loadSessionMessages(sessionId);
    } catch (error) {
      window.alert(error?.message || '聊天记录加载失败，请稍后再试。');
    }
  }
  await loadQuestionnaireStatus(sessionId);
};

const startAssessment = async (scaleId) => {
  if (assessmentStarting.value) return;
  assessmentStarting.value = true;
  try {
    let sessionId = activeSessionId.value;
    if (!sessionId) {
      const created = await createConversationRequest({ title: '状态评估' });
      if (created.conversation) {
        sessions.value = [created.conversation, ...sessions.value];
        activeSessionId.value = created.conversation.id;
        messagesBySession[created.conversation.id] = [];
        joinActiveRealtimeConversation();
        sessionId = created.conversation.id;
      }
    }
    if (!sessionId) throw new Error('会话创建失败，请稍后再试。');

    const data = await startQuestionnaireSession(sessionId, { scaleId });
    activeQuestionnaire.value = data.questionnaire || null;
    if (data.assistant_message) {
      upsertMessages(sessionId, data.assistant_message);
    }
    if (data.conversation) {
      const index = sessions.value.findIndex((session) => session.id === sessionId);
      if (index >= 0) {
        sessions.value.splice(index, 1, data.conversation);
      }
    }
    showAssessmentDialog.value = false;
  } catch (error) {
    window.alert(error?.message || '评估启动失败，请稍后再试。');
  } finally {
    assessmentStarting.value = false;
  }
};

const goAssessmentHistory = () => {
  showAssessmentDialog.value = false;
  router.push({ name: 'assessment' });
};

const renameSession = async (session) => {
  const title = window.prompt('请输入新的会话名称', session?.title || '');
  if (title === null) return;

  const nextTitle = title.trim();
  if (!nextTitle) {
    window.alert('会话名称不能为空。');
    return;
  }

  try {
    const data = await renameConversationRequest(session.id, { title: nextTitle });
    const updatedConversation = data.conversation;
    sessions.value = sessions.value.map((item) => (item.id === updatedConversation.id ? updatedConversation : item));
  } catch (error) {
    window.alert(error?.message || '会话重命名失败，请稍后再试。');
  }
};

const deleteSession = async (session) => {
  if (!window.confirm(`确定删除“${session?.title || '当前会话'}”吗？删除后无法恢复。`)) {
    return;
  }

  const deletedTitle = session?.title || '当前会话';

  try {
    const data = await deleteConversationRequest(session.id);
    sessions.value = sessions.value.filter((item) => item.id !== session.id);
    delete messagesBySession[session.id];

    if (activeSessionId.value === session.id) {
      activeSessionId.value = data.active_conversation_id || sessions.value[0]?.id || '';
      draft.value = '';
      clearAudioSelection();
      clearVideoSelection();

      if (activeSessionId.value && !messagesBySession[activeSessionId.value]) {
        try {
          await loadSessionMessages(activeSessionId.value);
        } catch (error) {
          console.error('Next conversation load failed after deletion:', error);
          window.alert(error?.message || '当前会话已删除，但下一条聊天记录加载失败，请稍后重试。');
        }
      }
    }

    window.alert(data?.message || `“${deletedTitle}”已删除。`);
  } catch (error) {
    window.alert(error?.message || '会话删除失败，请稍后再试。');
  }
};

const formatPendingTime = (date = new Date()) =>
  date.toLocaleTimeString('zh-CN', {
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  });

const sendMessage = async () => {
  const content = draft.value.trim();
  if (isSending.value) return;

  let audioFile = attachedAudio.value;
  let videoFile = attachedVideo.value;

  if (voiceActive.value) {
    try {
      audioFile = await stopVoiceCapture({ commit: true });
    } catch (error) {
      console.error(error);
      window.alert('语音转换失败，请重试。');
      return;
    }
  }

  if (videoCaptureActive.value) {
    try {
      videoFile = await stopVideoCapture({ commit: true });
    } catch (error) {
      console.error(error);
      window.alert('视频整理失败，请检查摄像头权限后重试。');
      return;
    }
  }

  if (!content && !audioFile && !videoFile) {
    window.alert('当前没有可发送的文本、语音或视频内容。');
    return;
  }

  let sessionId = activeSessionId.value;
  let pendingUserId = '';
  let pendingAssistantId = '';
  const pendingContent = buildPendingContent(content, audioFile, videoFile);

  try {
    if (!activeSessionId.value) {
      const created = await createConversationRequest();
      if (created.conversation) {
        sessions.value = [created.conversation, ...sessions.value];
        activeSessionId.value = created.conversation.id;
        messagesBySession[created.conversation.id] = [];
        sessionId = created.conversation.id;
      }
    }

    if (!sessionId) {
      throw new Error('新会话创建失败，请稍后再试。');
    }

    const pendingMark = `${Date.now()}-${Math.random().toString(16).slice(2, 8)}`;
    pendingUserId = `pending-user-${pendingMark}`;
    pendingAssistantId = `pending-assistant-${pendingMark}`;
    const pendingTime = formatPendingTime();

    messagesBySession[sessionId] = [
      ...(messagesBySession[sessionId] || []),
      {
        id: pendingUserId,
        sender: 'user',
        senderLabel: authStore.displayName,
        content: pendingContent,
        time: pendingTime,
        isPending: true,
        audioUrl: audioFile ? '__pending__' : '',
        videoUrl: videoFile ? '__pending__' : '',
        multimodalSummary: null,
      },
      {
        id: pendingAssistantId,
        sender: 'assistant',
        senderLabel: '心陪陪',
        content: '心陪陪正在整理回复，请稍等...',
        time: '思考中',
        isPending: true,
      },
    ];

    const pendingConversationIndex = sessions.value.findIndex((session) => session.id === sessionId);
    if (pendingConversationIndex >= 0) {
      sessions.value.splice(pendingConversationIndex, 1, {
        ...sessions.value[pendingConversationIndex],
        preview: pendingContent,
      });
    }

    draft.value = '';
    isSending.value = true;

    let payload = { content };
    if (audioFile || videoFile) {
      payload = new FormData();
      if (content) payload.append('content', content);
      if (audioFile) payload.append('audio', audioFile);
      if (videoFile) payload.append('video', videoFile);
    }

    const data = await sendConversationMessage(sessionId, payload);
    activeQuestionnaire.value = data.questionnaire?.session || null;
    messagesBySession[sessionId] = (messagesBySession[sessionId] || []).filter(
      (message) => message.id !== pendingUserId && message.id !== pendingAssistantId,
    );
    upsertMessages(sessionId, [data.user_message, data.assistant_message]);

    attachedAudio.value = null;
    attachedVideo.value = null;
    videoCaptureStatus.value = '';

    const updatedConversation = data.conversation;
    const targetIndex = sessions.value.findIndex((session) => session.id === sessionId);
    if (targetIndex >= 0 && updatedConversation) {
      sessions.value.splice(targetIndex, 1, updatedConversation);
    }
  } catch (error) {
    if (sessionId) {
      messagesBySession[sessionId] = (messagesBySession[sessionId] || []).filter(
        (message) => message.id !== pendingUserId && message.id !== pendingAssistantId,
      );
    }
    draft.value = content;
    window.alert(error?.message || '发送失败，请稍后再试。');
  } finally {
    isSending.value = false;
  }
};

const handleAvatarAction = async (key) => {
  if (key === 'profile') {
    showProfile.value = true;
    try {
      await loadProfile();
    } catch (error) {
      window.alert(error?.message || '个人信息加载失败，请稍后再试。');
    }
    return;
  }

  if (key === 'settings') {
    showSettings.value = true;
    return;
  }

  if (key === 'transfer') {
    activeSupportDialog.value = key;
  }
};

const handleSupportConfirm = async () => {
  if (activeSupportDialog.value !== 'transfer') {
    activeSupportDialog.value = '';
    return;
  }

  if (transferSubmitting.value) return;

  transferSubmitting.value = true;
  try {
    const data = await requestHumanIntervention({
      conversation_id: activeSessionId.value || undefined,
    });
    activeSupportDialog.value = '';
    window.alert(data?.message || '已提交转人工申请。');
  } catch (error) {
    window.alert(error?.message || '转人工申请提交失败，请稍后再试。');
  } finally {
    transferSubmitting.value = false;
  }
};

const saveProfile = async (payload) => {
  profileSaving.value = true;
  try {
    const data = await updateMyProfileRequest(payload);
    syncProfile(data.profile || {});
    showProfile.value = false;
  } catch (error) {
    window.alert(error?.message || '个人信息保存失败，请稍后再试。');
  } finally {
    profileSaving.value = false;
  }
};

const saveSettings = (payload) => {
  updateMySettingsRequest(payload)
    .then((data) => {
      syncSettings(data.settings);
      showSettings.value = false;
    })
    .catch((error) => {
      window.alert(error?.message || '设置保存失败，请稍后再试。');
    });
};

watch(
  activeDigitalHumanSourceKey,
  () => {
    hydrateLatestDigitalHumanAnalysis();
  },
  { immediate: true },
);

onMounted(() => {
  setupRealtime();
  loadWorkspace();
});

onBeforeUnmount(async () => {
  if (joinedConversationId) {
    leaveConversationRoom(joinedConversationId);
    joinedConversationId = '';
  }
  if (realtimeSocket) {
    realtimeSocket.off('message:new');
    realtimeSocket.off('questionnaire:updated');
    realtimeSocket.off('intervention:started');
    realtimeSocket.off('intervention:ended');
  }
  try {
    await stopVideoCapture({ commit: false });
  } catch (error) {
    console.error(error);
  }

  try {
    await stopVoiceCapture({ commit: false });
  } catch (error) {
    console.error(error);
  }
});
</script>

<style scoped>
.workspace { height:calc(100vh - 132px); max-height:calc(100vh - 132px); min-height:calc(100vh - 132px); overflow:hidden; display:grid; grid-template-columns:minmax(220px,2fr) minmax(440px,5fr) minmax(300px,3fr); gap:18px; }
.left-column, .center-column, .right-column { min-height:0; }
.left-column { display:grid; grid-template-rows:auto minmax(0, 1fr) auto; gap:16px; }
.center-column { display:grid; grid-template-rows:minmax(0, 1fr) auto; gap:16px; min-width:0; }
.right-column { min-height:0; height:100%; display:flex; }
.dialog-mask { position:fixed; inset:0; z-index:30; background:rgba(48,61,67,.28); display:flex; align-items:center; justify-content:center; padding:24px; }
.dialog-panel { width:min(460px, 100%); padding:24px; }
.dialog-panel h2 { margin:0; color:var(--text-main); }
.dialog-panel p { margin:14px 0 0; color:var(--text-soft); line-height:1.8; }
.dialog-actions { margin-top:20px; display:flex; justify-content:end; }
.assessment-dialog { width:min(560px, 100%); }
.scale-list { margin-top:18px; display:grid; gap:10px; }
.scale-option { width:100%; border:1px solid rgba(90,117,118,.18); background:rgba(255,255,255,.86); border-radius:8px; padding:14px 16px; display:grid; gap:5px; text-align:left; cursor:pointer; color:var(--text-main); transition:border-color .2s ease, transform .2s ease, box-shadow .2s ease; }
.scale-option:hover:not(:disabled) { border-color:rgba(43,125,116,.42); transform:translateY(-1px); box-shadow:0 10px 22px rgba(47,79,79,.08); }
.scale-option:disabled { opacity:.68; cursor:not-allowed; }
.scale-option strong { font-size:1rem; }
.scale-option span { color:var(--text-main); }
.scale-option small { color:var(--text-soft); }
.split-actions { justify-content:space-between; gap:12px; }
@media (max-width:1180px) { .workspace { height:auto; max-height:none; min-height:0; overflow:visible; grid-template-columns:1fr; } .right-column { min-height:420px; } }
</style>

