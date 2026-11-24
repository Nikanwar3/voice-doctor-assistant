import { useEffect, useRef, useState } from "react";
import { fetchAppointments } from "../api";

function formatDateTime(date, time) {
  const d = new Date(date + "T" + time);
  return d.toLocaleString(undefined, {
    weekday: "short",
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

function formatPhone(phone) {
  if (!phone || phone.length !== 10) return phone;
  return `${phone.slice(0, 5)} ${phone.slice(5)}`;
}

export default function AppointmentsPanel({ refreshTick, onNewAppointment }) {
  const [appointments, setAppointments] = useState([]);
  const [flashIds, setFlashIds] = useState(new Set());
  const knownIds = useRef(new Set());
  const isFirstLoad = useRef(true);

  useEffect(() => {
    let cancelled = false;

    fetchAppointments()
      .then((data) => {
        if (cancelled) return;

        const freshIds = data.filter((a) => !knownIds.current.has(a.id));
        if (!isFirstLoad.current && freshIds.length > 0) {
          setFlashIds(new Set(freshIds.map((a) => a.id)));
          freshIds.forEach((a) => onNewAppointment?.(a));
          setTimeout(() => {
            setFlashIds(new Set());
          }, 2200);
        }

        data.forEach((a) => knownIds.current.add(a.id));
        isFirstLoad.current = false;
        setAppointments(data);
      })
      .catch((err) => console.error("Failed to load appointments", err));

    return () => {
      cancelled = true;
    };
  }, [refreshTick, onNewAppointment]);

  return (
    <section className="panel">
      <div className="panel-header">
        <h2>Appointments</h2>
        <span className="panel-subtitle">{appointments.length} total</span>
      </div>

      {appointments.length === 0 ? (
        <p className="empty-state">No appointments yet</p>
      ) : (
        <div className="appointment-table">
          <div className="appointment-row appointment-row-head">
            <span>Phone</span>
            <span>Doctor</span>
            <span>When</span>
            <span>Status</span>
          </div>
          {appointments.map((a) => (
            <div
              key={a.id}
              className={`appointment-row ${flashIds.has(a.id) ? "row-flash" : ""} ${
                a.status === "cancelled" ? "row-cancelled" : ""
              }`}
            >
              <span className="mono">{formatPhone(a.phone_number)}</span>
              <span>
                {a.doctor_name}
                <span className="specialty-inline"> · {a.specialty}</span>
              </span>
              <span>{formatDateTime(a.date, a.time)}</span>
              <span className={`status-badge status-${a.status}`}>{a.status}</span>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
