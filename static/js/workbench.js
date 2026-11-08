/* Evidence workbench. All dynamic text is rendered with textContent or AM.markdown. */
(() => {
  'use strict';
  const { $, $$, request, node, markdown, toast } = AM;
  const ACTIVE = new Set(['QUEUED', 'RUNNING', 'WAITING_USER']);
  const RETRYABLE = new Set(['FAILED', 'PARTIAL', 'CANCELLED', 'ABSTAINED']);
  const TERMINAL = new Set(['SUCCEEDED', 'COMPLETED', 'PARTIAL', 'ABSTAINED', 'FAILED', 'CANCELLED']);

  const readJson = id => {
    const host = document.getElementById(id);
    if (!host) return [];
    try { return JSON.parse(host.textContent || '[]'); } catch (_error) { return []; }
  };

  const workspaceSelect = $('#workbench-workspace-select');
  const taskList = $('#workbench-task-list');
  const result = $('#workbench-result');
  const queryInput = $('#workbench-query');
  const taskType = $('#workbench-task-type');
  const taskMode = $('#workbench-task-mode');
  const submitButton = $('#workbench-submit');
  const inlineError = $('#workbench-inline-error');
  const uploadInput = $('#workbench-file-input');
  const uploadButton = $('#workbench-upload-button');
  const uploadStatus = $('#workbench-upload-status');
  const uploadZone = $('#workbench-upload-zone');
  const initialTasks = readJson('workbench-tasks-data');
  let currentRunId = '';
  let pollTimer = null;
  let pollFailures = 0;

  const wsId = () => workspaceSelect ? workspaceSelect.value : '';
  const csrf = () => {
    const field = $('input[name=csrfmiddlewaretoken]');
    if (field) return field.value;
    return document.cookie.split(';').map(item => item.trim()).find(item => item.startsWith('csrftoken='))?.slice(10) || '';
  };
  const errorBox = message => {
    if (!inlineError) return;
    inlineError.textContent = message;
    inlineError.hidden = !message;
  };
  const pillTone = status => (
    ['SUCCEEDED', 'COMPLETED'].includes(status) ? 'teal' :
    status === 'FAILED' ? 'red' :
    ['ABSTAINED', 'PARTIAL'].includes(status) ? 'amber' :
    status === 'CANCELLED' ? 'gray' : 'blue'
  );
  const statusPill = (host, status, label) => {
    host.className = 'pill ' + pillTone(status);
    host.textContent = label || status;
  };
  const draftKey = () => `algomentor-workbench-draft:${wsId()}:${taskType ? taskType.value : 'grounded_qa'}`;
  const saveDraft = () => {
    if (!queryInput) return;
    try { localStorage.setItem(draftKey(), queryInput.value); } catch (_error) { /* storage disabled */ }
  };
  const loadDraft = () => {
    if (!queryInput) return;
    try { queryInput.value = localStorage.getItem(draftKey()) || ''; } catch (_error) { queryInput.value = ''; }
  };
  const humanTime = value => {
    if (!value) return '';
    const time = new Date(value);
    return Number.isNaN(time.getTime()) ? '' : time.toLocaleString('zh-CN', { hour12: false });
  };

  function addTaskToList(task) {
    if (!taskList) return;
    const empty = $('#workbench-task-empty');
    if (empty) empty.remove();
    const button = node('button', { class: 'algomentor-workbench-task active', type: 'button', dataset: { runId: task.run_id } });
    button.append(node('span', { class: 'algomentor-workbench-taskquery' }, String(task.query || '').slice(0, 60)));
    const meta = node('span', { class: 'algomentor-workbench-taskmeta' });
    const pill = node('span', { class: 'pill blue' }, task.status_label || task.status);
    meta.append(
      pill,
      node('span', {}, task.stage || ''),
      node('span', {}, `${String(task.created_at || '').slice(0, 16)} · ${String(task.run_id || '').slice(0, 8)}`),
    );
    button.append(meta);
    button.addEventListener('click', () => selectTask(task.run_id));
    $$('.algomentor-workbench-task', taskList).forEach(item => item.classList.remove('active'));
    taskList.prepend(button);
  }

  function linkifyCitations(host, citations) {
    if (!host || !citations || !citations.length) return;
    const pattern = /\[来源(\d+)\]/g;
    const walker = document.createTreeWalker(host, NodeFilter.SHOW_TEXT);
    const textNodes = [];
    while (walker.nextNode()) {
      const current = walker.currentNode;
      if (current.parentElement && current.parentElement.closest('a')) continue;
      if (pattern.test(current.nodeValue)) textNodes.push(current);
      pattern.lastIndex = 0;
    }
    for (const textNode of textNodes) {
      const text = textNode.nodeValue;
      const fragment = document.createDocumentFragment();
      let last = 0;
      let match;
      pattern.lastIndex = 0;
      while ((match = pattern.exec(text)) !== null) {
        const number = Number(match[1]);
        const citation = citations[number - 1];
        fragment.append(document.createTextNode(text.slice(last, match.index)));
        if (citation) {
          const href = citation.url || citation.source_uri
            || (citation.chunk_id ? `/knowledge/source/${encodeURIComponent(citation.chunk_id)}/` : '');
          if (href) {
            fragment.append(node('a', { href, class: 'algomentor-workbench-inline-citation' }, match[0]));
          } else {
            fragment.append(document.createTextNode(match[0]));
          }
        } else {
          fragment.append(document.createTextNode(match[0]));
        }
        last = match.index + match[0].length;
      }
      fragment.append(document.createTextNode(text.slice(last)));
      textNode.parentNode.replaceChild(fragment, textNode);
    }
  }

  function renderArtifacts(items) {
    const host = $('#workbench-artifacts');
    if (!host) return;
    host.replaceChildren();
    for (const artifact of items || []) {
      host.append(node('a', { href: artifact.download_url, rel: 'noopener' }, `下载 ${artifact.filename}`));
    }
  }

  function renderCitations(items) {
    const host = $('#workbench-citations');
    if (!host) return;
    host.replaceChildren();
    (items || []).forEach((item, index) => {
      const box = node('div', { class: 'algomentor-workbench-citation' });
      box.append(node('strong', {}, `[来源${index + 1}] ${item.document_name || '未命名来源'}`));
      const meta = [
        item.page_number ? `第 ${item.page_number} 页` : '',
        item.heading_path || '',
        item.char_start !== null && item.char_start !== undefined ? `字符 ${item.char_start}–${item.char_end}` : '',
      ].filter(Boolean);
      if (meta.length) box.append(node('div', { class: 'meta' }, meta.join(' · ')));
      box.append(node('p', {}, String(item.content || '').slice(0, 900)));
      const href = item.url || item.source_uri || (item.chunk_id ? `/knowledge/source/${encodeURIComponent(item.chunk_id)}/` : '');
      if (href) box.append(node('a', { class: 'card-link', href }, '查看完整原文 →'));
      host.append(box);
    });
  }

  function renderEvidence(items) {
    const host = $('#workbench-evidence');
    if (!host) return;
    host.replaceChildren();
    if (!items || !items.length) {
      host.append(node('p', { class: 'algomentor-workbench-muted' }, '本次任务没有可展示的证据片段。'));
      return;
    }
    for (const item of items) {
      const box = node('div', { class: 'algomentor-workbench-citation' });
      box.append(node('strong', {}, item.heading_path || item.chunk_id || item.evidence_id));
      const meta = [item.page ? `第 ${item.page} 页` : '', item.source_version ? `版本 ${item.source_version}` : '', item.content_hash ? `hash ${String(item.content_hash).slice(0, 10)}` : ''].filter(Boolean);
      if (meta.length) box.append(node('div', { class: 'meta' }, meta.join(' · ')));
      box.append(node('p', {}, item.content || ''));
      const href = item.source_uri || (item.chunk_id ? `/knowledge/source/${encodeURIComponent(item.chunk_id)}/` : '');
      if (href) box.append(node('a', { class: 'card-link', href }, '打开原文 →'));
      host.append(box);
    }
  }

  function renderSkills(items) {
    const host = $('#workbench-skills');
    if (!host) return;
    host.replaceChildren();
    if (!items || !items.length) {
      host.append(node('p', { class: 'algomentor-workbench-muted' }, '本次任务使用基础路径，未加载 Skill。'));
      return;
    }
    for (const item of items) {
      const box = node('div', { class: 'algomentor-workbench-citation' });
      box.append(node('strong', {}, `${item.skill_id}@${item.version}`));
      const detail = item.tool_scope
        ? `工具范围：${item.tool_scope.join(', ') || '无'} · hash ${String(item.content_hash || '').slice(0, 12)}`
        : (item.result_summary || '方法已加载');
      box.append(node('div', { class: 'meta' }, detail));
      host.append(box);
    }
  }

  function renderSteps(items) {
    const host = $('#workbench-steps');
    if (!host) return;
    host.replaceChildren();
    if (!items || !items.length) {
      const row = node('tr');
      const cell = node('td', { colspan: '6', class: 'algomentor-workbench-muted' }, '尚无步骤记录。');
      row.append(cell);
      host.append(row);
      return;
    }
    for (const step of items) {
      const row = node('tr');
      row.append(
        node('td', {}, step.step_id), node('td', {}, step.step_type), node('td', {}, step.decision),
        node('td', {}, step.latency_ms === undefined ? '—' : `${step.latency_ms} ms`),
        node('td', {}, step.tool_calls === undefined ? '—' : String(step.tool_calls)),
        node('td', {}, step.failure_code || ''),
      );
      host.append(row);
    }
  }

  function renderTask(task) {
    if (!task || !result) return;
    currentRunId = task.run_id;
    result.hidden = false;
    const statusHost = $('#workbench-result-status');
    statusPill(statusHost, task.status, task.status_label || task.status);
    $('#workbench-result-title').textContent = `${task.task_type} · ${String(task.query || '').slice(0, 70)}`;
    $('#workbench-result-meta').textContent = [
      `run ${String(task.run_id).slice(0, 10)}`,
      `阶段 ${task.stage || '—'}`,
      `${task.evidence_count || 0} 条证据`,
      `${task.step_count || 0} 步`,
      task.attempts ? `第 ${task.attempts} 次尝试` : '',
      task.requested_mode ? `预算 ${task.requested_mode}` : '',
      task.finished_at ? humanTime(task.finished_at) : '',
    ].filter(Boolean).join(' · ');

    const progress = $('#workbench-progress');
    progress.replaceChildren();
    progress.append(node('span', {}, `当前阶段：${task.stage || '等待开始'}`));
    if (ACTIVE.has(task.status)) {
      progress.append(node('span', { class: 'spinner', 'aria-hidden': 'true' }));
      progress.append(node('span', { class: 'algomentor-workbench-muted' }, task.worker && task.worker.online === false
        ? '任务服务未启动，任务会保持排队；启动 worker 后自动继续。'
        : '任务已受理，正在执行，页面会自动刷新状态。'));
    }
    if (task.status === 'CANCELLED') progress.append(node('span', { class: 'algomentor-workbench-muted' }, '已取消，已保留完成步骤与证据。'));
    if (task.error_code) progress.append(node('span', { class: 'pill amber' }, task.error_code));

    const answer = $('#workbench-answer');
    markdown(answer, task.answer || (ACTIVE.has(task.status) ? '正在检索证据并核验引用…' : '本次任务没有文本回答，请查看证据与产物。'));
    linkifyCitations(answer, task.citations);

    renderArtifacts(task.artifacts);
    renderCitations(task.citations);
    renderEvidence(task.evidence);
    renderSkills(task.skill_activations);
    renderSteps(task.steps);

    $('#workbench-cancel').hidden = !ACTIVE.has(task.status);
    $('#workbench-retry').hidden = !RETRYABLE.has(task.status);
    $('#workbench-feedback').hidden = !TERMINAL.has(task.status);

    $$('.algomentor-workbench-task', taskList).forEach(item => {
      item.classList.toggle('active', item.dataset.runId === task.run_id);
      if (item.dataset.runId === task.run_id) {
        const pill = item.querySelector('.pill');
        if (pill) {
          pill.className = 'pill ' + pillTone(task.status);
          pill.textContent = task.status_label || task.status;
        }
        const meta = item.querySelector('.algomentor-workbench-taskmeta');
        if (meta && meta.children.length > 1) meta.children[1].textContent = task.stage || '';
      }
    });
    const url = new URL(window.location.href);
    url.searchParams.set('task', task.run_id);
    window.history.replaceState({}, '', url);
  }

  function selectTask(runId) {
    if (!runId) return;
    if (pollTimer) { clearTimeout(pollTimer); pollTimer = null; }
    currentRunId = runId;
    loadTask(runId);
  }

  async function loadTask(runId) {
    try {
      const task = await request(`/api/v1/workbench/tasks/${encodeURIComponent(runId)}/`);
      pollFailures = 0;
      renderTask(task);
      if (ACTIVE.has(task.status)) {
        pollTimer = setTimeout(() => {
          if (currentRunId === runId) loadTask(runId);
        }, 2000);
      }
    } catch (error) {
      pollFailures += 1;
      if (pollFailures <= 2) toast(error.message || '任务状态加载失败，请稍后重试。');
    }
  }

  async function submitTask() {
    if (!queryInput || !workspaceSelect) return;
    const query = queryInput.value.trim();
    if (!query) { errorBox('请先输入任务目标。'); queryInput.focus(); return; }
    errorBox('');
    submitButton.disabled = true;
    submitButton.textContent = '提交中…';
    try {
      const task = await request('/api/v1/workbench/tasks/', {
        method: 'POST',
        body: JSON.stringify({
          workspace_id: wsId(), task_type: taskType.value, query,
          requested_mode: taskMode.value,
        }),
      });
      addTaskToList(task);
      try { localStorage.removeItem(draftKey()); } catch (_error) { /* ignore */ }
      queryInput.value = '';
      renderTask(task);
      toast('任务已提交，正在执行。');
      if (ACTIVE.has(task.status)) {
        pollTimer = setTimeout(() => loadTask(task.run_id), 1200);
      }
    } catch (error) {
      errorBox(error.message || '任务提交失败，请稍后重试。');
    } finally {
      submitButton.disabled = false;
      submitButton.textContent = '提交任务';
    }
  }

  async function uploadFiles(files) {
    if (!files || !files.length) {
      uploadStatus.textContent = '请选择至少一个文件。';
      return;
    }
    uploadButton.disabled = true;
    errorBox('');
    for (const file of Array.from(files)) {
      uploadStatus.textContent = `正在上传并解析：${file.name}…`;
      const form = new FormData();
      form.append('file', file, file.name);
      try {
        const response = await fetch(`/api/v1/workbench/workspaces/${encodeURIComponent(wsId())}/documents/`, {
          method: 'POST',
          credentials: 'same-origin',
          headers: { 'X-CSRFToken': csrf(), Accept: 'application/json' },
          body: form,
        });
        let payload = {};
        try { payload = await response.json(); } catch (_error) { payload = {}; }
        if (!response.ok || payload.success === false) {
          throw new Error(payload.error?.message || '上传或解析失败。');
        }
        uploadStatus.textContent = `${file.name} 解析完成，正在刷新资料状态…`;
      } catch (error) {
        errorBox(`${file.name}：${error.message || '上传失败'}`);
        uploadStatus.textContent = '解析失败的文件会保留在列表中，可重试或移除。';
        await new Promise(resolve => setTimeout(resolve, 900));
        window.location.reload();
        return;
      }
    }
    window.location.reload();
  }

  async function documentAction(documentId, action) {
    try {
      await request(`/api/v1/workbench/workspaces/${encodeURIComponent(wsId())}/documents/${encodeURIComponent(documentId)}/action/`, {
        method: 'POST', body: JSON.stringify({ action }),
      });
      window.location.reload();
    } catch (error) {
      errorBox(error.message || '资料操作失败。');
    }
  }

  async function taskAction(action) {
    if (!currentRunId) return;
    try {
      const task = await request(`/api/v1/workbench/tasks/${encodeURIComponent(currentRunId)}/action/`, {
        method: 'POST', body: JSON.stringify({ action }),
      });
      if (action === 'retry' && task.run_id) {
        addTaskToList(task);
        currentRunId = task.run_id;
        renderTask(task);
        pollTimer = setTimeout(() => loadTask(task.run_id), 1200);
      } else {
        renderTask(task);
      }
      toast(action === 'cancel' ? '已请求取消任务。' : '已创建新的重试任务。');
    } catch (error) {
      errorBox(error.message || '任务操作失败。');
    }
  }

  async function sendFeedback(rating) {
    if (!currentRunId) return;
    try {
      await request(`/api/v1/workbench/tasks/${encodeURIComponent(currentRunId)}/action/`, {
        method: 'POST', body: JSON.stringify({ action: 'feedback', rating }),
      });
      toast('感谢反馈，已记录。');
    } catch (error) {
      errorBox(error.message || '反馈提交失败。');
    }
  }

  function openCreateModal() {
    const modal = $('#workbench-create-modal');
    if (!modal) return;
    modal.hidden = false;
    $('#workbench-new-name')?.focus();
  }
  function closeCreateModal() {
    const modal = $('#workbench-create-modal');
    if (modal) modal.hidden = true;
    const error = $('#workbench-create-error');
    if (error) error.hidden = true;
  }

  async function createWorkspace() {
    const name = ($('#workbench-new-name')?.value || '').trim();
    const domain = $('#workbench-new-domain')?.value || 'generic';
    const description = ($('#workbench-new-description')?.value || '').trim();
    const error = $('#workbench-create-error');
    if (!name) {
      if (error) { error.textContent = '请输入空间名称。'; error.hidden = false; }
      return;
    }
    const button = $('#workbench-create-submit');
    if (button) { button.disabled = true; button.textContent = '创建中…'; }
    try {
      const workspace = await request('/api/v1/workbench/workspaces/', {
        method: 'POST', body: JSON.stringify({ name, domain_pack_id: domain, description }),
      });
      window.location.href = `/workbench/?workspace=${encodeURIComponent(workspace.id)}`;
    } catch (exc) {
      if (error) { error.textContent = exc.message || '创建失败。'; error.hidden = false; }
    } finally {
      if (button) { button.disabled = false; button.textContent = '创建空间'; }
    }
  }

  function bind() {
    workspaceSelect?.addEventListener('change', () => {
      window.location.href = `/workbench/?workspace=${encodeURIComponent(workspaceSelect.value)}`;
    });
    taskType?.addEventListener('change', loadDraft);
    queryInput?.addEventListener('input', () => { saveDraft(); errorBox(''); });
    queryInput?.addEventListener('keydown', event => {
      if (event.key === 'Enter' && (event.metaKey || event.ctrlKey) && !event.isComposing) {
        event.preventDefault();
        submitTask();
      }
    });
    submitButton?.addEventListener('click', submitTask);

    uploadInput?.addEventListener('change', () => {
      const files = uploadInput.files;
      if (!files || !files.length) {
        uploadButton.disabled = true;
        uploadStatus.textContent = '尚未选择文件';
        return;
      }
      uploadButton.disabled = false;
      uploadStatus.textContent = `已选择 ${files.length} 个文件：${Array.from(files).map(file => file.name).join('、')}`;
    });
    uploadButton?.addEventListener('click', () => uploadFiles(uploadInput?.files));
    if (uploadZone) {
      ['dragenter', 'dragover'].forEach(name => uploadZone.addEventListener(name, event => {
        event.preventDefault();
        uploadZone.classList.add('dragging');
      }));
      ['dragleave', 'drop'].forEach(name => uploadZone.addEventListener(name, event => {
        event.preventDefault();
        uploadZone.classList.remove('dragging');
      }));
      uploadZone.addEventListener('drop', event => {
        const files = event.dataTransfer?.files;
        if (files && files.length && uploadInput) {
          const transfer = new DataTransfer();
          Array.from(files).forEach(file => transfer.items.add(file));
          uploadInput.files = transfer.files;
          uploadInput.dispatchEvent(new Event('change'));
        }
      });
    }
    $$('[data-doc-action]').forEach(button => button.addEventListener('click', () => {
      documentAction(button.dataset.documentId, button.dataset.docAction);
    }));
    $$('.algomentor-workbench-task').forEach(button => button.addEventListener('click', () => selectTask(button.dataset.runId)));
    $('#workbench-cancel')?.addEventListener('click', () => taskAction('cancel'));
    $('#workbench-retry')?.addEventListener('click', () => taskAction('retry'));
    $$('[data-feedback]').forEach(button => button.addEventListener('click', () => sendFeedback(Number(button.dataset.feedback))));

    $('#workbench-create-toggle')?.addEventListener('click', openCreateModal);
    $('#workbench-create-empty')?.addEventListener('click', openCreateModal);
    $('#workbench-create-close')?.addEventListener('click', closeCreateModal);
    $('#workbench-create-cancel')?.addEventListener('click', closeCreateModal);
    $('#workbench-create-submit')?.addEventListener('click', createWorkspace);
  }

  bind();
  loadDraft();
  const taskParam = new URL(window.location.href).searchParams.get('task');
  if (taskParam) {
    selectTask(taskParam);
  } else if (initialTasks.length) {
    const latest = initialTasks[0];
    if (latest && latest.run_id) {
      currentRunId = latest.run_id;
      if (ACTIVE.has(latest.status) || latest.answer) loadTask(latest.run_id);
    }
  }
})();
