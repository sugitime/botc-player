// Injected before page load: expose Dino camera + wire real Pulse mic/speakers.
(() => {
  if (window.__botcMediaPatched) return;
  window.__botcMediaPatched = true;

  const FPS = 15;
  const canvas = document.createElement("canvas");
  canvas.width = 640;
  canvas.height = 640;
  canvas.id = "botc-dino-cam";
  const ctx = canvas.getContext("2d", { alpha: false });
  ctx.fillStyle = "#5aa05a";
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  // Draw a simple face so even without frame pushes something is visible
  ctx.fillStyle = "#3d7a3d";
  ctx.beginPath();
  ctx.ellipse(320, 340, 180, 200, 0, 0, Math.PI * 2);
  ctx.fill();
  ctx.fillStyle = "#f0e68c";
  ctx.beginPath();
  ctx.arc(260, 300, 28, 0, Math.PI * 2);
  ctx.arc(380, 300, 28, 0, Math.PI * 2);
  ctx.fill();
  ctx.fillStyle = "#222";
  ctx.beginPath();
  ctx.arc(260, 300, 12, 0, Math.PI * 2);
  ctx.arc(380, 300, 12, 0, Math.PI * 2);
  ctx.fill();

  let canvasStream = null;
  let videoTrack = null;

  function ensureVideoTrack() {
    if (!canvasStream || videoTrack?.readyState === "ended") {
      canvasStream = canvas.captureStream(FPS);
      videoTrack = canvasStream.getVideoTracks()[0];
      try {
        videoTrack.contentHint = "motion";
      } catch (e) {}
    }
    return videoTrack;
  }

  window.__botcPushFrame = (b64) => {
    const im = new Image();
    im.onload = () => {
      try {
        ctx.drawImage(im, 0, 0, canvas.width, canvas.height);
      } catch (e) {}
    };
    im.src = "data:image/jpeg;base64," + b64;
  };

  const md = navigator.mediaDevices;
  if (!md) return;

  const nativeGUM = md.getUserMedia.bind(md);
  const nativeEnum = md.enumerateDevices.bind(md);
  const nativeED = md.getDisplayMedia ? md.getDisplayMedia.bind(md) : null;

  const DINO_CAM = {
    deviceId: "botc-dino-face",
    groupId: "botc-dino-group",
    kind: "videoinput",
    label: "Dino Face Camera",
    toJSON() {
      return this;
    },
  };

  md.enumerateDevices = async () => {
    let real = [];
    try {
      real = await nativeEnum();
    } catch (e) {
      real = [];
    }
    // After permission, labels populate. Always expose our dino camera.
    const hasDino = real.some(
      (d) => d.deviceId === DINO_CAM.deviceId || (d.kind === "videoinput" && /dino/i.test(d.label || ""))
    );
    const out = real.slice();
    if (!hasDino) out.push({ ...DINO_CAM });
    // Ensure audio devices keep their labels when present
    return out.map((d) => {
      if (d.kind === "audioinput" && !d.label) {
        return Object.assign(Object.create(Object.getPrototypeOf(d)), d, {
          label: d.deviceId?.slice?.(0, 8) === "default" ? "Default Microphone" : "Microphone",
        });
      }
      if (d.kind === "audiooutput" && !d.label) {
        return Object.assign(Object.create(Object.getPrototypeOf(d)), d, {
          label: "Default Speaker",
        });
      }
      return d;
    });
  };

  md.getUserMedia = async (constraints) => {
    constraints = constraints || { audio: true, video: true };
    const wantAudio = !!constraints.audio;
    const wantVideo = !!constraints.video;
    const tracks = [];

    if (wantAudio) {
      try {
        // Prefer default / any real mic (Pulse VirtualMic.monitor is default source in Docker)
        const audioConstraints =
          typeof constraints.audio === "object" && constraints.audio
            ? { ...constraints.audio }
            : true;
        // Drop forced deviceId if it's our fake dino id
        if (audioConstraints && audioConstraints.deviceId) {
          const id = audioConstraints.deviceId.exact || audioConstraints.deviceId.ideal || audioConstraints.deviceId;
          if (id === DINO_CAM.deviceId) delete audioConstraints.deviceId;
        }
        const a = await nativeGUM({ audio: audioConstraints, video: false });
        tracks.push(...a.getAudioTracks());
      } catch (e) {
        console.warn("[botc] audio getUserMedia failed", e);
        // last resort: try unconstrained
        try {
          const a2 = await nativeGUM({ audio: true, video: false });
          tracks.push(...a2.getAudioTracks());
        } catch (e2) {
          console.warn("[botc] audio fallback failed", e2);
        }
      }
    }

    if (wantVideo) {
      // Always serve the dino canvas as the camera, regardless of deviceId
      const vt = ensureVideoTrack();
      if (vt) {
        const clone = vt.clone ? vt.clone() : vt;
        tracks.push(clone);
      }
    }

    if (!tracks.length) {
      return nativeGUM(constraints);
    }
    return new MediaStream(tracks);
  };

  // Warm up permissions so enumerateDevices returns labeled audio devices
  window.__botcWarmMedia = async () => {
    try {
      const s = await nativeGUM({ audio: true, video: false });
      s.getTracks().forEach((t) => t.stop());
    } catch (e) {
      console.warn("[botc] warm audio failed", e);
    }
    try {
      // Also request video once so camera permission is granted
      const vs = new MediaStream([ensureVideoTrack()].filter(Boolean));
      vs.getTracks().forEach((t) => {
        /* keep dino track alive via canvasStream; don't stop the shared track */
      });
    } catch (e) {}
    try {
      return await md.enumerateDevices();
    } catch (e) {
      return [];
    }
  };

  console.info("[botc] media inject active (Dino Face Camera + Pulse audio)");
})();
