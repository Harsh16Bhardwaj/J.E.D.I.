export const TUTORIAL_COMPLETE_KEY = "jedi:tutorial-complete:v1";
export const TUTORIAL_COMPLETE_EVENT = "jedi:tutorial-complete";
export const TUTORIAL_CHAPTERS_KEY = "jedi:tutorial-chapters:v2";

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

export function completedTutorialChapters(storage: TutorialStorage | null): Set<string> {
  const chapters = new Set<string>();
  if (hasCompletedTutorial(storage)) chapters.add("core-guide");
  try {
    const stored: unknown = JSON.parse(storage?.getItem(TUTORIAL_CHAPTERS_KEY) ?? "[]");
    if (Array.isArray(stored)) {
      for (const id of stored) if (typeof id === "string") chapters.add(id);
    }
  } catch {
    // Preserve the legacy core completion when chapter storage is unavailable.
  }
  return chapters;
}

export function completeTutorialChapter(storage: TutorialStorage | null, id: string): Set<string> {
  const chapters = completedTutorialChapters(storage);
  chapters.add(id);
  try {
    storage?.setItem(TUTORIAL_CHAPTERS_KEY, JSON.stringify([...chapters]));
  } catch {
    // A blocked storage session can still show in-memory completion.
  }
  return chapters;
}
