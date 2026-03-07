// permissions.js — Helper page script to request microphone permission
// Opens in a real tab so Chrome can show the permission prompt

const statusEl = document.getElementById("status");

(async () => {
  try {
    // Request microphone access — Chrome will show the permission prompt
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });

    // Permission granted — release the stream immediately
    stream.getTracks().forEach((track) => track.stop());

    statusEl.textContent = "✅ Microphone access granted! This tab will close shortly...";
    statusEl.className = "status granted";

    // Notify the background/popup that permission is granted
    chrome.runtime.sendMessage({ type: "MIC_PERMISSION_GRANTED" });

    // Close this tab after a brief delay
    setTimeout(() => {
      window.close();
    }, 1500);
  } catch (error) {
    statusEl.textContent = "❌ Microphone access denied. Please try again and click Allow.";
    statusEl.className = "status denied";

    chrome.runtime.sendMessage({ type: "MIC_PERMISSION_DENIED" });
  }
})();
