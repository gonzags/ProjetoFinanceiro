/**
 * onboarding.js - Gerenciador do Wizard Interativo de Onboarding (6 Passos)
 * Ledger Horizon Financial Platform
 */

let currentOnboardingStep = 1;
let userType = 'pf';  // NOVA VARIÁVEL GLOBAL
const PF_TOTAL_STEPS = 9;
const PJ_TOTAL_STEPS = 7;

function getTotalSteps() {
  return userType === 'pj' ? PJ_TOTAL_STEPS : PF_TOTAL_STEPS;
}

const totalOnboardingSteps = 9;  // Manter para compatibilidade, mas usar getTotalSteps()

const stepHeaders = {
  1: { title: 'Perfil Pessoal', subtitle: 'Conte-nos um pouco sobre você para personalizar a análise.' },
  2: { title: 'Fontes de Renda', subtitle: 'Liste cada fonte de renda separadamente, incluindo temporárias.' },
  3: { title: 'Cartões & Contas', subtitle: 'Seus cartões e contas bancárias para rastrear faturas e fluxo.' },
  4: { title: 'Dívidas & Financiamentos', subtitle: 'Dívidas ativas que impactam seu fluxo de caixa mensal.' },
  5: { title: 'Patrimônio & Bens', subtitle: 'Imóvel, veículo e investimentos já existentes.' },
  6: { title: 'Despesas Fixas', subtitle: 'Gastos fixos mensais — quanto mais detalhar, melhor a análise.' },
  7: { title: 'Despesas Variáveis', subtitle: 'Médias mensais de gastos variáveis para calibrar sua margem real.' },
  8: { title: 'Objetivo Financeiro', subtitle: 'Defina uma meta clara para que a IA planeje o caminho.' },
  9: { title: 'Perfil & Consentimento', subtitle: 'Finalize com suas preferências de investimento e autorize o uso dos dados.' },
};

function handleUserTypeChange() {
  userType = document.getElementById('obUserType')?.value || 'pf';
  const pjSection = document.getElementById('pjSection');
  if (pjSection) pjSection.style.display = userType === 'pj' ? 'block' : 'none';
  updateOnboardingUI();
}

function updateOnboardingUI() {
  const total = getTotalSteps();
  for (let i = 1; i <= 9; i++) {
    const stepEl = document.getElementById(`step${i}`);
    if (stepEl) {
      stepEl.style.display = i === currentOnboardingStep ? "block" : "none";
    }
  }

  const info = stepHeaders[currentOnboardingStep];
  const titleEl   = document.getElementById("onboardingTitle");
  const subtitleEl = document.getElementById("onboardingSubtitle");
  const badgeEl   = document.getElementById("onboardingStepBadge");
  const percentEl = document.getElementById("onboardingStepPercent");
  const barEl     = document.getElementById("onboardingProgressBar");

  const pct = Math.round((currentOnboardingStep / total) * 100);

  if (titleEl)    titleEl.textContent    = info.title;
  if (subtitleEl) subtitleEl.textContent = info.subtitle;
  if (badgeEl)    badgeEl.textContent    = `Passo ${currentOnboardingStep} de ${total}`;
  if (percentEl)  percentEl.textContent  = `${pct}% concluído`;
  if (barEl)      barEl.style.width      = `${pct}%`;

  const btnPrev   = document.getElementById("btnObPrev");
  const btnNext   = document.getElementById("btnObNext");
  const btnSubmit = document.getElementById("btnObSubmit");

  if (btnPrev)   btnPrev.style.display   = currentOnboardingStep > 1 ? "inline-block" : "none";
  if (btnNext)   btnNext.style.display   = currentOnboardingStep < total ? "inline-block" : "none";
  if (btnSubmit) btnSubmit.style.display = currentOnboardingStep === total ? "inline-block" : "none";

  // Recalcular totais para manter reatividade consistente ao navegar
  if (typeof updateIncomeTotal === 'function') updateIncomeTotal();
  if (typeof updateDebtsTotal === 'function') updateDebtsTotal();
  if (typeof updateExpensesTotal === 'function') updateExpensesTotal();
  if (typeof updateVarTotal === 'function') updateVarTotal();
}

function validateCurrentStep() {
  hideOnboardingFeedback();
  if (currentOnboardingStep === 1) {
    const name = document.getElementById("obName")?.value.trim();
    const age  = parseInt(document.getElementById("obAge")?.value, 10);
    const occ  = document.getElementById("obOccupation")?.value.trim();
    if (!name) { showOnboardingFeedback("Por favor, preencha seu nome completo.", "error"); return false; }
    if (isNaN(age) || age < 14 || age > 120) { showOnboardingFeedback("Por favor, insira uma idade válida (14–120).", "error"); return false; }
    if (!occ) { showOnboardingFeedback("Por favor, informe sua profissão ou área.", "error"); return false; }
  } else if (currentOnboardingStep === 2) {
    // Pelo menos 1 fonte de renda com nome e valor positivo
    const names   = document.querySelectorAll('.ob-income-name');
    const amounts = document.querySelectorAll('.ob-income-amount');
    let hasValidIncome = false;
    for (let i = 0; i < names.length; i++) {
      if (names[i].value.trim() && parseFloat(amounts[i].value) > 0) { hasValidIncome = true; break; }
    }
    if (!hasValidIncome) {
      showOnboardingFeedback('Adicione ao menos uma fonte de renda com nome e valor.', 'error');
      return false;
    }
  } else if (currentOnboardingStep === 3) {
    // Cartões & Contas — sem obrigatoriedade, mas validar consistency
    return true; // Pode avançar com 0 cartões e 0 contas
  } else if (currentOnboardingStep === 4) {
    // Dívidas — se não marcou "sem dívidas" e tem linhas vazias, alertar
    const noDebts = document.getElementById('obNoDebts')?.checked;
    if (!noDebts) {
      const rows = document.querySelectorAll('.ob-debt-row');
      // OK se não tem linhas (equivale a sem dívidas)
    }
    return true;
  } else if (currentOnboardingStep === 5) {
    // Patrimônio — sem obrigatoriedade
    return true;
  } else if (currentOnboardingStep === 6) {
    // Despesas itemizadas (era step 3)
    const names = document.querySelectorAll('.ob-expense-name');
    const amounts = document.querySelectorAll('.ob-expense-amount');
    let hasValid = false;
    for (let i = 0; i < names.length; i++) {
      if (names[i].value.trim() && parseFloat(amounts[i].value) > 0) { hasValid = true; break; }
    }
    if (!hasValid) { showOnboardingFeedback('Adicione ao menos uma despesa fixa.', 'error'); return false; }
  } else if (currentOnboardingStep === 7) {
    // Despesas variáveis — sem obrigatoriedade
    return true;
  } else if (currentOnboardingStep === 9) {
    const consent = document.getElementById("obDataConsent");
    if (consent && !consent.checked) {
      showOnboardingFeedback("É necessário aceitar os termos de compartilhamento de dados para continuar.", "error");
      return false;
    }
  }
  return true;
}

function onboardingNextStep() {
  if (!validateCurrentStep()) return;
  const total = getTotalSteps();
  if (currentOnboardingStep < total) {
    currentOnboardingStep++;
    updateOnboardingUI();
  }
}

function onboardingPrevStep() {
  if (currentOnboardingStep > 1) {
    currentOnboardingStep--;
    updateOnboardingUI();
  }
}

function collectOnboardingData() {
  const assetCheckboxes = document.querySelectorAll('input[name="obAssetType"]:checked');
  const selectedAssets  = Array.from(assetCheckboxes).map(cb => cb.value);
  const selectedRisk    = document.querySelector('input[name="obRiskTolerance"]:checked')?.value || "moderado";
  const dataConsent     = document.getElementById("obDataConsent")?.checked || false;

  // ── Coletar fontes de renda itemizadas ──────────────────────────────────
  const incomeRows = document.querySelectorAll(".ob-income-row");
  const incomeList = [];
  incomeRows.forEach(row => {
    const name   = row.querySelector(".ob-income-name")?.value.trim();
    const amount = parseFloat(row.querySelector(".ob-income-amount")?.value) || 0;
    const type   = row.querySelector(".ob-income-type")?.value || "other";
    const months = parseInt(row.querySelector(".ob-income-months")?.value, 10) || null;  // null = permanente
    if (name && amount > 0) {
      incomeList.push({ name, amount, type, months_remaining: months });
    }
  });

  // Derivados para compatibilidade com backend legado
  const permanentIncome = incomeList
    .filter(s => !s.months_remaining && ['salary','benefit'].includes(s.type))
    .reduce((s, e) => s + e.amount, 0);
  const temporaryIncome = incomeList
    .filter(s => s.months_remaining || ['extra','bonus','investment_return','other'].includes(s.type))
    .reduce((s, e) => s + e.amount, 0);
  const totalMonthlyIncome = incomeList.reduce((s, e) => s + e.amount, 0);

  // ── Coletar despesas itemizadas ──────────────────────────────────────────
  const expenseRows = document.querySelectorAll(".ob-expense-row");
  const fixedExpenses = [];
  expenseRows.forEach(row => {
    const name     = row.querySelector(".ob-expense-name")?.value.trim();
    const amount   = parseFloat(row.querySelector(".ob-expense-amount")?.value) || 0;
    const category = row.querySelector(".ob-expense-category")?.value || "outro";
    if (name && amount > 0) {
      fixedExpenses.push({ name, amount, category });
    }
  });
  const fixedTotal = fixedExpenses.reduce((s, e) => s + e.amount, 0);

  // ── Objetivo ─────────────────────────────────────────────────────────────
  const goalType    = document.getElementById("obGoalType")?.value || "emergencia";
  const goalTitleEl = document.getElementById("obGoalTitle");
  const goalTitle   = goalTitleEl?.value.trim() || goalTypeDefaultTitle(goalType);
  const goalAmount  = parseFloat(document.getElementById("obGoalAmount")?.value) || null;
  const goalDate    = document.getElementById("obGoalDate")?.value || null;
  const goalCurrent = parseFloat(document.getElementById("obGoalCurrent")?.value) || 0;

  // ── Coletar cartões ──────────────────────────────────────────────────────
  const cardRows = document.querySelectorAll('.ob-card-row');
  const cards = [];
  cardRows.forEach(row => {
    const name = row.querySelector('.ob-card-name')?.value.trim();
    const closingDay = parseInt(row.querySelector('.ob-card-closing')?.value) || null;
    const dueDay = parseInt(row.querySelector('.ob-card-due')?.value) || null;
    if (name && closingDay && dueDay) {
      cards.push({
        name, closing_day: closingDay, due_day: dueDay,
        credit_limit: parseFloat(row.querySelector('.ob-card-limit')?.value) || 0,
        current_balance: parseFloat(row.querySelector('.ob-card-balance')?.value) || 0,
      });
    }
  });

  // ── Coletar contas ───────────────────────────────────────────────────────
  const accountRows = document.querySelectorAll('.ob-account-row');
  const bankAccounts = [];
  accountRows.forEach(row => {
    const bankName = row.querySelector('.ob-account-bank')?.value.trim();
    if (bankName) {
      bankAccounts.push({
        bank_name: bankName,
        account_type: row.querySelector('.ob-account-type')?.value || 'corrente',
        balance_approx: parseFloat(row.querySelector('.ob-account-balance')?.value) || 0,
      });
    }
  });

  // ── Coletar dívidas ──────────────────────────────────────────────────────
  const noDebts = document.getElementById('obNoDebts')?.checked;
  const debtRows = document.querySelectorAll('.ob-debt-row');
  const debts = [];
  if (!noDebts) {
    debtRows.forEach(row => {
      const desc = row.querySelector('.ob-debt-desc')?.value.trim();
      const payment = parseFloat(row.querySelector('.ob-debt-payment')?.value) || 0;
      if (desc && payment > 0) {
        debts.push({
          description: desc,
          debt_type: row.querySelector('.ob-debt-type')?.value || 'outro',
          total_amount: parseFloat(row.querySelector('.ob-debt-total')?.value) || 0,
          monthly_payment: payment,
          installments_remaining: parseInt(row.querySelector('.ob-debt-installments')?.value) || null,
          interest_rate_monthly: parseFloat(row.querySelector('.ob-debt-interest')?.value) || null,
        });
      }
    });
  }

  // ── Coletar patrimônio ───────────────────────────────────────────────────
  const assets = [];
  const imovelVal = document.getElementById('obImovel')?.value;
  if (imovelVal && imovelVal !== 'nenhum') {
    assets.push({
      asset_type: imovelVal === 'proprio_quitado' ? 'imovel_proprio' : 'imovel_financiando',
      description: 'Imóvel',
      estimated_value: parseFloat(document.getElementById('obImovelValue')?.value) || null,
      monthly_payment: imovelVal === 'financiando' ? parseFloat(document.getElementById('obImovelPayment')?.value) || null : null,
      installments_remaining: imovelVal === 'financiando' ? parseInt(document.getElementById('obImovelMonths')?.value) || null : null,
    });
  }
  const veiculoVal = document.getElementById('obVeiculo')?.value;
  if (veiculoVal && veiculoVal !== 'nenhum') {
    assets.push({
      asset_type: veiculoVal === 'proprio_quitado' ? 'veiculo_quitado' : 'veiculo_financiando',
      description: 'Veículo',
      estimated_value: parseFloat(document.getElementById('obVeiculoValue')?.value) || null,
      monthly_payment: veiculoVal === 'financiando' ? parseFloat(document.getElementById('obVeiculoPayment')?.value) || null : null,
      installments_remaining: veiculoVal === 'financiando' ? parseInt(document.getElementById('obVeiculoMonths')?.value) || null : null,
    });
  }
  document.querySelectorAll('.ob-asset-row').forEach(row => {
    const val = parseFloat(row.querySelector('.ob-asset-value')?.value) || 0;
    if (val > 0) {
      assets.push({
        asset_type: row.querySelector('.ob-asset-type')?.value || 'outro',
        description: 'Investimento',
        estimated_value: val,
      });
    }
  });

  // ── Coletar despesas variáveis médias ────────────────────────────────────
  const variableExpenseAverages = {
    alimentacao_fora: parseFloat(document.getElementById('obVarAlimentacao')?.value) || 0,
    transporte: parseFloat(document.getElementById('obVarTransporte')?.value) || 0,
    lazer: parseFloat(document.getElementById('obVarLazer')?.value) || 0,
    vestuario: parseFloat(document.getElementById('obVarVestuario')?.value) || 0,
    outros: parseFloat(document.getElementById('obVarOutros')?.value) || 0,
  };

  // ── Coletar dados PJ (se userType === 'pj') ──────────────────────────────
  let pjData = null;
  if (userType === 'pj') {
    pjData = {
      cnpj: document.getElementById('obPjCnpj')?.value.trim() || null,
      regime_tributario: document.getElementById('obPjRegime')?.value || null,
      business_type: document.getElementById('obPjBusinessType')?.value.trim() || null,
      monthly_revenue_avg: parseFloat(document.getElementById('obPjRevenue')?.value) || null,
      prolabore: parseFloat(document.getElementById('obPjProlabore')?.value) || null,
      payroll_total: parseFloat(document.getElementById('obPjPayroll')?.value) || null,
      tax_monthly: parseFloat(document.getElementById('obPjTax')?.value) || null,
      operational_costs: parseFloat(document.getElementById('obPjOpCosts')?.value) || null,
      partner_count: parseInt(document.getElementById('obPjPartners')?.value) || 1,
    };
  }

  return {
    is_draft:              false,
    data_consent:          dataConsent,
    user_type:             userType,
    marital_status:        document.getElementById('obMaritalStatus')?.value || null,
    dependents:            parseInt(document.getElementById('obDependents')?.value) || 0,
    work_regime:           document.getElementById('obWorkRegime')?.value || null,
    pj_data:               pjData,
    // Identificação
    name:                  document.getElementById("obName")?.value.trim() || "",
    age:                   parseInt(document.getElementById("obAge")?.value, 10) || null,
    occupation:            document.getElementById("obOccupation")?.value.trim() || "",
    // Renda — lista detalhada + derivados para compatibilidade
    income_list:           incomeList,
    monthly_income:        permanentIncome || totalMonthlyIncome,   // só permanente, ou tudo se não houver distinção
    extra_income:          temporaryIncome,
    saved_amount:          parseFloat(document.getElementById("obSavedAmount")?.value) || 0.0,
    // Despesas
    fixed_expenses_val:    fixedTotal,
    fixed_expenses_list:   fixedExpenses,
    variable_expenses_val: 0,
    variable_expense_averages: variableExpenseAverages,
    // Objetivo
    goal_type:             goalType,
    goal_title:            goalTitle,
    goal_target_amount:    goalAmount,
    goal_target_date:      goalDate ? goalDate + "-01" : null,
    goal_current_amount:   goalCurrent,
    // Novos
    cards,
    bank_accounts:         bankAccounts,
    debts,
    assets,
    // Perfil de investimento
    invests:               document.getElementById("obInvests")?.value || "nao_investe",
    investment_types:      selectedAssets,
    risk_tolerance:        selectedRisk,
  };
}

function goalTypeDefaultTitle(type) {
  const map = {
    emergencia: "Reserva de Emergência", imovel: "Compra de Imóvel",
    aposentadoria: "Aposentadoria Antecipada", viagem: "Viagem / Experiência",
    divida: "Quitação de Dívidas", independencia: "Independência Financeira", outro: "Objetivo Financeiro"
  };
  return map[type] || "Objetivo Financeiro";
}


async function submitOnboardingFinal() {
  if (!validateCurrentStep()) return;
  const data = collectOnboardingData();

  const wizardHeader = document.getElementById("onboardingWizardHeader");
  const formEl = document.getElementById("onboardingForm");
  const procScreen = document.getElementById("onboardingProcessingScreen");
  const stageText = document.getElementById("obProcStageText");
  const progressBar = document.getElementById("obProcProgressBar");
  const percentText = document.getElementById("obProcPercentText");

  // Transição visual imediata para a tela de carregamento dedicada
  if (wizardHeader) wizardHeader.style.display = "none";
  if (formEl) formEl.style.display = "none";
  hideOnboardingFeedback();
  if (procScreen) procScreen.style.display = "block";

  let currentPct = 8;
  const stages = [
    { at: 10, text: "Salvando suas informações financeiras..." },
    { at: 35, text: "Mapeando fontes de renda, cartões e patrimônio..." },
    { at: 65, text: "Consultando comitê de inteligência artificial..." },
    { at: 85, text: "Consolidando alocações e metas orçamentárias..." }
  ];

  if (progressBar) progressBar.style.width = `${currentPct}%`;
  if (percentText) percentText.textContent = `${currentPct}% concluído`;
  if (stageText) stageText.textContent = stages[0].text;

  const timer = setInterval(() => {
    if (currentPct < 90) {
      currentPct += Math.floor(Math.random() * 6) + 4;
      if (currentPct > 90) currentPct = 90;
      if (progressBar) progressBar.style.width = `${currentPct}%`;
      if (percentText) percentText.textContent = `${currentPct}% concluído`;

      const matched = stages.slice().reverse().find(s => currentPct >= s.at);
      if (matched && stageText) stageText.textContent = matched.text;
    }
  }, 350);

  try {
    const res = await fetch("/api/onboarding", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data)
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "Erro ao concluir onboarding.");
    }

    // Iniciar cálculo em segundo plano para agilizar o dashboard
    fetch("/api/consensus?month=Outubro").catch(() => {});

    clearInterval(timer);
    if (progressBar) progressBar.style.width = "100%";
    if (percentText) percentText.textContent = "100% concluído";
    if (stageText) {
      stageText.innerHTML = '<span style="color:#22c55e;font-weight:600;">✓ Perfil configurado com sucesso! Abrindo seu painel...</span>';
    }

    document.dispatchEvent(new CustomEvent('onboardingComplete'));

    setTimeout(() => {
      window.location.href = "/";
    }, 900);

  } catch (err) {
    clearInterval(timer);
    if (procScreen) procScreen.style.display = "none";
    if (wizardHeader) wizardHeader.style.display = "block";
    if (formEl) formEl.style.display = "block";

    showOnboardingFeedback(err.message, "error");
    const btnSubmit = document.getElementById("btnObSubmit");
    if (btnSubmit) {
      btnSubmit.disabled = false;
      btnSubmit.textContent = "Concluir e Analisar com IA";
    }
  }
}

function showOnboardingFeedback(msg, type) {
  const fb = document.getElementById("onboardingFeedback");
  if (!fb) return;
  fb.style.display = "block";
  fb.textContent = msg;

  if (type === "error") {
    fb.style.background = "#fdf2f2";
    fb.style.color = "#991b1b";
    fb.style.border = "1px solid #f87171";
  } else if (type === "success") {
    fb.style.background = "#f0fdf4";
    fb.style.color = "#166534";
    fb.style.border = "1px solid #86efac";
  } else {
    fb.style.background = "#eff6ff";
    fb.style.color = "#1e40af";
    fb.style.border = "1px solid #93c5fd";
  }
}

function hideOnboardingFeedback() {
  const fb = document.getElementById("onboardingFeedback");
  if (fb) fb.style.display = "none";
}

function toggleOnboardingModal(show) {
  const modal = document.getElementById("onboardingModal");
  if (modal) {
    modal.style.display = show ? "flex" : "none";
    if (show) {
      updateOnboardingUI();
    }
  }
}

async function checkAndInitOnboarding() {
  try {
    const res = await fetch("/api/onboarding");
    if (res.ok) {
      const info = await res.json();
      if (info.user && !info.user.onboarding_completed) {
        // Preencher rascunho anterior se houver
        if (info.profile) {
          const p = info.profile;
          if (p.name) document.getElementById("obName").value = p.name;
          if (p.age) document.getElementById("obAge").value = p.age;
          if (p.occupation) document.getElementById("obOccupation").value = p.occupation;
          if (p.monthly_income) document.getElementById("obIncome").value = p.monthly_income;
          if (p.extra_income) document.getElementById("obExtraIncome").value = p.extra_income;
          if (p.fixed_expenses_val) document.getElementById("obFixedExpenses").value = p.fixed_expenses_val;
          if (p.variable_expenses_val) document.getElementById("obVariableExpenses").value = p.variable_expenses_val;
          if (p.saved_amount) document.getElementById("obSavedAmount").value = p.saved_amount;
          if (p.saved_destination) document.getElementById("obSavedDestination").value = p.saved_destination;
          if (p.invests) document.getElementById("obInvests").value = p.invests;
          if (p.risk_tolerance) {
            const radio = document.querySelector(`input[name="obRiskTolerance"][value="${p.risk_tolerance}"]`);
            if (radio) radio.checked = true;
          }
        }
        toggleOnboardingModal(true);
      }
    }
  } catch (e) {
    console.debug("Onboarding check skipped:", e);
  }
}

document.addEventListener("DOMContentLoaded", () => {
  // Inicialização defensiva do onboarding
  checkAndInitOnboarding();
});
