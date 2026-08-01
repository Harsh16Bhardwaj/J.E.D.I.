"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { zodResolver } from "@hookform/resolvers/zod";
import { ArrowLeft, ArrowRight, LockKeyhole } from "lucide-react";
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
      const requestedPath = new URLSearchParams(window.location.search).get("next");
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
    <main className="grid min-h-screen overflow-hidden lg:grid-cols-[1.15fr_.85fr]">
      <section className="hidden border-r-2 border-foreground bg-acid p-10 text-background lg:flex lg:flex-col lg:justify-between">
        <Link href="/" className="font-mono text-sm font-black tracking-[0.28em]">
          JEDI/
        </Link>
        <motion.div
          initial={{ opacity: 0, y: 28 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.45 }}
        >
          <p className="font-mono text-xs font-bold uppercase tracking-[0.25em]">
            Private access only
          </p>
          <h1 className="mt-5 text-[clamp(4rem,8vw,8rem)] font-black uppercase leading-[0.78] tracking-[-0.08em]">
            Less noise.
            <br />
            Better bets.
          </h1>
        </motion.div>
        <p className="max-w-md text-sm font-bold leading-6">
          Your session lives in a signed HttpOnly cookie. The browser never
          stores your password or exposes the token to JavaScript.
        </p>
      </section>

      <section className="flex items-center justify-center p-5 sm:p-10">
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
            Back to system
          </Link>
          <LockKeyhole className="size-9 text-acid" />
          <p className="mt-7 font-mono text-xs font-bold uppercase tracking-[0.22em] text-acid">
            Authenticate
          </p>
          <h2 className="mt-3 text-5xl font-black uppercase tracking-[-0.05em]">
            Enter JEDI.
          </h2>
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
                className="mt-2 min-h-12 border-2 bg-card"
                aria-invalid={Boolean(errors.email)}
                {...register("email")}
              />
              {errors.email && (
                <p className="mt-2 text-sm text-coral">{errors.email.message}</p>
              )}
            </div>
            <div>
              <label htmlFor="password" className="ops-label">
                Password
              </label>
              <Input
                id="password"
                type="password"
                autoComplete="current-password"
                className="mt-2 min-h-12 border-2 bg-card"
                aria-invalid={Boolean(errors.password)}
                {...register("password")}
              />
              {errors.password && (
                <p className="mt-2 text-sm text-coral">
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
              className="min-h-12 w-full rounded-lg border border-border bg-foreground font-mono font-black uppercase text-background hover:bg-acid"
            >
              {isSubmitting ? "Checking credentials…" : "Open command center"}
              {!isSubmitting && <ArrowRight className="size-4" />}
            </Button>
          </form>
          <p className="mt-6 text-center text-sm text-muted-foreground">
            Have an invitation?{" "}
            <Link href="/register" className="font-semibold text-foreground hover:text-acid">
              Create an account
            </Link>
          </p>
        </motion.div>
      </section>
    </main>
  );
}
