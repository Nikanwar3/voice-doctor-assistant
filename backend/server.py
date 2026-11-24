"""FastAPI server: WebRTC signaling for the voice agent + REST API for the dashboard.

Both halves share the same SQLite file (store.py). The voice pipeline writes to
it via the tool functions in tools.py; the dashboard reads it through the REST
routes below. Polling the REST routes from the frontend is what makes booked/
cancelled appointments show up on the dashboard during a live call.
"""

import argparse
import sys
from contextlib import asynccontextmanager

import store
import uvicorn
from bot import run_bot
from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
from pipecat.transports.smallwebrtc.request_handler import (
    SmallWebRTCPatchRequest,
    SmallWebRTCRequest,
    SmallWebRTCRequestHandler,
)

load_dotenv(override=True)
store.init_db()

small_webrtc_handler = SmallWebRTCRequestHandler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await small_webrtc_handler.close()


app = FastAPI(title="Voice Doctor Appointment Assistant", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/api/offer")
async def offer(request: SmallWebRTCRequest, background_tasks: BackgroundTasks):
    """WebRTC SDP offer/answer exchange. Launches one bot run per call."""

    async def webrtc_connection_callback(connection):
        background_tasks.add_task(run_bot, connection)

    return await small_webrtc_handler.handle_web_request(
        request=request,
        webrtc_connection_callback=webrtc_connection_callback,
    )


@app.patch("/api/offer")
async def ice_candidate(request: SmallWebRTCPatchRequest):
    await small_webrtc_handler.handle_patch_request(request)
    return {"status": "success"}


@app.get("/api/doctors")
def get_doctors():
    return store.list_doctors()


@app.get("/api/doctors/{doctor_id}/slots")
def get_doctor_slots(doctor_id: int):
    doctors = {d["id"]: d for d in store.list_doctors()}
    doctor = doctors.get(doctor_id)
    if not doctor:
        return {"doctor": None, "availability": []}
    availability = store.list_available_slots(doctor["name"], "any")
    return {"doctor": doctor, "availability": availability[0]["slots"] if availability else []}


@app.get("/api/appointments")
def get_appointments():
    return store.list_appointments()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Voice doctor appointment assistant server")
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=7860)
    parser.add_argument("--verbose", "-v", action="count")
    args = parser.parse_args()

    logger.remove(0)
    logger.add(sys.stderr, level="TRACE" if args.verbose else "DEBUG")

    uvicorn.run(app, host=args.host, port=args.port)
