/** The development sign-in: the session is the token `dev:<email>` the API gives for the right
 * password (POST /auth/dev/sign-in), kept in localStorage. */

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

export function storeDevToken(token: string) {
  writeDevToken(token);
}

export function signOutDev() {
  writeDevToken(null);
}

export function onDevSessionChange(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}
