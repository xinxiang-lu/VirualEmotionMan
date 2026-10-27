from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from importlib import import_module
from pathlib import Path
from typing import Protocol

import numpy as np
from flask import current_app


class RAGContextProvider(Protocol):
    def build_context(self, *, scope: str, **kwargs) -> dict | None: ...


class NoopRAGContextProvider:
    def build_context(self, *, scope: str, **kwargs) -> dict | None:
        return None


@dataclass
class RAGProviderStatus:
    available: bool
    reason: str = ""
    chunk_count: int = 0
    index_dir: str = ""


class FaissRAGContextProvider:
    """Local FAISS-backed RAG provider for the project knowledge JSON."""

    INDEX_FILENAME = "knowledge.faiss"
    CHUNKS_FILENAME = "chunks.json"
    MANIFEST_FILENAME = "manifest.json"

    def __init__(self, config) -> None:
        self.config = config
        self.knowledge_path = Path(config.get("RAG_KNOWLEDGE_PATH", "")).resolve()
        self.index_dir = Path(config.get("RAG_INDEX_DIR", "")).resolve()
        self.embedding_dim = int(config.get("RAG_EMBEDDING_DIM", 512))
        self.chunk_size = int(config.get("RAG_CHUNK_SIZE", 420))
        self.chunk_overlap = int(config.get("RAG_CHUNK_OVERLAP", 80))
        self.top_k = int(config.get("RAG_TOP_K", 5))
        self.min_score = float(config.get("RAG_MIN_SCORE", 0.08))
        self._faiss = None
        self._index = None
        self._chunks: list[dict] = []
        self._status = RAGProviderStatus(available=False, index_dir=str(self.index_dir))

    @property
    def status(self) -> RAGProviderStatus:
        return self._status

    def initialize(self) -> bool:
        try:
            self._faiss = import_module("faiss")
        except Exception as error:
            self._status = RAGProviderStatus(
                available=False,
                reason=f"{type(error).__name__}: {error}",
                index_dir=str(self.index_dir),
            )
            return False

        try:
            if self._should_rebuild():
                self._build_index()
            else:
                self._load_index()
        except Exception as error:
            self._status = RAGProviderStatus(
                available=False,
                reason=f"{type(error).__name__}: {error}",
                index_dir=str(self.index_dir),
            )
            return False

        self._status = RAGProviderStatus(
            available=True,
            chunk_count=len(self._chunks),
            index_dir=str(self.index_dir),
        )
        return True

    def build_context(self, *, scope: str, **kwargs) -> dict | None:
        if not self._status.available:
            return None

        query = self._build_query(scope=scope, **kwargs)
        if not query:
            return None

        hits = self.search(query, scope=scope, top_k=self.top_k)
        if not hits:
            return None

        return {
            "provider": "local_faiss",
            "scope": scope,
            "query": query,
            "hits": hits,
        }

    def search(self, query: str, *, scope: str = "all", top_k: int | None = None) -> list[dict]:
        if self._index is None or not self._chunks:
            return []

        query_vector = self._embed_text(query).reshape(1, -1)
        requested_top_k = top_k or self.top_k
        search_k = min(max(requested_top_k * 10, 50), len(self._chunks))
        scores, indices = self._index.search(query_vector, search_k)

        candidates = []
        for score, index in zip(scores[0], indices[0]):
            if index < 0 or index >= len(self._chunks):
                continue
            chunk = self._chunks[index]
            if not self._scope_matches(chunk.get("scope"), scope):
                continue
            score = float(score)
            lexical_score = self._lexical_score(query, chunk)
            combined_score = score + (0.35 * lexical_score)
            if combined_score < self.min_score:
                continue
            candidates.append(
                {
                    "id": chunk["chunk_id"],
                    "record_id": chunk["record_id"],
                    "title": chunk["title"],
                    "source": chunk["source"],
                    "category": chunk["category"],
                    "record_type": chunk["record_type"],
                    "scope": chunk["scope"],
                    "tags": chunk["tags"],
                    "score": round(combined_score, 4),
                    "vector_score": round(score, 4),
                    "content": chunk["content"],
                }
            )
        candidates.sort(key=lambda item: item["score"], reverse=True)
        return candidates[:requested_top_k]

    def _should_rebuild(self) -> bool:
        index_path = self._index_path()
        chunks_path = self._chunks_path()
        manifest_path = self._manifest_path()
        if not index_path.exists() or not chunks_path.exists() or not manifest_path.exists():
            return self.knowledge_path.exists()

        if not self.knowledge_path.exists():
            return False

        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            return True

        source_mtime = self.knowledge_path.stat().st_mtime
        return float(manifest.get("source_mtime") or 0) < source_mtime

    def _build_index(self) -> None:
        if not self.knowledge_path.exists():
            raise FileNotFoundError(f"RAG knowledge file not found: {self.knowledge_path}")

        payload = json.loads(self.knowledge_path.read_text(encoding="utf-8"))
        records = payload.get("records") if isinstance(payload, dict) else None
        if not isinstance(records, list):
            raise ValueError("RAG knowledge file must contain a records list")

        chunks = self._records_to_chunks(records)
        if not chunks:
            raise ValueError("RAG knowledge file has no usable chunks")

        vectors = np.vstack([self._embed_text(chunk["embedding_text"]) for chunk in chunks]).astype("float32")
        index = self._faiss.IndexFlatIP(self.embedding_dim)
        index.add(vectors)

        self.index_dir.mkdir(parents=True, exist_ok=True)
        self._faiss.write_index(index, str(self._index_path()))
        self._chunks_path().write_text(json.dumps(chunks, ensure_ascii=False, indent=2), encoding="utf-8")
        self._manifest_path().write_text(
            json.dumps(
                {
                    "source_path": str(self.knowledge_path),
                    "source_mtime": self.knowledge_path.stat().st_mtime,
                    "chunk_count": len(chunks),
                    "embedding": "local_hashing_char_ngrams",
                    "embedding_dim": self.embedding_dim,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        self._index = index
        self._chunks = chunks

    def _load_index(self) -> None:
        if not self._index_path().exists() or not self._chunks_path().exists():
            raise FileNotFoundError("RAG index files are missing")

        self._index = self._faiss.read_index(str(self._index_path()))
        self._chunks = json.loads(self._chunks_path().read_text(encoding="utf-8"))
        if not self._chunks:
            raise ValueError("RAG chunks metadata is empty")

    def _records_to_chunks(self, records: list[dict]) -> list[dict]:
        chunks = []
        for record in records:
            record_id = str(record.get("id") or "").strip()
            content = self._clean_text(record.get("content"))
            if not record_id or not content:
                continue

            title = self._clean_text(record.get("title"))
            category = self._clean_text(record.get("category"))
            source = self._clean_text(record.get("source"))
            scope = self._clean_text(record.get("scope")) or "all"
            record_type = self._clean_text(record.get("record_type")) or "knowledge"
            tags = [self._clean_text(item) for item in (record.get("tags") or []) if self._clean_text(item)]

            for chunk_index, chunk_text in enumerate(self._split_text(content)):
                chunk_id = f"{record_id}#chunk-{chunk_index}"
                embedding_text = "\n".join(
                    [
                        f"标题：{title}",
                        f"分类：{category}",
                        f"标签：{' '.join(tags)}",
                        f"来源：{source}",
                        chunk_text,
                    ]
                )
                chunks.append(
                    {
                        "chunk_id": chunk_id,
                        "record_id": record_id,
                        "scope": scope,
                        "category": category,
                        "record_type": record_type,
                        "title": title,
                        "source": source,
                        "tags": tags,
                        "content": chunk_text,
                        "embedding_text": embedding_text,
                    }
                )
        return chunks

    def _split_text(self, text: str) -> list[str]:
        text = self._clean_text(text)
        if len(text) <= self.chunk_size:
            return [text]

        chunks = []
        start = 0
        overlap = max(0, min(self.chunk_overlap, self.chunk_size // 2))
        while start < len(text):
            end = min(len(text), start + self.chunk_size)
            candidate = text[start:end]
            if end < len(text):
                punctuation_cut = max(candidate.rfind("。"), candidate.rfind("；"), candidate.rfind("！"), candidate.rfind("？"))
                if punctuation_cut >= int(self.chunk_size * 0.55):
                    end = start + punctuation_cut + 1
                    candidate = text[start:end]
            chunks.append(candidate.strip())
            if end >= len(text):
                break
            start = max(end - overlap, start + 1)
        return [item for item in chunks if item]

    def _embed_text(self, text: str) -> np.ndarray:
        vector = np.zeros(self.embedding_dim, dtype="float32")
        features = self._features(text)
        if not features:
            return vector

        for feature in features:
            digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
            bucket = int.from_bytes(digest, "little") % self.embedding_dim
            vector[bucket] += 1.0

        norm = float(np.linalg.norm(vector))
        if norm > 0:
            vector /= norm
        return vector

    def _features(self, text: str) -> list[str]:
        normalized = self._clean_text(text).lower()
        if not normalized:
            return []

        compact = re.sub(r"\s+", "", normalized)
        features: list[str] = []
        features.extend(re.findall(r"[a-z0-9]+", normalized))
        features.extend(re.findall(r"[\u4e00-\u9fff]", normalized))
        for size in (2, 3, 4):
            if len(compact) >= size:
                features.extend(compact[index : index + size] for index in range(len(compact) - size + 1))
        return features

    def _lexical_score(self, query: str, chunk: dict) -> float:
        query_terms = [term for term in re.split(r"\s+", self._clean_text(query)) if term]
        if not query_terms:
            return 0.0

        title = chunk.get("title") or ""
        tags = " ".join(chunk.get("tags") or [])
        candidate_text = " ".join(
            [
                title,
                tags,
                chunk.get("category") or "",
                chunk.get("content") or "",
            ]
        )

        matched = sum(1 for term in query_terms if term in candidate_text)
        score = matched / len(query_terms)
        if query_terms and all(term in f"{title} {tags}" for term in query_terms):
            score += 0.5
        return min(score, 1.0)

    def _build_query(self, *, scope: str, **kwargs) -> str:
        context = kwargs.get("context") or {}
        parts = [scope]

        user = kwargs.get("user")
        if user is not None:
            profile = getattr(user, "profile", None)
            if profile is not None:
                parts.extend(
                    [
                        getattr(profile, "nickname", "") or "",
                        getattr(profile, "gender", "") or "",
                        str(getattr(profile, "age", "") or ""),
                        getattr(profile, "occupation", "") or "",
                    ]
                )
            try:
                parts.extend([relation.tag.description or relation.tag.name for relation in user.profile_goals])
            except Exception:
                pass

        user_profile = context.get("user_profile") or {}
        if isinstance(user_profile, dict):
            parts.extend(
                [
                    user_profile.get("nickname") or "",
                    user_profile.get("gender") or "",
                    str(user_profile.get("age") or ""),
                    user_profile.get("occupation") or "",
                    " ".join(user_profile.get("use_purpose") or []),
                ]
            )

        parts.extend(self._dialogue_texts(context.get("recent_dialogue") or context.get("recent_dialogue_records") or []))
        parts.extend(self._assessment_texts(context.get("previous_assessment")))
        parts.extend(self._assessment_texts(context.get("historical_psych_state_logs") or []))
        parts.extend(self._strategy_texts(context.get("historical_strategies_logs") or []))
        parts.extend(self._multimodal_texts(context.get("multimodal_features") or []))

        conversation = kwargs.get("conversation")
        if conversation is not None:
            parts.extend([getattr(conversation, "title", "") or "", getattr(conversation, "summary", "") or ""])

        expanded_keywords = self._expand_psychology_keywords(" ".join(str(item) for item in parts if item))
        parts.extend(expanded_keywords)

        query = self._clean_text(" ".join(str(item) for item in parts if item))
        return query[:2500]

    def _expand_psychology_keywords(self, text: str) -> list[str]:
        expansions = []
        rules = [
            (["室友", "同学", "朋友", "关系", "孤独", "开口", "社交", "人际"], "人际关系 人际交往 孤独 社交支持 同伴关系"),
            (["睡不着", "失眠", "睡眠", "熬夜", "休息"], "睡眠 压力 放松 睡前减压"),
            (["压力", "任务", "作业", "实习", "毕业", "考试", "课程"], "压力管理 任务拆分 学业压力 适应"),
            (["焦虑", "担心", "紧张", "不安", "害怕"], "焦虑情绪 缓解方法 情绪调节"),
            (["低落", "无力", "很累", "撑不住", "耗竭"], "情绪低落 心理支持 求助 保护因素"),
            (["恋爱", "爱情", "分手", "喜欢"], "恋爱 爱情 亲密关系"),
            (["自伤", "自杀", "活不下去", "结束生命"], "危机干预 高风险 求助 人工介入"),
        ]
        for keywords, expansion in rules:
            if any(keyword in text for keyword in keywords):
                expansions.append(expansion)
        return expansions

    def _dialogue_texts(self, rows) -> list[str]:
        if not isinstance(rows, list):
            return []

        texts = []
        for item in rows[-8:]:
            if not isinstance(item, dict):
                continue
            role = item.get("role") or ""
            content = item.get("content") or ""
            if role in {"user", "admin"} or content:
                texts.append(content)
        return texts

    def _assessment_texts(self, value) -> list[str]:
        rows = value if isinstance(value, list) else [value]
        texts = []
        for item in rows:
            if not isinstance(item, dict):
                continue
            texts.extend(
                [
                    item.get("risk_level") or "",
                    item.get("mood_summary") or "",
                    item.get("trend") or "",
                    item.get("risk_reason") or "",
                    item.get("core_psychological_issue") or "",
                    item.get("advice") or "",
                    " ".join(item.get("tags") or []),
                ]
            )
        return texts

    def _strategy_texts(self, rows) -> list[str]:
        if not isinstance(rows, list):
            return []

        texts = []
        for item in rows[-6:]:
            if not isinstance(item, dict):
                continue
            texts.extend(
                [
                    item.get("type") or "",
                    item.get("content") or "",
                    item.get("note") or "",
                    " ".join(item.get("sample_messages") or []),
                ]
            )
        return texts

    def _multimodal_texts(self, rows) -> list[str]:
        if not isinstance(rows, list):
            return []

        texts = []
        for item in rows[-5:]:
            if not isinstance(item, dict):
                continue
            texts.extend(
                [
                    item.get("transcript_text") or "",
                    " ".join(item.get("event_tags") or []),
                    json.dumps(item.get("overall_summary") or {}, ensure_ascii=False),
                ]
            )
        return texts

    def _scope_matches(self, chunk_scope, requested_scope: str) -> bool:
        if not chunk_scope or chunk_scope == "all":
            return True
        if isinstance(chunk_scope, list):
            return "all" in chunk_scope or requested_scope in chunk_scope
        return str(chunk_scope) == requested_scope

    def _index_path(self) -> Path:
        return self.index_dir / self.INDEX_FILENAME

    def _chunks_path(self) -> Path:
        return self.index_dir / self.CHUNKS_FILENAME

    def _manifest_path(self) -> Path:
        return self.index_dir / self.MANIFEST_FILENAME

    @staticmethod
    def _clean_text(value) -> str:
        if value is None:
            return ""
        return " ".join(str(value).strip().split())


def resolve_rag_context(scope: str, **kwargs) -> dict | None:
    provider = current_app.extensions.get("rag_context_provider")
    if provider is None:
        return None

    try:
        result = provider.build_context(scope=scope, **kwargs)
    except Exception as error:  # pragma: no cover - reserved for future integrations
        current_app.logger.warning("RAG context provider failed for scope %s: %s", scope, error)
        return None

    return result or None
