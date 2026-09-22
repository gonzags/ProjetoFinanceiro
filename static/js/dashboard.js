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

// -----------------------------------------------------------------------------
// Inicialização no Carregamento do DOM
// -----------------------------------------------------------------------------
document.addEventListener('DOMContentLoaded', () => {
  initTheme();
  initMethodologyDonut();
  loadTimeline();
  loadKPIs();
  loadConsensus();
});

