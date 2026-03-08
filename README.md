# Interview Intelligence Agent

![Interview Intelligence Agent](https://img.shields.io/badge/Status-Active-brightgreen) ![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-blue) ![FastAPI](https://img.shields.io/badge/FastAPI-Framework-teal) ![Vite](https://img.shields.io/badge/Vite-Frontend-purple)

The **Interview Intelligence Agent** is an advanced, real-time technical interview assistant. It captures live audio from Google Meet conversations, transcribes it using Deepgram, and leverages powerful LLMs (via Groq/Llama 3) to analyze candidate performance, verify resume claims, and validate technical projects against actual GitHub commit histories.

##  Key Features

* ** Real-Time Transcription:** Seamlessly captures Google Meet audio via a custom Chrome Extension and transcribes it instantly using Deepgram via WebSockets.
* ** LLM Reasoning Engine:** Continuously analyzes the conversation using Llama 3 (via Groq) to evaluate candidate answers, score technical depth, and identify red flags.
* ** Resume Intelligence:** Upload a candidate's PDF resume to automatically extract skills, experience, and project links.
* ** Consistency Analysis:** Cross-references the candidate's spoken answers during the interview against their resume claims in real-time to detect inconsistencies or confirm verified claims.
* ** Dynamic Follow-Up Questions:** Generates highly specific, probing follow-up questions during the interview based on the candidate's resume and the live transcript context.
* ** GitHub Project Verification:** Automatically extracts GitHub links from the resume, finds candidate repositories, and deeply analyzes commit histories (volume, frequency, commit messages, and text content) to generate a "legitimacy score" for their projects.
* ** Post-Interview Report:** Generates a comprehensive summary report immediately after the interview, including overall scores, skill assessments, strengths/weaknesses, and a final hiring recommendation.

---

## 🏗️ Project Architecture

The system is separated into three main components:

### 1. Backend (`backend/`)
A Python **FastAPI** application acting as the core intelligence engine.
* **`main.py`**: Entrypoint containing REST and WebSocket endpoints.
* **`audio_router.py`**: Manages the WebSockets bridging the Chrome Extension audio to Deepgram.
* **`conversation_manager.py`**: Maintains conversation state and real-time messaging context.
* **`llm_reasoning_engine.py`**: Handles AI intelligence workflows via the Groq API.
* **`resume_intelligence/`**: Submodule handling PDF parsing, keyword extraction, and the `github_verifier.py` tool.

### 2. Frontend (`frontend/`)
A fast, **Vite-based Vanilla JavaScript** web dashboard.
* Connects to the backend via Server-Sent Events (SSE) to display real-time metrics, transcripts, candidate profiles, and dynamic UI elements without page refreshes.

### 3. Chrome Extension (`extension/`)
A browser extension designed specifically for Google Meet.
* Uses Manifest V3 and offscreen documents to securely capture tab audio and stream it over WebSockets to the Python backend.

---

## Prerequisites

* **Python 3.11+** installed
* **Node.js** (for running the Vite frontend)
* **Google Chrome** browser
* **Deepgram API Key** ([Get one for free](https://console.deepgram.com/signup))
* **Groq API Key** (For Llama 3 LLM features)
* **GitHub Personal Access Token** (Optional, but highly recommended in `.env` to avoid API rate limits during GitHub verification)

---

## Setup Instructions

### 1. Environment Variables
Create a `.env` file inside the `backend/` directory:
```env
DEEPGRAM_API_KEY=your_deepgram_api_key
GROQ_API_KEY=your_groq_api_key
GITHUB_TOKEN=your_github_pat_token_optional
```

### 2. Start the Backend
Navigate to the `backend/` directory, set up your virtual environment, and run the server:
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
Check if it's running by navigating to `http://localhost:8000/health`.

### 3. Start the Frontend
In a new terminal, navigate to the `frontend/` directory and start the Vite development server:
```bash
cd frontend
npm install
npm run dev
```

### 4. Load the Chrome Extension
1. Open Chrome and navigate to `chrome://extensions`
2. Enable **Developer mode** (toggle in the top right corner).
3. Click **Load unpacked** and select the `extension/` folder from this repository.
4. Pin the "Interview Intelligence" extension to your toolbar.

---

## Usage Guide

1. Ensure both the **Backend** and **Frontend** servers are actively running.
2. Open a **Google Meet** call in Chrome.
3. Click the Interview Intelligence Chrome Extension icon and press **Start Capture**.
4. Speak or have a conversation in the meeting. The audio is securely piped to the backend.
5. Open your Frontend Dashboard (usually `http://localhost:5173`) to view:
   * Live streaming transcripts.
   * Real-time AI consistency analysis.
   * Generated follow-up questions.
6. Upload a Candidate Resume via the dashboard to unlock GitHub verification and resume-based technical probing.
7. Click **Stop Capture** when finished to receive the final AI-generated Post-Interview Analysis Report.

---

## 👥 Contributors

A huge thank you to the brilliant minds who built this project:

* **Alen Saji**
* **athul30**
* **Jovel-J**
* **juanmoncy011**
* **Kevinjose102**

---
*Created during hackathons & late-night coding sessions. Built to make technical interviewing smarter, fairer, and highly automated.*
