export const TUTORIAL_COMPLETE_KEY = "jedi:tutorial-complete:v1";
export const TUTORIAL_COMPLETE_EVENT = "jedi:tutorial-complete";

type TutorialStorage = Pick<Storage, "getItem" | "setItem">;

export function hasCompletedTutorial(storage: TutorialStorage | null): boolean {
  if (!storage) return false;
  try {
    return storage.getItem(TUTORIAL_COMPLETE_KEY) === "1";
  } catch {
    return false;
  }
}

export function persistTutorialComplete(storage: TutorialStorage | null): void {
  if (!storage) return;
  try {
    storage.setItem(TUTORIAL_COMPLETE_KEY, "1");
  } catch {
    // Storage may be unavailable. The tutorial itself remains accessible.
  }
}

export function markTutorialCompleteInBrowser(): void {
  if (typeof window === "undefined") return;
  persistTutorialComplete(window.localStorage);
  window.dispatchEvent(new Event(TUTORIAL_COMPLETE_EVENT));
}
