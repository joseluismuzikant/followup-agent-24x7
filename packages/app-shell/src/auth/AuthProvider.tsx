import { createContext, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { Navigate } from "react-router";

import type { AuthAdapter, AuthSession } from "./adapter";

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

/** `adapter` is read once, when the provider mounts. */
export function AuthProvider({
  adapter: getAdapter,
  children,
}: {
  adapter: () => AuthAdapter;
  children: ReactNode;
}) {
  const [session, setSession] = useState<AuthSession | null>(null);
  const [loading, setLoading] = useState(true);
  const [adapter] = useState(getAdapter);

  useEffect(() => {
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
  }, [adapter]);

  const value = useMemo(
    () => ({ session, loading, signOut: () => adapter.signOut() }),
    [session, loading, adapter],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  return useContext(AuthContext);
}

export function RequireAuth({ children }: { children: ReactNode }) {
  const { session, loading } = useAuth();
  if (loading) {
    return null;
  }
  if (!session) {
    return <Navigate to="/ingreso" replace />;
  }
  return <>{children}</>;
}

export function RedirectIfAuthed({ children }: { children: ReactNode }) {
  const { session, loading } = useAuth();
  if (loading) {
    return null;
  }
  if (session) {
    return <Navigate to="/" replace />;
  }
  return <>{children}</>;
}
