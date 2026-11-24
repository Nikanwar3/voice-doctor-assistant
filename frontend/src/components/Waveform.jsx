import { useEffect, useRef } from "react";

const BAR_COUNT = 28;

export default function Waveform({ track, active }) {
  const canvasRef = useRef(null);
  const frameRef = useRef(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    const ctx2d = canvas.getContext("2d");

    if (!track || !active) {
      // Idle state: a flat, gently breathing line so the phone doesn't look dead.
      let t = 0;
      const drawIdle = () => {
        t += 0.05;
        ctx2d.clearRect(0, 0, canvas.width, canvas.height);
        const barWidth = canvas.width / BAR_COUNT;
        for (let i = 0; i < BAR_COUNT; i++) {
          const h = 3 + Math.sin(t + i * 0.4) * 2;
          ctx2d.fillStyle = "rgba(255,255,255,0.25)";
          const x = i * barWidth + barWidth * 0.25;
          const y = canvas.height / 2 - h / 2;
          ctx2d.fillRect(x, y, barWidth * 0.5, h);
        }
        frameRef.current = requestAnimationFrame(drawIdle);
      };
      drawIdle();
      return () => cancelAnimationFrame(frameRef.current);
    }

    const audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    const source = audioCtx.createMediaStreamSource(new MediaStream([track]));
    const analyser = audioCtx.createAnalyser();
    analyser.fftSize = 64;
    source.connect(analyser);

    const data = new Uint8Array(analyser.frequencyBinCount);

    const draw = () => {
      analyser.getByteFrequencyData(data);
      ctx2d.clearRect(0, 0, canvas.width, canvas.height);
      const barWidth = canvas.width / BAR_COUNT;
      for (let i = 0; i < BAR_COUNT; i++) {
        const value = data[i % data.length] / 255;
        const h = Math.max(3, value * canvas.height);
        ctx2d.fillStyle = `rgba(110, 231, 183, ${0.4 + value * 0.6})`;
        const x = i * barWidth + barWidth * 0.25;
        const y = canvas.height / 2 - h / 2;
        ctx2d.fillRect(x, y, barWidth * 0.5, h);
      }
      frameRef.current = requestAnimationFrame(draw);
    };
    draw();

    return () => {
      cancelAnimationFrame(frameRef.current);
      source.disconnect();
      audioCtx.close();
    };
  }, [track, active]);

  return <canvas ref={canvasRef} width={280} height={56} className="waveform-canvas" />;
}
