import {
  BriefcaseBusiness,
  Boxes,
  CalendarCheck,
  Gauge,
  Home,
  Mail,
  Settings,
  SlidersHorizontal,
  Sparkles,
  UserRound,
} from "lucide-react";

export const primaryNavigation = [
  { href: "/", label: "System index", icon: Home },
  { href: "/dashboard", label: "Dashboard", icon: Gauge },
  { href: "/batches", label: "Batches", icon: Boxes },
  { href: "/jobs", label: "Jobs", icon: BriefcaseBusiness },
  { href: "/applications", label: "Applications", icon: CalendarCheck },
] as const;

export const settingsNavigation = [
  { href: "/settings", label: "Settings", icon: Settings },
  { href: "/settings/profile", label: "Profile", icon: UserRound },
  { href: "/settings/sources", label: "Sources", icon: SlidersHorizontal },
  { href: "/settings/models", label: "Models", icon: Sparkles },
  { href: "/settings/email", label: "Email", icon: Mail },
] as const;

export const allNavigation = [...primaryNavigation, ...settingsNavigation];
