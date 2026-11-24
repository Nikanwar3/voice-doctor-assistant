# Aura Clinic — Voice Doctor Appointment Assistant

A voice AI agent that checks doctor availability, books appointments and
cancels appointments over a live phone-style call in the browser, plus a
dashboard to run the call and watch it happen. Built for the SDE Intern Round 1
assignment.

## Stack

| Piece       | Choice                                                            |
| ----------- | ------------------------------------------------------------------ |
| Voice pipeline | [Pipecat](https://github.com/pipecat-ai/pipecat) (Python)        |
| STT / TTS   | ElevenLabs                                                          |
| LLM         | Google Gemini (`GoogleLLMService`, defaults to Gemini's current free-tier flash model — no model string is hardcoded, so it stays current as Google rotates models) |
| Transport   | Pipecat's SmallWebRTC (peer-to-peer, no third-party calling account needed) |
| VAD         | Silero (bonus requirement)                                          |
| Frontend    | React + Vite, official `@pipecat-ai/client-js` / `client-react` SDK |
| Mock data   | SQLite (`backend/clinic.db`, created and seeded automatically)      |

## Architecture

```
Browser (React dashboard)
 ├─ REST polling ──────────────► FastAPI (/api/doctors, /api/appointments) ──► SQLite
 └─ WebRTC call ───────────────► FastAPI (/api/offer) ──► one Pipecat pipeline per call:
                                   caller audio → ElevenLabs STT → Gemini LLM (+ tools)
                                   → ElevenLabs TTS → caller audio
                                   Gemini's tool calls read/write the same SQLite file.
```

Each call gets its own pipeline and conversation history (`server.py` spawns
`run_bot()` as a background task per WebRTC offer). The dashboard and the
voice pipeline are two views onto the same SQLite file — that's what makes a
booking made by voice show up on the dashboard a moment later, and the chosen
bonus tools talk over polling because of a tight deadline rather than needing
a websocket push you can't demo in three minutes.

## Setup

### 1. Get API keys

- **Google Gemini**: free key at https://aistudio.google.com/apikey
- **ElevenLabs**: key at https://elevenlabs.io/app/settings/api-keys (used for
  both STT and TTS)

### 2. Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate        # .venv\Scripts\activate on Windows
pip install -r requirements.txt
cp .env.example .env             # then fill in GOOGLE_API_KEY and ELEVENLABS_API_KEY
python server.py                 # serves on http://localhost:7860
```

### 3. Frontend

```bash
cd frontend
cp .env.example .env             # defaults already point at localhost:7860
npm install
npm run dev                      # opens on http://localhost:5173
```

Open the dashboard, click **Try Call**, allow microphone access, and talk to
Aura. Say a phone number, ask what's available, and book or cancel — the
appointments panel updates within a few seconds.

Three slots are pre-booked under these phone numbers so you can demo the
*cancel* flow immediately without booking first: `9876543210`,
`9123456780`, `9988776655`.

## The three tools

Defined in `backend/tools.py`, registered into the LLM context in
`backend/bot.py`. Pipecat builds each tool's JSON schema straight from the
function's type hints and docstring, so there's no separate schema to keep in
sync with the code:

- **`check_doctor_availability(doctor_name, date)`** — looks up open slots.
  Either field can be `"any"` if the caller has no preference.
- **`book_appointment(phone_number, doctor_name, date, time)`** — books a
  specific open slot under the caller's phone number.
- **`cancel_appointment(phone_number, date)`** — cancels the caller's booked
  appointment, found only by phone number (`date` can be `"any"`).

The system prompt (in `bot.py`) instructs the agent to read the phone number
back in digit groups and get an explicit "yes" before calling `book_appointment`
or `cancel_appointment` — this is prompt-level, not code-enforced, matching
how a real receptionist would confirm it by ear.

Phone numbers are normalized to their last 10 digits in `store.py` so it
doesn't matter whether the caller says them with spaces, dashes, or a country
code — `book_appointment` and `cancel_appointment` always match on the same
normalized form.

## Pipeline description (for the submission form)

> The agent is a single Pipecat pipeline: the browser streams mic audio over
> WebRTC straight into the backend (no telephony provider — Pipecat's
> SmallWebRTC transport handles the peer connection directly), ElevenLabs
> transcribes it, the text goes to Gemini along with the running conversation
> history and three function tools, and Gemini's reply is spoken back through
> ElevenLabs TTS. Silero VAD sits in front of the LLM so it only responds once
> the caller has actually stopped talking. The three tools
> (`check_doctor_availability`, `book_appointment`, `cancel_appointment`) are
> plain Python functions that read and write a small SQLite database of mock
> doctors, slots and appointments; Pipecat auto-generates their JSON schemas
> from type hints and docstrings, so Gemini sees exactly what each tool needs.
> The caller is identified purely by the phone number they say out loud —
> there's no auth — so the system prompt requires the agent to read it back
> and get explicit confirmation before it's allowed to book or cancel
> anything. The React dashboard polls the same database over a small REST API,
> which is how a booking made mid-call shows up live in the appointments list.

Feel free to tighten this further in your own words before submitting — it's
meant as an honest starting draft, not a polished essay.

## Notes / things worth knowing before you're asked about them

- One call = one pipeline instance with its own fresh conversation history;
  nothing about a prior call leaks into the next one.
- Mock data lives in `backend/clinic.db`, created and seeded the first time
  `server.py` or `bot.py` runs. Delete the file to reset to the seed data.
- No API keys are committed — `backend/.env` and `frontend/.env` are
  git-ignored; only the `.env.example` files are tracked.
