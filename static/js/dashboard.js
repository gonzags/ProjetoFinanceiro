/**
 * dashboard.js - Lógica Frontend, ApexCharts, Modo Escuro e Integrações REST
 * Ledger Horizon Analytics Platform
 */

let timelineChart = null;
let donutChart = null;

// Cores alinhadas com o Design System Ledger Horizon
function getThemeColors() {
  const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
  return {
    cobalt: isDark ? '#4A90E2' : '#1E56A0',
    amber: isDark ? '#E59830' : '#B76E00',
    green: isDark ? '#2EA884' : '#1A7F64',
    inkSubdued: isDark ? '#8B9BAE' : '#5A6A80',
    border: isDark ? '#2A3441' : '#E2E8F0',
    panel: isDark ? '#151B22' : '#FFFFFF',
    textMain: isDark ? '#F0F4F8' : '#1C2530'
  };
}

// -----------------------------------------------------------------------------
// Gerenciamento de Tema (Dark / Light Mode)
// -----------------------------------------------------------------------------
function initTheme() {
  const savedTheme = localStorage.getItem('lh_theme') || 'light';
  document.documentElement.setAttribute('data-theme', savedTheme);
  updateThemeIcons(savedTheme);
}

function toggleTheme() {
  const current = document.documentElement.getAttribute('data-theme') || 'light';
  const newTheme = current === 'light' ? 'dark' : 'light';
  document.documentElement.setAttribute('data-theme', newTheme);
  localStorage.setItem('lh_theme', newTheme);
  updateThemeIcons(newTheme);
  refreshChartsTheme();
}

function updateThemeIcons(theme) {
  const sunIcon = document.getElementById('themeIconSun');
  const moonIcon = document.getElementById('themeIconMoon');
  if (theme === 'dark') {
    if (sunIcon) sunIcon.style.display = 'block';
    if (moonIcon) moonIcon.style.display = 'none';
  } else {
    if (sunIcon) sunIcon.style.display = 'none';
    if (moonIcon) moonIcon.style.display = 'block';
  }
}

// -----------------------------------------------------------------------------
// Formatação de Moeda e Valores
// -----------------------------------------------------------------------------
function formatCurrency(val) {
  return new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(val);
}

// -----------------------------------------------------------------------------
// Inicialização dos Gráficos com ApexCharts
// -----------------------------------------------------------------------------
function initTimelineChart(data) {
  const colors = getThemeColors();
  const categories = data.map(d => d.month);
  const fixedCosts = data.map(d => d.fixed_costs);
  const debtsTotal = data.map(d => d.debts_total + (d.special_events || 0));
  const surplus = data.map(d => d.net_surplus);

  const options = {
    chart: {
      type: 'bar',
      height: 330,
      stacked: true,
      toolbar: { show: false },
      fontFamily: 'Plus Jakarta Sans, sans-serif'
    },
    colors: [colors.cobalt, colors.amber, colors.green],
    plotOptions: {
      bar: {
        horizontal: false,
        borderRadius: 4,
        columnWidth: '55%'
      }
    },
    dataLabels: { enabled: false },
    series: [
      { name: 'Custos Fixos', data: fixedCosts },
      { name: 'Dívidas & Compromissos', data: debtsTotal },
      { name: 'Sobra Líquida Real', data: surplus }
    ],
    xaxis: {
      categories: categories,
      labels: {
        style: { colors: colors.inkSubdued, fontSize: '12px' }
      },
      axisBorder: { color: colors.border },
      axisTicks: { color: colors.border }
    },
    yaxis: {
      labels: {
        style: { colors: colors.inkSubdued, fontSize: '12px' },
        formatter: (val) => `R$ ${val.toFixed(0)}`
      }
    },
    legend: {
      position: 'top',
      horizontalAlign: 'right',
      labels: { colors: colors.textMain }
    },
    grid: {
      borderColor: colors.border,
      strokeDashArray: 4
    },
    tooltip: {
      y: { formatter: (val) => formatCurrency(val) }
    }
  };

  const el = document.querySelector("#chartCashFlowTimeline");
  if (el) {
    el.innerHTML = '';
    timelineChart = new ApexCharts(el, options);
    timelineChart.render();
  }
}

function initMethodologyDonut(nec = 50, des = 30, fut = 20) {
  const colors = getThemeColors();
  const options = {
    chart: {
      type: 'donut',
      height: 250,
      fontFamily: 'Plus Jakarta Sans, sans-serif'
    },
    colors: [colors.cobalt, colors.amber, colors.green],
    labels: ['Necessidades', 'Desejos', 'Futuro'],
    series: [nec, des, fut],
    dataLabels: {
      enabled: true,
      formatter: (val) => `${val.toFixed(0)}%`
    },
    legend: {
      position: 'bottom',
      labels: { colors: colors.textMain }
    },
    stroke: {
      colors: [colors.panel],
      width: 2
    },
    tooltip: {
      y: { formatter: (val) => `${val}%` }
    }
  };

  const el = document.querySelector("#chartMethodologyDonut");
  if (el) {
    el.innerHTML = '';
    donutChart = new ApexCharts(el, options);
    donutChart.render();
  }
}

function refreshChartsTheme() {
  const colors = getThemeColors();
  if (timelineChart) {
    timelineChart.updateOptions({
      colors: [colors.cobalt, colors.amber, colors.green],
      xaxis: { labels: { style: { colors: colors.inkSubdued } } },
      yaxis: { labels: { style: { colors: colors.inkSubdued } } },
      legend: { labels: { colors: colors.textMain } },
      grid: { borderColor: colors.border }
    });
  }
  if (donutChart) {
    donutChart.updateOptions({
      colors: [colors.cobalt, colors.amber, colors.green],
      legend: { labels: { colors: colors.textMain } },
      stroke: { colors: [colors.panel] }
    });
  }
}

let currentTimeline = [];
let currentKPIs = null;
let lastActiveElement = null;

// -----------------------------------------------------------------------------
// Régua de Liquidez Dinâmica (The Debt-Free Horizon Gauge)
// -----------------------------------------------------------------------------
function updateHorizonGauge(timeline, kpis) {
  if (!timeline || timeline.length === 0) return;
  const oct = timeline[0];

  // Cálculo do percentual de progresso de libertação de dívidas
  const freePct = kpis?.metrics?.gauge_progress_pct ?? 
    Math.round(((oct.total_income - oct.debts_total) / oct.total_income) * 100);
  const safePct = Math.max(0, Math.min(100, Math.round(freePct)));

  const fillEl = document.getElementById('gaugeFill');
  const trackEl = document.getElementById('gaugeTrack');
  const pctLabel = document.getElementById('gaugePctLabel');

  if (fillEl) fillEl.style.width = `${safePct}%`;
  if (trackEl) {
    trackEl.setAttribute('aria-valuenow', safePct);
    trackEl.setAttribute('aria-label', `Progresso rumo à liquidação das dívidas: ${safePct}% da renda livre`);
  }
  if (pctLabel) pctLabel.textContent = `${safePct}%`;

  // Atualização dinâmica dos marcos na timeline
  const milestonesGrid = document.getElementById('milestonesGrid');
  if (milestonesGrid && timeline.length >= 7) {
    const m0 = timeline[0]; // Outubro
    const m1 = timeline[1]; // Novembro
    const m2 = timeline[2]; // Dezembro
    const m6 = timeline[6]; // Abril+

    milestonesGrid.innerHTML = `
      <div class="lh-milestone-item">
        <div class="lh-milestone-month">${m0.month} 2026</div>
        <div class="lh-milestone-details">${m0.status_label || 'Zona Crítica'} (Sobra ${formatCurrency(m0.net_surplus)})</div>
      </div>
      <div class="lh-milestone-item">
        <div class="lh-milestone-month">${m1.month} 2026</div>
        <div class="lh-milestone-details">Alívio (+${formatCurrency(m1.net_surplus)}) • Reserva</div>
      </div>
      <div class="lh-milestone-item">
        <div class="lh-milestone-month">${m2.month} 2026</div>
        <div class="lh-milestone-details">Folga Sólida (+${formatCurrency(m2.net_surplus)})</div>
      </div>
      <div class="lh-milestone-item">
        <div class="lh-milestone-month">${m6.month} 2027+</div>
        <div class="lh-milestone-details text-green"><strong>Liberdade: +${formatCurrency(m6.net_surplus)} livre</strong></div>
      </div>
    `;
  }
}

// -----------------------------------------------------------------------------
// Chamadas à API REST
// -----------------------------------------------------------------------------
async function loadTimeline() {
  try {
    const res = await fetch('/api/timeline');
    if (!res.ok) throw new Error('Falha ao carregar timeline');
    const data = await res.json();
    currentTimeline = data;
    initTimelineChart(data);
    updateHorizonGauge(currentTimeline, currentKPIs);
  } catch (e) {
    console.error('Erro na timeline:', e);
  }
}

async function loadKPIs() {
  try {
    const res = await fetch('/api/kpis?month=Outubro');
    if (!res.ok) throw new Error('Falha ao carregar KPIs');
    const data = await res.json();
    currentKPIs = data;
    const s = data.summary;
    const m = data.metrics;

    document.getElementById('kpiIncome').textContent = formatCurrency(s.total_income);
    document.getElementById('kpiFixed').textContent = formatCurrency(s.fixed_costs);
    document.getElementById('kpiDebts').textContent = formatCurrency(s.debts_total + (s.special_events || 0));
    
    const surplusEl = document.getElementById('kpiSurplus');
    surplusEl.textContent = (s.net_surplus >= 0 ? '+ ' : '- ') + formatCurrency(Math.abs(s.net_surplus));

    // Subtítulos dinâmicos
    const incomeSub = document.getElementById('kpiIncomeSub');
    if (incomeSub) incomeSub.textContent = `Salário ${formatCurrency(s.salary_net)} + Extras ${formatCurrency(s.receivables || 0)}`;

    const fixedSub = document.getElementById('kpiFixedSub');
    if (fixedSub) fixedSub.textContent = `${m.fixed_ratio_pct}% da renda líquida`;

    const debtsSub = document.getElementById('kpiDebtsSub');
    if (debtsSub) debtsSub.textContent = `PicPay ${formatCurrency(s.picpay_amount)} • Nu ${formatCurrency(s.nubank_amount)}`;

    const surplusDiag = document.getElementById('kpiSurplusDiag');
    if (surplusDiag) surplusDiag.textContent = s.net_surplus > 500 ? 'Folga sólida consolidada' : 'Zona crítica controlada • Saldo positivo';

    updateHorizonGauge(currentTimeline, currentKPIs);
  } catch (e) {
    console.error('Erro nos KPIs:', e);
  }
}

async function loadConsensus() {
  try {
    const res = await fetch('/api/consensus?month=Outubro');
    if (!res.ok) throw new Error('Falha ao carregar consenso');
    const data = await res.json();
    renderConsensus(data);
  } catch (e) {
    console.error('Erro no consenso:', e);
  }
}

function renderConsensus(data) {
  const badge = document.getElementById('consensusBadge');
  const badgeText = document.getElementById('consensusBadgeText');
  const headerBadge = document.getElementById('headerStatusBadge');
  const headerStatusText = document.getElementById('headerStatusText');

  // Atualiza badge de consenso
  if (data.consensus_status === 'total') {
    badge.className = 'lh-badge lh-badge-status-connected';
    badgeText.textContent = 'Consenso Total Atingido';
  } else if (data.consensus_status === 'parcial') {
    badge.className = 'lh-badge lh-badge-status-partial';
    badgeText.textContent = 'Consenso Parcial (3 Rodadas)';
    if (headerBadge && headerStatusText) {
      headerBadge.className = 'lh-badge lh-badge-status-partial';
      headerStatusText.textContent = 'Consenso parcial (3 rodadas sem convergência total)';
    }
  } else {
    badge.className = 'lh-badge lh-badge-status-demo';
    badgeText.textContent = 'Fallback Determinístico Local';
  }

  // Alocações
  const alloc = data.allocation;
  document.getElementById('aiAllocNec').textContent = `${alloc.necessidades.toFixed(1)}%`;
  document.getElementById('aiAllocDes').textContent = `${alloc.desejos.toFixed(1)}%`;
  document.getElementById('aiAllocFut').textContent = `${alloc.futuro.toFixed(1)}%`;

  // Confiança e Parecer
  const confPct = Math.round(data.confidence_score * 100);
  document.getElementById('aiConfidenceScore').textContent = `Confiança: ${confPct}%`;
  document.getElementById('aiReasoningQuote').textContent = `"${data.reasoning_summary}"`;

  // Flags de Risco
  const tagsContainer = document.getElementById('aiRiskTagsContainer');
  tagsContainer.innerHTML = '';
  if (data.risk_flags && data.risk_flags.length > 0) {
    data.risk_flags.forEach(flag => {
      const span = document.createElement('span');
      span.className = 'lh-risk-tag';
      span.textContent = `⚠ ${flag}`;
      tagsContainer.appendChild(span);
    });
  } else {
    tagsContainer.innerHTML = '<span class="lh-risk-tag">Nenhum sinal crítico detectado.</span>';
  }

  // Metadados
  const provs = data.participating_providers || [];
  document.getElementById('aiProvidersMeta').textContent = 
    provs.length > 0 ? `Provedores participantes: ${provs.join(', ')}` : 'Modo determinístico local';
  document.getElementById('aiRoundsMeta').textContent = 
    `Rodadas executadas: ${data.rounds_executed || 1}`;
}

// -----------------------------------------------------------------------------
// Recalcular Consenso (com Rate Limiting de 3/hora)
// -----------------------------------------------------------------------------
async function recalculateConsensus() {
  const btn = document.getElementById('recalculateBtn');
  const btnText = document.getElementById('recalculateBtnText');
  const rateNotice = document.getElementById('rateLimitNotice');

  btn.disabled = true;
  btnText.textContent = 'Deliberando...';
  rateNotice.style.display = 'none';

  try {
    const res = await fetch('/api/consensus/recalculate?month=Outubro', { method: 'POST' });
    if (res.status === 429) {
      rateNotice.style.display = 'block';
      rateNotice.textContent = 'Limite atingido: máximo de 3 recálculos por hora por IP.';
      return;
    }
    if (!res.ok) throw new Error('Erro ao recalcular');
    const data = await res.json();
    renderConsensus(data);
  } catch (e) {
    console.error('Erro no recálculo:', e);
  } finally {
    btn.disabled = false;
    btnText.textContent = 'Recalcular Decisões';
  }
}

// -----------------------------------------------------------------------------
// Alternar Metodologia
// -----------------------------------------------------------------------------
async function switchMethodology(methodology, btnElement) {
  // Atualiza classe ativa dos botões
  document.querySelectorAll('.lh-pill-btn').forEach(b => b.classList.remove('active'));
  if (btnElement) btnElement.classList.add('active');

  try {
    const res = await fetch('/api/methodology', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ methodology: methodology })
    });
    const data = await res.json();
    
    let pNec, pDes, pFut;
    if (methodology === 'zero_based') {
      pNec = data.percentages.necessidades;
      pDes = data.percentages.desejos;
      pFut = data.percentages.futuro + data.percentages.reserva_disponivel;
    } else {
      pNec = data.percentages.necessidades;
      pDes = data.percentages.desejos;
      pFut = data.percentages.futuro;
    }

    if (donutChart) {
      donutChart.updateSeries([pNec, pDes, pFut]);
    }

    const detailsEl = document.getElementById('methodologyDetails');
    if (detailsEl) {
      detailsEl.innerHTML = `Necessidades: <strong>${pNec}%</strong> • Desejos: <strong>${pDes}%</strong> • Futuro: <strong>${pFut}%</strong>`;
    }
  } catch (e) {
    console.error('Erro ao trocar metodologia:', e);
  }
}

// -----------------------------------------------------------------------------
// Modal do Questionário com Focus Trap e Esc Key
// -----------------------------------------------------------------------------
function updateFixedTotalPreview() {
  const ac = parseFloat(document.getElementById('inputFixedAcademia')?.value) || 0;
  const nr = parseFloat(document.getElementById('inputFixedNetRes')?.value) || 0;
  const nm = parseFloat(document.getElementById('inputFixedNetMov')?.value) || 0;
  const sp = parseFloat(document.getElementById('inputFixedSpotify')?.value) || 0;
  const gg = parseFloat(document.getElementById('inputFixedGoogle')?.value) || 0;
  const total = ac + nr + nm + sp + gg;
  const lbl = document.getElementById('labelFixedTotal');
  if (lbl) lbl.textContent = `Total: ${formatCurrency(total)}`;
}

function handleModalKeyDown(e) {
  const modal = document.getElementById('questionnaireModal');
  if (!modal || !modal.classList.contains('open')) return;

  if (e.key === 'Escape') {
    toggleQuestionnaireModal(false);
    return;
  }

  // Focus trap
  if (e.key === 'Tab') {
    const focusable = modal.querySelectorAll('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])');
    if (focusable.length === 0) return;
    const firstElement = focusable[0];
    const lastElement = focusable[focusable.length - 1];

    if (e.shiftKey) {
      if (document.activeElement === firstElement) {
        lastElement.focus();
        e.preventDefault();
      }
    } else {
      if (document.activeElement === lastElement) {
        firstElement.focus();
        e.preventDefault();
      }
    }
  }
}

function toggleQuestionnaireModal(show) {
  const modal = document.getElementById('questionnaireModal');
  if (!modal) return;

  if (show) {
    lastActiveElement = document.activeElement;
    modal.classList.add('open');
    document.addEventListener('keydown', handleModalKeyDown);
    updateFixedTotalPreview();

    // Foca o primeiro input acessível
    setTimeout(() => {
      const firstInput = document.getElementById('inputSalaryNet');
      if (firstInput) firstInput.focus();
    }, 50);
  } else {
    modal.classList.remove('open');
    document.removeEventListener('keydown', handleModalKeyDown);
    if (lastActiveElement && typeof lastActiveElement.focus === 'function') {
      lastActiveElement.focus();
    }
  }
}

async function submitQuestionnaire(event) {
  event.preventDefault();
  const salary = parseFloat(document.getElementById('inputSalaryNet').value) || 0;
  const picpay = parseFloat(document.getElementById('inputPicPay').value) || 0;
  const nubank = parseFloat(document.getElementById('inputNubank').value) || 0;
  const special = parseFloat(document.getElementById('inputSpecialEvent').value) || 0;
  const friendDebt = parseFloat(document.getElementById('inputFriendDebt').value) || 0;

  // Coleta completa dos custos fixos editados
  const fixedExpenses = [
    { name: "Academia", amount: parseFloat(document.getElementById('inputFixedAcademia')?.value) || 0, category: "Saúde" },
    { name: "Internet Residencial", amount: parseFloat(document.getElementById('inputFixedNetRes')?.value) || 0, category: "Conectividade" },
    { name: "Internet Móvel", amount: parseFloat(document.getElementById('inputFixedNetMov')?.value) || 0, category: "Conectividade" },
    { name: "Spotify", amount: parseFloat(document.getElementById('inputFixedSpotify')?.value) || 0, category: "Assinaturas" },
    { name: "Armazenamento Google", amount: parseFloat(document.getElementById('inputFixedGoogle')?.value) || 0, category: "Assinaturas" }
  ];

  // Coleta completa dos compromissos pontuais (Viagem E Amigo)
  const oneOffs = [];
  if (special > 0) {
    oneOffs.push({ name: "Viagem / Pontual", amount: special, month: "Outubro" });
  }
  if (friendDebt > 0) {
    oneOffs.push({ name: "Quitação amigo", amount: friendDebt, month: "Outubro" });
  }

  const payload = {
    salary_net: salary,
    fixed_expenses: fixedExpenses,
    card_schedules: {
      PicPay: { closing_day: 27, installments: { Outubro: picpay } },
      Nubank: { closing_day: 4, installments: { Outubro: nubank } }
    },
    one_off_commitments: oneOffs
  };

  const saveBtn = document.getElementById('saveQuestionnaireBtn');
  saveBtn.disabled = true;
  saveBtn.textContent = 'Atualizando...';

  try {
    const res = await fetch('/api/questionnaire', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    if (!res.ok) throw new Error('Erro ao salvar');

    toggleQuestionnaireModal(false);
    // Recarregar dados da interface de forma coordenada
    await loadTimeline();
    await loadKPIs();
    await loadConsensus();
  } catch (e) {
    alert('Erro ao atualizar os dados: ' + e.message);
  } finally {
    saveBtn.disabled = false;
    saveBtn.textContent = 'Salvar e Atualizar Projeções';
  }
}


// =============================================================================
// Estado de Navegação de Mês
// =============================================================================
let _viewYear  = (typeof APP_CONFIG !== 'undefined') ? APP_CONFIG.currentYear  : new Date().getFullYear();
let _viewMonth = (typeof APP_CONFIG !== 'undefined') ? APP_CONFIG.currentMonth : new Date().getMonth() + 1;
let _budgetMonthId = null;
let _monthClosed   = false;
let _categories    = [];

function navigateMonth(delta) {
  _viewMonth += delta;
  if (_viewMonth > 12) { _viewMonth = 1;  _viewYear++; }
  if (_viewMonth < 1)  { _viewMonth = 12; _viewYear--; }
  loadBudgetMonth();
}

async function loadBudgetMonth() {
  const label = monthLabel(_viewYear, _viewMonth);
  document.getElementById('currentMonthLabel').textContent = label;

  try {
    const res = await fetch(`/api/budget/${_viewYear}/${_viewMonth}`);
    if (!res.ok) throw new Error(res.status);
    const data = await res.json();

    _budgetMonthId = data.budget_month.id;
    _monthClosed   = data.budget_month.is_closed;

    // Badge de encerrado
    const badge = document.getElementById('closedBadge');
    if (badge) badge.style.display = _monthClosed ? 'inline-flex' : 'none';

    // KPIs
    const s = data.summary;
    setText('kpiIncome',  formatCurrency(s.total_income));
    setText('kpiFixed',   formatCurrency(s.total_expenses_fixed));
    setText('kpiDebts',   formatCurrency((s.total_expenses_debt||0) + (s.total_expenses_card||0)));
    const surplus = s.net_surplus;
    const surplusEl = document.getElementById('kpiSurplus');
    if (surplusEl) {
      surplusEl.textContent = (surplus >= 0 ? '+ ' : '') + formatCurrency(surplus);
      surplusEl.className = 'lh-kpi-value tabular-nums ' + (surplus >= 0 ? 'text-green' : 'text-red');
    }

    // Listas
    renderExpenses(data.expenses);
    renderIncome(data.income);
  } catch(e) {
    console.warn('loadBudgetMonth error:', e);
    renderExpenses([]);
    renderIncome([]);
  }
}

async function closeCurrentMonth() {
  if (!confirm(`Encerrar ${monthLabel(_viewYear, _viewMonth)}? Esta ação é irreversível.`)) return;
  await fetch(`/api/budget/${_viewYear}/${_viewMonth}/close`, { method: 'POST' });
  loadBudgetMonth();
}

function monthLabel(y, m) {
  const names = ['Janeiro','Fevereiro','Março','Abril','Maio','Junho',
                 'Julho','Agosto','Setembro','Outubro','Novembro','Dezembro'];
  return `${names[m-1]}/${y}`;
}

function setText(id, val) {
  const el = document.getElementById(id);
  if (el) el.textContent = val;
}

// =============================================================================
// Categorias de Despesa
// =============================================================================
async function loadCategories() {
  try {
    const res = await fetch('/api/expenses/categories');
    if (!res.ok) return;
    _categories = await res.json();
    // Preenche select do modal de despesa
    const sel = document.getElementById('editExpenseCategory');
    if (!sel) return;
    sel.innerHTML = '<option value="">— sem categoria —</option>';
    _categories.forEach(c => {
      const opt = document.createElement('option');
      opt.value = c.id;
      opt.textContent = `${c.icon || ''} ${c.name}`;
      sel.appendChild(opt);
    });
  } catch(e) { console.warn('loadCategories:', e); }
}

// =============================================================================
// Renderização e CRUD — Despesas
// =============================================================================
function renderExpenses(list) {
  const container = document.getElementById('expenseListContainer');
  if (!container) return;

  if (!list || list.length === 0) {
    container.innerHTML = `<div style="text-align:center; color:var(--lh-text-muted); font-size:0.82rem; padding:20px;">
      Nenhuma despesa registrada para este mês.</div>`;
    setText('expensesTotalDisplay', formatCurrency(0));
    return;
  }

  const typeFilter = document.getElementById('expenseTypeFilter')?.value || '';
  const filtered = typeFilter ? list.filter(e => e.expense_type === typeFilter) : list;
  const total = list.reduce((s, e) => s + parseFloat(e.amount), 0);
  setText('expensesTotalDisplay', formatCurrency(total));

  container.innerHTML = filtered.map(e => `
    <div class="lh-editable-row expense-row" data-id="${e.id}">
      <div>
        <div class="lh-row-label">${e.description}</div>
        <div class="lh-row-category">${e.category_name || e.expense_type}${e.installment_current ? ` · ${e.installment_current}/${e.installment_total}x` : ''}</div>
      </div>
      <div class="lh-row-amount expense">${formatCurrency(e.amount)}</div>
      <div style="font-size:0.75rem; color:var(--lh-text-muted);">${expenseTypeLabel(e.expense_type)}</div>
      <button class="lh-row-btn" onclick="editExpense(${JSON.stringify(e).replace(/"/g,'&quot;')})" title="Editar" ${_monthClosed ? 'disabled' : ''}>✏️</button>
      <button class="lh-row-btn del" onclick="deleteExpense(${e.id})" title="Remover" ${_monthClosed ? 'disabled' : ''}>✕</button>
    </div>`).join('');
}

function expenseTypeLabel(t) {
  return {fixed:'Fixo', variable:'Variável', debt:'Dívida', card:'Cartão'}[t] || t;
}

function loadExpenses() { loadBudgetMonth(); }

function openAddExpenseModal() {
  if (_monthClosed) { alert('Este mês está encerrado.'); return; }
  document.getElementById('expenseModalTitle').textContent = 'Adicionar Despesa';
  document.getElementById('editExpenseId').value = '';
  ['editExpenseName','editExpenseAmount','editExpenseDue',
   'editInstallmentCurrent','editInstallmentTotal'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.value = '';
  });
  document.getElementById('editExpenseType').value = 'fixed';
  document.getElementById('editExpenseCategory').value = '';
  const modal = document.getElementById('modalExpense');
  if (modal) { modal.style.display = 'flex'; }
}

function editExpense(entry) {
  if (_monthClosed) { alert('Este mês está encerrado.'); return; }
  document.getElementById('expenseModalTitle').textContent = 'Editar Despesa';
  document.getElementById('editExpenseId').value      = entry.id;
  document.getElementById('editExpenseName').value    = entry.description;
  document.getElementById('editExpenseAmount').value  = entry.amount;
  document.getElementById('editExpenseType').value    = entry.expense_type;
  document.getElementById('editExpenseCategory').value = entry.category_id || '';
  document.getElementById('editExpenseDue').value     = entry.due_date || '';
  document.getElementById('editInstallmentCurrent').value = entry.installment_current || '';
  document.getElementById('editInstallmentTotal').value   = entry.installment_total || '';
  const modal = document.getElementById('modalExpense');
  if (modal) modal.style.display = 'flex';
}

function closeExpenseModal() {
  const modal = document.getElementById('modalExpense');
  if (modal) modal.style.display = 'none';
}

async function saveExpense() {
  const name   = document.getElementById('editExpenseName').value.trim();
  const amount = parseFloat(document.getElementById('editExpenseAmount').value);
  if (!name || !amount || amount <= 0) { alert('Preencha descrição e valor.'); return; }

  const payload = {
    id:              parseInt(document.getElementById('editExpenseId').value) || null,
    budget_month_id: _budgetMonthId,
    description:     name,
    amount:          amount,
    expense_type:    document.getElementById('editExpenseType').value,
    category_id:     parseInt(document.getElementById('editExpenseCategory').value) || null,
    due_date:        document.getElementById('editExpenseDue').value || null,
    installment_current: parseInt(document.getElementById('editInstallmentCurrent').value) || null,
    installment_total:   parseInt(document.getElementById('editInstallmentTotal').value) || null,
  };

  try {
    const res = await fetch('/api/expenses', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify(payload)
    });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || res.status);
    }
    closeExpenseModal();
    loadBudgetMonth();
  } catch(e) { alert('Erro ao salvar: ' + e.message); }
}

async function deleteExpense(id) {
  if (!confirm('Remover este lançamento?')) return;
  try {
    const res = await fetch(`/api/expenses/${id}`, { method: 'DELETE' });
    if (!res.ok) { const e = await res.json(); throw new Error(e.detail); }
    loadBudgetMonth();
  } catch(e) { alert('Erro: ' + e.message); }
}

// =============================================================================
// Renderização e CRUD — Receitas
// =============================================================================
function renderIncome(list) {
  const container = document.getElementById('incomeListContainer');
  if (!container) return;

  if (!list || list.length === 0) {
    container.innerHTML = `<div style="text-align:center; color:var(--lh-text-muted); font-size:0.82rem; padding:20px;">
      Nenhuma receita registrada para este mês.</div>`;
    setText('incomeTotalDisplay', formatCurrency(0));
    return;
  }

  const total = list.reduce((s, e) => s + parseFloat(e.amount), 0);
  setText('incomeTotalDisplay', formatCurrency(total));

  container.innerHTML = list.map(e => `
    <div class="lh-editable-row" data-id="${e.id}">
      <div>
        <div class="lh-row-label">${e.description}</div>
        <div class="lh-row-category">${incomeTypeLabel(e.income_type)}${e.is_received ? ' · ✓ Recebido' : ''}</div>
      </div>
      <div class="lh-row-amount income">${formatCurrency(e.amount)}</div>
      <button class="lh-row-btn" onclick="editIncome(${JSON.stringify(e).replace(/"/g,'&quot;')})" title="Editar" ${_monthClosed ? 'disabled' : ''}>✏️</button>
      <button class="lh-row-btn del" onclick="deleteIncome(${e.id})" title="Remover" ${_monthClosed ? 'disabled' : ''}>✕</button>
    </div>`).join('');
}

function incomeTypeLabel(t) {
  return {salary:'Salário', extra:'Extra/Freela', benefit:'Benefício', investment_return:'Investimento', other:'Outro'}[t] || t;
}

function openAddIncomeModal() {
  if (_monthClosed) { alert('Este mês está encerrado.'); return; }
  document.getElementById('incomeModalTitle').textContent = 'Adicionar Receita';
  document.getElementById('editIncomeId').value = '';
  ['editIncomeName','editIncomeAmount'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.value = '';
  });
  document.getElementById('editIncomeType').value = 'salary';
  const modal = document.getElementById('modalIncome');
  if (modal) modal.style.display = 'flex';
}

function editIncome(entry) {
  if (_monthClosed) { alert('Este mês está encerrado.'); return; }
  document.getElementById('incomeModalTitle').textContent = 'Editar Receita';
  document.getElementById('editIncomeId').value    = entry.id;
  document.getElementById('editIncomeName').value  = entry.description;
  document.getElementById('editIncomeAmount').value = entry.amount;
  document.getElementById('editIncomeType').value  = entry.income_type;
  const modal = document.getElementById('modalIncome');
  if (modal) modal.style.display = 'flex';
}

function closeIncomeModal() {
  const modal = document.getElementById('modalIncome');
  if (modal) modal.style.display = 'none';
}

async function saveIncome() {
  const name   = document.getElementById('editIncomeName').value.trim();
  const amount = parseFloat(document.getElementById('editIncomeAmount').value);
  if (!name || !amount || amount <= 0) { alert('Preencha descrição e valor.'); return; }

  const payload = {
    id:              parseInt(document.getElementById('editIncomeId').value) || null,
    budget_month_id: _budgetMonthId,
    description:     name,
    amount:          amount,
    income_type:     document.getElementById('editIncomeType').value,
  };

  try {
    const res = await fetch('/api/income', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify(payload)
    });
    if (!res.ok) { const e = await res.json(); throw new Error(e.detail || res.status); }
    closeIncomeModal();
    loadBudgetMonth();
  } catch(e) { alert('Erro ao salvar: ' + e.message); }
}

async function deleteIncome(id) {
  if (!confirm('Remover esta receita?')) return;
  try {
    const res = await fetch(`/api/income/${id}`, { method: 'DELETE' });
    if (!res.ok) { const e = await res.json(); throw new Error(e.detail); }
    loadBudgetMonth();
  } catch(e) { alert('Erro: ' + e.message); }
}

// =============================================================================
// Objetivo Financeiro
// =============================================================================
async function loadGoal() {
  try {
    const res = await fetch('/api/goals');
    if (!res.ok) return;
    const goal = await res.json();
    renderGoal(goal);
  } catch(e) { console.warn('loadGoal:', e); }
}

function renderGoal(goal) {
  const panel = document.getElementById('goalPanel');
  const subtitle = document.getElementById('goalSubtitle');
  if (!panel) return;

  if (!goal || !goal.id) {
    panel.innerHTML = `<div style="text-align:center; color:var(--lh-text-muted); font-size:0.82rem; padding:20px;">
      Nenhum objetivo definido ainda.<br>
      <button class="lh-add-row-btn" onclick="openGoalModal()" style="margin-top:8px; width:auto; padding:6px 16px; border-radius:6px;">
        + Definir objetivo
      </button></div>`;
    return;
  }

  if (subtitle) subtitle.textContent = goalTypeLabel(goal.goal_type);

  const pct = goal.target_amount
    ? Math.min(100, Math.round((goal.current_amount / goal.target_amount) * 100))
    : 0;
  const remaining = goal.target_amount ? (goal.target_amount - goal.current_amount) : null;

  panel.innerHTML = `
    <div style="padding: 4px 0;">
      <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;">
        <strong style="font-size:0.9rem;">${goal.title}</strong>
        <span style="font-size:0.78rem; font-weight:700; color:var(--lh-primary);">${pct}%</span>
      </div>
      <div class="lh-goal-bar-track">
        <div class="lh-goal-bar-fill" style="width:${pct}%;"></div>
      </div>
      <div style="display:grid; grid-template-columns:1fr 1fr 1fr; gap:6px; margin-top:10px; font-size:0.78rem; color:var(--lh-text-muted);">
        <div>
          <div style="font-weight:700; color:var(--lh-text);">${formatCurrency(goal.current_amount)}</div>
          <div>Acumulado</div>
        </div>
        ${goal.target_amount ? `<div>
          <div style="font-weight:700; color:var(--lh-text);">${formatCurrency(remaining)}</div>
          <div>Restam</div>
        </div>
        <div>
          <div style="font-weight:700; color:var(--lh-text);">${formatCurrency(goal.target_amount)}</div>
          <div>Meta</div>
        </div>` : '<div></div><div></div>'}
      </div>
      ${goal.target_date ? `<div style="font-size:0.75rem; color:var(--lh-text-muted); margin-top:8px;">📅 Prazo: ${goal.target_date}</div>` : ''}
    </div>`;
}

function goalTypeLabel(t) {
  return {emergencia:'Reserva de Emergência', imovel:'Compra de Imóvel', aposentadoria:'Aposentadoria',
          viagem:'Viagem / Experiência', divida:'Quitação de Dívidas', independencia:'Independência Financeira', outro:'Objetivo Personalizado'}[t] || t;
}

function openGoalModal(goal) {
  document.getElementById('editGoalId').value      = goal?.id || '';
  document.getElementById('editGoalType').value    = goal?.goal_type || 'emergencia';
  document.getElementById('editGoalTitle').value   = goal?.title || '';
  document.getElementById('editGoalTarget').value  = goal?.target_amount || '';
  document.getElementById('editGoalDate').value    = goal?.target_date ? goal.target_date.slice(0,7) : '';
  document.getElementById('editGoalCurrent').value = goal?.current_amount || 0;
  const modal = document.getElementById('modalGoal');
  if (modal) modal.style.display = 'flex';
}

function closeGoalModal() {
  const modal = document.getElementById('modalGoal');
  if (modal) modal.style.display = 'none';
}

async function saveGoal() {
  const title = document.getElementById('editGoalTitle').value.trim();
  if (!title) { alert('Preencha o nome do objetivo.'); return; }

  const dateVal = document.getElementById('editGoalDate').value;
  const payload = {
    id:           parseInt(document.getElementById('editGoalId').value) || null,
    goal_type:    document.getElementById('editGoalType').value,
    title:        title,
    target_amount: parseFloat(document.getElementById('editGoalTarget').value) || null,
    target_date:   dateVal ? dateVal + '-01' : null,
    current_amount: parseFloat(document.getElementById('editGoalCurrent').value) || 0,
    priority:      1,
  };

  try {
    const res = await fetch('/api/goals', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify(payload)
    });
    if (!res.ok) { const e = await res.json(); throw new Error(e.detail || res.status); }
    closeGoalModal();
    loadGoal();
  } catch(e) { alert('Erro ao salvar objetivo: ' + e.message); }
}

// =============================================================================
// Portfólio de Investimentos
// =============================================================================
async function loadPortfolio() {
  try {
    const res = await fetch('/api/portfolio');
    if (!res.ok) return;
    const portfolio = await res.json();
    renderPortfolio(portfolio);
  } catch(e) { console.warn('loadPortfolio:', e); }
}

function renderPortfolio(p) {
  const panel = document.getElementById('portfolioPanel');
  const date  = document.getElementById('portfolioDate');
  if (!panel) return;

  if (!p || !p.id) {
    panel.innerHTML = `<div style="text-align:center; color:var(--lh-text-muted); font-size:0.82rem; padding:20px;">
      Clique em <strong>"Atualizar IA"</strong> para gerar sua carteira personalizada.</div>`;
    return;
  }

  if (date && p.generated_at) {
    date.textContent = 'Gerado em ' + new Date(p.generated_at).toLocaleDateString('pt-BR');
  }

  const allocs = [
    { label: 'Renda Fixa', pct: p.pct_renda_fixa, color: '#1E56A0' },
    { label: 'Tesouro',    pct: p.pct_tesouro,    color: '#2EA884' },
    { label: 'FIIs',       pct: p.pct_fiis,        color: '#7C5CBF' },
    { label: 'Ações',      pct: p.pct_acoes,       color: '#E59830' },
    { label: 'Liq.',       pct: p.pct_reserva_liquida, color: '#5A6A80' },
    { label: 'Cripto',     pct: p.pct_cripto,      color: '#EF4444' },
  ].filter(a => a.pct > 0);

  panel.innerHTML = `
    <div class="lh-portfolio-grid">
      ${allocs.map(a => `
        <div class="lh-portfolio-item">
          <div class="lh-portfolio-pct" style="color:${a.color};">${a.pct}%</div>
          <div class="lh-portfolio-label">${a.label}</div>
        </div>`).join('')}
    </div>
    <div style="margin-top:12px; padding:10px 12px; background:var(--lh-surface-2, rgba(100,116,139,0.06)); border-radius:6px; font-size:0.8rem; color:var(--lh-text-muted);">
      <strong>Aporte mensal sugerido:</strong>
      <span style="font-weight:700; color:var(--lh-primary);">${formatCurrency(p.monthly_investment_target || 0)}</span>
      ${p.months_to_goal ? ` · ${p.months_to_goal} meses para o objetivo` : ''}
    </div>
    ${p.rationale ? `<details style="margin-top:10px; font-size:0.78rem; color:var(--lh-text-muted);">
      <summary style="cursor:pointer; font-weight:600; color:var(--lh-text);">Justificativa da IA</summary>
      <p style="margin-top:6px; line-height:1.5;">${p.rationale}</p>
    </details>` : ''}`;
}

async function generatePortfolio() {
  const btn = document.getElementById('btnGeneratePortfolio');
  if (btn) { btn.disabled = true; btn.textContent = 'Gerando...'; }
  try {
    const res = await fetch('/api/portfolio/generate', { method: 'POST' });
    if (!res.ok) { const e = await res.json(); throw new Error(e.detail || res.status); }
    const data = await res.json();
    if (data.portfolio) renderPortfolio(data.portfolio);
    else await loadPortfolio();
  } catch(e) { alert('Erro ao gerar carteira: ' + e.message); }
  finally {
    if (btn) { btn.disabled = false; btn.textContent = 'Atualizar IA'; }
  }
}

// =============================================================================
// Timeline Real (substitui dados do seed)
// =============================================================================
async function loadTimeline() {
  try {
    const res = await fetch('/api/forecast/12');
    if (!res.ok) throw new Error(res.status);
    const data = await res.json();
    if (data && data.length > 0 && data[0].label !== undefined) {
      // Novo formato: dados reais do banco
      initTimelineChartReal(data);
    } else {
      // Fallback: formato antigo do seed
      initTimelineChart(data);
    }
  } catch(e) {
    console.warn('loadTimeline fallback to /api/timeline:', e);
    try {
      const res2 = await fetch('/api/timeline');
      if (res2.ok) initTimelineChart(await res2.json());
    } catch(e2) { console.warn('timeline fallback failed:', e2); }
  }
}

function initTimelineChartReal(data) {
  const colors = getThemeColors();
  const categories = data.map(d => d.label || monthLabel(d.year, d.month));
  const income   = data.map(d => d.total_income || 0);
  const fixed    = data.map(d => d.total_expenses_fixed || 0);
  const variable = data.map(d => d.total_expenses_variable || 0);
  const debts    = data.map(d => (d.total_expenses_debt || 0) + (d.total_expenses_card || 0));
  const surplus  = data.map(d => d.net_surplus || 0);

  const options = {
    chart: { type: 'bar', height: 330, stacked: true, toolbar: { show: false }, fontFamily: 'Plus Jakarta Sans, sans-serif' },
    colors: [colors.cobalt, '#7C5CBF', colors.amber, colors.green],
    series: [
      { name: 'Fixos',    data: fixed },
      { name: 'Variáveis',data: variable },
      { name: 'Dívidas',  data: debts },
      { name: 'Sobra',    data: surplus },
    ],
    xaxis: { categories },
    yaxis: { labels: { formatter: v => formatCurrency(v).replace('R$\u00a0','') } },
    legend: { position: 'top' },
    tooltip: { y: { formatter: v => formatCurrency(v) } },
    plotOptions: { bar: { borderRadius: 4 } },
    dataLabels: { enabled: false },
    grid: { borderColor: colors.border },
  };

  const el = document.getElementById('chartCashFlowTimeline');
  if (!el) return;
  if (timelineChart) { timelineChart.destroy(); timelineChart = null; }
  timelineChart = new ApexCharts(el, options);
  timelineChart.render();
}

// =============================================================================
// Inicialização no Carregamento do DOM
// =============================================================================
document.addEventListener('DOMContentLoaded', () => {
  initTheme();
  initMethodologyDonut();
  loadCategories();
  loadBudgetMonth();   // carrega KPIs + despesas + receitas do mês atual
  loadTimeline();      // gráfico de fluxo de caixa
  loadKPIs();          // KPIs legados (consenso, etc.)
  loadConsensus();     // hub de decisão IA
  loadGoal();          // objetivo principal
  loadPortfolio();     // carteira ativa
});
