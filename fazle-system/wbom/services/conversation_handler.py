# ============================================================
# WBOM — Conversation Handler
# Phase 5 §5.3: Context-aware general/query message handling
# ============================================================
import logging
import re
from datetime import datetime
from typing import Optional

from database import (
    get_row, list_rows, search_rows, execute_query,
)

logger = logging.getLogger("wbom.conversation_handler")


class ConversationHandler:
    """Handle general and query-type messages with context awareness.

    Workflow:
    1. Load conversation context (recent messages, active programs)
    2. Analyze intent (status_query, billing_query, greeting, manual)
    3. Route to appropriate handler
    """

    GREETING_KEYWORDS = [
        "hi", "hello", "hey", "salam", "assalamu",
        "সালাম", "হ্যালো", "good morning", "good evening",
    ]
    STATUS_KEYWORDS = [
        "status", "where", "কোথায়", "কখন", "when",
        "update", "progress", "কি হলো", "খবর",
    ]
    BILLING_KEYWORDS = [
        "bill", "invoice", "payment due", "বিল", "বাকি",
        "outstanding", "due", "হিসাব",
    ]

    def handle_general_message(
        self,
        message_id: int,
        sender_number: str,
        message_body: str,
        contact_id: Optional[int] = None,
    ) -> dict:
        """Main entry point for general/query messages.

        Returns dict with response suggestion and context.
        """
        # Step 1: Load conversation context
        context = self._load_context(sender_number, contact_id)

        # Step 2: Analyze intent
        intent = self._analyze_intent(message_body)

        # Step 3: Route to handler
        response = None
        handler_used = intent

        if intent == "status_query":
            response = self.handle_status_query(
                message_body, contact_id, context
            )
        elif intent == "billing_query":
            response = self.handle_billing_query(contact_id, context)
        elif intent == "greeting":
            response = self.generate_greeting_response(
                contact_id, context
            )
        else:
            # Manual handling required
            response = {
                "suggested_reply": None,
                "note": "Manual response required — no automated handler matched.",
            }

        return {
            "message_id": message_id,
            "classification": "general",
            "intent": intent,
            "handler_used": handler_used,
            "context": {
                "recent_message_count": len(context.get("recent_messages", [])),
                "active_programs": len(context.get("active_programs", [])),
            },
            "response": response,
            "requires_admin_input": intent == "manual",
        }

    def handle_status_query(
        self,
        message_body: str,
        contact_id: Optional[int],
        context: dict,
    ) -> dict:
        """Handle status inquiry messages.

        Looks up active programs and returns status summary.
        """
        active_programs = context.get("active_programs", [])

        if not active_programs:
            return {
                "suggested_reply": "No active escort programs found.",
                "programs": [],
            }

        # Check if query is about a specific vessel
        vessel_name = self._extract_vessel_from_query(message_body)

        if vessel_name:
            matching = [
                p for p in active_programs
                if vessel_name.lower() in (p.get("mother_vessel", "") + " " +
                                           p.get("lighter_vessel", "")).lower()
            ]
            programs = matching if matching else active_programs
        else:
            programs = active_programs

        # Build status summary
        lines = []
        for p in programs[:5]:
            status = p.get("status", "Unknown")
            mv = p.get("mother_vessel", "?")
            lv = p.get("lighter_vessel", "?")
            dest = p.get("destination", "?")
            lines.append(f"MV {mv} / {lv} → {dest}: {status}")

        summary = "\n".join(lines)
        return {
            "suggested_reply": f"Active programs:\n{summary}",
            "programs": programs,
        }

    def handle_billing_query(
        self, contact_id: Optional[int], context: dict
    ) -> dict:
        """Handle billing/invoice inquiry messages."""
        if not contact_id:
            return {
                "suggested_reply": "Contact not identified. Cannot look up billing.",
                "bills": [],
            }

        outstanding = execute_query(
            """
            SELECT b.*, p.mother_vessel, p.lighter_vessel
            FROM wbom_billing_records b
            JOIN wbom_escort_programs p ON b.program_id = p.program_id
            WHERE b.contact_id = %s AND b.payment_status != 'Paid'
            ORDER BY b.bill_date DESC
            LIMIT 10
            """,
            (contact_id,),
        )

        if not outstanding:
            return {
                "suggested_reply": "No outstanding bills found.",
                "bills": [],
            }

        total_due = sum(
            float(b.get("total_amount", 0) or 0) for b in outstanding
        )
        lines = []
        for b in outstanding:
            mv = b.get("mother_vessel", "?")
            amt = b.get("total_amount", 0)
            status = b.get("payment_status", "Pending")
            lines.append(f"  {mv}: {amt}/- ({status})")

        summary = "\n".join(lines)
        return {
            "suggested_reply": (
                f"Outstanding bills ({len(outstanding)}):\n{summary}\n"
                f"Total due: {total_due}/-"
            ),
            "bills": outstanding,
            "total_due": total_due,
        }

    def generate_greeting_response(
        self, contact_id: Optional[int], context: dict
    ) -> dict:
        """Generate a contextual greeting response."""
        greeting = "Assalamu Alaikum"
        contact_name = ""

        if contact_id:
            contact = get_row("wbom_contacts", "contact_id", contact_id)
            if contact:
                contact_name = contact.get("display_name", "")

        active = context.get("active_programs", [])
        if active:
            reply = (
                f"{greeting} {contact_name}.\n"
                f"You have {len(active)} active program(s)."
            )
        else:
            reply = f"{greeting} {contact_name}.\nHow can we assist you today?"

        return {"suggested_reply": reply.strip()}

    # ── Private helpers ───────────────────────────────────────

    def _load_context(
        self, sender_number: str, contact_id: Optional[int]
    ) -> dict:
        """Load conversation context: recent messages + active programs."""
        context = {"recent_messages": [], "active_programs": []}

        # Recent messages from this sender
        try:
            context["recent_messages"] = list_rows(
                "wbom_whatsapp_messages",
                {"sender_number": sender_number},
                order_by="received_at DESC",
                limit=10,
            )
        except Exception as e:
            logger.debug("Failed to load recent messages: %s", e)

        # Active programs for this contact
        if contact_id:
            try:
                context["active_programs"] = execute_query(
                    """
                    SELECT p.*, e.employee_name
                    FROM wbom_escort_programs p
                    LEFT JOIN wbom_employees e
                      ON p.escort_employee_id = e.employee_id
                    WHERE p.contact_id = %s
                      AND p.status IN ('Assigned', 'Running')
                    ORDER BY p.program_date DESC
                    LIMIT 10
                    """,
                    (contact_id,),
                )
            except Exception as e:
                logger.debug("Failed to load active programs: %s", e)

        return context

    def _analyze_intent(self, message_body: str) -> str:
        """Analyze message intent to route to appropriate handler."""
        text = message_body.lower()

        if any(kw in text for kw in self.STATUS_KEYWORDS):
            return "status_query"
        if any(kw in text for kw in self.BILLING_KEYWORDS):
            return "billing_query"
        if any(kw in text for kw in self.GREETING_KEYWORDS):
            return "greeting"

        return "manual"

    @staticmethod
    def _extract_vessel_from_query(message_body: str) -> Optional[str]:
        """Try to extract a vessel name from a status query."""
        patterns = [
            r"(?i)m\.?v\.?\s*([a-zA-Z0-9\u0980-\u09FF\s\-\.]+?)(?=\s*\?|\s*status|\s*কোথায়|$)",
            r"(?i)(?:vessel|জাহাজ)\s+([a-zA-Z0-9\u0980-\u09FF\s\-\.]+?)(?=\s*\?|$)",
        ]
        for pattern in patterns:
            match = re.search(pattern, message_body)
            if match:
                return match.group(1).strip()
        return None
