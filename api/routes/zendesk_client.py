"""
Zendesk API Client
==================
تكامل كامل مع Zendesk API لإدارة تذاكر الدعم الفني

Supports:
    - Create / Read / List / Update tickets
    - Add comments to tickets
    - List users and organizations
    - Rate-limit handling with exponential backoff
    - Demo mode (no API key required)

Authentication:
    Zendesk uses email + API token:
        email = "user@example.com/token"
        OR  email = "user@example.com" + api_token = "xxxxx"

Free tier:
    https://developer.zendesk.com/api-reference/ticketing/tickets/
    Trial sandbox: https://{subdomain}.zendesk.com
"""

import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# Data Classes
# ──────────────────────────────────────────────

class TicketStatus:
    """حالات التذكرة"""
    NEW = "new"
    OPEN = "open"
    PENDING = "pending"
    HOLD = "hold"
    SOLVED = "solved"
    CLOSED = "closed"


class TicketPriority:
    """أولويات التذكرة"""
    URGENT = "urgent"
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"


class ZendeskTicket:
    """نموذج بيانات التذكرة"""

    def __init__(
        self,
        subject: str,
        description: str,
        requester_email: str,
        requester_name: str = "",
        priority: str = TicketPriority.NORMAL,
        status: str = TicketStatus.NEW,
        tags: Optional[List[str]] = None,
        group_id: Optional[int] = None,
        assignee_id: Optional[int] = None,
        external_id: Optional[str] = None,
        # حقول Zendesk الداخلية
        zendesk_id: Optional[int] = None,
        created_at: Optional[str] = None,
        updated_at: Optional[str] = None,
    ):
        self.subject = subject
        self.description = description
        self.requester_email = requester_email
        self.requester_name = requester_name or requester_email.split("@")[0]
        self.priority = priority
        self.status = status
        self.tags = tags or ["smart-land"]
        self.group_id = group_id
        self.assignee_id = assignee_id
        self.external_id = external_id or f"SLC-{uuid.uuid4().hex[:8].upper()}"
        self.zendesk_id = zendesk_id
        self.created_at = created_at
        self.updated_at = updated_at

    def to_zendesk_payload(self) -> Dict[str, Any]:
        """تحويل التذكرة إلى صيغة Zendesk API"""
        payload: Dict[str, Any] = {
            "subject": self.subject,
            "comment": {"body": self.description},
            "priority": self.priority,
            "status": self.status,
            "tags": self.tags,
            "external_id": self.external_id,
        }
        if self.requester_name:
            payload["requester"] = {"name": self.requester_name, "email": self.requester_email}
        else:
            payload["requester"] = {"email": self.requester_email}
        if self.group_id:
            payload["group_id"] = self.group_id
        if self.assignee_id:
            payload["assignee_id"] = self.assignee_id
        return {"ticket": payload}

    def to_dict(self) -> Dict[str, Any]:
        """تحويل التذكرة إلى قاموس"""
        return {
            "external_id": self.external_id,
            "zendesk_id": self.zendesk_id,
            "subject": self.subject,
            "description": self.description,
            "requester_email": self.requester_email,
            "requester_name": self.requester_name,
            "priority": self.priority,
            "status": self.status,
            "tags": self.tags,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_zendesk_response(cls, data: Dict[str, Any]) -> "ZendeskTicket":
        """إنشاء تذكرة من استجابة Zendesk API"""
        return cls(
            subject=data.get("subject", ""),
            description=data.get("description", ""),
            requester_email=data.get("requester", {}).get("email", ""),
            requester_name=data.get("requester", {}).get("name", ""),
            priority=data.get("priority", TicketPriority.NORMAL),
            status=data.get("status", TicketStatus.NEW),
            tags=data.get("tags", []),
            group_id=data.get("group_id"),
            assignee_id=data.get("assignee_id"),
            external_id=data.get("external_id"),
            zendesk_id=data.get("id"),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
        )

    def __repr__(self) -> str:
        return (
            f"ZendeskTicket(zendesk_id={self.zendesk_id}, "
            f"subject='{self.subject[:40]}', "
            f"status={self.status}, priority={self.priority})"
        )


# ──────────────────────────────────────────────
# Zendesk Client
# ──────────────────────────────────────────────

class ZendeskClient:
    """
    عميل Zendesk API — تكامل كامل مع نظام تذاكر الدعم

    Usage:
        # Demo mode (no API key):
        client = ZendeskClient(demo_mode=True)

        # Live mode:
        client = ZendeskClient(
            subdomain="my-company",
            email="support@my-company.com",
            api_token="xxxxxxxxxxxxxxxxxxxx",
        )

    Rate Limiting:
        Zendesk limits to 700 requests/minute on Enterprise,
        200/minute on Team. This client handles 429 responses
        with exponential backoff.
    """

    BASE_URL_TEMPLATE = "https://{subdomain}.zendesk.com/api/v2"

    # حقول مخصصة (Custom Fields) — يجب تعريفها في Zendesk أولاً
    CUSTOM_FIELD_IDS = {
        "land_id": 900000000001,       # معرف الأرض
        "transaction_id": 900000000002, # معرف المعاملة
        "governorate": 900000000003,   # المحافظة
        "inquiry_type": 900000000004,  # نوع الاستفسار
        "chatbot_handoff": 900000000005, # تحويل من الشات بوت
    }

    def __init__(
        self,
        subdomain: str = "smartland",
        email: str = "",
        api_token: str = "",
        demo_mode: bool = False,
        timeout: int = 30,
        max_retries: int = 3,
    ):
        """
        تهيئة عميل Zendesk

        Args:
            subdomain: اسم النطاق الفرعي في Zendesk (مثال: smartland)
            email: البريد الإلكتروني للحساب
            api_token: رمز API من Zendesk
            demo_mode: وضع العرض التوضيحي (لا يحتاج مفتاح API)
            timeout: مهلة الاتصال بالثواني
            max_retries: عدد المحاولات عند فشل الطلب
        """
        self.subdomain = subdomain
        self.email = email
        self.api_token = api_token
        self.demo_mode = demo_mode
        self.timeout = timeout
        self.max_retries = max_retries

        self.base_url = self.BASE_URL_TEMPLATE.format(subdomain=subdomain)

        # Demo storage
        self._demo_tickets: Dict[int, ZendeskTicket] = {}
        self._demo_comments: Dict[int, List[Dict[str, Any]]] = {}
        self._demo_next_id = 1

        if not demo_mode and (not email or not api_token):
            logger.warning(
                "Zendesk: لا يوجد بريد أو رمز API — التبديل التلقائي لوضع العرض"
            )
            self.demo_mode = True

        logger.info(
            f"ZendeskClient initialized | subdomain={subdomain} | "
            f"demo={self.demo_mode}"
        )

    # ──────────────────────────────────────────
    # HTTP Layer
    # ──────────────────────────────────────────

    def _get_auth(self) -> tuple:
        """الحصول على بيانات المصادقة"""
        # Zendesk supports "email/token" format or basic auth with email + token
        return (f"{self.email}/token", self.api_token)

    def _request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict] = None,
        params: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """
        إرسال طلب HTTP إلى Zendesk API مع إعادة المحاولة

        Args:
            method: طريقة HTTP (GET, POST, PUT, DELETE)
            endpoint: مسار النقطة النهائية (مثال: /tickets.json)
            data: البيانات المرسلة
            params: معلمات الاستعلام

        Returns:
            الاستجابة كقاموس JSON

        Raises:
            ZendeskAPIError: عند فشل الطلب
        """
        url = f"{self.base_url}{endpoint}"
        headers = {"Content-Type": "application/json"}
        auth = self._get_auth()

        for attempt in range(1, self.max_retries + 1):
            try:
                response = requests.request(
                    method=method,
                    url=url,
                    auth=auth,
                    json=data,
                    params=params,
                    headers=headers,
                    timeout=self.timeout,
                )

                # Handle rate limiting (429)
                if response.status_code == 429:
                    retry_after = int(response.headers.get("Retry-After", 5))
                    logger.warning(
                        f"Zendesk rate limited — retrying in {retry_after}s "
                        f"(attempt {attempt}/{self.max_retries})"
                    )
                    time.sleep(retry_after)
                    continue

                # Handle other errors
                if response.status_code >= 400:
                    error_body = response.text[:500]
                    raise ZendeskAPIError(
                        f"Zendesk API error {response.status_code}: {error_body}",
                        status_code=response.status_code,
                    )

                return response.json()

            except requests.exceptions.Timeout:
                if attempt < self.max_retries:
                    wait = 2 ** attempt
                    logger.warning(f"Zendesk timeout — retrying in {wait}s")
                    time.sleep(wait)
                    continue
                raise ZendeskAPIError(f"Zendesk request timed out after {self.max_retries} attempts")

            except requests.exceptions.ConnectionError as e:
                if attempt < self.max_retries:
                    wait = 2 ** attempt
                    logger.warning(f"Zendesk connection error — retrying in {wait}s")
                    time.sleep(wait)
                    continue
                raise ZendeskAPIError(f"Zendesk connection failed: {str(e)[:200]}")

        raise ZendeskAPIError("Max retries exceeded")

    # ──────────────────────────────────────────
    # Ticket CRUD
    # ──────────────────────────────────────────

    def create_ticket(self, ticket: ZendeskTicket) -> Dict[str, Any]:
        """
        إنشاء تذكرة جديدة في Zendesk

        Args:
            ticket: كائن ZendeskTicket

        Returns:
            قاموس يحتوي على تفاصيل التذكرة المُنشأة
        """
        if self.demo_mode:
            return self._demo_create_ticket(ticket)

        payload = ticket.to_zendesk_payload()
        response = self._request("POST", "/tickets.json", data=payload)
        zendesk_ticket = response.get("ticket", {})

        logger.info(
            f"Ticket created in Zendesk | id={zendesk_ticket.get('id')} | "
            f"subject='{ticket.subject[:50]}'"
        )

        return {
            "success": True,
            "zendesk_id": zendesk_ticket.get("id"),
            "external_id": ticket.external_id,
            "status": zendesk_ticket.get("status"),
            "url": zendesk_ticket.get("url"),
            "ticket": ZendeskTicket.from_zendesk_response(zendesk_ticket).to_dict(),
        }

    def get_ticket(self, ticket_id: int) -> Optional[Dict[str, Any]]:
        """
        استرجاع تذكرة من Zendesk

        Args:
            ticket_id: معرف التذكرة في Zendesk

        Returns:
            بيانات التذكرة أو None إذا لم تُوجد
        """
        if self.demo_mode:
            return self._demo_get_ticket(ticket_id)

        response = self._request("GET", f"/tickets/{ticket_id}.json")
        zendesk_ticket = response.get("ticket", {})
        return ZendeskTicket.from_zendesk_response(zendesk_ticket).to_dict()

    def list_tickets(
        self,
        status: Optional[str] = None,
        assignee_id: Optional[int] = None,
        tags: Optional[List[str]] = None,
        sort_by: str = "created_at",
        sort_order: str = "desc",
        per_page: int = 25,
        page: int = 1,
    ) -> Dict[str, Any]:
        """
        عرض قائمة التذاكر مع فلاتر متعددة

        Args:
            status: فلتر الحالة (new/open/pending/solved/closed)
            assignee_id: فلتر معرف المسؤول
            tags: فلتر الوسوم
            sort_by: حقل الترتيب
            sort_order: اتجاه الترتيب (asc/desc)
            per_page: عدد النتائج في الصفحة
            page: رقم الصفحة

        Returns:
            قاموس يحتوي على قائمة التذاكر ومعلومات الصفحات
        """
        if self.demo_mode:
            return self._demo_list_tickets(status, per_page, page)

        params: Dict[str, Any] = {
            "sort_by": sort_by,
            "sort_order": sort_order,
            "per_page": min(per_page, 100),
            "page": page,
        }
        if status:
            params["status"] = status
        if assignee_id:
            params["assignee_id"] = assignee_id
        if tags:
            params["tags"] = ",".join(tags)

        response = self._request("GET", "/tickets.json", params=params)
        tickets = response.get("tickets", [])
        next_page = response.get("next_page")
        prev_page = response.get("previous_page")
        count = response.get("count", 0)

        return {
            "tickets": [
                ZendeskTicket.from_zendesk_response(t).to_dict() for t in tickets
            ],
            "total_count": count,
            "next_page": next_page,
            "previous_page": prev_page,
            "page": page,
            "per_page": per_page,
        }

    def update_ticket(
        self,
        ticket_id: int,
        status: Optional[str] = None,
        priority: Optional[str] = None,
        assignee_id: Optional[int] = None,
        tags: Optional[List[str]] = None,
        comment_body: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        تحديث تذكرة موجودة

        Args:
            ticket_id: معرف التذكرة
            status: الحالة الجديدة
            priority: الأولوية الجديدة
            assignee_id: معرف المسؤول الجديد
            tags: الوسوم الجديدة
            comment_body: نص التعليق (يُضاف كتعليق داخلي)

        Returns:
            بيانات التذكرة المُحدثة
        """
        if self.demo_mode:
            return self._demo_update_ticket(
                ticket_id, status, priority, assignee_id, comment_body
            )

        payload: Dict[str, Any] = {"ticket": {}}
        if status:
            payload["ticket"]["status"] = status
        if priority:
            payload["ticket"]["priority"] = priority
        if assignee_id:
            payload["ticket"]["assignee_id"] = assignee_id
        if tags is not None:
            payload["ticket"]["tags"] = tags
        if comment_body:
            payload["ticket"]["comment"] = {
                "body": comment_body,
                "author_id": None,  # سيتم تعيينه تلقائياً
            }

        response = self._request("PUT", f"/tickets/{ticket_id}.json", data=payload)
        zendesk_ticket = response.get("ticket", {})

        logger.info(
            f"Ticket {ticket_id} updated | status={status} | priority={priority}"
        )

        return ZendeskTicket.from_zendesk_response(zendesk_ticket).to_dict()

    def add_comment(
        self,
        ticket_id: int,
        body: str,
        is_public: bool = True,
        author_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        إضافة تعليق على تذكرة

        Args:
            ticket_id: معرف التذكرة
            body: نص التعليق
            is_public: هل التعليق مرئي للعميل؟
            author_id: معرف الكاتب (اختياري)

        Returns:
            بيانات التعليق المُضاف
        """
        if self.demo_mode:
            return self._demo_add_comment(ticket_id, body, is_public)

        payload = {
            "ticket": {
                "comment": {
                    "body": body,
                    "public": is_public,
                }
            }
        }
        if author_id:
            payload["ticket"]["comment"]["author_id"] = author_id

        response = self._request("PUT", f"/tickets/{ticket_id}.json", data=payload)
        audit = response.get("audit", {})
        events = audit.get("events", [])
        comment_event = next(
            (e for e in events if e.get("type") == "Comment"), {}
        )

        logger.info(
            f"Comment added to ticket {ticket_id} | "
            f"public={is_public} | chars={len(body)}"
        )

        return {
            "ticket_id": ticket_id,
            "comment_id": comment_event.get("id"),
            "body": body,
            "is_public": is_public,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

    # ──────────────────────────────────────────
    # Users & Organizations
    # ──────────────────────────────────────────

    def get_user(self, user_id: int) -> Dict[str, Any]:
        """استرجاع بيانات مستخدم"""
        if self.demo_mode:
            return {
                "id": user_id,
                "name": "مستخدم تجريبي",
                "email": "demo@smartland.eg",
                "role": "end-user",
            }
        response = self._request("GET", f"/users/{user_id}.json")
        return response.get("user", {})

    def search_users(self, query: str) -> List[Dict[str, Any]]:
        """البحث عن مستخدمين"""
        if self.demo_mode:
            return [
                {
                    "id": 1,
                    "name": "أحمد محمد",
                    "email": "ahmed@example.com",
                    "role": "end-user",
                }
            ]
        response = self._request("GET", "/users/search.json", params={"query": query})
        return response.get("users", [])

    # ──────────────────────────────────────────
    # Dashboard / Metrics
    # ──────────────────────────────────────────

    def get_ticket_metrics(self) -> Dict[str, Any]:
        """استخراج مقاييس التذاكر من Zendesk"""
        if self.demo_mode:
            all_tickets = list(self._demo_tickets.values())
            return self._compute_demo_metrics(all_tickets)

        # Fetch tickets by status for counting
        result = {"status_counts": {}, "total": 0}
        for status in [TicketStatus.NEW, TicketStatus.OPEN, TicketStatus.PENDING,
                       TicketStatus.SOLVED, TicketStatus.CLOSED, TicketStatus.HOLD]:
            resp = self.list_tickets(status=status, per_page=1)
            count = resp.get("total_count", 0)
            result["status_counts"][status] = count
            result["total"] += count

        result["avg_score"] = 0
        return result

    # ──────────────────────────────────────────
    # Demo Mode Implementation
    # ──────────────────────────────────────────

    def _demo_create_ticket(self, ticket: ZendeskTicket) -> Dict[str, Any]:
        """إنشاء تذكرة في وضع العرض التوضيحي"""
        ticket.zendesk_id = self._demo_next_id
        self._demo_next_id += 1
        ticket.created_at = datetime.now(timezone.utc).isoformat()
        ticket.updated_at = ticket.created_at
        self._demo_tickets[ticket.zendesk_id] = ticket
        self._demo_comments[ticket.zendesk_id] = []

        logger.info(
            f"[DEMO] Ticket created | id={ticket.zendesk_id} | "
            f"subject='{ticket.subject[:50]}'"
        )

        return {
            "success": True,
            "zendesk_id": ticket.zendesk_id,
            "external_id": ticket.external_id,
            "status": ticket.status,
            "url": f"https://{self.subdomain}.zendesk.com/agent/tickets/{ticket.zendesk_id}",
            "ticket": ticket.to_dict(),
        }

    def _demo_get_ticket(self, ticket_id: int) -> Optional[Dict[str, Any]]:
        """استرجاع تذكرة في وضع العرض التوضيحي"""
        ticket = self._demo_tickets.get(ticket_id)
        return ticket.to_dict() if ticket else None

    def _demo_list_tickets(
        self, status: Optional[str] = None, per_page: int = 25, page: int = 1
    ) -> Dict[str, Any]:
        """عرض التذاكر في وضع العرض التوضيحي"""
        all_tickets = list(self._demo_tickets.values())
        if status:
            all_tickets = [t for t in all_tickets if t.status == status]

        total = len(all_tickets)
        start = (page - 1) * per_page
        end = start + per_page
        page_tickets = all_tickets[start:end]

        return {
            "tickets": [t.to_dict() for t in page_tickets],
            "total_count": total,
            "next_page": f"?page={page + 1}" if end < total else None,
            "previous_page": f"?page={page - 1}" if page > 1 else None,
            "page": page,
            "per_page": per_page,
        }

    def _demo_update_ticket(
        self,
        ticket_id: int,
        status: Optional[str] = None,
        priority: Optional[str] = None,
        assignee_id: Optional[int] = None,
        comment_body: Optional[str] = None,
    ) -> Dict[str, Any]:
        """تحديث تذكرة في وضع العرض التوضيحي"""
        ticket = self._demo_tickets.get(ticket_id)
        if not ticket:
            raise ZendeskAPIError(f"Ticket {ticket_id} not found (demo)")

        if status:
            ticket.status = status
        if priority:
            ticket.priority = priority
        if assignee_id:
            ticket.assignee_id = assignee_id
        ticket.updated_at = datetime.now(timezone.utc).isoformat()

        if comment_body:
            self._demo_comments.setdefault(ticket_id, []).append({
                "id": len(self._demo_comments.get(ticket_id, [])) + 1,
                "body": comment_body,
                "created_at": ticket.updated_at,
            })

        return ticket.to_dict()

    def _demo_add_comment(
        self, ticket_id: int, body: str, is_public: bool = True
    ) -> Dict[str, Any]:
        """إضافة تعليق في وضع العرض التوضيحي"""
        ticket = self._demo_tickets.get(ticket_id)
        if not ticket:
            raise ZendeskAPIError(f"Ticket {ticket_id} not found (demo)")

        comment = {
            "id": len(self._demo_comments.get(ticket_id, [])) + 1,
            "body": body,
            "is_public": is_public,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self._demo_comments.setdefault(ticket_id, []).append(comment)
        ticket.updated_at = comment["created_at"]

        return {
            "ticket_id": ticket_id,
            "comment_id": comment["id"],
            "body": body,
            "is_public": is_public,
            "created_at": comment["created_at"],
        }

    @staticmethod
    def _compute_demo_metrics(tickets: List[ZendeskTicket]) -> Dict[str, Any]:
        """حساب مقاييس في وضع العرض التوضيحي"""
        status_counts: Dict[str, int] = {}
        for t in tickets:
            status_counts[t.status] = status_counts.get(t.status, 0) + 1

        return {
            "status_counts": status_counts,
            "total": len(tickets),
            "avg_score": 0,
        }


# ──────────────────────────────────────────────
# Custom Exception
# ──────────────────────────────────────────────

class ZendeskAPIError(Exception):
    """خطأ في Zendesk API"""

    def __init__(self, message: str, status_code: int = 0):
        super().__init__(message)
        self.status_code = status_code

    def __repr__(self) -> str:
        return f"ZendeskAPIError(status={self.status_code}, message='{str(self)[:100]}')"