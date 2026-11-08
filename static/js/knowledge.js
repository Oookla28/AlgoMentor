/* Course knowledge search + additive EvidenceRAG Studio UI.
   All dynamic text is inserted with textContent; no untrusted HTML is parsed. */
(() => {
  'use strict';
  const { $, $$, request, node, sources, toast } = AM;
  const form = $('#knowledge-search-form');
  const target = $('#knowledge-search-results');
  const isStaff = target?.dataset.staff === '1';
  const treeHost = $('#evidence-rag-tree');
  const adminHost = $('#evidence-rag-admin');
  const adminEditor = $('#evidence-rag-admin-editor');
  let treeLoaded = false;
  let adminLoaded = false;
  let lastTree = null;

  const chip = (text, kind = '') => node('span', { class: 'evidence-rag-chip' + (kind ? ' ' + kind : '') }, text);
  const score = value => (typeof value === 'number' && Number.isFinite(value) ? value.toFixed(3) : '—');
  const textOf = value => (value === null || value === undefined ? '' : String(value));
  const csrf = () => {
    const field = $('input[name=csrfmiddlewaretoken]');
    if (field) return field.value;
    return document.cookie.split(';').map(x => x.trim()).find(x => x.startsWith('csrftoken='))?.slice(10) || '';
  };
  const mediaUrl = assetId => '/api/v1/knowledge/media/' + encodeURIComponent(assetId) + '/file/';
  const timeLabel = seconds => {
    if (seconds === null || seconds === undefined) return '';
    const total = Math.max(0, Math.floor(Number(seconds)));
    return String(Math.floor(total / 60)).padStart(2, '0') + ':' + String(total % 60).padStart(2, '0');
  };
  const notice = (message, kind = '') => node('div', { class: 'notice' + (kind ? ' ' + kind : '') }, message);
  const empty = message => node('div', { class: 'evidence-rag-empty' }, message);
  const details = (title, open = false) => {
    const box = node('details', { class: 'evidence-rag-panel' });
    box.open = open;
    box.append(node('summary', {}, title));
    return box;
  };

  function renderMedia(host, items) {
    if (!items || !items.length) return;
    const grid = node('div', { class: 'evidence-rag-media-grid' });
    for (const item of items) {
      const card = node('div', { class: 'evidence-rag-media-card' });
      const title = node('div', { class: 'evidence-rag-actions' });
      title.append(chip(item.modality === 'video' ? '视频证据' : item.modality === 'image' ? '图片证据' : '音频证据'));
      title.append(node('span', { class: 'evidence-rag-muted' }, item.evidence_id || ''));
      card.append(title);
      if (item.modality === 'image' && item.evidence_id) {
        card.append(node('img', {
          src: mediaUrl(item.evidence_id.replace(/^media:/, '')),
          alt: item.caption || item.text || '图片证据',
          loading: 'lazy',
        }));
      } else if ((item.modality === 'video' || item.modality === 'audio') && item.evidence_id) {
        card.append(node(item.modality === 'video' ? 'video' : 'audio', {
          src: mediaUrl(item.evidence_id.replace(/^media:/, '')),
          controls: '',
          preload: 'metadata',
        }));
      }
      const description = item.caption || item.ocr_text || item.asr_text || item.text || '无文字标注';
      card.append(node('p', { class: 'evidence-rag-media-caption' }, description));
      if (item.page_number) card.append(node('div', { class: 'evidence-rag-muted' }, '第 ' + item.page_number + ' 页'));
      if (item.start_time !== null && item.start_time !== undefined) {
        card.append(node('div', { class: 'evidence-rag-muted' }, '时间范围：' + timeLabel(item.start_time) + ' – ' + timeLabel(item.end_time)));
      }
      grid.append(card);
    }
    host.append(grid);
  }

  function renderConflicts(host, conflicts) {
    if (!conflicts || !conflicts.length) return;
    const box = details('冲突证据（' + conflicts.length + '）', true);
    for (const conflict of conflicts) {
      const card = node('div', { class: 'evidence-rag-conflict ' + (conflict.verdict === 'UNRESOLVED' ? 'unresolved' : 'settled') });
      const head = node('div', { class: 'evidence-rag-actions' });
      head.append(chip(conflict.conflict_type, 'amber'));
      head.append(chip(conflict.verdict_label || conflict.verdict));
      head.append(node('span', { class: 'evidence-rag-muted' }, '相似度 ' + score(conflict.confidence)));
      card.append(head);
      for (const [label, claim] of [['证据 A', conflict.claim_a], ['证据 B', conflict.claim_b]]) {
        const row = node('div', { class: 'evidence-rag-claim' });
        row.append(node('strong', {}, label));
        const body = node('div');
        body.append(node('div', {}, claim.text || ''));
        body.append(node('code', {}, claim.chunk_id || ''));
        row.append(body);
        card.append(row);
      }
      card.append(node('p', { class: 'evidence-rag-muted' }, conflict.explanation || ''));
      box.append(card);
    }
    host.append(box);
  }

  function renderTrace(host, payload) {
    const trace = payload.retrieval_trace || [];
    const variants = payload.query_variants || [];
    const box = details('高级检索轨迹', false);
    const chips = node('div', { class: 'evidence-rag-actions' });
    chips.append(node('span', { class: 'evidence-rag-muted' }, '查询变体：'));
    for (const variant of variants) chips.append(chip(variant));
    box.append(chips);
    if (payload.fallback && payload.fallback.used) {
      box.append(notice('高级模式已回退：' + (payload.fallback.reason || '未知原因'), 'warning'));
    }
    if ((payload.fallback?.warnings || []).length) {
      box.append(node('p', { class: 'evidence-rag-muted' }, '降级记录：' + payload.fallback.warnings.join('；')));
    }
    if (!trace.length) {
      box.append(empty('本次未产生逐路召回记录。'));
    } else {
      const wrapper = node('div', { class: 'table-scroll' });
      const table = node('table', { class: 'evidence-rag-route-table' });
      const head = node('tr');
      for (const label of ['查询变体', '召回器', '片段', '排名', '原始分', 'RRF', '重排', '选中']) head.append(node('th', {}, label));
      table.append(node('thead', {}, ''), node('tbody'));
      table.querySelector('thead').append(head);
      const body = table.querySelector('tbody');
      for (const row of trace.slice(0, 80)) {
        const tr = node('tr');
        tr.append(node('td', {}, row.query_variant || ''));
        tr.append(node('td', {}, row.retriever_name || ''));
        tr.append(node('td', { class: 'numeric' }, row.chunk_id || ''));
        tr.append(node('td', { class: 'numeric' }, String(row.rank ?? '')));
        tr.append(node('td', { class: 'numeric' }, score(row.raw_score)));
        tr.append(node('td', { class: 'numeric' }, score(row.rrf_score)));
        tr.append(node('td', { class: 'numeric' }, score(row.rerank_score)));
        tr.append(node('td', {}, row.selected ? '是' : '否'));
        body.append(tr);
      }
      wrapper.append(table);
      box.append(wrapper);
      if (trace.length > 80) box.append(node('p', { class: 'evidence-rag-muted' }, '仅显示前 80 条逐路记录。'));
    }
    if (payload.trace_id) {
      box.append(node('p', { class: 'evidence-rag-muted' }, '轨迹编号：' + payload.trace_id));
    }
    host.append(box);
  }

  function renderContexts(host, citations) {
    const rows = citations.filter(citation => citation.context);
    if (!rows.length) return;
    const box = details('证据上下文（Small2Big）', false);
    for (const citation of rows) {
      const item = node('details');
      const summary = node('summary', {}, (citation.heading_path || citation.document_name || citation.chunk_id) + ' · ' + citation.chunk_id);
      item.append(summary);
      item.append(node('p', { class: 'evidence-rag-muted' },
        '父块 ' + (citation.parent_chunk_id || '—') + ' · 第 ' + citation.page_number + ' 页 · 字符 ' + (citation.char_start ?? '—') + '–' + (citation.char_end ?? '—')));
      const contextText = citation.context || '';
      const matched = citation.matched_content || '';
      const paragraph = node('p', { style: 'white-space:pre-wrap' });
      const matchIndex = matched ? contextText.indexOf(matched) : -1;
      if (matchIndex >= 0) {
        paragraph.append(document.createTextNode(contextText.slice(0, matchIndex)));
        paragraph.append(node('mark', { class: 'evidence-rag-match' }, matched));
        paragraph.append(document.createTextNode(contextText.slice(matchIndex + matched.length)));
      } else {
        paragraph.textContent = contextText;
      }
      item.append(paragraph);
      box.append(item);
    }
    host.append(box);
  }

  function renderAdvanced(payload, query) {
    target.replaceChildren();
    target.hidden = false;
    target.append(node('p', { class: 'small-text muted' },
      '高级检索模式 · ' + (payload.evidence_sufficient ? '找到可核验证据' : '证据不足') + ' · ' + query));
    if (payload.fallback && payload.fallback.used) {
      const reason = isStaff ? '（' + (payload.fallback.reason || '未知原因') + '）' : '';
      target.append(notice('高级索引暂不可用，已自动回退到基础检索' + reason + '。原有搜索结果仍可使用。', 'warning'));
    }
    if (!payload.evidence_sufficient) {
      target.append(notice('当前课程资料没有提供充分证据。可以调整关键词，或使用独立百科查询入口；系统不会用无关片段强行回答。', 'warning'));
    }
    const citations = payload.citations || payload.results || [];
    const sourceBox = node('div');
    sources(sourceBox, citations);
    target.append(sourceBox);
    if (isStaff) renderTrace(target, payload);
    renderConflicts(target, payload.conflicts);
    const mediaBox = node('div');
    renderMedia(mediaBox, payload.media_evidence);
    if (mediaBox.childNodes.length) {
      const box = details('媒体证据（' + payload.media_evidence.length + '）', false);
      box.append(mediaBox);
      target.append(box);
    }
    renderContexts(target, citations);
  }

  function renderLegacy(payload) {
    target.replaceChildren();
    target.hidden = false;
    const items = payload.results || payload.citations || [];
    if (!items.length) {
      target.append(notice('当前课程资料没有提供充分证据。可调整关键词，或从独立百科查询入口查找扩展资料。', 'warning'));
      return;
    }
    target.append(node('p', { class: 'small-text muted' }, '找到 ' + items.length + ' 个原文片段。此处展示检索证据，完整解释可交由 AI 助教生成。'));
    sources(target, items);
  }

  form?.addEventListener('submit', async event => {
    event.preventDefault();
    const query = $('#knowledge-query').value.trim();
    if (!query) return;
    const button = $('button', form);
    const advanced = $('#knowledge-advanced-mode')?.checked;
    button.disabled = true;
    target.hidden = false;
    target.replaceChildren(node('p', { class: 'small-text muted' }, advanced ? '正在执行层次化混合检索…' : '正在从课程向量索引检索真实证据…'));
    try {
      const data = await request('/api/v1/knowledge/search/?q=' + encodeURIComponent(query) + (advanced ? '&mode=advanced' : ''));
      if (advanced || data.mode === 'advanced') renderAdvanced(data, query);
      else renderLegacy(data);
    } catch (error) {
      target.replaceChildren(notice(error.message || '检索未完成，请稍后重试。', 'warning'));
    } finally {
      button.disabled = false;
    }
  });

  function renderTree(documents) {
    treeHost.replaceChildren();
    if (!documents || !documents.length) {
      treeHost.append(empty('暂无已入库资料。管理员上传或执行 ingest_knowledge 后可查看切片树。'));
      return;
    }
    for (const document of documents) {
      const docBox = node('details');
      docBox.open = true;
      const summary = node('summary');
      summary.append(node('strong', {}, document.name));
      summary.append(chip(document.source_type || 'pdf', 'grey'));
      summary.append(chip(document.ingestion_status || 'legacy'));
      summary.append(node('span', { class: 'evidence-rag-muted' }, ' 父块 ' + document.parent_count + ' · 子块 ' + document.child_count + ' · 媒体 ' + document.media_count));
      docBox.append(summary);
      if (document.parents && document.parents.length) {
        const parents = node('div', { class: 'evidence-rag-tree-children' });
        for (const parent of document.parents) {
          const parentBox = node('details');
          const parentSummary = node('summary');
          parentSummary.append(node('span', {}, parent.heading_path || parent.chunk_id));
          parentSummary.append(chip('第 ' + parent.page_number + ' 页', 'grey'));
          parentSummary.append(chip(parent.token_count + ' tokens', 'grey'));
          parentBox.append(parentSummary);
          if (parent.children && parent.children.length) {
            const childBox = node('div', { class: 'evidence-rag-tree-children' });
            for (const child of parent.children) {
              const row = node('div', { class: 'evidence-rag-tree-child' });
              const link = node('a', { href: '/knowledge/source/' + encodeURIComponent(child.chunk_id) + '/' }, child.chunk_id);
              row.append(link);
              row.append(node('span', {}, '第 ' + child.page_number + ' 页 · ' + child.token_count + ' tokens'));
              childBox.append(row);
            }
            parentBox.append(childBox);
          }
          parents.append(parentBox);
        }
        docBox.append(parents);
      }
      if (document.media && document.media.length) {
        const mediaHost = node('div');
        renderMedia(mediaHost, document.media);
        docBox.append(mediaHost);
      }
      if (document.truncated) docBox.append(node('p', { class: 'evidence-rag-muted' }, '切片较多，树视图已截断；可继续使用检索定位片段。'));
      treeHost.append(docBox);
    }
    if (lastTree && lastTree.documents) adminHostData(lastTree.documents);
  }

  async function loadTree(force = false) {
    if (!treeHost) return;
    if (treeLoaded && !force) return;
    treeHost.replaceChildren(node('p', { class: 'small-text muted' }, '正在读取切片树…'));
    try {
      const data = await request('/api/v1/knowledge/tree/');
      treeLoaded = true;
      lastTree = data;
      renderTree(data.documents || []);
    } catch (error) {
      treeHost.replaceChildren(notice(error.message || '切片树加载失败。', 'warning'));
    }
  }

  function adminHostData(documents) {
    if (!adminHost) return;
    adminHost.replaceChildren();
    if (!documents.length) {
      adminHost.append(empty('暂无资料可维护。'));
      return;
    }
    for (const document of documents) {
      const card = node('div', { class: 'evidence-rag-admin-card' });
      const head = node('div', { class: 'evidence-rag-admin-head' });
      const title = node('div');
      title.append(node('h3', {}, document.name));
      title.append(node('div', { class: 'evidence-rag-muted' },
        '文档 #' + document.id + ' · ' + (document.source_type || 'pdf') + ' · ' + (document.ingestion_status || 'legacy') +
        ' · 高级索引 ' + (document.advanced_index_version || '未建立')));
      head.append(title);
      const actions = node('div', { class: 'evidence-rag-actions' });
      const advanced = node('button', { class: 'button secondary small', type: 'button', 'data-reindex': String(document.id), 'data-mode': 'advanced' }, '重建高级索引');
      actions.append(advanced);
      if (document.source_type === 'pdf') {
        actions.append(node('button', { class: 'button secondary small', type: 'button', 'data-reindex': String(document.id), 'data-mode': 'legacy' }, '重建旧版索引'));
      }
      head.append(actions);
      card.append(head);
      if (document.parents && document.parents.length) {
        const list = node('div', { class: 'evidence-rag-tree-children' });
        for (const parent of document.parents) {
          for (const child of (parent.children || [])) {
            const row = node('div', { class: 'evidence-rag-tree-child' });
            row.append(node('span', {}, child.chunk_id));
            const edit = node('button', { class: 'button text small', type: 'button', 'data-chunk': child.chunk_id }, '编辑片段');
            row.append(edit);
            list.append(row);
          }
        }
        card.append(list);
      }
      adminHost.append(card);
    }
  }

  async function loadAdmin(force = false) {
    if (!adminHost) return;
    if (adminLoaded && !force) return;
    adminHost.replaceChildren(node('p', { class: 'small-text muted' }, '正在读取维护数据…'));
    try {
      const data = await request('/api/v1/knowledge/tree/');
      adminLoaded = true;
      lastTree = data;
      adminHostData(data.documents || []);
    } catch (error) {
      adminHost.replaceChildren(notice(error.message || '维护数据加载失败。', 'warning'));
    }
  }

  async function renderChunkEditor(chunkId) {
    if (!adminEditor) return;
    adminEditor.replaceChildren(node('p', { class: 'small-text muted' }, '正在读取片段…'));
    try {
      const chunk = await request('/api/v1/knowledge/chunks/' + encodeURIComponent(chunkId) + '/');
      adminEditor.replaceChildren();
      const card = node('div', { class: 'evidence-rag-admin-card' });
      const head = node('div', { class: 'evidence-rag-admin-head' });
      const title = node('div');
      title.append(node('h3', {}, chunk.chunk_id));
      title.append(node('div', { class: 'evidence-rag-muted' },
        chunk.document_name + ' · 第 ' + chunk.page_number + ' 页 · ' + chunk.chunk_type + ' · ' + chunk.token_count + ' tokens'));
      head.append(title);
      head.append(node('span', { class: 'evidence-rag-chip' + (chunk.is_active ? '' : ' amber') }, chunk.is_active ? '启用' : '已删除'));
      card.append(head);
      const textarea = node('textarea', { class: 'evidence-rag-chunk-editor', maxlength: '20000', 'aria-label': '片段内容' });
      textarea.value = chunk.content || '';
      card.append(textarea);
      let parentInput = null;
      if (chunk.chunk_type === 'child') {
        const parentRow = node('label', { class: 'evidence-rag-muted', style: 'display:block;margin-top:8px' });
        parentRow.append(document.createTextNode('父块编号（留空表示解除父块关系）：'));
        parentInput = node('input', {
          type: 'text', class: 'evidence-rag-chunk-editor', style: 'min-height:auto;padding:8px 10px',
          maxlength: '100', placeholder: 'adv-xxxx-P001', 'aria-label': '父块编号',
        });
        parentInput.value = chunk.parent_chunk_id || '';
        parentRow.append(parentInput);
        card.append(parentRow);
      }
      const actions = node('div', { class: 'evidence-rag-actions', style: 'margin-top:10px' });
      const save = node('button', { class: 'button primary small', type: 'button' }, '保存并同步索引');
      const remove = node('button', { class: 'button secondary small', type: 'button' }, '删除片段');
      const restore = node('button', { class: 'button text small', type: 'button' }, '恢复片段');
      actions.append(save, remove, restore);
      card.append(actions);
      adminEditor.append(card);
      save.addEventListener('click', async () => {
        save.disabled = true;
        try {
          const payload = { content: textarea.value };
          if (parentInput) payload.parent_chunk_id = parentInput.value.trim();
          await request('/api/v1/knowledge/chunks/' + encodeURIComponent(chunkId) + '/', {
            method: 'PATCH', body: JSON.stringify(payload),
          });
          toast('片段已保存');
          treeLoaded = false;
          await loadTree(true);
          await loadAdmin(true);
        } catch (error) {
          adminEditor.prepend(notice(error.message || '保存失败。', 'warning'));
        } finally {
          save.disabled = false;
        }
      });
      remove.addEventListener('click', async () => {
        if (!window.confirm('确认删除该片段？删除后可恢复。')) return;
        try {
          await request('/api/v1/knowledge/chunks/' + encodeURIComponent(chunkId) + '/', { method: 'DELETE' });
          toast('片段已软删除');
          await renderChunkEditor(chunkId);
          treeLoaded = false;
          await loadTree(true);
        } catch (error) {
          adminEditor.prepend(notice(error.message || '删除失败。', 'warning'));
        }
      });
      restore.addEventListener('click', async () => {
        try {
          await request('/api/v1/knowledge/chunks/' + encodeURIComponent(chunkId) + '/restore/', { method: 'POST' });
          toast('片段已恢复');
          await renderChunkEditor(chunkId);
          treeLoaded = false;
          await loadTree(true);
        } catch (error) {
          adminEditor.prepend(notice(error.message || '恢复失败。', 'warning'));
        }
      });
    } catch (error) {
      adminEditor.replaceChildren(notice(error.message || '片段加载失败。', 'warning'));
    }
  }

  adminHost?.addEventListener('click', async event => {
    const reindex = event.target.closest('[data-reindex]');
    if (reindex) {
      reindex.disabled = true;
      try {
        await request('/api/v1/knowledge/documents/' + encodeURIComponent(reindex.dataset.reindex) + '/reindex/', {
          method: 'POST', body: JSON.stringify({ mode: reindex.dataset.mode, rebuild: true }),
        });
        toast('索引重建完成');
        treeLoaded = false;
        await loadTree(true);
        await loadAdmin(true);
      } catch (error) {
        adminHost.prepend(notice(error.message || '索引重建失败。', 'warning'));
      } finally {
        reindex.disabled = false;
      }
      return;
    }
    const chunk = event.target.closest('[data-chunk]');
    if (chunk) await renderChunkEditor(chunk.dataset.chunk);
  });

  $('#evidence-rag-chunk-load')?.addEventListener('click', async () => {
    const value = $('#evidence-rag-chunk-id').value.trim();
    if (value) await renderChunkEditor(value);
  });

  $('#evidence-rag-upload')?.addEventListener('submit', async event => {
    event.preventDefault();
    const formElement = event.currentTarget;
    const button = $('button', formElement);
    button.disabled = true;
    try {
      const response = await fetch('/api/v1/knowledge/documents/upload/', {
        method: 'POST', credentials: 'same-origin', headers: { 'X-CSRFToken': csrf() }, body: new FormData(formElement),
      });
      let payload;
      try { payload = await response.json(); } catch { throw new Error('服务返回了无法识别的响应。'); }
      if (!response.ok || payload.success === false) throw new Error(payload.error?.message || '上传失败。');
      const data = payload.data || payload;
      toast(data.warning ? '已保存，但索引未完成：' + data.warning : '上传并入库完成');
      formElement.reset();
      treeLoaded = false;
      adminLoaded = false;
      await loadTree(true);
      await loadAdmin(true);
    } catch (error) {
      formElement.prepend(notice(error.message || '上传失败。', 'warning'));
    } finally {
      button.disabled = false;
    }
  });

  $$('[data-tabs] [data-tab]').forEach(button => {
    button.addEventListener('click', () => {
      if (button.dataset.tab === 'tree') loadTree();
      if (button.dataset.tab === 'maintenance') loadAdmin();
    });
  });

})();
