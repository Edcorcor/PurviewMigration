async function loadContext() {
  const response = await fetch('/api/context');
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.detail || 'Could not load Fabric context.');
  }
  return response.json();
}

function setBusy(isBusy) {
  const submitButton = document.getElementById('submit-button');
  const refreshButton = document.getElementById('refresh-context');
  if (submitButton) {
    submitButton.disabled = isBusy;
    submitButton.textContent = isBusy ? 'Provisioning...' : 'Provision Workspace + Environment + Notebook';
  }
  if (refreshButton) {
    refreshButton.disabled = isBusy;
  }
}

function populateWorkspaces(workspaces) {
  const select = document.getElementById('workspace_id');
  select.innerHTML = '';
  if (!workspaces || workspaces.length === 0) {
    const opt = document.createElement('option');
    opt.value = '';
    opt.textContent = 'No workspaces found';
    select.appendChild(opt);
    return;
  }

  for (const ws of workspaces) {
    const opt = document.createElement('option');
    opt.value = ws.id;
    opt.textContent = `${ws.displayName} (${ws.type || 'Workspace'})`;
    select.appendChild(opt);
  }
}

function populateCapacities(capacities) {
  const select = document.getElementById('capacity_id');
  select.innerHTML = '<option value="">No explicit capacity</option>';
  for (const c of capacities || []) {
    const opt = document.createElement('option');
    opt.value = c.id || '';
    opt.textContent = c.displayName || c.id;
    select.appendChild(opt);
  }
}

function setContextSummary(context) {
  const el = document.getElementById('context-summary');
  if (!el) {
    return;
  }

  const summary = context.summary || {};
  el.textContent = `Tenant ${context.tenant?.tenant_id || 'unknown'} | ${summary.workspace_count || 0} workspace(s) | ${summary.capacity_count || 0} capacity option(s)`;
}

function setStatus(message, payload) {
  const el = document.getElementById('status');
  const body = payload ? `\n\n${JSON.stringify(payload, null, 2)}` : '';
  el.textContent = `${message}${body}`;
}

function wireWorkspaceModeToggle() {
  const existingGroup = document.getElementById('existing-workspace-group');
  const createGroup = document.getElementById('create-workspace-group');

  document.querySelectorAll('input[name="workspace_mode"]').forEach((input) => {
    input.addEventListener('change', () => {
      if (input.value === 'create' && input.checked) {
        existingGroup.classList.add('hidden');
        createGroup.classList.remove('hidden');
      } else if (input.value === 'existing' && input.checked) {
        createGroup.classList.add('hidden');
        existingGroup.classList.remove('hidden');
      }
    });
  });
}

async function handleProvisionSubmit(event) {
  event.preventDefault();

  const mode = document.querySelector('input[name="workspace_mode"]:checked').value;
  const payload = {
    workspace_mode: mode,
    workspace_id: document.getElementById('workspace_id').value || null,
    workspace_name: document.getElementById('workspace_name').value || null,
    capacity_id: document.getElementById('capacity_id').value || null,
    environment_name: document.getElementById('environment_name').value || 'PurviewAuditSpark',
    notebook_name: document.getElementById('notebook_name').value || '00-Setup'
  };

  setBusy(true);
  setStatus('Provisioning in progress. This can take a few minutes...');

  try {
    const response = await fetch('/api/provision', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });

    const result = await response.json().catch(() => ({}));
    if (!response.ok) {
      setStatus('Provisioning failed.', result);
      return;
    }

    setStatus('Provisioning complete.', result);
    const context = await loadContext();
    populateWorkspaces(context.workspaces);
    populateCapacities(context.capacities);
    setContextSummary(context);
  } catch (error) {
    setStatus(error.message || 'Provisioning failed unexpectedly.');
  } finally {
    setBusy(false);
  }
}

async function refreshContext() {
  setBusy(true);
  setStatus('Refreshing Fabric context...');
  try {
    const context = await loadContext();
    populateWorkspaces(context.workspaces);
    populateCapacities(context.capacities);
    setContextSummary(context);
    setStatus('Context loaded. Select capacity and workspace options, then provision.');
  } catch (error) {
    setStatus(error.message || 'Initialization failed.');
  } finally {
    setBusy(false);
  }
}

(async function init() {
  try {
    wireWorkspaceModeToggle();
    document.getElementById('refresh-context').addEventListener('click', refreshContext);
    await refreshContext();

    document.getElementById('provision-form').addEventListener('submit', handleProvisionSubmit);
  } catch (error) {
    setStatus(error.message || 'Initialization failed.');
  }
})();
