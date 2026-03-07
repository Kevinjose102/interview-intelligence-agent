// offscreen.js — Dual audio capture and WebSocket streaming
// Captures tab audio (interviewer) and mic audio (candidate),
// streams both to separate backend WebSocket endpoints

const BACKEND_WS_BASE = "ws://localhost:8000/audio_stream";
const RECORDER_TIMESLICE_MS = 250;
const SAMPLE_RATE = 48000;

let tabRecorder = null;
let micRecorder = null;
let tabWs = null;
let micWs = null;
let sessionStart = null;
let tabStream = null;
let micStream = null;
let tabAudioCtx = null;
let micAudioCtx = null;
let playbackAudio = null;

// Listen for messages from background.js
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.type === "start-recording" && message.target === "offscreen") {
    startRecording(message.streamId);
  } else if (message.type === "stop-recording" && message.target === "offscreen") {
    stopRecording();
  }
});

async function startRecording(streamId) {
  try {
    sendStatus("connecting", "Acquiring audio streams...");

    // Simultaneously acquire both streams
    const [acquiredTabStream, acquiredMicStream] = await Promise.all([
      // Tab audio stream (interviewer) — uses the tab capture stream ID
      navigator.mediaDevices.getUserMedia({
        audio: {
          mandatory: {
            chromeMediaSource: "tab",
            chromeMediaSourceId: streamId,
          },
        },
      }),
      // Microphone stream (candidate) — standard mic capture
      navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      }),
    ]);

    // Record session start immediately after both streams resolve
    sessionStart = Date.now();

    tabStream = acquiredTabStream;
    micStream = acquiredMicStream;

    // Play back tab audio so user can still hear the call
    // Use an <audio> element — AudioContext.destination doesn't work in offscreen docs
    playbackAudio = new Audio();
    playbackAudio.srcObject = tabStream;
    playbackAudio.play().catch((e) => console.warn("[offscreen] Playback autoplay blocked:", e));

    // Force mono 48kHz for tab stream via AudioContext
    const monoTabStream = forceMonoStream(tabStream, "tab");

    // Force mono 48kHz for mic stream via AudioContext
    const monoMicStream = forceMonoStream(micStream, "mic");

    // Open WebSocket connections
    // Tab audio = other person on call (candidate)
    // Mic audio = you, the interviewer
    tabWs = createWebSocket("candidate");
    micWs = createWebSocket("interviewer");

    // Wait for both WebSockets to open
    await Promise.all([
      waitForWsOpen(tabWs),
      waitForWsOpen(micWs),
    ]);

    sendStatus("capturing", "Recording in progress...");

    // Create MediaRecorders with opus codec
    tabRecorder = createRecorder(monoTabStream, tabWs, "candidate");
    micRecorder = createRecorder(monoMicStream, micWs, "interviewer");

    // Start recording with 250ms chunks
    tabRecorder.start(RECORDER_TIMESLICE_MS);
    micRecorder.start(RECORDER_TIMESLICE_MS);

    console.log("[offscreen] Recording started for both streams");
  } catch (error) {
    console.error("[offscreen] Failed to start recording:", error);
    sendStatus("error", `Failed: ${error.message}`);
    cleanup();
  }
}

function forceMonoStream(stream, label) {
  const audioCtx = new AudioContext({ sampleRate: SAMPLE_RATE });
  const source = audioCtx.createMediaStreamSource(stream);
  const dest = audioCtx.createMediaStreamDestination();

  // Connect source directly to destination (mono by default with single input)
  source.connect(dest);

  // Store context reference for cleanup
  if (label === "tab") {
    tabAudioCtx = audioCtx;
  } else {
    micAudioCtx = audioCtx;
  }

  return dest.stream;
}

function createWebSocket(speaker) {
  const ws = new WebSocket(`${BACKEND_WS_BASE}/${speaker}`);

  ws.onopen = () => {
    console.log(`[offscreen] WebSocket connected for ${speaker}`);
  };

  ws.onclose = (event) => {
    console.log(`[offscreen] WebSocket closed for ${speaker}: code=${event.code}`);
  };

  ws.onerror = (error) => {
    console.error(`[offscreen] WebSocket error for ${speaker}:`, error);
  };

  return ws;
}

function waitForWsOpen(ws) {
  return new Promise((resolve, reject) => {
    if (ws.readyState === WebSocket.OPEN) {
      resolve();
      return;
    }

    const onOpen = () => {
      ws.removeEventListener("open", onOpen);
      ws.removeEventListener("error", onError);
      resolve();
    };

    const onError = (err) => {
      ws.removeEventListener("open", onOpen);
      ws.removeEventListener("error", onError);
      reject(new Error("WebSocket connection failed"));
    };

    ws.addEventListener("open", onOpen);
    ws.addEventListener("error", onError);
  });
}

function createRecorder(stream, ws, speaker) {
  const recorder = new MediaRecorder(stream, {
    mimeType: "audio/webm;codecs=opus",
  });

  recorder.ondataavailable = async (event) => {
    if (event.data.size === 0) return;
    if (ws.readyState !== WebSocket.OPEN) return;

    // Compute timestamp relative to session start
    const timestamp = (Date.now() - sessionStart) / 1000;

    // Send JSON metadata frame first
    ws.send(JSON.stringify({
      speaker: speaker,
      timestamp: timestamp,
    }));

    // Then send the binary audio chunk
    const buffer = await event.data.arrayBuffer();
    ws.send(buffer);
  };

  recorder.onstop = () => {
    console.log(`[offscreen] MediaRecorder stopped for ${speaker}`);
  };

  return recorder;
}

function stopRecording() {
  console.log("[offscreen] Stopping recording...");

  // Stop MediaRecorders
  if (tabRecorder && tabRecorder.state !== "inactive") {
    tabRecorder.stop();
  }
  if (micRecorder && micRecorder.state !== "inactive") {
    micRecorder.stop();
  }

  cleanup();

  sendStatus("stopped", "Recording stopped");
  chrome.runtime.sendMessage({ type: "RECORDING_STOPPED" });
}

function cleanup() {
  // Close WebSockets
  if (tabWs && tabWs.readyState === WebSocket.OPEN) {
    tabWs.close();
  }
  if (micWs && micWs.readyState === WebSocket.OPEN) {
    micWs.close();
  }

  // Stop all media tracks
  if (tabStream) {
    tabStream.getTracks().forEach((track) => track.stop());
  }
  if (micStream) {
    micStream.getTracks().forEach((track) => track.stop());
  }

  // Close AudioContexts
  if (tabAudioCtx) tabAudioCtx.close().catch(() => {});
  if (micAudioCtx) micAudioCtx.close().catch(() => {});
  if (playbackAudio) {
    playbackAudio.pause();
    playbackAudio.srcObject = null;
  }

  tabRecorder = null;
  micRecorder = null;
  tabWs = null;
  micWs = null;
  tabStream = null;
  micStream = null;
  tabAudioCtx = null;
  micAudioCtx = null;
  playbackAudio = null;
  sessionStart = null;
}

function sendStatus(status, detail) {
  chrome.runtime.sendMessage({
    type: "STATUS_UPDATE",
    status: status,
    detail: detail,
  });
}
