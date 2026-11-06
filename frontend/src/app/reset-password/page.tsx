import type { Metadata } from "next";
import { PasswordRecovery } from "@/components/password-recovery";

export const metadata: Metadata = { title: "Reset password", referrer: "no-referrer" };

export default function ResetPasswordPage() {
  return <PasswordRecovery reset />;
}
