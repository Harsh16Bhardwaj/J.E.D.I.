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
  { href: "/jobs", label: "Jobs", icon: BriefcaseBusiness },
  { href: "/applications", label: "Applications", icon: ClipboardCheck },
  { href: "/learning", label: "Learning", icon: GraduationCap },
  { href: "/tutorial", label: "Tutorial", icon: BookOpenCheck, tutorial: true },
  { href: "/batches", label: "Batches", icon: Boxes },
] satisfies readonly NavigationItem[];

export const settingsNavigation = [
  { href: "/settings/group", label: "Group", icon: UsersRound },
  { href: "/settings/email", label: "Email", icon: Mail },
  { href: "/settings/profile", label: "Shared Profile", icon: UserRound, ownerOnly: true },
  { href: "/settings/models", label: "Models", icon: Sparkles, ownerOnly: true },
] satisfies readonly NavigationItem[];

export const miscNavigation = [
  { href: "/misc/training-data", label: "Training Data", icon: DatabaseZap, ownerOnly: true },
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
