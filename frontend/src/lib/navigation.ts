import type { LucideIcon } from "lucide-react";
import {
  BookOpenCheck,
  GraduationCap,
  Boxes,
  BriefcaseBusiness,
  ClipboardCheck,
  DatabaseZap,
  Mail,
  Newspaper,
  Radar,
  Sparkles,
  UserRound,
  UsersRound,
} from "lucide-react";

export type NavigationItem = {
  href: string;
  label: string;
  icon: LucideIcon;
  ownerOnly?: boolean;
  tutorial?: boolean;
};

export const primaryNavigation = [
  { href: "/dashboard", label: "Daily Feed", icon: Newspaper },
  { href: "/dashboard/personal", label: "Personal feed", icon: Sparkles },
  { href: "/jobs", label: "Jobs", icon: BriefcaseBusiness },
  { href: "/jobs/intake", label: "Resume fit", icon: Sparkles },
  { href: "/applications", label: "Applications", icon: ClipboardCheck },
  { href: "/learning", label: "Learning", icon: GraduationCap },
  { href: "/tutorial", label: "Tutorial", icon: BookOpenCheck, tutorial: true },
  { href: "/batches", label: "Batches", icon: Boxes },
  { href: "/scraper", label: "Scraper", icon: Radar, ownerOnly: true },
] satisfies readonly NavigationItem[];

export const settingsNavigation = [
  { href: "/settings/group", label: "Group", icon: UsersRound },
  { href: "/settings/email", label: "Email", icon: Mail, ownerOnly: true },
] satisfies readonly NavigationItem[];

export const miscNavigation = [
  { href: "/legacy/dashboard", label: "Shared leaderboard", icon: Newspaper },
  {
    href: "/settings/profile",
    label: "Shared Profile",
    icon: UserRound,
    ownerOnly: true,
  },
  {
    href: "/settings/models",
    label: "Models",
    icon: Sparkles,
    ownerOnly: true,
  },
  {
    href: "/misc/training-data",
    label: "Training Data",
    icon: DatabaseZap,
    ownerOnly: true,
  },
] satisfies readonly NavigationItem[];

export const allNavigation: readonly NavigationItem[] = [
  ...primaryNavigation,
  ...settingsNavigation,
  ...miscNavigation,
];

export function visibleNavigation<T extends NavigationItem>(
  items: readonly T[],
  user: { isGroupOwner: boolean } | null | undefined,
): T[] {
  return items.filter((item) => !item.ownerOnly || user?.isGroupOwner === true);
}

export function currentNavigation(
  pathname: string,
  items: readonly NavigationItem[] = allNavigation,
) {
  return items
    .filter(({ href }) => pathname === href || pathname.startsWith(`${href}/`))
    .sort((a, b) => b.href.length - a.href.length)[0];
}

export function searchNavigation(
  query: string,
  user: { isGroupOwner: boolean },
) {
  const words = query.trim().toLocaleLowerCase().split(/\s+/).filter(Boolean);
  return visibleNavigation(allNavigation, user).filter((item) => {
    const text = `${item.label} ${item.href}`.toLocaleLowerCase();
    return words.every((word) => text.includes(word));
  });
}
