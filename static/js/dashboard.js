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
        <div class="lh-milestone-month">${m0.month} ${m0.year || new Date().getFullYear()}</div>
        <div class="lh-milestone-details">${m0.status_label || 'Zona Crítica'} (Sobra ${formatCurrency(m0.net_surplus)})</div>
      </div>
      <div class="lh-milestone-item">
        <div class="lh-milestone-month">${m1.month} ${m1.year || new Date().getFullYear()}</div>
        <div class="lh-milestone-details">Alívio (+${formatCurrency(m1.net_surplus)}) • Reserva</div>
      </div>
      <div class="lh-milestone-item">
        <div class="lh-milestone-month">${m2.month} ${m2.year || new Date().getFullYear()}</div>
        <div class="lh-milestone-details">Folga Sólida (+${formatCurrency(m2.net_surplus)})</div>
      </div>
      <div class="lh-milestone-item">
        <div class="lh-milestone-month">${m6.month} ${(m6.year || new Date().getFullYear())+'+'}</div>
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
    if (debtsSub) {
      // Usar cartões carregados via loadCardBadges() se disponíveis
      if (window._userCards && window._userCards.length > 0) {
        debtsSub.textContent = window._userCards
          .map(c => `${c.name} fecha dia ${c.closing_day}`)
          .join(' • ');
      } else {
        debtsSub.textContent = 'Compromissos mensais';
      }
    }

    const surplusDiag = document.getElementById('kpiSurplusDiag');
    if (surplusDiag) surplusDiag.textContent = s.net_surplus > 500 ? 'Folga sólida consolidada' : 'Zona crítica controlada • Saldo positivo';

    updateHorizonGauge(currentTimeline, currentKPIs);
  } catch (e) {
    console.error('Erro nos KPIs:', e);
  }
}

let aiProgressInterval = null;
let _globalOverlayInterval = null;

function _startGlobalOverlay() {
  const ov = document.getElementById('aiGlobalOverlay');
  const bar = document.getElementById('aiGlobalProgressBar');
  const pct = document.getElementById('aiGlobalPct');
  const stage = document.getElementById('aiGlobalStage');
  if (!ov) return;

  ov.classList.add('visible');

  const stages = [
    { at:  5, text: 'Estruturando dados de receitas e custos fixos...' },
    { at: 30, text: 'Consultando comitê de inteligência artificial...' },
    { at: 60, text: 'Auditando riscos e metas orçamentárias...' },
    { at: 85, text: 'Consolidando parecer e alocação recomendada...' },
  ];

  let p = 5;
  if (bar) bar.style.width = `${p}%`;
  if (pct) pct.textContent = `${p}%`;
  if (stage) stage.textContent = stages[0].text;

  if (_globalOverlayInterval) clearInterval(_globalOverlayInterval);
  _globalOverlayInterval = setInterval(() => {
    if (p < 92) {
      p += Math.floor(Math.random() * 5) + 3;
      if (p > 92) p = 92;
      if (bar) bar.style.width = `${p}%`;
      if (pct) pct.textContent = `${p}%`;
      const matched = stages.slice().reverse().find(s => p >= s.at);
      if (matched && stage) stage.textContent = matched.text;
    }
  }, 500);
}

function _stopGlobalOverlay(success) {
  if (_globalOverlayInterval) { clearInterval(_globalOverlayInterval); _globalOverlayInterval = null; }
  const ov = document.getElementById('aiGlobalOverlay');
  const bar = document.getElementById('aiGlobalProgressBar');
  const pct = document.getElementById('aiGlobalPct');
  const stage = document.getElementById('aiGlobalStage');
  if (!ov) return;
  if (success) {
    if (bar) bar.style.width = '100%';
    if (pct) pct.textContent = '100%';
    if (stage) stage.textContent = '✓ Análise concluída!';
    setTimeout(() => ov.classList.remove('visible'), 600);
  } else {
    ov.classList.remove('visible');
  }
}

function startAiLoadingIndicator(customMessage) {
  const banner = document.getElementById('aiLoadingBanner');
  const stageEl = document.getElementById('aiLoadingStage');
  const pctEl = document.getElementById('aiLoadingPct');
  const barEl = document.getElementById('aiLoadingBar');
  const timestamp = document.getElementById('analysisTimestamp');

  if (!banner) return;
  banner.style.display = 'block';

  if (timestamp) timestamp.textContent = 'Processando comitê de inteligência artificial...';

  let pct = 8;
  const stages = [
    { at: 10, text: customMessage || 'Estruturando dados de receitas e custos fixos...' },
    { at: 35, text: 'Consultando comitê de inteligência artificial...' },
    { at: 65, text: 'Auditando riscos e analisando metas orçamentárias...' },
    { at: 85, text: 'Consolidando parecer e alocação recomendada...' }
  ];

  if (stageEl) stageEl.textContent = stages[0].text;
  if (pctEl) pctEl.textContent = `${pct}%`;
  if (barEl) barEl.style.width = `${pct}%`;

  if (aiProgressInterval) clearInterval(aiProgressInterval);

  aiProgressInterval = setInterval(() => {
    if (pct < 92) {
      pct += Math.floor(Math.random() * 5) + 3;
      if (pct > 92) pct = 92;
      if (pctEl) pctEl.textContent = `${pct}%`;
      if (barEl) barEl.style.width = `${pct}%`;

      const matchedStage = stages.slice().reverse().find(s => pct >= s.at);
      if (matchedStage && stageEl) {
        stageEl.textContent = matchedStage.text;
      }
    }
  }, 450);
}

function stopAiLoadingIndicator(success = true) {
  if (aiProgressInterval) {
    clearInterval(aiProgressInterval);
    aiProgressInterval = null;
  }
  const banner = document.getElementById('aiLoadingBanner');
  const stageEl = document.getElementById('aiLoadingStage');
  const pctEl = document.getElementById('aiLoadingPct');
  const barEl = document.getElementById('aiLoadingBar');
  const timestamp = document.getElementById('analysisTimestamp');

  if (!banner) return;

  if (success) {
    if (pctEl) pctEl.textContent = '100%';
    if (barEl) barEl.style.width = '100%';
    if (stageEl) stageEl.textContent = '✓ Análise concluída com sucesso!';
    if (timestamp) timestamp.textContent = 'Análise do comitê de IA consolidada.';
    setTimeout(() => {
      banner.style.display = 'none';
    }, 500);
  } else {
    banner.style.display = 'none';
  }
}

async function loadConsensus() {
  _startGlobalOverlay();
  startAiLoadingIndicator('Carregando parecer do comitê de inteligência artificial...');
  try {
    const res = await fetch('/api/consensus?month=Outubro');
    if (!res.ok) throw new Error('Falha ao carregar consenso');
    const data = await res.json();
    _stopGlobalOverlay(true);
    stopAiLoadingIndicator(true);
    renderConsensus(data);
  } catch (e) {
    console.error('Erro no consenso:', e);
    _stopGlobalOverlay(false);
    stopAiLoadingIndicator(false);
  }
}

async function loadCardBadges() {
  try {
    const res = await fetch('/api/profile/cards');
    if (!res.ok) return;
    const cards = await res.json();
    window._userCards = cards;

    const bar = document.getElementById('cardBadgesBar');
    if (!bar) return;

    if (!cards || cards.length === 0) {
      bar.innerHTML = `
        <span style="font-size:0.78rem; color:var(--lh-text-muted);">Nenhum cartão cadastrado.</span>
        <button onclick="reseedCards()" style="font-size:0.75rem; padding:3px 10px; border-radius:4px;
          background:rgba(30,86,160,.15); border:1px solid rgba(30,86,160,.3);
          color:var(--lh-primary); cursor:pointer;">
          🔄 Importar do cadastro
        </button>`;
      return;
    }

    bar.innerHTML = cards.map(c => `
      <span style="
        display:inline-flex; align-items:center; gap:5px;
        padding:5px 10px; background:var(--lh-surface-2, rgba(100,116,139,0.08));
        border:1px solid var(--lh-border); border-radius:20px;
        font-size:0.78rem; color:var(--lh-text);">
        💳 <strong>${c.name}</strong>: fecha dia ${c.closing_day}, vence dia ${c.due_day}
        ${c.current_balance > 0 ? `<span style="color:#ef4444;margin-left:4px;">R$ ${c.current_balance.toLocaleString('pt-BR', {minimumFractionDigits:2})}</span>` : ''}
      </span>
    `).join('');
  } catch (e) {
    console.error('Erro ao carregar cartões:', e);
  }
}

async function reseedCards() {
  try {
    const res = await fetch('/api/profile/cards/reseed', { method: 'POST' });
    const data = await res.json();
    if (data.reseeded > 0) {
      await loadCardBadges();
    } else {
      alert('Nenhum cartão encontrado no seu cadastro. Acesse Editar Perfil para adicionar cartões.');
    }
  } catch(e) { console.error('Erro ao importar cartões:', e); }
}

// =============================================================================
// Insights Automáticos do Mês
// =============================================================================
function renderInsights(s) {
  const panel = document.getElementById('insightsPanel');
  const list  = document.getElementById('insightsList');
  if (!panel || !list) return;

  const income  = s.total_income || 0;
  const fixed   = s.total_expenses_fixed || 0;
  const varExp  = s.total_expenses_variable || 0;
  const debts   = (s.total_expenses_debt || 0) + (s.total_expenses_card || 0);
  const surplus = s.net_surplus || 0;
  const totalOut = fixed + varExp + debts;

  const insights = [];

  const chip = (icon, text, color) =>
    `<div style="display:inline-flex;align-items:center;gap:6px;padding:6px 12px;
      border-radius:20px;font-size:0.8rem;background:${color}15;border:1px solid ${color}40;color:var(--lh-text);">
      <span>${icon}</span><span>${text}</span>
    </div>`;

  // Sem renda registrada
  if (income === 0) {
    insights.push(chip('⚠️', 'Nenhuma receita lançada — registre sua renda para ativar todos os indicadores', '#f59e0b'));
  }

  // Despesas variáveis altas (>30% da renda)
  if (income > 0 && varExp > 0) {
    const varPct = Math.round((varExp / income) * 100);
    if (varPct > 30) {
      insights.push(chip('🔴', `Variáveis em ${varPct}% da renda (${formatCurrency(varExp)}) — acima do ideal de 30%`, '#ef4444'));
    } else if (varPct > 15) {
      insights.push(chip('🟡', `Variáveis em ${varPct}% da renda (${formatCurrency(varExp)}) — monitorar`, '#f59e0b'));
    } else if (varPct > 0) {
      insights.push(chip('🟢', `Variáveis controladas: ${varPct}% da renda (${formatCurrency(varExp)})`, '#22c55e'));
    }
  }

  // Sobra < 10% — risco
  if (income > 0 && surplus >= 0 && surplus < income * 0.1) {
    insights.push(chip('⚠️', `Sobra de apenas ${Math.round((surplus/income)*100)}% da renda — pouco espaço para imprevistos`, '#f59e0b'));
  }

  // Despesas fixas > 70% da renda
  if (income > 0 && fixed > income * 0.7) {
    const pct = Math.round((fixed / income) * 100);
    insights.push(chip('🔴', `Custos fixos em ${pct}% da renda — compromete liberdade financeira`, '#ef4444'));
  }

  // Dívidas > 30% da renda
  if (income > 0 && debts > income * 0.3) {
    const pct = Math.round((debts / income) * 100);
    insights.push(chip('🔴', `Dívidas/cartões em ${pct}% da renda (${formatCurrency(debts)}) — avaliar renegociação`, '#ef4444'));
  }

  // Déficit
  if (surplus < 0) {
    insights.push(chip('🚨', `Deficit de ${formatCurrency(Math.abs(surplus))} este mês — despesas superam receitas`, '#ef4444'));
  }

  // Tudo bem
  if (income > 0 && surplus > income * 0.2 && varExp <= income * 0.3 && fixed <= income * 0.6) {
    insights.push(chip('✅', `Mês equilibrado: sobra ${Math.round((surplus/income)*100)}% da renda`, '#22c55e'));
  }

  if (insights.length === 0) {
    panel.style.display = 'none';
    return;
  }

  list.innerHTML = insights.join('');
  panel.style.display = 'block';
}

function renderConsensus(data) {
  // Alocações
  const aiAllocNec = document.getElementById('aiAllocNec');
  const aiAllocDes = document.getElementById('aiAllocDes');
  const aiAllocFut = document.getElementById('aiAllocFut');
  const aiReasoningQuote = document.getElementById('aiReasoningQuote');
  const aiRiskTagsContainer = document.getElementById('aiRiskTagsContainer');
  const recalcBtn = document.getElementById('recalculateBtn');
  const timestampFooter = document.getElementById('analysisTimestampFooter');

  if (data.allocation) {
    if (aiAllocNec) aiAllocNec.textContent = `${(data.allocation.necessidades || 0).toFixed(1)}%`;
    if (aiAllocDes) aiAllocDes.textContent = `${(data.allocation.desejos || 0).toFixed(1)}%`;
    if (aiAllocFut) aiAllocFut.textContent = `${(data.allocation.futuro || 0).toFixed(1)}%`;
  }

  if (aiReasoningQuote && data.reasoning_summary) {
    aiReasoningQuote.textContent = data.reasoning_summary;
  }

  if (aiRiskTagsContainer) {
    const flags = data.risk_flags || [];
    if (flags.length > 0) {
      aiRiskTagsContainer.innerHTML = flags.map(f => `<span class="lh-risk-tag">⚠️ ${f}</span>`).join('');
    } else {
      aiRiskTagsContainer.innerHTML = '<span style="font-size:0.82rem; color:#22c55e;">✅ Nenhum alerta crítico identificado</span>';
    }
  }

  // Timestamp
  if (timestampFooter) {
    const now = new Date();
    timestampFooter.textContent = `Última análise: ${now.toLocaleDateString('pt-BR')} às ${now.toLocaleTimeString('pt-BR', {hour:'2-digit', minute:'2-digit'})}`;
  }
}

// -----------------------------------------------------------------------------
// Recalcular Consenso (com Rate Limiting de 3/hora)
// -----------------------------------------------------------------------------
async function recalculateConsensus() {
  const btn = document.getElementById('recalculateBtn');
  const btnText = document.getElementById('recalculateBtnText');
  const rateNotice = document.getElementById('rateLimitNotice');

  if (btn) btn.disabled = true;
  if (btnText) btnText.textContent = 'Deliberando...';
  if (rateNotice) rateNotice.style.display = 'none';

  startAiLoadingIndicator('Acionando nova rodada de deliberação com IA...');

  try {
    const res = await fetch('/api/consensus/recalculate?month=Outubro', { method: 'POST' });
    if (res.status === 429) {
      stopAiLoadingIndicator(false);
      if (rateNotice) {
        rateNotice.style.display = 'block';
        rateNotice.textContent = 'Limite atingido: máximo de 3 recálculos por hora por IP.';
      }
      return;
    }
    if (!res.ok) throw new Error('Erro ao recalcular');
    const data = await res.json();
    stopAiLoadingIndicator(true);
    renderConsensus(data);
  } catch (e) {
    console.error('Erro no recálculo:', e);
    stopAiLoadingIndicator(false);
  } finally {
    if (btn) btn.disabled = false;
    if (btnText) btnText.textContent = '↻ Atualizar análise';
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


// =============================================================================
// Modal de Perfil do Usuário
// =============================================================================

function openProfileModal() {
  const modal = document.getElementById('profileModal');
  if (!modal) return;
  modal.style.display = 'flex';
  document.body.style.overflow = 'hidden';
  loadProfileData();
}

function closeProfileModal() {
  const modal = document.getElementById('profileModal');
  if (!modal) return;
  modal.style.display = 'none';
  document.body.style.overflow = '';
}

// Fechar ao clicar no backdrop
document.addEventListener('DOMContentLoaded', () => {
  const modal = document.getElementById('profileModal');
  if (modal) {
    modal.addEventListener('click', e => { if (e.target === modal) closeProfileModal(); });
  }
});

function switchProfileTab(tab) {
  document.querySelectorAll('.profile-tab-content').forEach(el => el.style.display = 'none');
  document.querySelectorAll('.profile-tab').forEach(btn => {
    btn.classList.remove('active');
    btn.style.borderBottomColor = 'transparent';
    btn.style.color = 'var(--lh-text-muted)';
  });
  const content = document.getElementById('profileTab-' + tab);
  if (content) content.style.display = 'block';
  const btn = document.getElementById('tab-' + tab);
  if (btn) {
    btn.classList.add('active');
    btn.style.borderBottomColor = '#1E56A0';
    btn.style.color = 'var(--lh-text)';
  }
}

async function loadProfileData() {
  try {
    const res = await fetch('/api/profile/me');
    if (!res.ok) return;
    const p = await res.json();

    // Hero
    const name = p.name || 'Usuário';
    const initials = name.split(' ').slice(0, 2).map(w => w[0]).join('').toUpperCase();
    document.getElementById('profileHeroName').textContent = name;
    document.getElementById('profileHeroEmail').textContent = p.email || '—';
    document.getElementById('profileAvatarInitials').textContent = initials;
    document.getElementById('headerAvatarInitials').textContent = initials;

    if (p.avatar_url) {
      _setAvatarImage(p.avatar_url);
    }

    const badge = document.getElementById('profileUserTypeBadge');
    if (badge) badge.textContent = (p.user_type || 'pf').toUpperCase();

    const since = document.getElementById('profileMemberSince');
    if (since && p.member_since) since.textContent = 'Membro desde ' + p.member_since;

    // Tab Dados Pessoais
    const maritalMap = { solteiro: 'Solteiro(a)', casado: 'Casado(a)', uniao_estavel: 'União Estável', divorciado: 'Divorciado(a)', viuvo: 'Viúvo(a)' };
    _setProfileField('pf-name', p.name);
    _setProfileField('pf-age', p.age ? p.age + ' anos' : null);
    _setProfileField('pf-occupation', p.occupation);
    _setProfileField('pf-marital', maritalMap[p.marital_status] || p.marital_status);
    _setProfileField('pf-dependents', p.dependents != null ? (p.dependents === 0 ? 'Nenhum' : p.dependents + ' dependente(s)') : null);
    _setProfileField('pf-email', p.email);

    // Tab Financeiro
    _setProfileField('pf-income', p.monthly_income ? formatCurrency(p.monthly_income) : null);
    _setProfileField('pf-risk', p.risk_tolerance);
    const investsMap = { nao_investe: 'Não investe ainda', investe: 'Sim, investe', quer_comecar: 'Quer começar' };
    _setProfileField('pf-invests', investsMap[p.invests] || p.invests);
    _setProfileField('pf-inv-types', (p.investment_types || []).join(', ') || 'Nenhum informado');

    // Tab Cartões
    const cardsList = document.getElementById('profileCardsList');
    if (cardsList) {
      if (!p.cards || p.cards.length === 0) {
        cardsList.innerHTML = '<div style="text-align:center;color:var(--lh-text-muted);font-size:0.85rem;padding:20px;">Nenhum cartão cadastrado.</div>';
      } else {
        cardsList.innerHTML = p.cards.map(c => `
          <div style="background:var(--lh-panel-alt,rgba(100,116,139,.06));border:1px solid var(--lh-border);border-radius:8px;padding:12px 14px;display:flex;justify-content:space-between;align-items:center;gap:8px;">
            <div>
              <div style="font-weight:700;font-size:0.9rem;">${c.name}${c.bank ? ' · ' + c.bank : ''}</div>
              <div style="font-size:0.78rem;color:var(--lh-text-muted);margin-top:2px;">Fecha dia ${c.closing_day || '—'} · Vence dia ${c.due_day || '—'}</div>
            </div>
            <div style="text-align:right;flex-shrink:0;">
              ${c.credit_limit ? `<div style="font-size:0.78rem;color:var(--lh-text-muted);">Limite: ${formatCurrency(c.credit_limit)}</div>` : ''}
              ${c.current_balance != null ? `<div style="font-size:0.85rem;font-weight:700;color:#ef4444;">Fatura: ${formatCurrency(c.current_balance)}</div>` : ''}
            </div>
          </div>`).join('');
      }
    }

    // Tab Objetivo
    const goalEl = document.getElementById('profileGoalContent');
    if (goalEl) {
      if (!p.goal) {
        goalEl.innerHTML = '<div style="text-align:center;color:var(--lh-text-muted);font-size:0.85rem;padding:20px;">Nenhum objetivo cadastrado.<br><a href="/onboarding" style="color:#1E56A0;font-weight:600;">Cadastrar objetivo</a></div>';
      } else {
        const g = p.goal;
        const pct = g.target_amount > 0 ? Math.min(100, Math.round((g.current_amount / g.target_amount) * 100)) : 0;
        goalEl.innerHTML = `
          <div style="margin-bottom:12px;">
            <div style="font-size:1rem;font-weight:700;">${g.title || g.goal_type}</div>
            ${g.target_date ? `<div style="font-size:0.78rem;color:var(--lh-text-muted);margin-top:2px;">Prazo: ${new Date(g.target_date).toLocaleDateString('pt-BR',{month:'long',year:'numeric'})}</div>` : ''}
          </div>
          <div style="margin-bottom:8px;">
            <div style="display:flex;justify-content:space-between;font-size:0.8rem;margin-bottom:6px;">
              <span style="color:var(--lh-text-muted);">Progresso</span>
              <span style="font-weight:700;color:#2EA884;">${pct}%</span>
            </div>
            <div style="background:var(--lh-border);border-radius:4px;height:8px;">
              <div style="background:linear-gradient(90deg,#1E56A0,#2EA884);height:100%;border-radius:4px;width:${pct}%;transition:width .5s ease;"></div>
            </div>
          </div>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-top:14px;">
            <div><div style="font-size:0.72rem;color:var(--lh-text-muted);text-transform:uppercase;letter-spacing:.5px;margin-bottom:4px;">Já guardei</div><div style="font-size:1rem;font-weight:700;color:#2EA884;">${formatCurrency(g.current_amount || 0)}</div></div>
            <div><div style="font-size:0.72rem;color:var(--lh-text-muted);text-transform:uppercase;letter-spacing:.5px;margin-bottom:4px;">Meta total</div><div style="font-size:1rem;font-weight:700;">${formatCurrency(g.target_amount || 0)}</div></div>
          </div>`;
      }
    }
  } catch(e) {
    console.warn('loadProfileData:', e);
  }
}

function _setProfileField(id, value) {
  const el = document.getElementById(id);
  if (el) el.textContent = value || '—';
}

function _setAvatarImage(url) {
  const img = document.getElementById('profileAvatarImg');
  const initials = document.getElementById('profileAvatarInitials');
  const headerImg = document.getElementById('headerAvatarImg');
  const headerInitials = document.getElementById('headerAvatarInitials');
  if (img) { img.src = url; img.style.display = 'block'; }
  if (initials) initials.style.display = 'none';
  if (headerImg) { headerImg.src = url; headerImg.style.display = 'block'; }
  if (headerInitials) headerInitials.style.display = 'none';
}

async function uploadAvatar(file) {
  if (!file) return;
  const formData = new FormData();
  formData.append('file', file);
  try {
    const res = await fetch('/api/profile/avatar', { method: 'POST', body: formData });
    if (!res.ok) { const e = await res.json(); throw new Error(e.detail || res.status); }
    const data = await res.json();
    _setAvatarImage(data.avatar_url + '?t=' + Date.now());
  } catch(e) {
    alert('Erro ao enviar foto: ' + e.message);
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

    // KPIs — usa total_outflow (fixos + variáveis + dívidas + cartão)
    const s = data.summary;
    const totalOut = (s.total_expenses_fixed||0) + (s.total_expenses_variable||0) +
                     (s.total_expenses_debt||0) + (s.total_expenses_card||0);
    setText('kpiIncome',  formatCurrency(s.total_income));
    setText('kpiFixed',   formatCurrency(totalOut));
    setText('kpiDebts',   formatCurrency((s.total_expenses_debt||0) + (s.total_expenses_card||0)));
    const surplus = s.net_surplus;
    const surplusEl = document.getElementById('kpiSurplus');
    if (surplusEl) {
      surplusEl.textContent = (surplus >= 0 ? '+ ' : '') + formatCurrency(surplus);
      surplusEl.className = 'lh-kpi-value tabular-nums ' + (surplus >= 0 ? 'text-green' : 'text-red');
    }

    // Subtítulo de despesas com breakdown
    const fixedSub = document.getElementById('kpiFixedSub');
    if (fixedSub) {
      const parts = [];
      if (s.total_expenses_fixed > 0) parts.push(`Fixos ${formatCurrency(s.total_expenses_fixed)}`);
      if (s.total_expenses_variable > 0) parts.push(`Variáveis ${formatCurrency(s.total_expenses_variable)}`);
      if ((s.total_expenses_debt||0)+(s.total_expenses_card||0) > 0)
        parts.push(`Dívidas/Cartão ${formatCurrency((s.total_expenses_debt||0)+(s.total_expenses_card||0))}`);
      fixedSub.textContent = parts.length > 0 ? parts.join(' · ') : 'Fixos + Variáveis + Dívidas';
    }

    // Subtítulo de receita
    const incomeSub = document.getElementById('kpiIncomeSub');
    if (incomeSub) incomeSub.textContent = `Total de entradas do mês`;

    // Diagnóstico de sobra
    const surplusDiag = document.getElementById('kpiSurplusDiag');
    if (surplusDiag) surplusDiag.textContent = surplus > 500 ? 'Folga sólida consolidada' : surplus >= 0 ? 'Saldo positivo' : 'Atenção: déficit no mês';

    // Listas
    renderExpenses(data.expenses);
    renderIncome(data.income);

    // Insights automáticos
    renderInsights(s);
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

  const aporte   = p.monthly_investment_target || 0;
  const income   = p.monthly_income_base || 0;
  const pctSav   = p.pct_savings_used || 0;
  const srcLabel = p.income_source === 'perfil_onboarding'
    ? '(renda do cadastro)'
    : '(lançamentos do mês)';

  const allocs = [
    { label: 'Renda Fixa', key: 'pct_renda_fixa',      pct: p.pct_renda_fixa,      color: '#1E56A0', icon: '🏦' },
    { label: 'Tesouro',    key: 'pct_tesouro',          pct: p.pct_tesouro,          color: '#2EA884', icon: '🟢' },
    { label: 'FIIs',       key: 'pct_fiis',             pct: p.pct_fiis,             color: '#7C5CBF', icon: '🏢' },
    { label: 'Ações',      key: 'pct_acoes',            pct: p.pct_acoes,            color: '#E59830', icon: '📈' },
    { label: 'Liquidez',   key: 'pct_reserva_liquida',  pct: p.pct_reserva_liquida,  color: '#5A6A80', icon: '💧' },
    { label: 'Cripto',     key: 'pct_cripto',           pct: p.pct_cripto,           color: '#EF4444', icon: '₿' },
  ].filter(a => a.pct > 0).map(a => ({
    ...a,
    valor: aporte > 0 ? aporte * (a.pct / 100) : 0
  }));

  // ── Cadeia de origem → destino ─────────────────────────────────────────────
  const chainHtml = income > 0 ? `
    <div style="margin-bottom:14px; padding:10px 12px; background:rgba(30,86,160,0.08); border:1px solid rgba(30,86,160,0.2); border-radius:8px; font-size:0.79rem;">
      <div style="font-weight:700; color:var(--lh-text); margin-bottom:6px; font-size:0.78rem; text-transform:uppercase; letter-spacing:.4px;">Origem → Destino</div>
      <div style="display:flex; flex-wrap:wrap; align-items:center; gap:4px; line-height:1.6;">
        <span style="background:var(--lh-panel-alt,rgba(100,116,139,.1)); padding:2px 8px; border-radius:4px; font-weight:600; color:var(--lh-text);">${formatCurrency(income)}</span>
        <span style="color:var(--lh-text-muted);">renda mensal ${srcLabel}</span>
        <span style="color:var(--lh-text-muted); padding:0 2px;">×</span>
        <span style="background:rgba(46,168,132,.12); padding:2px 8px; border-radius:4px; font-weight:700; color:#2EA884;">${pctSav}% poupança</span>
        <span style="color:var(--lh-text-muted); padding:0 2px;">=</span>
        <span style="background:rgba(30,86,160,.12); padding:2px 8px; border-radius:4px; font-weight:800; color:#1E56A0;">${formatCurrency(aporte)}/mês</span>
        <span style="color:var(--lh-text-muted);">para investir</span>
      </div>
    </div>` : `
    <div style="margin-bottom:14px; padding:10px 12px; background:rgba(239,68,68,.07); border:1px solid rgba(239,68,68,.2); border-radius:8px; font-size:0.79rem; color:var(--lh-text-muted);">
      ⚠️ Renda não encontrada — <a href="/onboarding" style="color:#1E56A0; font-weight:600;">cadastre sua renda</a> para ver valores em R$.
    </div>`;

  // ── Grid de alocações com % e R$ ──────────────────────────────────────────
  const gridHtml = `
    <div style="display:grid; grid-template-columns:repeat(auto-fill, minmax(140px, 1fr)); gap:8px; margin-bottom:12px;">
      ${allocs.map(a => `
        <div style="background:var(--lh-panel-alt,rgba(100,116,139,.06)); border:1px solid var(--lh-border); border-radius:8px; padding:10px 12px;">
          <div style="display:flex; align-items:center; gap:5px; margin-bottom:4px;">
            <span style="font-size:0.9rem;">${a.icon}</span>
            <span style="font-size:0.78rem; color:var(--lh-text-muted); font-weight:500;">${a.label}</span>
          </div>
          <div style="font-size:1.3rem; font-weight:800; color:${a.color}; line-height:1;">${a.pct}%</div>
          ${aporte > 0
            ? `<div style="font-size:0.82rem; font-weight:700; color:var(--lh-text); margin-top:3px;">${formatCurrency(a.valor)}<span style="font-size:0.7rem; font-weight:400; color:var(--lh-text-muted);">/mês</span></div>
               <div style="font-size:0.68rem; color:var(--lh-text-muted); margin-top:2px;">${formatCurrency(aporte)} × ${a.pct}%</div>`
            : `<div style="font-size:0.72rem; color:var(--lh-text-muted); margin-top:3px;">— sem renda</div>`
          }
        </div>`).join('')}
    </div>`;

  // ── Resumo de destinos ─────────────────────────────────────────────────────
  const reserva = p.emergency_reserve_target || 0;
  const resumoHtml = `
    <div style="display:grid; grid-template-columns:1fr 1fr; gap:8px; margin-bottom:12px;">
      <div style="padding:10px 12px; background:var(--lh-panel-alt,rgba(100,116,139,.06)); border:1px solid var(--lh-border); border-radius:8px;">
        <div style="font-size:0.7rem; color:var(--lh-text-muted); text-transform:uppercase; letter-spacing:.4px; margin-bottom:3px;">Aporte mensal</div>
        <div style="font-size:1rem; font-weight:800; color:#1E56A0;">${formatCurrency(aporte)}</div>
        ${income > 0 ? `<div style="font-size:0.7rem; color:var(--lh-text-muted); margin-top:2px;">${pctSav}% de ${formatCurrency(income)}</div>` : ''}
      </div>
      <div style="padding:10px 12px; background:var(--lh-panel-alt,rgba(100,116,139,.06)); border:1px solid var(--lh-border); border-radius:8px;">
        <div style="font-size:0.7rem; color:var(--lh-text-muted); text-transform:uppercase; letter-spacing:.4px; margin-bottom:3px;">Reserva de emergência</div>
        <div style="font-size:1rem; font-weight:800; color:#E59830;">${formatCurrency(reserva)}</div>
        ${income > 0 ? `<div style="font-size:0.7rem; color:var(--lh-text-muted); margin-top:2px;">6 × ${formatCurrency(income)}</div>` : ''}
      </div>
    </div>
    ${p.months_to_goal ? `
    <div style="padding:8px 12px; background:rgba(46,168,132,.08); border:1px solid rgba(46,168,132,.2); border-radius:8px; margin-bottom:12px; font-size:0.8rem;">
      <strong>🎯 Meta:</strong> com ${formatCurrency(aporte)}/mês, você atinge o objetivo em <strong>${p.months_to_goal} meses</strong>
      (~${Math.ceil(p.months_to_goal / 12)} ${Math.ceil(p.months_to_goal / 12) === 1 ? 'ano' : 'anos'})
    </div>` : ''}`;

  // ── Justificativa ──────────────────────────────────────────────────────────
  const rationaleHtml = p.rationale ? `
    <details style="margin-top:4px; font-size:0.78rem; color:var(--lh-text-muted);">
      <summary style="cursor:pointer; font-weight:600; color:var(--lh-text); user-select:none;">▾ Justificativa da IA</summary>
      <p style="margin-top:6px; line-height:1.5; padding:8px; background:var(--lh-panel-alt,rgba(100,116,139,.06)); border-radius:6px;">${p.rationale}</p>
    </details>` : '';

  panel.innerHTML = chainHtml + gridHtml + resumoHtml + rationaleHtml;
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
  const surplus  = data.map(d => Math.max(0, d.net_surplus || 0));
  const isProjected = data.map(d => !!d.is_projected);

  const options = {
    chart: {
      type: 'bar', height: 330, stacked: true,
      toolbar: { show: false },
      fontFamily: 'Plus Jakarta Sans, Inter, sans-serif',
    },
    colors: [colors.cobalt, '#7C5CBF', colors.amber, colors.green],
    series: [
      { name: 'Fixos',     data: fixed,    type: 'bar' },
      { name: 'Variáveis', data: variable, type: 'bar' },
      { name: 'Dívidas',   data: debts,    type: 'bar' },
      { name: 'Sobra',     data: surplus,  type: 'bar' },
    ],
    xaxis: {
      categories,
      labels: { style: { fontSize: '11px' } }
    },
    yaxis: {
      labels: { formatter: v => 'R$\u00a0' + v.toLocaleString('pt-BR', {minimumFractionDigits: 0, maximumFractionDigits: 0}) }
    },
    legend: { position: 'top', fontSize: '12px' },
    tooltip: {
      shared: true,
      intersect: false,
      y: { formatter: v => formatCurrency(v) },
      custom: function({ series, seriesIndex, dataPointIndex, w }) {
        const d = data[dataPointIndex];
        const inc = d.total_income || 0;
        const fix = d.total_expenses_fixed || 0;
        const vari = d.total_expenses_variable || 0;
        const dbt = (d.total_expenses_debt || 0) + (d.total_expenses_card || 0);
        const sob = d.net_surplus || 0;
        const proj = d.is_projected ? '<div style="color:#f59e0b;font-size:10px;margin-bottom:4px;">📊 Projeção (sem lançamentos reais)</div>' : '';
        const row = (label, val, color) =>
          `<div style="display:flex;justify-content:space-between;gap:16px;padding:2px 0;">
            <span style="color:${color||'inherit'}">${label}</span>
            <strong>${formatCurrency(val)}</strong>
          </div>`;
        return `<div style="padding:10px 14px;font-size:12px;min-width:200px;">
          ${proj}
          <div style="font-weight:700;margin-bottom:6px;">${d.label || ''}</div>
          ${row('Receita', inc, '#2EA884')}
          <hr style="border:none;border-top:1px solid rgba(100,116,139,.2);margin:4px 0;">
          ${row('Fixos', fix, colors.cobalt)}
          ${vari > 0 ? row('Variáveis', vari, '#7C5CBF') : ''}
          ${dbt > 0 ? row('Dívidas/Cartão', dbt, colors.amber) : ''}
          <hr style="border:none;border-top:1px solid rgba(100,116,139,.2);margin:4px 0;">
          ${row(sob >= 0 ? 'Sobra' : 'Deficit', sob, sob >= 0 ? '#2EA884' : '#ef4444')}
        </div>`;
      }
    },
    plotOptions: {
      bar: {
        borderRadius: 3,
        columnWidth: '65%',
      }
    },
    dataLabels: { enabled: false },
    grid: { borderColor: colors.border, strokeDashArray: 3 },
    // Destaque visual de meses com dados reais vs projetados
    annotations: {
      xaxis: data
        .map((d, i) => d.is_projected ? null : {
          x: categories[i],
          borderColor: 'rgba(30,86,160,0.4)',
          borderWidth: 2,
          label: { text: '', style: { background: 'transparent' } }
        })
        .filter(Boolean)
    },
    fill: {
      opacity: data.map(d => d.is_projected ? 0.45 : 1),
    },
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

  const onboarded = typeof APP_CONFIG !== 'undefined' && APP_CONFIG.isReturning;

  if (!onboarded) {
    // Usuário ainda não fez onboarding — mostrar estado vazio em tudo
    initMethodologyDonut();  // gráfico vazio (sem dados, não chama API)
    const emptyMsg = '<div style="text-align:center; color:var(--lh-text-muted); font-size:0.85rem; padding:24px;">Complete o cadastro para ver seus dados aqui.</div>';
    ['expenseListContainer','incomeListContainer','goalPanel','portfolioPanel'].forEach(id => {
      const el = document.getElementById(id);
      if (el) el.innerHTML = emptyMsg;
    });
    ['kpiIncome','kpiFixed','kpiDebts','kpiSurplus'].forEach(id => {
      const el = document.getElementById(id);
      if (el) el.textContent = '—';
    });
    return;  // 🚫 nada mais carrega — sem seed data
  }

  // Usuário autenticado com onboarding completo
  initMethodologyDonut();
  loadCategories();
  loadBudgetMonth();   // KPIs + despesas + receitas do mês
  loadTimeline();      // gráfico de fluxo de caixa
  loadCardBadges();
  loadKPIs();          // KPIs legados (consenso)
  loadConsensus();     // hub de decisão IA
  loadGoal();          // objetivo principal
  loadPortfolio();     // carteira ativa
});
