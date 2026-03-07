// popup.js — Popup UI controller
// Handles Start/Stop buttons and displays status updates

const startBtn = document.getElementById("startBtn");
const stopBtn = document.getElementById("stopBtn");
const statusDot = document.getElementById("statusDot");
const statusLabel = document.getElementById("statusLabel");
const statusDetail = document.getElementById("statusDetail");

// On popup open, check if we're already recording
chrome.runtime.sendMessage({ type: "GET_STATE" }, (response) => {
  if (response && response.isRecording) {
    startBtn.disabled = true;
    stopBtn.disabled = false;
    updateStatus("capturing", "Capturing", "Recording in progress...");
  }
});

// Start Capture
startBtn.addEventListener("click", async () => {
  try {
    // Query for the active tab — must be a Google Meet tab
    const [tab] = await chrome.tabs.query({
      active: true,
      currentWindow: true,
    });

    if (!tab) {
      updateStatus("error", "Error", "No active tab found");
      return;
    }

    if (!tab.url || !tab.url.includes("meet.google.com")) {
      updateStatus("error", "Error", "Please navigate to a Google Meet tab first");
      return;
    }

    startBtn.disabled = true;
    stopBtn.disabled = false;

    // Check if microphone permission is already granted
    const micPermission = await navigator.permissions.query({ name: "microphone" });

    if (micPermission.state !== "granted") {
      updateStatus("connecting", "Connecting", "Opening mic permission page...");

      // Open helper tab to request mic permission (popups can't show the prompt)
      chrome.tabs.create({
        url: chrome.runtime.getURL("permissions.html"),
        active: true,
      });

      updateStatus("connecting", "Connecting", "Grant mic access in the new tab, then click Start again");
      startBtn.disabled = false;
      stopBtn.disabled = true;
      return;
    }

    updateStatus("connecting", "Connecting", "Capturing tab audio...");

    // Get the tab capture stream ID — user gesture is active
    const streamId = await new Promise((resolve, reject) => {
      chrome.tabCapture.getMediaStreamId({ targetTabId: tab.id }, (id) => {
        if (chrome.runtime.lastError) {
          reject(new Error(chrome.runtime.lastError.message));
        } else {
          resolve(id);
        }
      });
    });

    updateStatus("connecting", "Connecting", "Starting recording...");

    // Send streamId to background to set up offscreen document
    chrome.runtime.sendMessage({
      type: "START_CAPTURE",
      tabId: tab.id,
      streamId: streamId,
    });
  } catch (error) {
    updateStatus("error", "Error", error.message);
    startBtn.disabled = false;
    stopBtn.disabled = true;
  }
});

// Stop Capture
stopBtn.addEventListener("click", () => {
  chrome.runtime.sendMessage({ type: "STOP_CAPTURE" });

  startBtn.disabled = false;
  stopBtn.disabled = true;

  updateStatus("stopped", "Stopped", "Capture ended");
});

// Listen for status updates from background.js
chrome.runtime.onMessage.addListener((message) => {
  if (message.type === "STATUS_UPDATE") {
    const labelText = message.status.charAt(0).toUpperCase() + message.status.slice(1);
    updateStatus(message.status, labelText, message.detail || "");

    if (message.status === "capturing") {
      startBtn.disabled = true;
      stopBtn.disabled = false;
    } else if (message.status === "stopped" || message.status === "error") {
      startBtn.disabled = false;
      stopBtn.disabled = true;
    }
  }
});

function updateStatus(state, label, detail) {
  statusDot.className = `status-dot ${state}`;
  statusLabel.textContent = label;
  statusDetail.textContent = detail;
}
