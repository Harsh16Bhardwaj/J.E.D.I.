import type { User } from "./api";

export type PublicSessionMode = "loading" | "authenticated" | "anonymous";

export function publicSessionMode(
  user: User | undefined,
  isLoading: boolean,
): PublicSessionMode {
  if (user) return "authenticated";
  return isLoading ? "loading" : "anonymous";
}

// Existing members return here to review resume facts and manual preferences.
export function onboardingRedirect(
  user: Pick<User, "onboardingComplete"> | undefined,
  pathname: string,
): "/onboarding" | null {
  return user && !user.onboardingComplete && pathname !== "/onboarding"
    ? "/onboarding"
    : null;
}
