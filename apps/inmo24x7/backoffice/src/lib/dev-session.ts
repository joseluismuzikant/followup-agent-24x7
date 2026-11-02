/** The development sign-in: the session is the token `dev:<email>` kept in localStorage. */

const STORAGE_KEY = "followup.devSession";
const listeners = new Set<() => void>();

export function readDevToken(): string | null {
  try {
    return window.localStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}

function writeDevToken(token: string | null) {
  try {
    if (token) {
      window.localStorage.setItem(STORAGE_KEY, token);
    } else {
      window.localStorage.removeItem(STORAGE_KEY);
    }
  } catch {
    // Storage blocked: the session just won't survive a reload.
  }
  listeners.forEach((listener) => listener());
}

export function signInDev(email: string) {
  writeDevToken(`dev:${email.trim().toLowerCase()}`);
}

export function signOutDev() {
  writeDevToken(null);
}

export function onDevSessionChange(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}
