# ============================================================
# Unified Teaching Pipeline
# Single entry point for all owner-driven knowledge ingestion:
# WhatsApp commands, web chat, file upload, audio transcript,
# web-link scrape, image OCR, manual text
# ============================================================
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional

logger = logging.getLogger("fazle-brain.teaching")

DATABASE_URL = os.getenv(
    "FAZLE_DATABASE_URL",
    "postgresql://postgres:postgres@postgres:5432/postgres",
)
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/1")


class TeachingSource(str, Enum):
    WHATSAPP_CHAT = "whatsapp_chat"
    WEB_CHAT = "web_chat"
    FILE_UPLOAD = "file_upload"
    AUDIO_TRANSCRIPT = "audio_transcript"
    IMAGE_OCR = "image_ocr"
    WEB_SCRAPE = "web_scrape"
    MANUAL_TEXT = "manual_text"
    OWNER_CORRECTION = "owner_correction"
    OWNER_FEEDBACK = "owner_feedback"


class ApprovalStatus(str, Enum):
    AUTO_APPROVED = "auto_approved"  # Owner-sourced, high confidence
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    REJECTED = "rejected"


@dataclass
class TeachingInput:
    content: str
    source: TeachingSource
    category: str = "general"  # business, personal, pricing, employee_rules, etc.
    key: str = ""  # Optional key for knowledge base
    language: str = "bn"
    confidence: float = 1.0
    metadata: dict = field(default_factory=dict)
    # Context for corrections
    original_query: str = ""
    original_reply: str = ""


@dataclass
class TeachingResult:
    success: bool
    knowledge_id: Optional[str] = None
    approval_status: ApprovalStatus = ApprovalStatus.AUTO_APPROVED
    message: str = ""
    error: str = ""


class UnifiedTeachingPipeline:
    """Single entry point for all knowledge ingestion into Fazle.

    All teaching inputs go through:
    1. Validation + sanitization
    2. Source classification (determines auto-approve vs review needed)
    3. Category detection (if not provided)
    4. Knowledge lifecycle storage (create/replace)
    5. Vector memory storage (Qdrant)
    6. Audit trail
    """

    def __init__(self, dsn: str = None, redis_url: str = None):
        self._dsn = dsn or DATABASE_URL
        self._redis_url = redis_url or REDIS_URL
        self._knowledge_engine = None
        self._redis = None

    def _get_knowledge_engine(self):
        if self._knowledge_engine is None:
            from owner_control.knowledge_lifecycle import KnowledgeLifecycleEngine
            self._knowledge_engine = KnowledgeLifecycleEngine(self._dsn)
        return self._knowledge_engine

    def _get_redis(self):
        if self._redis is None:
            try:
                import redis as redis_lib
                self._redis = redis_lib.Redis.from_url(self._redis_url, decode_responses=True)
            except Exception:
                pass
        return self._redis

    def teach(self, inp: TeachingInput) -> TeachingResult:
        """Process a teaching input through the unified pipeline."""
        # 1. Validate
        if not inp.content or not inp.content.strip():
            return TeachingResult(success=False, error="Empty content")

        content = inp.content.strip()
        if len(content) > 10000:
            content = content[:10000]

        # 2. Determine approval status
        approval = self._determine_approval(inp)

        # 3. Auto-detect category if not provided
        if not inp.category or inp.category == "general":
            inp.category = self._detect_category(content)

        # 4. Generate key if not provided
        if not inp.key:
            inp.key = self._generate_key(content, inp.category)

        # 5. Store in knowledge lifecycle
        kg = self._get_knowledge_engine()
        try:
            if inp.source == TeachingSource.OWNER_CORRECTION:
                # Corrections replace existing knowledge
                item = kg.replace(
                    category=inp.category,
                    key=inp.key,
                    new_value=content,
                    reason=f"Owner correction. Original: {inp.original_reply[:200]}",
                    replaced_by="owner",
                    source=inp.source.value,
                    confidence=inp.confidence,
                )
            else:
                item = kg.create(
                    category=inp.category,
                    key=inp.key,
                    value=content,
                    source=inp.source.value,
                    confidence=inp.confidence,
                    language=inp.language,
                    created_by="owner" if self._is_owner_source(inp.source) else "system",
                    metadata=inp.metadata,
                )

            if item:
                # 6. Audit trail via Redis pub
                self._publish_teaching_event(inp, item.id, approval)

                return TeachingResult(
                    success=True,
                    knowledge_id=item.id,
                    approval_status=approval,
                    message=f"Knowledge stored: {inp.category}/{inp.key}",
                )
            return TeachingResult(success=False, error="Knowledge engine storage failed")

        except Exception as e:
            logger.exception("Teaching pipeline failed for %s", inp.source)
            return TeachingResult(success=False, error=str(e))

    def teach_from_whatsapp(
        self, text: str, sender_id: str, is_owner: bool,
        context: str = "",
    ) -> TeachingResult:
        """Convenience: teach from WhatsApp message."""
        return self.teach(TeachingInput(
            content=text,
            source=TeachingSource.WHATSAPP_CHAT if is_owner else TeachingSource.WHATSAPP_CHAT,
            confidence=1.0 if is_owner else 0.5,
            metadata={"sender_id": sender_id, "context": context},
        ))

    def teach_from_correction(
        self, correction_text: str, original_query: str,
        original_reply: str, platform: str = "whatsapp",
    ) -> TeachingResult:
        """Convenience: teach from owner correction of AI reply."""
        return self.teach(TeachingInput(
            content=correction_text,
            source=TeachingSource.OWNER_CORRECTION,
            confidence=1.0,
            original_query=original_query,
            original_reply=original_reply,
            key=f"correction:{original_query[:80]}",
            metadata={"platform": platform},
        ))

    def teach_from_file(
        self, content: str, filename: str,
        file_type: str = "text", category: str = "",
    ) -> TeachingResult:
        """Convenience: teach from uploaded file content."""
        return self.teach(TeachingInput(
            content=content,
            source=TeachingSource.FILE_UPLOAD,
            category=category or self._detect_category(content),
            confidence=0.8,  # Files need review
            metadata={"filename": filename, "file_type": file_type},
        ))

    def teach_from_audio(
        self, transcript: str, confidence: float,
        sender_id: str = "owner",
    ) -> TeachingResult:
        """Convenience: teach from audio transcription."""
        return self.teach(TeachingInput(
            content=transcript,
            source=TeachingSource.AUDIO_TRANSCRIPT,
            confidence=confidence,
            metadata={"sender_id": sender_id},
        ))

    def teach_from_web_scrape(
        self, content: str, url: str,
        category: str = "",
    ) -> TeachingResult:
        """Convenience: teach from web page scrape."""
        return self.teach(TeachingInput(
            content=content,
            source=TeachingSource.WEB_SCRAPE,
            category=category,
            confidence=0.6,  # External content needs careful review
            metadata={"url": url},
        ))

    def teach_from_image(
        self, ocr_text: str, confidence: float,
        caption: str = "",
    ) -> TeachingResult:
        """Convenience: teach from image OCR."""
        return self.teach(TeachingInput(
            content=ocr_text,
            source=TeachingSource.IMAGE_OCR,
            confidence=confidence / 100.0 if confidence > 1 else confidence,
            metadata={"caption": caption},
        ))

    # ── Internal helpers ─────────────────────────────────────

    def _determine_approval(self, inp: TeachingInput) -> ApprovalStatus:
        """Owner sources get auto-approved. External needs review."""
        if self._is_owner_source(inp.source) and inp.confidence >= 0.8:
            return ApprovalStatus.AUTO_APPROVED
        if inp.confidence >= 0.9:
            return ApprovalStatus.AUTO_APPROVED
        return ApprovalStatus.PENDING_REVIEW

    def _is_owner_source(self, source: TeachingSource) -> bool:
        return source in (
            TeachingSource.WHATSAPP_CHAT,
            TeachingSource.WEB_CHAT,
            TeachingSource.MANUAL_TEXT,
            TeachingSource.OWNER_CORRECTION,
            TeachingSource.OWNER_FEEDBACK,
        )

    def _detect_category(self, content: str) -> str:
        """Simple keyword-based category detection."""
        text = content.lower()
        if any(w in text for w in ["salary", "বেতন", "pay", "price", "দাম", "cost", "charge", "rate"]):
            return "pricing"
        if any(w in text for w in ["guard", "security", "সিকিউরিটি", "গার্ড", "scout", "সার্ভে", "vessel"]):
            return "business"
        if any(w in text for w in ["employee", "staff", "কর্মী", "worker", "duty", "shift", "ডিউটি"]):
            return "employee_rules"
        if any(w in text for w in ["hire", "apply", "join", "নিয়োগ", "চাকরি", "job", "vacancy"]):
            return "hiring"
        if any(w in text for w in ["office", "address", "অফিস", "ঠিকানা", "location", "phone", "contact"]):
            return "contact_info"
        if any(w in text for w in ["family", "wife", "daughter", "son", "পরিবার", "বউ", "মেয়ে", "ছেলে"]):
            return "personal"
        return "general"

    def _generate_key(self, content: str, category: str) -> str:
        """Generate a key from content for knowledge base lookup."""
        # Take first meaningful words as key
        words = content.strip().split()[:8]
        key = " ".join(words)
        if len(key) > 100:
            key = key[:100]
        return key

    def _publish_teaching_event(
        self, inp: TeachingInput, knowledge_id: str,
        approval: ApprovalStatus,
    ):
        """Publish teaching event to Redis for dashboard notification."""
        r = self._get_redis()
        if not r:
            return
        try:
            event = json.dumps({
                "type": "knowledge_taught",
                "knowledge_id": knowledge_id,
                "source": inp.source.value,
                "category": inp.category,
                "approval": approval.value,
                "timestamp": datetime.utcnow().isoformat(),
            })
            r.publish("fazle:events:teaching", event)
        except Exception:
            pass
