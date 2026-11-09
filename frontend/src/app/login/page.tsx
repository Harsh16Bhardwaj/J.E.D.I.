"use client";

import { useState } from "react";
import { SignalArt, SignalMark } from "@/components/signal-art";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { zodResolver } from "@hookform/resolvers/zod";
import { ArrowLeft, ArrowRight, Eye, EyeOff, LockKeyhole } from "lucide-react";
import { motion } from "motion/react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import { useSWRConfig } from "swr";
import { z } from "zod";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  apiRequest,
  errorSummary,
  isApiError,
  safeNext,
  type User,
} from "@/lib/api";

const loginSchema = z.object({
  email: z.string().trim().email("Enter a valid email address."),
  password: z.string().min(1, "Password is required.").max(256),
});
type LoginValues = z.infer<typeof loginSchema>;

export default function LoginPage() {
  const router = useRouter();
  const [showPassword, setShowPassword] = useState(false);
  const { mutate } = useSWRConfig();
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<LoginValues>({
    resolver: zodResolver(loginSchema),
    defaultValues: { email: "", password: "" },
  });

  async function login(values: LoginValues) {
    try {
      const user = await apiRequest<User>("/api/auth/login", {
        method: "POST",
        body: JSON.stringify(values),
      });
      await mutate("/api/auth/session", user, { revalidate: false });
      toast.success("Welcome back.", { description: user.email });
      const requestedPath = new URLSearchParams(window.location.search).get(
        "next",
      );
      router.replace(
        user.onboardingComplete ? safeNext(requestedPath) : "/onboarding",
      );
    } catch (error) {
      const message = errorSummary(error);
      setError("root", { message });
      toast.error(message, {
        description:
          isApiError(error) && error.requestId
            ? `Request ${error.requestId}`
            : undefined,
      });
    }
  }

  return (
    <main className="workspace-login">
      <section className="workspace-login-story">
        <Link href="/" className="workspace-brand">
          <SignalMark className="size-9" />
          <span>JEDI.</span>
        </Link>
        <div className="workspace-login-message">
          <p className="ops-label text-acid">
            A little clarity goes a long way
          </p>
          <h2>
            Welcome to
            <br />
            your next
            <br />
            <span>chapter.</span>
          </h2>
          <SignalArt className="workspace-login-art" />
          <p>
            Find work that fits your direction.
            <br />
            Build the confidence to go for it.
          </p>
        </div>
        <p className="workspace-login-footer">
          <LockKeyhole size={13} /> Your personal workspace. Your pace.
        </p>
      </section>

      <section className="workspace-login-form">
        <motion.div
          initial={{ opacity: 0, x: 24 }}
          animate={{ opacity: 1, x: 0 }}
          className="w-full max-w-md"
        >
          <Link
            href="/"
            className="mb-10 inline-flex min-h-11 items-center gap-2 font-mono text-xs font-bold uppercase tracking-widest text-muted-foreground hover:text-acid"
          >
            <ArrowLeft className="size-4" />
            Back to JEDI
          </Link>
          <LockKeyhole className="size-9 text-acid" />
          <p className="mt-7 font-mono text-xs font-bold uppercase tracking-[0.22em] text-acid">
            Your space is waiting
          </p>
          <h1 className="mt-3 text-4xl font-medium tracking-[-0.05em] sm:text-5xl">
            Welcome back.
          </h1>
          <p className="mt-4 text-sm leading-6 text-muted-foreground">
            Use your JEDI account, or create one with a group invitation code.
          </p>

          <form onSubmit={handleSubmit(login)} className="mt-9 space-y-5">
            <div>
              <label htmlFor="email" className="ops-label">
                Email
              </label>
              <Input
                id="email"
                type="email"
                autoComplete="email"
                className="mt-2 min-h-12 bg-card"
                aria-invalid={Boolean(errors.email)}
                aria-describedby={errors.email ? "email-error" : undefined}
                {...register("email")}
              />
              {errors.email && (
                <p id="email-error" className="mt-2 text-sm text-coral">
                  {errors.email.message}
                </p>
              )}
            </div>
            <div>
              <label htmlFor="password" className="ops-label">
                Password
              </label>
              <div className="relative">
                <Input
                  id="password"
                  type={showPassword ? "text" : "password"}
                  autoComplete="current-password"
                  className="mt-2 min-h-12 bg-card"
                  aria-invalid={Boolean(errors.password)}
                  aria-describedby={
                    errors.password ? "password-error" : undefined
                  }
                  {...register("password")}
                  style={{ paddingRight: "3rem" }}
                />
                <button
                  type="button"
                  className="password-reveal"
                  onClick={() => setShowPassword((value) => !value)}
                  aria-label={showPassword ? "Hide password" : "Show password"}
                  aria-pressed={showPassword}
                >
                  {showPassword ? <EyeOff size={17} /> : <Eye size={17} />}
                </button>
              </div>
              {errors.password && (
                <p id="password-error" className="mt-2 text-sm text-coral">
                  {errors.password.message}
                </p>
              )}
            </div>
            {errors.root && (
              <div
                role="alert"
                className="border-2 border-coral bg-coral/10 p-3 text-sm text-coral"
              >
                {errors.root.message}
              </div>
            )}
            <Button
              type="submit"
              disabled={isSubmitting}
              className="min-h-12 w-full justify-between px-4"
            >
              {isSubmitting ? "Checking credentials…" : "Sign in"}
              {!isSubmitting && <ArrowRight className="size-4" />}
            </Button>
            <Link
              href="/forgot-password"
              className="block text-center text-sm font-semibold text-foreground hover:text-acid"
            >
              Forgot password?
            </Link>
          </form>
          <p className="mt-6 text-center text-sm text-muted-foreground">
            Have an invitation?{" "}
            <Link
              href="/register"
              className="font-semibold text-foreground hover:text-acid"
            >
              Create an account
            </Link>
          </p>
        </motion.div>
      </section>
    </main>
  );
}
