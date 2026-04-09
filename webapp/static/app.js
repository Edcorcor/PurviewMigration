let cachedContext = null;

function fabricWorkspaceConfigured() {
  return Boolean(cachedContext?.fabric_workspace?.configured);
}

async function loadContext() {
  const response = await fetch('/api/context');
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.detail || 'Could not load Azure context.');
  }
  return response.json();
}

function setBusy(isBusy) {
  const submitButton = document.getElementById('save-selection-button');
  const refreshButton = document.getElementById('refresh-context');
  const ensureButton = document.getElementById('ensure-workspace');
  if (submitButton) {
    submitButton.disabled = isBusy;
    submitButton.textContent = isBusy ? 'Saving...' : 'Save Selection';
  }
  if (refreshButton) {
    refreshButton.disabled = isBusy;
  }
  if (ensureButton) {
    ensureButton.disabled = isBusy;
  }
}

function populateSubscriptions(subscriptions) {
  const select = document.getElementById('subscription_id');
  select.innerHTML = '';
  if (!subscriptions || subscriptions.length === 0) {
    const opt = document.createElement('option');
    opt.value = '';
    opt.textContent = 'No subscriptions found';
    select.appendChild(opt);
    return;
  }

  for (const sub of subscriptions) {
    const opt = document.createElement('option');
    opt.value = sub.subscriptionId;
    opt.textContent = `${sub.displayName} (${sub.subscriptionId})`;
    select.appendChild(opt);
  }
}

function populateKeyVaults(keyVaults) {
  const select = document.getElementById('key_vault_id');
  select.innerHTML = '';
  if (!keyVaults || keyVaults.length === 0) {
    const opt = document.createElement('option');
    opt.value = '';
    opt.textContent = 'No key vaults found';
    select.appendChild(opt);
    return;
  }

  for (const vault of keyVaults) {
    const opt = document.createElement('option');
    opt.value = vault.id || '';
    opt.textContent = `${vault.name} [${vault.subscription_id}]`;
    opt.dataset.vaultName = vault.name || '';
    opt.dataset.subscriptionId = vault.subscription_id || '';
    select.appendChild(opt);
  }
}

function populatePurviewAccounts(purview) {
  const select = document.getElementById('primary_purview_name');
  if (!select) {
    return;
  }

  select.innerHTML = '';
  const accounts = purview?.accounts || [];
  if (accounts.length === 0) {
    const opt = document.createElement('option');
    opt.value = '';
    opt.textContent = 'No Purview accounts found';
    select.appendChild(opt);
    return;
  }

  for (const account of accounts) {
    const opt = document.createElement('option');
    opt.value = account.name || '';
    opt.textContent = `${account.name} [${account.subscription_id}]`;
    if (purview?.primary_account_name && purview.primary_account_name === account.name) {
      opt.selected = true;
    }
    select.appendChild(opt);
  }
}

function setContextSummary(context) {
  const el = document.getElementById('context-summary');
  if (!el) {
    return;
  }

  const summary = context.summary || {};
  el.textContent = `Tenant ${context.tenant?.tenant_id || 'unknown'} | ${summary.subscription_count || 0} subscription(s) | ${summary.key_vault_count || 0} key vault(s) | ${summary.purview_account_count || 0} Purview account(s)`;
}

function setFabricWorkspaceSummary(context) {
  const el = document.getElementById('fabric-workspace-summary');
  if (!el) {
    return;
  }

  const ws = context.fabric_workspace || {};
  if (!ws.configured) {
    el.textContent = 'No Fabric workspace configured yet. Click Ensure Fabric Workspace to create one now and reuse it on future runs.';
    return;
  }

  el.textContent = `Workspace ${ws.workspace_name} (${ws.workspace_id}) | Status: ${ws.status || 'REUSED'}`;
}

function setStatus(message, payload) {
  const el = document.getElementById('status');
  const body = payload ? `\n\n${JSON.stringify(payload, null, 2)}` : '';
  el.textContent = `${message}${body}`;
}

function renderSteps(steps) {
  const container = document.getElementById('steps-list');
  container.innerHTML = '';

  for (const step of steps || []) {
    const row = document.createElement('div');
    row.className = 'step-row';

    const info = document.createElement('div');
    info.className = 'step-info';
    info.innerHTML = `
      <h3>${step.title}</h3>
      <p>${step.description}</p>
      <p><strong>Notebook:</strong> ${step.notebook}</p>
      <p><strong>Status:</strong> ${step.status}</p>
    `;

    const action = document.createElement('div');
    action.className = 'step-action';
    const button = document.createElement('button');
    button.className = 'button secondary';
    button.type = 'button';
    button.textContent = 'Run Step';
    button.addEventListener('click', () => runStep(step.id));
    action.appendChild(button);

    row.appendChild(info);
    row.appendChild(action);
    container.appendChild(row);
  }
}

function getSelection() {
  const subscriptionId = document.getElementById('subscription_id').value;
  const vaultSelect = document.getElementById('key_vault_id');
  const vaultOption = vaultSelect.options[vaultSelect.selectedIndex];

  return {
    subscription_id: subscriptionId,
    key_vault_id: vaultSelect.value || '',
    key_vault_name: vaultOption?.dataset.vaultName || '',
    primary_purview_name: document.getElementById('primary_purview_name')?.value || ''
  };
}

async function runStep(stepId) {
  if (!fabricWorkspaceConfigured()) {
    setStatus('Ensure Fabric workspace first, then run guided steps.');
    return;
  }

  const selection = getSelection();
  if (!selection.subscription_id) {
    setStatus('Choose a subscription before running a step.');
    return;
  }
  if (!selection.key_vault_id) {
    setStatus('Choose a key vault before running a step.');
    return;
  }

  const proceed = window.confirm(`Run ${stepId}? You will be prompted to execute the matching notebook step.`);
  if (!proceed) {
    return;
  }

  const payload = {
    step_id: stepId,
    ...selection
  };

  setBusy(true);
  setStatus(`Running ${stepId}...`);

  try {
    const response = await fetch('/api/steps/run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });

    const result = await response.json().catch(() => ({}));
    if (!response.ok) {
      setStatus('Step run failed.', result);
      return;
    }

    setStatus(result.prompt || 'Step processed.', result);
    await refreshContext();
  } catch (error) {
    setStatus(error.message || 'Step run failed unexpectedly.');
  } finally {
    setBusy(false);
  }
}

async function handleSelectionSave(event) {
  event.preventDefault();
  const payload = {
    ...getSelection()
  };

  if (!payload.subscription_id || !payload.key_vault_id) {
    setStatus('Pick a subscription and key vault, then save your selection.');
    return;
  }

  if (!payload.primary_purview_name) {
    setStatus('Select a primary Purview account before saving selection.');
    return;
  }

  try {
    const response = await fetch('/api/purview/selection', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ primary_account_name: payload.primary_purview_name })
    });
    const result = await response.json().catch(() => ({}));
    if (!response.ok) {
      setStatus('Could not save Purview primary selection.', result);
      return;
    }
  } catch (error) {
    setStatus(error.message || 'Could not save Purview selection.');
    return;
  }

  setStatus('Selection saved. Use Run Step to proceed through each notebook stage.', payload);
}

async function refreshContext() {
  setBusy(true);
  setStatus('Refreshing Azure context...');
  try {
    const context = await loadContext();
    cachedContext = context;
    populateSubscriptions(context.subscriptions);
    populateKeyVaults(context.key_vaults);
    populatePurviewAccounts(context.purview);
    renderSteps(context.steps);
    setContextSummary(context);
    setFabricWorkspaceSummary(context);
    setStatus('Context loaded. Select your subscription and key vault, then run each step.');
  } catch (error) {
    setStatus(error.message || 'Initialization failed.');
  } finally {
    setBusy(false);
  }
}

async function ensureWorkspace() {
  setBusy(true);
  setStatus('Ensuring Fabric workspace and bootstrapping Spark environment/notebooks...');
  try {
    const response = await fetch('/api/fabric/workspace/ensure', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' }
    });
    const result = await response.json().catch(() => ({}));
    if (!response.ok) {
      setStatus('Could not ensure Fabric workspace.', result);
      return;
    }

    setStatus('Fabric workspace and assets are ready and persisted for reuse.', result);
    await refreshContext();
  } catch (error) {
    setStatus(error.message || 'Could not ensure Fabric workspace.');
  } finally {
    setBusy(false);
  }
}

(async function init() {
  try {
    document.getElementById('refresh-context').addEventListener('click', refreshContext);
    document.getElementById('ensure-workspace').addEventListener('click', ensureWorkspace);
    await refreshContext();

    document.getElementById('guided-form').addEventListener('submit', handleSelectionSave);
  } catch (error) {
    setStatus(error.message || 'Initialization failed.');
  }
})();
