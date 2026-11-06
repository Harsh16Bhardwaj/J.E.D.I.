"use client";

import Link from "next/link";
import { useState, useSyncExternalStore, type FormEvent } from "react";
import { useSWRConfig } from "swr";
import { BrutalCard } from "@/components/brutal-card";
import { buttonVariants } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { apiRequest, errorSummary } from "@/lib/api";

function subscribeToHash(change: () => void) {
  window.addEventListener("hashchange", change);
  return () => window.removeEventListener("hashchange", change);
}

function readToken() {
  return new URLSearchParams(window.location.hash.slice(1)).get("token") ?? "";
}

export function PasswordRecovery({ reset = false }: { reset?: boolean }) {
  const { cache } = useSWRConfig();
  const hashToken = useSyncExternalStore(subscribeToHash, readToken, () => null);
  const token = reset && hashToken && /^[A-Za-z0-9_-]{43}$/.test(hashToken) ? hashToken : undefined;
  const [verifying, setVerifying] = useState(reset);
  const [pending, setPending] = useState(false);
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState<string>();
  const [deliveryMessage, setDeliveryMessage] = useState<string>();
  const [done, setDone] = useState<string>();

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (pending) return;
    setError(undefined);
    if (verifying && !token && !/^[A-Z2-7]{16}$/i.test(code.replace(/[ \t\r\n-]/g, ""))) {
      setError("Enter the 16-character recovery code from your email.");
      return;
    }
    if (verifying && password !== confirmPassword) {
      setError("The passwords must match.");
      return;
    }
    setPending(true);
    try {
      const result = await apiRequest<{ message: string } | undefined>(
        verifying ? "/api/auth/reset-password" : "/api/auth/forgot-password",
        {
          method: "POST",
          signal: AbortSignal.timeout(15_000),
          body: JSON.stringify(verifying
            ? { ...(token ? { token } : { email, code }), password, confirmPassword }
            : { email }),
        },
      );
      if (verifying) {
        if (token) window.history.replaceState(window.history.state, "", window.location.pathname);
        Array.from(cache.keys()).forEach((key) => cache.delete(key));
        setCode("");
        setPassword("");
        setConfirmPassword("");
        setDone("Password updated. Sign in with your new password.");
      } else {
        setDeliveryMessage(result?.message ?? "If an account exists for that email, a recovery code will be sent.");
        setVerifying(true);
      }
    } catch (error) {
      setError(errorSummary(error));
    } finally {
      setPending(false);
    }
  }

  return (
    <main className="grid min-h-screen place-items-center px-4 py-10">
      <BrutalCard className="w-full max-w-md space-y-4">
        <h1 className="text-3xl font-black">{verifying ? "Choose a new password" : "Forgot password?"}</h1>
        {done ? (
          <p role="status" className="text-sm text-muted-foreground">{done}</p>
        ) : reset && hashToken === null ? (
          <p role="status" className="text-sm text-muted-foreground">Loading recovery form…</p>
        ) : (
          <form method="post" className="space-y-4" onSubmit={submit}>
            {deliveryMessage && <p role="status" className="text-sm text-muted-foreground">{deliveryMessage}</p>}
            {!token && (
              <div>
                {!verifying && <p className="mb-3 text-sm text-muted-foreground">Enter the email you use to sign in to JEDI.</p>}
                <label htmlFor="recovery-email" className="text-sm font-semibold">Email</label>
                <Input id="recovery-email" name="email" type="email" autoComplete="email" maxLength={320} required disabled={pending} className="mt-1 min-h-11" value={email} onChange={(event) => setEmail(event.target.value)} />
              </div>
            )}
            {verifying && (
              <div className="space-y-3">
                {!token && (
                  <div>
                    <label htmlFor="recovery-code" className="text-sm font-semibold">Email recovery code</label>
                    <Input id="recovery-code" name="code" autoComplete="one-time-code" autoCapitalize="characters" spellCheck={false} minLength={16} maxLength={64} required disabled={pending} aria-describedby="recovery-code-help" className="mt-1 min-h-11" value={code} onChange={(event) => setCode(event.target.value)} />
                    <p id="recovery-code-help" className="mt-1 text-xs text-muted-foreground">Paste the 16-character code from the email. It expires in 15 minutes.</p>
                  </div>
                )}
                <div>
                  <label htmlFor="new-password" className="text-sm font-semibold">New password</label>
                  <Input id="new-password" name="password" type="password" autoComplete="new-password" minLength={8} maxLength={256} required disabled={pending} className="mt-1 min-h-11" value={password} onChange={(event) => setPassword(event.target.value)} />
                  <p className="mt-1 text-xs text-muted-foreground">Use at least 8 characters.</p>
                </div>
                <div>
                  <label htmlFor="confirm-password" className="text-sm font-semibold">Confirm new password</label>
                  <Input id="confirm-password" name="confirmPassword" type="password" autoComplete="new-password" minLength={8} maxLength={256} required disabled={pending} className="mt-1 min-h-11" value={confirmPassword} onChange={(event) => setConfirmPassword(event.target.value)} />
                </div>
              </div>
            )}
            {error && <p role="alert" className="text-sm text-coral">{error}</p>}
            <button type="submit" disabled={pending} className={buttonVariants({ className: "min-h-11" })}>
              {pending ? "Please wait…" : verifying ? "Update password" : "Email recovery code"}
            </button>
          </form>
        )}
        <div className="flex flex-wrap gap-2">
          <Link href="/login" className={buttonVariants({ variant: "outline" })}>Back to sign in</Link>
          {!done && verifying && (
            reset ? (
              <Link href="/forgot-password" className={buttonVariants({ variant: "ghost" })}>Request a new code</Link>
            ) : (
              <button type="button" disabled={pending} className={buttonVariants({ variant: "ghost" })} onClick={() => {
                setVerifying(false);
                setDeliveryMessage(undefined);
                setError(undefined);
                setCode("");
                setPassword("");
                setConfirmPassword("");
              }}>Request a new code</button>
            )
          )}
          {!done && !verifying && (
            <Link href="/reset-password" className={buttonVariants({ variant: "ghost" })}>I already have a code</Link>
          )}
        </div>
      </BrutalCard>
    </main>
  );
}
