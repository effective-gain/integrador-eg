/* ============================================================
   Integrador EG — SPA
   ============================================================ */

// ── State ──────────────────────────────────────────────────────
const S = {
  user: null,       // { id, email, nome, papel, cliente_id }
  tab: null,        // tab ativa
  periodo: 'semana',
};

// ── DOM refs ───────────────────────────────────────────────────
const $ = id => document.getElementById(id);
const viewLogin   = $('view-login');
const viewApp     = $('view-app');
const tabsNav     = $('tabs');
const pageContent = $('page-content');
const topbarUser  = $('topbar-user');
const topbarTag   = $('topbar-tag');
const toast       = $('toast');

// ── Boot ───────────────────────────────────────────────────────
(async () => {
  try {
    const me = await api('/api/me');
    login(me);
  } catch {
    showLogin();
  }
})();

// ── Login form ─────────────────────────────────────────────────
$('form-login').addEventListener('submit', async e => {
  e.preventDefault();
  const btn   = $('btn-login');
  const email = $('login-email').value;
  const senha = $('login-senha').value;
  const err   = $('login-error');

  btn.disabled = true;
  btn.textContent = 'Entrando…';
  err.classList.add('hidden');

  try {
    const user = await api('/api/login', { method: 'POST', body: { email, senha } });
    login(user);
  } catch (ex) {
    err.textContent = ex.message || 'Credenciais inválidas.';
    err.classList.remove('hidden');
  } finally {
    btn.disabled = false;
    btn.textContent = 'Entrar';
  }
});

// ── Logout ─────────────────────────────────────────────────────
$('btn-logout').addEventListener('click', async () => {
  await api('/api/logout', { method: 'POST' }).catch(() => {});
  S.user = null;
  showLogin();
});

// ── Views ──────────────────────────────────────────────────────
function showLogin() {
  viewLogin.classList.remove('hidden');
  viewApp.classList.add('hidden');
}

function login(user) {
  S.user = user;
  viewLogin.classList.add('hidden');
  viewApp.classList.remove('hidden');

  // topbar
  topbarUser.textContent = user.nome;
  if (user.papel === 'admin') {
    topbarTag.textContent = 'Admin EG';
    topbarTag.classList.add('admin-tag');
    buildAdminTabs();
    navigate('clientes');
  } else {
    topbarTag.textContent = 'Portal';
    topbarTag.classList.remove('admin-tag');
    buildPortalTabs();
    navigate('resumo');
  }
}

// ── Tab builders ───────────────────────────────────────────────
function buildPortalTabs() {
  const tabs = [
    { id: 'resumo',    label: '📊 Visão Geral' },
    { id: 'execucoes', label: '⚡ Execuções' },
    { id: 'receitas',  label: '🔧 Automações' },
    { id: 'briefings', label: '📬 Briefings' },
  ];
  renderTabs(tabs);
}

function buildAdminTabs() {
  const tabs = [
    { id: 'clientes',       label: '👥 Clientes' },
    { id: 'execucoes',      label: '⚡ Execuções' },
    { id: 'usuarios',       label: '🔑 Usuários' },
    { id: 'sistema',        label: '🛠 Sistema' },
    { id: 'configuracoes',  label: '⚙️ Configurações' },
  ];
  renderTabs(tabs);
}

function renderTabs(tabs) {
  tabsNav.innerHTML = tabs.map(t =>
    `<button class="tab" data-tab="${t.id}">${t.label}</button>`
  ).join('');
  tabsNav.querySelectorAll('.tab').forEach(btn => {
    btn.addEventListener('click', () => navigate(btn.dataset.tab));
  });
}

// ── Router ─────────────────────────────────────────────────────
function navigate(tab) {
  S.tab = tab;
  // mark active tab
  tabsNav.querySelectorAll('.tab').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.tab === tab);
  });
  if (S.user.papel === 'admin') {
    renderAdminTab(tab);
  } else {
    renderPortalTab(tab);
  }
}

// ── Portal: renders ────────────────────────────────────────────
async function renderPortalTab(tab) {
  switch (tab) {
    case 'resumo':    return renderResumo();
    case 'execucoes': return renderExecucoes();
    case 'receitas':  return renderReceitas();
    case 'briefings': return renderBriefings();
  }
}

// ── Resumo (visão geral) ───────────────────────────────────────
async function renderResumo() {
  pageContent.innerHTML = loadingHtml('Carregando dados…');
  const data = await api('/api/portal/resumo').catch(() => null);
  if (!data) { pageContent.innerHTML = errorHtml('Não foi possível carregar os dados.'); return; }

  const recentes = await api(`/api/portal/execucoes?periodo=semana&limit=10`).catch(() => ({ items: [] }));

  pageContent.innerHTML = `
    <div class="page-header">
      <div class="page-title">Visão Geral</div>
      <div class="page-subtitle">Resumo das automações executadas para o seu negócio</div>
    </div>

    <div class="metrics-grid">
      <div class="metric-card accent">
        <div class="metric-label">Ações este mês</div>
        <div class="metric-value">${data.execucoes_mes}</div>
        <div class="metric-sub">${data.execucoes_hoje} hoje</div>
      </div>
      <div class="metric-card ok">
        <div class="metric-label">Horas economizadas</div>
        <div class="metric-value">${data.horas_economizadas}h</div>
        <div class="metric-sub">estimativa este mês</div>
      </div>
      <div class="metric-card">
        <div class="metric-label">Automações ativas</div>
        <div class="metric-value">${data.automacoes_ativas}</div>
        <div class="metric-sub">receitas configuradas</div>
      </div>
      <div class="metric-card">
        <div class="metric-label">Briefings enviados</div>
        <div class="metric-value">${data.briefings_mes}</div>
        <div class="metric-sub">últimos 30 dias</div>
      </div>
    </div>

    <div class="section">
      <div class="section-header">
        <div class="section-title">Atividade recente</div>
        <button class="btn btn-ghost btn-sm" onclick="navigate('execucoes')">Ver tudo →</button>
      </div>
      <div class="timeline" id="timeline-recente">
        ${recentes.items.length ? recentes.items.map(execucaoHtml).join('') : emptyHtml('Nenhuma execução esta semana', '⚡')}
      </div>
    </div>
  `;
}

// ── Execuções ──────────────────────────────────────────────────
async function renderExecucoes() {
  pageContent.innerHTML = `
    <div class="page-header">
      <div class="page-title">Execuções</div>
      <div class="page-subtitle">Histórico completo de ações executadas</div>
    </div>
    <div class="filters">
      ${['hoje','semana','mes','tudo'].map(p =>
        `<button class="filter-btn ${p === S.periodo ? 'active' : ''}" onclick="setPeriodo('${p}')">${periodoLabel(p)}</button>`
      ).join('')}
    </div>
    <div id="execucoes-list" class="timeline">${loadingHtml()}</div>
  `;
  await carregarExecucoes();
}

async function carregarExecucoes() {
  const list = $('execucoes-list');
  if (!list) return;
  list.innerHTML = loadingHtml();
  const data = await api(`/api/portal/execucoes?periodo=${S.periodo}&limit=100`).catch(() => null);
  if (!data) { list.innerHTML = errorHtml(); return; }
  list.innerHTML = data.items.length
    ? data.items.map(execucaoHtml).join('')
    : emptyHtml('Nenhuma execução neste período', '⚡');
}

function setPeriodo(p) {
  S.periodo = p;
  document.querySelectorAll('.filter-btn').forEach(b => {
    b.classList.toggle('active', b.textContent.toLowerCase().includes(periodoLabel(p).toLowerCase()) || b.getAttribute('onclick')?.includes(`'${p}'`));
  });
  // rerender filters correctly
  navigate('execucoes');
}

// ── Automações (receitas) ──────────────────────────────────────
async function renderReceitas() {
  pageContent.innerHTML = loadingHtml('Carregando automações…');
  const data = await api('/api/portal/receitas').catch(() => null);
  if (!data) { pageContent.innerHTML = errorHtml(); return; }

  pageContent.innerHTML = `
    <div class="page-header">
      <div class="page-title">Automações</div>
      <div class="page-subtitle">Receitas ativas configuradas para o seu projeto</div>
    </div>
    <div class="recipes-grid">
      ${data.items.length
        ? data.items.map(receitaHtml).join('')
        : emptyHtml('Nenhuma automação configurada', '🔧')}
    </div>
  `;
}

// ── Briefings ──────────────────────────────────────────────────
async function renderBriefings() {
  pageContent.innerHTML = loadingHtml('Carregando briefings…');
  const data = await api('/api/portal/briefings').catch(() => null);
  if (!data) { pageContent.innerHTML = errorHtml(); return; }

  pageContent.innerHTML = `
    <div class="page-header">
      <div class="page-title">Briefings</div>
      <div class="page-subtitle">Resumos diários enviados para o seu WhatsApp</div>
    </div>
    <div>
      ${data.items.length
        ? data.items.map(briefingHtml).join('')
        : emptyHtml('Nenhum briefing enviado ainda', '📬')}
    </div>
  `;
}

// ── Admin: renders ─────────────────────────────────────────────
async function renderAdminTab(tab) {
  switch (tab) {
    case 'clientes':      return renderAdminClientes();
    case 'execucoes':     return renderAdminExecucoes();
    case 'usuarios':      return renderAdminUsuarios();
    case 'sistema':       return renderAdminSistema();
    case 'configuracoes': return renderConfiguracoes();
  }
}

// ── Admin: Clientes ────────────────────────────────────────────
async function renderAdminClientes() {
  pageContent.innerHTML = loadingHtml('Carregando clientes…');
  const [resumo, clientesData] = await Promise.all([
    api('/api/admin/resumo').catch(() => ({})),
    api('/api/admin/clientes').catch(() => ({ items: [] })),
  ]);

  pageContent.innerHTML = `
    <div class="page-header flex justify-between items-center">
      <div>
        <div class="page-title">Clientes</div>
        <div class="page-subtitle">Gestão de clientes e projetos ativos</div>
      </div>
      <button class="btn btn-secondary" onclick="modalNovoCliente()">+ Novo cliente</button>
    </div>

    <div class="metrics-grid" style="margin-bottom: var(--sp-8)">
      <div class="metric-card accent">
        <div class="metric-label">Clientes ativos</div>
        <div class="metric-value">${resumo.clientes_ativos ?? '—'}</div>
      </div>
      <div class="metric-card">
        <div class="metric-label">Execuções hoje</div>
        <div class="metric-value">${resumo.execucoes_hoje ?? '—'}</div>
      </div>
      <div class="metric-card ok">
        <div class="metric-label">Execuções este mês</div>
        <div class="metric-value">${resumo.execucoes_mes ?? '—'}</div>
      </div>
      <div class="metric-card ${(resumo.dead_letter_pendentes ?? 0) > 0 ? 'danger' : ''}">
        <div class="metric-label">Dead letter</div>
        <div class="metric-value">${resumo.dead_letter_pendentes ?? 0}</div>
        <div class="metric-sub">operações com falha</div>
      </div>
    </div>

    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Cliente</th>
            <th>Grupo WA</th>
            <th>Plano</th>
            <th>Exec. mês</th>
            <th>Receitas ativas</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          ${clientesData.items.map(c => `
            <tr>
              <td><strong>${esc(c.nome)}</strong><br><span class="tiny">${esc(c.slug)}</span></td>
              <td><span class="mono small">${esc(c.whatsapp_grupo || '—')}</span></td>
              <td>${planoBadge(c.plano)}</td>
              <td><strong>${c.execucoes_mes ?? 0}</strong></td>
              <td>${c.receitas_ativas ?? 0}</td>
              <td><span class="status-dot ${c.ativo ? 'ok' : 'offline'}"></span>${c.ativo ? 'Ativo' : 'Inativo'}</td>
            </tr>
          `).join('') || '<tr><td colspan="6" class="muted" style="padding:24px;text-align:center">Nenhum cliente cadastrado</td></tr>'}
        </tbody>
      </table>
    </div>
  `;
}

// ── Admin: Execuções ───────────────────────────────────────────
async function renderAdminExecucoes() {
  pageContent.innerHTML = `
    <div class="page-header">
      <div class="page-title">Todas as Execuções</div>
      <div class="page-subtitle">Visão global de todos os clientes</div>
    </div>
    <div class="filters">
      ${['hoje','semana','mes'].map(p =>
        `<button class="filter-btn ${p === S.periodo ? 'active' : ''}" onclick="setAdminPeriodo('${p}')">${periodoLabel(p)}</button>`
      ).join('')}
    </div>
    <div id="admin-exec-list">${loadingHtml()}</div>
  `;
  await carregarAdminExecucoes();
}

async function carregarAdminExecucoes() {
  const el = $('admin-exec-list');
  if (!el) return;
  const data = await api(`/api/admin/execucoes?periodo=${S.periodo}&limit=200`).catch(() => null);
  if (!data) { el.innerHTML = errorHtml(); return; }

  if (!data.items.length) { el.innerHTML = emptyHtml('Nenhuma execução neste período', '⚡'); return; }

  el.innerHTML = `
    <div class="table-wrap">
      <table>
        <thead>
          <tr><th>Quando</th><th>Cliente</th><th>Ação</th><th>Projeto</th><th>Remetente</th><th>Resultado</th></tr>
        </thead>
        <tbody>
          ${data.items.map(e => `
            <tr>
              <td class="tiny">${tempoRelativo(e.criado_em)}</td>
              <td class="small">${esc(e.cliente_nome || '—')}</td>
              <td>${acaoEmoji(e.acao)} <span class="small">${acaoLabel(e.acao)}</span></td>
              <td class="small muted">${esc(e.projeto || '—')}</td>
              <td class="small muted">${esc(e.remetente || '—')}</td>
              <td>${resultadoBadge(e.resultado)}</td>
            </tr>
          `).join('')}
        </tbody>
      </table>
    </div>
  `;
}

function setAdminPeriodo(p) {
  S.periodo = p;
  navigate('execucoes');
}

// ── Admin: Usuários ────────────────────────────────────────────
async function renderAdminUsuarios() {
  pageContent.innerHTML = loadingHtml('Carregando usuários…');
  const data = await api('/api/admin/usuarios').catch(() => ({ items: [] }));

  pageContent.innerHTML = `
    <div class="page-header flex justify-between items-center">
      <div>
        <div class="page-title">Usuários</div>
        <div class="page-subtitle">Admins EG e representantes de clientes</div>
      </div>
      <button class="btn btn-secondary" onclick="modalNovoUsuario()">+ Novo usuário</button>
    </div>

    <div class="table-wrap">
      <table>
        <thead>
          <tr><th>Nome</th><th>E-mail</th><th>Papel</th><th>Cliente</th><th>Criado em</th></tr>
        </thead>
        <tbody>
          ${data.items.map(u => `
            <tr>
              <td><strong>${esc(u.nome)}</strong></td>
              <td class="small muted">${esc(u.email)}</td>
              <td>${papelBadge(u.papel)}</td>
              <td class="small">${esc(u.cliente_nome || '—')}</td>
              <td class="tiny">${formatData(u.criado_em)}</td>
            </tr>
          `).join('') || '<tr><td colspan="5" class="muted" style="padding:24px;text-align:center">Nenhum usuário</td></tr>'}
        </tbody>
      </table>
    </div>
  `;
}

// ── Admin: Sistema ─────────────────────────────────────────────
async function renderAdminSistema() {
  pageContent.innerHTML = loadingHtml('Verificando sistema…');
  const data = await api('/api/dashboard').catch(() => null);
  if (!data) { pageContent.innerHTML = errorHtml(); return; }

  // E-mail status helpers
  const emailOk = ['outlook_ok', 'smtp_gmail'].includes(data.email);
  const emailLabel = {
    outlook_ok:   'Outlook (Graph API)',
    outlook_erro: 'Outlook — erro de auth',
    smtp_gmail:   'SMTP Gmail (fallback)',
    inativo:      'Não configurado',
  }[data.email] || data.email || 'Inativo';

  const items = [
    { label: 'Ambiente',     val: data.ambiente,             status: data.ambiente === 'production' ? 'ok' : 'warn' },
    { label: 'Obsidian',     val: data.obsidian,             status: data.obsidian === 'online' ? 'ok' : 'danger' },
    { label: 'E-mail',       val: emailLabel,                status: emailOk ? 'ok' : data.email === 'inativo' ? 'warn' : 'danger' },
    { label: 'Whisper',      val: data.whisper,              status: data.whisper === 'ativo' ? 'ok' : 'warn' },
    { label: 'Briefing',     val: data.briefing,             status: data.briefing !== 'inativo' ? 'ok' : 'warn' },
    { label: 'Dead letter',  val: `${data.dead_letter_pendentes} pendentes`, status: data.dead_letter_pendentes > 0 ? 'warn' : 'ok' },
    { label: 'WhatsApp',     val: data.whatsapp_numero,      status: 'ok' },
  ];

  pageContent.innerHTML = `
    <div class="page-header">
      <div class="page-title">Sistema</div>
      <div class="page-subtitle">Status dos componentes de infraestrutura</div>
    </div>
    <div class="health-grid">
      ${items.map(i => `
        <div class="health-card">
          <h4>${i.label}</h4>
          <div class="health-val">
            <span class="status-dot ${i.status}"></span>${esc(String(i.val))}
          </div>
        </div>
      `).join('')}
    </div>
    <p class="tiny" style="margin-top: var(--sp-6); text-align:right">
      Atualizado às ${new Date().toLocaleTimeString('pt-BR')}
      — <button class="briefing-expand" onclick="renderAdminSistema()">Atualizar</button>
    </p>
  `;
}

// ── Modals ─────────────────────────────────────────────────────
function modalNovoCliente() {
  showModal(`
    <div class="modal-title">Novo cliente</div>
    <form id="form-cliente">
      <div class="form-field"><label>Nome</label><input id="mc-nome" placeholder="K2Con" required /></div>
      <div class="form-field"><label>Slug</label><input id="mc-slug" placeholder="k2con" required /></div>
      <div class="form-field"><label>Grupo WhatsApp</label><input id="mc-grupo" placeholder="k2con" /></div>
      <div class="form-field">
        <label>Plano</label>
        <select id="mc-plano">
          <option value="premium">Premium</option>
          <option value="basic">Basic</option>
        </select>
      </div>
      <div id="mc-error" class="error-msg hidden"></div>
      <div class="modal-footer">
        <button type="button" class="btn btn-ghost" onclick="closeModal()">Cancelar</button>
        <button type="submit" class="btn btn-secondary">Criar cliente</button>
      </div>
    </form>
  `);
  $('form-cliente').addEventListener('submit', async e => {
    e.preventDefault();
    const err = $('mc-error');
    err.classList.add('hidden');
    try {
      await api('/api/admin/clientes', { method: 'POST', body: {
        nome: $('mc-nome').value,
        slug: $('mc-slug').value,
        whatsapp_grupo: $('mc-grupo').value,
        plano: $('mc-plano').value,
      }});
      closeModal();
      showToast('Cliente criado!', 'ok');
      navigate('clientes');
    } catch (ex) {
      err.textContent = ex.message || 'Erro ao criar cliente.';
      err.classList.remove('hidden');
    }
  });
}

function modalNovoUsuario() {
  showModal(`
    <div class="modal-title">Novo usuário</div>
    <form id="form-usuario">
      <div class="form-field"><label>Nome</label><input id="mu-nome" required /></div>
      <div class="form-field"><label>E-mail</label><input type="email" id="mu-email" required /></div>
      <div class="form-field"><label>Senha</label><input type="password" id="mu-senha" required minlength="8" /></div>
      <div class="form-field">
        <label>Papel</label>
        <select id="mu-papel">
          <option value="cliente">Cliente</option>
          <option value="admin">Admin EG</option>
        </select>
      </div>
      <div class="form-field"><label>cliente_id (opcional)</label><input type="number" id="mu-cid" placeholder="1" /></div>
      <div id="mu-error" class="error-msg hidden"></div>
      <div class="modal-footer">
        <button type="button" class="btn btn-ghost" onclick="closeModal()">Cancelar</button>
        <button type="submit" class="btn btn-secondary">Criar usuário</button>
      </div>
    </form>
  `);
  $('form-usuario').addEventListener('submit', async e => {
    e.preventDefault();
    const err = $('mu-error');
    err.classList.add('hidden');
    const cid = $('mu-cid').value;
    try {
      await api('/api/admin/usuarios', { method: 'POST', body: {
        nome: $('mu-nome').value,
        email: $('mu-email').value,
        senha: $('mu-senha').value,
        papel: $('mu-papel').value,
        cliente_id: cid ? parseInt(cid) : null,
      }});
      closeModal();
      showToast('Usuário criado!', 'ok');
      navigate('usuarios');
    } catch (ex) {
      err.textContent = ex.message || 'Erro ao criar usuário.';
      err.classList.remove('hidden');
    }
  });
}

function showModal(html) {
  closeModal();
  const overlay = document.createElement('div');
  overlay.className = 'modal-overlay';
  overlay.id = 'modal-overlay';
  overlay.innerHTML = `<div class="modal">${html}</div>`;
  overlay.addEventListener('click', e => { if (e.target === overlay) closeModal(); });
  document.body.appendChild(overlay);
}

function closeModal() {
  const el = $('modal-overlay');
  if (el) el.remove();
}

// ── HTML builders ───────────────────────────────────────────────
function execucaoHtml(e) {
  return `
    <div class="timeline-item">
      <div class="timeline-icon">${acaoEmoji(e.acao)}</div>
      <div class="timeline-body">
        <div class="timeline-top">
          <div>
            <div class="timeline-action">${acaoLabel(e.acao)}</div>
            <div class="timeline-project">${esc(e.projeto || '')}${e.cliente_nome ? ` · ${esc(e.cliente_nome)}` : ''}</div>
          </div>
          ${resultadoBadge(e.resultado)}
        </div>
        ${e.conteudo_resumo ? `<div class="timeline-content">${esc(e.conteudo_resumo)}</div>` : ''}
        <div class="timeline-meta">
          <span class="timeline-time">${tempoRelativo(e.criado_em)}</span>
          ${e.remetente ? `<span class="timeline-sender">· ${esc(e.remetente)}</span>` : ''}
        </div>
      </div>
    </div>
  `;
}

function receitaHtml(r) {
  const statusMap = { ativa: 'badge-ok', pausada: 'badge-warn', erro: 'badge-danger' };
  const statusLabel = { ativa: 'Ativa', pausada: 'Pausada', erro: 'Com erro' };
  return `
    <div class="recipe-card">
      <div class="recipe-header">
        <div class="recipe-name">${esc(r.nome)}</div>
        <span class="badge ${statusMap[r.status] || 'badge-neutral'}">${statusLabel[r.status] || r.status}</span>
      </div>
      ${r.descricao ? `<div class="recipe-desc">${esc(r.descricao)}</div>` : ''}
      ${r.gatilho ? `<div class="recipe-trigger">🎯 Gatilho: <span>${esc(r.gatilho)}</span></div>` : ''}
      <div class="recipe-footer">
        <div class="recipe-stat">
          Sistema: <strong>${esc(r.sistema_destino || '—')}</strong>
        </div>
        <div class="recipe-stat">
          <strong>${r.total_execucoes ?? 0}</strong> execuções
        </div>
      </div>
      ${r.ultima_execucao ? `<div class="recipe-stat">Última: ${tempoRelativo(r.ultima_execucao)}</div>` : ''}
    </div>
  `;
}

function briefingHtml(b) {
  const id = `brief-${b.id}`;
  return `
    <div class="briefing-item">
      <div class="briefing-header">
        <div class="briefing-date">📬 ${formatData(b.data_referencia)}</div>
        <div style="display:flex;gap:8px;align-items:center">
          <span class="tiny">${tempoRelativo(b.enviado_em)}</span>
          <span class="badge ${b.sucesso ? 'badge-ok' : 'badge-danger'}">${b.sucesso ? 'Enviado' : 'Falhou'}</span>
        </div>
      </div>
      <div class="briefing-content" id="${id}">${esc(b.conteudo || '(sem conteúdo)')}</div>
      <button class="briefing-expand" onclick="toggleBriefing('${id}', this)">Ver completo ↓</button>
    </div>
  `;
}

function toggleBriefing(id, btn) {
  const el = $(id);
  const expanded = el.classList.toggle('expanded');
  btn.textContent = expanded ? 'Recolher ↑' : 'Ver completo ↓';
}

// ── Utility HTML ───────────────────────────────────────────────
function loadingHtml(msg = 'Carregando…') {
  return `<div class="loading-center"><div class="spinner"></div>${msg}</div>`;
}

function errorHtml(msg = 'Erro ao carregar dados. Tente novamente.') {
  return `<div class="empty-state"><div class="empty-icon">⚠️</div><p>${msg}</p></div>`;
}

function emptyHtml(msg, icon = '📭') {
  return `<div class="empty-state"><div class="empty-icon">${icon}</div><p>${msg}</p></div>`;
}

// ── Formatters ─────────────────────────────────────────────────
function esc(s) {
  return String(s ?? '')
    .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
    .replace(/"/g,'&quot;').replace(/'/g,'&#39;');
}

function tempoRelativo(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  const diff = Date.now() - d.getTime();
  const min  = Math.floor(diff / 60000);
  const h    = Math.floor(diff / 3600000);
  const dias = Math.floor(diff / 86400000);
  if (min < 1)  return 'agora mesmo';
  if (min < 60) return `há ${min} min`;
  if (h < 24)   return `há ${h}h`;
  if (dias < 7) return `há ${dias} dia${dias > 1 ? 's' : ''}`;
  return d.toLocaleDateString('pt-BR');
}

function formatData(iso) {
  if (!iso) return '—';
  return new Date(iso).toLocaleDateString('pt-BR', { day: '2-digit', month: 'short', year: 'numeric' });
}

function periodoLabel(p) {
  return { hoje: 'Hoje', semana: 'Esta semana', mes: 'Este mês', tudo: 'Tudo' }[p] || p;
}

// ── Configurações ──────────────────────────────────────────────

async function renderConfiguracoes() {
  pageContent.innerHTML = loadingHtml('Carregando configurações…');

  const cfg = await api('/api/admin/configuracoes').catch(() => null);
  if (!cfg) { pageContent.innerHTML = errorHtml('Não foi possível carregar as configurações.'); return; }

  const v = (chave, padrao = '') => cfg[chave]?.valor ?? padrao;
  const preenchido = chave => cfg[chave]?.preenchido ? '✅' : '⚠️';

  pageContent.innerHTML = `
    <div class="page-header">
      <div class="page-title">Configurações</div>
      <div class="page-subtitle">Gerencie as integrações do sistema sem editar arquivos</div>
    </div>

    <!-- ── E-mail ─────────────────────────────────────────────── -->
    <div class="cfg-section">
      <div class="cfg-section-header">
        <span class="cfg-section-icon">📧</span>
        <div>
          <div class="cfg-section-title">E-mail</div>
          <div class="cfg-section-desc">Conta Gmail usada para envio de e-mails via WhatsApp</div>
        </div>
        <span id="badge-email" class="cfg-badge ${cfg.gmail_app_password?.preenchido ? 'badge-ok' : 'badge-warn'}">
          ${cfg.gmail_app_password?.preenchido ? 'Configurado' : 'Pendente'}
        </span>
      </div>
      <form id="form-email" class="cfg-form">
        <div class="cfg-row">
          <div class="form-field">
            <label>Conta Gmail</label>
            <input id="cfg-gmail-user" type="email" placeholder="info@effectivegain.com"
                   value="${esc(v('gmail_user'))}" />
          </div>
          <div class="form-field">
            <label>Nome do remetente</label>
            <input id="cfg-email-nome" type="text" placeholder="Effective Gain"
                   value="${esc(v('email_remetente_nome', 'Effective Gain'))}" />
          </div>
        </div>
        <div class="cfg-row">
          <div class="form-field">
            <label>Senha de app Gmail <a class="cfg-link" href="https://myaccount.google.com/apppasswords" target="_blank">↗ Gerar</a></label>
            <input id="cfg-gmail-pass" type="password" placeholder="${cfg.gmail_app_password?.preenchido ? '••••••••' : 'xxxx xxxx xxxx xxxx'}" />
            <span class="form-hint">Deixe em branco para manter a senha atual</span>
          </div>
          <div class="form-field">
            <label>Servidor SMTP</label>
            <input id="cfg-smtp-host" type="text" value="${esc(v('smtp_host', 'smtp.gmail.com'))}" />
          </div>
        </div>
        <div class="cfg-actions">
          <button type="submit" class="btn btn-primary">Salvar e-mail</button>
          <button type="button" class="btn btn-secondary" onclick="testarEmail()">Testar conexão</button>
          <span id="status-email" class="cfg-status"></span>
        </div>
      </form>
    </div>

    <!-- ── WhatsApp ───────────────────────────────────────────── -->
    <div class="cfg-section">
      <div class="cfg-section-header">
        <span class="cfg-section-icon">💬</span>
        <div>
          <div class="cfg-section-title">WhatsApp</div>
          <div class="cfg-section-desc">Instância Evolution API conectada ao número +55 31 97224-4045</div>
        </div>
        <span class="cfg-badge ${cfg.evolution_instance?.preenchido ? 'badge-ok' : 'badge-warn'}">
          ${cfg.evolution_instance?.preenchido ? 'Configurado' : 'Pendente'}
        </span>
      </div>
      <form id="form-whatsapp" class="cfg-form">
        <div class="cfg-row">
          <div class="form-field">
            <label>Nome da instância Evolution API</label>
            <input id="cfg-wa-instance" type="text" placeholder="effectivegain"
                   value="${esc(v('evolution_instance'))}" />
            <span class="form-hint">Mesmo nome criado no painel Evolution API</span>
          </div>
        </div>
        <div class="cfg-actions">
          <button type="submit" class="btn btn-primary">Salvar WhatsApp</button>
          <span id="status-whatsapp" class="cfg-status"></span>
        </div>
      </form>
    </div>

    <!-- ── Obsidian ──────────────────────────────────────────── -->
    <div class="cfg-section">
      <div class="cfg-section-header">
        <span class="cfg-section-icon">🗂</span>
        <div>
          <div class="cfg-section-title">Obsidian</div>
          <div class="cfg-section-desc">Vault onde as notas, tasks e decisões são registradas</div>
        </div>
        <span class="cfg-badge ${cfg.obsidian_api_key?.preenchido ? 'badge-ok' : 'badge-warn'}">
          ${cfg.obsidian_api_key?.preenchido ? 'Configurado' : 'Pendente'}
        </span>
      </div>
      <form id="form-obsidian" class="cfg-form">
        <div class="cfg-row">
          <div class="form-field">
            <label>URL da API <span class="form-hint" style="display:inline">padrão: http://localhost:27124</span></label>
            <input id="cfg-obsidian-url" type="text"
                   value="${esc(v('obsidian_api_url', 'http://localhost:27124'))}" />
          </div>
          <div class="form-field">
            <label>Chave da API <a class="cfg-link" href="obsidian://preferences/community-plugins" target="_blank">↗ Abrir Obsidian</a></label>
            <input id="cfg-obsidian-key" type="password"
                   placeholder="${cfg.obsidian_api_key?.preenchido ? '••••••••' : 'Cole a chave do plugin Local REST API'}" />
            <span class="form-hint">Deixe em branco para manter a chave atual</span>
          </div>
        </div>
        <div class="cfg-actions">
          <button type="submit" class="btn btn-primary">Salvar Obsidian</button>
          <span id="status-obsidian" class="cfg-status"></span>
        </div>
      </form>
    </div>

    <!-- ── Segurança ──────────────────────────────────────────── -->
    <div class="cfg-section">
      <div class="cfg-section-header">
        <span class="cfg-section-icon">🔒</span>
        <div>
          <div class="cfg-section-title">Segurança</div>
          <div class="cfg-section-desc">Chave secreta para autenticar o webhook da Evolution API</div>
        </div>
        <span class="cfg-badge ${cfg.webhook_secret?.preenchido ? 'badge-ok' : 'badge-warn'}">
          ${cfg.webhook_secret?.preenchido ? 'Configurado' : 'Pendente'}
        </span>
      </div>
      <form id="form-seguranca" class="cfg-form">
        <div class="cfg-row">
          <div class="form-field">
            <label>Webhook Secret</label>
            <input id="cfg-webhook-secret" type="password"
                   placeholder="${cfg.webhook_secret?.preenchido ? '••••••••' : 'String aleatória segura'}" />
            <span class="form-hint">Configure o mesmo valor na Evolution API → x-webhook-secret</span>
          </div>
        </div>
        <div class="cfg-actions">
          <button type="submit" class="btn btn-primary">Salvar</button>
          <button type="button" class="btn btn-secondary" onclick="gerarSecret()">Gerar automaticamente</button>
          <span id="status-seguranca" class="cfg-status"></span>
        </div>
      </form>
    </div>

    <!-- ── Briefing ───────────────────────────────────────────── -->
    <div class="cfg-section">
      <div class="cfg-section-header">
        <span class="cfg-section-icon">☀️</span>
        <div>
          <div class="cfg-section-title">Briefing matinal</div>
          <div class="cfg-section-desc">Resumo diário enviado automaticamente pelo WhatsApp</div>
        </div>
        <label class="cfg-toggle">
          <input type="checkbox" id="cfg-briefing-ativo"
                 ${v('briefing_ativo', 'true') === 'true' ? 'checked' : ''} />
          <span class="cfg-toggle-track"></span>
        </label>
      </div>
      <form id="form-briefing" class="cfg-form">
        <div class="cfg-row">
          <div class="form-field">
            <label>Número de destino (WhatsApp)</label>
            <input id="cfg-briefing-numero" type="text" placeholder="5531972244045"
                   value="${esc(v('briefing_numero_destino'))}" />
            <span class="form-hint">Só números, com DDI (ex: 5531972244045)</span>
          </div>
          <div class="form-field">
            <label>Horário de envio</label>
            <input id="cfg-briefing-hora" type="time" value="${esc(v('briefing_hora', '08:00'))}" />
          </div>
        </div>
        <div class="cfg-actions">
          <button type="submit" class="btn btn-primary">Salvar briefing</button>
          <span id="status-briefing" class="cfg-status"></span>
        </div>
      </form>
    </div>
  `;

  // ── Handlers de submit ──────────────────────────────────────

  $('form-email').addEventListener('submit', async e => {
    e.preventDefault();
    const st = $('status-email');
    const btn = e.target.querySelector('[type=submit]');
    btn.disabled = true;
    st.textContent = 'Salvando…';
    st.className = 'cfg-status';

    try {
      const res = await api('/api/admin/configuracoes/email', {
        method: 'POST',
        body: {
          gmail_user:          $('cfg-gmail-user').value.trim(),
          gmail_app_password:  $('cfg-gmail-pass').value,
          email_remetente_nome: $('cfg-email-nome').value.trim(),
          smtp_host:           $('cfg-smtp-host').value.trim(),
          smtp_port:           '587',
        },
      });
      const ok = res.status === 'ativo';
      st.textContent = ok ? '✅ E-mail ativo e funcionando' : `⚠️ Salvo — ${res.status}`;
      st.className   = 'cfg-status ' + (ok ? 'cfg-ok' : 'cfg-warn');
      if (ok) $('badge-email').className = 'cfg-badge badge-ok';
      $('badge-email').textContent = ok ? 'Configurado' : 'Verificar';
    } catch (ex) {
      st.textContent = '❌ ' + (ex.message || 'Erro ao salvar');
      st.className = 'cfg-status cfg-err';
    } finally {
      btn.disabled = false;
    }
  });

  $('form-whatsapp').addEventListener('submit', async e => {
    e.preventDefault();
    const st = $('status-whatsapp');
    const btn = e.target.querySelector('[type=submit]');
    btn.disabled = true;
    st.textContent = 'Salvando…';
    st.className = 'cfg-status';

    try {
      const res = await api('/api/admin/configuracoes/whatsapp', {
        method: 'POST',
        body: { evolution_instance: $('cfg-wa-instance').value.trim() },
      });
      const ok = res.status === 'ativo';
      st.textContent = ok ? '✅ WhatsApp conectado' : `⚠️ Salvo — ${res.status}`;
      st.className   = 'cfg-status ' + (ok ? 'cfg-ok' : 'cfg-warn');
    } catch (ex) {
      st.textContent = '❌ ' + (ex.message || 'Erro ao salvar');
      st.className = 'cfg-status cfg-err';
    } finally {
      btn.disabled = false;
    }
  });

  $('form-obsidian').addEventListener('submit', async e => {
    e.preventDefault();
    const st  = $('status-obsidian');
    const btn = e.target.querySelector('[type=submit]');
    btn.disabled = true;
    st.textContent = 'Salvando…';
    st.className = 'cfg-status';
    try {
      const body = { obsidian_api_url: $('cfg-obsidian-url').value.trim() };
      const key = $('cfg-obsidian-key').value;
      if (key) body.obsidian_api_key = key;
      await api('/api/admin/configuracoes/generico', { method: 'POST', body });
      st.textContent = '✅ Obsidian salvo — aplica no próximo reinício';
      st.className = 'cfg-status cfg-ok';
    } catch (ex) {
      st.textContent = '❌ ' + (ex.message || 'Erro ao salvar');
      st.className = 'cfg-status cfg-err';
    } finally {
      btn.disabled = false;
    }
  });

  $('form-seguranca').addEventListener('submit', async e => {
    e.preventDefault();
    const st  = $('status-seguranca');
    const btn = e.target.querySelector('[type=submit]');
    btn.disabled = true;
    st.textContent = 'Salvando…';
    st.className = 'cfg-status';
    try {
      const secret = $('cfg-webhook-secret').value;
      if (!secret) { st.textContent = '⚠️ Informe a chave'; st.className = 'cfg-status cfg-warn'; btn.disabled = false; return; }
      await api('/api/admin/configuracoes/generico', { method: 'POST', body: { webhook_secret: secret } });
      st.textContent = '✅ Secret salvo — ativo imediatamente';
      st.className = 'cfg-status cfg-ok';
      $('cfg-webhook-secret').value = '';
    } catch (ex) {
      st.textContent = '❌ ' + (ex.message || 'Erro ao salvar');
      st.className = 'cfg-status cfg-err';
    } finally {
      btn.disabled = false;
    }
  });

  $('form-briefing').addEventListener('submit', async e => {
    e.preventDefault();
    const st  = $('status-briefing');
    const btn = e.target.querySelector('[type=submit]');
    btn.disabled = true;
    st.textContent = 'Salvando…';
    st.className = 'cfg-status';

    try {
      await api('/api/admin/configuracoes/briefing', {
        method: 'POST',
        body: {
          briefing_numero_destino: $('cfg-briefing-numero').value.trim(),
          briefing_hora:           $('cfg-briefing-hora').value,
          briefing_ativo:          $('cfg-briefing-ativo').checked ? 'true' : 'false',
        },
      });
      st.textContent = '✅ Briefing salvo — aplica no próximo reinício';
      st.className = 'cfg-status cfg-ok';
    } catch (ex) {
      st.textContent = '❌ ' + (ex.message || 'Erro ao salvar');
      st.className = 'cfg-status cfg-err';
    } finally {
      btn.disabled = false;
    }
  });
}

function gerarSecret() {
  const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789';
  const arr   = crypto.getRandomValues(new Uint8Array(32));
  const secret = Array.from(arr).map(b => chars[b % chars.length]).join('');
  const input = $('cfg-webhook-secret');
  if (input) {
    input.value = secret;
    input.type  = 'text';
    setTimeout(() => { if (input) input.type = 'password'; }, 4000);
  }
}

async function testarEmail() {
  const st = $('status-email');
  st.textContent = 'Testando…';
  st.className = 'cfg-status';
  try {
    const res = await api('/api/admin/configuracoes/testar-email', { method: 'POST' });
    const ok  = res.status === 'ok';
    st.textContent = ok ? '✅ ' + res.mensagem : '❌ ' + res.mensagem;
    st.className   = 'cfg-status ' + (ok ? 'cfg-ok' : 'cfg-err');
  } catch (ex) {
    st.textContent = '❌ ' + (ex.message || 'Erro no teste');
    st.className = 'cfg-status cfg-err';
  }
}

// ── Labels e emojis ────────────────────────────────────────────

const ACAO_LABELS = {
  criar_nota:           'Nota criada',
  criar_reuniao:        'Reunião agendada',
  criar_task:           'Task criada',
  registrar_decisao:    'Decisão registrada',
  registrar_lancamento: 'Lançamento registrado',
  criar_daily:          'Daily criada',
  atualizar_status:     'Status atualizado',
  consultar_tasks:      'Tasks consultadas',
  enviar_email:         'E-mail enviado',
  responder_email:      'E-mail respondido',
  encaminhar_email:     'E-mail encaminhado',
  criar_rascunho:       'Rascunho criado',
  ambigua:              'Mensagem ambígua',
};

const ACAO_EMOJIS = {
  criar_nota:           '📝',
  criar_reuniao:        '📅',
  criar_task:           '✅',
  registrar_decisao:    '🎯',
  registrar_lancamento: '💰',
  criar_daily:          '📆',
  atualizar_status:     '🔄',
  consultar_tasks:      '📋',
  enviar_email:         '📧',
  responder_email:      '↩️',
  encaminhar_email:     '↪️',
  criar_rascunho:       '✉️',
  ambigua:              '❓',
};

function acaoLabel(a)  { return ACAO_LABELS[a]  || a || '—'; }
function acaoEmoji(a)  { return ACAO_EMOJIS[a]  || '⚡'; }

function resultadoBadge(r) {
  const map = { sucesso: 'badge-ok', erro: 'badge-danger', ambigua: 'badge-warn' };
  const lbl = { sucesso: 'Sucesso', erro: 'Erro', ambigua: 'Ambígua' };
  return `<span class="badge ${map[r] || 'badge-neutral'}">${lbl[r] || r}</span>`;
}

function planoBadge(p) {
  return p === 'premium'
    ? '<span class="badge badge-accent">Premium</span>'
    : '<span class="badge badge-neutral">Basic</span>';
}

function papelBadge(p) {
  return p === 'admin'
    ? '<span class="badge badge-accent">Admin EG</span>'
    : '<span class="badge badge-neutral">Cliente</span>';
}

// ── Toast ───────────────────────────────────────────────────────
let _toastTimer;
function showToast(msg, type = 'ok') {
  clearTimeout(_toastTimer);
  toast.textContent = msg;
  toast.className = `toast-${type}`;
  _toastTimer = setTimeout(() => { toast.classList.add('toast-hidden'); }, 3500);
}

// ── API helper ─────────────────────────────────────────────────
async function api(url, opts = {}) {
  const res = await fetch(url, {
    method: opts.method || 'GET',
    headers: { 'Content-Type': 'application/json' },
    body: opts.body ? JSON.stringify(opts.body) : undefined,
    credentials: 'same-origin',
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }
  return res.json();
}
