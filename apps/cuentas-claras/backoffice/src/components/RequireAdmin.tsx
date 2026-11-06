import { RequireAdmin as ShellRequireAdmin } from "@followup/app-shell";
import type { ReactNode } from "react";

import { account } from "../api/client";
import { fetchMe } from "../api/me";
import { useAuth } from "../lib/auth";
import { authMode } from "../lib/auth-mode";
import { getSupabase } from "../lib/supabase";

export function RequireAdmin({ children }: { children: ReactNode }) {
  return (
    <ShellRequireAdmin
      productName="Cuentas Claras"
      fetchMe={fetchMe}
      account={account}
      authMode={authMode}
      getSupabase={getSupabase}
      useAuth={useAuth}
    >
      {children}
    </ShellRequireAdmin>
  );
}
