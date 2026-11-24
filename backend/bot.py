"""The Pipecat voice pipeline: caller audio -> STT -> LLM -> TTS -> caller audio.

One run_bot() call handles one phone call end to end. server.py spawns a fresh
call of this function per WebRTC connection, so each call gets its own
pipeline, LLM context and conversation history.
"""

import os
from datetime import datetime

import aiohttp
import store
from dotenv import load_dotenv
from loguru import logger
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.frames.frames import LLMRunFrame, TTSSpeakFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineParams, PipelineWorker, ProcessorUnusablePolicy
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.services.elevenlabs.stt import ElevenLabsSTTService
from pipecat.services.elevenlabs.tts import ElevenLabsTTSService
from pipecat.services.google.llm import GoogleLLMService
from pipecat.transports.base_transport import TransportParams
from pipecat.transports.smallwebrtc.connection import SmallWebRTCConnection
from pipecat.transports.smallwebrtc.transport import SmallWebRTCTransport
from pipecat.workers.runner import WorkerRunner

from tools import book_appointment, cancel_appointment, check_doctor_availability

load_dotenv(override=True)

store.init_db()

SYSTEM_PROMPT = f"""\
You are Aura, the voice receptionist for Aura Clinic. You speak with callers on
the phone to check doctor availability, book appointments and cancel appointments.

Today's date is {datetime.now().date().isoformat()}. If the caller says a relative
date like "today" or "tomorrow", convert it to an actual YYYY-MM-DD date yourself
before calling any tool — tools only accept exact dates (or "any").

The clinic has these doctors: {", ".join(f"{n} ({s})" for n, s in store.DOCTORS)}.

Rules you must always follow:
- The caller is identified only by the phone number they say out loud. There is
  no login and no caller ID, so you must always ask for it before booking or
  cancelling anything.
- Before calling book_appointment or cancel_appointment, repeat the phone number
  back to the caller in small groups of digits (e.g. "that's 9-8-7-6, 5-4-3-2-1-0,
  is that right?") and wait for them to explicitly confirm it. Never call those
  two tools without that confirmation.
- When checking availability, if the caller has no preference for doctor or date,
  pass "any" for that field rather than guessing.
- Always check availability before booking, unless the caller already told you an
  exact date and time to book.
- Keep responses short and conversational — you are being heard, not read. Never
  use emojis, asterisks, bullet points, or any text formatting; spell out times
  naturally (e.g. "two thirty PM") even though you pass 24-hour HH:MM to tools.
- If a tool reports an error (slot unavailable, doctor not found, no appointment
  found to cancel), explain that plainly to the caller and offer a next step —
  don't expose raw error codes.
"""


async def run_bot(webrtc_connection: SmallWebRTCConnection):
    logger.info("Starting bot for new call")

    async with aiohttp.ClientSession() as session:
        transport = SmallWebRTCTransport(
            webrtc_connection=webrtc_connection,
            params=TransportParams(
                audio_in_enabled=True,
                audio_out_enabled=True,
            ),
        )

        stt = ElevenLabsSTTService(
            api_key=os.environ["ELEVENLABS_API_KEY"],
            aiohttp_session=session,
        )

        tts = ElevenLabsTTSService(
            api_key=os.environ["ELEVENLABS_API_KEY"],
            settings=ElevenLabsTTSService.Settings(
                voice=os.environ.get("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM"),
                model="eleven_flash_v2_5",
            ),
        )

        llm = GoogleLLMService(
            api_key=os.environ["GOOGLE_API_KEY"],
            settings=GoogleLLMService.Settings(system_instruction=SYSTEM_PROMPT),
        )

        @llm.event_handler("on_function_calls_started")
        async def on_function_calls_started(service, function_calls):
            await tts.queue_frame(TTSSpeakFrame("Sure, one moment."))

        context = LLMContext(
            tools=[check_doctor_availability, book_appointment, cancel_appointment]
        )
        user_aggregator, assistant_aggregator = LLMContextAggregatorPair(
            context,
            user_params=LLMUserAggregatorParams(vad_analyzer=SileroVADAnalyzer()),
        )

        pipeline = Pipeline(
            [
                transport.input(),
                stt,
                user_aggregator,
                llm,
                tts,
                transport.output(),
                assistant_aggregator,
            ]
        )

        worker = PipelineWorker(
            pipeline,
            params=PipelineParams(
                enable_metrics=True,
                enable_usage_metrics=True,
            ),
            processor_unusable_policy=ProcessorUnusablePolicy.END,
        )

        runner = WorkerRunner(handle_sigint=False)
        await runner.add_workers(worker)

        @transport.event_handler("on_client_connected")
        async def on_client_connected(transport, client):
            logger.info("Caller connected")
            context.add_message(
                {
                    "role": "developer",
                    "content": "Greet the caller, introduce yourself as Aura from Aura "
                    "Clinic, and ask how you can help.",
                }
            )
            await worker.queue_frames([LLMRunFrame()])

        @transport.event_handler("on_client_disconnected")
        async def on_client_disconnected(transport, client):
            logger.info("Caller disconnected")
            await runner.cancel()

        await runner.run()
