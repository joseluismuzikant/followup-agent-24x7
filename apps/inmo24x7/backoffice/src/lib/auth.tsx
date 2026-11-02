import { createContext, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";

import { authAdapter } from "./auth-adapter";
import type { AuthSession } from "./auth-adapter";

interface AuthState {
  session: AuthSession | null;
  loading: boolean;
  signOut: () => Promise<void>;
}

const AuthContext = createContext<AuthState>({
  session: null,
  loading: true,
  signOut: async () => {},
});

const signOut = () => authAdapter().signOut();

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<AuthSession | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const adapter = authAdapter();
    let active = true;
    void adapter.getSession().then((current) => {
      if (active) {
        setSession(current);
        setLoading(false);
      }
    });
    const unsubscribe = adapter.subscribe(setSession);
    return () => {
      active = false;
      unsubscribe();
    };
  }, []);

  const value = useMemo(() => ({ session, loading, signOut }), [session, loading]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  return useContext(AuthContext);
}
