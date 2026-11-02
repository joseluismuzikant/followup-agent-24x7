import type { Session } from "@supabase/supabase-js";

import { authMode } from "./auth-mode";
import { onDevSessionChange, readDevToken, signOutDev } from "./dev-session";
import { getSupabase } from "./supabase";

export interface AuthSession {
  accessToken: string;
  email: string;
}

/** What AuthProvider needs from a sign-in method, so pages don't care which one is active. */
export interface AuthAdapter {
  getSession(): Promise<AuthSession | null>;
  subscribe(onChange: (session: AuthSession | null) => void): () => void;
  signOut(): Promise<void>;
}

function fromSupabase(session: Session | null): AuthSession | null {
  return session ? { accessToken: session.access_token, email: session.user.email ?? "" } : null;
}

export const supabaseAdapter: AuthAdapter = {
  async getSession() {
    const { data } = await getSupabase().auth.getSession();
    return fromSupabase(data.session);
  },
  subscribe(onChange) {
    const { data } = getSupabase().auth.onAuthStateChange((_event, session) =>
      onChange(fromSupabase(session)),
    );
    return () => data.subscription.unsubscribe();
  },
  async signOut() {
    await getSupabase().auth.signOut();
  },
};

function devSession(): AuthSession | null {
  const token = readDevToken();
  return token ? { accessToken: token, email: token.slice("dev:".length) } : null;
}

export const devAdapter: AuthAdapter = {
  async getSession() {
    return devSession();
  },
  subscribe(onChange) {
    return onDevSessionChange(() => onChange(devSession()));
  },
  async signOut() {
    signOutDev();
  },
};

export function authAdapter(): AuthAdapter {
  return authMode === "dev" ? devAdapter : supabaseAdapter;
}

export async function getAccessToken(): Promise<string | null> {
  return (await authAdapter().getSession())?.accessToken ?? null;
}
