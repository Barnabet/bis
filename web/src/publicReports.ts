import type { Asset, Period, Program } from "./types";

export const reportFamilies = [
  {
    value: "quarterly-revenue-v1",
    label: "Regional revenue",
    description: "Posted EUR transactions, regional tables and an explicitly reviewed selection policy.",
  },
  {
    value: "census_marts",
    label: "US Census retail headlines",
    description: "Monthly retail headlines from the Census release workbook. Includes published USD and percentage figures; remaining report content requires review.",
  },
  {
    value: "ons_retail",
    label: "ONS retail headlines",
    description: "Seven monthly headline measures from the ONS release CSV. Preserves each source vintage and published percentage scale; remaining report content requires review.",
  },
] as const;

export type PublicFamily = "census_marts" | "ons_retail";
export type ReportFamily = (typeof reportFamilies)[number]["value"];

export function sourceRole(program: Program | undefined): string {
  const contract = program?.input_contract;
  if (contract && typeof contract === "object" && "role" in contract && typeof contract.role === "string")
    return contract.role;
  return "transactions";
}

export function publicFamily(program: Program | undefined): PublicFamily | null {
  const role = sourceRole(program);
  if (role === "public_source:census_marts") return "census_marts";
  if (role === "public_source:ons_retail") return "ons_retail";
  return null;
}

export function eligibleSources(assets: Asset[], program: Program | undefined): Asset[] {
  const role = sourceRole(program);
  return assets.filter((asset) => !asset.reserved && asset.status !== "blocked"
    && Array.isArray(asset.profile?.eligible_roles) && asset.profile.eligible_roles.includes(role));
}

export function eligibleTargets(assets: Asset[], program: Program): Asset[] {
  const family = publicFamily(program);
  return assets.filter((asset) => !asset.reserved && asset.status !== "blocked"
    && Array.isArray(asset.profile?.eligible_roles) && asset.profile.eligible_roles.includes("historical_target")
    && (family ? /\.pdf$/i : /\.(docx|pdf)$/i).test(asset.filename)
    && (!asset.profile.public_family || asset.profile.public_family === family));
}

export function monthlySourcePeriod(asset: Asset | undefined, family: PublicFamily | null): Period | null {
  if (!family || asset?.profile?.public_family !== family) return null;
  const period = asset.profile.period;
  const vintage = asset.profile.vintage;
  if (typeof period !== "string" || !/^\d{4}-(0[1-9]|1[0-2])$/.test(period)
      || typeof vintage !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(vintage)) return null;
  const [year, month] = period.split("-").map(Number);
  const start = new Date(Date.UTC(year, month - 1, 1));
  const release = new Date(`${vintage}T00:00:00Z`);
  if (!Number.isFinite(release.getTime()) || release.toISOString().slice(0, 10) !== vintage
      || vintage.slice(0, 7) <= period) return null;
  const day = (value: Date) => value.toISOString().slice(0, 10);
  return {
    label: new Intl.DateTimeFormat("en-GB", { month: "long", year: "numeric", timeZone: "UTC" }).format(start),
    start: day(start),
    end_exclusive: day(new Date(Date.UTC(year, month, 1))),
    comparison: { start: day(new Date(Date.UTC(year, month - 2, 1))), end_exclusive: day(start) },
    timezone: "UTC",
    as_of: `${vintage}T23:59:59+00:00`,
  };
}

export function sourceUploadBody(file: File, family: PublicFamily | ""): FormData {
  const body = new FormData();
  body.append("file", file);
  if (family) body.append("public_family", family);
  return body;
}
