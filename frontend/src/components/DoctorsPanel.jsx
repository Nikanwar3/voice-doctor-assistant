import { useEffect, useState } from "react";
import { fetchDoctors, fetchDoctorSlots } from "../api";

function dateLabel(isoDate) {
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const target = new Date(isoDate + "T00:00:00");
  const diffDays = Math.round((target - today) / 86400000);
  if (diffDays === 0) return "Today";
  if (diffDays === 1) return "Tomorrow";
  return target.toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" });
}

function timeLabel(hhmm) {
  const [h, m] = hhmm.split(":").map(Number);
  const period = h >= 12 ? "PM" : "AM";
  const hour12 = h % 12 === 0 ? 12 : h % 12;
  return `${hour12}:${String(m).padStart(2, "0")} ${period}`;
}

export default function DoctorsPanel({ refreshTick }) {
  const [doctors, setDoctors] = useState([]);
  const [slotsByDoctor, setSlotsByDoctor] = useState({});
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        const docs = await fetchDoctors();
        if (cancelled) return;
        setDoctors(docs);

        const entries = await Promise.all(
          docs.map(async (d) => [d.id, await fetchDoctorSlots(d.id)])
        );
        if (cancelled) return;
        setSlotsByDoctor(Object.fromEntries(entries));
      } catch (err) {
        console.error("Failed to load doctors", err);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    load();
    return () => {
      cancelled = true;
    };
  }, [refreshTick]);

  return (
    <section className="panel">
      <div className="panel-header">
        <h2>Doctors &amp; Availability</h2>
        <span className="panel-subtitle">{doctors.length} on staff</span>
      </div>

      {loading && doctors.length === 0 ? (
        <p className="empty-state">Loading...</p>
      ) : (
        <div className="doctor-list">
          {doctors.map((doc) => {
            const availability = slotsByDoctor[doc.id]?.availability || [];
            const grouped = availability.reduce((acc, s) => {
              (acc[s.date] ||= []).push(s.time);
              return acc;
            }, {});
            const dates = Object.keys(grouped).sort();

            return (
              <article key={doc.id} className="doctor-card">
                <div className="doctor-card-head">
                  <div className="doctor-avatar">{doc.name.replace("Dr. ", "").charAt(0)}</div>
                  <div>
                    <h3>{doc.name}</h3>
                    <span className="specialty-badge">{doc.specialty}</span>
                  </div>
                </div>

                {dates.length === 0 ? (
                  <p className="empty-state subtle">No open slots in the next few days</p>
                ) : (
                  <div className="slot-groups">
                    {dates.map((date) => (
                      <div key={date} className="slot-group">
                        <span className="slot-date">{dateLabel(date)}</span>
                        <div className="slot-chips">
                          {grouped[date].map((t) => (
                            <span key={t} className="slot-chip">
                              {timeLabel(t)}
                            </span>
                          ))}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </article>
            );
          })}
        </div>
      )}
    </section>
  );
}
