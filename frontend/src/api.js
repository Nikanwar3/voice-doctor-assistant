import { BACKEND_URL } from "./pipecatClient";

export async function fetchDoctors() {
  const res = await fetch(`${BACKEND_URL}/api/doctors`);
  if (!res.ok) throw new Error(`GET /api/doctors failed: ${res.status}`);
  return res.json();
}

export async function fetchDoctorSlots(doctorId) {
  const res = await fetch(`${BACKEND_URL}/api/doctors/${doctorId}/slots`);
  if (!res.ok) throw new Error(`GET /api/doctors/${doctorId}/slots failed: ${res.status}`);
  return res.json();
}

export async function fetchAppointments() {
  const res = await fetch(`${BACKEND_URL}/api/appointments`);
  if (!res.ok) throw new Error(`GET /api/appointments failed: ${res.status}`);
  return res.json();
}
