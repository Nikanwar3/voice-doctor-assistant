"""The three tools the voice agent can call: availability, booking, cancellation.

Pipecat builds each tool's JSON schema automatically from the function's type
hints and its Google-style docstring, so the functions below are plain async
functions — no separate schema object to keep in sync. Each one offloads its
SQLite work to a thread so the pipeline's event loop never blocks on disk I/O.
"""

import asyncio

import store
from loguru import logger
from pipecat.services.llm_service import FunctionCallParams


async def check_doctor_availability(params: FunctionCallParams, doctor_name: str, date: str):
    """Look up a doctor's open appointment slots.

    Args:
        doctor_name: The doctor's name (e.g. "Dr. Mehta") or a specialty (e.g.
            "cardiologist", "dentist"). Pass "any" if the caller has no preference.
        date: The date to check, formatted YYYY-MM-DD. Convert relative terms like
            "today" or "tomorrow" into an actual date yourself before calling this.
            Pass "any" to see all upcoming availability regardless of date.
    """
    logger.info(f"check_doctor_availability(doctor_name={doctor_name!r}, date={date!r})")
    results = await asyncio.to_thread(store.list_available_slots, doctor_name, date)
    if not results:
        await params.result_callback(
            {"found": False, "message": "No matching doctor or no open slots for that date."}
        )
        return
    await params.result_callback({"found": True, "availability": results})


async def book_appointment(
    params: FunctionCallParams, phone_number: str, doctor_name: str, date: str, time: str
):
    """Book an appointment slot for the caller.

    Only call this after you have read the phone number back to the caller
    (grouped digit by digit) and they have explicitly confirmed it is correct.

    Args:
        phone_number: The caller's phone number, exactly as they said it.
        doctor_name: The doctor's name or specialty, matching one from a prior
            availability check.
        date: The appointment date, formatted YYYY-MM-DD.
        time: The appointment time, formatted 24-hour HH:MM (e.g. "14:00").
    """
    logger.info(
        f"book_appointment(phone={phone_number!r}, doctor={doctor_name!r}, "
        f"date={date!r}, time={time!r})"
    )
    result = await asyncio.to_thread(store.book_slot, doctor_name, date, time, phone_number)
    await params.result_callback(result)


async def cancel_appointment(params: FunctionCallParams, phone_number: str, date: str):
    """Cancel the caller's existing appointment, identified only by phone number.

    Only call this after you have read the phone number back to the caller
    (grouped digit by digit) and they have explicitly confirmed it is correct.

    Args:
        phone_number: The caller's phone number, exactly as they said it.
        date: The date of the appointment to cancel, formatted YYYY-MM-DD, if the
            caller mentioned one. Pass "any" to cancel their next upcoming
            appointment regardless of date.
    """
    logger.info(f"cancel_appointment(phone={phone_number!r}, date={date!r})")
    result = await asyncio.to_thread(store.cancel_by_phone, phone_number, date)
    await params.result_callback(result)
