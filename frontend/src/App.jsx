import { useCallback, useEffect, useState } from "react";
import { PipecatClientAudio, PipecatClientProvider } from "@pipecat-ai/client-react";
import { pipecatClient } from "./pipecatClient";
import DoctorsPanel from "./components/DoctorsPanel";
import AppointmentsPanel from "./components/AppointmentsPanel";
import CallPhone from "./components/CallPhone";

const POLL_MS = 3000;

export default function App() {
  const [refreshTick, setRefreshTick] = useState(0);
  const [callOpen, setCallOpen] = useState(false);
  const [latestAppointment, setLatestAppointment] = useState(null);

  useEffect(() => {
    const id = setInterval(() => setRefreshTick((t) => t + 1), POLL_MS);
    return () => clearInterval(id);
  }, []);

  const handleNewAppointment = useCallback((appointment) => {
    setLatestAppointment(appointment);
  }, []);

  return (
    <PipecatClientProvider client={pipecatClient}>
      <div className="app-shell">
        <header className="app-header">
          <div>
            <h1>Aura Clinic</h1>
            <p>Voice appointment desk — live dashboard</p>
          </div>
          <button
            className="try-call-btn"
            onClick={() => {
              setLatestAppointment(null);
              setCallOpen(true);
            }}
          >
            Try Call
          </button>
        </header>

        <main className="dashboard-grid">
          <DoctorsPanel refreshTick={refreshTick} />
          <AppointmentsPanel refreshTick={refreshTick} onNewAppointment={handleNewAppointment} />
        </main>

        <CallPhone
          open={callOpen}
          onClose={() => setCallOpen(false)}
          latestAppointment={latestAppointment}
        />

        <PipecatClientAudio />
      </div>
    </PipecatClientProvider>
  );
}
