export const DIETARY_OPTIONS = [
  { value: "none", label: "None" },
  { value: "vegetarian", label: "Vegetarian" },
  { value: "vegan", label: "Vegan" },
  { value: "halal", label: "Halal" },
  { value: "kosher", label: "Kosher" },
  { value: "gluten-free", label: "Gluten-Free" },
];

function isBlank(value) {
  return String(value ?? "").trim() === "";
}

function isIsoDate(value) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const parsed = new Date(`${value}T00:00:00`);
  return !Number.isNaN(parsed.getTime()) && parsed.toISOString().slice(0, 10) === value;
}

export function getTodayLocalIso() {
  const now = new Date();
  const year = now.getFullYear();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

export function normalizeTravelForm(form) {
  return {
    days: form?.days ?? "4",
    budget_sgd: form?.budget_sgd ?? "3000",
    country: form?.country ?? "",
    start_date: form?.start_date ?? "",
    dietary_restrictions: form?.dietary_restrictions ?? "none",
  };
}

export function validateTravelForm(form) {
  const errors = {};
  const days = String(form.days ?? "").trim();
  const budget = String(form.budget_sgd ?? "").trim();
  const country = String(form.country ?? "").trim();
  const startDate = String(form.start_date ?? "").trim();

  if (isBlank(days)) {
    errors.days = "Enter the number of travel days.";
  } else if (!/^\d+$/.test(days)) {
    errors.days = "Travel days must be a whole number.";
  } else {
    const numericDays = Number(days);
    if (numericDays < 1) {
      errors.days = "Travel days must be at least 1.";
    } else if (numericDays > 365) {
      errors.days = "Travel days must be 365 or fewer.";
    }
  }

  if (isBlank(budget)) {
    errors.budget_sgd = "Enter your total budget in SGD.";
  } else if (!/^\d+(\.\d{1,2})?$/.test(budget)) {
    errors.budget_sgd = "Budget must be a valid amount.";
  } else if (Number(budget) <= 0) {
    errors.budget_sgd = "Budget must be greater than 0.";
  }

  if (!country) {
    errors.country = "Enter the country you want to visit.";
  } else if (country.length < 2) {
    errors.country = "Country must be at least 2 characters.";
  }

  if (!startDate) {
    errors.start_date = "Select a travel start date.";
  } else if (!isIsoDate(startDate)) {
    errors.start_date = "Use a valid date in YYYY-MM-DD format.";
  } else if (startDate < getTodayLocalIso()) {
    errors.start_date = "Travel start date cannot be in the past.";
  }

  return errors;
}

export function buildTravelRequest(form) {
  return {
    days: Number.parseInt(String(form.days).trim(), 10),
    budget_sgd: Number.parseFloat(String(form.budget_sgd).trim()),
    country: String(form.country ?? "").trim(),
    start_date: String(form.start_date ?? "").trim(),
    dietary_restrictions: String(form.dietary_restrictions ?? "").trim() || "none",
  };
}
