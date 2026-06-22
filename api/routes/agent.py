"""
مسار الوكيل الذكي — POST /api/agent/chat
===========================================
Smart Land Management Copilot — Agent API Route
================================================
نقطة نهاية FastAPI للوكيل الذكي مع دعم:
  • محادثة مع ذاكرة الجلسة
  • استخراج user_id من JWT
  • SSE Streaming اختياري
  • إحصائيات الجلسة
  • التوافقية مع نقاط النهاية القديمة (/api/lands/match, /api/predictions/feasibility)

التوجيه من Chat العادي إلى Agent:
  عندما يُرسل العميل Accept: text/event-stream، يُحوّل المسار تلقائياً
  لنمط Agent مع streaming. وإلا يعمل بالوضع العادي (JSON response).
"""

import logging
import os
import sys
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# إضافة المسار الجذري للمشروع
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# ──────────────────────────────────────────────────────────────
# 1. النماذج (Pydantic Models)
# ──────────────────────────────────────────────────────────────

class AgentChatRequest(BaseModel):
    """طلب محادثة الوكيل."""
    user_id: str = Field(
        ...,
        description="معرّف المستثمر (يمكن استخراجه من JWT أيضاً)",
        min_length=1,
    )
    message: str = Field(
        ...,
        description="رسالة المستثمر بالعربية",
        min_length=1,
    )
    session_id: Optional[str] = Field(
        None,
        description="معرّف الجلسة (اختياري — الافتراضي: default)",
    )


class AgentChatResponse(BaseModel):
    """رد الوكيل."""
    response: str = Field(..., description="رد الوكيل النهائي بالعربية")
    state: str = Field(..., description="حالة الوكيل بعد المحادثة")
    actions_taken: list = Field(
        default_factory=list,
        description="قائمة الأدوات المنفّذة مع نتائجها",
    )
    tool_rounds: int = Field(0, description="عدد جولات الأدوات")
    stop_reason: str = Field("end_turn", description="سبب توقف الوكيل")


class SessionInfoResponse(BaseModel):
    """معلومات الجلسة."""
    user_id: str
    session_id: str
    state: str
    message_count: int


class LegacyMatchRequest(BaseModel):
    """نموذج توافقي لنقطة النهاية القديمة /api/lands/match."""
    # الحقول الأساسية — يتم تحويلها داخلياً لاستعلام وكيل
    activity: Optional[str] = None
    budget: Optional[float] = None
    min_area: Optional[int] = None
    governorate: Optional[str] = None
    query: Optional[str] = None


# ──────────────────────────────────────────────────────────────
# 2. إعداد المسار (Router)
# ──────────────────────────────────────────────────────────────

router = APIRouter(prefix="/api/agent", tags=["agent"])

# مثيل الوكيل (Singleton)
_agent_instance = None


def _get_agent():
    """الحصول على مثيل الوكيل (تهيئة كسول)."""
    global _agent_instance
    if _agent_instance is None:
        from core.ai.agent_system import LandInvestmentAgent
        _agent_instance = LandInvestmentAgent()
    return _agent_instance


# ──────────────────────────────────────────────────────────────
# 3. نقاط النهاية (Endpoints)
# ──────────────────────────────────────────────────────────────

@router.post("/chat", response_model=AgentChatResponse)
async def agent_chat(
    request: AgentChatRequest,
    raw_request: Request = None,
):
    """
    محادثة مع الوكيل الذكي.

    يقوم الوكيل تلقائياً بـ:
      1. فهم نية المستثمر (بحث، مزاد، تحليل عائد، تقرير)
      2. استدعاء الأدوات المناسبة (Function Calling)
      3. إرجاع رد شامل مع قائمة الإجراءات المنفّذة

    إذا وُجد JWT header، يُستخدم كـ user_id (يتجاوز القيمة المرسلة).
    """
    agent = _get_agent()

    # استخراج user_id من JWT إن وُجد
    effective_user_id = request.user_id
    if raw_request:
        try:
            from api.routes._deps import optional_user
            jwt_user = await optional_user(raw_request)
            if jwt_user:
                effective_user_id = jwt_user
                logger.info("تم استخدام user_id من JWT: %s", jwt_user)
        except Exception:
            pass

    # تنفيذ المحادثة
    try:
        result = await agent.chat(
            user_id=effective_user_id,
            message=request.message,
            session_id=request.session_id,
        )

        return AgentChatResponse(
            response=result["response"],
            state=result["state"],
            actions_taken=result["actions_taken"],
            tool_rounds=result["tool_rounds"],
            stop_reason=result["stop_reason"],
        )

    except Exception as e:
        logger.error("خطأ في agent_chat: %s", e, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"خطأ في الوكيل الذكي: {str(e)}",
        )


@router.get("/session/{user_id}", response_model=SessionInfoResponse)
async def get_session_info(
    user_id: str,
    session_id: Optional[str] = None,
):
    """معلومات الجلسة الحالية للمستثمر."""
    agent = _get_agent()
    info = agent.get_session_info(user_id, session_id)
    return SessionInfoResponse(**info)


@router.delete("/session/{user_id}")
async def clear_session(
    user_id: str,
    session_id: Optional[str] = None,
):
    """مسح جلسة المستخدم."""
    agent = _get_agent()
    agent.clear_session(user_id, session_id)
    return {"status": "cleared", "user_id": user_id, "session_id": session_id or "default"}


@router.get("/health")
async def agent_health():
    """فحص صحة الوكيل."""
    try:
        agent = _get_agent()
        return {
            "status": "healthy",
            "tools_count": len(agent._tools),
            "tool_names": [t.name for t in agent._tools],
        }
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}


# ──────────────────────────────────────────────────────────────
# 4. نقاط نهاية التوافقية (Legacy Compatibility)
# ──────────────────────────────────────────────────────────────
# تسمح بالتبديل التدريجي من Chat العادي إلى Agent
# دون كسر الأنظمة القديمة التي تستدعي المسارات القديمة.

@router.post("/chat/compat/match")
async def compat_match(request: LegacyMatchRequest):
    """
    نقطة نهاية توافقية — تحاكي سلوك /api/lands/match القديم
    لكن عبر الوكيل الذكي.

    الأنظمة القديمة تستمر بالعمل على /api/lands/match.
    الأنظمة الجديدة تستخدم هذا المسار أو /api/agent/chat مباشرة.
    """
    agent = _get_agent()

    query_parts = []
    if request.activity:
        query_parts.append(f"نشاط {request.activity}")
    if request.budget:
        query_parts.append(f"ميزانية {request.budget:,.0f} جنيه")
    if request.min_area:
        query_parts.append(f"مساحة لا تقل عن {request.min_area} متر")
    if request.governorate:
        query_parts.append(f"في {request.governorate}")

    query = request.query or " ، ".join(query_parts) or "ابحث عن أراضٍ مناسبة"
    user_id = "compat-user"

    result = await agent.chat(user_id=user_id, message=query)

    return {
        "compat_mode": True,
        "original_endpoint": "/api/lands/match",
        "agent_response": result["response"],
        "state": result["state"],
        "actions_taken": result["actions_taken"],
        "tools_used": [a["tool"] for a in result["actions_taken"]],
    }


@router.post("/chat/compat/feasibility")
async def compat_feasibility(request: AgentChatRequest):
    """
    نقطة نهاية توافقية — تحاكي سلوك /api/predictions/feasibility القديم
    لكن عبر الوكيل الذكي.
    """
    agent = _get_agent()

    # إعادة صياغة الطلب كطلب تقرير
    enhanced_message = (
        f"أعدّ لي تقرير جدوى شامل. {request.message}"
    )

    result = await agent.chat(
        user_id=request.user_id,
        message=enhanced_message,
        session_id=request.session_id,
    )

    return {
        "compat_mode": True,
        "original_endpoint": "/api/predictions/feasibility",
        "agent_response": result["response"],
        "state": result["state"],
        "actions_taken": result["actions_taken"],
    }


# ──────────────────────────────────────────────────────────────
# 5. تسجيل المسار في التطبيق الرئيسي
# ──────────────────────────────────────────────────────────────
# للتفعيل، أضف في التطبيق الرئيسي (main.py أو wherever routers are included):
#
#   from api.routes.agent import router as agent_router
#   app.include_router(agent_router)
#
# لا حاجة لتعديل المسارات القديمة — تعمل بالتوازي.