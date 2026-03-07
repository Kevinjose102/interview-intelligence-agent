# Interview Intelligence Agent — Setup Guide

## Prerequisites

- **Python 3.11+** installed
- **Google Chrome** browser
- **Deepgram API key** — get one free at [deepgram.com](https://console.deepgram.com/signup)

---

## 1. Set the Deepgram API Key

Edit `backend/.env` and replace the placeholder:

```
DEEPGRAM_API_KEY=your_actual_deepgram_api_key
```

---

## 2. Run the FastAPI Backend

```bash
cd backend
python -m venv venv

# Windows
venv\Scripts\activate

# macOS/Linux
# source venv/bin/activate

pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Verify it's running:

```bash
curl http://localhost:8000/health
# Should return: {"status": "ok"}
```

---

## 3. Load the Chrome Extension

1. Open Chrome and go to `chrome://extensions`
2. Enable **Developer mode** (toggle in top-right)
3. Click **Load unpacked**
4. Select the `extension/` folder
5. The "Interview Intelligence" extension should appear with no errors

---

## 4. Test the Full Pipeline

1. **Start the backend** (Step 2 above)
2. **Open a Google Meet call** in Chrome
3. **Click the extension icon** in the toolbar
4. **Click "Start Capture"** — status should show "Capturing"
5. **Speak** — watch the backend terminal for transcript output like:
   ```
   [12.3s] CANDIDATE: Hello, I have experience with Python (confidence: 0.95)
   [15.7s] INTERVIEWER: Tell me about your projects (confidence: 0.97)
   ```
6. **Check transcripts via API:**
   ```bash
   curl http://localhost:8000/transcripts
   ```
7. **Click "Stop Capture"** when done

---

## Project Structure

```
├── backend/
│   ├── main.py              # FastAPI app entrypoint
│   ├── audio_router.py      # WebSocket bridge (Extension ↔ Deepgram)
│   ├── transcript_handler.py # Transcript logging & buffering
│   ├── models.py            # Pydantic data models
│   ├── requirements.txt     # Python dependencies
│   └── .env                 # API keys (not committed)
├── extension/
│   ├── manifest.json        # Chrome Extension manifest
│   ├── background.js        # Service worker
│   ├── offscreen.html/js    # Audio capture & streaming
│   ├── popup.html/js        # Extension popup UI
│   └── icons/               # Extension icons
└── SETUP.md                 # This file
```

---

## Troubleshooting

| Issue                       | Fix                                                      |
| --------------------------- | -------------------------------------------------------- |
| Extension shows "Error"     | Make sure you're on a `meet.google.com` tab              |
| No transcripts appearing    | Check that `DEEPGRAM_API_KEY` is set correctly in `.env` |
| WebSocket connection failed | Ensure the backend is running on `localhost:8000`        |
| Mic permission denied       | Allow microphone access when Chrome prompts              |
