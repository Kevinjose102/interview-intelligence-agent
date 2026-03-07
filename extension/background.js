// background.js — Service Worker
// Manages offscreen document lifecycle and relays messages between popup and offscreen

let isRecording = false;

// Listen for messages from popup and offscreen
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  switch (message.type) {
    case "START_CAPTURE":
      // streamId is now provided by popup.js (where user gesture originates)
      handleStartCapture(message.streamId);
      sendResponse({ status: "starting" });
      break;

    case "STOP_CAPTURE":
      handleStopCapture();
      sendResponse({ status: "stopping" });
      break;

    // Popup asks for current recording state on open
    case "GET_STATE":
      sendResponse({ isRecording: isRecording });
      break;

    // Status updates from offscreen document — forward to popup
    case "STATUS_UPDATE":
      chrome.runtime.sendMessage({
        type: "STATUS_UPDATE",
        status: message.status,
        detail: message.detail,
      }).catch(() => {
        // Popup may not be open — ignore
      });
      break;

    case "RECORDING_STOPPED":
      isRecording = false;
      chrome.runtime.sendMessage({
        type: "STATUS_UPDATE",
        status: "stopped",
        detail: "Recording stopped",
      }).catch(() => {});
      break;
  }

  return true; // Keep message channel open for async responses
});

async function handleStartCapture(streamId) {
  try {
    // Close any existing offscreen document to release previous streams
    await closeOffscreenDocument();

    // Create a fresh offscreen document
    await ensureOffscreenDocument();

    // Send streamId to offscreen document to begin recording
    chrome.runtime.sendMessage({
      type: "start-recording",
      target: "offscreen",
      streamId: streamId,
    });

    isRecording = true;
  } catch (error) {
    console.error("Failed to start capture:", error);
    await closeOffscreenDocument().catch(() => {});
    chrome.runtime.sendMessage({
      type: "STATUS_UPDATE",
      status: "error",
      detail: `Failed: ${error.message}`,
    }).catch(() => {});
  }
}

async function handleStopCapture() {
  try {
    chrome.runtime.sendMessage({
      type: "stop-recording",
      target: "offscreen",
    });
  } catch (e) {
    // Offscreen may not exist
  }

  isRecording = false;

  // Close offscreen document after a short delay to allow cleanup
  setTimeout(async () => {
    await closeOffscreenDocument().catch(() => {});
  }, 500);
}

async function ensureOffscreenDocument() {
  const contexts = await chrome.runtime.getContexts({
    contextTypes: ["OFFSCREEN_DOCUMENT"],
    documentUrls: [chrome.runtime.getURL("offscreen.html")],
  });

  if (contexts.length > 0) {
    return;
  }

  await chrome.offscreen.createDocument({
    url: "offscreen.html",
    reasons: ["USER_MEDIA"],
    justification: "Capture tab and microphone audio for transcription",
  });
}

async function closeOffscreenDocument() {
  try {
    const contexts = await chrome.runtime.getContexts({
      contextTypes: ["OFFSCREEN_DOCUMENT"],
      documentUrls: [chrome.runtime.getURL("offscreen.html")],
    });

    if (contexts.length > 0) {
      await chrome.offscreen.closeDocument();
    }
  } catch (e) {
    console.warn("closeOffscreenDocument error (harmless):", e);
  }
}
