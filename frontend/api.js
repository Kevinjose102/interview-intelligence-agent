/**
 * api.js — Thin API client for the Interview Intelligence backend
 */

const BASE = '';

export async function checkHealth() {
  const res = await fetch(`${BASE}/health`);
  return res.json();
}

export async function uploadResume(file) {
  const form = new FormData();
  form.append('file', file);
  const res = await fetch(`${BASE}/resume/upload`, { method: 'POST', body: form });
  return res.json();
}

export async function generateQuestions(profile, transcriptContext = '') {
  const res = await fetch(`${BASE}/resume/questions`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ profile, transcript_context: transcriptContext }),
  });
  return res.json();
}

export async function analyzeConsistency(profile, transcript) {
  const res = await fetch(`${BASE}/analyze/consistency`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ profile, transcript }),
  });
  return res.json();
}

export async function getTranscripts(n = 50) {
  const res = await fetch(`${BASE}/transcripts?n=${n}`);
  return res.json();
}

export async function getSummary() {
  const res = await fetch(`${BASE}/summary`);
  return res.json();
}

export async function getConversations() {
  const res = await fetch(`${BASE}/conversations`);
  return res.json();
}

export async function getConversation(sessionId) {
  const res = await fetch(`${BASE}/conversations/${sessionId}`);
  return res.json();
}

export async function verifyGitHub(profile, transcript = '') {
  const res = await fetch(`${BASE}/verify/github`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ profile, transcript, github_username: profile?.github_username }),
  });
  return res.json();
}

export async function analyzeLatest() {
  const res = await fetch(`${BASE}/analyze_latest`);
  return res.json();
}

export async function postInterviewAnalysis(resumeProfile) {
  const res = await fetch(`${BASE}/post_interview_analysis`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ resume_profile: resumeProfile || null }),
  });
  return res.json();
}

export function subscribeSSE(onMessage) {
  const source = new EventSource(`${BASE}/conversations/stream`);
  source.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      onMessage(data);
    } catch (e) {
      console.error('[SSE] parse error', e);
    }
  };
  source.onerror = () => {
    console.warn('[SSE] connection error — will auto-reconnect');
  };
  return source;
}
