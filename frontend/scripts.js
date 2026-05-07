/* =============================================
   INSIGHT AI — SCRIPTS.JS
   Complete frontend logic for AI Research Assistant
   ============================================= */

'use strict';

// =============================================
// CONFIG
// =============================================
const CONFIG = {
  API_KEY: 'dev-key',
  USER_ID: 'user',
  BASE_URL: '',  // same origin
  PLACEHOLDERS: [
    'Ask about quantum computing breakthroughs…',
    'Explain CRISPR gene editing…',
    'What is the impact of AI on jobs?',
    'How does nuclear fusion work?',
    'Latest research on climate change…',
    'Explain the James Webb telescope findings…',
    'What causes inflation?',
    'How does mRNA vaccine technology work?',
  ],
};

// =============================================
// STATE
// =============================================
const state = {
  currentChatId: null,
  isLoading: false,
  chats: [],           // [{id, title, is_pinned, created_at}]
  placeholderIdx: 0,
  placeholderTimer: null,
  renameChatId: null,
  activeStream: null,  // AbortController
};

// =============================================
// DOM REFS
// =============================================
const $ = id => document.getElementById(id);

const DOM = {
  sidebar:          $('sidebar'),
  sidebarToggle:    $('sidebarToggle'),
  mobileMenuBtn:    $('mobileMenuBtn'),
  newChatBtn:       $('newChatBtn'),
  chatSearch:       $('chatSearch'),
  todayList:        $('todayList'),
  yesterdayList:    $('yesterdayList'),
  olderList:        $('olderList'),
  todayGroup:       $('todayGroup'),
  yesterdayGroup:   $('yesterdayGroup'),
  olderGroup:       $('olderGroup'),
  emptyHistory:     $('emptyHistory'),
  welcomeScreen:    $('welcomeScreen'),
  messagesContainer:$('messagesContainer'),
  chatArea:         $('chatArea'),
  queryInput:       $('queryInput'),
  sendBtn:          $('sendBtn'),
  statusPill:       $('statusPill'),
  statusText:       $('statusText'),
  metaChips:        $('metaChips'),
  modeVal:          $('modeVal'),
  latencyVal:       $('latencyVal'),
  confidenceVal:    $('confidenceVal'),
  renameModal:      $('renameModal'),
  renameInput:      $('renameInput'),
  renameCancelBtn:  $('renameCancelBtn'),
  renameConfirmBtn: $('renameConfirmBtn'),
  toastContainer:   $('toastContainer'),
  previewToggle:    $('previewToggle'),
  previewBody:      $('previewBody'),
  previewChevron:   document.querySelector('.preview-chevron'),
  inputBar:         $('inputBar'),
};

// =============================================
// INIT
// =============================================
document.addEventListener('DOMContentLoaded', () => {
  initEventListeners();
  loadChatHistory();
  startPlaceholderRotation();
  autoResizeTextarea();
});

// =============================================
// EVENT LISTENERS
// =============================================
function initEventListeners() {
  // Send
  DOM.sendBtn.addEventListener('click', handleSend);
  DOM.queryInput.addEventListener('keydown', e => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  });

  // Input auto-resize
  DOM.queryInput.addEventListener('input', () => {
    autoResizeTextarea();
  });

  // Sidebar toggle (desktop)
  DOM.sidebarToggle.addEventListener('click', () => {
    DOM.sidebar.classList.toggle('collapsed');
  });

  // Mobile sidebar
  DOM.mobileMenuBtn.addEventListener('click', openMobileSidebar);

  // New chat
  DOM.newChatBtn.addEventListener('click', startNewChat);

  // Search
  DOM.chatSearch.addEventListener('input', e => filterChats(e.target.value));

  // Rename modal
  DOM.renameCancelBtn.addEventListener('click', closeRenameModal);
  DOM.renameConfirmBtn.addEventListener('click', confirmRename);
  DOM.renameInput.addEventListener('keydown', e => {
    if (e.key === 'Enter') confirmRename();
    if (e.key === 'Escape') closeRenameModal();
  });
  DOM.renameModal.addEventListener('click', e => {
    if (e.target === DOM.renameModal) closeRenameModal();
  });

  // Suggested queries & trending
  document.addEventListener('click', e => {
    const btn = e.target.closest('[data-query]');
    if (btn) {
      const q = btn.getAttribute('data-query');
      if (q) submitQuery(q);
    }
  });

  // Example preview toggle
  if (DOM.previewToggle) {
    DOM.previewToggle.addEventListener('click', () => {
      const isOpen = DOM.previewBody.style.display !== 'none';
      DOM.previewBody.style.display = isOpen ? 'none' : 'block';
      if (DOM.previewChevron) DOM.previewChevron.classList.toggle('open', !isOpen);
    });
  }

  // Mobile backdrop
  document.addEventListener('click', e => {
    if (e.target.classList.contains('sidebar-backdrop')) closeMobileSidebar();
  });
}

// =============================================
// AUTO-RESIZE TEXTAREA
// =============================================
function autoResizeTextarea() {
  const ta = DOM.queryInput;
  ta.style.height = 'auto';
  ta.style.height = Math.min(ta.scrollHeight, 180) + 'px';
}

// =============================================
// PLACEHOLDER ROTATION
// =============================================
function startPlaceholderRotation() {
  const setPlaceholder = () => {
    DOM.queryInput.placeholder = CONFIG.PLACEHOLDERS[state.placeholderIdx % CONFIG.PLACEHOLDERS.length];
    state.placeholderIdx++;
  };
  setPlaceholder();
  state.placeholderTimer = setInterval(setPlaceholder, 3500);
}

// =============================================
// SIDEBAR — MOBILE
// =============================================
function openMobileSidebar() {
  DOM.sidebar.classList.add('mobile-open');
  let backdrop = document.querySelector('.sidebar-backdrop');
  if (!backdrop) {
    backdrop = document.createElement('div');
    backdrop.className = 'sidebar-backdrop';
    document.body.appendChild(backdrop);
  }
  backdrop.style.display = 'block';
}

function closeMobileSidebar() {
  DOM.sidebar.classList.remove('mobile-open');
  const backdrop = document.querySelector('.sidebar-backdrop');
  if (backdrop) backdrop.style.display = 'none';
}

// =============================================
// CHAT HISTORY — LOAD
// =============================================
async function loadChatHistory() {
  try {
    const res = await fetch('/history', {
      headers: { 'x-api-key': CONFIG.API_KEY },
    });
    if (!res.ok) return;
    const data = await res.json();
    state.chats = data.chats || [];
    renderChatList(state.chats);
  } catch (err) {
    console.warn('History load failed:', err);
  }
}

// =============================================
// CHAT HISTORY — RENDER
// =============================================
function renderChatList(chats) {
  const now = new Date();
  const todayStr = now.toDateString();
  const yesterday = new Date(now);
  yesterday.setDate(now.getDate() - 1);
  const yesterdayStr = yesterday.toDateString();

  const groups = { today: [], yesterday: [], older: [] };

  (chats || []).forEach(chat => {
    const d = chat.created_at ? new Date(chat.created_at).toDateString() : '';
    if (d === todayStr) groups.today.push(chat);
    else if (d === yesterdayStr) groups.yesterday.push(chat);
    else groups.older.push(chat);
  });

  renderGroup(DOM.todayList, DOM.todayGroup, groups.today);
  renderGroup(DOM.yesterdayList, DOM.yesterdayGroup, groups.yesterday);
  renderGroup(DOM.olderList, DOM.olderGroup, groups.older);

  const hasAny = chats && chats.length > 0;
  DOM.emptyHistory.classList.toggle('visible', !hasAny);
}

function renderGroup(listEl, groupEl, items) {
  listEl.innerHTML = '';
  groupEl.style.display = items.length ? 'block' : 'none';
  items.forEach(chat => listEl.appendChild(createChatItem(chat)));
}

function createChatItem(chat) {
  const li = document.createElement('li');
  li.className = 'chat-item' + (chat.id === state.currentChatId ? ' active' : '');
  li.dataset.chatId = chat.id;

  li.innerHTML = `
    <div class="chat-item-inner">
      <span class="chat-item-title">${escapeHtml(chat.title || 'Untitled')}</span>
      <div class="chat-item-actions">
        <button class="chat-action-btn" data-action="rename" title="Rename">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M17 3a2.85 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z"/>
          </svg>
        </button>
        <button class="chat-action-btn danger" data-action="delete" title="Delete">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M3 6h18M19 6l-1 14H6L5 6M10 11v6M14 11v6M9 6V4h6v2"/>
          </svg>
        </button>
      </div>
    </div>
  `;

  // Click to load
  li.addEventListener('click', e => {
    if (e.target.closest('[data-action]')) return;
    loadChat(chat.id);
  });

  // Action buttons
  li.querySelector('[data-action="rename"]').addEventListener('click', e => {
    e.stopPropagation();
    openRenameModal(chat.id, chat.title);
  });

  li.querySelector('[data-action="delete"]').addEventListener('click', e => {
    e.stopPropagation();
    deleteChat(chat.id);
  });

  return li;
}

function setActiveChat(chatId) {
  state.currentChatId = chatId;
  document.querySelectorAll('.chat-item').forEach(el => {
    el.classList.toggle('active', el.dataset.chatId === chatId);
  });
}

// =============================================
// CHAT HISTORY — FILTER
// =============================================
function filterChats(query) {
  const q = query.toLowerCase().trim();
  const filtered = q
    ? state.chats.filter(c => (c.title || '').toLowerCase().includes(q))
    : state.chats;
  renderChatList(filtered);
}

// =============================================
// LOAD EXISTING CHAT
// =============================================
async function loadChat(chatId) {
  try {
    closeMobileSidebar();
    setActiveChat(chatId);
    showMessagesView();
    DOM.messagesContainer.innerHTML = '';

    const res = await fetch(`/chat/${chatId}`, {
      headers: { 'x-api-key': CONFIG.API_KEY },
    });
    if (!res.ok) return;
    const data = await res.json();
    const messages = data.messages || [];

    messages.forEach(msg => {
      if (msg.role === 'user') {
        appendUserMessage(msg.content);
      } else if (msg.role === 'assistant') {
        appendRestoredAssistantMessage(msg.content);
      }
    });

    scrollToBottom();
  } catch (err) {
    console.warn('Load chat failed:', err);
    showToast('Failed to load chat', 'error');
  }
}

function appendRestoredAssistantMessage(content) {
  const wrapper = document.createElement('div');
  wrapper.className = 'msg-ai';

  const card = buildResponseCard();
  card.dataset.restored = 'true';

  // Parse sections from raw content
  const { answer, detailed, keyPoints, examples } = parseResponseSections(content);

  const answerEl = card.querySelector('.answer-text');
  if (answerEl) answerEl.innerHTML = renderMarkdown(answer || content);

  const detailedEl = card.querySelector('[data-section="detailed"] .collapsible-body');
  if (detailedEl && detailed) {
    detailedEl.innerHTML = `<div class="answer-text">${renderMarkdown(detailed)}</div>`;
  }

  const keyPointsEl = card.querySelector('.key-points-list');
  if (keyPointsEl && keyPoints.length) {
    keyPointsEl.innerHTML = keyPoints.map((pt, i) => `
      <div class="key-point">
        <span class="key-point-num">0${i + 1}</span>
        <span>${escapeHtml(pt)}</span>
      </div>
    `).join('');
  }

  wrapper.appendChild(card);
  DOM.messagesContainer.appendChild(wrapper);
}

// =============================================
// NEW CHAT
// =============================================
function startNewChat() {
  state.currentChatId = null;
  DOM.messagesContainer.innerHTML = '';
  showWelcomeView();
  setActiveChat(null);
  DOM.queryInput.value = '';
  DOM.queryInput.style.height = 'auto';
  DOM.queryInput.focus();
  closeMobileSidebar();

  // Reset header meta
  DOM.metaChips.style.display = 'none';
  setStatus('Ready', false);
}

// =============================================
// SEND / SUBMIT
// =============================================
function handleSend() {
  const q = DOM.queryInput.value.trim();
  if (!q || state.isLoading) return;
  submitQuery(q);
}

async function submitQuery(query) {
  if (!query.trim() || state.isLoading) return;

  // Abort previous stream if any
  if (state.activeStream) {
    state.activeStream.abort();
    state.activeStream = null;
  }

  DOM.queryInput.value = '';
  DOM.queryInput.style.height = 'auto';

  showMessagesView();
  appendUserMessage(query);

  const chatId = state.currentChatId || null;

  await streamResearch(query, chatId);
}

// =============================================
// VIEWS
// =============================================
function showWelcomeView() {
  DOM.welcomeScreen.style.display = 'flex';
  DOM.messagesContainer.style.display = 'none';
}

function showMessagesView() {
  DOM.welcomeScreen.style.display = 'none';
  DOM.messagesContainer.style.display = 'flex';
}

// =============================================
// APPEND USER MESSAGE
// =============================================
function appendUserMessage(text) {
  const div = document.createElement('div');
  div.className = 'msg-user';
  div.innerHTML = `<div class="msg-user-bubble">${escapeHtml(text)}</div>`;
  DOM.messagesContainer.appendChild(div);
  scrollToBottom();
}

// =============================================
// STREAM RESEARCH
// =============================================
async function streamResearch(query, existingChatId) {
  state.isLoading = true;
  setLoading(true);
  setStatus('Thinking…', true);

  // Show skeleton
  const skeletonEl = appendSkeleton();

  const controller = new AbortController();
  state.activeStream = controller;

  // Build response card (hidden until skeleton removed)
  let responseCard = null;
  let cardWrapper = null;
  let streamBuffer = '';
  let answerEl = null;
  let cursorEl = null;
  let sourcesRendered = false;
  let evalRendered = false;
  let metricsRendered = false;
  let streamStarted = false;
  let currentChatId = existingChatId;
  let pendingSources = null;   // ✅ FIX: buffer sources if card not ready yet

  try {
    const body = {
      topic: query,
      user_id: CONFIG.USER_ID,
    };
    if (currentChatId) body.chat_id = currentChatId;

    const res = await fetch('/research', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'x-api-key': CONFIG.API_KEY,
      },
      body: JSON.stringify(body),
      signal: controller.signal,
    });

    if (!res.ok) {
      throw new Error(`HTTP ${res.status}`);
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });

      const lines = buffer.split('\n');
      buffer = lines.pop(); // keep incomplete line

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        const raw = line.slice(6).trim();
        if (!raw) continue;

        let event;
        try {
          event = JSON.parse(raw);
        } catch {
          continue;
        }

        // --- STAGE ---
        if (event.type === 'stage') {
          setStatus(event.content, true);
          continue;
        }

        // --- TOKEN (streaming answer) ---
        if (event.type === 'token') {
          if (!streamStarted) {
            streamStarted = true;
            // Remove skeleton, create card
            skeletonEl.remove();
            const built = buildAndAppendResponseCard(query);
            cardWrapper = built.wrapper;
            responseCard = built.card;
            answerEl = built.answerEl;
            cursorEl = built.cursorEl;

            // ✅ FIX: apply buffered sources now that card exists
            if (pendingSources && !sourcesRendered) {
              sourcesRendered = true;
              renderSources(responseCard, pendingSources);
              const section = responseCard.querySelector('[data-section="sources"]');
              const body = section?.querySelector('.collapsible-body');
              const chevron = section?.querySelector('.collapsible-chevron');
              if (body) body.classList.add('open');
              if (chevron) chevron.classList.add('open');
              pendingSources = null;
            }
          }

          streamBuffer += event.content;
          // Render markdown incrementally
          if (answerEl) {
            answerEl.innerHTML = renderMarkdown(streamBuffer);
            if (cursorEl) answerEl.appendChild(cursorEl);
          }
          scrollToBottom();
          continue;
        }

        // --- SOURCES ---
        if (event.type === 'sources' && !sourcesRendered) {
          if (responseCard) {
            // card already exists — render immediately
            sourcesRendered = true;
            renderSources(responseCard, event.data);
            const section = responseCard.querySelector('[data-section="sources"]');
            const body = section?.querySelector('.collapsible-body');
            const chevron = section?.querySelector('.collapsible-chevron');
            if (body) body.classList.add('open');
            if (chevron) chevron.classList.add('open');
          } else {
            // ✅ FIX: card not built yet — buffer and apply on first token
            pendingSources = event.data;
          }
          continue;
        }

        // --- CONFIDENCE ---
        if (event.type === 'confidence') {
          const pct = Math.round((event.value || 0) * 100);
          DOM.confidenceVal.textContent = pct + '%';
          DOM.metaChips.style.display = 'flex';
          if (responseCard) {
            const badge = responseCard.querySelector('[data-badge="confidence"]');
            if (badge) badge.textContent = pct + '%';
          }
          continue;
        }

        // --- EVALUATION ---
        if (event.type === 'evaluation' && !evalRendered) {
          evalRendered = true;
          if (responseCard) renderEvaluation(responseCard, event.data);
          continue;
        }

        // --- EXPLAIN ---
        if (event.type === 'explain') {
          if (responseCard) {
            const sysEl = responseCard.querySelector('.sys-info-row');
            if (sysEl) {
              const explainBadge = sysEl.querySelector('[data-badge="explain"]');
              if (explainBadge) explainBadge.innerHTML = `<strong>${escapeHtml(event.content)}</strong>`;
            }
          }
          continue;
        }

        // --- METRICS ---
        if (event.type === 'metrics' && !metricsRendered) {
          metricsRendered = true;
          const { latency, mode } = event.data || {};
          if (latency !== undefined) DOM.latencyVal.textContent = latency + 's';
          if (mode) {
            DOM.modeVal.textContent = mode.toUpperCase();
            if (responseCard) {
              const tag = responseCard.querySelector('.card-mode-tag');
              if (tag) {
                tag.textContent = mode.toUpperCase();
                tag.className = `card-mode-tag ${mode}`;
              }
            }
          }
          DOM.metaChips.style.display = 'flex';
          continue;
        }

        // --- ERROR ---
        if (event.type === 'error') {
          if (!streamStarted) skeletonEl.remove();
          showToast('Error: ' + (event.content || 'Unknown error'), 'error');
          setStatus('Error', false);
          break;
        }

        // --- DONE ---
        if (event.type === 'done') {
          if (!streamStarted) skeletonEl.remove();
          break;
        }
      }
    }

    // Finalize stream
    if (cursorEl) cursorEl.remove();

    // Parse sections from final buffer
    if (responseCard && streamBuffer) {
      finalizeResponseCard(responseCard, streamBuffer, query);
    }

    // Fetch updated chat ID from history (if new chat)
    if (!currentChatId) {
      await loadChatHistory();
      // Pick the latest chat
      if (state.chats.length > 0) {
        currentChatId = state.chats[0].id;
        state.currentChatId = currentChatId;
        setActiveChat(currentChatId);
      }
    }

    setStatus('Ready', false);

  } catch (err) {
    if (err.name === 'AbortError') {
      setStatus('Cancelled', false);
    } else {
      console.error('Stream error:', err);
      showToast('Connection error. Please try again.', 'error');
      setStatus('Error', false);
    }
    if (!streamStarted) {
      try { skeletonEl.remove(); } catch {}
    }
  } finally {
    state.isLoading = false;
    state.activeStream = null;
    setLoading(false);
    scrollToBottom();
  }
}




// =============================================
// BUILD RESPONSE CARD STRUCTURE
// =============================================
function buildResponseCard() {
  const card = document.createElement('div');
  card.className = 'response-card';
  card.innerHTML = `
    <!-- CARD HEADER -->
    <div class="card-header">
      <div class="card-ai-avatar">✦</div>
      <span class="card-ai-name">Insight AI</span>
      <span class="card-mode-tag">—</span>
    </div>

    <!-- CARD BODY -->
    <div class="card-body">

      <!-- ANSWER -->
      <div class="answer-section">
        <div class="section-label">
          <span class="section-label-dot"></span>
          Answer
        </div>
        <div class="answer-text"></div>
      </div>

      <!-- DETAILED EXPLANATION (collapsible) -->
      <div class="collapsible-section" data-section="detailed">
        <div class="collapsible-header">
          <div class="section-label">
            <span class="section-label-dot"></span>
            Detailed Explanation
          </div>
          <svg class="collapsible-chevron" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="m6 9 6 6 6-6"/>
          </svg>
        </div>
        <div class="collapsible-body"></div>
      </div>

      <!-- KEY INSIGHTS (collapsible) -->
      <div class="collapsible-section" data-section="keypoints">
        <div class="collapsible-header">
          <div class="section-label">
            <span class="section-label-dot"></span>
            Key Insights
          </div>
          <svg class="collapsible-chevron" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="m6 9 6 6 6-6"/>
          </svg>
        </div>
        <div class="collapsible-body">
          <div class="key-points-list"></div>
        </div>
      </div>

      <!-- SOURCES (collapsible) -->
      <div class="collapsible-section" data-section="sources">
        <div class="collapsible-header">
          <div class="section-label">
            <span class="section-label-dot"></span>
            Sources
          </div>
          <svg class="collapsible-chevron" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="m6 9 6 6 6-6"/>
          </svg>
        </div>
        <div class="collapsible-body">
          <div class="sources-grid"></div>
        </div>
      </div>

      <!-- EVALUATION (collapsible) -->
      <div class="collapsible-section" data-section="evaluation">
        <div class="collapsible-header">
          <div class="section-label">
            <span class="section-label-dot"></span>
            Evaluation
          </div>
          <svg class="collapsible-chevron" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="m6 9 6 6 6-6"/>
          </svg>
        </div>
        <div class="collapsible-body">
          <div class="eval-block">
            <div class="eval-metric" data-eval="relevance">
              <span class="eval-label">Relevance</span>
              <div class="eval-bar-wrap"><div class="eval-bar"></div></div>
              <span class="eval-value">—</span>
            </div>
            <div class="eval-metric" data-eval="grounded">
              <span class="eval-label">Groundedness</span>
              <div class="eval-bar-wrap"><div class="eval-bar"></div></div>
              <span class="eval-value">—</span>
            </div>
            <div class="eval-metric" data-eval="clarity">
              <span class="eval-label">Clarity</span>
              <div class="eval-bar-wrap"><div class="eval-bar"></div></div>
              <span class="eval-value">—</span>
            </div>
            <div class="eval-metric final" data-eval="final">
              <span class="eval-label">Final Score</span>
              <div class="eval-bar-wrap"><div class="eval-bar"></div></div>
              <span class="eval-value">—</span>
            </div>
          </div>
        </div>
      </div>

      <!-- SYSTEM INFO -->
      <div class="collapsible-section" data-section="sysinfo">
        <div class="collapsible-header">
          <div class="section-label">
            <span class="section-label-dot"></span>
            System Info
          </div>
          <svg class="collapsible-chevron" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="m6 9 6 6 6-6"/>
          </svg>
        </div>
        <div class="collapsible-body">
          <div class="sys-info-row">
            <span class="sys-badge">
              <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <circle cx="12" cy="12" r="3"/><path d="M12 1v4M12 19v4M4.22 4.22l2.83 2.83M16.95 16.95l2.83 2.83M1 12h4M19 12h4M4.22 19.78l2.83-2.83M16.95 7.05l2.83-2.83"/>
              </svg>
              <strong data-badge="explain">—</strong>
            </span>
            <span class="sys-badge">
              <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20z"/><path d="M12 6v6l4 2"/>
              </svg>
              Latency: <strong id="cardLatency">—</strong>
            </span>
            <span class="sys-badge">
              <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="m22 11.08V12a10 10 0 1 1-5.93-9.14"/>
                <path d="m9 11 3 3L22 4"/>
              </svg>
              Confidence: <strong data-badge="confidence">—</strong>
            </span>
          </div>
        </div>
      </div>

    </div><!-- /card-body -->

    <!-- CARD FOOTER -->
    <div class="card-footer">
      <button class="card-action-btn copy-btn" title="Copy answer">
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <rect width="14" height="14" x="8" y="8" rx="2" ry="2"/>
          <path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"/>
        </svg>
        Copy
      </button>
      <button class="card-action-btn export-btn" title="Export as PDF">
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="m7 10 5 5 5-5"/><path d="M12 15V3"/>
        </svg>
        Export PDF
      </button>
      <div class="feedback-row">
        <button class="feedback-btn" data-fb="up" title="Good response">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M14 9V5a3 3 0 0 0-3-3l-4 9v11h11.28a2 2 0 0 0 2-1.7l1.38-9a2 2 0 0 0-2-2.3H14z"/>
            <path d="M7 22H4a2 2 0 0 1-2-2v-7a2 2 0 0 1 2-2h3"/>
          </svg>
        </button>
        <button class="feedback-btn" data-fb="down" title="Bad response">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M10 15v4a3 3 0 0 0 3 3l4-9V2H5.72a2 2 0 0 0-2 1.7l-1.38 9a2 2 0 0 0 2 2.3H10z"/>
            <path d="M17 2h2.67A2.31 2.31 0 0 1 22 4v7a2.31 2.31 0 0 1-2.33 2H17"/>
          </svg>
        </button>
      </div>
    </div>
  `;

  // Wire collapsible sections
  card.querySelectorAll('.collapsible-header').forEach(header => {
    header.addEventListener('click', () => {
      const body = header.nextElementSibling;
      const chevron = header.querySelector('.collapsible-chevron');
      const isOpen = body.classList.contains('open');
      body.classList.toggle('open', !isOpen);
      if (chevron) chevron.classList.toggle('open', !isOpen);
    });
  });

  // Copy button
  card.querySelector('.copy-btn').addEventListener('click', () => {
    const text = card.querySelector('.answer-text')?.innerText || '';
    navigator.clipboard.writeText(text).then(() => {
      const btn = card.querySelector('.copy-btn');
      btn.classList.add('copied');
      btn.innerHTML = `
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
          <path d="m20 6-11 11-5-5"/>
        </svg>
        Copied!
      `;
      setTimeout(() => {
        btn.classList.remove('copied');
        btn.innerHTML = `
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <rect width="14" height="14" x="8" y="8" rx="2" ry="2"/>
            <path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"/>
          </svg>
          Copy
        `;
      }, 2000);
    }).catch(() => showToast('Copy failed', 'error'));
  });

  // Export PDF
  card.querySelector('.export-btn').addEventListener('click', () => {
    exportCardAsPDF(card);
  });

  // Feedback buttons
  card.querySelectorAll('.feedback-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      card.querySelectorAll('.feedback-btn').forEach(b => b.style.opacity = '0.3');
      btn.style.opacity = '1';
      showToast(btn.dataset.fb === 'up' ? '👍 Thanks for the feedback!' : '👎 Noted, will improve!', 'success');
    });
  });

  return card;
}

function buildAndAppendResponseCard(query) {
  const wrapper = document.createElement('div');
  wrapper.className = 'msg-ai';

  const card = buildResponseCard();
  wrapper.appendChild(card);
  DOM.messagesContainer.appendChild(wrapper);

  const answerEl = card.querySelector('.answer-text');
  const cursorEl = document.createElement('span');
  cursorEl.className = 'stream-cursor';
  if (answerEl) answerEl.appendChild(cursorEl);

  scrollToBottom();
  return { wrapper, card, answerEl, cursorEl };
}

// =============================================
// FINALIZE RESPONSE CARD (parse sections)
// =============================================
function finalizeResponseCard(card, rawText, query) {
  const { answer, detailed, keyPoints, examples } = parseResponseSections(rawText);

  // Answer section
  const answerEl = card.querySelector('.answer-section .answer-text');
  if (answerEl) answerEl.innerHTML = renderMarkdown(answer || rawText);

  // Detailed explanation
  if (detailed) {
    const detBody = card.querySelector('[data-section="detailed"] .collapsible-body');
    if (detBody) {
      detBody.innerHTML = `<div class="answer-text">${renderMarkdown(detailed)}</div>`;
      detBody.classList.add('open');
      const chevron = card.querySelector('[data-section="detailed"] .collapsible-chevron');
      if (chevron) chevron.classList.add('open');
    }
  }

  // Key points
  if (keyPoints.length > 0) {
    const kpList = card.querySelector('.key-points-list');
    if (kpList) {
      kpList.innerHTML = keyPoints.map((pt, i) => `
        <div class="key-point">
          <span class="key-point-num">0${i + 1}</span>
          <span>${renderMarkdown(pt)}</span>
        </div>
      `).join('');
      const kpBody = card.querySelector('[data-section="keypoints"] .collapsible-body');
      if (kpBody) {
        kpBody.classList.add('open');
        const chevron = card.querySelector('[data-section="keypoints"] .collapsible-chevron');
        if (chevron) chevron.classList.add('open');
      }
    }
  }

  // Examples (append to detailed or answer)
  if (examples) {
    const detBody = card.querySelector('[data-section="detailed"] .collapsible-body');
    if (detBody) {
      detBody.innerHTML += `<div class="answer-text" style="margin-top:12px"><strong>Examples</strong><br>${renderMarkdown(examples)}</div>`;
    }
  }
}

// =============================================
// PARSE RESPONSE SECTIONS
// =============================================
function parseResponseSections(text) {
  const sections = {
    answer: '',
    detailed: '',
    keyPoints: [],
    examples: '',
  };

  if (!text) return sections;

  // Extract ## Answer
  const answerMatch = text.match(/##\s*Answer\s*\n([\s\S]*?)(?=##|$)/i);
  if (answerMatch) sections.answer = answerMatch[1].trim();

  // Extract ## Detailed Explanation
  const detailedMatch = text.match(/##\s*Detailed\s*Explanation\s*\n([\s\S]*?)(?=##|$)/i);
  if (detailedMatch) sections.detailed = detailedMatch[1].trim();

  // Extract ## Key Points
  const kpMatch = text.match(/##\s*Key\s*(?:Points|Insights)\s*\n([\s\S]*?)(?=##|$)/i);
  if (kpMatch) {
    sections.keyPoints = kpMatch[1]
      .split('\n')
      .map(l => l.replace(/^[-•*]\s*/, '').trim())
      .filter(l => l.length > 5);
  }

  // Extract ## Examples
  const examplesMatch = text.match(/##\s*Examples?\s*(?:\(.*?\))?\s*\n([\s\S]*?)(?=##|$)/i);
  if (examplesMatch) sections.examples = examplesMatch[1].trim();

  // If no sections found, use whole text as answer
  if (!sections.answer && !sections.detailed) {
    sections.answer = text;
  }

  return sections;
}

// =============================================
// RENDER SOURCES
// =============================================
function renderSources(card, sources) {
  const container = card.querySelector(".sources-grid");
  if (!container) return;

  container.innerHTML = "";

  if (!sources || sources.length === 0) {
    container.innerHTML = `<div class="empty-text">No sources available</div>`;
    return;
  }

  sources.forEach(src => {
    const item = document.createElement("div");
    item.className = "source-item";

    item.innerHTML = `
      <a href="${src.url || '#'}" target="_blank" class="source-link">
        <span class="source-id">[${src.id}]</span>
        <span class="source-title">${src.title || "Untitled"}</span>
      </a>
    `;

    container.appendChild(item);
  });
}

// =============================================
// RENDER EVALUATION
// =============================================
function renderEvaluation(card, evalData) {
  if (!evalData) return;

  const metrics = ['relevance', 'grounded', 'clarity', 'final'];

  metrics.forEach(key => {
    const metricEl = card.querySelector(`[data-eval="${key}"]`);
    if (!metricEl) return;

    const raw = evalData[key] || 0;
    const pct = Math.round(raw * 100);

    const bar = metricEl.querySelector('.eval-bar');
    const val = metricEl.querySelector('.eval-value');

    if (bar) {
      setTimeout(() => { bar.style.width = pct + '%'; }, 100);
    }
    if (val) val.textContent = pct + '%';
  });

  // Auto-open evaluation
  const evalBody = card.querySelector('[data-section="evaluation"] .collapsible-body');
  if (evalBody) {
    evalBody.classList.add('open');
    const chevron = card.querySelector('[data-section="evaluation"] .collapsible-chevron');
    if (chevron) chevron.classList.add('open');
  }
}

// =============================================
// SKELETON LOADER
// =============================================
function appendSkeleton() {
  const wrapper = document.createElement('div');
  wrapper.className = 'msg-ai skeleton-wrapper';
  wrapper.innerHTML = `
    <div class="skeleton-card">
      <div style="display:flex;gap:10px;align-items:center;margin-bottom:4px">
        <div class="skeleton-line h-lg" style="width:28px;border-radius:8px;flex-shrink:0"></div>
        <div class="skeleton-line h-sm" style="width:80px"></div>
      </div>
      <div class="skeleton-line w-full h-lg" style="margin-top:8px"></div>
      <div class="skeleton-line w-3-4"></div>
      <div class="skeleton-line w-full"></div>
      <div class="skeleton-line w-2-3 h-sm"></div>
      <div style="display:flex;gap:8px;margin-top:8px">
        <div class="skeleton-line h-sm" style="width:60px;border-radius:999px"></div>
        <div class="skeleton-line h-sm" style="width:80px;border-radius:999px"></div>
        <div class="skeleton-line h-sm" style="width:50px;border-radius:999px"></div>
      </div>
    </div>
  `;
  DOM.messagesContainer.appendChild(wrapper);
  scrollToBottom();
  return wrapper;
}

// =============================================
// RENAME CHAT
// =============================================
function openRenameModal(chatId, currentTitle) {
  state.renameChatId = chatId;
  DOM.renameInput.value = currentTitle || '';
  DOM.renameModal.style.display = 'flex';
  setTimeout(() => {
    DOM.renameInput.focus();
    DOM.renameInput.select();
  }, 50);
}

function closeRenameModal() {
  DOM.renameModal.style.display = 'none';
  state.renameChatId = null;
  DOM.renameInput.value = '';
}

async function confirmRename() {
  const title = DOM.renameInput.value.trim();
  if (!title || !state.renameChatId) { closeRenameModal(); return; }

  try {
    await fetch('/rename_chat', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'x-api-key': CONFIG.API_KEY,
      },
      body: JSON.stringify({ chat_id: state.renameChatId, title }),
    });

    // Update local state
    const chat = state.chats.find(c => c.id === state.renameChatId);
    if (chat) chat.title = title;
    renderChatList(state.chats);
    showToast('Chat renamed', 'success');
  } catch {
    showToast('Rename failed', 'error');
  }

  closeRenameModal();
}

// =============================================
// DELETE CHAT
// =============================================
async function deleteChat(chatId) {
  try {
    await fetch('/delete_chat', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'x-api-key': CONFIG.API_KEY,
      },
      body: JSON.stringify({ chat_id: chatId }),
    });

    state.chats = state.chats.filter(c => c.id !== chatId);
    renderChatList(state.chats);

    if (state.currentChatId === chatId) {
      startNewChat();
    }

    showToast('Chat deleted', 'success');
  } catch {
    showToast('Delete failed', 'error');
  }
}

// =============================================
// EXPORT PDF
// =============================================
function exportCardAsPDF(card) {
  showToast('Generating PDF…', 'success');

  // =============================================
  // EXTRACT TEXT FROM CARD SECTIONS
  // =============================================
  const answer    = card.querySelector('.answer-section .answer-text')?.innerText?.trim() || '';
  const detailed  = card.querySelector('[data-section="detailed"] .collapsible-body')?.innerText?.trim() || '';
  const keyPoints = Array.from(card.querySelectorAll('.key-point')).map(k => {
    const num  = k.querySelector('.key-point-num')?.innerText?.trim() || '';
    const text = k.querySelector('span:last-child')?.innerText?.trim() || '';
    return `${num}  ${text}`;
  }).filter(Boolean);
  const sources   = Array.from(card.querySelectorAll('.source-item')).map((s, i) => {
    const title = s.querySelector('.source-title')?.innerText?.trim() || 'Source';
    const url   = s.querySelector('a')?.href || '';
    return { title, url };
  });
  const evalVals = {
    relevance : card.querySelector('[data-eval="relevance"] .eval-value')?.innerText  || '—',
    grounded  : card.querySelector('[data-eval="grounded"] .eval-value')?.innerText   || '—',
    clarity   : card.querySelector('[data-eval="clarity"] .eval-value')?.innerText    || '—',
    final     : card.querySelector('[data-eval="final"] .eval-value')?.innerText      || '—',
  };

  // =============================================
  // BUILD A CLEAN PRINTABLE HTML PAGE
  // =============================================
  const sourcesHTML = sources.length
    ? sources.map((s, i) => `
        <div class="source-row">
          <span class="src-id">[${i+1}]</span>
          <a href="${s.url}" class="src-title">${s.title}</a>
        </div>`).join('')
    : '<p class="muted">No sources available</p>';

  const keyHTML = keyPoints.length
    ? keyPoints.map(pt => `<div class="kp-row">${pt}</div>`).join('')
    : '<p class="muted">—</p>';

  const html = `<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8"/>
<title>Insight AI Research</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: 'Segoe UI', Arial, sans-serif;
    background: #0e1320;
    color: #e2e8f0;
    padding: 24px 28px 24px 28px;
    font-size: 12px;
    line-height: 1.75;
    width: 794px;
    min-width: 794px;
    max-width: 794px;
    overflow: hidden;
  }
  .wrapper {
    width: 738px;
    max-width: 738px;
    margin: 0 auto;
  }
  .header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    border-bottom: 2px solid #7c3aed;
    padding-bottom: 12px;
    margin-bottom: 24px;
  }
  .brand { font-size: 20px; font-weight: 700; color: #a78bfa; }
  .date  { font-size: 11px; color: #64748b; }
  .section { margin-bottom: 24px; }
  .section-title {
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 1.5px;
    color: #a78bfa;
    text-transform: uppercase;
    border-left: 3px solid #7c3aed;
    padding-left: 8px;
    margin-bottom: 10px;
  }
  .answer-box {
    background: #1e293b;
    border-radius: 8px;
    padding: 16px;
    color: #f1f5f9;
    font-size: 12.5px;
    line-height: 1.8;
    word-wrap: break-word;
    overflow-wrap: break-word;
  }
  .detailed-box {
    background: #141c2e;
    border-radius: 8px;
    padding: 16px;
    color: #cbd5e1;
    font-size: 11.5px;
    white-space: pre-wrap;
    word-wrap: break-word;
    overflow-wrap: break-word;
  }
  .kp-row {
    background: #1e293b;
    border-radius: 6px;
    padding: 10px 14px;
    margin-bottom: 6px;
    color: #e2e8f0;
    font-size: 12.5px;
  }
  .source-row {
    display: flex;
    align-items: flex-start;
    gap: 10px;
    padding: 8px 12px;
    background: #1e293b;
    border-radius: 6px;
    margin-bottom: 5px;
  }
  .src-id  { color: #a78bfa; font-weight: 700; min-width: 28px; }
  .src-title { color: #7dd3fc; font-size: 11px; word-break: break-word; overflow-wrap: break-word; }
  .eval-grid {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 8px;
  }
  .eval-box {
    background: #1e293b;
    border-radius: 8px;
    padding: 12px;
    text-align: center;
  }
  .eval-label { font-size: 9px; color: #64748b; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 4px; }
  .eval-val   { font-size: 18px; font-weight: 700; color: #f1f5f9; }
  .eval-val.final { color: #a78bfa; }
  .footer {
    margin-top: 28px;
    border-top: 1px solid #1e293b;
    padding-top: 10px;
    font-size: 10px;
    color: #475569;
    text-align: center;
  }
  .muted { color: #475569; font-style: italic; }
</style>
</head>
<body>
  <div class="wrapper">
  <div class="header">
    <div class="brand">✦ Insight AI — Research Report</div>
    <div class="date">${new Date().toLocaleDateString('en-US', { year:'numeric', month:'long', day:'numeric' })}</div>
  </div>

  <div class="section">
    <div class="section-title">Answer</div>
    <div class="answer-box">${answer.replace(/\n/g, '<br>')}</div>
  </div>

  ${detailed ? `
  <div class="section">
    <div class="section-title">Detailed Explanation</div>
    <div class="detailed-box">${detailed}</div>
  </div>` : ''}

  ${keyPoints.length ? `
  <div class="section">
    <div class="section-title">Key Insights</div>
    ${keyHTML}
  </div>` : ''}

  <div class="section">
    <div class="section-title">Sources</div>
    ${sourcesHTML}
  </div>

  <div class="section">
    <div class="section-title">Evaluation</div>
    <div class="eval-grid">
      <div class="eval-box"><div class="eval-label">Relevance</div><div class="eval-val">${evalVals.relevance}</div></div>
      <div class="eval-box"><div class="eval-label">Groundedness</div><div class="eval-val">${evalVals.grounded}</div></div>
      <div class="eval-box"><div class="eval-label">Clarity</div><div class="eval-val">${evalVals.clarity}</div></div>
      <div class="eval-box"><div class="eval-label">Final Score</div><div class="eval-val final">${evalVals.final}</div></div>
    </div>
  </div>

  <div class="footer">Generated by Insight AI &nbsp;·&nbsp; Powered by GPT-4o + Tavily</div>
  </div>
</body>
</html>`;

  // =============================================
  // RENDER IN HIDDEN IFRAME → html2pdf
  // =============================================
  const iframe = document.createElement('iframe');
  iframe.style.cssText = 'position:fixed;top:0;left:0;width:794px;height:1123px;border:none;z-index:-9999;visibility:hidden;';
  document.body.appendChild(iframe);

  iframe.onload = () => {
    setTimeout(() => {
      const iframeDoc = iframe.contentDocument;
      const iframeBody = iframeDoc.body;
      const iframeHtml = iframeDoc.documentElement;

      html2pdf()
        .set({
          margin: 0,
          filename: 'insight-ai-research.pdf',
          image: { type: 'jpeg', quality: 0.97 },
          html2canvas: {
            scale: 2,
            useCORS: true,
            backgroundColor: '#0e1320',
            windowWidth: 794,
            width: 794,
            x: 0,
            y: 0,
            scrollX: 0,
            scrollY: 0,
            logging: false,
          },
          jsPDF: { unit: 'mm', format: 'a4', orientation: 'portrait' },
          pagebreak: { mode: 'avoid-all' },
        })
        .from(iframeBody)
        .save()
        .then(() => {
          document.body.removeChild(iframe);
          showToast('PDF exported successfully!', 'success');
        })
        .catch(() => {
          document.body.removeChild(iframe);
          showToast('Export failed', 'error');
        });
    }, 400);
  };

  // Write HTML into iframe
  iframe.contentDocument.open();
  iframe.contentDocument.write(html);
  iframe.contentDocument.close();
}

// =============================================
// STATUS / LOADING
// =============================================
function setStatus(text, isThinking) {
  DOM.statusText.textContent = text;
  DOM.statusPill.classList.toggle('thinking', isThinking);
}

function setLoading(loading) {
  DOM.sendBtn.disabled = loading;
  DOM.queryInput.disabled = loading;
  DOM.sendBtn.style.opacity = loading ? '0.4' : '1';
}

// =============================================
// SCROLL
// =============================================
function scrollToBottom() {
  requestAnimationFrame(() => {
    DOM.chatArea.scrollTo({ top: DOM.chatArea.scrollHeight, behavior: 'smooth' });
  });
}

// =============================================
// TOAST
// =============================================
function showToast(message, type = 'success') {
  const toast = document.createElement('div');
  toast.className = `toast ${type}`;

  const icon = type === 'success'
    ? `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#34d399" stroke-width="2.5"><path d="m20 6-11 11-5-5"/></svg>`
    : `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#f87171" stroke-width="2.5"><path d="M18 6 6 18M6 6l12 12"/></svg>`;

  toast.innerHTML = `${icon} ${escapeHtml(message)}`;
  DOM.toastContainer.appendChild(toast);

  setTimeout(() => {
    toast.style.animation = 'toastOut 0.25s ease forwards';
    setTimeout(() => toast.remove(), 300);
  }, 3000);
}

// =============================================
// MARKDOWN RENDER
// =============================================
function renderMarkdown(text) {
  if (!text) return '';
  try {
    if (typeof marked !== 'undefined') {
      return marked.parse(text, { breaks: true, gfm: true });
    }
  } catch {}
  // Fallback: basic formatting
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.*?)\*/g, '<em>$1</em>')
    .replace(/`(.*?)`/g, '<code>$1</code>')
    .replace(/\n/g, '<br>');
}

// =============================================
// ESCAPE HTML
// =============================================
function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}