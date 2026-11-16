const originForm = document.querySelector('#origin-form');
const originInput = document.querySelector('#origin-input');
const originList = document.querySelector('#origin-list');
const scanButton = document.querySelector('#scan-button');
const statusMessage = document.querySelector('#status');
const controlList = document.querySelector('#control-list');
const ORIGINS_KEY = 'allowedOrigins';
const MAX_ALLOWED_ORIGINS = 50;

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

function renderOrigins(origins) {
  originList.replaceChildren();
  for (const origin of origins) {
    const item = document.createElement('li');
    item.className = 'origin-entry';
    const label = document.createElement('span');
    label.textContent = origin;
    const removeButton = document.createElement('button');
    removeButton.type = 'button';
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

async function loadOrigins() {
  const saved = await chrome.storage.local.get(ORIGINS_KEY);
  const origins = Array.isArray(saved[ORIGINS_KEY]) ? saved[ORIGINS_KEY] : [];
  renderOrigins(origins);
  return origins;
}

async function addOrigin(event) {
  event.preventDefault();
  try {
    const origin = parseAllowedOrigin(originInput.value.trim());
    const origins = await loadOrigins();
    if (origins.includes(origin)) {
      setStatus('Ese origen ya está autorizado.');
      return;
    }
    if (origins.length >= MAX_ALLOWED_ORIGINS) {
      setStatus('Alcanzaste el máximo de orígenes autorizados.', 'error');
      return;
    }
    const updated = [...origins, origin];
    await chrome.storage.local.set({ [ORIGINS_KEY]: updated });
    originInput.value = '';
    renderOrigins(updated);
    setStatus('Origen agregado. Confirma que el sitio permite este uso.');
  } catch (error) {
    setStatus(error instanceof Error ? error.message : 'No se pudo agregar el origen.', 'error');
  }
}

async function removeOrigin(origin) {
  const origins = await loadOrigins();
  const updated = origins.filter((savedOrigin) => savedOrigin !== origin);
  await chrome.storage.local.set({ [ORIGINS_KEY]: updated });
  renderOrigins(updated);
  setStatus('Origen eliminado.');
}

function scanVisibleFormControls() {
  const controls = Array.from(
    document.querySelectorAll('form input, form textarea, form select, [role="form"] input, [role="form"] textarea, [role="form"] select'),
  );
  const groupedControls = new Map();
  const excludedTypes = new Set(['hidden', 'password', 'file', 'submit', 'button', 'reset', 'image']);
  const clean = (value) => (value || '').replace(/\s+/g, ' ').trim();

  const visible = (element) => {
    if (
      element.matches(':disabled, [readonly]') ||
      element.closest('[hidden], [aria-hidden="true"]') ||
      element.getClientRects().length === 0
    ) {
      return false;
    }
    const style = window.getComputedStyle(element);
    return style.display !== 'none' && style.visibility !== 'hidden' && style.opacity !== '0';
  };

  const labelledByText = (element) => {
    const ids = (element.getAttribute('aria-labelledby') || '').split(/\s+/).filter(Boolean);
    return clean(ids.map((id) => document.getElementById(id)?.textContent || '').join(' '));
  };

  const labelText = (element) =>
    clean(
      element.getAttribute('aria-label') ||
        labelledByText(element) ||
        Array.from(element.labels || [])
          .map((label) => label.textContent || '')
          .join(' '),
    );

  controls.forEach((element, index) => {
    const inputType = element instanceof HTMLInputElement ? element.type.toLowerCase() : '';
    if (excludedTypes.has(inputType) || !visible(element)) return;

    const isChoice = inputType === 'radio' || inputType === 'checkbox';
    const fieldset = element.closest('fieldset');
    const legend = fieldset?.querySelector('legend');
    const question =
      isChoice && legend
        ? clean(legend.textContent)
        : isChoice
          ? labelledByText(element)
          : labelText(element);
    const groupKey = isChoice
      ? `${inputType}:${element.name || `control-${index}`}`
      : `control-${index}`;

    if (!groupedControls.has(groupKey)) {
      const options =
        element instanceof HTMLSelectElement
          ? Array.from(element.options)
              .filter((option) => !option.disabled && clean(option.label))
              .map((option) => clean(option.label))
          : [];
      groupedControls.set(groupKey, {
        question,
        control_type:
          inputType || (element instanceof HTMLTextAreaElement ? 'textarea' : 'select'),
        required: element.required,
        max_length: element.maxLength > 0 ? element.maxLength : null,
        options,
      });
    }

    if (isChoice) {
      groupedControls.get(groupKey).options.push(labelText(element));
    }
  });

  return Array.from(groupedControls.values());
}

async function inspectActiveTab() {
  scanButton.disabled = true;
  controlList.replaceChildren();
  setStatus('Revisando controles visibles en la pestaña activa...');
  try {
    const origins = await loadOrigins();
    const [tab] = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
    if (!tab?.id || !tab.url) {
      throw new Error('No se pudo obtener la pestaña activa.');
    }
    const activeOrigin = new URL(tab.url).origin;
    if (!origins.includes(activeOrigin)) {
      throw new Error('El origen de esta pestaña no está en la lista autorizada.');
    }
    const results = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: scanVisibleFormControls,
    });
    const controls = results[0]?.result;
    if (!Array.isArray(controls)) {
      throw new Error('No se pudo inspeccionar esta página.');
    }
    if (!controls.length) {
      setStatus('No se encontraron controles visibles dentro de un formulario.');
      return;
    }
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
      controlList.append(item);
    }
    setStatus(`Se encontraron ${controls.length} controles. No se envió información al backend.`);
  } catch (error) {
    setStatus(error instanceof Error ? error.message : 'No se pudo inspeccionar la pestaña.', 'error');
  } finally {
    scanButton.disabled = false;
  }
}

originForm.addEventListener('submit', (event) => void addOrigin(event));
scanButton.addEventListener('click', () => void inspectActiveTab());
void loadOrigins().catch((error) => {
  setStatus(error instanceof Error ? error.message : 'No se pudo cargar la lista de orígenes.', 'error');
});
