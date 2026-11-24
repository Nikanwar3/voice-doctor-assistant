import { PipecatClient } from "@pipecat-ai/client-js";
import { SmallWebRTCTransport } from "@pipecat-ai/small-webrtc-transport";

export const BACKEND_URL = import.meta.env.VITE_BACKEND_URL || "http://localhost:7860";

export const pipecatClient = new PipecatClient({
  transport: new SmallWebRTCTransport(),
  enableMic: true,
  enableCam: false,
});

export function connectCall() {
  return pipecatClient.connect({
    webrtcRequestParams: { endpoint: `${BACKEND_URL}/api/offer` },
  });
}

export function disconnectCall() {
  return pipecatClient.disconnect();
}

// A call is "live" for our purposes anywhere between the handshake starting
// and it tearing down — the phone UI uses this to pick ringing vs connected.
export const CONNECTING_STATES = new Set([
  "initializing",
  "initialized",
  "authenticating",
  "authenticated",
  "connecting",
  "connected",
]);
