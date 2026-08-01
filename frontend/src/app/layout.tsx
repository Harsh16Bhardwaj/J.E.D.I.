import type { Metadata } from "next";

import { AppShell } from "@/components/app-shell";
import { Toaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";

import "./globals.css";

export const metadata: Metadata = {
  title: {
    default: "JEDI : Job Evaluation & Delivery Intelligence ",
    template: "%s · JEDI",
  },
  description:
    "An invite-only daily job feed and model-ranked opportunity leaderboard.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className="dark">
      <body>
        <TooltipProvider>
          <AppShell>{children}</AppShell>
          <Toaster richColors closeButton />
        </TooltipProvider>
      </body>
    </html>
  );
}
