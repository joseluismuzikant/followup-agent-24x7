const KEY = "onboardingDeferred";

/** "Terminar después" only skips the wizard for the current browser session. */
export function deferOnboarding(): void {
  try {
    sessionStorage.setItem(KEY, "1");
  } catch {
    // Storage can be unavailable (private mode); the wizard just reopens next time.
  }
}

export function resumeOnboarding(): void {
  try {
    sessionStorage.removeItem(KEY);
  } catch {
    // See deferOnboarding.
  }
}

export function isOnboardingDeferred(): boolean {
  try {
    return sessionStorage.getItem(KEY) === "1";
  } catch {
    return false;
  }
}
