import type { Metadata } from "next";

import { SiteTheme } from "@/components/theme-controls";
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
    "Personal job discovery, resume evidence, and a clearer next move. Built around your preferences.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body>
        <SiteTheme>
          <TooltipProvider>
            <AppShell>{children}</AppShell>
            <Toaster richColors closeButton />
          </TooltipProvider>
        </SiteTheme>
      </body>
    </html>
  );
}
