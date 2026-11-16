const API_BASE_URL = 'http://127.0.0.1:8000/api/v1/chrome-extension';
const API_TOKEN_KEY = 'chromeExtensionApiToken';
const ORIGINS_KEY = 'allowedOrigins';
const MAX_ALLOWED_ORIGINS = 50;

const connectionForm = document.querySelector('#connection-form');
const apiTokenInput = document.querySelector('#api-token');
const disconnectButton = document.querySelector('#disconnect-button');
const connectionStatus = document.querySelector('#connection-status');
const extensionOriginLabel = document.querySelector('#extension-origin');
const profileSelect = document.querySelector('#profile-select');
const originForm = document.querySelector('#origin-form');
const originInput = document.querySelector('#origin-input');
const originList = document.querySelector('#origin-list');
const scanButton = document.querySelector('#scan-button');
const statusMessage = document.querySelector('#status');
const controlList = document.querySelector('#control-list');
const reviewSection = document.querySelector('#review-section');
const reviewQuestion = document.querySelector('#review-question');
const supportStatus = document.querySelector('#support-status');
const sourceList = document.querySelector('#source-list');
const answerDraft = document.querySelector('#answer-draft');
const reviewReason = document.querySelector('#review-reason');
const approveButton = document.querySelector('#approve-button');
const rejectButton = document.querySelector('#reject-button');
const fillButton = document.querySelector('#fill-button');

let apiToken = '';
let profiles = [];
let allowedOrigins = [];
let controls = [];
let activeTabContext = null;
let selectedControl = null;
let currentProposal = null;

const clean = (value) => (value || '').replace(/\s+/g, ' ').trim();

function isLoopback(hostname) {
  const host = hostname.toLowerCase().replace(/^\[|\]$/g, '');
  return host === 'localhost' || host === '127.0.0.1' || host === '::1';
}

function parseAllowedOrigin(rawValue) {
  const parsed = new URL(rawValue);
  if (
    parsed.username ||
    parsed.password ||
    parsed.pathname !== '/' ||
    parsed.search ||
    parsed.hash ||
    (parsed.protocol !== 'https:' &&
      !(parsed.protocol === 'http:' && isLoopback(parsed.hostname)))
  ) {
    throw new Error('Usa un origen HTTPS exacto; HTTP solo se permite para localhost.');
  }
  return parsed.origin;
}

function setStatus(message, state = 'info') {
  statusMessage.textContent = message;
  statusMessage.dataset.state = state;
}

function setConnectionStatus(message, state = 'info') {
  connectionStatus.textContent = message;
  connectionStatus.dataset.state = state;
}

function explainApiError(error) {
  if (error instanceof TypeError) {
    return `No se pudo contactar el backend. Verifica que esté activo y que CORS_ALLOWED_ORIGINS incluya ${chrome.runtime.id ? `chrome-extension://${chrome.runtime.id}` : 'el origen de la extensión'}.`;
  }
  return error instanceof Error ? error.message : 'La solicitud al backend falló.';
}

async function apiRequest(path, { method = 'GET', body } = {}) {
  const headers = { Authorization: `Bearer ${apiToken}` };
  const request = {
    method,
    headers,
    cache: 'no-store',
    credentials: 'omit',
    referrerPolicy: 'no-referrer',
  };
  if (body !== undefined) {
    headers['Content-Type'] = 'application/json';
    request.body = JSON.stringify(body);
  }
  const response = await fetch(`${API_BASE_URL}${path}`, request);
  let payload;
  try {
    payload = await response.json();
  } catch {
    throw new Error(`El backend devolvió una respuesta inválida (HTTP ${response.status}).`);
  }
  if (!response.ok) {
    const detail = payload?.detail;
    throw new Error(typeof detail === 'string' ? detail : `Solicitud rechazada (HTTP ${response.status}).`);
  }
  return payload;
}

async function loadAllowedOrigins() {
  const saved = await chrome.storage.local.get(ORIGINS_KEY);
  allowedOrigins = Array.isArray(saved[ORIGINS_KEY]) ? saved[ORIGINS_KEY] : [];
  renderOrigins();
  return allowedOrigins;
}

function renderOrigins() {
  originList.replaceChildren();
  for (const origin of allowedOrigins) {
    const item = document.createElement('li');
    item.className = 'origin-entry';
    const label = document.createElement('span');
    label.textContent = origin;
    const removeButton = document.createElement('button');
    removeButton.type = 'button';
    removeButton.className = 'secondary';
    removeButton.textContent = 'Quitar';
    removeButton.setAttribute('aria-label', `Quitar ${origin}`);
    removeButton.addEventListener('click', () => {
      void removeOrigin(origin).catch((error) => {
        setStatus(error instanceof Error ? error.message : 'No se pudo quitar el origen.', 'error');
      });
    });
    item.append(label, document.createElement('br'), removeButton);
    originList.append(item);
  }
}

async function addOrigin(event) {
  event.preventDefault();
  try {
    const origin = parseAllowedOrigin(originInput.value.trim());
    await loadAllowedOrigins();
    if (allowedOrigins.includes(origin)) {
      setStatus('Ese origen ya está autorizado.');
      return;
    }
    if (allowedOrigins.length >= MAX_ALLOWED_ORIGINS) {
      setStatus('Alcanzaste el máximo de orígenes autorizados.', 'error');
      return;
    }
    allowedOrigins = [...allowedOrigins, origin];
    await chrome.storage.local.set({ [ORIGINS_KEY]: allowedOrigins });
    originInput.value = '';
    renderOrigins();
    setStatus('Origen agregado. Confirma que el sitio permite este uso asistido.');
  } catch (error) {
    setStatus(error instanceof Error ? error.message : 'No se pudo agregar el origen.', 'error');
  }
}

async function removeOrigin(origin) {
  await loadAllowedOrigins();
  allowedOrigins = allowedOrigins.filter((savedOrigin) => savedOrigin !== origin);
  await chrome.storage.local.set({ [ORIGINS_KEY]: allowedOrigins });
  renderOrigins();
  setStatus('Origen eliminado.');
}

function renderProfiles() {
  profileSelect.replaceChildren();
  const placeholder = document.createElement('option');
  placeholder.value = '';
  placeholder.textContent = 'Selecciona tu perfil real';
  profileSelect.append(placeholder);
  for (const profile of profiles) {
    const option = document.createElement('option');
    option.value = profile.id;
    option.textContent = profile.name;
    profileSelect.append(option);
  }
  profileSelect.disabled = profiles.length === 0;
  scanButton.disabled = !apiToken || !profileSelect.value;
}

async function connectWithToken(token) {
  apiToken = token;
  try {
    const response = await apiRequest('/profiles');
    profiles = response;
    await chrome.storage.session.set({ [API_TOKEN_KEY]: apiToken });
    profileSelect.value = '';
    renderProfiles();
    disconnectButton.hidden = false;
    setConnectionStatus(`Conectado. Origen de extensión: chrome-extension://${chrome.runtime.id}`);
  } catch (error) {
    apiToken = '';
    profiles = [];
    await chrome.storage.session.remove(API_TOKEN_KEY);
    renderProfiles();
    disconnectButton.hidden = true;
    setConnectionStatus(explainApiError(error), 'error');
  }
}

async function connect(event) {
  event.preventDefault();
  const token = apiTokenInput.value.trim();
  if (!token) {
    setConnectionStatus('Introduce el token local del backend.', 'error');
    return;
  }
  apiTokenInput.value = '';
  setConnectionStatus('Verificando conexión...');
  await connectWithToken(token);
}

async function disconnect() {
  await chrome.storage.session.remove(API_TOKEN_KEY);
  apiToken = '';
  profiles = [];
  controls = [];
  activeTabContext = null;
  selectedControl = null;
  currentProposal = null;
  controlList.replaceChildren();
  reviewSection.hidden = true;
  disconnectButton.hidden = true;
  profileSelect.value = '';
  renderProfiles();
  setConnectionStatus('Desconectado. El token de esta sesión se eliminó.');
  setStatus('Conecta el backend y selecciona tu perfil para empezar.');
}

async function getActiveTabContext() {
  const [tab] = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
  if (!tab?.id || !tab.url) {
    throw new Error('No se pudo obtener la pestaña activa.');
  }
  const parsedUrl = new URL(tab.url);
  if (!allowedOrigins.includes(parsedUrl.origin)) {
    throw new Error('El origen de esta pestaña no está en la lista autorizada.');
  }
  return {
    tabId: tab.id,
    origin: parsedUrl.origin,
    pageUrl: tab.url,
  };
}

async function recordAudit(action, origin, controlType = null) {
  await apiRequest('/audit', {
    method: 'POST',
    body: {
      profile_id: profileSelect.value,
      origin,
      action,
      control_type: controlType,
    },
  });
}

function clearReview() {
  selectedControl = null;
  currentProposal = null;
  reviewSection.hidden = true;
  reviewQuestion.textContent = '';
  supportStatus.textContent = '';
  sourceList.replaceChildren();
  answerDraft.value = '';
  reviewReason.textContent = '';
  approveButton.disabled = true;
  rejectButton.disabled = true;
  fillButton.disabled = true;
}

function isFillSupported(control) {
  return [
    'text',
    'search',
    'email',
    'tel',
    'url',
    'number',
    'date',
    'month',
    'week',
    'time',
    'datetime-local',
    'textarea',
    'radio',
    'select-one',
  ].includes(control.control_type);
}

function renderControls() {
  controlList.replaceChildren();
  for (const control of controls) {
    const item = document.createElement('li');
    item.className = 'control-item';
    const question = document.createElement('span');
    question.className = 'control-question';
    question.textContent = control.question || 'Campo sin etiqueta visible';
    const meta = document.createElement('span');
    meta.className = 'control-meta';
    meta.textContent = `${control.control_type}${control.required ? ' · obligatorio' : ''}`;
    item.append(question, meta);
    if (control.options.length) {
      const options = document.createElement('p');
      options.className = 'control-options';
      options.textContent = `Opciones visibles: ${control.options.join(', ')}`;
      item.append(options);
    }
    if (control.question) {
      const proposeButton = document.createElement('button');
      proposeButton.type = 'button';
      proposeButton.textContent = 'Proponer respuesta';
      proposeButton.addEventListener('click', () => void proposeAnswer(control));
      item.append(proposeButton);
    }
    if (!isFillSupported(control)) {
      const unsupported = document.createElement('p');
      unsupported.className = 'hint';
      unsupported.textContent = 'Este tipo de control aún no admite relleno automático.';
      item.append(unsupported);
    }
    controlList.append(item);
  }
}

async function inspectActiveTab() {
  scanButton.disabled = true;
  controlList.replaceChildren();
  clearReview();
  setStatus('Revisando controles visibles en la pestaña activa...');
  try {
    await loadAllowedOrigins();
    const context = await getActiveTabContext();
    const results = await chrome.scripting.executeScript({
      target: { tabId: context.tabId },
      func: inspectOrFillVisibleControl,
      args: ['inspect', null, null, null],
    });
    const result = results[0]?.result;
    if (result?.blocked) {
      await recordAudit('policy_blocked', context.origin);
      throw new Error(
        result.blocked === 'captcha'
          ? 'Se detectó un CAPTCHA o desafío anti-bot. La extensión se detuvo.'
          : 'Se detectó una pregunta de elegibilidad o selección. Continúa manualmente.',
      );
    }
    if (!Array.isArray(result?.controls)) {
      throw new Error('No se pudo inspeccionar esta página.');
    }
    activeTabContext = context;
    controls = result.controls;
    if (!controls.length) {
      setStatus('No se encontraron controles visibles compatibles dentro de un formulario.');
      return;
    }
    renderControls();
    try {
      await recordAudit('question_inspected', context.origin);
      setStatus(`Se encontraron ${controls.length} controles. No se leyeron respuestas existentes.`);
    } catch (error) {
      setStatus(
        `Se encontraron ${controls.length} controles, pero no se pudo guardar la auditoría: ${explainApiError(error)}`,
        'error',
      );
    }
  } catch (error) {
    setStatus(explainApiError(error), 'error');
  } finally {
    scanButton.disabled = !apiToken || !profileSelect.value;
  }
}

async function ensureScannedPageIsActive() {
  const active = await getActiveTabContext();
  if (
    !activeTabContext ||
    active.tabId !== activeTabContext.tabId ||
    active.origin !== activeTabContext.origin ||
    active.pageUrl !== activeTabContext.pageUrl
  ) {
    throw new Error('La pestaña o página cambió. Inspecciónala de nuevo antes de continuar.');
  }
  return active;
}

async function proposeAnswer(control) {
  if (!profileSelect.value || !apiToken) {
    setStatus('Conecta el backend y selecciona tu perfil real.', 'error');
    return;
  }
  try {
    const context = await ensureScannedPageIsActive();
    const consent = window.confirm(
      'Se enviarán la pregunta y sus opciones al backend local. La propuesta y su contexto se guardarán en el historial y el contexto pertinente puede enviarse al proveedor de IA configurado. ¿Deseas continuar?',
    );
    if (!consent) {
      setStatus('No se envió la pregunta.');
      return;
    }
    clearReview();
    selectedControl = control;
    setStatus('Generando una propuesta con el perfil seleccionado...');
    const proposal = await apiRequest('/proposals', {
      method: 'POST',
      body: {
        profile_id: profileSelect.value,
        origin: context.origin,
        question_text: control.question,
        options: control.options,
        required: control.required,
        max_length: control.max_length,
      },
    });
    currentProposal = proposal;
    renderProposal();
    setStatus('Propuesta lista para revisión. Aún no se ha aprobado ni rellenado.');
  } catch (error) {
    setStatus(explainApiError(error), 'error');
  }
}

function renderProposal() {
  if (!currentProposal || !selectedControl) {
    clearReview();
    return;
  }
  reviewSection.hidden = false;
  reviewQuestion.textContent = selectedControl.question;
  supportStatus.textContent =
    `Respaldo: ${currentProposal.support_status} · Confianza: ${Math.round(currentProposal.confidence * 100)}%`;
  answerDraft.value = currentProposal.suggested_answer;
  answerDraft.disabled = currentProposal.status === 'approved';
  reviewReason.textContent = currentProposal.review_reason || '';
  sourceList.replaceChildren();
  for (const source of currentProposal.sources || []) {
    const item = document.createElement('li');
    item.textContent = `${source.source_type}: ${source.excerpt}`;
    sourceList.append(item);
  }
  approveButton.disabled =
    currentProposal.status === 'approved' ||
    currentProposal.support_status !== 'supported' ||
    !currentProposal.suggested_answer.trim();
  rejectButton.disabled = ['approved', 'rejected'].includes(currentProposal.status);
  fillButton.hidden = currentProposal.status !== 'approved';
  fillButton.disabled =
    currentProposal.status !== 'approved' ||
    !isFillSupported(selectedControl) ||
    selectedControl.filled === true;
  if (currentProposal.status !== 'approved') {
    fillButton.hidden = true;
  }
}

async function approveProposal() {
  if (!currentProposal?.proposal_id || !selectedControl || !profileSelect.value) return;
  approveButton.disabled = true;
  try {
    const context = await ensureScannedPageIsActive();
    let proposal = currentProposal;
    const editedAnswer = answerDraft.value.trim();
    if (editedAnswer !== proposal.suggested_answer) {
      proposal = await apiRequest(`/proposals/${proposal.proposal_id}/correct`, {
        method: 'POST',
        body: {
          profile_id: profileSelect.value,
          origin: context.origin,
          correction: editedAnswer,
        },
      });
      currentProposal = proposal;
    }
    if (proposal.support_status !== 'supported') {
      throw new Error('No se puede aprobar una propuesta sin respaldo suficiente.');
    }
    currentProposal = await apiRequest(`/proposals/${proposal.proposal_id}/approve`, {
      method: 'POST',
      body: {
        profile_id: profileSelect.value,
        origin: context.origin,
      },
    });
    renderProposal();
    setStatus('Aprobada por ti. Rellenar el campo requiere otra acción explícita.');
  } catch (error) {
    approveButton.disabled = false;
    setStatus(explainApiError(error), 'error');
  }
}

async function rejectProposal() {
  if (!currentProposal?.proposal_id || !profileSelect.value) return;
  rejectButton.disabled = true;
  try {
    const context = await ensureScannedPageIsActive();
    currentProposal = await apiRequest(`/proposals/${currentProposal.proposal_id}/reject`, {
      method: 'POST',
      body: {
        profile_id: profileSelect.value,
        origin: context.origin,
      },
    });
    renderProposal();
    setStatus('Propuesta rechazada; no se rellenó ningún campo.');
  } catch (error) {
    rejectButton.disabled = false;
    setStatus(explainApiError(error), 'error');
  }
}

async function fillApprovedAnswer() {
  if (
    currentProposal?.status !== 'approved' ||
    !selectedControl ||
    !isFillSupported(selectedControl)
  ) {
    return;
  }
  fillButton.disabled = true;
  try {
    const context = await ensureScannedPageIsActive();
    const answer = currentProposal.suggested_answer;
    const results = await chrome.scripting.executeScript({
      target: { tabId: context.tabId },
      func: inspectOrFillVisibleControl,
      args: ['fill', selectedControl.control_index, selectedControl.signature, answer],
    });
    const result = results[0]?.result;
    if (!result?.verified) {
      throw new Error(
        result?.error === 'blocked'
          ? 'Se detectó un CAPTCHA o control restringido; no se rellenó el campo.'
          : 'El formulario cambió o la respuesta no coincide exactamente con el campo inspeccionado.',
      );
    }
    selectedControl.filled = true;
    renderProposal();
    setStatus('Campo aprobado rellenado y verificado. El formulario no se envió.');
    await recordAudit('field_filled', context.origin, selectedControl.control_type);
  } catch (error) {
    fillButton.disabled = false;
    setStatus(explainApiError(error), 'error');
  }
}

function inspectOrFillVisibleControl(action, targetIndex, expectedSignature, answer) {
  const elements = Array.from(
    document.querySelectorAll(
      'form input, form textarea, form select, [role="form"] input, [role="form"] textarea, [role="form"] select',
    ),
  );
  const captchaSelectors = [
    'iframe[src*="recaptcha" i]',
    'iframe[src*="hcaptcha" i]',
    '[class*="g-recaptcha" i]',
    '[class*="h-captcha" i]',
    '[id*="captcha" i]',
    '[name*="captcha" i]',
  ];
  if (captchaSelectors.some((selector) => document.querySelector(selector))) {
    return { blocked: 'captcha' };
  }

  const excludedTypes = new Set(['hidden', 'password', 'file', 'submit', 'button', 'reset', 'image']);
  const cleanText = (value) => (value || '').replace(/\s+/g, ' ').trim();
  const normalizeChoice = (value) =>
    cleanText(value)
      .normalize('NFD')
      .replace(/[\u0300-\u036f]/g, '')
      .toLocaleLowerCase();
  const isVisible = (element) => {
    for (let ancestor = element; ancestor; ancestor = ancestor.parentElement) {
      if (ancestor.hidden || ancestor.getAttribute('aria-hidden') === 'true') return false;
      const style = window.getComputedStyle(ancestor);
      if (
        style.display === 'none' ||
        style.visibility === 'hidden' ||
        style.visibility === 'collapse' ||
        style.opacity === '0'
      ) {
        return false;
      }
    }
    return element.getClientRects().length > 0;
  };
  const labelledByText = (element) => {
    const ids = (element.getAttribute('aria-labelledby') || '').split(/\s+/).filter(Boolean);
    return cleanText(ids.map((id) => document.getElementById(id)?.textContent || '').join(' '));
  };
  const labelText = (element) =>
    cleanText(
      element.getAttribute('aria-label') ||
        labelledByText(element) ||
        Array.from(element.labels || [])
          .map((label) => label.textContent || '')
          .join(' '),
    );
  const groupedControls = new Map();

  elements.forEach((element, index) => {
    const inputType = element instanceof HTMLInputElement ? element.type.toLowerCase() : '';
    if (excludedTypes.has(inputType) || !isVisible(element) || element.matches(':disabled, [readonly]')) {
      return;
    }
    const isChoice = inputType === 'radio' || inputType === 'checkbox';
    const fieldset = element.closest('fieldset');
    const legend = fieldset?.querySelector('legend');
    const question =
      isChoice && legend
        ? cleanText(legend.textContent)
        : isChoice
          ? labelledByText(element)
          : labelText(element);
    const controlType =
      element instanceof HTMLSelectElement
        ? element.multiple
          ? 'select-multiple'
          : 'select-one'
        : inputType || (element instanceof HTMLTextAreaElement ? 'textarea' : 'text');
    const formIndex = element.form ? Array.from(document.forms).indexOf(element.form) : -1;
    const fieldsetIndex = fieldset
      ? Array.from(document.querySelectorAll('fieldset')).indexOf(fieldset)
      : -1;
    const groupKey =
      isChoice && element.name
        ? `${controlType}:${formIndex}:${fieldsetIndex}:${element.name}`
        : `element:${index}`;
    if (!groupedControls.has(groupKey)) {
      groupedControls.set(groupKey, {
        control_index: index,
        indexes: [],
        question,
        control_type: controlType,
        required: false,
        max_length: null,
        options: [],
        choiceIndexes: [],
      });
    }
    const group = groupedControls.get(groupKey);
    group.indexes.push(index);
    group.required = group.required || element.required;
    if (element.maxLength > 0) group.max_length = element.maxLength;

    if (element instanceof HTMLSelectElement) {
      Array.from(element.options).forEach((option, optionIndex) => {
        if (!option.disabled && option.value !== '' && cleanText(option.label)) {
          group.options.push(cleanText(option.label));
          group.choiceIndexes.push(optionIndex);
        }
      });
    } else if (isChoice) {
      group.options.push(labelText(element));
      group.choiceIndexes.push(index);
    }
  });

  const controls = Array.from(groupedControls.values()).map((group) => ({
    control_index: group.control_index,
    indexes: group.indexes,
    question: group.question,
    control_type: group.control_type,
    required: group.required,
    max_length: group.max_length,
    options: group.options,
    signature: JSON.stringify([
      group.control_index,
      group.indexes,
      group.question,
      group.control_type,
      group.required,
      group.max_length,
      group.options,
    ]),
    choiceIndexes: group.choiceIndexes,
  }));
  const questionText = controls.map((control) => control.question).join(' ');
  if (/\b(captcha|recaptcha|hcaptcha)\b/i.test(questionText)) {
    return { blocked: 'captcha' };
  }
  if (/\b(eligibility|eligible|qualif(?:y|ying|ication)|screen(?:er|ing))\b/i.test(questionText)) {
    return { blocked: 'eligibility' };
  }
  if (action !== 'fill') {
    return {
      controls: controls.map(({ choiceIndexes, ...control }) => control),
    };
  }

  const control = controls.find((candidate) => candidate.control_index === targetIndex);
  if (!control || control.signature !== expectedSignature) {
    return { error: 'stale' };
  }
  if (!isVisible(elements[control.control_index])) {
    return { error: 'stale' };
  }
  const normalizedAnswer = normalizeChoice(answer);
  if (!normalizedAnswer) return { error: 'empty' };

  if (control.control_type === 'radio' || control.control_type === 'select-one') {
    const matchingOptions = control.options
      .map((label, index) => ({ label, optionIndex: control.choiceIndexes[index] }))
      .filter((option) => normalizeChoice(option.label) === normalizedAnswer);
    if (matchingOptions.length !== 1) return { error: 'option_mismatch' };
    const match = matchingOptions[0];
    if (control.control_type === 'radio') {
      const element = elements[match.optionIndex];
      if (!element || !isVisible(element) || element.matches(':disabled')) return { error: 'stale' };
      element.checked = true;
      element.dispatchEvent(new Event('input', { bubbles: true }));
      element.dispatchEvent(new Event('change', { bubbles: true }));
      return { verified: element.checked };
    }
    const element = elements[control.control_index];
    const option = element?.options[match.optionIndex];
    if (!element || !option || option.disabled) return { error: 'stale' };
    option.selected = true;
    element.dispatchEvent(new Event('input', { bubbles: true }));
    element.dispatchEvent(new Event('change', { bubbles: true }));
    return { verified: option.selected && !element.multiple };
  }

  if (
    ![
      'text',
      'search',
      'email',
      'tel',
      'url',
      'number',
      'date',
      'month',
      'week',
      'time',
      'datetime-local',
      'textarea',
    ].includes(control.control_type)
  ) {
    return { error: 'unsupported' };
  }
  if (control.max_length && answer.length > control.max_length) return { error: 'too_long' };
  const element = elements[control.control_index];
  if (!element || !isVisible(element) || element.matches(':disabled, [readonly]')) {
    return { error: 'stale' };
  }
  const valueSetter = Object.getOwnPropertyDescriptor(Object.getPrototypeOf(element), 'value')?.set;
  if (!valueSetter) return { error: 'unsupported' };
  valueSetter.call(element, answer);
  element.dispatchEvent(new Event('input', { bubbles: true }));
  element.dispatchEvent(new Event('change', { bubbles: true }));
  return { verified: element.value === answer };
}

async function approveProposal() {
  if (!currentProposal?.proposal_id || !selectedControl || !profileSelect.value) return;
  approveButton.disabled = true;
  try {
    const context = await ensureScannedPageIsActive();
    let proposal = currentProposal;
    const editedAnswer = answerDraft.value.trim();
    if (editedAnswer !== proposal.suggested_answer) {
      proposal = await apiRequest(`/proposals/${proposal.proposal_id}/correct`, {
        method: 'POST',
        body: {
          profile_id: profileSelect.value,
          origin: context.origin,
          correction: editedAnswer,
        },
      });
      currentProposal = proposal;
    }
    if (proposal.support_status !== 'supported') {
      throw new Error('No se puede aprobar una propuesta sin respaldo suficiente.');
    }
    currentProposal = await apiRequest(`/proposals/${proposal.proposal_id}/approve`, {
      method: 'POST',
      body: {
        profile_id: profileSelect.value,
        origin: context.origin,
      },
    });
    renderProposal();
    setStatus('Aprobada por ti. Rellenar el campo requiere otra acción explícita.');
  } catch (error) {
    approveButton.disabled = false;
    setStatus(explainApiError(error), 'error');
  }
}

async function rejectProposal() {
  if (!currentProposal?.proposal_id || !profileSelect.value) return;
  rejectButton.disabled = true;
  try {
    const context = await ensureScannedPageIsActive();
    currentProposal = await apiRequest(`/proposals/${currentProposal.proposal_id}/reject`, {
      method: 'POST',
      body: {
        profile_id: profileSelect.value,
        origin: context.origin,
      },
    });
    renderProposal();
    setStatus('Propuesta rechazada; no se rellenó ningún campo.');
  } catch (error) {
    rejectButton.disabled = false;
    setStatus(explainApiError(error), 'error');
  }
}

async function fillApprovedAnswer() {
  if (
    currentProposal?.status !== 'approved' ||
    !selectedControl ||
    !isFillSupported(selectedControl)
  ) {
    return;
  }
  fillButton.disabled = true;
  try {
    const context = await ensureScannedPageIsActive();
    if (
      !window.confirm(
        `Se rellenará “${selectedControl.question}” con la respuesta aprobada. No se enviará ni avanzará el formulario. ¿Continuar?`,
      )
    ) {
      fillButton.disabled = false;
      setStatus('No se rellenó el campo.');
      return;
    }
    const results = await chrome.scripting.executeScript({
      target: { tabId: context.tabId },
      func: inspectOrFillVisibleControl,
      args: [
        'fill',
        selectedControl.control_index,
        selectedControl.signature,
        currentProposal.suggested_answer,
      ],
    });
    const result = results[0]?.result;
    if (!result?.verified) {
      throw new Error(
        result?.error === 'blocked'
          ? 'Se detectó un CAPTCHA o control restringido; no se rellenó el campo.'
          : 'El formulario cambió o la respuesta no coincide exactamente con el campo inspeccionado.',
      );
    }
    selectedControl.filled = true;
    renderProposal();
    setStatus('Campo aprobado rellenado y verificado. El formulario no se envió.');
    try {
      await recordAudit('field_filled', context.origin, selectedControl.control_type);
    } catch (error) {
      setStatus(
        `El campo se rellenó y verificó, pero no se pudo registrar la auditoría: ${explainApiError(error)}`,
        'error',
      );
    }
  } catch (error) {
    fillButton.disabled = false;
    setStatus(explainApiError(error), 'error');
  }
}

function renderProposal() {
  if (!currentProposal || !selectedControl) {
    clearReview();
    return;
  }
  reviewSection.hidden = false;
  reviewQuestion.textContent = selectedControl.question;
  supportStatus.textContent =
    `Respaldo: ${currentProposal.support_status} · Confianza: ${Math.round(currentProposal.confidence * 100)}%`;
  answerDraft.value = currentProposal.suggested_answer;
  answerDraft.disabled = currentProposal.status === 'approved';
  reviewReason.textContent = currentProposal.review_reason || '';
  sourceList.replaceChildren();
  for (const source of currentProposal.sources || []) {
    const item = document.createElement('li');
    item.textContent = `${source.source_type}: ${source.excerpt}`;
    sourceList.append(item);
  }
  approveButton.disabled =
    currentProposal.status === 'approved' ||
    currentProposal.support_status !== 'supported' ||
    !currentProposal.suggested_answer.trim();
  rejectButton.disabled = ['approved', 'rejected'].includes(currentProposal.status);
  fillButton.hidden = currentProposal.status !== 'approved';
  fillButton.disabled =
    currentProposal.status !== 'approved' ||
    !isFillSupported(selectedControl) ||
    selectedControl.filled === true;
  if (currentProposal.status !== 'approved') {
    fillButton.hidden = true;
  }
}

async function ensureScannedPageIsActive() {
  const active = await getActiveTabContext();
  if (
    !activeTabContext ||
    active.tabId !== activeTabContext.tabId ||
    active.origin !== activeTabContext.origin ||
    active.pageUrl !== activeTabContext.pageUrl
  ) {
    throw new Error('La pestaña o página cambió. Inspecciónala de nuevo antes de continuar.');
  }
  return active;
}

async function proposeAnswer(control) {
  if (!profileSelect.value || !apiToken) {
    setStatus('Conecta el backend y selecciona tu perfil real.', 'error');
    return;
  }
  try {
    const context = await ensureScannedPageIsActive();
    const consent = window.confirm(
      'Se enviarán la pregunta y sus opciones al backend local. La propuesta y su contexto se guardarán en el historial y el contexto pertinente puede enviarse al proveedor de IA configurado. ¿Deseas continuar?',
    );
    if (!consent) {
      setStatus('No se envió la pregunta.');
      return;
    }
    clearReview();
    selectedControl = control;
    setStatus('Generando una propuesta con el perfil seleccionado...');
    const proposal = await apiRequest('/proposals', {
      method: 'POST',
      body: {
        profile_id: profileSelect.value,
        origin: context.origin,
        question_text: control.question,
        options: control.options,
        required: control.required,
        max_length: control.max_length,
      },
    });
    currentProposal = proposal;
    renderProposal();
    setStatus('Propuesta lista para revisión. Aún no se ha aprobado ni rellenado.');
  } catch (error) {
    setStatus(explainApiError(error), 'error');
  }
}

function handleProfileChange() {
  controls = [];
  activeTabContext = null;
  controlList.replaceChildren();
  clearReview();
  scanButton.disabled = !apiToken || !profileSelect.value;
  if (!profileSelect.value) {
    setStatus('Selecciona tu perfil real.');
  }
}

connectionForm.addEventListener('submit', (event) => void connect(event));
disconnectButton.addEventListener('click', () => void disconnect());
originForm.addEventListener('submit', (event) => void addOrigin(event));
scanButton.addEventListener('click', () => void inspectActiveTab());
profileSelect.addEventListener('change', handleProfileChange);
approveButton.addEventListener('click', () => void approveProposal());
rejectButton.addEventListener('click', () => void rejectProposal());
fillButton.addEventListener('click', () => void fillApprovedAnswer());
extensionOriginLabel.textContent = `chrome-extension://${chrome.runtime.id}`;

void loadAllowedOrigins().catch((error) => {
  setStatus(error instanceof Error ? error.message : 'No se pudo cargar la lista de orígenes.', 'error');
});
void chrome.storage.session
  .get(API_TOKEN_KEY)
  .then((saved) => {
    const storedToken = saved[API_TOKEN_KEY];
    if (typeof storedToken === 'string' && storedToken) {
      return connectWithToken(storedToken);
    }
  })
  .catch((error) => {
    setConnectionStatus(error instanceof Error ? error.message : 'No se pudo leer el token local.', 'error');
  });
