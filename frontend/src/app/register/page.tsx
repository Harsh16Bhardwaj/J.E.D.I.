"use client";

import { useEffect } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { zodResolver } from "@hookform/resolvers/zod";
import { ArrowLeft, ArrowRight, KeyRound, UsersRound } from "lucide-react";
import { motion } from "motion/react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import useSWR, { useSWRConfig } from "swr";
import { z } from "zod";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  apiRequest,
  errorSummary,
  isApiError,
  type User,
} from "@/lib/api";

const registerSchema = z
  .object({
    inviteCode: z
      .string()
      .trim()
      .regex(
        /^[A-Za-z0-9]{5,64}$/,
        "Enter the invitation or owner registration code.",
      ),
    email: z.string().trim().email("Enter a valid email address."),
    password: z.string().min(8, "Use at least eight characters.").max(256),
    confirmPassword: z.string(),
  })
  .refine((values) => values.password === values.confirmPassword, {
    path: ["confirmPassword"],
    message: "Passwords do not match.",
  });

type RegisterValues = z.infer<typeof registerSchema>;

export default function RegisterPage() {
  const router = useRouter();
  const session = useSWR<User>("/api/auth/session", {
    shouldRetryOnError: false,
  });
  const { mutate } = useSWRConfig();
  const {
    register,
    handleSubmit,
    setError,
    setValue,
    formState: { errors, isSubmitting },
  } = useForm<RegisterValues>({
    resolver: zodResolver(registerSchema),
    defaultValues: {
      inviteCode: "",
      email: "",
      password: "",
      confirmPassword: "",
    },
  });

  useEffect(() => {
    if (session.data) {
      router.replace(
        session.data.onboardingComplete ? "/dashboard" : "/onboarding",
      );
    }
  }, [router, session.data]);

  async function submit(values: RegisterValues) {
    try {
      const user = await apiRequest<User>("/api/auth/register", {
        method: "POST",
        body: JSON.stringify({
          inviteCode: values.inviteCode.toUpperCase(),
          email: values.email,
          password: values.password,
        }),
      });
      await mutate("/api/auth/session", user, { revalidate: false });
      toast.success("Account created.", {
        description: `Welcome to ${user.group?.name ?? "JEDI"}.`,
      });
      router.replace("/onboarding");
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
    <main className="grid min-h-screen lg:grid-cols-[.9fr_1.1fr]">
      <section className="flex items-center justify-center p-5 sm:p-10">
        <motion.div
          initial={{ opacity: 0, y: 18 }}
          animate={{ opacity: 1, y: 0 }}
          className="w-full max-w-md"
        >
          <Link
            href="/login"
            className="mb-10 inline-flex min-h-11 items-center gap-2 font-mono text-xs font-bold uppercase tracking-widest text-muted-foreground hover:text-acid"
          >
            <ArrowLeft className="size-4" />
            Back to login
          </Link>
          <KeyRound className="size-9 text-acid" />
          <p className="mt-7 font-mono text-xs font-bold uppercase tracking-[0.22em] text-acid">
            Invitation access
          </p>
          <h1 className="mt-3 text-5xl font-black uppercase tracking-[-0.05em]">
            Join JEDI.
          </h1>
          <p className="mt-4 text-sm leading-6 text-muted-foreground">
            Your invitation connects you to the shared ranking profile, model,
            batches, and daily dispatch.
          </p>

          <form onSubmit={handleSubmit(submit)} className="mt-9 space-y-5">
            <div>
              <label htmlFor="inviteCode" className="ops-label">
                Invitation code
              </label>
              <Input
                id="inviteCode"
                autoComplete="one-time-code"
                maxLength={64}
                className="mt-2 min-h-12 border-2 bg-card font-mono text-lg uppercase tracking-[0.35em]"
                aria-invalid={Boolean(errors.inviteCode)}
                {...register("inviteCode", {
                  onChange: (event) =>
                    setValue(
                      "inviteCode",
                      event.target.value
                        .replace(/[^a-z0-9]/gi, "")
                        .slice(0, 64)
                        .toUpperCase(),
                      { shouldValidate: true },
                    ),
                })}
              />
              {errors.inviteCode && (
                <p className="mt-2 text-sm text-coral">
                  {errors.inviteCode.message}
                </p>
              )}
            </div>
            <div>
              <label htmlFor="email" className="ops-label">Email</label>
              <Input
                id="email"
                type="email"
                autoComplete="email"
                className="mt-2 min-h-12 border-2 bg-card"
                aria-invalid={Boolean(errors.email)}
                {...register("email")}
              />
              {errors.email && <p className="mt-2 text-sm text-coral">{errors.email.message}</p>}
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              <div>
                <label htmlFor="password" className="ops-label">Password</label>
                <Input id="password" type="password" autoComplete="new-password" className="mt-2 min-h-12 border-2 bg-card" aria-invalid={Boolean(errors.password)} {...register("password")} />
                {errors.password && <p className="mt-2 text-sm text-coral">{errors.password.message}</p>}
              </div>
              <div>
                <label htmlFor="confirmPassword" className="ops-label">Confirm</label>
                <Input id="confirmPassword" type="password" autoComplete="new-password" className="mt-2 min-h-12 border-2 bg-card" aria-invalid={Boolean(errors.confirmPassword)} {...register("confirmPassword")} />
                {errors.confirmPassword && <p className="mt-2 text-sm text-coral">{errors.confirmPassword.message}</p>}
              </div>
            </div>
            {errors.root && (
              <div role="alert" className="rounded-lg border border-coral/40 bg-coral/5 p-3 text-sm text-coral">
                {errors.root.message}
              </div>
            )}
            <Button type="submit" disabled={isSubmitting} className="min-h-12 w-full bg-foreground font-mono font-black uppercase text-background hover:bg-acid">
              {isSubmitting ? "Creating account..." : "Create account"}
              {!isSubmitting && <ArrowRight className="size-4" />}
            </Button>
          </form>
        </motion.div>
      </section>

      <section className="hidden border-l border-border bg-card p-12 lg:flex lg:flex-col lg:justify-between">
        <div className="flex items-center gap-3 font-mono text-xs font-bold uppercase tracking-[0.24em] text-muted-foreground">
          <UsersRound className="size-5 text-purple" />
          One shared signal
        </div>
        <div>
          <p className="max-w-lg text-4xl font-semibold leading-tight tracking-[-0.04em]">
            The group receives one ranked view of the market, powered by the
            established JEDI preference model.
          </p>
          <div className="mt-10 grid grid-cols-3 gap-3 font-mono text-xs uppercase text-muted-foreground">
            <span className="border-t border-border pt-3">Shared batches</span>
            <span className="border-t border-border pt-3">Shared ranking</span>
            <span className="border-t border-border pt-3">Shared dispatch</span>
          </div>
        </div>
        <p className="text-sm leading-6 text-muted-foreground">
          Your own profile is saved during onboarding for the personalized v2
          model. It does not change group results today.
        </p>
      </section>
    </main>
  );
}
