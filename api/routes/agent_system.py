"""
نظام الوكيل الذكي (Agent System) — النسخة v1.0
================================================
Smart Land Management Copilot — AI Agent with Function Calling
================================================
وكيل ذكي يعتمد على GLM-5.2-turbo مع استدعاء الدوال (Tool Calling)
لتنفيذ عمليات استثمارية عقارية متكاملة.

المعمارية:
  • Agent Loop يدعم أداوت (Tools) مسجّلة بـ JSON Schema
  • يدير حالة المحادثة (States): idle / investigating_land / bidding_auction / calculating_roi
  • يتذكر السياق عبر Session Memory (ذاكرة مشتركة لكل مستخدم)
  • يتكامل مع: محرك المطابقة 7D، محرك المزادات، المحافظ الرقمية، GLM للتقارير

الترقية من GLM-5 → 5.2-turbo:
  • تمت إضافة call_agent_api في LLMRouter يدعم messages + tools + tool_choice
  • يعالج stop_reason: "tool_calls" → تنفيذ الأداة، "end_turn" → رد نهائي،
    "max_tokens" → اقتطاع، "human_intervention" → تحويل للوكيل البشري

متغيرات البيئة:
  AGENT_MAX_TOOL_ROUNDS  — الحد الأقصى لجولات الأدوات (الافتراضي: 5)
  AGENT_SESSION_TTL     — مدة صلاحية الجلسة بالثواني (الافتراضي: 3600)
  GLM_MODEL             — النموذج (الافتراضي: glm-5.2-turbo)
"""

import os
import json
import time
import logging
import hashlib
from typing import Any, Callable, Dict, List, Optional
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────
# 1. حالات الوكيل (Agent States)
# ──────────────────────────────────────────────────────────────

class AgentState(str, Enum):
    """حالات الوكيل المحتملة."""
    IDLE = "idle"                           # بانتظار استعلام جديد
    INVESTIGATING_LAND = "investigating_land"  # يبحث عن أراضي ويحللها
    BIDDING_AUCTION = "bidding_auction"       # يقدم عرضاً في مزاد
    CALCULATING_ROI = "calculating_roi"       # يحسب العائد على الاستثمار
    GENERATING_REPORT = "generating_report"   # يولّد تقرير جدوى


# ──────────────────────────────────────────────────────────────
# 2. تعريف الأداة (Tool Definition)
# ──────────────────────────────────────────────────────────────

@dataclass
class ToolDefinition:
    """تعريف أداة واحدة يمكن للوكيل استدعاؤها."""
    name: str
    description: str
    parameters_schema: dict  # JSON Schema
    handler: Callable


# ──────────────────────────────────────────────────────────────
# 3. ذاكرة الجلسة (Session Memory)
# ──────────────────────────────────────────────────────────────

class SessionMemory:
    """
    ذاكرة محادثة لكل مستخدم.

    تُخزّن تاريخ المحادثة في الذاكرة (dict).
    يمكن استبدالها بـ Redis للإنتاج عبر تعديل _store/_load فقط.
    """

    def __init__(self, ttl_seconds: int = 3600):
        self._sessions: Dict[str, Dict[str, Any]] = {}
        self._ttl = ttl_seconds

    def _session_key(self, user_id: str, session_id: Optional[str] = None) -> str:
        """مفتاح الجلسة الفريد."""
        sid = session_id or "default"
        return f"{user_id}:{sid}"

    def get_messages(
        self, user_id: str, session_id: Optional[str] = None
    ) -> List[dict]:
        """استرجاع رسائل الجلسة."""
        key = self._session_key(user_id, session_id)
        session = self._sessions.get(key)
        if session is None:
            return []
        # فحص انتهاء الصلاحية
        if time.time() - session.get("created_at", 0) > self._ttl:
            del self._sessions[key]
            return []
        return session.get("messages", [])

    def add_message(
        self,
        user_id: str,
        role: str,
        content: str,
        session_id: Optional[str] = None,
        tool_calls: Optional[List[dict]] = None,
        tool_call_id: Optional[str] = None,
        name: Optional[str] = None,
    ):
        """إضافة رسالة إلى الجلسة."""
        key = self._session_key(user_id, session_id)
        if key not in self._sessions:
            self._sessions[key] = {"created_at": time.time(), "messages": []}
        msg: dict = {"role": role, "content": content}
        if tool_calls:
            msg["tool_calls"] = tool_calls
        if tool_call_id:
            msg["tool_call_id"] = tool_call_id
        if name:
            msg["name"] = name
        self._sessions[key]["messages"].append(msg)
        # اقتطاع الجلسة عند 50 رسالة لمنع نفاد الذاكرة
        if len(self._sessions[key]["messages"]) > 50:
            self._sessions[key]["messages"] = self._sessions[key]["messages"][-40:]

    def clear_session(self, user_id: str, session_id: Optional[str] = None):
        """مسح جلسة محددة."""
        key = self._session_key(user_id, session_id)
        self._sessions.pop(key, None)

    def get_state(
        self, user_id: str, session_id: Optional[str] = None
    ) -> AgentState:
        """استرجاع حالة الوكيل الحالية."""
        key = self._session_key(user_id, session_id)
        session = self._sessions.get(key, {})
        return AgentState(session.get("state", AgentState.IDLE.value))

    def set_state(
        self,
        state: AgentState,
        user_id: str,
        session_id: Optional[str] = None,
    ):
        """تعيين حالة الوكيل."""
        key = self._session_key(user_id, session_id)
        if key not in self._sessions:
            self._sessions[key] = {"created_at": time.time(), "messages": []}
        self._sessions[key]["state"] = state.value


# ──────────────────────────────────────────────────────────────
# 4. تعريفات الأدوات (Tool Definitions)
# ──────────────────────────────────────────────────────────────

def _tool_search_lands() -> ToolDefinition:
    """أداة البحث عن الأراضي عبر محرك المطابقة السباعي."""
    return ToolDefinition(
        name="search_lands",
        description=(
            "ابحث عن الأراضي المتاحة في مصر باستخدام محرك المطابقة السباعي الأبعاد. "
            "يُرجع قائمة بالأراضي الأكثر توافقاً مع معايير المستثمر مع نسبة التوافق "
            "(0-100%) وتفاصيل كل أرض. استخدمها عندما يطلب المستثمر البحث عن أرض "
            "أو يسأل عن أراضٍ مناسبة لنشاطه أو ميزانيته."
        ),
        parameters_schema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": (
                        "وصف استعلام البحث بالعربية. مثال: "
                        "'أبحث عن أرض صناعية في العاصمة الإدارية بميزانية 5 مليون جنيه'"
                    ),
                },
                "activity": {
                    "type": "string",
                    "enum": [
                        "صناعي", "زراعي", "سكني", "تجاري",
                        "خدمات لوجستية", "سياحي", "تعليمي", "طبي",
                    ],
                    "description": "نوع النشاط الاستثماري المطلوب (اختياري).",
                },
                "max_budget": {
                    "type": "number",
                    "description": "الحد الأقصى للميزانية الإجمالية بالجنيه المصري (اختياري).",
                },
                "min_area": {
                    "type": "integer",
                    "description": "الحد الأدنى للمساحة بالمتر المربع (اختياري).",
                },
                "governorate": {
                    "type": "string",
                    "description": "المحافظة المفضلة بالعربية (اختياري).",
                },
            },
            "required": ["query"],
        },
        handler=None,  # يُعيَّن لاحقاً في LandInvestmentAgent.__init__
    )


def _tool_analyze_roi() -> ToolDefinition:
    """أداة تحليل العائد على الاستثمار."""
    return ToolDefinition(
        name="analyze_roi",
        description=(
            "احسب العائد على الاستثمار (ROI) ومعدل العائد الداخلي (IRR) لأرض محددة "
            "على أفق زمني معين. يُرجع تحليلاً مالياً يشمل: إجمالي الاستثمار، "
            "القيمة المتوقعة بعد سنوات، صافي الربح، ROI، IRR التقريبي. "
            "استخدمها عندما يسأل المستثمر عن جدوى أرض أو عائد استثمار أو يطلب تحليلاً مالياً."
        ),
        parameters_schema={
            "type": "object",
            "properties": {
                "land_id": {
                    "type": "string",
                    "description": "معرّف الأرض المراد تحليلها.",
                },
                "horizon_years": {
                    "type": "integer",
                    "description": "أفق الاستثمار بالسنوات (الافتراضي: 5).",
                    "default": 5,
                },
            },
            "required": ["land_id"],
        },
        handler=None,
    )


def _tool_check_wallet() -> ToolDefinition:
    """أداة فحص رصيد المحفظة."""
    return ToolDefinition(
        name="check_wallet",
        description=(
            "تحقق من رصيد محفظة المستثمر المتاح (بدون المبالغ المجمدة في المزادات). "
            "استخدمها قبل تقديم عرض في مزاد أو عند سؤال المستثمر عن رصيده."
        ),
        parameters_schema={
            "type": "object",
            "properties": {
                "investor_id": {
                    "type": "string",
                    "description": "معرّف المستثمر.",
                },
            },
            "required": ["investor_id"],
        },
        handler=None,
    )


def _tool_place_bid() -> ToolDefinition:
    """أداة تقديم عرض في المزاد."""
    return ToolDefinition(
        name="place_bid",
        description=(
            "قدّم عرضاً في مزاد علني لأرض محددة. النظام يجمّد تلقائياً 10% ضمان "
            "من رصيد المستثمر عند أول مزايدة. يجب أن يكون العرض أعلى من السعر الحالي "
            "بنسبة لا تقل عن 2%. استخدمها عندما يطلب المستثمر المشاركة في مزاد أو "
            "تقديم عرض شراء."
        ),
        parameters_schema={
            "type": "object",
            "properties": {
                "land_id": {
                    "type": "string",
                    "description": "معرّف الأرض المزاد عليها.",
                },
                "amount": {
                    "type": "number",
                    "description": "مقدار العرض بالجنيه المصري.",
                },
            },
            "required": ["land_id", "amount"],
        },
        handler=None,
    )


def _tool_send_report() -> ToolDefinition:
    """أداة إرسال تقرير جدوى."""
    return ToolDefinition(
        name="send_report",
        description=(
            "ولّد تقرير جدوى استشاري شامل لأرض محددة باستخدام الذكاء الاصطناعي (GLM). "
            "التقرير يتضمن 6 أقسام: ملخص تنفيذي، تقييم المستثمر، تحليل الأراضي، "
            "تحليل مقارن، توصية استراتيجية، وإخلاء مسؤولية. "
            "استخدمها عندما يطلب المستثمر تقريراً مفصلاً أو تقرير جدوى."
        ),
        parameters_schema={
            "type": "object",
            "properties": {
                "land_id": {
                    "type": "string",
                    "description": "معرّف الأرض المراد إنشاء التقرير لها.",
                },
            },
            "required": ["land_id"],
        },
        handler=None,
    )


# ──────────────────────────────────────────────────────────────
# 5. الوكيل الرئيسي (Land Investment Agent)
# ──────────────────────────────────────────────────────────────

# Persona ثابتة للوكيل
AGENT_PERSONA = """\
You are an Egyptian land investment agent that helps investors buy land, \
participate in auctions, and analyze ROI. You work for "Smart Land Copilot" \
— the first AI-powered land investment platform in Egypt and the Middle East.

You MUST:
1. Always respond in Arabic (Egyptian dialect for conversation, formal Arabic for reports).
2. Use Egyptian Pound (EGP / جنيه مصري) for all financial figures.
3. Proactively use your available tools when an investor's request requires action \
   (search, bid, analyze, etc.).
4. When searching for lands, always call search_lands first — never guess land data.
5. Before placing a bid, always call check_wallet to verify sufficient balance.
6. If you need more information from the investor, ask clearly before acting.
7. Reference Egyptian laws when relevant: Investment Law 72/2017, NUCA regulations, GAFI.
8. Never invent land data or financial figures — always use tools to get real data.
9. If the user's request is outside your capabilities, offer to connect them with \
   a human agent (stop_reason: "human_intervention").
10. Keep responses concise and action-oriented for chat, but comprehensive for reports.
"""

# تقدير معدلات نمو الأسعار حسب المحافظة (fallback حتى توفر بيانات TFT الحقيقية)
_GOVERNORATE_APPRECIATION_RATES = {
    "العاصمة الإدارية الجديدة": 0.18,
    "6 أكتوبر": 0.15,
    "الشيخ زايد": 0.14,
    "القاهرة الجديدة": 0.12,
    "العين السخنة": 0.10,
    "رأس سدر": 0.13,
    "السخنة": 0.09,
    "المنصورة": 0.08,
    "طنطا": 0.07,
    "أسيوط": 0.06,
}


class LandInvestmentAgent:
    """
    وكيل الاستثمار العقاري الذكي.

    يدير حلقة وكيل كاملة (Agent Loop) مع Function Calling:
      1. يستقبل رسالة المستخدم
      2. يبني الرسائل (system + history + user + tools)
      3. يرسلها لـ GLM-5.2-turbo عبر LLMRouter
      4. إذا ردّ النموذج بـ tool_calls → ينفّذها ويعيد النتائج
      5. يكرر حتى يُنتج النموذج رداً نصياً نهائياً أو يصل للحد الأقصى للجولات

    الاستخدام:
        agent = LandInvestmentAgent()
        result = await agent.chat(
            user_id="inv-001",
            message="أريد أرضاً صناعية بـ 5 مليون",
        )
        print(result["response"])
        print(result["actions_taken"])  # [{"tool": "search_lands", "result": ...}]
    """

    MAX_TOOL_ROUNDS = int(os.environ.get("AGENT_MAX_TOOL_ROUNDS", "5"))

    def __init__(
        self,
        memory: Optional[SessionMemory] = None,
        session_ttl: int = 3600,
        auto_init_router: bool = True,
    ):
        """
        تهيئة الوكيل.

        Args:
            memory: ذاكرة الجلسات (الافتراضي: ذاكرة في الذاكرة)
            session_ttl: مدة صلاحية الجلسة بالثواني
            auto_init_router: تهيئة LLMRouter تلقائياً
        """
        # ذاكرة الجلسات
        self.memory = memory or SessionMemory(ttl_seconds=session_ttl)

        # LLM Router (كسول التهيئة)
        self._router = None
        self._auto_init_router = auto_init_router

        # تعريفات الأدوات
        self._tools: List[ToolDefinition] = [
            _tool_search_lands(),
            _tool_analyze_roi(),
            _tool_check_wallet(),
            _tool_place_bid(),
            _tool_send_report(),
        ]

        # ربط الـ handlers
        self._bind_handlers()

        logger.info(
            "تم تهيئة LandInvestmentAgent — %d أدوات مسجّلة",
            len(self._tools),
        )

    # ──────────────────────────────────────────────────────────
    # 5.1 ربط الـ Handlers
    # ──────────────────────────────────────────────────────────

    def _bind_handlers(self):
        """ربط دوال التنفيذ بكل أداة."""
        for tool in self._tools:
            if tool.name == "search_lands":
                tool.handler = self._handle_search_lands
            elif tool.name == "analyze_roi":
                tool.handler = self._handle_analyze_roi
            elif tool.name == "check_wallet":
                tool.handler = self._handle_check_wallet
            elif tool.name == "place_bid":
                tool.handler = self._handle_place_bid
            elif tool.name == "send_report":
                tool.handler = self._handle_send_report

    def _get_router(self):
        """الحصول على مثيل LLMRouter (كسول)."""
        if self._router is None and self._auto_init_router:
            from core.ai.llm.router import LLMRouter
            self._router = LLMRouter()
        return self._router

    # ──────────────────────────────────────────────────────────
    # 5.2 Handlers — تنفيذ الأدوات
    # ──────────────────────────────────────────────────────────

    async def _handle_search_lands(self, arguments: dict) -> str:
        """تنفيذ البحث عن الأراضي عبر محرك المطابقة."""
        query = arguments.get("query", "")
        logger.info("أداة search_lands — استعلام: %s", query)

        try:
            # تحويل الاستعلام إلى معايير مطابقة
            from core.matchmaking.service import (
                InvestorCriteria,
                investor_smart_match,
                format_match_results_for_llm,
            )
            from core.domain.land_database import get_all_lands

            criteria = InvestorCriteria(
                النشاط_المطلوب=arguments.get("activity"),
                الميزانية_الإجمالية=arguments.get("max_budget"),
                الحد_الأدنى_للمساحة=arguments.get("min_area"),
                المحافظة_المفضلة=arguments.get("governorate"),
            )

            matches = investor_smart_match(criteria, top_k=5, min_score=20)
            lands_data = get_all_lands()

            if not matches:
                return json.dumps({
                    "status": "no_results",
                    "message": "لم يتم العثور على أراضٍ مطابقة. حاول توسيع معايير البحث.",
                    "results": [],
                }, ensure_ascii=False)

            # تحويل النتائج إلى صيغة مهيكلة
            results = []
            for m in matches:
                results.append({
                    "land_id": m.land_id,
                    "compatibility_pct": round(m.compatibility_pct, 1),
                    "is_auction": m.is_auction,
                    "quality": m.land_quality_rating,
                    "match_reasons": m.match_reasons[:3],
                    "gap_warnings": m.gap_warnings[:2],
                })

            # تحضير نص سياقي للتقرير (مختصر)
            context_text = format_match_results_for_llm(
                matches, lands_data, None
            )

            return json.dumps({
                "status": "success",
                "message": f"تم العثور على {len(results)} أرض متطابقة",
                "results": results,
                "context_for_report": context_text[:2000],  # اقتطاع للتقرير
            }, ensure_ascii=False)

        except ImportError as e:
            logger.warning("لا يمكن استيراد وحدة المطابقة: %s", e)
            return json.dumps({
                "status": "error",
                "message": f"وحدة المطابقة غير متاحة: {e}",
            }, ensure_ascii=False)
        except Exception as e:
            logger.error("خطأ في search_lands: %s", e, exc_info=True)
            return json.dumps({
                "status": "error",
                "message": f"خطأ في البحث: {e}",
            }, ensure_ascii=False)

    async def _handle_analyze_roi(self, arguments: dict) -> str:
        """حساب ROI/IRR لأرض محددة."""
        land_id = arguments.get("land_id", "")
        horizon = arguments.get("horizon_years", 5)
        logger.info("أداة analyze_roi — land_id: %s, horizon: %d", land_id, horizon)

        try:
            from core.domain.land_database import get_all_lands

            lands = get_all_lands()
            land = None
            for l in lands:
                if l.get("المعرف") == land_id or l.get("id") == land_id:
                    land = l
                    break

            if land is None:
                return json.dumps({
                    "status": "error",
                    "message": f"الأرض {land_id} غير موجودة في قاعدة البيانات",
                }, ensure_ascii=False)

            # استخراج بيانات الأرض
            price_total = float(land.get("السعر_الإجمالي", land.get("total_price", 0)))
            area = float(land.get("المساحة_بالمتر", land.get("area_sqm", 0)))
            price_sqm = price_total / area if area > 0 else 0
            governorate = land.get("المحافظة", "")
            quality = land.get("الجودة", "B")

            # معدل النمو السنوي المتوقع
            appreciation_rate = _GOVERNORATE_APPRECIATION_RATES.get(
                governorate, 0.08
            )

            # جودة الأرض تؤثر على النمو (AAA=1.2x, AA=1.1x, A=1.0x, B=0.9x)
            quality_multiplier = {"AAA": 1.2, "AA": 1.1, "A": 1.0, "B": 0.9}
            effective_rate = appreciation_rate * quality_multiplier.get(quality, 1.0)

            # حساب القيمة المستقبلية
            future_value = price_total * ((1 + effective_rate) ** horizon)

            # تكلفة التطوير المقدرة (10-30% حسب النوع)
            dev_cost_pct = 0.15  # متوسط
            dev_cost = price_total * dev_cost_pct
            total_investment = price_total + dev_cost

            # صافي الربح (باعتبار البيع بعد تطوير بسيط)
            net_profit = future_value - total_investment
            roi = (net_profit / total_investment) * 100 if total_investment > 0 else 0

            # IRR تقريبي (باستخدام صيغة معدل النمو المركب)
            irr_approx = (effective_rate * 100) - dev_cost_pct * 100 / horizon

            # تحليل المخاطر
            risk_factors = []
            if quality in ("B",):
                risk_factors.append("جودة الأرض أساسية — قد تحتاج استثمار إضافي في البنية التحتية")
            if appreciation_rate < 0.10:
                risk_factors.append("معدل النمو في المحافظة متوسط — استثمار طويل الأجل")
            if horizon > 7:
                risk_factors.append("أفق الاستثمار طويل — مخاطر تنظيمية وتضخمية أعلى")

            return json.dumps({
                "status": "success",
                "land_id": land_id,
                "governorate": governorate,
                "quality": quality,
                "analysis": {
                    "current_value_egp": round(price_total, 0),
                    "estimated_dev_cost_egp": round(dev_cost, 0),
                    "total_investment_egp": round(total_investment, 0),
                    "projected_value_egp": round(future_value, 0),
                    "horizon_years": horizon,
                    "annual_appreciation_rate": round(effective_rate * 100, 1),
                    "net_profit_egp": round(net_profit, 0),
                    "roi_pct": round(roi, 1),
                    "irr_approx_pct": round(irr_approx, 1),
                    "risk_factors": risk_factors,
                },
            }, ensure_ascii=False)

        except Exception as e:
            logger.error("خطأ في analyze_roi: %s", e, exc_info=True)
            return json.dumps({
                "status": "error",
                "message": f"خطأ في تحليل العائد: {e}",
            }, ensure_ascii=False)

    async def _handle_check_wallet(self, arguments: dict) -> str:
        """فحص رصيد محفظة المستثمر."""
        investor_id = arguments.get("investor_id", "")
        logger.info("أداة check_wallet — investor_id: %s", investor_id)

        try:
            # محاولة استخدام المتجر المتزامن (للمرحلة الحالية)
            from infrastructure.persistence.account_store import (
                init_stores, InvestorStore,
            )
            inv_store, _ = init_stores()

            if hasattr(inv_store, "get_balance"):
                balance = inv_store.get_balance(investor_id)
            elif hasattr(inv_store, "get_wallet"):
                wallet = inv_store.get_wallet(investor_id)
                balance = wallet.get("balance", 0)
            else:
                balance = 0

            return json.dumps({
                "status": "success",
                "investor_id": investor_id,
                "available_balance_egp": float(balance),
                "currency": "EGP",
            }, ensure_ascii=False)

        except Exception as e:
            logger.warning("خطأ في check_wallet: %s", e)
            return json.dumps({
                "status": "error",
                "message": f"لا يمكن الوصول للمحفظة: {e}",
                "investor_id": investor_id,
                "available_balance_egp": 0,
            }, ensure_ascii=False)

    async def _handle_place_bid(self, arguments: dict) -> str:
        """تقديم عرض في المزاد."""
        land_id = arguments.get("land_id", "")
        amount = float(arguments.get("amount", 0))
        logger.info("أداة place_bid — land_id: %s, amount: %s", land_id, amount)

        try:
            from infrastructure.database import get_session
            from core.auction.engine import AuctionEngine, AuctionNotActiveError, BidTooLowError, InsufficientBalanceError

            async with get_session() as session:
                engine = AuctionEngine(session=session)

                # نحتاج investor_id من سياق المحادثة
                # سيتم تمريره عبر _current_user_id
                investor_id = self._current_user_id or "anonymous"

                success = await engine.place_bid(
                    land_id=land_id,
                    investor_id=investor_id,
                    bid_amount=amount,
                )
                await session.commit()

                if success:
                    return json.dumps({
                        "status": "success",
                        "message": f"تم تقديم عرضك بنجاح: {amount:,.0f} جنيه على الأرض {land_id}",
                        "land_id": land_id,
                        "bid_amount": amount,
                        "investor_id": investor_id,
                    }, ensure_ascii=False)
                else:
                    return json.dumps({
                        "status": "failed",
                        "message": "فشل تقديم العرض. تحقق من أن المزاد نشط وأن المبلغ كافٍ.",
                    }, ensure_ascii=False)

        except (AuctionNotActiveError, BidTooLowError, InsufficientBalanceError) as e:
            return json.dumps({
                "status": "error",
                "message": str(e),
                "land_id": land_id,
            }, ensure_ascii=False)
        except Exception as e:
            logger.error("خطأ في place_bid: %s", e, exc_info=True)
            return json.dumps({
                "status": "error",
                "message": f"خطأ في تقديم العرض: {e}",
            }, ensure_ascii=False)

    async def _handle_send_report(self, arguments: dict) -> str:
        """توليد تقرير جدوى عبر GLM."""
        land_id = arguments.get("land_id", "")
        logger.info("أداة send_report — land_id: %s", land_id)

        try:
            from core.domain.land_database import get_all_lands
            from core.ai.llm.router import LLMRouter

            # الحصول على بيانات الأرض
            lands = get_all_lands()
            land = None
            for l in lands:
                if l.get("المعرف") == land_id or l.get("id") == land_id:
                    land = l
                    break

            if land is None:
                return json.dumps({
                    "status": "error",
                    "message": f"الأرض {land_id} غير موجودة",
                }, ensure_ascii=False)

            # توليد التقرير عبر LLMRouter
            router = self._get_router()
            if router is None:
                router = LLMRouter()

            land_summary = json.dumps(land, ensure_ascii=False, default=str)
            report = router.chat_completion(
                user_query=(
                    f"أنشئ تقرير جدوى استشاري شامل للأرض التالية:\n\n"
                    f"بيانات الأرض:\n{land_summary}\n\n"
                    f"ركّز على: جدوى الاستثمار، المخاطر، التوصية الاستراتيجية."
                ),
                context=f"بيانات الأرض {land_id}: {land_summary}",
                temperature=0.3,
                max_tokens=4096,
            )

            return json.dumps({
                "status": "success",
                "land_id": land_id,
                "report": report,
                "message": "تم توليد تقرير الجدوى بنجاح",
            }, ensure_ascii=False)

        except Exception as e:
            logger.error("خطأ في send_report: %s", e, exc_info=True)
            return json.dumps({
                "status": "error",
                "message": f"خطأ في توليد التقرير: {e}",
            }, ensure_ascii=False)

    # ──────────────────────────────────────────────────────────
    # 5.3 تحويل الأدوات إلى صيغة OpenAI Function Calling
    # ──────────────────────────────────────────────────────────

    def _get_openai_tools(self) -> List[dict]:
        """تحويل تعريفات الأدوات إلى صيغة OpenAI tools."""
        return [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.parameters_schema,
                },
            }
            for t in self._tools
        ]

    # ──────────────────────────────────────────────────────────
    # 5.4 حلقة الوكيل الرئيسية (Agent Loop)
    # ──────────────────────────────────────────────────────────

    def _classify_state(self, message: str, actions_taken: List[dict]) -> AgentState:
        """تصنيف حالة الوكيل بناءً على الرسالة والأدوات المنفّذة."""
        if actions_taken:
            last_action = actions_taken[-1].get("tool", "")
            if last_action == "place_bid":
                return AgentState.BIDDING_AUCTION
            elif last_action == "analyze_roi":
                return AgentState.CALCULATING_ROI
            elif last_action == "search_lands":
                return AgentState.INVESTIGATING_LAND
            elif last_action == "send_report":
                return AgentState.GENERATING_REPORT

        # تصنيف بناءً على محتوى الرسالة
        msg_lower = message.lower()
        bid_keywords = ["مزاد", "عرض", "زايد", "مزايدة", "أقدم عرض"]
        roi_keywords = ["عائد", "ربح", "جدوى", "roi", "irr", "استثمار"]
        search_keywords = ["بحث", "أبحث", "أريد أرض", "ابحث عن", "مطابق"]

        if any(k in msg_lower for k in bid_keywords):
            return AgentState.BIDDING_AUCTION
        elif any(k in msg_lower for k in roi_keywords):
            return AgentState.CALCULATING_ROI
        elif any(k in msg_lower for k in search_keywords):
            return AgentState.INVESTIGATING_LAND

        return AgentState.IDLE

    async def chat(
        self,
        user_id: str,
        message: str,
        session_id: Optional[str] = None,
    ) -> dict:
        """
        نقطة الدخول الرئيسية — محادثة كاملة مع الوكيل.

        Args:
            user_id: معرّف المستثمر
            message: رسالة المستثمر
            session_id: معرّف الجلسة (اختياري)

        Returns:
            {
                "response": str,           # رد الوكيل النهائي
                "state": str,              # حالة الوكيل بعد المحادثة
                "actions_taken": [dict],   # الأدوات المنفّذة
                "tool_rounds": int,        # عدد جولات الأدوات
                "stop_reason": str,        # سبب التوقف
            }
        """
        self._current_user_id = user_id
        router = self._get_router()

        # 1. حفظ رسالة المستخدم في الذاكرة
        self.memory.add_message(
            user_id, "user", message, session_id=session_id
        )

        # 2. بناء قائمة الرسائل للإرسال
        messages = self._build_messages(user_id, session_id, message)

        # 3. حلقة الأدوات
        actions_taken: List[dict] = []
        tool_rounds = 0
        stop_reason = "end_turn"

        for round_num in range(self.MAX_TOOL_ROUNDS):
            tool_rounds = round_num + 1
            logger.info(
                "جولة الأدوات %d/%d — user_id: %s",
                tool_rounds, self.MAX_TOOL_ROUNDS, user_id,
            )

            # إرسال الرسائل + الأدوات لـ GLM
            try:
                result = self._call_agent_api(
                    router=router,
                    messages=messages,
                    tools=self._get_openai_tools(),
                )
            except Exception as e:
                logger.error("خطأ في استدعاء الوكيل: %s", e, exc_info=True)
                # Fallback: رد عادي بدون أدوات
                try:
                    response_text = router.chat_completion(
                        user_query=message,
                        context="",
                        temperature=0.4,
                    )
                    return {
                        "response": response_text,
                        "state": AgentState.IDLE.value,
                        "actions_taken": actions_taken,
                        "tool_rounds": 0,
                        "stop_reason": "fallback",
                    }
                except Exception:
                    return {
                        "response": "عذراً، حدث خطأ تقني. يرجى المحاولة مرة أخرى أو التواصل مع الدعم الفني.",
                        "state": AgentState.IDLE.value,
                        "actions_taken": [],
                        "tool_rounds": 0,
                        "stop_reason": "error",
                    }

            assistant_message = result.get("message", {})
            content = assistant_message.get("content", "")
            tool_calls = assistant_message.get("tool_calls", [])
            result_stop = result.get("stop_reason", "end_turn")

            # حفظ رد المساعد (قبل تنفيذ الأدوات)
            self.memory.add_message(
                user_id, "assistant", content or "",
                session_id=session_id,
                tool_calls=tool_calls if tool_calls else None,
            )

            # إذا لم يطلب استدعاء أدوات → نهاية
            if not tool_calls:
                stop_reason = result_stop
                break

            # تنفيذ كل أداة مطلوبة
            for tc in tool_calls:
                fn_name = tc.get("function", {}).get("name", "")
                fn_args_str = tc.get("function", {}).get("arguments", "{}")
                tc_id = tc.get("id", "")

                try:
                    fn_args = json.loads(fn_args_str)
                except json.JSONDecodeError:
                    fn_args = {}

                logger.info("تنفيذ الأداة: %s(%s)", fn_name, fn_args)

                # البحث عن الأداة وتنفيذها
                tool_result = "أداة غير معروفة"
                for tool_def in self._tools:
                    if tool_def.name == fn_name and tool_def.handler:
                        try:
                            tool_result = await tool_def.handler(fn_args)
                        except Exception as e:
                            tool_result = json.dumps({
                                "status": "error",
                                "message": f"خطأ في تنفيذ الأداة: {e}",
                            }, ensure_ascii=False)
                        break

                # تسجيل نتيجة الأداة
                action_record = {
                    "tool": fn_name,
                    "arguments": fn_args,
                    "result": tool_result,
                }
                actions_taken.append(action_record)

                # إضافة نتيجة الأداة للرسائل
                self.memory.add_message(
                    user_id,
                    "tool",
                    tool_result,
                    session_id=session_id,
                    tool_call_id=tc_id,
                    name=fn_name,
                )

            # إعادة بناء الرسائل مع نتائج الأدوات
            messages = self._build_messages(user_id, session_id, message)

            # تحديث حالة الوكيل
            new_state = self._classify_state(message, actions_taken)
            self.memory.set_state(new_state, user_id, session_id)

        else:
            # وصلنا للحد الأقصى للجولات
            stop_reason = "max_tool_rounds"
            logger.warning("وصل الوكيل للحد الأقصى لجولات الأدوات: %d", self.MAX_TOOL_ROUNDS)

        # 4. استخراج الرد النهائي
        final_response = messages[-1].get("content", "") if messages else ""
        if not final_response:
            # تجميع ردود الأدوات كرد نهائي
            if actions_taken:
                final_response = self._synthesize_tool_results(actions_taken)
            else:
                final_response = "تم تنفيذ طلبك بنجاح."

        # 5. تحديث الحالة النهائية
        final_state = self._classify_state(message, actions_taken)
        self.memory.set_state(final_state, user_id, session_id)

        return {
            "response": final_response,
            "state": final_state.value,
            "actions_taken": actions_taken,
            "tool_rounds": tool_rounds,
            "stop_reason": stop_reason,
        }

    # ──────────────────────────────────────────────────────────
    # 5.5 دوال مساعدة
    # ──────────────────────────────────────────────────────────

    def _build_messages(
        self,
        user_id: str,
        session_id: Optional[str],
        current_message: str,
    ) -> List[dict]:
        """بناء قائمة الرسائل الكاملة للإرسال."""
        messages = [{"role": "system", "content": AGENT_PERSONA}]

        # إضافة تاريخ المحادثة
        history = self.memory.get_messages(user_id, session_id)
        for msg in history:
            filtered = {"role": msg["role"], "content": msg["content"]}
            if "tool_calls" in msg:
                filtered["tool_calls"] = msg["tool_calls"]
            if "tool_call_id" in msg:
                filtered["tool_call_id"] = msg["tool_call_id"]
            if "name" in msg:
                filtered["name"] = msg["name"]
            messages.append(filtered)

        return messages

    def _call_agent_api(
        self,
        router: Any,
        messages: List[dict],
        tools: List[dict],
    ) -> dict:
        """
        استدعاء API مع دعم Function Calling.

        يستخدم call_agent_api من LLMRouter (الترقية لـ 5.2).
        إذا لم يكن متاحاً، يfallback لـ call_glm_api العادي.
        """
        # محاولة استخدام call_agent_api الجديد
        if hasattr(router, "call_agent_api"):
            return router.call_agent_api(
                messages=messages,
                tools=tools,
                temperature=0.4,
            )

        # Fallback: استدعاء GLM مباشرة مع tools
        import os
        import requests

        config = {
            "api_key": os.environ.get(
                "GLM_API_KEY", os.environ.get("OPENROUTER_API_KEY", "")
            ),
            "base_url": os.environ.get(
                "GLM_BASE_URL", "https://openrouter.ai/api/v1"
            ),
            "model": os.environ.get("GLM_MODEL", "glm-5.2-turbo"),
        }

        if not config["api_key"]:
            # Mock fallback — محاكاة رد بدون أدوات
            return {
                "message": {
                    "role": "assistant",
                    "content": "عذراً، مفتاح API غير متاح. يرجى تعيين GLM_API_KEY أو OPENROUTER_API_KEY.",
                },
                "stop_reason": "end_turn",
            }

        payload = {
            "model": config["model"],
            "messages": messages,
            "tools": tools,
            "tool_choice": "auto",
            "temperature": 0.4,
            "max_tokens": 4096,
        }

        headers = {
            "Authorization": f"Bearer {config['api_key']}",
            "Content-Type": "application/json",
        }

        resp = requests.post(
            f"{config['base_url']}/chat/completions",
            headers=headers,
            json=payload,
            timeout=120,
        )
        resp.raise_for_status()
        data = resp.json()

        choice = data["choices"][0]
        message = choice.get("message", {})
        finish_reason = choice.get("finish_reason", "stop")

        # تحويل finish_reason إلى stop_reason
        stop_reason = "end_turn"
        if finish_reason == "tool_calls":
            stop_reason = "tool_calls"
        elif finish_reason == "length":
            stop_reason = "max_tokens"

        return {
            "message": message,
            "stop_reason": stop_reason,
        }

    def _synthesize_tool_results(self, actions: List[dict]) -> str:
        """تجميع نتائج الأدوات في رد نصي مختصر."""
        parts = []
        for action in actions:
            tool_name = action["tool"]
            result_str = action.get("result", "")

            try:
                result_data = json.loads(result_str)
                status = result_data.get("status", "")
                msg = result_data.get("message", "")

                if tool_name == "search_lands":
                    count = len(result_data.get("results", []))
                    parts.append(f"تم العثور على {count} أرض متطابقة. {msg}")
                elif tool_name == "analyze_roi":
                    analysis = result_data.get("analysis", {})
                    roi = analysis.get("roi_pct", "N/A")
                    parts.append(
                        f"تحليل العائد: ROI = {roi}%, "
                        f"القيمة المتوقعة = {analysis.get('projected_value_egp', 'N/A'):,} جنيه"
                    )
                elif tool_name == "check_wallet":
                    balance = result_data.get("available_balance_egp", 0)
                    parts.append(f"رصيدك المتاح: {balance:,.0f} جنيه")
                elif tool_name == "place_bid":
                    parts.append(msg)
                elif tool_name == "send_report":
                    parts.append("تم توليد تقرير الجدوى بنجاح.")
                else:
                    parts.append(msg or f"تم تنفيذ {tool_name}")
            except (json.JSONDecodeError, TypeError):
                parts.append(f"تم تنفيذ {tool_name}: {result_str[:200]}")

        return "\n\n".join(parts)

    def get_session_info(
        self, user_id: str, session_id: Optional[str] = None
    ) -> dict:
        """معلومات الجلسة الحالية."""
        state = self.memory.get_state(user_id, session_id)
        messages = self.memory.get_messages(user_id, session_id)
        return {
            "user_id": user_id,
            "session_id": session_id or "default",
            "state": state.value,
            "message_count": len(messages),
        }

    def clear_session(
        self, user_id: str, session_id: Optional[str] = None
    ):
        """مسح جلسة المستخدم."""
        self.memory.clear_session(user_id, session_id)
        logger.info("تم مسح جلسة المستخدم: %s", user_id)


# ──────────────────────────────────────────────────────────────
# 6. مثال محادثة (Conversation Example)
# ──────────────────────────────────────────────────────────────

EXAMPLE_CONVERSATION = """
=== مثال على محادثة وكيل كاملة ===

المستثمر: "أريد أرضاً صناعية بـ 5 مليون جنيه، ابحث عن توافق وأرسل عرضاً"

--- الجولة 1: الوكيل يستدعي search_lands ---
  Tool: search_lands({
      "query": "أرض صناعية بميزانية 5 مليون جنيه",
      "activity": "صناعي",
      "max_budget": 5000000
  })
  Result: {
      "status": "success",
      "results": [
          {"land_id": "LAND-042", "compatibility_pct": 87.5, "quality": "AA"},
          {"land_id": "LAND-018", "compatibility_pct": 82.3, "quality": "A"},
      ]
  }

--- الجولة 2: الوكيل يستدعي check_wallet (قبل العرض) ---
  Tool: check_wallet({"investor_id": "inv-001"})
  Result: {"available_balance_egp": 7500000}

--- الجولة 3: الوكيل يستدعي place_bid ---
  Tool: place_bid({"land_id": "LAND-042", "amount": 4800000})
  Result: {"status": "success", "message": "تم تقديم عرضك بنجاح: 4,800,000 جنيه"}

--- الرد النهائي للوكيل ---
"تم تنفيذ طلبك بالكامل:

1. البحث: تم العثور على أرضين صناعيتين متطابقتين:
   - LAND-042 في العاصمة الإدارية (توافق 87.5%، جودة AA) — الأفضل توافقاً
   - LAND-018 في 6 أكتوبر (توافق 82.3%، جودة A)

2. المحفظة: رصيدك المتاح 7,500,000 جنيه — كافٍ لتقديم العرض.

3. المزاد: تم تقديم عرضك بقيمة 4,800,000 جنيه على الأرض LAND-042.
   تم تجميد 480,000 جنيه (10%) كضمان في محفظتك.

هل تريدني أن أُعدّ تقرير جدوى شامل للأرض المختارة؟"

=== نهاية المثال ===
"""