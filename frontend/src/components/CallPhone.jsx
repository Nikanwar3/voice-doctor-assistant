import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  usePipecatClientMediaTrack,
  usePipecatClientMicControl,
  usePipecatClientTransportState,
  usePipecatConversation,
} from "@pipecat-ai/client-react";
import { CONNECTING_STATES, connectCall, disconnectCall } from "../pipecatClient";
import Waveform from "./Waveform";

const FUNCTION_LABELS = {
  check_doctor_availability: "Checking availability",
  book_appointment: "Booking the appointment",
  cancel_appointment: "Cancelling the appointment",
};

function messageText(message) {
  return message.parts
    .map((p) => {
      if (typeof p.text === "string") return p.text;
      if (p.text && typeof p.text === "object") {
        return `${p.text.spoken || ""}${p.text.unspoken || ""}`;
      }
      return "";
    })
    .join(" ")
    .trim();
}

function formatTimer(seconds) {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

// A couple of oscillator beeps — no audio assets to ship or license.
function playTone(ctx, freq, startAt, duration) {
  const osc = ctx.createOscillator();
  const gain = ctx.createGain();
  osc.frequency.value = freq;
  osc.type = "sine";
  gain.gain.setValueAtTime(0, startAt);
  gain.gain.linearRampToValueAtTime(0.15, startAt + 0.02);
  gain.gain.linearRampToValueAtTime(0, startAt + duration);
  osc.connect(gain);
  gain.connect(ctx.destination);
  osc.start(startAt);
  osc.stop(startAt + duration);
}

export default function CallPhone({ open, onClose, latestAppointment }) {
  const transportState = usePipecatClientTransportState();
  const { messages } = usePipecatConversation();
  const { isMicEnabled, enableMic } = usePipecatClientMicControl();
  const botAudioTrack = usePipecatClientMediaTrack("audio", "bot");

  const [seconds, setSeconds] = useState(0);
  const [confirmation, setConfirmation] = useState(null);
  const transcriptRef = useRef(null);
  const audioCtxRef = useRef(null);
  const ringIntervalRef = useRef(null);
  const hasConnectedRef = useRef(false);

  const phase = useMemo(() => {
    if (!open) return "idle";
    if (transportState === "ready") return "connected";
    if (transportState === "disconnected" || transportState === "error") {
      return hasConnectedRef.current ? "ended" : "connecting";
    }
    if (CONNECTING_STATES.has(transportState)) return "connecting";
    return "connecting";
  }, [open, transportState]);

  const getAudioCtx = useCallback(() => {
    if (!audioCtxRef.current) {
      audioCtxRef.current = new (window.AudioContext || window.webkitAudioContext)();
    }
    return audioCtxRef.current;
  }, []);

  // Kick off the WebRTC connection the moment the phone opens.
  useEffect(() => {
    if (open) {
      hasConnectedRef.current = false;
      setSeconds(0);
      setConfirmation(null);
      connectCall().catch((err) => console.error("connect() failed", err));
    }
  }, [open]);

  useEffect(() => {
    if (phase === "connected") hasConnectedRef.current = true;
  }, [phase]);

  // Call timer.
  useEffect(() => {
    if (phase !== "connected") return;
    const id = setInterval(() => setSeconds((s) => s + 1), 1000);
    return () => clearInterval(id);
  }, [phase]);

  // Ringback tone while connecting.
  useEffect(() => {
    if (phase !== "connecting") {
      clearInterval(ringIntervalRef.current);
      return;
    }
    const ctx = getAudioCtx();
    const ring = () => {
      const now = ctx.currentTime;
      playTone(ctx, 440, now, 0.35);
      playTone(ctx, 480, now, 0.35);
    };
    ring();
    ringIntervalRef.current = setInterval(ring, 2000);
    return () => clearInterval(ringIntervalRef.current);
  }, [phase, getAudioCtx]);

  // Short descending tone when the call ends.
  useEffect(() => {
    if (phase !== "ended") return;
    const ctx = getAudioCtx();
    const now = ctx.currentTime;
    playTone(ctx, 500, now, 0.18);
    playTone(ctx, 320, now + 0.18, 0.22);
  }, [phase, getAudioCtx]);

  useEffect(() => {
    if (transcriptRef.current) {
      transcriptRef.current.scrollTop = transcriptRef.current.scrollHeight;
    }
  }, [messages]);

  // Surface a freshly booked/cancelled appointment as a card inside the phone.
  // Deliberately keyed only on latestAppointment itself — if this also
  // depended on `phase`, re-entering "connected" on a *later* call would
  // replay whatever confirmation happened to be left over from an earlier one.
  useEffect(() => {
    if (!latestAppointment) return;
    setConfirmation(latestAppointment);
    const t = setTimeout(() => setConfirmation(null), 4500);
    return () => clearTimeout(t);
  }, [latestAppointment]);

  const handleEndCall = () => {
    disconnectCall();
  };

  const handleClose = () => {
    if (phase === "connected" || phase === "connecting") {
      disconnectCall();
    }
    onClose();
  };

  if (!open) return null;

  const statusText = {
    connecting: "Calling Aura Clinic…",
    connected: "Connected",
    ended: "Call ended",
  }[phase];

  return (
    <div className="phone-overlay" onClick={handleClose}>
      <div className="phone-card" onClick={(e) => e.stopPropagation()}>
        <button className="phone-close" onClick={handleClose} aria-label="Close">
          ×
        </button>

        <div className="phone-header">
          <div className={`phone-avatar ${phase === "connecting" ? "pulsing" : ""}`}>AC</div>
          <h3>Aura Clinic Assistant</h3>
          <p className={`phone-status phone-status-${phase}`}>
            {statusText}
            {phase === "connected" && <span className="phone-timer"> · {formatTimer(seconds)}</span>}
          </p>
        </div>

        <Waveform track={botAudioTrack} active={phase === "connected"} />

        <div className="phone-transcript" ref={transcriptRef}>
          {messages.length === 0 && phase !== "ended" && (
            <p className="transcript-placeholder">
              {phase === "connecting" ? "Connecting…" : "Say hello to get started."}
            </p>
          )}
          {messages
            .filter((m) => m.role !== "system")
            .map((m, i) => {
              if (m.role === "function_call") {
                const label = FUNCTION_LABELS[m.functionCall?.function_name] || "Working on it";
                return (
                  <div key={i} className="transcript-tool-chip">
                    {label}
                    {m.functionCall?.status === "completed" ? " ✓" : "…"}
                  </div>
                );
              }
              const text = messageText(m);
              if (!text) return null;
              return (
                <div
                  key={i}
                  className={`transcript-bubble ${m.role === "user" ? "bubble-user" : "bubble-bot"}`}
                >
                  {text}
                </div>
              );
            })}
        </div>

        {confirmation && (
          <div className={`confirmation-card ${confirmation.status === "cancelled" ? "confirmation-cancelled" : ""}`}>
            <strong>{confirmation.status === "cancelled" ? "Appointment cancelled" : "Appointment booked"}</strong>
            <span>
              {confirmation.doctor_name} · {confirmation.date} at {confirmation.time}
            </span>
          </div>
        )}

        <div className="phone-controls">
          {phase !== "ended" ? (
            <>
              <button
                className={`control-btn ${isMicEnabled ? "" : "control-btn-active"}`}
                onClick={() => enableMic(!isMicEnabled)}
              >
                {isMicEnabled ? "Mute" : "Unmute"}
              </button>
              <button className="control-btn control-btn-end" onClick={handleEndCall}>
                End call
              </button>
            </>
          ) : (
            <button className="control-btn" onClick={handleClose}>
              Close
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
