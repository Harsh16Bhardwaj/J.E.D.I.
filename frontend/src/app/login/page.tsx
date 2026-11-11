"use client";

import Image from "next/image";
import { CareerEngraving } from "@/components/career-engraving";
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
    <main className="newspaper-login">
      <section className="newspaper-login-cover">
        <div className="newspaper-login-masthead">
          <Link
            href="/"
            className="flex items-center gap-2 font-black tracking-tight"
          >
            <Image src="/logo.png" alt="" width={30} height={34} />
            JEDI/
          </Link>
          <span>THE DAILY SIGNAL</span>
        </div>
        <div className="newspaper-login-story">
          <p className="newspaper-kicker">CAREERS / YOUR PERSONAL EDITION</p>
          <h2>
            A new chapter.
            <br />
            <em>A clearer direction.</em>
          </h2>
          <figure>
            <CareerEngraving />
            <figcaption>
              FIELD NOTES / OPPORTUNITIES WORTH A CLOSER LOOK
            </figcaption>
          </figure>
          <p>
            Find your next opportunity.
            <br />
            Give your experience a place to go.
          </p>
        </div>
        <div className="newspaper-login-foot">
          <span>Discover</span>
          <span>Compare</span>
          <span>Make your move ↗</span>
        </div>
      </section>

      <section className="newspaper-login-form">
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
            MEMBER SIGN-IN
          </p>
          <h1 className="newspaper-login-title">Welcome back.</h1>
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
                {...register("email")}
              />
              {errors.email && (
                <p className="mt-2 text-sm text-coral">
                  {errors.email.message}
                </p>
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
                className="mt-2 min-h-12 bg-card"
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
