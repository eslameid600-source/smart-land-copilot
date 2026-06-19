"""
Customer Service Hub — Orchestrator
=====================================
المُنسق المركزي لجميع مكونات خدمة العملاء

Integrates:
    1. RAGChatbot        → auto-answers FAQ queries
    2. ZendeskClient     → manages support tickets
    3. WhatsAppService   → WhatsApp Business messaging
    4. SurveyService     → satisfaction surveys

Flow:
    Customer Message arrives (Web / WhatsApp / API)
        ↓
    CustomerServiceHub.handle_message()
        ↓
    RAGChatbot.answer()
        ├── confidence ≥ 0.45 → Auto-reply (no ticket)
        ├── 0.20 ≤ confidence < 0.45 → Create ticket + partial answer
        └── confidence < 0.20  → Escalate to agent (create ticket)
        ↓
    After resolution → SurveyService.survey_user()

Usage:
    hub = CustomerServiceHub()  # All demo mode

    # Handle a customer query
    response = hub.handle_message(
        query="كيف أبدأ استخدام المنصة؟",
        channel="web",
        user_email="user@example.com",
    )
    print(response)

    # Handle WhatsApp message
    response = hub.handle_whatsapp_message(
        from_number="+201012345678",
        body="مشكلة في الدفع",
        profile_name="أحمد",
    )

    # Record survey
    result = hub.survey_user("TXN-001", rating=5, comment="ممتاز")
"""
import json
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
from services.customer_service.zendesk_client import ZendeskClient, ZendeskTicket, TicketStatus, TicketPriority, ZendeskAPIError
from services.customer_service.whatsapp_service import WhatsAppService, WebhookEvent, Provider, MessageDirection
from services.customer_service.rag_chatbot import RAGChatbot, ChatbotResponse
from services.customer_service.survey_service import SurveyService, SurveyType, SurveyRecord
logger = logging.getLogger(__name__)

class HubResponse:
    """استجابة مُنسق خدمة العملاء — موحدة لجميع القنوات"""

    def __init__(self, reply: str, channel: str='web', auto_resolved: bool=False, escalated: bool=False, ticket_created: bool=False, ticket_id: Optional[str]=None, zendesk_id: Optional[int]=None, chatbot_confidence: float=0.0, chatbot_category: str='', survey_id: Optional[str]=None, metadata: Optional[Dict[str, Any]]=None):
        self.reply = reply
        self.channel = channel
        self.auto_resolved = auto_resolved
        self.escalated = escalated
        self.ticket_created = ticket_created
        self.ticket_id = ticket_id
        self.zendesk_id = zendesk_id
        self.chatbot_confidence = chatbot_confidence
        self.chatbot_category = chatbot_category
        self.survey_id = survey_id
        self.metadata = metadata or {}

    def to_dict(self) -> Dict[str, Any]:
        return {'reply': self.reply, 'channel': self.channel, 'auto_resolved': self.auto_resolved, 'escalated': self.escalated, 'ticket_created': self.ticket_created, 'ticket_id': self.ticket_id, 'zendesk_id': self.zendesk_id, 'chatbot_confidence': round(self.chatbot_confidence, 4), 'chatbot_category': self.chatbot_category, 'survey_id': self.survey_id, 'metadata': self.metadata}

    def __repr__(self) -> str:
        return f'HubResponse(auto_resolved={self.auto_resolved}, escalated={self.escalated}, ticket={self.ticket_created}, confidence={self.chatbot_confidence:.2f})'

class CustomerServiceHub:
    """
    المُنسق المركزي لخدمة العملاء — يربط جميع المكونات

    Responsibilities:
        1. Receive customer queries from any channel
        2. Route to RAG chatbot first
        3. Decide: auto-reply, partial-reply + ticket, or escalate
        4. Create Zendesk tickets when needed
        5. Send WhatsApp notifications
        6. Trigger surveys after resolution

    All components default to demo mode (no API keys required).
    """

    def __init__(self, zendesk_subdomain: str='smartland', zendesk_email: str='', zendesk_api_token: str='', zendesk_demo_mode: bool=True, whatsapp_provider: str=Provider.TWILIO, whatsapp_demo_mode: bool=True, whatsapp_account_sid: str='', whatsapp_auth_token: str='', whatsapp_number: str='', whatsapp_meta_token: str='', whatsapp_phone_number_id: str='', chatbot_confidence_threshold: float=0.45, chatbot_escalate_threshold: float=0.2, chatbot_use_llm: bool=False, auto_survey_after_ticket: bool=True):
        """
        تهيئة مُنسق خدمة العملاء

        Args:
            zendesk_subdomain: نطاق Zendesk الفرعي
            zendesk_email: بريد Zendesk
            zendesk_api_token: رمز Zendesk API
            zendesk_demo_mode: وضع العرض (True = لا يحتاج مفتاح)
            whatsapp_provider: مزود واتساب (twilio/meta)
            whatsapp_demo_mode: وضع العرض
            whatsapp_account_sid: معرف Twilio
            whatsapp_auth_token: رمز Twilio
            whatsapp_number: رقم واتساب Twilio
            whatsapp_meta_token: رمز Meta API
            whatsapp_phone_number_id: معرف رقم Meta
            chatbot_confidence_threshold: عتبة ثقة الرد التلقائي
            chatbot_escalate_threshold: عتبة التحويل للوكيل
            chatbot_use_llm: استخدام LLM لتحسين الردود
            auto_survey_after_ticket: إرسال استبيان تلقائي بعد حل التذكرة
        """
        self.zendesk = ZendeskClient(subdomain=zendesk_subdomain, email=zendesk_email, api_token=zendesk_api_token, demo_mode=zendesk_demo_mode)
        self.whatsapp = WhatsAppService(provider=whatsapp_provider, demo_mode=whatsapp_demo_mode, account_sid=whatsapp_account_sid, auth_token=whatsapp_auth_token, whatsapp_number=whatsapp_number, access_token=whatsapp_meta_token, phone_number_id=whatsapp_phone_number_id)
        self.chatbot = RAGChatbot(confidence_threshold=chatbot_confidence_threshold, escalate_threshold=chatbot_escalate_threshold, use_llm=chatbot_use_llm)
        self.survey = SurveyService()
        self.auto_survey_after_ticket = auto_survey_after_ticket
        self._total_handled = 0
        self._auto_resolved = 0
        self._escalated = 0
        logger.info('CustomerServiceHub initialized — all components ready')

    def handle_message(self, query: str, channel: str='web', user_email: str='', user_name: str='', user_id: str='', phone_number: str='', transaction_id: str='', agent_id: str='') -> HubResponse:
        """
        معالجة رسالة العميل — الدالة الرئيسية

        Args:
            query: نص رسالة/استعلام العميل
            channel: القناة (web/whatsapp/email/api)
            user_email: بريد العميل
            user_name: اسم العميل
            user_id: معرف العميل
            phone_number: رقم هاتف العميل
            transaction_id: معرف المعاملة (إن وُجد)
            agent_id: معرف الوكيل (إن وُجد)

        Returns:
            HubResponse يحتوي على الرد وقرار التحويل
        """
        self._total_handled += 1
        logger.info(f"Handling message | channel={channel} | query='{query[:60]}' | user={user_email or phone_number}")
        user_context = {'user_id': user_id, 'user_email': user_email, 'channel': channel}
        if transaction_id:
            user_context['transaction_id'] = transaction_id
        chatbot_response = self.chatbot.answer(query, user_context=user_context)
        if not chatbot_response.should_escalate and chatbot_response.confidence >= self.chatbot.confidence_threshold:
            self._auto_resolved += 1
            return HubResponse(reply=chatbot_response.answer, channel=channel, auto_resolved=True, escalated=False, ticket_created=False, chatbot_confidence=chatbot_response.confidence, chatbot_category=chatbot_response.category, metadata={'source_id': chatbot_response.source_id, 'action': 'auto_resolved'})
        ticket = self._create_ticket_from_query(query=query, user_email=user_email, user_name=user_name, chatbot_response=chatbot_response, channel=channel, transaction_id=transaction_id)
        reply = chatbot_response.answer
        ticket_id = None
        zendesk_id = None
        ticket_created = False
        if ticket:
            ticket_id = ticket.get('external_id', '')
            zendesk_id = ticket.get('zendesk_id')
            ticket_created = True
            if chatbot_response.should_escalate and phone_number:
                self._send_escalation_whatsapp(phone_number=phone_number, ticket_id=ticket_id, user_name=user_name)
        if chatbot_response.should_escalate:
            self._escalated += 1
        return HubResponse(reply=reply, channel=channel, auto_resolved=False, escalated=chatbot_response.should_escalate, ticket_created=ticket_created, ticket_id=ticket_id, zendesk_id=zendesk_id, chatbot_confidence=chatbot_response.confidence, chatbot_category=chatbot_response.category, metadata={'source_id': chatbot_response.source_id, 'action': 'escalated' if chatbot_response.should_escalate else 'partial_answer_with_ticket'})

    def handle_whatsapp_message(self, from_number: str, body: str, profile_name: str='') -> HubResponse:
        """
        معالجة رسالة واتساب واردة

        Args:
            from_number: رقم المرسل
            body: نص الرسالة
            profile_name: اسم المرسل (من Meta profile)

        Returns:
            HubResponse مع النتيجة
        """
        conv = self.whatsapp.get_conversation(from_number)
        if not conv:
            self.whatsapp.start_conversation(from_number, context={'profile_name': profile_name})
        response = self.handle_message(query=body, channel='whatsapp', phone_number=from_number, user_name=profile_name)
        self.whatsapp.send_text(to=from_number, body=response.reply)
        if response.ticket_created:
            self.whatsapp.send_template(to=from_number, template_key='ticket_created', params={'ticket_number': response.ticket_id or 'N/A'})
        if response.escalated:
            self.whatsapp.send_interactive_buttons(to=from_number, body='تم تحويلك لوكيل الدعم. هل تريد إضافة أي معلومات إضافية؟', options=[{'id': 'add_info', 'title': 'إضافة معلومات'}, {'id': 'urgent', 'title': 'طلب عاجل'}, {'id': 'cancel', 'title': 'إلغاء'}])
        return response

    def handle_webhook(self, payload: Dict[str, Any], provider: str='meta') -> List[HubResponse]:
        """
        معالجة webhook وارد من WhatsApp (Meta أو Twilio)

        Args:
            payload: JSON payload
            provider: مزود الخدمة (meta/twilio)

        Returns:
            قائمة بالاستجابات
        """
        self.whatsapp.provider = provider
        events = self.whatsapp.process_webhook_payload(payload)
        responses = []
        for event in events:
            if event.event_type == 'message' and event.message_body:
                response = self.handle_whatsapp_message(from_number=event.phone_number, body=event.message_body, profile_name=event.profile_name)
                responses.append(response)
        return responses

    def survey_user(self, transaction_id: str, rating: int, survey_type: str=SurveyType.CSAT, user_id: str='', user_email: str='', comment: str='', channel: str='', agent_id: str='', ticket_id: str='') -> Dict[str, Any]:
        """
        تسجيل تقييم رضا العميل — واجهة عامة

        هذه هي الدالة المطلوبة:
            survey_user(transaction_id, rating)

        Args:
            transaction_id: معرف المعاملة
            rating: التقييم (1-5 لـ CSAT, 0-10 لـ NPS)
            survey_type: نوع الاستبيان
            user_id: معرف المستخدم
            user_email: بريد المستخدم
            comment: تعليق
            channel: القناة
            agent_id: معرف الوكيل
            ticket_id: معرف التذكرة

        Returns:
            نتيجة التسجيل
        """
        result = self.survey.survey_user(transaction_id=transaction_id, rating=rating, survey_type=survey_type, user_id=user_id, user_email=user_email, comment=comment, channel=channel, agent_id=agent_id, ticket_id=ticket_id)
        logger.info(f"Survey recorded | txn={transaction_id} | rating={rating} | success={result['success']}")
        return result

    def survey_after_ticket_resolution(self, ticket_id: str, rating: int, user_email: str='', comment: str='') -> Dict[str, Any]:
        """
        استبيان تلقائي بعد حل التذكرة

        يُستدعى من Zendesk webhook عند تغيير حالة التذكرة إلى "solved".
        """
        return self.survey_user(transaction_id=f'TKT-{ticket_id}', rating=rating, survey_type=SurveyType.POST_TICKET, user_email=user_email, comment=comment, channel='ticket_system', ticket_id=ticket_id)

    def resolve_ticket(self, ticket_id: str, resolution: str, agent_id: str='') -> Dict[str, Any]:
        """
        حل تذكرة — يمكن استدعاؤها من لوحة تحكم الوكيل

        Args:
            ticket_id: معرف التذكرة (external_id أو zendesk_id)
            resolution: نص الحل
            agent_id: معرف الوكيل

        Returns:
            نتيجة العملية
        """
        if ticket_id.startswith('TK-'):
            zid = self._find_zendesk_id_by_external(ticket_id)
            if not zid:
                return {'success': False, 'message': f'Ticket {ticket_id} not found'}
            zendesk_id = zid
        else:
            try:
                zendesk_id = int(ticket_id)
            except ValueError:
                return {'success': False, 'message': 'Invalid ticket ID format'}
        try:
            self.zendesk.update_ticket(zendesk_id, status=TicketStatus.SOLVED, comment_body=resolution)
        except ZendeskAPIError as e:
            logger.error(f'Failed to resolve ticket {zendesk_id}: {e}')
            return {'success': False, 'message': str(e)}
        survey_result = None
        if self.auto_survey_after_ticket:
            survey_result = self.survey.create_invitation(transaction_id=f'TKT-{ticket_id}', survey_type=SurveyType.POST_TICKET, channel='web')
        logger.info(f'Ticket {ticket_id} resolved by agent {agent_id}')
        return {'success': True, 'ticket_id': ticket_id, 'zendesk_id': zendesk_id, 'resolution': resolution, 'survey_invitation': survey_result}

    def get_dashboard(self, days: int=30) -> Dict[str, Any]:
        """
        لوحة معلومات خدمة العملاء — تجمع بيانات من جميع المكونات

        Returns:
            {
                "hub": {total_handled, auto_resolved, escalated, ...},
                "chatbot": {stats},
                "zendesk": {metrics},
                "whatsapp": {metrics},
                "survey": {dashboard_summary},
            }
        """
        zendesk_metrics = self.zendesk.get_ticket_metrics()
        chatbot_stats = self.chatbot.get_stats()
        whatsapp_metrics = self.whatsapp.get_metrics()
        survey_dashboard = self.survey.get_dashboard_summary(days=days)
        auto_rate = self._auto_resolved / max(self._total_handled, 1) * 100
        escalation_rate = self._escalated / max(self._total_handled, 1) * 100
        return {'hub': {'total_messages_handled': self._total_handled, 'auto_resolved': self._auto_resolved, 'escalated': self._escalated, 'auto_resolution_rate': round(auto_rate, 2), 'escalation_rate': round(escalation_rate, 2)}, 'chatbot': chatbot_stats, 'zendesk': zendesk_metrics, 'whatsapp': whatsapp_metrics, 'survey': survey_dashboard}

    def _create_ticket_from_query(self, query: str, user_email: str, user_name: str, chatbot_response: ChatbotResponse, channel: str, transaction_id: str='') -> Optional[Dict[str, Any]]:
        """إنشاء تذكرة Zendesk من استعلام العميل"""
        priority = TicketPriority.HIGH if chatbot_response.should_escalate else TicketPriority.NORMAL
        subject = query[:100] if len(query) <= 100 else query[:97] + '...'
        description_parts = [f'الاستفسار الأصلي: {query}', '', f'القناة: {channel}', f"البريد: {user_email or 'غير محدد'}"]
        if chatbot_response.category:
            description_parts.append(f'التصنيف: {chatbot_response.category}')
        if chatbot_response.source_id:
            description_parts.append(f'أقرب FAQ: {chatbot_response.source_id}')
            description_parts.append(f'نص FAQ: {chatbot_response.source_question}')
        if transaction_id:
            description_parts.append(f'معرف المعاملة: {transaction_id}')
        description_parts.append(f'\nثقة الشات بوت: {chatbot_response.confidence:.2%}')
        if chatbot_response.should_escalate:
            description_parts.append('⚠️ تم التحويل التلقائي — يحتاج وكيل بشري')
        ticket = ZendeskTicket(subject=subject, description='\n'.join(description_parts), requester_email=user_email or 'unknown@example.com', requester_name=user_name, priority=priority, tags=['smart-land', f'channel-{channel}', 'chatbot-escalated' if chatbot_response.should_escalate else 'chatbot-partial'])
        try:
            result = self.zendesk.create_ticket(ticket)
            logger.info(f"Ticket created | external_id={result.get('external_id')} | zendesk_id={result.get('zendesk_id')} | escalated={chatbot_response.should_escalate}")
            return result
        except ZendeskAPIError as e:
            logger.error(f'Failed to create ticket: {e}')
            return None

    def _send_escalation_whatsapp(self, phone_number: str, ticket_id: str, user_name: str) -> None:
        """إرسال إشعار تحويل عبر واتساب"""
        name = user_name or 'العميل'
        message = f'مرحباً {name}،\n\nتم تحويل استفسارك إلى أحد وكلاء الدعم المتخصصين.\nرقم التذكرة: {ticket_id}\nسيتم التواصل معك في أقرب وقت ممكن.\n\nشكراً لصبرك! 🙏'
        try:
            self.whatsapp.send_text(to=phone_number, body=message)
        except Exception as e:
            logger.error(f'Failed to send escalation WhatsApp: {e}')

    def _find_zendesk_id_by_external(self, external_id: str) -> Optional[int]:
        """البحث عن معرف Zendesk بالمعرف الخارجي"""
        if self.zendesk.demo_mode:
            for zid, ticket in self.zendesk._demo_tickets.items():
                if ticket.external_id == external_id:
                    return zid
            return None
        try:
            response = self.zendesk.list_tickets()
            for ticket in response.get('tickets', []):
                if ticket.get('external_id') == external_id:
                    return ticket.get('zendesk_id')
        except Exception:
            pass
        return None

    def run_demo(self) -> Dict[str, Any]:
        """
        تشغيل عرض توضيحي شامل — يختبر جميع المكونات

        Returns:
            ملخص نتائج العرض
        """
        logger.info('=== Starting CustomerService Demo ===')
        demo_queries = [('كيف أبدأ استخدام المنصة؟', 'web'), ('ما هي طرق الدفع المتاحة؟', 'web'), ('كيف يتم تصنيف جودة الأراضي؟', 'web'), ('مشكلة خطيرة في المزاد لا أستطيع تقديم عرض', 'whatsapp'), ('أريد استرداد أموالي فوراً', 'whatsapp'), ('سؤال عن شيء غير موجود في القاعدة', 'web')]
        results = []
        for query, channel in demo_queries:
            response = self.handle_message(query=query, channel=channel, user_email='demo@smartland.eg', user_name='مستخدم تجريبي')
            results.append({'query': query[:50], 'channel': channel, 'auto_resolved': response.auto_resolved, 'escalated': response.escalated, 'ticket_created': response.ticket_created, 'confidence': response.chatbot_confidence})
        survey_results = []
        for i, rating in enumerate([5, 4, 3, 5, 2, 4]):
            sr = self.survey_user(transaction_id=f'TXN-DEMO-{i + 1:03d}', rating=rating, user_email='demo@smartland.eg', channel='web')
            survey_results.append(sr)
        dashboard = self.get_dashboard()
        logger.info('=== Demo Complete ===')
        return {'queries_tested': len(demo_queries), 'query_results': results, 'surveys_recorded': len(survey_results), 'dashboard': dashboard}