"""
RAG Chatbot for Customer Service
=================================
روبوت محادثة ذكي يعتمد على RAG (Retrieval-Augmented Generation)
للرد التلقائي على الأسئلة الشائعة قبل التحويل للوكيل البشري

Architecture:
    1. Knowledge Base  : قاعدة معرفة عربية منظمة بالأسئلة والأجوبة
    2. Retriever       : TF-IDF + Cosine Similarity (بدون مكتبات ثقيلة)
    3. Confidence Gate : عتبة ثقة — أقل من العتبة = تحويل للوكيل
    4. LLM Generator   : GLM-5 Turbo لتوليد إجابات طبيعية (اختياري)
    5. Fallback        : رد افتراضي عند عدم العثور على إجابة مناسبة

No heavy dependencies:
    - Uses only Python stdlib + requests
    - TF-IDF computed from scratch (no scikit-learn needed)
    - Arabic text normalization built-in
"""

import json
import math
import os
import re
import logging
import unicodedata
from collections import Counter
from typing import List, Dict, Optional, Tuple, Any

import requests

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# Arabic Text Processing
# ──────────────────────────────────────────────

class ArabicNormalizer:
    """معالج نصوص عربية — توحيد الأشكال المختلفة للحرف نفسه"""

    # خريطة التطبيع
    NORMALIZE_MAP = {
        "\u0622": "\u0627",  # آ → ا
        "\u0623": "\u0627",  # أ → ا
        "\u0625": "\u0627",  # إ → ا
        "\u0624": "\u0648",  # ؤ → و
        "\u0626": "\u064a",  # ئ → ي
        "\u0649": "\u064a",  # ى → ي
    }

    # أحرف التشكيل (Tashkeel) — تُزال لأنها لا تؤثر على المعنى
    TASHKEEL = set(range(0x0617, 0x061A + 1)) | {
        0x064B, 0x064C, 0x064D, 0x064E, 0x064F, 0x0650, 0x0651, 0x0652,
        0x0670,  # شدة + كسرة + سكون
    }

    @classmethod
    def normalize(cls, text: str) -> str:
        """توحيد النص العربي — إزالة التشكيل وتوحيد الألف والياء"""
        # إزالة التشكيل
        text = "".join(
            c for c in text
            if ord(c) not in cls.TASHKEEL
        )
        # توحيد الأحرف
        for old, new in cls.NORMALIZE_MAP.items():
            text = text.replace(old, new)
        # إزالة التكرار
        text = re.sub(r"(.)\1{2,}", r"\1", text)
        # توحيد المسافات
        text = re.sub(r"\s+", " ", text).strip()
        return text

    @classmethod
    def tokenize(cls, text: str) -> List[str]:
        """تقسيم النص إلى كلمات"""
        text = cls.normalize(text)
        # إزالة علامات الترقيم
        text = re.sub(r"[^\w\s\u0600-\u06FF]", " ", text)
        # تقسيم على المسافات
        tokens = text.split()
        # تصفية الكلمات القصيرة جداً
        tokens = [t for t in tokens if len(t) >= 2]
        return tokens


# ──────────────────────────────────────────────
# TF-IDF Retriever
# ──────────────────────────────────────────────

class TFIDFRetriever:
    """
    محرك بحث TF-IDF خفيف — لا يحتاج scikit-learn

    يحسب تشابه جيب التمام (Cosine Similarity) بين
    استعلام المستخدم وكل سؤال في قاعدة المعرفة.
    """

    def __init__(self, documents: List[Dict[str, str]]):
        """
        Args:
            documents: قائمة بالوثائق [{"id": "...", "question": "...", "answer": "..."}]
        """
        self.documents = documents
        self.normalizer = ArabicNormalizer()
        self.vocab: Dict[str, int] = {}
        self.idf: Dict[str, float] = {}
        self.doc_vectors: List[Dict[str, float]] = []

        self._build_index()

    def _build_index(self) -> None:
        """بناء فهرس TF-IDF لجميع الوثائق"""
        all_tokens: List[List[str]] = []

        # Tokenize all documents
        for doc in self.documents:
            tokens = self.normalizer.tokenize(doc.get("question", ""))
            all_tokens.append(tokens)

        # Build vocabulary
        doc_freq: Counter = Counter()
        for tokens in all_tokens:
            unique_tokens = set(tokens)
            for token in unique_tokens:
                doc_freq[token] += 1
                if token not in self.vocab:
                    self.vocab[token] = len(self.vocab)

        # Compute IDF (Inverse Document Frequency)
        n_docs = len(self.documents)
        for token, df in doc_freq.items():
            self.idf[token] = math.log((n_docs + 1) / (df + 1)) + 1

        # Compute TF-IDF vectors for each document
        for tokens in all_tokens:
            tf: Counter = Counter(tokens)
            max_tf = max(tf.values()) if tf else 1
            vector: Dict[str, float] = {}
            for token, count in tf.items():
                tf_normalized = 0.5 + 0.5 * (count / max_tf)
                vector[token] = tf_normalized * self.idf.get(token, 0)
            self.doc_vectors.append(vector)

    def search(
        self, query: str, top_k: int = 3, min_score: float = 0.0
    ) -> List[Tuple[int, float]]:
        """
        البحث عن أكثر الوثائق تشابهاً مع الاستعلام

        Args:
            query: نص الاستعلام
            top_k: عدد النتائج الأعلى
            min_score: الحد الأدنى لدرجة التشابه (0-1)

        Returns:
            قائمة (index, score) مرتبة تنازلياً
        """
        # Compute query TF-IDF vector
        tokens = self.normalizer.tokenize(query)
        tf: Counter = Counter(tokens)
        max_tf = max(tf.values()) if tf else 1

        query_vector: Dict[str, float] = {}
        for token, count in tf.items():
            tf_normalized = 0.5 + 0.5 * (count / max_tf)
            query_vector[token] = tf_normalized * self.idf.get(token, 0)

        if not query_vector:
            return []

        # Compute cosine similarity with each document
        scores: List[Tuple[int, float]] = []
        query_norm = math.sqrt(sum(v * v for v in query_vector.values()))

        for i, doc_vector in enumerate(self.doc_vectors):
            # Dot product
            dot_product = sum(
                query_vector.get(token, 0) * doc_vector.get(token, 0)
                for token in query_vector
                if token in doc_vector
            )
            doc_norm = math.sqrt(sum(v * v for v in doc_vector.values()))

            if query_norm > 0 and doc_norm > 0:
                similarity = dot_product / (query_norm * doc_norm)
            else:
                similarity = 0.0

            if similarity >= min_score:
                scores.append((i, similarity))

        # Sort by score descending
        scores.sort(key=lambda x: x[1], reverse=True)
        return scores[:top_k]


# ──────────────────────────────────────────────
# Knowledge Base
# ──────────────────────────────────────────────

# قاعدة المعرفة العربية — الأسئلة الشائعة لمنصة Smart Land Copilot
FAQ_KNOWLEDGE_BASE: List[Dict[str, str]] = [
    # ── عام ──
    {
        "id": "faq_001",
        "category": "عام",
        "question": "ما هي منصة Smart Land Copilot؟",
        "answer": "Smart Land Copilot هي منصة ذكية لإدارة الأراضي والعقارات في مصر. تساعد المستثمرين في البحث عن الأراضي وتحليل جدوى الاستثمار ومطابقة الأراضي المناسبة بناءً على معايير محددة مثل النشاط الاستثماري والمساحة والميزانية والموقع. المنصة تستخدم الذكاء الاصطناعي لتقديم تقارير استشارية وتوصيات مخصصة.",
    },
    {
        "id": "faq_002",
        "category": "عام",
        "question": "كيف أبدأ استخدام المنصة؟",
        "answer": "يمكنك البدء بإنشاء حساب مجاني عبر صفحة التسجيل. بعد ذلك، يمكنك إعداد معايير الاستثمار الخاصة بك (النشاط، الميزانية، المحافظة المفضلة) وسيعرض لك النظام الأراضي المتوافقة تلقائياً. يمكنك أيضاً تصفح الخريطة التفاعلية أو التحدث مع المساعد الذكي للحصول على توصيات مخصصة.",
    },
    {
        "id": "faq_003",
        "category": "عام",
        "question": "هل المنصة مجانية؟",
        "answer": "المنصة تقدم خططاً متعددة: خطة مجانية تتيح البحث الأساسي وعرض 5 نتائج مطابقة يومياً، وخطة احترافية تشمل تقارير الجدوى الكاملة والتحليلات المتقدمة، وخطة مؤسسية للشركات بميزات إضافية مثل API والاشتراكات المخصصة. يمكنك البدء مجاناً والترقية في أي وقت.",
    },
    # ── الأسعار والدفع ──
    {
        "id": "faq_004",
        "category": "أسعار ودفع",
        "question": "ما هي طرق الدفع المتاحة؟",
        "answer": "نحن نقبل الدفع عبر عدة قنوات: فوري (Fawry) للدفع عبر المحفظة أو فروع فوري، بطاقات الائتمان (Visa/Mastercard) عبر Stripe، وبالتحويل البنكي المباشر. جميع المعاملات مؤمنة بتشفير SSL 256-bit. يمكنك أيضاً الدفع على أقساط لبعض الخطط.",
    },
    {
        "id": "faq_005",
        "category": "أسعار ودفع",
        "question": "كيف أحصل على استرداد المبلغ؟",
        "answer": "يمكنك طلب استرداد المبلغ خلال 14 يوماً من الشراء إذا لم تكن راضياً عن الخدمة. يتم معالجة الاسترداد خلال 5-7 أيام عمل. لفتح طلب استرداد، اذهب إلى إعدادات الحساب > الاشتراك > طلب استرداد، أو تواصل مع فريق الدعم عبر الواتساب.",
    },
    {
        "id": "faq_006",
        "category": "أسعار ودفع",
        "question": "هل يمكنني الدفع بالتقسيط؟",
        "answer": "نعم، نقدم خيار التقسيط على 3 أو 6 أشهر للخطط الاحترافية والمؤسسية. يتم ذلك بالتعاون مع فوري إنستالمنت. لا توجد رسوم إضافية على التقسيط. يمكنك اختيار خيار التقسيط عند الدفع.",
    },
    # ── الأراضي والبحث ──
    {
        "id": "faq_007",
        "category": "أراضي وبحث",
        "question": "كيف يتم تصنيف جودة الأراضي؟",
        "answer": "يتم تصنيف الأراضي بناءً على نظام تقييم مرجح يشمل ثلاثة معايير رئيسية: البنية التحتية والمرافق (40%) مثل توفر الكهرباء والمياه والصرف الصحي، القرب من الطرق السريعة (30%) مثل القرب من الطرق الإقليمية والقومية، والقرب من الموانئ (30%) مثل الموانئ البحرية والجافة. بناءً على الدرجة الإجمالية، تُصنف الأراضي إلى: AAA (ممتازة)، AA (جيدة جداً)، A (جيدة)، أو B (مقبولة).",
    },
    {
        "id": "faq_008",
        "category": "أراضي وبحث",
        "question": "ما هي المحافظات المتاحة في المنصة؟",
        "answer": "تغطي المنصة حالياً 13 محافظة مصرية تشمل: القاهرة، الجيزة، الإسكندرية، 6 أكتوبر، العاصمة الإدارية الجديدة، السويس، الإسماعيلية، بورسعيد، دمياط، الدقهلية، المنوفية، الغربية، وكفر الشيخ. نعمل باستمرار على إضافة محافظات جديدة.",
    },
    {
        "id": "faq_009",
        "category": "أراضي وبحث",
        "question": "كيف يعمل نظام المطابقة الذكية؟",
        "answer": "نظام المطابقة الذكية يحلل معايير الاستثمار الخاصة بك عبر 7 أبعاد مرجحة: النشاط الاستثماري (25%)، المساحة المناسبة (20%)، السعر والميزانية (20%)، توفر المرافق (15%)، جودة الأرض (10%)، حالة المزاد (5%)، والمحافظة المفضلة (5%). يتم حساب نسبة التوافق من 0 إلى 100% وتقديم النتائج مرتبة من الأعلى.",
    },
    {
        "id": "faq_010",
        "category": "أراضي وبحث",
        "question": "هل يمكنني البحث عن أراضي في مزاد؟",
        "answer": "نعم، يمكنك فلترة النتائج لعرض الأراضي المتاحة في المزادات فقط. توجد علامة مميزة على أراضي المزاد في الخريطة التفاعلية ونتائج البحث. كما نوفر إشعارات فورية عند إضافة أراضي جديدة للمزاد تطابق معاييرك.",
    },
    # ── التقارير والتحليل ──
    {
        "id": "faq_011",
        "category": "تقارير",
        "question": "ما هو تقرير الجدوى الاستشاري؟",
        "answer": "تقرير الجدوى الاستشاري هو تقرير مؤسسي مفصل يُنشئه المساعد الذكي (GLM-5 Turbo) بناءً على بيانات الأرض المحددة. يتضمن تحليل الموقع والبنية التحتية، تقدير تكلفة التطوير، تحليل العائد على الاستثمار، المخاطر المحتملة وتوصيات التخفيف، مقارنة مع مناطق مماثلة، وتوصية استثمارية شاملة. التقرير متاح بالعربية.",
    },
    {
        "id": "faq_012",
        "category": "تقارير",
        "question": "هل يمكنني تصدير البيانات؟",
        "answer": "نعم، يمكنك تصدير نتائج البحث والتقارير بصيغ متعددة: PDF للتقارير الاستشارية، Excel لبيانات الأراضي والتحليلات، و CSV للبيانات الخام. كما نوفر API للشركات المؤسسية لاستخراج البيانات برمجياً.",
    },
    # ── الحساب والأمان ──
    {
        "id": "faq_013",
        "category": "حساب وأمان",
        "question": "كيف أغيّر كلمة المرور؟",
        "answer": "يمكنك تغيير كلمة المرور من خلال: إعدادات الحساب > الأمان > تغيير كلمة المرور. ستحتاج لإدخال كلمة المرور الحالية ثم كلمة المرور الجديدة مرتين. ننصح باستخدام كلمة مرور قوية تحتوي على أحرف وأرقام ورموز ولا تقل عن 8 أحرف.",
    },
    {
        "id": "faq_014",
        "category": "حساب وأمان",
        "question": "هل بياناتي محمية؟",
        "answer": "نعم، نأخذ أمان بياناتك بجدية تامة. نستخدم تشفير SSL 256-bit لجميع الاتصالات، وتشفير AES-256 لبيانات الحسابات المخزنة. لا نشارك بياناتك مع أطراف ثالثة. نلتزم بسياسة خصوصية صارمة وفقاً للقوانين المصرية. كما نوفر المصادقة الثنائية (2FA) لحماية إضافية.",
    },
    {
        "id": "faq_015",
        "category": "حساب وأمان",
        "question": "نسيت كلمة المرور، ماذا أفعل؟",
        "answer": "اذهب إلى صفحة تسجيل الدخول واضغط على 'نسيت كلمة المرور؟'. أدخل بريدك الإلكتروني المسجل وسيتم إرسال رابط إعادة تعيين كلمة المرور خلال دقائق. الرابط صالح لمدة ساعة واحدة. إذا لم تستلم الرسالة، تحقق من مجلد الرسائل غير المرغوبة.",
    },
    # ── المزادات ──
    {
        "id": "faq_016",
        "category": "مزادات",
        "question": "كيف أشترك في المزاد؟",
        "answer": "للمشاركة في المزاد: 1) سجّل دخولك، 2) اختر الأرض المتاحة في المزاد، 3) راجع تفاصيل الأرض وتقرير الجدوى، 4) اضغط 'تقديم عرض'، 5) أدخل مبلغ العرض الخاص بك، 6) أكمل عملية التأكيد. ستتلقى إشعاراً بقبول عرضك أو إذا تم تجاوزه من خلال الواتساب والبريد الإلكتروني.",
    },
    {
        "id": "faq_017",
        "category": "مزادات",
        "question": "ما هي رسوم المزاد؟",
        "answer": "رسوم المزاد تشمل: تأمين المشاركة (5% من الحد الأدنى للمزاد، يُرد بعد انتهاء المزاد إذا لم تفز)، وعمولة المنصة (2% من قيمة الصفقة النهائية في حال الفوز). لا توجد رسوم إضافية مخفية.",
    },
    # ── الدعم الفني ──
    {
        "id": "faq_018",
        "category": "دعم فني",
        "question": "كيف أتواصل مع فريق الدعم؟",
        "answer": "يمكنك التواصل معنا عبر عدة قنوات: واتساب (متاح من السبت إلى الخميس، 9 صباحاً - 9 مساءً)، البريد الإلكتروني support@smartland.eg، أو من خلال نموذج الاتصال داخل المنصة. كما يمكنك فتح تذكرة دعم فني مباشرة من خلال المنصة وسيتم الرد خلال 24 ساعة.",
    },
    {
        "id": "faq_019",
        "category": "دعم فني",
        "question": "المنصة لا تعمل بشكل صحيح، ماذا أفعل؟",
        "answer": "إذا واجهت مشكلة تقنية: 1) جرب تحديث الصفحة (Ctrl+F5)، 2) امسح ذاكرة المتصفح وملفات تعريف الارتباط، 3) تأكد من استخدام متصفح حديث (Chrome/Firefox/Safari)، 4) جرب من متصفح آخر أو جهاز آخر، 5) إذا استمرت المشكلة، تواصل مع الدعم الفني مع وصف المشكلة ولقطة شاشة.",
    },
    {
        "id": "faq_020",
        "category": "دعم فني",
        "question": "كم يستغرق الرد على استفساري؟",
        "answer": "وقت الاستجابة يعتمد على نوع الاستفسار: الأسئلة العامة تُجاب خلال 1-2 ساعة عمل، المشاكل التقنية خلال 4 ساعات عمل، الاستفسارات المالية خلال 24 ساعة عمل. في حالات الطوارئ (مثل مشاكل المزاد) نقدم دعماً على مدار الساعة خلال فترة المزاد.",
    },
]


# ──────────────────────────────────────────────
# RAG Chatbot
# ──────────────────────────────────────────────

class ChatbotResponse:
    """نموذج إجابة الشات بوت"""

    def __init__(
        self,
        answer: str,
        source_id: str = "",
        source_question: str = "",
        confidence: float = 0.0,
        should_escalate: bool = False,
        category: str = "",
        is_fallback: bool = False,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        self.answer = answer
        self.source_id = source_id
        self.source_question = source_question
        self.confidence = confidence
        self.should_escalate = should_escalate
        self.category = category
        self.is_fallback = is_fallback
        self.metadata = metadata or {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "answer": self.answer,
            "source_id": self.source_id,
            "source_question": self.source_question,
            "confidence": round(self.confidence, 4),
            "should_escalate": self.should_escalate,
            "category": self.category,
            "is_fallback": self.is_fallback,
            "metadata": self.metadata,
        }


class RAGChatbot:
    """
    روبوت محادثة RAG — يرد على الأسئلة الشائعة تلقائياً

    Pipeline:
        1. Input → Arabic Normalization
        2. Query → TF-IDF Vector
        3. Similarity Search → Top-K FAQ matches
        4. Confidence Check:
           - confidence >= 0.45 → Return answer directly
           - 0.20 <= confidence < 0.45 → Send to LLM for rephrase
           - confidence < 0.20 → Escalate to human agent
        5. Output → ChatbotResponse

    Usage:
        chatbot = RAGChatbot()  # Uses built-in FAQ KB
        response = chatbot.answer("كيف أبدأ استخدام المنصة؟")
        print(response.answer)
        print(f"Escalate: {response.should_escalate}")
    """

    # Default settings
    DEFAULT_CONFIDENCE_THRESHOLD = 0.45
    DEFAULT_ESCALATE_THRESHOLD = 0.20
    DEFAULT_TOP_K = 3

    # ردود fallback عربية
    FALLBACK_RESPONSES = {
        "no_match": (
            "عذراً، لم أتمكن من العثور على إجابة مناسبة لسؤالك. "
            "سأحولك إلى أحد وكلاء الدعم لمساعدتك. "
            "يمكنك أيضاً مراجعة قسم الأسئلة الشائعة في المنصة."
        ),
        "low_confidence": (
            "لست متأكداً من الإجابة الدقيقة لسؤالك. "
            "دعني أحولك إلى أحد المتخصصين الذين يمكنهم مساعدتك بشكل أفضل."
        ),
        "greeting": "مرحباً بك! أنا المساعد الذكي لمنصة Smart Land Copilot. كيف يمكنني مساعدتك اليوم؟",
        "thanks": "العفو! سعيد أنني استطعت المساعدة. هل لديك سؤال آخر؟",
        "goodbye": "مع السلامة! نتمنى لك يوماً سعيداً. لا تتردد في العودة إلينا في أي وقت.",
    }

    # كلمات التحية والوداع
    GREETING_WORDS = [
        "مرحبا", "سلام", "اهلا", "أهلاً", "هاي", "صباح الخير",
        "مساء الخير", "حياك", "السلام عليكم",
    ]
    THANKS_WORDS = [
        "شكرا", "شكراً", "مشكور", "جزاك", "يعطيك", "ممتن",
        "شكرا جزيلا", "thank",
    ]
    GOODBYE_WORDS = [
        "مع السلامة", "باي", "وداعا", "الى اللقاء", "إلى اللقاء",
        "في أمان الله", "bye", "goodbye",
    ]

    def __init__(
        self,
        knowledge_base: Optional[List[Dict[str, str]]] = None,
        confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
        escalate_threshold: float = DEFAULT_ESCALATE_THRESHOLD,
        top_k: int = DEFAULT_TOP_K,
        # LLM settings (optional)
        use_llm: bool = False,
        llm_api_key: str = "",
        llm_base_url: str = "",
        llm_model: str = "glm-5-turbo",
    ):
        """
        تهيئة الشات بوت

        Args:
            knowledge_base: قاعدة المعرفة (قائمة أسئلة وأجوبة)
            confidence_threshold: عتبة الثقة للرد المباشر (0-1)
            escalate_threshold: عتبة التحويل للوكيل البشري (0-1)
            top_k: عدد النتائج المُسترجعة
            use_llm: استخدام LLM لتحسين الإجابات
            llm_api_key: مفتاح API للنموذج اللغوي
            llm_base_url: رابط API للنموذج اللغوي
            llm_model: اسم النموذج
        """
        self.knowledge_base = knowledge_base or FAQ_KNOWLEDGE_BASE
        self.confidence_threshold = confidence_threshold
        self.escalate_threshold = escalate_threshold
        self.top_k = top_k
        self.use_llm = use_llm
        self.llm_api_key = llm_api_key or os.getenv("GLM_API_KEY", "")
        self.llm_base_url = llm_base_url or os.getenv("GLM_BASE_URL", "")
        self.llm_model = llm_model or os.getenv("GLM_MODEL", "glm-5-turbo")

        self.normalizer = ArabicNormalizer()

        # Build TF-IDF index
        self.retriever = TFIDFRetriever(self.knowledge_base)

        # Stats
        self._total_queries = 0
        self._auto_answered = 0
        self._escalated = 0

        logger.info(
            f"RAGChatbot initialized | KB size={len(self.knowledge_base)} | "
            f"confidence_threshold={confidence_threshold} | "
            f"use_llm={use_llm}"
        )

    def answer(
        self,
        query: str,
        user_context: Optional[Dict[str, Any]] = None,
    ) -> ChatbotResponse:
        """
        الرد على استعلام المستخدم — الدالة الرئيسية

        Args:
            query: نص سؤال المستخدم
            user_context: سياق إضافي (معرف المستخدم، المحافظة، إلخ)

        Returns:
            ChatbotResponse يحتوي على الإجابة وقرار التحويل
        """
        self._total_queries += 1
        query = query.strip()

        if not query:
            return ChatbotResponse(
                answer=self.FALLBACK_RESPONSES["greeting"],
                confidence=1.0,
                is_fallback=True,
            )

        # Check for special intents (greeting, thanks, goodbye)
        special = self._check_special_intent(query)
        if special:
            return ChatbotResponse(
                answer=self.FALLBACK_RESPONSES[special],
                confidence=1.0,
                is_fallback=True,
                category="intent",
                metadata={"detected_intent": special},
            )

        # TF-IDF retrieval
        results = self.retriever.search(query, top_k=self.top_k)

        if not results:
            self._escalated += 1
            return ChatbotResponse(
                answer=self.FALLBACK_RESPONSES["no_match"],
                confidence=0.0,
                should_escalate=True,
                is_fallback=True,
            )

        best_idx, best_score = results[0]
        best_doc = self.knowledge_base[best_idx]

        # High confidence → answer directly
        if best_score >= self.confidence_threshold:
            self._auto_answered += 1
            answer = best_doc["answer"]

            # Optionally enhance with LLM
            if self.use_llm and self.llm_api_key:
                answer = self._llm_enhance(query, best_doc["answer"], user_context)

            return ChatbotResponse(
                answer=answer,
                source_id=best_doc["id"],
                source_question=best_doc["question"],
                confidence=best_score,
                should_escalate=False,
                category=best_doc.get("category", ""),
                metadata={
                    "retrieved_count": len(results),
                    "all_scores": [(self.knowledge_base[idx]["id"], round(score, 4))
                                   for idx, score in results],
                },
            )

        # Low confidence → escalate
        if best_score < self.escalate_threshold:
            self._escalated += 1
            return ChatbotResponse(
                answer=self.FALLBACK_RESPONSES["low_confidence"],
                confidence=best_score,
                should_escalate=True,
                is_fallback=True,
                category=best_doc.get("category", ""),
                metadata={
                    "best_match_id": best_doc["id"],
                    "best_match_score": round(best_score, 4),
                },
            )

        # Medium confidence → try LLM or return best match with disclaimer
        if self.use_llm and self.llm_api_key:
            self._auto_answered += 1
            enhanced = self._llm_enhance(query, best_doc["answer"], user_context)
            return ChatbotResponse(
                answer=enhanced,
                source_id=best_doc["id"],
                source_question=best_doc["question"],
                confidence=best_score,
                should_escalate=False,
                category=best_doc.get("category", ""),
            )

        # Without LLM, return best match but mark for possible escalation
        self._auto_answered += 1
        return ChatbotResponse(
            answer=best_doc["answer"],
            source_id=best_doc["id"],
            source_question=best_doc["question"],
            confidence=best_score,
            should_escalate=False,
            category=best_doc.get("category", ""),
            metadata={
                "note": "medium_confidence_without_llm",
            },
        )

    def _check_special_intent(self, query: str) -> Optional[str]:
        """فحص النوايا الخاصة (تحية، شكر، وداع)"""
        normalized = self.normalizer.normalize(query)
        for word in self.GREETING_WORDS:
            if word in normalized:
                return "greeting"
        for word in self.THANKS_WORDS:
            if word in normalized:
                return "thanks"
        for word in self.GOODBYE_WORDS:
            if word in normalized:
                return "goodbye"
        return None

    def _llm_enhance(
        self,
        query: str,
        base_answer: str,
        user_context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        تحسين الإجابة باستخدام نموذج لغوي (GLM-5 Turbo)

        يُرسل السؤال والإجابة الأساسية إلى النموذج اللغوي
        لصياغة رد أكثر طبيعية وسياقية.
        """
        try:
            context_str = ""
            if user_context:
                context_str = f"\nسياق المستخدم: {json.dumps(user_context, ensure_ascii=False)}"

            prompt = (
                f"أنت مساعد خدمة عملاء لمنصة Smart Land Copilot المصرية.\n"
                f"السؤال: {query}\n"
                f"الإجابة الأساسية من قاعدة المعرفة: {base_answer}{context_str}\n\n"
                f"أعد صياغة الإجابة بطريقة مهنية ومفصلة بالعربية. "
                f"حافظ على المعلومات الأساسية وأضف تفاصيل مفيدة."
            )

            response = requests.post(
                self.llm_base_url or "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.llm_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.llm_model,
                    "messages": [
                        {"role": "system", "content": "أنت مساعد خدمة عملاء محترف. أجب بالعربية."},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.7,
                    "max_tokens": 500,
                },
                timeout=30,
            )

            if response.status_code == 200:
                data = response.json()
                enhanced = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                if enhanced:
                    return enhanced.strip()

        except Exception as e:
            logger.error(f"LLM enhancement failed: {e}")

        # Fallback to base answer
        return base_answer

    # ──────────────────────────────────────────
    # Knowledge Base Management
    # ──────────────────────────────────────────

    def add_faq(
        self, question: str, answer: str, category: str = "", faq_id: str = ""
    ) -> str:
        """
        إضافة سؤال جديد لقاعدة المعرفة

        Args:
            question: نص السؤال
            answer: نص الإجابة
            category: التصنيف
            faq_id: معرف اختياري

        Returns:
            معرف السؤال المُضاف
        """
        faq_id = faq_id or f"faq_{len(self.knowledge_base) + 1:03d}"
        new_faq = {
            "id": faq_id,
            "category": category,
            "question": question,
            "answer": answer,
        }
        self.knowledge_base.append(new_faq)

        # Rebuild index
        self.retriever = TFIDFRetriever(self.knowledge_base)

        logger.info(f"FAQ added: {faq_id} | question='{question[:50]}'")
        return faq_id

    def remove_faq(self, faq_id: str) -> bool:
        """حذف سؤال من قاعدة المعرفة"""
        original_len = len(self.knowledge_base)
        self.knowledge_base = [f for f in self.knowledge_base if f["id"] != faq_id]

        if len(self.knowledge_base) < original_len:
            self.retriever = TFIDFRetriever(self.knowledge_base)
            logger.info(f"FAQ removed: {faq_id}")
            return True
        return False

    # ──────────────────────────────────────────
    # Analytics
    # ──────────────────────────────────────────

    def get_stats(self) -> Dict[str, Any]:
        """إحصائيات الشات بوت"""
        auto_rate = (self._auto_answered / max(self._total_queries, 1)) * 100
        escalation_rate = (self._escalated / max(self._total_queries, 1)) * 100

        return {
            "total_queries": self._total_queries,
            "auto_answered": self._auto_answered,
            "escalated": self._escalated,
            "auto_resolution_rate": round(auto_rate, 2),
            "escalation_rate": round(escalation_rate, 2),
            "knowledge_base_size": len(self.knowledge_base),
        }

    def search_faq(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """
        بحث يدوي في قاعدة المعرفة (للأغراض الإدارية)

        Args:
            query: نص البحث
            top_k: عدد النتائج

        Returns:
            قائمة بالنتائج مع درجة التشابه
        """
        results = self.retriever.search(query, top_k=top_k)
        return [
            {
                **self.knowledge_base[idx],
                "score": round(score, 4),
            }
            for idx, score in results
        ]