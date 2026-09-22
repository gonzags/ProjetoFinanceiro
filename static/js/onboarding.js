/**
 * onboarding.js - Gerenciador do Wizard Interativo de Onboarding (5 Passos)
 * Ledger Horizon Financial Platform
 */

let currentOnboardingStep = 1;
const totalOnboardingSteps = 5;

const stepHeaders = {
  1: {
    title: "Identificação & Atuação",
    subtitle: "Conte-nos sobre você para que o comitê de inteligência conheça seu momento profissional.",
    percent: "20% concluído"
  },
  2: {
    title: "Rendimentos & Benefícios",
    subtitle: "Informe quanto você recebe mensalmente para dimensionarmos seu fluxo de caixa real.",
    percent: "40% concluído"
  },
  3: {
    title: "Despesas & Custos de Vida",
    subtitle: "Mapeie suas despesas fixas e variáveis para calcularmos sua margem de sobrevivência.",
    percent: "60% concluído"
  },
  4: {
    title: "Patrimônio & Objetivos",
    subtitle: "Nos diga o que você tem guardado e qual a sua prioridade financeira no momento.",
    percent: "80% concluído"
  },
  5: {
    title: "Investimentos & Perfil de Risco",
    subtitle: "Defina como você lida com investimentos e o direcionamento para o comitê de IA.",
    percent: "100% - Quase lá!"
  }
};

function updateOnboardingUI() {
  // Esconder todos os passos e mostrar o atual
  for (let i = 1; i <= totalOnboardingSteps; i++) {
    const stepEl = document.getElementById(`step${i}`);
    if (stepEl) {
      stepEl.style.display = i === currentOnboardingStep ? "block" : "none";
    }
  }

  // Atualizar textos e badges
  const info = stepHeaders[currentOnboardingStep];
  const titleEl = document.getElementById("onboardingTitle");
  const subtitleEl = document.getElementById("onboardingSubtitle");
  const badgeEl = document.getElementById("onboardingStepBadge");
  const percentEl = document.getElementById("onboardingStepPercent");
  const barEl = document.getElementById("onboardingProgressBar");

  if (titleEl) titleEl.textContent = info.title;
  if (subtitleEl) subtitleEl.textContent = info.subtitle;
  if (badgeEl) badgeEl.textContent = `Passo ${currentOnboardingStep} de ${totalOnboardingSteps}`;
  if (percentEl) percentEl.textContent = info.percent;
  if (barEl) barEl.style.width = `${(currentOnboardingStep / totalOnboardingSteps) * 100}%`;

  // Botões de navegação
  const btnPrev = document.getElementById("btnObPrev");
  const btnNext = document.getElementById("btnObNext");
  const btnSubmit = document.getElementById("btnObSubmit");

  if (btnPrev) btnPrev.style.display = currentOnboardingStep > 1 ? "inline-block" : "none";
  if (btnNext) btnNext.style.display = currentOnboardingStep < totalOnboardingSteps ? "inline-block" : "none";
  if (btnSubmit) btnSubmit.style.display = currentOnboardingStep === totalOnboardingSteps ? "inline-block" : "none";
}

function validateCurrentStep() {
  hideOnboardingFeedback();
  if (currentOnboardingStep === 1) {
    const name = document.getElementById("obName")?.value.trim();
    const age = parseInt(document.getElementById("obAge")?.value, 10);
    const occ = document.getElementById("obOccupation")?.value.trim();
    if (!name) {
      showOnboardingFeedback("Por favor, preencha seu nome completo.", "error");
      return false;
    }
    if (isNaN(age) || age < 14 || age > 120) {
      showOnboardingFeedback("Por favor, insira uma idade válida (entre 14 e 120 anos).", "error");
      return false;
    }
    if (!occ) {
      showOnboardingFeedback("Por favor, informe sua profissão ou área de atuação.", "error");
      return false;
    }
  } else if (currentOnboardingStep === 2) {
    const income = parseFloat(document.getElementById("obIncome")?.value);
    if (isNaN(income) || income < 0) {
      showOnboardingFeedback("Por favor, informe sua renda líquida mensal.", "error");
      return false;
    }
  } else if (currentOnboardingStep === 3) {
    const fixed = parseFloat(document.getElementById("obFixedExpenses")?.value);
    const variable = parseFloat(document.getElementById("obVariableExpenses")?.value);
    if (isNaN(fixed) || fixed < 0) {
      showOnboardingFeedback("Por favor, informe seus gastos fixos essenciais.", "error");
      return false;
    }
    if (isNaN(variable) || variable < 0) {
      showOnboardingFeedback("Por favor, informe uma estimativa para gastos variáveis.", "error");
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
  const selectedAssets = Array.from(assetCheckboxes).map(cb => cb.value);
  const selectedRisk = document.querySelector('input[name="obRiskTolerance"]:checked')?.value || "moderado";

  return {
    is_draft: isDraft,
    name: document.getElementById("obName")?.value.trim() || "",
    age: parseInt(document.getElementById("obAge")?.value, 10) || null,
    occupation: document.getElementById("obOccupation")?.value.trim() || "",
    monthly_income: parseFloat(document.getElementById("obIncome")?.value) || 0.0,
    extra_income: parseFloat(document.getElementById("obExtraIncome")?.value) || 0.0,
    fixed_expenses_val: parseFloat(document.getElementById("obFixedExpenses")?.value) || 0.0,
    variable_expenses_val: parseFloat(document.getElementById("obVariableExpenses")?.value) || 0.0,
    saved_amount: parseFloat(document.getElementById("obSavedAmount")?.value) || 0.0,
    saved_destination: document.getElementById("obSavedDestination")?.value || "reserva_emergencia",
    invests: document.getElementById("obInvests")?.value || "nao_interesse",
    investment_types: selectedAssets,
    risk_tolerance: selectedRisk
  };
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
