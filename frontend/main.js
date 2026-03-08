/**
 * main.js — InterviewIQ Dashboard (Industry-Level)
 */

import {
  uploadResume,
  generateQuestions,
  analyzeConsistency,
  analyzeLatest,
  postInterviewAnalysis,
  subscribeSSE,
  getConversations,
  getConversation,
} from './api.js';

/* ──────── STATE ──────── */
const state = {
  resumeProfile: null,
  transcriptMessages: [],
  sseSource: null,
  currentSessionId: null,
  currentView: 'dashboard',
  questionsData: [],
  consistencyData: null,
};

/* ──────── SELECTORS ──────── */
const $ = (s) => document.querySelector(s);
const $$ = (s) => document.querySelectorAll(s);

/* ──────── BOOT ──────── */
document.addEventListener('DOMContentLoaded', () => {
  initLandingPage();
  initClock();
  initNavigation();
  initSidebarToggle();
  initUploadZone();
  initButtons();
  initExport();
  initKeyboardShortcuts();
  initSSE();
  initSkillConfidence();
  initReport();
  loadExistingConversations();
  initHealthCheck();
  startAnalyzeLatestPolling();
});

/* ================================================================
   LANDING PAGE
   ================================================================ */
function initLandingPage() {
  const landing = document.getElementById('landing-page');
  if (!landing) return;

  const enterApp = () => {
    landing.classList.add('hidden');
  };

  // All CTA buttons
  ['landing-cta-nav', 'landing-cta-hero', 'landing-cta-footer'].forEach((id) => {
    const btn = document.getElementById(id);
    if (btn) btn.addEventListener('click', enterApp);
  });
}

/* ================================================================
   NAVIGATION
   ================================================================ */
function initNavigation() {
  $$('.nav-item').forEach((btn) => {
    btn.addEventListener('click', () => {
      const panel = btn.dataset.panel;
      switchView(panel);
    });
  });
}

function switchView(viewId) {
  // Update nav items
  $$('.nav-item').forEach((n) => n.classList.remove('active'));
  const navBtn = $(`[data-panel="${viewId}"]`);
  if (navBtn) navBtn.classList.add('active');

  // Update views
  $$('.view').forEach((v) => v.classList.remove('active'));
  const view = $(`#view-${viewId}`);
  if (view) view.classList.add('active');

  // Update breadcrumb
  const names = {
    dashboard: 'Dashboard',
    resume: 'Resume Analysis',
    questions: 'Follow-up Questions',
    transcript: 'Live Transcript',
    consistency: 'Consistency Analysis',
    report: 'Post-Interview Report',
    history: 'Session History',
    settings: 'Settings',
  };
  $('#breadcrumb-page').textContent = names[viewId] || viewId;

  // Load history on navigation
  if (viewId === 'history') loadHistoryView();
  // Sync settings status
  if (viewId === 'settings') syncSettingsStatus();
  state.currentView = viewId;
}

/* ================================================================
   SIDEBAR TOGGLE
   ================================================================ */
function initSidebarToggle() {
  $('#sidebar-toggle').addEventListener('click', () => {
    const sidebar = $('#sidebar');
    const main = $('#main-wrapper');
    sidebar.classList.toggle('collapsed');
    main.classList.toggle('expanded');
    // Mobile
    sidebar.classList.toggle('mobile-open');
  });
}

/* ================================================================
   CLOCK
   ================================================================ */
function initClock() {
  const el = $('#topbar-clock');
  const tick = () => {
    el.textContent = new Date().toLocaleTimeString('en-US', {
      hour: '2-digit', minute: '2-digit', second: '2-digit',
    });
  };
  tick();
  setInterval(tick, 1000);
}

/* ================================================================
   UPLOAD ZONE
   ================================================================ */
function initUploadZone() {
  const zone = $('#upload-zone');
  const input = $('#resume-file-input');
  const browseBtn = $('#upload-browse-btn');

  zone.addEventListener('click', (e) => {
    if (e.target !== browseBtn && !browseBtn.contains(e.target)) {
      input.click();
    }
  });
  browseBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    input.click();
  });

  zone.addEventListener('dragover', (e) => { e.preventDefault(); zone.classList.add('dragover'); });
  zone.addEventListener('dragleave', () => zone.classList.remove('dragover'));
  zone.addEventListener('drop', (e) => {
    e.preventDefault();
    zone.classList.remove('dragover');
    if (e.dataTransfer.files[0]) handleResumeUpload(e.dataTransfer.files[0]);
  });
  input.addEventListener('change', () => {
    if (input.files[0]) handleResumeUpload(input.files[0]);
  });
}

async function handleResumeUpload(file) {
  if (!file.name.toLowerCase().endsWith('.pdf')) {
    showToast('Only PDF files are supported', 'error');
    return;
  }

  // Show loading
  $('#upload-card').classList.add('hidden');
  $('#resume-loading-card').classList.remove('hidden');

  try {
    const result = await uploadResume(file);
    if (result.error) throw new Error(result.error);

    state.resumeProfile = result.profile;
    renderResumeProfile(result.profile);
    updateDashboardResumePreview(result.profile);

    // Render deep analysis if available
    if (result.deep_analysis) {
      renderDeepAnalysis(result.deep_analysis);
    }

    showToast('Resume analyzed successfully!', 'success');

    // Enable dependent buttons
    $('#btn-generate-questions').disabled = false;
    updateAnalyzeButton();

    // Update stats
    $('#stat-resume').textContent = 'Parsed';
    $('#stat-resume').style.color = 'var(--emerald)';
    $('#resume-pill').textContent = 'Parsed';
    $('#resume-pill').classList.add('active');
  } catch (err) {
    showToast(`Upload failed: ${err.message}`, 'error');
    $('#upload-card').classList.remove('hidden');
  } finally {
    $('#resume-loading-card').classList.add('hidden');
  }
}

function renderResumeProfile(profile) {
  // Skills
  const skillsEl = $('#resume-skills');
  skillsEl.innerHTML = '';
  const skills = profile.skills || [];
  skills.forEach((s, i) => {
    const tag = document.createElement('span');
    tag.className = 'skill-tag';
    tag.textContent = s;
    tag.style.animationDelay = `${i * 0.04}s`;
    skillsEl.appendChild(tag);
  });
  $('#skill-count').textContent = skills.length;
  $('#resume-skills-card').classList.remove('hidden');

  // Projects
  const projEl = $('#resume-projects');
  projEl.innerHTML = '';
  const projects = profile.projects || [];
  projects.forEach((p) => {
    const card = document.createElement('div');
    card.className = 'project-card';
    card.innerHTML = `
      <div class="project-card-title">${esc(p.name)}</div>
      ${p.description ? `<div class="project-card-desc">${esc(p.description)}</div>` : ''}
      <div class="project-card-tech">
        ${(p.technologies || []).map((t) => `<span class="tech-tag">${esc(t)}</span>`).join('')}
      </div>`;
    projEl.appendChild(card);
  });
  $('#project-count').textContent = projects.length;
  $('#resume-projects-card').classList.remove('hidden');

  // Experience
  const expEl = $('#resume-experience');
  expEl.innerHTML = '';
  const exps = profile.experience || [];
  exps.forEach((e) => {
    const it = document.createElement('div');
    it.className = 'exp-item';
    it.textContent = e;
    expEl.appendChild(it);
  });
  $('#exp-count').textContent = exps.length;
  $('#resume-exp-card').classList.remove('hidden');
}

function updateDashboardResumePreview(profile) {
  const el = $('#dash-resume-preview');
  const skills = (profile.skills || []).slice(0, 8);
  el.innerHTML = `
    <div class="tag-cloud" style="margin-bottom:12px">
      ${skills.map((s) => `<span class="skill-tag">${esc(s)}</span>`).join('')}
      ${profile.skills && profile.skills.length > 8 ? `<span class="skill-tag" style="opacity:0.5">+${profile.skills.length - 8} more</span>` : ''}
    </div>
    <p class="text-sm text-muted">${(profile.projects || []).length} projects · ${(profile.experience || []).length} experience entries</p>
  `;
}

/* ================================================================
   DEEP ANALYSIS RENDERING
   ================================================================ */
function renderDeepAnalysis(analysis) {
  if (!analysis) return;

  // Show divider
  const divider = $('#analysis-divider');
  if (divider) divider.classList.remove('hidden');

  // ── 1. Overall Quality Score Ring ──
  const qualityCard = $('#resume-quality-card');
  const qualityBody = $('#resume-quality-body');
  if (qualityCard && qualityBody) {
    const score = analysis.overall_score || 0;
    const verdict = analysis.overall_verdict || 'Unknown';
    let color = 'var(--emerald)';
    if (score < 40) color = 'var(--rose)';
    else if (score < 70) color = 'var(--amber)';

    const circ = 2 * Math.PI * 42;
    const offset = circ - (score / 100) * circ;

    qualityBody.innerHTML = `
      <div class="analysis-score-hero">
        <div class="score-ring-wrapper">
          <svg width="100" height="100" viewBox="0 0 100 100">
            <circle class="score-ring-bg" cx="50" cy="50" r="42"/>
            <circle class="score-ring-fill" cx="50" cy="50" r="42"
              stroke="${color}" stroke-dasharray="${circ}" stroke-dashoffset="${offset}"/>
          </svg>
          <div class="score-ring-num" style="color:${color}">${score}</div>
        </div>
        <div class="analysis-score-info">
          <div class="analysis-score-verdict" style="color:${color}">${esc(verdict)}</div>
          <div class="analysis-score-desc">Overall Resume Quality Score</div>
        </div>
      </div>`;
    qualityCard.classList.remove('hidden');
  }

  // ── 2. Career Trajectory ──
  const trajCard = $('#resume-trajectory-card');
  const trajBody = $('#resume-trajectory-body');
  if (trajCard && trajBody) {
    const anomalies = analysis.trajectory_anomalies || [];
    const summary = analysis.trajectory_summary || '';
    $('#trajectory-count').textContent = anomalies.length;

    if (anomalies.length === 0) {
      trajBody.innerHTML = `<div class="analysis-ok"><span class="analysis-ok-icon">✓</span> ${esc(summary) || 'No career trajectory anomalies detected.'}</div>`;
    } else {
      trajBody.innerHTML = `
        ${summary ? `<div class="analysis-summary">${esc(summary)}</div>` : ''}
        <div class="analysis-items">
          ${anomalies.map((a, i) => `
            <div class="analysis-item severity-${a.severity || 'medium'}" style="animation-delay:${i * 0.05}s">
              <div class="analysis-item-header">
                <span class="severity-badge ${a.severity || 'medium'}">${esc((a.anomaly_type || 'unknown').replace(/_/g, ' '))}</span>
                ${a.time_period ? `<span class="analysis-time">${esc(a.time_period)}</span>` : ''}
              </div>
              <div class="analysis-item-desc">${esc(a.description || '')}</div>
            </div>`).join('')}
        </div>`;
    }
    trajCard.classList.remove('hidden');
  }

  // ── 3. Resume Inflation ──
  const inflCard = $('#resume-inflation-card');
  const inflBody = $('#resume-inflation-body');
  if (inflCard && inflBody) {
    const flags = analysis.inflation_flags || [];
    const riskLevel = analysis.inflation_risk_level || 'low';
    const summary = analysis.inflation_summary || '';
    $('#inflation-count').textContent = flags.length;

    if (flags.length === 0) {
      inflBody.innerHTML = `<div class="analysis-ok"><span class="analysis-ok-icon">✓</span> ${esc(summary) || 'No resume inflation detected.'}</div>`;
    } else {
      inflBody.innerHTML = `
        <div class="analysis-risk-banner risk-${riskLevel}">
          <span class="risk-label">Inflation Risk:</span>
          <span class="risk-level">${esc(riskLevel.toUpperCase())}</span>
        </div>
        ${summary ? `<div class="analysis-summary">${esc(summary)}</div>` : ''}
        <div class="analysis-items">
          ${flags.map((f, i) => `
            <div class="analysis-item severity-${f.severity || 'medium'}" style="animation-delay:${i * 0.05}s">
              <div class="analysis-item-header">
                <span class="severity-badge ${f.severity || 'medium'}">${esc((f.category || 'unknown').replace(/_/g, ' '))}</span>
              </div>
              <div class="analysis-item-claim">"${esc(f.claim || '')}"</div>
              <div class="analysis-item-desc">${esc(f.reason || '')}</div>
            </div>`).join('')}
        </div>`;
    }
    inflCard.classList.remove('hidden');
  }

  // ── 4. Skill Decay ──
  const decayCard = $('#resume-decay-card');
  const decayBody = $('#resume-decay-body');
  if (decayCard && decayBody) {
    const decayed = analysis.decayed_skills || [];
    const summary = analysis.decay_summary || '';
    $('#decay-count').textContent = decayed.length;

    if (decayed.length === 0) {
      decayBody.innerHTML = `<div class="analysis-ok"><span class="analysis-ok-icon">✓</span> ${esc(summary) || 'All skills appear current.'}</div>`;
    } else {
      decayBody.innerHTML = `
        ${summary ? `<div class="analysis-summary">${esc(summary)}</div>` : ''}
        <div class="decay-items">
          ${decayed.map((d, i) => {
        const riskColor = d.decay_risk === 'high' ? 'var(--rose)' : d.decay_risk === 'medium' ? 'var(--amber)' : 'var(--emerald)';
        return `
            <div class="decay-item" style="animation-delay:${i * 0.05}s">
              <div class="decay-item-top">
                <span class="decay-skill">${esc(d.skill)}</span>
                <span class="decay-last-used" style="color:${riskColor}">${esc(d.last_used || 'Unknown')}</span>
              </div>
              <div class="decay-bar"><div class="decay-bar-fill" style="background:${riskColor};width:${d.decay_risk === 'high' ? '90%' : d.decay_risk === 'medium' ? '55%' : '25%'}"></div></div>
              ${d.recommendation ? `<div class="decay-rec">${esc(d.recommendation)}</div>` : ''}
            </div>`;
      }).join('')}
        </div>`;
    }
    decayCard.classList.remove('hidden');
  }

  // ── 5. ATS Compatibility ──
  const atsCard = $('#resume-ats-card');
  const atsBody = $('#resume-ats-body');
  if (atsCard && atsBody) {
    const ats = analysis.ats || {};
    const atsScore = ats.score || 0;
    let atsColor = 'var(--emerald)';
    if (atsScore < 40) atsColor = 'var(--rose)';
    else if (atsScore < 70) atsColor = 'var(--amber)';

    const subScores = [
      { label: 'Section Completeness', value: ats.section_completeness || 0 },
      { label: 'Keyword Density', value: ats.keyword_density || 0 },
      { label: 'Formatting', value: ats.formatting_score || 0 },
      { label: 'Quantified Achievements', value: ats.quantified_achievements || 0 },
    ];

    atsBody.innerHTML = `
      <div class="ats-score-header">
        <div class="ats-score-big" style="color:${atsColor}">${atsScore}<span class="ats-score-unit">/100</span></div>
        <div class="ats-score-label">ATS Compatibility Score</div>
      </div>
      <div class="ats-bars">
        ${subScores.map((s) => {
      let barColor = 'var(--emerald)';
      if (s.value < 40) barColor = 'var(--rose)';
      else if (s.value < 70) barColor = 'var(--amber)';
      return `
          <div class="ats-bar-row">
            <div class="ats-bar-label">${esc(s.label)}</div>
            <div class="ats-bar-track"><div class="ats-bar-fill" style="width:${s.value}%;background:${barColor}"></div></div>
            <div class="ats-bar-value">${s.value}</div>
          </div>`;
    }).join('')}
      </div>
      ${(ats.issues || []).length ? `
        <div class="ats-section-label">Issues</div>
        <div class="ats-list ats-issues">
          ${ats.issues.map((i) => `<div class="ats-list-item ats-issue">✗ ${esc(i)}</div>`).join('')}
        </div>` : ''}
      ${(ats.suggestions || []).length ? `
        <div class="ats-section-label">Suggestions</div>
        <div class="ats-list ats-suggestions">
          ${ats.suggestions.map((s) => `<div class="ats-list-item ats-suggestion">→ ${esc(s)}</div>`).join('')}
        </div>` : ''}`;
    atsCard.classList.remove('hidden');
  }

  // ── 6. Strengths & Weaknesses ──
  const swCard = $('#resume-sw-card');
  const swBody = $('#resume-sw-body');
  if (swCard && swBody) {
    const strengths = analysis.strengths || [];
    const weaknesses = analysis.weaknesses || [];
    if (strengths.length || weaknesses.length) {
      swBody.innerHTML = `
        <div class="sw-grid">
          <div class="sw-col">
            <div class="sw-col-label" style="color:var(--emerald)">Strengths</div>
            ${strengths.map((s) => `<div class="sw-item sw-strength"><span class="sw-icon">▲</span> ${esc(s)}</div>`).join('')}
            ${!strengths.length ? '<div class="text-muted text-sm">None identified</div>' : ''}
          </div>
          <div class="sw-col">
            <div class="sw-col-label" style="color:var(--rose)">Weaknesses</div>
            ${weaknesses.map((w) => `<div class="sw-item sw-weakness"><span class="sw-icon">▼</span> ${esc(w)}</div>`).join('')}
            ${!weaknesses.length ? '<div class="text-muted text-sm">None identified</div>' : ''}
          </div>
        </div>`;
      swCard.classList.remove('hidden');
    }
  }
}

/* ================================================================
   BUTTONS
   ================================================================ */
function initButtons() {
  $('#btn-generate-questions').addEventListener('click', handleGenerateQuestions);
  $('#btn-analyze').addEventListener('click', handleAnalyze);
  $('#btn-scroll-bottom').addEventListener('click', () => {
    const feed = $('#transcript-feed');
    feed.scrollTop = feed.scrollHeight;
  });
}

/* ================================================================
   EXPORT
   ================================================================ */
function initExport() {
  $('#btn-export-transcript').addEventListener('click', exportTranscript);
  $('#btn-export-report').addEventListener('click', exportReport);
}

function exportTranscript() {
  if (!state.transcriptMessages.length) return;
  const lines = state.transcriptMessages.map((m) =>
    `[${fmtTime(m.timestamp)}] ${m.speaker.toUpperCase()}: ${m.text}`
  );
  const header = `InterviewIQ — Transcript Export\nSession: ${state.currentSessionId || 'unknown'}\nDate: ${new Date().toLocaleString()}\n${'='.repeat(60)}\n\n`;
  downloadFile(header + lines.join('\n'), `transcript_${Date.now()}.txt`, 'text/plain');
  showToast('Transcript exported', 'success');
}

function exportReport() {
  if (!state.consistencyData) return;
  const r = state.consistencyData;
  let report = `InterviewIQ — Consistency Analysis Report\nDate: ${new Date().toLocaleString()}\n${'='.repeat(60)}\n\n`;
  report += `OVERALL CREDIBILITY SCORE: ${r.overall_score || 0}%\n`;
  report += `Total Claims Analyzed: ${r.total_claims || 0}\n\n`;
  report += `${'─'.repeat(60)}\nDETAILED CLAIMS\n${'─'.repeat(60)}\n\n`;
  (r.analysis || []).forEach((c, i) => {
    report += `${i + 1}. [${(c.status || 'unknown').toUpperCase()}] (${c.confidence || 0}% confidence)\n`;
    report += `   Claim: ${c.claim || ''}\n`;
    report += `   Explanation: ${c.explanation || ''}\n\n`;
  });
  downloadFile(report, `consistency_report_${Date.now()}.txt`, 'text/plain');
  showToast('Report exported', 'success');
}

function downloadFile(content, filename, type) {
  const blob = new Blob([content], { type });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

/* ================================================================
   KEYBOARD SHORTCUTS
   ================================================================ */
function initKeyboardShortcuts() {
  document.addEventListener('keydown', (e) => {
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
    if (!e.ctrlKey && !e.metaKey) return;

    const map = { '1': 'dashboard', '2': 'resume', '3': 'questions', '4': 'transcript', '5': 'consistency' };
    if (map[e.key]) { e.preventDefault(); switchView(map[e.key]); return; }
    if (e.key === 'b' || e.key === 'B') {
      e.preventDefault();
      $('#sidebar').classList.toggle('collapsed');
      $('#main-wrapper').classList.toggle('expanded');
    }
  });
}

/* ================================================================
   QUESTIONS
   ================================================================ */
async function handleGenerateQuestions() {
  if (!state.resumeProfile) return;
  const btn = $('#btn-generate-questions');
  btn.disabled = true;

  $('#questions-empty').classList.add('hidden');
  $('#questions-grid').classList.add('hidden');
  $('#questions-loading').classList.remove('hidden');

  try {
    const text = state.transcriptMessages.map((m) => `${m.speaker.toUpperCase()}: ${m.text}`).join('\n');
    const result = await generateQuestions(state.resumeProfile, text);

    if (result.error && !result.questions?.length) throw new Error(result.error);

    const questions = result.questions || [];
    state.questionsData = questions;
    renderQuestions(questions);
    showToast(`${questions.length} questions generated`, 'success');
    $('#stat-questions').textContent = questions.length;
    updateDashboardQuestionsPreview(questions);
  } catch (err) {
    showToast(`Failed: ${err.message}`, 'error');
    $('#questions-empty').classList.remove('hidden');
  } finally {
    $('#questions-loading').classList.add('hidden');
    btn.disabled = false;
  }
}

function renderQuestions(questions) {
  const grid = $('#questions-grid');
  grid.innerHTML = '';
  questions.forEach((q, i) => {
    const cat = q.category || 'general';
    const card = document.createElement('div');
    card.className = 'question-card';
    card.style.animationDelay = `${i * 0.06}s`;
    card.innerHTML = `
      <div class="question-card-header">
        <span class="question-number">Q${i + 1}</span>
        <span class="question-category" data-cat="${escAttr(cat)}">${esc(cat.replace(/_/g, ' '))}</span>
      </div>
      <div class="question-text">${esc(q.question)}</div>`;
    grid.appendChild(card);
  });
  grid.classList.remove('hidden');
}

function updateDashboardQuestionsPreview(questions) {
  const el = $('#dash-questions-preview');
  el.innerHTML = questions.slice(0, 3).map((q, i) =>
    `<div style="padding:6px 0;border-bottom:1px solid var(--border);font-size:0.82rem;color:var(--text-2)">
      <span style="color:var(--primary);font-weight:700;font-family:var(--mono);font-size:0.72rem">Q${i + 1}</span>
      ${esc(q.question.substring(0, 80))}${q.question.length > 80 ? '...' : ''}
    </div>`
  ).join('');
}

/* ================================================================
   ANALYZE LATEST — 10-SECOND POLLING
   ================================================================ */
let _lastAnalysisJSON = '';

function startAnalyzeLatestPolling() {
  // Initial call after a short delay to let backend warm up
  setTimeout(pollAnalyzeLatest, 3000);
  // Then every 10 seconds
  setInterval(pollAnalyzeLatest, 10000);
}

async function pollAnalyzeLatest() {
  try {
    const result = await analyzeLatest();

    // Skip if error or no analysis
    if (result.error || !result.analysis) return;

    const analysis = result.analysis;
    const questions = analysis.follow_up_questions || [];
    if (questions.length === 0) return;

    // Skip if nothing changed (avoid unnecessary re-renders)
    const newJSON = JSON.stringify(questions);
    if (newJSON === _lastAnalysisJSON) return;
    _lastAnalysisJSON = newJSON;

    // Convert plain strings to {question, category} format
    const formatted = questions.map((q) => ({
      question: typeof q === 'string' ? q : q.question || String(q),
      category: typeof q === 'object' && q.category ? q.category : 'ai_analysis',
    }));

    // Update state and render
    state.questionsData = formatted;
    renderQuestions(formatted);
    updateDashboardQuestionsPreview(formatted);
    $('#stat-questions').textContent = formatted.length;

    // Also update quality score if available
    if (analysis.answer_quality_score > 0) {
      const score = analysis.answer_quality_score;
      $('#stat-score').textContent = `${score}%`;
      $('#stat-score').style.color =
        score >= 70 ? 'var(--emerald)' : score >= 40 ? 'var(--amber)' : 'var(--rose)';
    }

    console.log(`[analyze_latest] Updated ${formatted.length} follow-up questions`);
  } catch (err) {
    // Silently ignore polling errors (backend may not have data yet)
    console.debug('[analyze_latest] Poll error:', err.message);
  }
}

/* ================================================================
   CONSISTENCY ANALYSIS
   ================================================================ */
async function handleAnalyze() {
  if (!state.resumeProfile || state.transcriptMessages.length === 0) return;
  const btn = $('#btn-analyze');
  btn.disabled = true;

  $('#consistency-empty').classList.add('hidden');
  $('#consistency-results').classList.add('hidden');
  $('#consistency-loading').classList.remove('hidden');

  try {
    const text = state.transcriptMessages.map((m) => `${m.speaker.toUpperCase()}: ${m.text}`).join('\n');
    const result = await analyzeConsistency(state.resumeProfile, text);

    if (result.error && !result.analysis?.length) throw new Error(result.error);

    state.consistencyData = result;
    renderConsistency(result);
    showToast('Consistency analysis complete', 'success');
    $('#stat-score').textContent = `${result.overall_score || 0}%`;
    $('#stat-score').style.color = (result.overall_score || 0) >= 70 ? 'var(--emerald)' : (result.overall_score || 0) >= 40 ? 'var(--amber)' : 'var(--rose)';
    updateDashboardConsistencyPreview(result);
    $('#btn-export-report').disabled = false;
  } catch (err) {
    showToast(`Analysis failed: ${err.message}`, 'error');
    $('#consistency-empty').classList.remove('hidden');
  } finally {
    $('#consistency-loading').classList.add('hidden');
    btn.disabled = false;
  }
}

function renderConsistency(result) {
  const hero = $('#score-hero');
  const score = result.overall_score || 0;
  const total = result.total_claims || 0;

  let color = 'var(--emerald)';
  let label = 'High Credibility';
  if (score < 40) { color = 'var(--rose)'; label = 'Low Credibility'; }
  else if (score < 70) { color = 'var(--amber)'; label = 'Moderate Credibility'; }

  const circ = 2 * Math.PI * 42;
  const offset = circ - (score / 100) * circ;

  const verified = (result.analysis || []).filter((a) => a.status === 'verified').length;
  const inconsistent = (result.analysis || []).filter((a) => a.status === 'inconsistent').length;
  const flags = (result.analysis || []).filter((a) => a.status === 'red_flag').length;

  hero.innerHTML = `
    <div class="score-ring-wrapper">
      <svg width="100" height="100" viewBox="0 0 100 100">
        <circle class="score-ring-bg" cx="50" cy="50" r="42"/>
        <circle class="score-ring-fill" cx="50" cy="50" r="42"
          stroke="${color}" stroke-dasharray="${circ}" stroke-dashoffset="${offset}"/>
      </svg>
      <div class="score-ring-num" style="color:${color}">${score}%</div>
    </div>
    <div class="score-info">
      <div class="score-title">${label}</div>
      <div class="score-desc">${total} claims analyzed across the interview transcript</div>
      <div class="score-breakdown">
        <div class="breakdown-item"><span class="breakdown-dot" style="background:var(--emerald)"></span> ${verified} verified</div>
        <div class="breakdown-item"><span class="breakdown-dot" style="background:var(--rose)"></span> ${inconsistent} inconsistent</div>
        <div class="breakdown-item"><span class="breakdown-dot" style="background:var(--amber)"></span> ${flags} red flags</div>
      </div>
    </div>`;

  const icons = { verified: '✓', inconsistent: '✗', unverifiable: '?', red_flag: '⚑' };
  const grid = $('#claims-grid');
  grid.innerHTML = '';
  (result.analysis || []).forEach((c, i) => {
    const s = c.status || 'unverifiable';
    const el = document.createElement('div');
    el.className = 'claim-card';
    el.style.animationDelay = `${i * 0.05}s`;
    el.innerHTML = `
      <div class="claim-header">
        <span class="claim-status-icon ${s}">${icons[s] || '?'}</span>
        <span class="claim-status-label ${s}">${s.replace(/_/g, ' ')}</span>
        <span class="claim-confidence">${c.confidence || 0}%</span>
      </div>
      <div class="claim-text">${esc(c.claim || '')}</div>
      <div class="claim-explanation">${esc(c.explanation || '')}</div>`;
    grid.appendChild(el);
  });

  $('#consistency-results').classList.remove('hidden');
}

function updateDashboardConsistencyPreview(result) {
  const el = $('#dash-consistency-preview');
  const score = result.overall_score || 0;
  let color = 'var(--emerald)';
  if (score < 40) color = 'var(--rose)';
  else if (score < 70) color = 'var(--amber)';

  el.innerHTML = `
    <div style="text-align:center">
      <div style="font-size:2.2rem;font-weight:900;color:${color};font-family:var(--mono)">${score}%</div>
      <div class="text-sm text-muted">${result.total_claims || 0} claims analyzed</div>
    </div>`;
}

/* ================================================================
   SSE / LIVE TRANSCRIPT
   ================================================================ */
function initSSE() {
  state.sseSource = subscribeSSE((event) => {
    if (event.type === 'new_message') {
      addTranscriptMessage(event);
      setSessionLive(event.session_id);
    }
  });
  setTimeout(() => {
    if (!state.transcriptMessages.length) {
      $('#conn-text').textContent = 'Waiting...';
      $('#live-text').textContent = 'Waiting';
    }
  }, 3000);
}

function setSessionLive(sid) {
  state.currentSessionId = sid;
  // Connection status
  const dot = $('.conn-dot');
  dot.classList.remove('offline');
  dot.classList.add('live');
  $('#conn-text').textContent = 'Connected';
  // Live indicator
  const ind = $('#live-indicator');
  ind.classList.add('active');
  $('#live-text').textContent = 'Live';
}

function addTranscriptMessage(event) {
  state.transcriptMessages.push({
    speaker: event.speaker,
    text: event.text,
    timestamp: event.timestamp,
  });

  const feed = $('#transcript-feed');
  const empty = $('#transcript-empty');
  empty.classList.add('hidden');
  feed.classList.remove('hidden');

  const cls = event.speaker === 'interviewer' ? 'speaker-interviewer' : 'speaker-candidate';
  const init = event.speaker === 'interviewer' ? 'INT' : 'CAN';

  const el = document.createElement('div');
  el.className = `transcript-msg ${cls}`;
  el.innerHTML = `
    <div class="speaker-avatar">${init}</div>
    <div class="transcript-msg-content">
      <div class="transcript-msg-header">
        <span class="transcript-speaker">${esc(event.speaker)}</span>
        <span class="transcript-time">${fmtTime(event.timestamp)}</span>
      </div>
      <div class="transcript-text">${esc(event.text)}</div>
    </div>`;
  feed.appendChild(el);
  feed.scrollTop = feed.scrollHeight;

  // Update counts
  const count = state.transcriptMessages.length;
  $('#msg-count-label').textContent = `${count} turn${count !== 1 ? 's' : ''}`;
  $('#nav-msg-count').textContent = count;
  $('#stat-messages').textContent = count;
  // Enable export
  $('#btn-export-transcript').disabled = false;

  // Dashboard preview
  updateDashboardTranscriptPreview();
  updateAnalyzeButton();
}

function updateDashboardTranscriptPreview() {
  const el = $('#dash-transcript-preview');
  const last = state.transcriptMessages.slice(-4);
  el.innerHTML = last.map((m) => {
    const cls = m.speaker === 'interviewer' ? 'speaker-interviewer' : 'speaker-candidate';
    const col = m.speaker === 'interviewer' ? 'var(--blue)' : 'var(--purple)';
    return `<div style="padding:5px 0;border-bottom:1px solid var(--border);font-size:0.82rem;color:var(--text-2)">
      <span style="color:${col};font-weight:700;font-size:0.68rem;text-transform:uppercase;letter-spacing:0.04em">${esc(m.speaker)}</span>
      <span style="margin-left:8px">${esc(m.text.substring(0, 80))}${m.text.length > 80 ? '...' : ''}</span>
    </div>`;
  }).join('');
}

function updateAnalyzeButton() {
  $('#btn-analyze').disabled = !(state.resumeProfile && state.transcriptMessages.length > 0);
}

/* ================================================================
   LOAD EXISTING CONVERSATIONS
   ================================================================ */
async function loadExistingConversations() {
  try {
    const data = await getConversations();
    const convs = data.conversations || [];
    state.allConversations = convs;
    if (convs.length > 0) {
      const latest = convs[convs.length - 1];
      if (latest.status === 'active') setSessionLive(latest.session_id);

      const conv = await getConversation(latest.session_id);
      if (conv?.messages?.length) {
        conv.messages.forEach((m) => {
          addTranscriptMessage({ speaker: m.speaker, text: m.text, timestamp: m.start_time });
        });
      }
    }
  } catch (e) {
    console.warn('[load]', e);
  }
}

/* ================================================================
   HISTORY VIEW
   ================================================================ */
async function loadHistoryView() {
  try {
    const data = await getConversations();
    const convs = data.conversations || [];
    if (convs.length === 0) return;

    $('#history-empty').classList.add('hidden');
    const container = $('#history-cards');
    container.classList.remove('hidden');
    container.innerHTML = '';

    convs.slice().reverse().forEach((c, i) => {
      const card = document.createElement('div');
      card.className = 'history-card';
      card.style.animationDelay = `${i * 0.05}s`;
      const msgCount = c.message_count || 0;
      const status = c.status || 'ended';
      card.innerHTML = `
        <div class="history-card-top">
          <span class="history-card-id">${esc(c.session_id?.substring(0, 12) || 'unknown')}...</span>
          <span class="history-card-status ${status}">${status}</span>
        </div>
        <div class="history-card-stats">
          <div class="history-stat">
            <span class="history-stat-value">${msgCount}</span>
            <span class="history-stat-label">Messages</span>
          </div>
          <div class="history-stat">
            <span class="history-stat-value">${c.speakers?.length || 0}</span>
            <span class="history-stat-label">Speakers</span>
          </div>
        </div>`;
      card.addEventListener('click', () => {
        switchView('transcript');
      });
      container.appendChild(card);
    });
  } catch (e) {
    console.warn('[history]', e);
  }
}

/* ================================================================
   SETTINGS SYNC
   ================================================================ */
function syncSettingsStatus() {
  // SSE status
  const sse = $('#setting-sse-status');
  if (state.sseSource && state.sseSource.readyState === EventSource.OPEN) {
    sse.textContent = 'Connected';
    sse.classList.add('active');
  } else {
    sse.textContent = 'Disconnected';
    sse.classList.remove('active');
  }
}

/* ================================================================
   TOASTS
   ================================================================ */
function showToast(message, type = 'info') {
  const container = $('#toast-container');
  const icons = { success: '✅', error: '❌', info: 'ℹ️' };
  const t = document.createElement('div');
  t.className = `toast toast-${type}`;
  t.innerHTML = `<span class="toast-icon">${icons[type] || 'ℹ️'}</span><span class="toast-msg">${esc(message)}</span>`;
  container.appendChild(t);
  setTimeout(() => {
    t.style.opacity = '0';
    t.style.transform = 'translateY(16px)';
    t.style.transition = 'all 0.3s ease';
    setTimeout(() => t.remove(), 300);
  }, 4000);
}

/* ================================================================
   HELPERS
   ================================================================ */
function esc(s) {
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}
function escAttr(s) {
  return s.replace(/[&"'<>]/g, (c) => ({ '&': '&amp;', '"': '&quot;', "'": '&#39;', '<': '&lt;', '>': '&gt;' }[c]));
}
function fmtTime(ts) {
  if (!ts) return '';
  const d = new Date(ts * 1000);
  if (isNaN(d.getTime())) {
    const m = Math.floor(ts / 60);
    const s = Math.floor(ts % 60);
    return `${m}:${String(s).padStart(2, '0')}`;
  }
  return d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

/* ================================================================
   SKILL CONFIDENCE SCORES (from /analyze_latest)
   ================================================================ */
function initSkillConfidence() {
  const btn = document.getElementById('btn-refresh-confidence');
  if (btn) {
    btn.addEventListener('click', fetchAndRenderSkillConfidence);
  }
}

async function fetchAndRenderSkillConfidence() {
  const btn = document.getElementById('btn-refresh-confidence');
  const barsContainer = document.getElementById('skill-confidence-bars');
  const emptyState = document.getElementById('skill-confidence-empty');
  const badge = document.getElementById('confidence-skill-count');

  if (!barsContainer) return;

  // Show loading state on button
  if (btn) {
    btn.disabled = true;
    btn.innerHTML = `
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="spin">
        <path d="M21 12a9 9 0 1 1-6.219-8.56"/>
      </svg>
      Analyzing...
    `;
  }

  try {
    const data = await analyzeLatest();

    if (data.error) {
      showToast(data.error, 'error');
      return;
    }

    const skills = data.analysis?.skill_confidence_updates || {};
    const entries = Object.entries(skills).sort((a, b) => b[1] - a[1]); // sort by highest confidence

    if (entries.length === 0) {
      showToast('No skill confidence data returned — start an interview first', 'warning');
      return;
    }

    // Update badge
    if (badge) badge.textContent = entries.length;

    // Build bars
    barsContainer.innerHTML = entries.map(([skill, score]) => {
      const level = score >= 70 ? 'high' : score >= 40 ? 'medium' : 'low';
      return `
        <div class="skill-conf-row">
          <span class="skill-conf-name" title="${esc(skill)}">${esc(skill)}</span>
          <div class="skill-conf-bar-wrap">
            <div class="skill-conf-bar-fill ${level}" style="width: 0%"></div>
          </div>
          <span class="skill-conf-pct ${level}">${score}%</span>
        </div>
      `;
    }).join('');

    // Show bars, hide empty state
    barsContainer.style.display = 'flex';
    if (emptyState) emptyState.style.display = 'none';

    // Animate bars after a brief delay
    requestAnimationFrame(() => {
      setTimeout(() => {
        barsContainer.querySelectorAll('.skill-conf-bar-fill').forEach((bar, i) => {
          bar.style.width = `${entries[i][1]}%`;
        });
      }, 50);
    });

    showToast(`Loaded confidence scores for ${entries.length} skills`, 'success');

  } catch (err) {
    console.error('[skill-confidence] Error:', err);
    showToast('Failed to fetch skill confidence data', 'error');
  } finally {
    // Reset button
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = `
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <polyline points="1 4 1 10 7 10"/><polyline points="23 20 23 14 17 14"/>
          <path d="M20.49 9A9 9 0 0 0 5.64 5.64L1 10m22 4l-4.64 4.36A9 9 0 0 1 3.51 15"/>
        </svg>
        Refresh from Interview
      `;
    }
  }
}

/* ================================================================
   POST-INTERVIEW REPORT
   ================================================================ */

function initReport() {
  const btn = $('#btn-generate-report');
  if (btn) btn.addEventListener('click', handleGenerateReport);
}

async function handleGenerateReport() {
  const btn = $('#btn-generate-report');
  btn.disabled = true;

  $('#report-empty').classList.add('hidden');
  $('#report-content').classList.add('hidden');
  $('#report-loading').classList.remove('hidden');

  try {
    const result = await postInterviewAnalysis(state.resumeProfile);

    if (result.error) throw new Error(result.error);
    if (!result.report) throw new Error('No report generated');

    renderReport(result.report, result);
    showToast('Post-interview report generated!', 'success');
  } catch (err) {
    showToast(`Report failed: ${err.message}`, 'error');
    $('#report-empty').classList.remove('hidden');
  } finally {
    $('#report-loading').classList.add('hidden');
    btn.disabled = false;
  }
}

function renderReport(report, meta) {
  // Score Hero
  const score = report.overall_score || 0;
  const verdict = report.verdict || 'Analysis Complete';
  let color = 'var(--emerald)';
  if (score < 40) color = 'var(--rose)';
  else if (score < 70) color = 'var(--amber)';

  const circ = 2 * Math.PI * 42;
  const offset = circ - (score / 100) * circ;

  const recColors = {
    'Strong Hire': 'var(--emerald)', 'Hire': 'var(--emerald)',
    'Lean Hire': 'var(--amber)', 'Lean No Hire': 'var(--amber)',
    'No Hire': 'var(--rose)', 'Strong No Hire': 'var(--rose)',
  };
  const recColor = recColors[report.hiring_recommendation] || 'var(--text-2)';

  $('#report-hero').innerHTML = `
    <div class="score-hero" style="margin-bottom:0">
      <div class="score-ring-wrapper">
        <svg width="100" height="100" viewBox="0 0 100 100">
          <circle class="score-ring-bg" cx="50" cy="50" r="42"/>
          <circle class="score-ring-fill" cx="50" cy="50" r="42"
            stroke="${color}" stroke-dasharray="${circ}" stroke-dashoffset="${offset}"/>
        </svg>
        <div class="score-ring-num" style="color:${color}">${score}</div>
      </div>
      <div class="score-info">
        <div class="score-title" style="color:${color}">${esc(verdict)}</div>
        <div class="score-desc">${meta.message_count || 0} messages analyzed · Session ${esc((meta.session_id || '').substring(0, 8))}</div>
        <div style="margin-top:10px">
          <span style="display:inline-block;padding:4px 14px;border-radius:var(--r-full);font-size:0.78rem;font-weight:700;background:${recColor}22;color:${recColor};border:1px solid ${recColor}44">
            ${esc(report.hiring_recommendation || 'Pending')}
          </span>
        </div>
      </div>
    </div>`;

  // Summary
  $('#report-summary').innerHTML = `<p style="font-size:0.92rem;color:var(--text-2);line-height:1.7">${esc(report.summary || '')}</p>`;

  // Strengths & Weaknesses
  const strengths = report.strengths || [];
  const weaknesses = report.weaknesses || [];
  $('#report-sw').innerHTML = `
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-top:16px">
      <div class="card">
        <div class="card-header"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="var(--emerald)" stroke-width="2"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg><h3 style="color:var(--emerald)">Strengths</h3></div>
        <div class="card-body">
          ${strengths.map(s => `<div style="display:flex;align-items:flex-start;gap:8px;padding:6px 0;border-bottom:1px solid var(--border);font-size:0.85rem;color:var(--text-2)"><span style="color:var(--emerald);font-weight:800;flex-shrink:0">▲</span>${esc(s)}</div>`).join('')}
          ${!strengths.length ? '<p class="text-muted text-sm">None identified</p>' : ''}
        </div>
      </div>
      <div class="card">
        <div class="card-header"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="var(--rose)" stroke-width="2"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg><h3 style="color:var(--rose)">Weaknesses</h3></div>
        <div class="card-body">
          ${weaknesses.map(w => `<div style="display:flex;align-items:flex-start;gap:8px;padding:6px 0;border-bottom:1px solid var(--border);font-size:0.85rem;color:var(--text-2)"><span style="color:var(--rose);font-weight:800;flex-shrink:0">▼</span>${esc(w)}</div>`).join('')}
          ${!weaknesses.length ? '<p class="text-muted text-sm">None identified</p>' : ''}
        </div>
      </div>
    </div>`;

  // Skill Assessments
  const skills = report.skill_assessments || [];
  $('#report-skills').innerHTML = skills.map(s => {
    const sc = s.score || 0;
    let barColor = 'var(--emerald)';
    if (sc < 40) barColor = 'var(--rose)';
    else if (sc < 70) barColor = 'var(--amber)';
    return `
      <div style="display:flex;align-items:center;gap:14px;padding:10px 0;border-bottom:1px solid var(--border)">
        <span style="min-width:120px;font-size:0.82rem;font-weight:600;color:var(--text-1)">${esc(s.skill)}</span>
        <div style="flex:1;height:8px;border-radius:var(--r-full);background:var(--bg-3);overflow:hidden">
          <div style="height:100%;width:${sc}%;background:${barColor};border-radius:var(--r-full);transition:width 1s ease"></div>
        </div>
        <span style="font-size:0.75rem;font-weight:700;color:${barColor};font-family:var(--mono);min-width:35px;text-align:right">${sc}%</span>
      </div>
      <div style="font-size:0.78rem;color:var(--text-3);padding:4px 0 8px 134px;line-height:1.5">${esc(s.evidence || '')}</div>`;
  }).join('');

  // Consistency Notes
  const notes = report.consistency_notes || [];
  const statusIcons = { verified: '✓', inconsistent: '✗', unverified: '?' };
  const statusColors = { verified: 'var(--emerald)', inconsistent: 'var(--rose)', unverified: 'var(--amber)' };
  $('#report-consistency').innerHTML = notes.map(n => {
    const st = n.status || 'unverified';
    const ic = statusIcons[st] || '?';
    const cl = statusColors[st] || 'var(--text-3)';
    return `
      <div style="padding:12px 0;border-bottom:1px solid var(--border)">
        <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px">
          <span style="width:22px;height:22px;border-radius:6px;display:flex;align-items:center;justify-content:center;font-size:0.72rem;font-weight:800;background:${cl}18;color:${cl}">${ic}</span>
          <span style="font-size:0.72rem;font-weight:700;text-transform:uppercase;letter-spacing:0.04em;color:${cl}">${esc(st)}</span>
        </div>
        <div style="font-size:0.85rem;color:var(--text-1);margin-bottom:4px"><strong>Resume:</strong> ${esc(n.claim || '')}</div>
        <div style="font-size:0.82rem;color:var(--text-3);padding-left:12px;border-left:2px solid var(--border)"><strong>Interview:</strong> ${esc(n.interview_evidence || '')}</div>
      </div>`;
  }).join('');

  // Hiring Recommendation
  $('#report-recommendation').innerHTML = `
    <div class="card" style="border-left:4px solid ${recColor}">
      <div class="card-header">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="${recColor}" stroke-width="2"><path d="M14 9V5a3 3 0 0 0-3-3l-4 9v11h11.28a2 2 0 0 0 2-1.7l1.38-9a2 2 0 0 0-2-2.3H14z"/><path d="M4 22H2V11h2"/></svg>
        <h3>Hiring Recommendation</h3>
        <span style="margin-left:auto;padding:4px 14px;border-radius:var(--r-full);font-size:0.78rem;font-weight:700;background:${recColor}18;color:${recColor}">${esc(report.hiring_recommendation || 'Pending')}</span>
      </div>
      <div class="card-body">
        <p style="font-size:0.9rem;color:var(--text-2);line-height:1.7">${esc(report.recommendation_reasoning || '')}</p>
      </div>
    </div>`;

  // Next Steps
  const steps = report.suggested_next_steps || [];
  $('#report-nextsteps').innerHTML = steps.map((s, i) =>
    `<div style="display:flex;align-items:flex-start;gap:10px;padding:8px 0;border-bottom:1px solid var(--border);font-size:0.85rem;color:var(--text-2)">
      <span style="color:var(--primary);font-weight:800;font-family:var(--mono);font-size:0.72rem;flex-shrink:0">${String(i + 1).padStart(2, '0')}</span>
      ${esc(s)}
    </div>`
  ).join('');

  // Show report
  $('#report-content').classList.remove('hidden');
}
