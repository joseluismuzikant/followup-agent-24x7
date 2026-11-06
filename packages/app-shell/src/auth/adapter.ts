import type { Session, SupabaseClient } from "@supabase/supabase-js";

import { onDevSessionChange, readDevToken, signOutDev } from "./dev-session";
import type { AuthMode } from "./mode";

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

export function supabaseAdapter(getSupabase: () => SupabaseClient): AuthAdapter {
  return {
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
}

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

export function pickAdapter(mode: AuthMode, getSupabase: () => SupabaseClient): AuthAdapter {
  return mode === "dev" ? devAdapter : supabaseAdapter(getSupabase);
}
