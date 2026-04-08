async function loadContext() {
  const response = await fetch('/api/context');
  if (!response.ok) {
    throw new Error('Could not load Fabric context.');
  }
  return response.json();
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
  for (const c of capacities || []) {
    const opt = document.createElement('option');
    opt.value = c.id || '';
    opt.textContent = c.displayName || c.id;
    select.appendChild(opt);
  }
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

  setStatus('Provisioning in progress. This can take a few minutes...');

  const response = await fetch('/api/provision', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });

  const result = await response.json();
  if (!response.ok) {
    setStatus('Provisioning failed.', result);
    return;
  }

  setStatus('Provisioning complete.', result);
}

(async function init() {
  try {
    wireWorkspaceModeToggle();
    const context = await loadContext();
    populateWorkspaces(context.workspaces);
    populateCapacities(context.capacities);

    document.getElementById('provision-form').addEventListener('submit', handleProvisionSubmit);
    setStatus('Context loaded. Select capacity and workspace options, then provision.');
  } catch (error) {
    setStatus(error.message || 'Initialization failed.');
  }
})();
