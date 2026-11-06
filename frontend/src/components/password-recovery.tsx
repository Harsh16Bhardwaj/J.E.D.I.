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
  const token = useSyncExternalStore(subscribeToHash, readToken, () => null);
  const [pending, setPending] = useState(false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState<string>();
  const [done, setDone] = useState<string>();
  const validToken = token !== null && /^[A-Za-z0-9_-]{43}$/.test(token);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (pending || (reset && !validToken)) return;
    setError(undefined);
    if (reset && password !== confirmPassword) {
      setError("The passwords must match.");
      return;
    }
    setPending(true);
    try {
      const result = await apiRequest<{ message: string } | undefined>(
        reset ? "/api/auth/reset-password" : "/api/auth/forgot-password",
        {
          method: "POST",
          signal: AbortSignal.timeout(15_000),
          body: JSON.stringify(reset ? { token, password, confirmPassword } : { email }),
        },
      );
      if (reset) {
        window.history.replaceState(window.history.state, "", window.location.pathname);
        Array.from(cache.keys()).forEach((key) => cache.delete(key));
        setPassword("");
        setConfirmPassword("");
        setDone("Password updated. Sign in with your new password.");
      } else {
        setDone(result?.message ?? "If an account exists for that email, a reset link will be sent.");
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
        <h1 className="text-3xl font-black">{reset ? "Choose a new password" : "Forgot password?"}</h1>
        {done ? (
          <p role="status" className="text-sm text-muted-foreground">{done}</p>
        ) : token === null ? (
          <p role="status" className="text-sm text-muted-foreground">{reset ? "Checking reset link…" : "Loading…"}</p>
        ) : reset && !validToken ? (
          <p role="alert" className="text-sm text-coral">This reset link is missing or invalid. Request a new link.</p>
        ) : (
          <form method="post" className="space-y-4" onSubmit={submit}>
            {reset ? (
              <div className="space-y-3">
                <div>
                  <label htmlFor="new-password" className="text-sm font-semibold">New password</label>
                  <Input id="new-password" name="password" type="password" autoComplete="new-password" minLength={8} maxLength={256} required className="mt-1 min-h-11" value={password} onChange={(event) => setPassword(event.target.value)} />
                  <p className="mt-1 text-xs text-muted-foreground">Use at least 8 characters.</p>
                </div>
                <div>
                  <label htmlFor="confirm-password" className="text-sm font-semibold">Confirm new password</label>
                  <Input id="confirm-password" name="confirmPassword" type="password" autoComplete="new-password" minLength={8} maxLength={256} required className="mt-1 min-h-11" value={confirmPassword} onChange={(event) => setConfirmPassword(event.target.value)} />
                </div>
              </div>
            ) : (
              <div>
                <p className="mb-3 text-sm text-muted-foreground">Enter the email you use to sign in to JEDI.</p>
                <label htmlFor="recovery-email" className="text-sm font-semibold">Email</label>
                <Input id="recovery-email" name="email" type="email" autoComplete="email" maxLength={320} required className="mt-1 min-h-11" value={email} onChange={(event) => setEmail(event.target.value)} />
              </div>
            )}
            {error && <p role="alert" className="text-sm text-coral">{error}</p>}
            <button type="submit" disabled={pending} className={buttonVariants({ className: "min-h-11" })}>
              {pending ? "Please wait…" : reset ? "Update password" : "Send reset link"}
            </button>
          </form>
        )}
        <div className="flex flex-wrap gap-2">
          <Link href="/login" className={buttonVariants({ variant: "outline" })}>Back to sign in</Link>
          {reset && !done && (
            <Link href="/forgot-password" className={buttonVariants({ variant: "ghost" })}>Request a new link</Link>
          )}
        </div>
      </BrutalCard>
    </main>
  );
}
