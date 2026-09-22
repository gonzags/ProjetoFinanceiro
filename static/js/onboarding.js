/**
 * onboarding.js - Gerenciador do Wizard Interativo de Onboarding (6 Passos)
 * Ledger Horizon Financial Platform
 */

let currentOnboardingStep = 1;
const totalOnboardingSteps = 5;  // Modal atual usa steps 1-5 (step3=despesas, step4=objetivo, step5=invest+consentimento)

const stepHeaders = {
  1: {
    title: "Identificação & Atuação",
    subtitle: "Conte-nos sobre você para que o comitê de inteligência conheça seu momento profissional.",
    percent: "20% concluído"
  },
  2: {
    title: "Rendimentos & Patrimônio",
    subtitle: "Informe sua renda e quanto já tem guardado para dimensionarmos seu fluxo de caixa.",
    percent: "40% concluído"
  },
  3: {
    title: "Gastos Fixos Mensais",
    subtitle: "Liste seus custos fixos mês a mês — quanto mais detalhar, mais precisa será a análise.",
    percent: "60% concluído"
  },
  4: {
    title: "Objetivo Financeiro Principal",
    subtitle: "Defina sua meta principal para que a IA calcule o caminho mais eficiente até lá.",
    percent: "80% concluído"
  },
  5: {
    title: "Perfil de Investimentos & Consentimento",
    subtitle: "Defina seu perfil de risco e autorize o compartilhamento de dados com os modelos de IA.",
    percent: "100% — Quase lá!"
  }
};

function updateOnboardingUI() {
  for (let i = 1; i <= totalOnboardingSteps; i++) {
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

  if (titleEl)    titleEl.textContent    = info.title;
  if (subtitleEl) subtitleEl.textContent = info.subtitle;
  if (badgeEl)    badgeEl.textContent    = `Passo ${currentOnboardingStep} de ${totalOnboardingSteps}`;
  if (percentEl)  percentEl.textContent  = info.percent;
  if (barEl)      barEl.style.width      = `${(currentOnboardingStep / totalOnboardingSteps) * 100}%`;

  const btnPrev   = document.getElementById("btnObPrev");
  const btnNext   = document.getElementById("btnObNext");
  const btnSubmit = document.getElementById("btnObSubmit");

  if (btnPrev)   btnPrev.style.display   = currentOnboardingStep > 1 ? "inline-block" : "none";
  if (btnNext)   btnNext.style.display   = currentOnboardingStep < totalOnboardingSteps ? "inline-block" : "none";
  if (btnSubmit) btnSubmit.style.display = currentOnboardingStep === totalOnboardingSteps ? "inline-block" : "none";
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
    // Despesas itemizadas — pelo menos 1 linha com nome e valor
    const names   = document.querySelectorAll(".ob-expense-name");
    const amounts = document.querySelectorAll(".ob-expense-amount");
    let hasValid = false;
    for (let i = 0; i < names.length; i++) {
      if (names[i].value.trim() && parseFloat(amounts[i].value) > 0) { hasValid = true; break; }
    }
    if (!hasValid) {
      showOnboardingFeedback("Adicione pelo menos um custo fixo com nome e valor.", "error");
      return false;
    }
  } else if (currentOnboardingStep === 5) {
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
  if (currentOnboardingStep < totalOnboardingSteps) {
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

function collectOnboardingData(isDraft = false) {
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

  return {
    is_draft:              isDraft,
    data_consent:          dataConsent,
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
    // Objetivo
    goal_type:             goalType,
    goal_title:            goalTitle,
    goal_target_amount:    goalAmount,
    goal_target_date:      goalDate ? goalDate + "-01" : null,
    goal_current_amount:   goalCurrent,
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

async function saveOnboardingDraft() {
  const data = collectOnboardingData(true);
  const btnDraft = document.getElementById("btnObDraft");
  if (btnDraft) btnDraft.textContent = "Salvando rascunho...";

  try {
    const res = await fetch("/api/onboarding", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data)
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "Falha ao salvar rascunho.");
    }

    showOnboardingFeedback("Rascunho salvo com sucesso! Você pode continuar a qualquer momento.", "success");
    setTimeout(() => {
      toggleOnboardingModal(false);
    }, 1500);
  } catch (err) {
    showOnboardingFeedback(err.message, "error");
  } finally {
    if (btnDraft) btnDraft.textContent = "Salvar rascunho e continuar depois";
  }
}

async function submitOnboardingFinal() {
  if (!validateCurrentStep()) return;
  const data = collectOnboardingData(false);
  const btnSubmit = document.getElementById("btnObSubmit");
  if (btnSubmit) {
    btnSubmit.disabled = true;
    btnSubmit.textContent = "Processando perfil e consenso com IA...";
  }

  showOnboardingFeedback("Gravando perfil e acionando comitê de inteligência artificial...", "info");

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

    showOnboardingFeedback("Perfil configurado com sucesso! Carregando seu dashboard...", "success");
    setTimeout(() => {
      window.location.reload();
    }, 1200);
  } catch (err) {
    showOnboardingFeedback(err.message, "error");
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
