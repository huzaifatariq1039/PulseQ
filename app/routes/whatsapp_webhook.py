import os
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from twilio.twiml.messaging_response import MessagingResponse
from app.database import get_db
from sqlalchemy.orm import Session
from sqlalchemy import or_
from app.db_models import User, Token
# ✅ FIX: send_queue_message is now async — import matches the new signature
from app.services.whatsapp_service import send_queue_message, send_template_message
from app.config import TWILIO_AUTH_TOKEN
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


def _clean_phone(raw: str) -> str:
    """
    Strip the whatsapp: prefix and return a plain E.164 string.
    send_template_message / send_queue_message both add the prefix themselves,
    so we must never pass it in from the outside.
    """
    return raw.replace("whatsapp:", "").strip()


@router.post("/twilio/webhook")
async def twilio_whatsapp_webhook(
    request: Request,
    db: Session = Depends(get_db),
):
    """Twilio WhatsApp Webhook — handles YES / NO replies from patients."""

    signature = request.headers.get("X-Twilio-Signature", "")
    body      = await request.body()

    webhook_url = "https://oyster-app-notep.ondigitalocean.app/api/v1/webhooks/twilio/webhook"
    is_prod     = os.getenv("ENVIRONMENT") == "production"

    if is_prod and signature:
        try:
            from twilio.request_validator import RequestValidator
            from urllib.parse import parse_qs

            validator = RequestValidator(TWILIO_AUTH_TOKEN)
            form_data = {k: v[0] for k, v in parse_qs(body.decode("utf-8")).items()}

            if not validator.validate(webhook_url, form_data, signature):
                logger.warning("Invalid Twilio signature")
                raise HTTPException(status_code=403, detail="Invalid Twilio Signature")
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Signature validation error: {e}")

    from urllib.parse import parse_qs

    form_data = {k: v[0] for k, v in parse_qs(body.decode("utf-8")).items()}

    From = form_data.get("From", "")
    Body = form_data.get("Body", "")

    # ✅ Single, consistent normalisation — clean once, use everywhere
    user_number = _clean_phone(From)   # plain "+923001234567"
    message     = Body.strip().lower()

    digits       = "".join([c for c in user_number if c.isdigit()])
    local_suffix = digits[-10:] if len(digits) >= 10 else digits

    logger.info(f"Incoming Twilio WhatsApp: {user_number} → '{message}'")

    twiml_response = MessagingResponse()

    # Find the latest active (non-cancelled, non-completed) token for this number
    token = (
        db.query(Token)
        .outerjoin(User, Token.patient_id == User.id)
        .filter(
            or_(
                Token.patient_phone.like(f"%{local_suffix}"),
                Token.patient_phone.like(f"%{digits}"),
                User.phone.like(f"%{local_suffix}"),
                User.phone.like(f"%{digits}"),
            )
        )
        .filter(~Token.status.in_(["cancelled", "completed"]))
        .order_by(Token.created_at.desc())
        .first()
    )

    if not token:
        twiml_response.message("You are not registered in any active queue.")
        return Response(content=str(twiml_response), media_type="application/xml")

    now = datetime.utcnow()

    # ── YES ────────────────────────────────────────────────────────────────────
    if message in ["yes", "y"]:
        token.status             = "confirmed"
        token.confirmed          = True
        token.confirmed_at       = now
        token.updated_at         = now
        token.confirmation_status = "confirmed"
        token.queue_opt_in       = True
        token.queue_opted_in_at  = now
        db.commit()

        # Cancel any pending confirmation-reminder jobs
        try:
            from app.services.app_scheduler import get_scheduler

            sch = get_scheduler()
            if sch:
                for job_id in [f"confirm_reminder:{token.id}", f"confirm_final:{token.id}"]:
                    try:
                        sch.remove_job(job_id)
                        logger.info(f"Cancelled scheduled job {job_id} after YES reply")
                    except Exception:
                        pass
        except Exception as e:
            logger.warning(f"Scheduler cleanup failed: {e}")

        try:
            patients_ahead = (
                db.query(Token)
                .filter(
                    Token.doctor_id       == token.doctor_id,
                    Token.hospital_id     == token.hospital_id,
                    Token.appointment_date == token.appointment_date,
                    Token.queue_position  < token.queue_position,
                    Token.status.in_(["waiting", "confirmed"]),
                )
                .count()
            )

            # ✅ FIX: param {{3}} must be a plain number string — NOT "X mins"
            await send_template_message(
                user_number,                            # already clean, no whatsapp: prefix
                "queue_update_alert",
                [
                    token.patient_name or "Patient",    # {{1}} name
                    str(patients_ahead),                # {{2}} patients ahead
                    str(token.estimated_wait_time or 0),# {{3}} wait time — number only
                    token.hospital_name or "Clinic",    # {{4}} hospital
                    str(token.token_number),            # {{5}} token
                ],
            )

            # Schedule all follow-up messages.
            # is_webhook_trigger=True prevents a duplicate token_number confirmation send.
            try:
                from app.services.message_scheduler import schedule_messages

                token_dict = {k: v for k, v in token.__dict__.items() if not k.startswith("_")}
                await schedule_messages(token_dict, is_webhook_trigger=True)
                logger.info(f"Follow-up message sequence scheduled for token {token.id}")
            except Exception as e:
                logger.error(f"Failed to schedule follow-up messages for token {token.id}: {e}")

            # Return empty TwiML — we already sent the reply via the API above
            return Response(content=str(MessagingResponse()), media_type="application/xml")

        except Exception as e:
            logger.error(f"Failed to send queue_update_alert on YES: {e}")
            twiml_response.message("Your appointment is confirmed. We will keep you updated.")
            return Response(content=str(twiml_response), media_type="application/xml")

    # ── NO / CANCEL ────────────────────────────────────────────────────────────
    elif message in ["no", "n", "cancel"]:
        token.status       = "cancelled"
        token.cancelled_at = now
        token.updated_at   = now
        db.commit()

        try:
            from app.services.queue_management_service import QueueManagementService

            await QueueManagementService.recalculate_positions(
                token.doctor_id, token.hospital_id, token.appointment_date
            )
        except Exception as e:
            logger.warning(f"Queue recalculation failed after cancellation: {e}")

        try:
            await send_template_message(
                user_number,                            # already clean
                "cancelled",
                [token.patient_name or "Patient"],
            )
        except Exception as e:
            logger.error(f"Failed to send cancellation message: {e}")
            twiml_response.message("Your appointment has been cancelled. Thank you.")
            return Response(content=str(twiml_response), media_type="application/xml")

        return Response(content=str(MessagingResponse()), media_type="application/xml")

    # ── UNKNOWN ────────────────────────────────────────────────────────────────
    else:
        twiml_response.message("Please reply YES to confirm or NO to cancel.")

    return Response(content=str(twiml_response), media_type="application/xml")