from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
load_dotenv(BASE_DIR / ".env")


class BaseConfig:
    SECRET_KEY = "dev-secret-key"
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL", f"sqlite:///{(DATA_DIR / 'app.db').as_posix()}")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "connect_args": {"timeout": 30},
    }
    JSON_AS_ASCII = False
    OSS_ACCESS_KEY_ID = os.getenv("OSS_ACCESS_KEY_ID")
    OSS_ACCESS_KEY_SECRET = os.getenv("OSS_ACCESS_KEY_SECRET")
    OSS_BUCKET_NAME = os.getenv("OSS_BUCKET_NAME")
    OSS_ENDPOINT = os.getenv("OSS_ENDPOINT")
    OSS_REGION = os.getenv("OSS_REGION")
    OSS_PUBLIC_BASE_URL = os.getenv("OSS_PUBLIC_BASE_URL", "")
    AVATAR_UPLOAD_MAX_MB = int(os.getenv("AVATAR_UPLOAD_MAX_MB", "5"))
    CHAT_MEDIA_ROOT = os.getenv("CHAT_MEDIA_ROOT", str((DATA_DIR / "chat_media").resolve()))
    STATIC_AUDIO_DIR = os.getenv("STATIC_AUDIO_DIR", str((BASE_DIR / "static" / "audio").resolve()))
    STATIC_AUDIO_URL_PREFIX = os.getenv("STATIC_AUDIO_URL_PREFIX", "/static/audio")
    MULTIMODAL_ANALYSIS_ROOT = os.getenv(
        "MULTIMODAL_ANALYSIS_ROOT",
        str((DATA_DIR / "multimodal_analysis").resolve()),
    )
    DIGITAL_HUMAN_IDENTITY_ROOT = os.getenv(
        "DIGITAL_HUMAN_IDENTITY_ROOT",
        str((DATA_DIR / "digital_human_identities").resolve()),
    )
    LIVE2D_MODEL_ROOT = os.getenv(
        "LIVE2D_MODEL_ROOT",
        str((PROJECT_ROOT / "front" / "public" / "live2d").resolve()),
    )
    DIGITAL_HUMAN_CHECKPOINT_PATH = os.getenv(
        "DIGITAL_HUMAN_CHECKPOINT_PATH",
        str((PROJECT_ROOT / "live2d_service" / "artifacts" / "model.pt").resolve()),
    )
    DIGITAL_HUMAN_DEVICE = os.getenv("DIGITAL_HUMAN_DEVICE", "")
    DIGITAL_HUMAN_CANDIDATE_NUM = int(os.getenv("DIGITAL_HUMAN_CANDIDATE_NUM", "3"))
    DIGITAL_HUMAN_DEFAULT_FPS = int(os.getenv("DIGITAL_HUMAN_DEFAULT_FPS", "25"))
    DIGITAL_HUMAN_MAX_SEQ_LEN = int(os.getenv("DIGITAL_HUMAN_MAX_SEQ_LEN", "751"))
    DIGITAL_HUMAN_SUMMARY_WINDOW_SECONDS = float(
        os.getenv("DIGITAL_HUMAN_SUMMARY_WINDOW_SECONDS", "3.0")
    )
    DIGITAL_HUMAN_SUMMARY_SEGMENTS = int(os.getenv("DIGITAL_HUMAN_SUMMARY_SEGMENTS", "3"))
    DIGITAL_HUMAN_EMOTION_EMA_ALPHA = float(os.getenv("DIGITAL_HUMAN_EMOTION_EMA_ALPHA", "0.4"))
    DIGITAL_HUMAN_SPEAKER_EMOTION_BLEND = float(os.getenv("DIGITAL_HUMAN_SPEAKER_EMOTION_BLEND", "0.01"))
    DIGITAL_HUMAN_SPEAKER_EMOTION_SHIFT = int(os.getenv("DIGITAL_HUMAN_SPEAKER_EMOTION_SHIFT", "2"))
    DIGITAL_HUMAN_PREDICTION_EMOTION_SHIFT = int(os.getenv("DIGITAL_HUMAN_PREDICTION_EMOTION_SHIFT", "-4"))
    DIGITAL_HUMAN_EMOTION_AU_GAIN = float(os.getenv("DIGITAL_HUMAN_EMOTION_AU_GAIN", "1.3"))
    DIGITAL_HUMAN_EMOTION_VA_GAIN = float(os.getenv("DIGITAL_HUMAN_EMOTION_VA_GAIN", "1.2"))
    DIGITAL_HUMAN_EMOTION_EXP_TEMPERATURE = float(os.getenv("DIGITAL_HUMAN_EMOTION_EXP_TEMPERATURE", "0.8"))
    DIGITAL_HUMAN_CANDIDATE_EMOTION_SPREAD = float(os.getenv("DIGITAL_HUMAN_CANDIDATE_EMOTION_SPREAD", "2.0"))
    LLM_PROVIDER = os.getenv("LLM_PROVIDER", "glm")
    GLM_API_KEY = os.getenv("GLM_API_KEY") or os.getenv("ZHIPUAI_API_KEY") or os.getenv("ZAI_API_KEY")
    GLM_MODEL = os.getenv("GLM_MODEL", "glm-4.7-flash")
    GLM_BASE_URL = os.getenv("GLM_BASE_URL", "https://api.z.ai/api/paas/v4")
    QWEN_API_KEY = os.getenv("QWEN_API_KEY") or os.getenv("DASHSCOPE_API_KEY")
    QWEN_MODEL = os.getenv("QWEN_MODEL", "qwen-plus")
    QWEN_BASE_URL = os.getenv("QWEN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
    DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
    DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash")
    DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    OPENAI_COMPATIBLE_API_KEY = os.getenv("OPENAI_COMPATIBLE_API_KEY")
    OPENAI_COMPATIBLE_MODEL = os.getenv("OPENAI_COMPATIBLE_MODEL", "")
    OPENAI_COMPATIBLE_BASE_URL = os.getenv("OPENAI_COMPATIBLE_BASE_URL", "")
    GLM_TIMEOUT_SECONDS = int(os.getenv("GLM_TIMEOUT_SECONDS", "60"))
    GLM_TEMPERATURE = float(os.getenv("GLM_TEMPERATURE", "0.7"))
    GLM_MAX_TOKENS = int(os.getenv("GLM_MAX_TOKENS", "1024"))
    GLM_HISTORY_LIMIT = int(os.getenv("GLM_HISTORY_LIMIT", "12"))
    GLM_RETRY_ATTEMPTS = int(os.getenv("GLM_RETRY_ATTEMPTS", "1"))
    GLM_RETRY_BACKOFF_SECONDS = float(os.getenv("GLM_RETRY_BACKOFF_SECONDS", "1.5"))
    GLM_THINKING_TYPE = os.getenv("GLM_THINKING_TYPE", "disabled")
    CHAT_REQUIRE_GLM = os.getenv("CHAT_REQUIRE_GLM", "1").lower() in {"1", "true", "yes", "on"}
    PROFILE_MEMORY_TEMPLATE_PATH = os.getenv("PROFILE_MEMORY_TEMPLATE_PATH", str((DATA_DIR / "profile_template.json").resolve()))
    QUESTIONNAIRE_ITEMS_PATH = os.getenv("QUESTIONNAIRE_ITEMS_PATH", str((DATA_DIR / "questionnaire_items.json").resolve()))
    QUESTIONNAIRE_ANSWER_LOOKBACK_DAYS = int(os.getenv("QUESTIONNAIRE_ANSWER_LOOKBACK_DAYS", "14"))
    RAG_KNOWLEDGE_PATH = os.getenv("RAG_KNOWLEDGE_PATH", str((PROJECT_ROOT / "rag_knowledge.json").resolve()))
    RAG_INDEX_DIR = os.getenv("RAG_INDEX_DIR", str((DATA_DIR / "rag_index").resolve()))
    RAG_EMBEDDING_DIM = int(os.getenv("RAG_EMBEDDING_DIM", "512"))
    RAG_CHUNK_SIZE = int(os.getenv("RAG_CHUNK_SIZE", "420"))
    RAG_CHUNK_OVERLAP = int(os.getenv("RAG_CHUNK_OVERLAP", "80"))
    RAG_TOP_K = int(os.getenv("RAG_TOP_K", "5"))
    RAG_MIN_SCORE = float(os.getenv("RAG_MIN_SCORE", "0.08"))
    ASR_BACKEND = os.getenv("ASR_BACKEND", "sensevoice_small")
    ASR_RUNTIME_PYTHON = os.getenv("ASR_RUNTIME_PYTHON", "<ASR_PYTHON_PATH>")
    ASR_MODEL_NAME = os.getenv("ASR_MODEL_NAME", "iic/SenseVoiceSmall")
    ASR_VAD_MODEL_NAME = os.getenv("ASR_VAD_MODEL_NAME", "iic/speech_fsmn_vad_zh-cn-16k-common-pytorch")
    ASR_DEVICE = os.getenv("ASR_DEVICE", "cuda:0")
    ASR_LANGUAGE = os.getenv("ASR_LANGUAGE", "auto")
    ASR_USE_ITN = os.getenv("ASR_USE_ITN", "0").lower() in {"1", "true", "yes", "on"}
    ASR_BATCH_SIZE_S = int(os.getenv("ASR_BATCH_SIZE_S", "60"))
    ASR_MERGE_VAD = os.getenv("ASR_MERGE_VAD", "1").lower() in {"1", "true", "yes", "on"}
    ASR_MERGE_LENGTH_S = int(os.getenv("ASR_MERGE_LENGTH_S", "15"))
    ASR_DISABLE_UPDATE = os.getenv("ASR_DISABLE_UPDATE", "1").lower() in {"1", "true", "yes", "on"}
    ASR_STARTUP_TIMEOUT_SECONDS = int(os.getenv("ASR_STARTUP_TIMEOUT_SECONDS", "600"))
    ASR_REQUEST_TIMEOUT_SECONDS = int(os.getenv("ASR_REQUEST_TIMEOUT_SECONDS", "180"))
    TTS_BACKEND = os.getenv("TTS_BACKEND", "demo")
    TTS_SPEED = float(os.getenv("TTS_SPEED", "1.0"))
    TTS_REQUEST_TIMEOUT_SECONDS = int(os.getenv("TTS_REQUEST_TIMEOUT_SECONDS", "300"))
    DOUBAO_TTS_BASE_URL = os.getenv("DOUBAO_TTS_BASE_URL", os.getenv("VOLCENGINE_TTS_BASE_URL", "https://sami.bytedance.com/api/v1/invoke"))
    DOUBAO_TTS_LEGACY_BASE_URL = os.getenv("DOUBAO_TTS_LEGACY_BASE_URL", os.getenv("VOLCENGINE_TTS_LEGACY_BASE_URL", "https://openspeech.bytedance.com/api/v1/tts"))
    DOUBAO_TTS_APP_ID = os.getenv("DOUBAO_TTS_APP_ID", os.getenv("VOLCENGINE_TTS_APP_ID", ""))
    DOUBAO_TTS_ACCESS_TOKEN = os.getenv("DOUBAO_TTS_ACCESS_TOKEN", os.getenv("VOLCENGINE_TTS_ACCESS_TOKEN", ""))
    DOUBAO_TTS_APP_KEY = os.getenv("DOUBAO_TTS_APP_KEY", os.getenv("VOLCENGINE_TTS_APP_KEY", ""))
    DOUBAO_TTS_TOKEN = os.getenv("DOUBAO_TTS_TOKEN", os.getenv("VOLCENGINE_TTS_TOKEN", ""))
    DOUBAO_TTS_ACCESS_KEY_ID = os.getenv("DOUBAO_TTS_ACCESS_KEY_ID", os.getenv("VOLCENGINE_TTS_ACCESS_KEY_ID", os.getenv("VOLC_ACCESSKEY", "")))
    DOUBAO_TTS_SECRET_ACCESS_KEY = os.getenv("DOUBAO_TTS_SECRET_ACCESS_KEY", os.getenv("VOLCENGINE_TTS_SECRET_ACCESS_KEY", os.getenv("VOLC_SECRETKEY", "")))
    DOUBAO_TTS_TOKEN_URL = os.getenv("DOUBAO_TTS_TOKEN_URL", os.getenv("VOLCENGINE_TTS_TOKEN_URL", "https://open.volcengineapi.com/?Action=GetToken&Version=2021-07-27"))
    DOUBAO_TTS_SPEAKER = os.getenv("DOUBAO_TTS_SPEAKER", os.getenv("VOLCENGINE_TTS_SPEAKER", "zh_female_qingxin"))
    DOUBAO_TTS_CLUSTER = os.getenv("DOUBAO_TTS_CLUSTER", os.getenv("VOLCENGINE_TTS_CLUSTER", "volcano_tts"))
    DOUBAO_TTS_VOICE_TYPE = os.getenv("DOUBAO_TTS_VOICE_TYPE", os.getenv("VOLCENGINE_TTS_VOICE_TYPE", "zh_female_vv_uranus_bigtts"))
    DOUBAO_TTS_MALE_SPEAKER = os.getenv("DOUBAO_TTS_MALE_SPEAKER", os.getenv("VOLCENGINE_TTS_MALE_SPEAKER", ""))
    DOUBAO_TTS_SAMPLE_RATE = int(os.getenv("DOUBAO_TTS_SAMPLE_RATE", os.getenv("VOLCENGINE_TTS_SAMPLE_RATE", "24000")))
    DOUBAO_TTS_ENABLE_TIMESTAMP = os.getenv("DOUBAO_TTS_ENABLE_TIMESTAMP", os.getenv("VOLCENGINE_TTS_ENABLE_TIMESTAMP", "0")).lower() in {"1", "true", "yes", "on"}
    DOUBAO_TTS_TOKEN_EXPIRATION_SECONDS = int(os.getenv("DOUBAO_TTS_TOKEN_EXPIRATION_SECONDS", os.getenv("VOLCENGINE_TTS_TOKEN_EXPIRATION_SECONDS", "3600")))
    DOUBAO_TTS_TIMEOUT_SECONDS = int(os.getenv("DOUBAO_TTS_TIMEOUT_SECONDS", os.getenv("VOLCENGINE_TTS_TIMEOUT_SECONDS", "60")))
    MENTAL_SUPPORT_SYSTEM_PROMPT = os.getenv(
        "MENTAL_SUPPORT_SYSTEM_PROMPT",
        (
            "你是“心陪陪”，一个面向青年心理陪伴场景的温和、耐心、克制的对话助手。"
            "请优先理解和承接用户情绪，避免诊断式表达，避免过度说教，"
            "给出贴近当下、可执行的小建议。"
        ),
    )


class DevelopmentConfig(BaseConfig):
    DEBUG = True


class ProductionConfig(BaseConfig):
    DEBUG = False


CONFIG_MAP = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    None: DevelopmentConfig,
}


def get_config(name: str | None):
    return CONFIG_MAP.get(name, DevelopmentConfig)

