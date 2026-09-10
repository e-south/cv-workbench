const DISCONNECTED_MESSAGE = 'Preview disconnected';
const PASSIVE_CONTROLLER_MESSAGE = 'Controller active in another tab';
const CONTROLLER_AVAILABLE_MESSAGE = 'Controller available; focus this tab to claim';
const RENDER_SETTLE_MS = 180;
const VISIBLE_REFRESH_MS = 1000;
const HIDDEN_REFRESH_MS = 4000;
const state = { data: null };
const history = [];
const iframe = document.getElementById('preview');
const projectSelect = document.getElementById('project-select');
const variantSelect = document.getElementById('variant-select');
const themeSelect = document.getElementById('theme-select');
const presetSelect = document.getElementById('preset-select');
const autoPdfToggle = document.getElementById('auto-pdf-toggle');
const formatTabs = document.getElementById('format-tabs');
const rebuildButton = document.getElementById('rebuild');
const stopButton = document.getElementById('stop-preview');
const statusEl = document.getElementById('status');
const errorEl = document.getElementById('error');
const summaryEl = document.getElementById('summary');
const projectGuidanceEl = document.getElementById('project-guidance');
const projectWarningEl = document.getElementById('project-warning');
const runList = document.getElementById('run-list');
const controllerPill = document.getElementById('controller-pill');
const buildPill = document.getElementById('build-pill');
const formats = ['html', 'pdf', 'md', 'ats'];
const controllerTabId = 'tab-' + Math.random().toString(36).slice(2);
let stopped = false;
let connectionError = null;
let currentFormat = 'html';
let lastSeenBuildId = document.body.dataset.cvwBuildId || '';
let lastControlsKey = null;
let lastOverlayKey = null;
let lastSummaryKey = null;
let lastProjectGuidanceKey = null;
let currentPreviewSrc = iframe.getAttribute('src') || '';
let pendingAction = null;
let refreshTimer = null;
let renderInFlight = false;
let scheduledRenderTimer = null;
let scheduledRenderRequest = null;
let queuedRenderRequest = null;
let currentSessionId = document.body.dataset.cvwSessionId || '';
let sessionChannel = null;
let passiveController = false;
let controllerClaimAvailable = false;

async function fetchState() {
  const res = await fetch('/api/state');
  if (!res.ok) {
    throw new Error(DISCONNECTED_MESSAGE);
  }
  return res.json();
}

function listSignature(list) {
  if (!list || list.length === 0) return '';
  return list.join('|');
}

function presetsSignature(presets) {
  if (!presets) return '';
  const themes = Object.keys(presets).sort();
  return themes
    .map((theme) => theme + ':' + listSignature(presets[theme] || []))
    .join('||');
}

function setControllerState(status) {
  document.body.dataset.cvwControllerState = status;
}

function setControllerPill(stateValue, label) {
  controllerPill.dataset.cvwState = stateValue;
  controllerPill.textContent = label;
}

function clearScheduledRender() {
  if (scheduledRenderTimer) {
    clearTimeout(scheduledRenderTimer);
    scheduledRenderTimer = null;
  }
  scheduledRenderRequest = null;
}

function hasQueuedRender() {
  return Boolean(scheduledRenderRequest || queuedRenderRequest);
}

function closeSessionChannel() {
  if (!sessionChannel) return;
  sessionChannel.close();
  sessionChannel = null;
}

function postControllerMessage(message) {
  if (!sessionChannel) return;
  sessionChannel.postMessage(message);
}

function claimController(reason) {
  if (!currentSessionId || typeof window.BroadcastChannel !== 'function') {
    passiveController = false;
    controllerClaimAvailable = false;
    return;
  }
  passiveController = false;
  controllerClaimAvailable = false;
  postControllerMessage({
    type: 'claim',
    reason,
    session_id: currentSessionId,
    tab_id: controllerTabId,
  });
}

function bindSessionChannel(sessionId) {
  const nextSessionId = sessionId || '';
  if (nextSessionId === currentSessionId) {
    document.body.dataset.cvwSessionId = nextSessionId;
    return;
  }
  closeSessionChannel();
  currentSessionId = nextSessionId;
  document.body.dataset.cvwSessionId = nextSessionId;
  passiveController = false;
  controllerClaimAvailable = false;
  if (!nextSessionId || typeof window.BroadcastChannel !== 'function') {
    return;
  }
  sessionChannel = new BroadcastChannel('cvw-preview:' + nextSessionId);
  sessionChannel.addEventListener('message', (event) => {
    const message = event.data || {};
    if (message.session_id !== currentSessionId || message.tab_id === controllerTabId) {
      return;
    }
    if (message.type === 'claim') {
      passiveController = true;
      controllerClaimAvailable = false;
      clearScheduledRender();
      queuedRenderRequest = null;
      if (refreshTimer) {
        clearTimeout(refreshTimer);
        refreshTimer = null;
      }
      syncOverlay(state.data || {}, true);
      return;
    }
    if (message.type === 'release' && passiveController) {
      if (document.visibilityState === 'visible' && document.hasFocus()) {
        claimController('release');
        syncOverlay(state.data || {}, true);
        scheduleRefresh(true);
        return;
      }
      controllerClaimAvailable = true;
      syncOverlay(state.data || {}, true);
      return;
    }
    if (message.type === 'stopped') {
      handleRemoteStop();
      syncOverlay(state.data || {}, true);
    }
  });
  claimController('connect');
}

function controlsSignature(data) {
  return [
    data.session_id || '',
    listSignature(data.projects),
    data.project || '',
    listSignature(data.variants),
    data.variant || '',
    listSignature(data.themes),
    data.theme || '',
    presetsSignature(data.presets || {}),
    data.style_preset || '',
    data.format || '',
    data.auto_pdf ? '1' : '0',
  ].join('::');
}

function overlaySignature(data) {
  const lastError = data && data.last_error ? data.last_error : '';
  return [
    stopped ? 'stopped' : 'live',
    pendingAction || '',
    lastError,
    connectionError || '',
    passiveController ? 'passive' : 'active',
    controllerClaimAvailable ? 'claimable' : 'claimed',
    hasQueuedRender() ? 'queued' : 'clear',
  ].join('::');
}

function renderOverlay(data) {
  const lastError = data && data.last_error ? data.last_error : '';
  if (connectionError) {
    setControllerState('disconnected');
    setControllerPill('disconnected', 'disconnected');
    statusEl.textContent = DISCONNECTED_MESSAGE + '.';
    errorEl.textContent = connectionError;
    errorEl.style.display = 'block';
    setControlsEnabled(false);
    return;
  }
  if (stopped) {
    setControllerState('stopped');
    setControllerPill('stopped', 'stopped');
    statusEl.textContent = 'Preview stopped.';
  } else if (passiveController) {
    setControllerState('passive');
    setControllerPill('passive', 'Other tab');
    statusEl.textContent = (
      controllerClaimAvailable ? CONTROLLER_AVAILABLE_MESSAGE : PASSIVE_CONTROLLER_MESSAGE
    ) + '.';
    errorEl.style.display = 'none';
    setControlsEnabled(false);
    return;
  } else if (pendingAction === 'render' && hasQueuedRender()) {
    setControllerState('active');
    setControllerPill('active', 'Live');
    statusEl.textContent = 'Finishing current rebuild; next change queued...';
  } else if (pendingAction === 'render') {
    setControllerState('active');
    setControllerPill('active', 'Live');
    statusEl.textContent = 'Rebuilding preview...';
  } else if (pendingAction === 'stop') {
    setControllerState('active');
    setControllerPill('active', 'Live');
    statusEl.textContent = 'Stopping preview...';
  } else if (hasQueuedRender()) {
    setControllerState('active');
    setControllerPill('active', 'Live');
    statusEl.textContent = 'Queued rebuild...';
  } else {
    setControllerState('active');
    setControllerPill('active', 'Live');
    statusEl.textContent = 'Listening for changes...';
  }
  if (lastError) {
    errorEl.textContent = lastError;
    errorEl.style.display = 'block';
  } else {
    errorEl.style.display = 'none';
  }
  setControlsEnabled(!stopped && pendingAction !== 'render' && pendingAction !== 'stop' && !passiveController);
}

function syncOverlay(data, force = false) {
  const nextOverlayKey = overlaySignature(data);
  if (!force && nextOverlayKey === lastOverlayKey) {
    return;
  }
  renderOverlay(data);
  lastOverlayKey = nextOverlayKey;
}

function appendSummaryField(line, label, value) {
  line.appendChild(document.createTextNode(label));
  const strong = document.createElement('strong');
  strong.textContent = value;
  line.appendChild(strong);
}

function summarySignature(data) {
  if (!data) {
    return 'none::' + currentFormat;
  }
  return [
    data.project || '',
    data.variant || '',
    data.theme || '',
    data.style_preset || '',
    currentFormat || 'html',
    data.build_id || '',
  ].join('::');
}

function renderSummary(data) {
  summaryEl.replaceChildren();
  if (!data) {
    buildPill.textContent = 'build pending';
    buildPill.dataset.cvwBuild = 'pending';
    return;
  }
  const projectLabel = data.project || 'none';
  const presetLabel = data.style_preset || 'default';
  const buildLabel = data.build_id ? ('#' + data.build_id) : 'pending';
  buildPill.textContent = buildLabel === 'pending' ? 'build pending' : ('build ' + buildLabel);
  buildPill.dataset.cvwBuild = data.build_id ? String(data.build_id) : 'pending';
  const lines = [
    ['project: ', projectLabel, ' | variant: ', data.variant || 'n/a'],
    ['theme: ', data.theme || 'n/a', ' | preset: ', presetLabel],
    ['format: ', currentFormat || 'html', ' | build: ', buildLabel],
  ];
  lines.forEach(([labelA, valueA, labelB, valueB]) => {
    const line = document.createElement('div');
    appendSummaryField(line, labelA, valueA);
    appendSummaryField(line, labelB, valueB);
    summaryEl.appendChild(line);
  });
}

function syncSummary(data, force = false) {
  const nextSummaryKey = summarySignature(data);
  if (!force && nextSummaryKey === lastSummaryKey) {
    return;
  }
  renderSummary(data);
  lastSummaryKey = nextSummaryKey;
}

function projectGuidanceSignature(data) {
  if (!data || !data.project_context) return data && data.project ? 'project::empty' : 'none';
  return JSON.stringify(data.project_context);
}

function renderProjectGuidance(data) {
  projectGuidanceEl.replaceChildren();
  projectWarningEl.replaceChildren();
  if (!data || !data.project) {
    const line = document.createElement('div');
    line.textContent = 'No project selected.';
    projectGuidanceEl.appendChild(line);
    return;
  }
  const context = data.project_context || null;
  if (!context) {
    const line = document.createElement('div');
    line.textContent = 'Project guidance unavailable.';
    projectGuidanceEl.appendChild(line);
    return;
  }
  if (context.project_context_error) {
    const line = document.createElement('div');
    line.textContent = 'Project guidance unavailable.';
    projectGuidanceEl.appendChild(line);
    const warning = document.createElement('div');
    warning.textContent = context.project_context_error;
    projectWarningEl.appendChild(warning);
    return;
  }
  const lines = [
    ['document: ', context.proposal_document_type || 'n/a', ' | patch: ', context.patch_status || 'n/a'],
    ['job files at last build: ', context.job_artifact_status || 'not checked', '', ''],
    ...(context.guidance_input_status
      ? [['guidance inputs at last build: ', context.guidance_input_status, '', '']]
      : []),
    [
      'recommended: ',
      context.recommended_variant || 'none',
      ' | status: ',
      context.recommendation_status || 'unknown',
    ],
    [
      'missing signals: ',
      (context.job_keywords_missing || []).join(', ') || 'none',
      '',
      '',
    ],
  ];
  lines.forEach(([labelA, valueA, labelB, valueB]) => {
    const line = document.createElement('div');
    appendSummaryField(line, labelA, valueA);
    if (labelB || valueB) {
      appendSummaryField(line, labelB, valueB || '');
    }
    projectGuidanceEl.appendChild(line);
  });
  if (context.recommendation_summary) {
    const line = document.createElement('div');
    appendSummaryField(line, 'recommendation: ', context.recommendation_summary);
    projectGuidanceEl.appendChild(line);
  }
  const steps = Array.isArray(context.steps) ? context.steps : [];
  steps.slice(0, 3).forEach((step, index) => {
    const line = document.createElement('div');
    appendSummaryField(line, 'step ' + String(index + 1) + ': ', step);
    projectGuidanceEl.appendChild(line);
  });
  const warnings = [];
  if (context.proposal_warning) warnings.push(context.proposal_warning);
  if (context.render_warning) warnings.push(context.render_warning);
  if (context.proposal_plan_error) warnings.push(context.proposal_plan_error);
  if (context.proposal_plan_warning) warnings.push(context.proposal_plan_warning);
  if (context.job_artifact_warning) warnings.push(context.job_artifact_warning);
  if (context.guidance_input_warning) warnings.push(context.guidance_input_warning);
  warnings.forEach((message) => {
    const line = document.createElement('div');
    line.textContent = message;
    projectWarningEl.appendChild(line);
  });
}

function syncProjectGuidance(data, force = false) {
  const nextGuidanceKey = projectGuidanceSignature(data);
  if (!force && nextGuidanceKey === lastProjectGuidanceKey) {
    return;
  }
  renderProjectGuidance(data);
  lastProjectGuidanceKey = nextGuidanceKey;
}

function nextOption(list, current) {
  if (!list || list.length === 0) return null;
  const idx = list.indexOf(current);
  return list[(idx + 1) % list.length];
}

function currentRenderState() {
  if (!state.data) return null;
  return {
    theme: state.data.theme || null,
    style_preset: state.data.style_preset || null,
    variant: state.data.variant || null,
    format: state.data.format || 'html',
    auto_pdf: !!state.data.auto_pdf,
  };
}

function normalizeRequestedState(theme, preset, variant, format, autoPdf) {
  const current = currentRenderState() || {
    theme: themeSelect.value || null,
    style_preset: presetSelect.value || null,
    variant: variantSelect.value || null,
    format: currentFormat || 'html',
    auto_pdf: !!autoPdfToggle.checked,
  };
  return {
    theme: theme || current.theme,
    style_preset: preset || null,
    variant: variant || current.variant,
    format: format || currentFormat || current.format || 'html',
    auto_pdf: typeof autoPdf === 'boolean' ? autoPdf : current.auto_pdf,
  };
}

function sameRenderState(left, right) {
  if (!left || !right) return false;
  return (
    left.theme === right.theme &&
    left.style_preset === right.style_preset &&
    left.variant === right.variant &&
    left.format === right.format &&
    left.auto_pdf === right.auto_pdf
  );
}

function syncSelect(selectEl, options, current, allowUnset = false) {
  selectEl.innerHTML = '';
  if (!options || options.length === 0) {
    const opt = document.createElement('option');
    opt.value = '';
    opt.textContent = 'none';
    selectEl.appendChild(opt);
    selectEl.value = '';
    selectEl.disabled = true;
    return;
  }
  selectEl.disabled = false;
  options.forEach((item) => {
    const opt = document.createElement('option');
    opt.value = item;
    opt.textContent = item;
    selectEl.appendChild(opt);
  });
  if (allowUnset && (!current || !options.includes(current))) {
    const opt = document.createElement('option');
    opt.value = '';
    opt.textContent = 'none';
    selectEl.insertBefore(opt, selectEl.firstChild);
  }
  selectEl.value = current && options.includes(current) ? current : (allowUnset ? '' : options[0]);
}

function renderControls(data) {
  const projectOptions = data.project ? [data.project] : [];
  syncSelect(projectSelect, projectOptions, data.project, true);
  projectSelect.disabled = true;
  syncSelect(variantSelect, data.variants || [], data.variant);
  syncSelect(themeSelect, data.themes || [], data.theme);
  const presets = (data.presets && data.presets[themeSelect.value]) || [];
  syncSelect(presetSelect, presets, data.style_preset);
  autoPdfToggle.checked = !!data.auto_pdf;
  updateFormatButtons();
}

function setControlsEnabled(enabled) {
  projectSelect.disabled = !enabled || projectSelect.disabled;
  variantSelect.disabled = !enabled || variantSelect.disabled;
  themeSelect.disabled = !enabled || themeSelect.disabled;
  presetSelect.disabled = !enabled || presetSelect.disabled;
  autoPdfToggle.disabled = !enabled;
  rebuildButton.disabled = !enabled;
  stopButton.disabled = !enabled;
}

function syncPreviewSrc() {
  if (!state.data || !state.data.outputs) return;
  const output = state.data.outputs[currentFormat] || state.data.outputs['html'];
  if (!output) return;
  const bust = state.data.build_id ? ('?v=' + state.data.build_id) : '';
  const nextPreviewSrc = '/' + output + bust;
  if (nextPreviewSrc !== currentPreviewSrc) {
    currentPreviewSrc = nextPreviewSrc;
    iframe.src = nextPreviewSrc;
  }
}

function updateFormatButtons() {
  const buttons = formatTabs.querySelectorAll('button');
  buttons.forEach((btn) => {
    const active = btn.dataset.format === currentFormat;
    if (active) {
      btn.classList.add('active');
    } else {
      btn.classList.remove('active');
    }
    btn.setAttribute('aria-pressed', active ? 'true' : 'false');
    btn.setAttribute('data-cvw-active', active ? 'true' : 'false');
  });
}

function recordRun(data) {
  if (!data || !data.build_id) return;
  if (history.some((entry) => entry.id === data.build_id)) return;
  history.unshift({ id: data.build_id, time: new Date().toLocaleTimeString() });
  if (history.length > 6) history.pop();
  runList.innerHTML = '';
  history.forEach((entry) => {
    const line = document.createElement('div');
    line.textContent = '#' + entry.id + ' @ ' + entry.time;
    runList.appendChild(line);
  });
}

function canApplyLocalFormatChange(nextState) {
  const current = currentRenderState();
  if (!state.data || !current || !state.data.outputs) {
    return false;
  }
  return (
    nextState.theme === current.theme &&
    nextState.style_preset === current.style_preset &&
    nextState.variant === current.variant &&
    nextState.auto_pdf === current.auto_pdf &&
    !!state.data.outputs[nextState.format]
  );
}

function applyLocalFormatChange(nextFormat) {
  if (!state.data || !state.data.outputs || !state.data.outputs[nextFormat]) {
    return;
  }
  currentFormat = nextFormat;
  updateFormatButtons();
  syncSummary(state.data, true);
  syncPreviewSrc();
}

function applyState(data) {
  if (!data) return;
  state.data = data;
  bindSessionChannel(data.session_id || '');
  const outputs = data.outputs || {};
  if (!currentFormat || !outputs[currentFormat]) {
    currentFormat = data.format || currentFormat || 'html';
  }
  const nextBuildId = data.build_id ? String(data.build_id) : '';
  const buildChanged = nextBuildId !== lastSeenBuildId;
  if (buildChanged) {
    lastSeenBuildId = nextBuildId;
    document.body.dataset.cvwBuildId = nextBuildId;
    recordRun(data);
  }
  const nextControlsKey = controlsSignature(data);
  if (nextControlsKey !== lastControlsKey) {
    lastControlsKey = nextControlsKey;
    renderControls(data);
  }
  const nextOverlayKey = overlaySignature(data);
  if (nextOverlayKey !== lastOverlayKey) {
    syncOverlay(data);
  }
  syncSummary(data);
  syncProjectGuidance(data);
  syncPreviewSrc();
}

function scheduleRenderRequest(nextState) {
  scheduledRenderRequest = { ...nextState };
  queuedRenderRequest = null;
  if (scheduledRenderTimer) {
    clearTimeout(scheduledRenderTimer);
  }
  scheduledRenderTimer = window.setTimeout(() => {
    const queued = scheduledRenderRequest;
    scheduledRenderRequest = null;
    scheduledRenderTimer = null;
    if (!queued || stopped || passiveController) {
      syncOverlay(state.data || {}, true);
      return;
    }
    if (renderInFlight) {
      queuedRenderRequest = queued;
      syncOverlay(state.data || {}, true);
      return;
    }
    void performRenderRequest(queued);
  }, RENDER_SETTLE_MS);
  syncOverlay(state.data || {}, true);
}

async function performRenderRequest(nextState) {
  if (!state.data || passiveController) {
    return state.data;
  }
  if (renderInFlight) {
    queuedRenderRequest = { ...nextState };
    syncOverlay(state.data || {}, true);
    return state.data;
  }
  renderInFlight = true;
  pendingAction = 'render';
  syncOverlay(state.data || {}, true);
  try {
    const res = await fetch('/api/render', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        theme: nextState.theme,
        style_preset: nextState.style_preset,
        variant: nextState.variant,
        format: nextState.format,
        auto_pdf: nextState.auto_pdf,
      }),
    });
    const payload = await res.json();
    if (!res.ok) {
      errorEl.textContent = payload.error || 'Build failed';
      errorEl.style.display = 'block';
      return state.data;
    }
    applyState(payload);
    return payload;
  } finally {
    pendingAction = null;
    renderInFlight = false;
    const data = state.data || {};
    syncOverlay(data, true);
    if (!stopped && !passiveController) {
      scheduleRefresh();
    }
    if (queuedRenderRequest) {
      const queued = queuedRenderRequest;
      queuedRenderRequest = null;
      window.setTimeout(() => {
        void performRenderRequest(queued);
      }, 0);
    }
  }
}

async function requestRender(theme, preset, variant, format, autoPdf, force = false) {
  if (!state.data || passiveController) {
    return state.data;
  }
  const nextState = normalizeRequestedState(theme, preset, variant, format, autoPdf);
  const currentState = currentRenderState();
  if (!force && canApplyLocalFormatChange(nextState)) {
    applyLocalFormatChange(nextState.format);
    return state.data;
  }
  if (!force && sameRenderState(nextState, currentState)) {
    clearScheduledRender();
    queuedRenderRequest = null;
    syncOverlay(state.data || {}, true);
    return state.data;
  }
  if (force) {
    clearScheduledRender();
    return performRenderRequest(nextState);
  }
  scheduleRenderRequest(nextState);
  return state.data;
}

async function requestStop() {
  clearScheduledRender();
  queuedRenderRequest = null;
  pendingAction = 'stop';
  syncOverlay(state.data || {}, true);
  try {
    const res = await fetch('/api/stop', { method: 'POST' });
    if (!res.ok) {
      errorEl.textContent = 'Failed to stop preview';
      errorEl.style.display = 'block';
      return;
    }
    postControllerMessage({
      type: 'stopped',
      session_id: currentSessionId,
      tab_id: controllerTabId,
    });
    if (refreshTimer) {
      clearTimeout(refreshTimer);
      refreshTimer = null;
    }
    stopped = true;
    passiveController = false;
    controllerClaimAvailable = false;
    connectionError = null;
    setControlsEnabled(false);
    const data = state.data || {};
    syncOverlay(data, true);
    closeSessionChannel();
  } finally {
    pendingAction = null;
    syncOverlay(state.data || {}, true);
  }
}

function handleRemoteStop() {
  clearScheduledRender();
  queuedRenderRequest = null;
  if (refreshTimer) {
    clearTimeout(refreshTimer);
    refreshTimer = null;
  }
  stopped = true;
  pendingAction = null;
  passiveController = false;
  controllerClaimAvailable = false;
  connectionError = null;
  setControlsEnabled(false);
  closeSessionChannel();
}

function refreshDelayMs() {
  return document.visibilityState === 'visible' ? VISIBLE_REFRESH_MS : HIDDEN_REFRESH_MS;
}

function scheduleRefresh(immediate = false) {
  if (stopped || passiveController || pendingAction === 'render') {
    return;
  }
  if (refreshTimer) {
    clearTimeout(refreshTimer);
  }
  refreshTimer = window.setTimeout(refresh, immediate ? 0 : refreshDelayMs());
}

async function refresh() {
  if (stopped || passiveController || pendingAction === 'render') return;
  try {
    const data = await fetchState();
    connectionError = null;
    applyState(data);
  } catch (_) {
    connectionError = DISCONNECTED_MESSAGE;
    const data = state.data || {};
    syncOverlay(data);
  } finally {
    if (!stopped && !passiveController) {
      scheduleRefresh();
    }
  }
}

async function handleKey(event) {
  if (stopped || passiveController) return;
  if (!state.data) return;
  if (event.metaKey || event.ctrlKey || event.altKey) return;
  const active = document.activeElement;
  const target = event.target;
  const isInteractive = (element) => {
    if (!element || typeof element.closest !== 'function') return false;
    if (element.isContentEditable) return true;
    if (['INPUT', 'SELECT', 'TEXTAREA', 'BUTTON', 'A', 'SUMMARY'].includes(element.tagName)) return true;
    return Boolean(element.closest('button,select,input,textarea,a,summary,[role="button"],[role="tab"]'));
  };
  if (isInteractive(active) || isInteractive(target)) return;
  const key = event.key.toLowerCase();
  if (key === 't') {
    const nextTheme = nextOption(state.data.themes, state.data.theme);
    const presets = state.data.presets[nextTheme] || [];
    const nextPreset = presets.includes(state.data.style_preset)
      ? state.data.style_preset
      : (presets[0] || null);
    await requestRender(nextTheme, nextPreset, state.data.variant, currentFormat, autoPdfToggle.checked);
  } else if (key === 'p') {
    const presets = state.data.presets[state.data.theme] || [];
    const nextPreset = nextOption(presets, state.data.style_preset);
    await requestRender(state.data.theme, nextPreset, state.data.variant, currentFormat, autoPdfToggle.checked);
  } else if (key === 'v') {
    const nextVariant = nextOption(state.data.variants, state.data.variant);
    await requestRender(state.data.theme, state.data.style_preset, nextVariant, currentFormat, autoPdfToggle.checked);
  } else if (key === 'f') {
    const nextFormat = nextOption(formats, currentFormat);
    await requestRender(
      state.data.theme,
      state.data.style_preset,
      state.data.variant,
      nextFormat || currentFormat,
      autoPdfToggle.checked
    );
  } else if (key === 'r') {
    await requestRender(
      state.data.theme,
      state.data.style_preset,
      state.data.variant,
      currentFormat,
      autoPdfToggle.checked,
      true
    );
  } else if (key === 'x') {
    await requestStop();
  }
}

document.addEventListener('keydown', handleKey);
iframe.addEventListener('load', () => {
  try {
    iframe.contentWindow.addEventListener('keydown', handleKey);
  } catch (_) {
    // ignore cross-origin or access errors
  }
});

themeSelect.addEventListener('change', async () => {
  if (!state.data) return;
  const presets = state.data.presets[themeSelect.value] || [];
  const nextPreset = presets[0] || null;
  await requestRender(themeSelect.value, nextPreset, state.data.variant, currentFormat, autoPdfToggle.checked);
});

presetSelect.addEventListener('change', async () => {
  if (!state.data) return;
  const value = presetSelect.value || null;
  await requestRender(themeSelect.value, value, state.data.variant, currentFormat, autoPdfToggle.checked);
});

variantSelect.addEventListener('change', async () => {
  if (!state.data) return;
  await requestRender(themeSelect.value, presetSelect.value || null, variantSelect.value, currentFormat, autoPdfToggle.checked);
});

projectSelect.addEventListener('change', async () => {
  return;
});

formatTabs.addEventListener('click', async (event) => {
  if (!state.data || passiveController) return;
  const target = event.target && typeof event.target.closest === 'function'
    ? event.target.closest('button[data-format]')
    : null;
  if (!target || !target.dataset) return;
  const nextFormat = target.dataset.format;
  if (!nextFormat) return;
  await requestRender(themeSelect.value, presetSelect.value || null, state.data.variant, nextFormat, autoPdfToggle.checked);
});

autoPdfToggle.addEventListener('change', async () => {
  if (!state.data) return;
  await requestRender(themeSelect.value, presetSelect.value || null, state.data.variant, currentFormat, autoPdfToggle.checked);
});

rebuildButton.addEventListener('click', async () => {
  if (!state.data) return;
  await requestRender(themeSelect.value, presetSelect.value || null, state.data.variant, currentFormat, autoPdfToggle.checked, true);
});

stopButton.addEventListener('click', async () => {
  await requestStop();
});

document.addEventListener('visibilitychange', () => {
  if (!stopped && document.visibilityState === 'visible') {
    scheduleRefresh(true);
  }
});
window.addEventListener('focus', () => {
  if (stopped) return;
  claimController('focus');
  scheduleRefresh(true);
});
window.addEventListener('beforeunload', () => {
  clearScheduledRender();
  if (currentSessionId) {
    postControllerMessage({
      type: 'release',
      session_id: currentSessionId,
      tab_id: controllerTabId,
    });
  }
  closeSessionChannel();
});
window.addEventListener('pagehide', () => {
  clearScheduledRender();
  if (currentSessionId) {
    postControllerMessage({
      type: 'release',
      session_id: currentSessionId,
      tab_id: controllerTabId,
    });
  }
  closeSessionChannel();
});

scheduleRefresh(true);
