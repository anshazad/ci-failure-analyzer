let activeRunId = null;

async function loadStats() {
  const r = await fetch('/api/stats');
  const d = await r.json();
  document.getElementById('m-total').textContent = d.total;
  document.getElementById('m-diagnosed').textContent = d.diagnosed;
  document.getElementById('m-rate').textContent = d.automation_rate + '%';
  document.getElementById('m-pending').textContent = d.pending;
}

async function loadFailures() {
  const r = await fetch('/api/failures');
  const failures = await r.json();
  const list = document.getElementById('failures-list');
  list.innerHTML = failures.map(f => `
    <div class="failure-row ${activeRunId === f.run_id ? 'active' : ''}"
         onclick="selectFailure(${f.run_id}, '${f.workflow}', '${f.fix_suggestion || ''}')">
      <div class="failure-info">
        <div class="failure-name">${f.workflow}</div>
        <div class="failure-meta">${f.branch} · ${f.created_at.slice(0,16)}</div>
      </div>
      <span class="badge badge-${f.status}">${f.status}</span>
    </div>
  `).join('');
}

function selectFailure(runId, workflow, fixSuggestion) {
  activeRunId = runId;
  loadFailures();

  const streamBox = document.getElementById('stream-box');
  const placeholder = document.getElementById('diagnosis-placeholder');
  const approvalBox = document.getElementById('approval-box');

  placeholder.style.display = 'none';
  streamBox.style.display = 'block';
  approvalBox.style.display = 'none';
  streamBox.innerHTML = '';

  if (window.activeEs) window.activeEs.close();	
  const es = new EventSource(`/api/diagnose-get?run_id=${runId}`);
  window.activeEs = es;

  es.addEventListener('thinking', e => {
    addLine(streamBox, 'thinking', '▸ ' + JSON.parse(e.data));
  });
  es.addEventListener('tool_start', e => {
    addLine(streamBox, 'tool_start', '⚙ ' + JSON.parse(e.data));
  });
  es.addEventListener('tool_result', e => {
    addLine(streamBox, 'tool_result', '✓ ' + JSON.parse(e.data));
  });
  es.addEventListener('stream', e => {
    addLine(streamBox, 'stream', JSON.parse(e.data));
  });
  es.addEventListener('error_event', e => {
    addLine(streamBox, 'error', JSON.parse(e.data));
    es.close();
  });
  es.addEventListener('done', e => {
    es.close();
    const result = JSON.parse(e.data);
    showApproval(runId, result);
    loadStats();
    loadFailures();
  });
}

function addLine(box, type, text) {
  const div = document.createElement('div');
  div.className = `stream-line ${type}`;
  div.textContent = text;
  box.appendChild(div);
  box.scrollTop = box.scrollHeight;
}

function showApproval(runId, result) {
  const box = document.getElementById('approval-box');
  box.style.display = 'block';
  box.innerHTML = `
    <div class="diagnosis-result">
      <div class="diagnosis-field">
        <div class="diagnosis-field-label">Root cause</div>
        <div class="diagnosis-field-value">${result.root_cause || '—'}</div>
      </div>
      <div class="diagnosis-field">
        <div class="diagnosis-field-label">Error category</div>
        <div class="diagnosis-field-value">${result.error_category || '—'}</div>
      </div>
    </div>
    <div class="approval-card">
      <div class="approval-title">⚠ Suggested fix — approve to mark resolved</div>
      <div class="approval-action">${result.fix_suggestion || 'No fix suggested'}</div>
      <div class="approval-btns">
        <button class="btn-approve" onclick="submitApproval(${runId}, true)">Approve</button>
        <button class="btn-reject" onclick="submitApproval(${runId}, false)">Reject</button>
      </div>
    </div>
  `;
}

async function submitApproval(runId, approved) {
  await fetch('/api/approve', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({run_id: runId, approved})
  });
  loadStats();
  loadFailures();
  document.getElementById('approval-box').innerHTML =
    `<div style="color:${approved ? '#3fb950' : '#f85149'};padding:12px 0;font-size:13px">
      ${approved ? '✓ Marked as resolved' : '✗ Rejected'}
    </div>`;
}

async function manualPoll() {
  document.getElementById('live-label').textContent = 'Polling...';
  await fetch('/api/poll', {method: 'POST'});
  await loadStats();
  await loadFailures();
  document.getElementById('live-label').textContent = 'Live';
}

// SSE needs a GET endpoint — add this route to main.py
// For now load via polling approach
setInterval(() => { loadStats(); loadFailures(); }, 30000);

loadStats();
loadFailures();
