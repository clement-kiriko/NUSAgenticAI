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

function parseDateToIso(value) {
  const raw = String(value ?? "").trim();
  if (!raw) return "";

  function toValidIso(year, month, day) {
    const normalizedYear = String(year).padStart(4, "0");
    const normalizedMonth = String(month).padStart(2, "0");
    const normalizedDay = String(day).padStart(2, "0");
    const iso = `${normalizedYear}-${normalizedMonth}-${normalizedDay}`;

    const parsed = new Date(
      Number(normalizedYear),
      Number(normalizedMonth) - 1,
      Number(normalizedDay),
    );

    const isSameDate =
      !Number.isNaN(parsed.getTime()) &&
      parsed.getFullYear() === Number(normalizedYear) &&
      parsed.getMonth() === Number(normalizedMonth) - 1 &&
      parsed.getDate() === Number(normalizedDay);

    return isSameDate ? iso : "";
  }

  if (/^\d{4}-\d{2}-\d{2}$/.test(raw)) {
    return toValidIso(raw.slice(0, 4), raw.slice(5, 7), raw.slice(8, 10));
  }

  const parts = raw.match(/\d+/g) || [];
  if (parts.length === 3) {
    const [first, second, third] = parts;

    if (first.length === 4) {
      return toValidIso(first, second, third);
    }

    if (third.length === 4) {
      return (
        toValidIso(third, second, first) ||
        toValidIso(third, first, second)
      );
    }
  }

  const digitsOnly = raw.replace(/\D/g, "");
  if (digitsOnly.length === 8) {
    return (
      toValidIso(digitsOnly.slice(0, 4), digitsOnly.slice(4, 6), digitsOnly.slice(6, 8)) ||
      toValidIso(digitsOnly.slice(4, 8), digitsOnly.slice(2, 4), digitsOnly.slice(0, 2))
    );
  }

  return "";
}

export function getTodayLocalIso() {
  const now = new Date();
  const year = now.getFullYear();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

export function normalizeTravelForm(form) {
  const normalizedStartDate = parseDateToIso(form?.start_date);
  return {
    days: form?.days ?? "4",
    budget_sgd: form?.budget_sgd ?? "3000",
    country: form?.country ?? "",
    city: form?.city ?? "",
    start_date: normalizedStartDate,
    dietary_restrictions: form?.dietary_restrictions ?? "none",
  };
}

export function validateTravelForm(form) {
  const errors = {};
  const days = String(form.days ?? "").trim();
  const budget = String(form.budget_sgd ?? "").trim();
  const country = String(form.country ?? "").trim();
  const city = String(form.city ?? "").trim();
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

  if (city && city.length < 2) {
    errors.city = "City must be at least 2 characters.";
  }

  if (!startDate) {
    errors.start_date = "Select a travel start date.";
  } else {
    const normalizedStartDate = parseDateToIso(startDate);
    if (!normalizedStartDate) {
      errors.start_date = "Select a valid date from the calendar.";
    } else if (normalizedStartDate < getTodayLocalIso()) {
      errors.start_date = "Travel start date cannot be in the past.";
    }
  }

  return errors;
}

export function buildTravelRequest(form) {
  const normalizedStartDate = parseDateToIso(form.start_date);
  return {
    days: Number.parseInt(String(form.days).trim(), 10),
    budget_sgd: Number.parseFloat(String(form.budget_sgd).trim()),
    country: String(form.country ?? "").trim(),
    city: String(form.city ?? "").trim(),
    start_date: normalizedStartDate,
    dietary_restrictions: String(form.dietary_restrictions ?? "").trim() || "none",
  };
}
