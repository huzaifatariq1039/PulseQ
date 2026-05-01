import asyncio
import json
import logging
from functools import partial

from twilio.rest import Client

from app.config import (
    TWILIO_ACCOUNT_SID,
    TWILIO_AUTH_TOKEN,
    TWILIO_WHATSAPP_NUMBER,
    TWILIO_TEMPLATE_SID,
    TWILIO_CALL_ALERT_SID,
    TWILIO_FINAL_ALERT_SID,
    TWILIO_DOCTOR_CHANGE_SID,
    TWILIO_CANCELLED_SID,
    TWILIO_THANKYOU_SID,
    TWILIO_SKIPPED_SID,
    TWILIO_REMINDER_CONFIRM_SID,
    TWILIO_QUEUE_UPDATE_SID,
    TWILIO_TOKEN_NUMBER_SID,
)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def _get_client() -> Client:
    return Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)


def _fmt_phone(phone: str) -> str:
    """
    Normalise any phone string to the whatsapp:+E.164 format that Twilio expects.
    Accepts bare numbers, +E.164, or already-prefixed whatsapp: strings.
    """
    p = phone.strip()
    if p.startswith("whatsapp:"):
        p = p[len("whatsapp:"):]
    if not p.startswith("+"):
        p = f"+{p}"
    return f"whatsapp:{p}"


def _fmt_from() -> str:
    """Return the sender number in whatsapp:+E.164 format."""
    f = (TWILIO_WHATSAPP_NUMBER or "").strip()
    if f.startswith("whatsapp:"):
        return f
    if not f.startswith("+"):
        f = f"+{f}"
    return f"whatsapp:{f}"


async def _send_blocking(fn) -> str | None:
    """
    ✅ FIX (Bug 2): Run a synchronous Twilio client.messages.create() call in a
    thread-pool executor so it never blocks the async event loop.
    """
    loop = asyncio.get_event_loop()
    try:
        msg = await loop.run_in_executor(None, fn)
        return msg.sid
    except Exception as e:
        logger.error(f"Twilio send error: {e}")
        return None


# ─────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────

async def send_queue_message(
    phone: str,
    name: str,
    position: int,
    wait_time: int,
    doctor_name: str = "N/A",
    hospital_name: str = "PulseQ Clinic",
    room_number: str = "Room 1",
) -> str | None:
    """
    Sends the initial booking confirmation WhatsApp message (with YES/NO buttons
    if TWILIO_TEMPLATE_SID is configured, plain text otherwise).

    ✅ FIX (Bug 1 / Bug 2): converted to async; blocking Twilio call offloaded to
    thread executor so it never stalls the event loop.
    """
    if not TWILIO_ACCOUNT_SID or not TWILIO_AUTH_TOKEN:
        logger.warning("Twilio credentials not configured. Skipping WhatsApp message.")
        return None

    if not phone:
        logger.warning("No phone number provided. Skipping WhatsApp message.")
        return None

    client = _get_client()
    to = _fmt_phone(phone)
    from_ = _fmt_from()

    if TWILIO_TEMPLATE_SID:
        fn = partial(
            client.messages.create,
            from_=from_,
            to=to,
            content_sid=TWILIO_TEMPLATE_SID,
            content_variables=json.dumps({
                "1": str(doctor_name),
                "2": str(name),
                "3": str(hospital_name),
                "4": str(room_number),
                "5": str(wait_time),
            }),
        )
        sid = await _send_blocking(fn)
        logger.info(f"WhatsApp template message sent to {to}: SID {sid}")
    else:
        body = (
            f"Apki appointment book ho chuki h!\n\n"
            f"Doctor: {doctor_name}\n"
            f"Patient: {name}\n"
            f"Hospital: {hospital_name}\n"
            f"Room Number: {room_number}\n"
            f"Estimated Time: {wait_time} minutes\n\n"
            f"Reply YES to receive live updates.\n\nPulseQ"
        )
        fn = partial(client.messages.create, from_=from_, to=to, body=body)
        sid = await _send_blocking(fn)
        logger.info(f"WhatsApp text message sent to {to}: SID {sid}")

    return sid


async def send_template_message(phone: str, template_name: str, params: list) -> str | None:
    """
    Sends a named WhatsApp template message via Twilio Content API.

    ✅ FIX (Bug 2): All client.messages.create() calls are now run in a thread
    executor via _send_blocking() — no event-loop blocking.
    ✅ FIX (Bug 3 & 4): patient_call_alert and appointment_doctor_change now have
    proper text fallbacks instead of falling through to the debug string.
    ✅ FIX (Bug 5): Removed the "Template: X | Params: Y" debug fallback — unknown
    template names now log a warning and return None instead of spamming patients.
    """
    if not TWILIO_ACCOUNT_SID or not TWILIO_AUTH_TOKEN:
        logger.warning("Twilio credentials not configured. Skipping template message.")
        return None

    if not phone:
        logger.warning("No phone number provided. Skipping template message.")
        return None

    client = _get_client()
    to = _fmt_phone(phone)
    from_ = _fmt_from()

    def _create(**kwargs) -> str | None:
        """Thin wrapper: schedules the blocking call and returns the coroutine."""
        return partial(client.messages.create, from_=from_, to=to, **kwargs)

    # ── token_number ──────────────────────────────────────────────────────────
    if template_name == "token_number":
        if TWILIO_TOKEN_NUMBER_SID:
            fn = _create(
                content_sid=TWILIO_TOKEN_NUMBER_SID,
                content_variables=json.dumps({
                    "1": str(params[0]) if params else "Doctor",
                    "2": str(params[1]) if len(params) > 1 else "Patient",
                    "3": str(params[2]) if len(params) > 2 else "Clinic",
                    "4": str(params[3]) if len(params) > 3 else "General",
                    "5": str(params[4]) if len(params) > 4 else "0",
                }),
            )
        else:
            body = (
                f"Apki appointment book ho chuki h!\n\n"
                f"Doctor: {params[0] if params else 'Doctor'}\n"
                f"Patient: {params[1] if len(params) > 1 else 'Patient'}\n"
                f"Hospital: {params[2] if len(params) > 2 else 'Clinic'}\n"
                f"Department: {params[3] if len(params) > 3 else 'General'}\n"
                f"Estimated Time: {params[4] if len(params) > 4 else '0'} minutes\n\n"
                f"Reply YES to receive live updates.\n\nPulseQ"
            )
            fn = _create(body=body)
        return await _send_blocking(fn)

    # ── patient_call_alert ────────────────────────────────────────────────────
    if template_name == "patient_call_alert":
        if TWILIO_CALL_ALERT_SID:
            fn = _create(
                content_sid=TWILIO_CALL_ALERT_SID,
                content_variables=json.dumps({
                    "1": str(params[0]) if params else "Patient",
                }),
            )
        else:
            # ✅ FIX (Bug 3): proper fallback — was silently falling through before
            patient_name = str(params[0]) if params else "Patient"
            body = (
                f"Dear {patient_name},\n\n"
                f"Aapki turn aa gayi hai. Meherbani karke doctor ke room mein tashreef le jayein.\n\n"
                f"PulseQ"
            )
            fn = _create(body=body)
        return await _send_blocking(fn)

    # ── final_alert ───────────────────────────────────────────────────────────
    if template_name == "final_alert":
        if TWILIO_FINAL_ALERT_SID:
            fn = _create(
                content_sid=TWILIO_FINAL_ALERT_SID,
                content_variables=json.dumps({
                    "1": str(params[0]) if params else "Patient",
                    "2": str(params[1]) if len(params) > 1 else "",
                }),
            )
        else:
            patient_name = str(params[0]) if params else "Patient"
            token_number = str(params[1]) if len(params) > 1 else ""
            body = (
                f"Hello {patient_name},\n\n"
                f"Aapki turn kisi bhi waqt aa sakti hai. Please hospital ki taraf rawana ho jayein.\n\n"
                f"Aapka token number {token_number} hai.\n\n"
                f"Kindly arrive on time.\n\nPulseQ"
            )
            fn = _create(body=body)
        return await _send_blocking(fn)

    # ── appointment_doctor_change ─────────────────────────────────────────────
    if template_name == "appointment_doctor_change":
        if TWILIO_DOCTOR_CHANGE_SID:
            fn = _create(
                content_sid=TWILIO_DOCTOR_CHANGE_SID,
                content_variables=json.dumps({
                    "1": str(params[0]) if params else "Patient",
                    "2": str(params[1]) if len(params) > 1 else "",
                    "3": str(params[2]) if len(params) > 2 else "",
                    "4": str(params[3]) if len(params) > 3 else "https://pulseq.blog/",
                }),
            )
        else:
            # ✅ FIX (Bug 4): proper fallback — was silently falling through before
            patient_name = str(params[0]) if params else "Patient"
            old_doctor  = str(params[1]) if len(params) > 1 else "your previous doctor"
            new_doctor  = str(params[2]) if len(params) > 2 else "a new doctor"
            booking_url = str(params[3]) if len(params) > 3 else "https://pulseq.blog/"
            body = (
                f"Dear {patient_name},\n\n"
                f"Aapki appointment mein tabdeeli aayi hai.\n"
                f"Pehle doctor: {old_doctor}\n"
                f"Naye doctor: {new_doctor}\n\n"
                f"Mazeed maloomat ke liye yahan visit karein: {booking_url}\n\n"
                f"PulseQ"
            )
            fn = _create(body=body)
        return await _send_blocking(fn)

    # ── cancelled ─────────────────────────────────────────────────────────────
    if template_name == "cancelled":
        if TWILIO_CANCELLED_SID:
            fn = _create(
                content_sid=TWILIO_CANCELLED_SID,
                content_variables=json.dumps({
                    "1": str(params[0]) if params else "Patient",
                }),
            )
        else:
            patient_name = str(params[0]) if params else "Patient"
            body = (
                f"Hello {patient_name},\n\n"
                f"Aapki appointment cancel ho chuki hai.\n\n"
                f"Agr ap dobara book krna chahte hain to is website ka through book kr skte hain: https://pulseq.blog/\n"
                f"Ya Hospital reception sa rabta karein.\n\nThankyou\n\nPulseQ"
            )
            fn = _create(body=body)
        return await _send_blocking(fn)

    # ── template (thank-you) ──────────────────────────────────────────────────
    if template_name == "template":
        if TWILIO_THANKYOU_SID:
            fn = _create(content_sid=TWILIO_THANKYOU_SID)
        else:
            body = (
                "Thankyou for visiting PulseQ.\n\n"
                "For future appointments use this link:\nhttps://pulseq.blog/\n\n"
                "Did you like our service?\n\n"
                "(Reply with one of the options below)\n"
                "1. Yes, It was Great\n"
                "2. No, I didn't like it"
            )
            fn = _create(body=body)
        return await _send_blocking(fn)

    # ── skipped ───────────────────────────────────────────────────────────────
    if template_name == "skipped":
        if TWILIO_SKIPPED_SID:
            fn = _create(
                content_sid=TWILIO_SKIPPED_SID,
                content_variables=json.dumps({
                    "1": str(params[0]) if params else "Patient",
                    "2": str(params[1]) if len(params) > 1 else "",
                }),
            )
        else:
            patient_name = str(params[0]) if params else "Patient"
            token_number = str(params[1]) if len(params) > 1 else ""
            body = (
                f"Hello {patient_name},\n\n"
                f"Lagta hai ke aap apni scheduled appointment miss kar chuke hain. "
                f"Aapka token number {token_number} tha.\n\n"
                f"Kindly jald az jald hospital reception se rabta karein taake aap apni "
                f"appointment reschedule kar saken ya mazeed madad le saken.\n\n"
                f"Thank you for your attention.\n\nPulseQ"
            )
            fn = _create(body=body)
        return await _send_blocking(fn)

    # ── reminder_for_confirmation ─────────────────────────────────────────────
    if template_name == "reminder_for_confirmation":
        if TWILIO_REMINDER_CONFIRM_SID:
            fn = _create(content_sid=TWILIO_REMINDER_CONFIRM_SID)
        else:
            body = (
                "Aapki appointment ke liye koi response receive nahi hua.\n\n"
                "Reply YES karein updates confirm karne ke liye aur NO karein cancel karne ke liye."
            )
            fn = _create(body=body)
        return await _send_blocking(fn)

    # ── queue_update_alert ────────────────────────────────────────────────────
    if template_name == "queue_update_alert":
        if TWILIO_QUEUE_UPDATE_SID:
            fn = _create(
                content_sid=TWILIO_QUEUE_UPDATE_SID,
                content_variables=json.dumps({
                    "1": str(params[0]) if params else "Patient",
                    "2": str(params[1]) if len(params) > 1 else "0",
                    "3": str(params[2]) if len(params) > 2 else "0",
                    "4": str(params[3]) if len(params) > 3 else "Clinic",
                    "5": str(params[4]) if len(params) > 4 else "Token",
                }),
            )
        else:
            patient_name  = str(params[0]) if params else "Patient"
            ahead         = str(params[1]) if len(params) > 1 else "0"
            wait          = str(params[2]) if len(params) > 2 else "0"
            hospital      = str(params[3]) if len(params) > 3 else "Clinic"
            token_display = str(params[4]) if len(params) > 4 else "Token"
            body = (
                f"Dear {patient_name},\n\n"
                f"Aapki turn qareeb aa rahi hai. Aap se pehle {ahead} patients hain. "
                f"Taqreeban wait {wait} minutes hai. Please {hospital} ki taraf chle jayein.\n"
                f"Token: {token_display}\n\n"
                f"Kindly tayar rhein.\n\nPulseQ"
            )
            fn = _create(body=body)
        return await _send_blocking(fn)

    # ── unknown template ──────────────────────────────────────────────────────
    # ✅ FIX (Bug 5): Log a warning instead of sending a raw debug string to the patient
    logger.warning(f"send_template_message: unknown template_name '{template_name}' — message not sent.")
    return None