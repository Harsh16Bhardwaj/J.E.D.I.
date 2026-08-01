import type { User } from "./api";

export type PublicSessionMode = "loading" | "authenticated" | "anonymous";

export function publicSessionMode(
  user: User | undefined,
  isLoading: boolean,
): PublicSessionMode {
  if (user) return "authenticated";
  return isLoading ? "loading" : "anonymous";
}
