export type SalaryPeriod = "YEARLY" | "MONTHLY" | null;

type Compensation = {
  salaryMin: number | null;
  salaryMax: number | null;
  salaryCurrency: string | null;
  salaryPeriod: SalaryPeriod;
};

function compact(value: number, maximumFractionDigits = 1) {
  return new Intl.NumberFormat("en-IN", {
    maximumFractionDigits,
  }).format(value);
}

export function formatCompensationLpa(compensation: Compensation) {
  const { salaryMin, salaryMax, salaryCurrency, salaryPeriod } = compensation;
  if (salaryMin === null && salaryMax === null) return "Salary not listed";

  const values = [salaryMin, salaryMax].filter(
    (value): value is number => value !== null,
  );
  const period = salaryPeriod ?? "YEARLY";
  const code = (salaryCurrency ?? "INR").toUpperCase();
  if (code !== "INR") {
    const range = values.map((value) => compact(value, 0)).join("-");
    return `${code} ${range}/${period === "MONTHLY" ? "month" : "year"}`;
  }

  const annualValues = values.map((value) =>
    period === "MONTHLY" ? value * 12 : value,
  );
  const annual = `${annualValues
    .map((value) => compact(value / 100_000))
    .join("-")} LPA`;
  if (period === "YEARLY") return annual;

  const monthly = values
    .map((value) => `₹${compact(value / 1_000)}K`)
    .join("-");
  return `${annual} · ${monthly}/month`;
}

export function postedDaysAgo(batchCreatedAt: string, now = new Date()) {
  const created = new Date(batchCreatedAt);
  if (Number.isNaN(created.getTime())) return "Posted recently";
  const elapsed = Math.max(0, now.getTime() - created.getTime());
  const days = Math.floor(elapsed / 86_400_000);
  if (days === 0) return "Posted today";
  if (days === 1) return "Posted 1 day ago";
  return `Posted ${days} days ago`;
}
