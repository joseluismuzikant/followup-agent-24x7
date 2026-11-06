/**
 * The account endpoints every product API has (followup_platform's account router): the
 * forced password change, the invitation link and the development sign-in. Plain fetch, so
 * the four apps share it whatever their generated client is.
 */
import { apiError } from "./api";

export interface AccountState {
  email: string;
  must_change_password: boolean;
}

export interface InvitationState {
  email: string;
  business_name: string;
  status: "valid" | "expired" | "used";
  needs_password: boolean;
}

export interface AccountApi {
  fetchAccount(): Promise<AccountState>;
  changePassword(password: string): Promise<void>;
  fetchInvitation(token: string): Promise<InvitationState>;
  /** The invited email (the page signs in with it). */
  acceptInvitation(token: string, password: string): Promise<string>;
  /** AUTH_MODE=dev only: the `dev:<email>` token for this email and password. */
  devSignIn(email: string, password: string): Promise<string>;
}

type TokenGetter = () => string | null | undefined | Promise<string | null | undefined>;

export function createAccountApi(baseUrl: string, getAccessToken: TokenGetter): AccountApi {
  const root = baseUrl.replace(/\/$/, "");

  async function call<T>(path: string, init: RequestInit = {}, auth = false): Promise<T> {
    const headers = new Headers(init.headers);
    if (init.body) {
      headers.set("Content-Type", "application/json");
    }
    if (auth) {
      const token = await getAccessToken();
      if (token) {
        headers.set("Authorization", `Bearer ${token}`);
      }
    }
    const response = await fetch(`${root}${path}`, { ...init, headers });
    if (response.status === 204) {
      return undefined as T;
    }
    const body: unknown = await response.json().catch(() => null);
    if (!response.ok) {
      throw apiError(response, body);
    }
    return body as T;
  }

  return {
    fetchAccount: () => call<AccountState>("/account", {}, true),
    changePassword: (password) =>
      call<void>("/account/password", { method: "POST", body: JSON.stringify({ password }) }, true),
    fetchInvitation: (token) => call<InvitationState>(`/invitations/${encodeURIComponent(token)}`),
    acceptInvitation: async (token, password) =>
      (
        await call<{ email: string }>("/invitations/accept", {
          method: "POST",
          body: JSON.stringify({ token, password }),
        })
      ).email,
    devSignIn: async (email, password) =>
      (
        await call<{ access_token: string }>("/auth/dev/sign-in", {
          method: "POST",
          body: JSON.stringify({ email, password }),
        })
      ).access_token,
  };
}
