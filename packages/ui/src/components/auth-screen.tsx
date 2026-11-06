import type * as React from "react";

import { cn } from "../lib/utils";
import { BrandMark } from "./brand-mark";

interface AuthScreenProps {
  productName: string;
  /** "Backoffice" under the product name, for the admin apps. */
  areaName?: string;
  title: string;
  description?: React.ReactNode;
  children: React.ReactNode;
  footer?: React.ReactNode;
  className?: string;
}

/** Sign-in, invitation and password screens: the landing's night-blue gradient and a card. */
function AuthScreen({
  productName,
  areaName,
  title,
  description,
  children,
  footer,
  className,
}: AuthScreenProps) {
  return (
    <div className="auth-backdrop flex min-h-screen flex-col items-center justify-center gap-6 px-4 py-10">
      <div className="flex items-center gap-3 text-white">
        <BrandMark name={productName} />
        <div>
          <p className="text-lg font-semibold leading-tight">{productName}</p>
          {areaName ? (
            <p className="text-xs uppercase tracking-wider text-white/70">{areaName}</p>
          ) : null}
        </div>
      </div>
      <div
        className={cn(
          "w-full max-w-md rounded-2xl border border-white/10 bg-card p-6 text-card-foreground shadow-2xl sm:p-8",
          className,
        )}
      >
        <h1 className="text-xl font-semibold tracking-tight text-brand">{title}</h1>
        {description ? (
          <div className="mt-1.5 text-sm text-muted-foreground">{description}</div>
        ) : null}
        <div className="mt-6 flex flex-col gap-4">{children}</div>
      </div>
      {footer ? <div className="text-xs text-white/70">{footer}</div> : null}
    </div>
  );
}

export { AuthScreen };
