import type { ReactNode } from "react";

import { cn } from "../lib/utils";

interface FormFieldProps {
  label: string;
  htmlFor?: string;
  hint?: string;
  error?: string | null;
  className?: string;
  children: ReactNode;
}

function FormField({ label, htmlFor, hint, error, className, children }: FormFieldProps) {
  return (
    <div data-slot="form-field" className={cn("flex flex-col gap-1.5", className)}>
      <label htmlFor={htmlFor} className="text-sm font-medium">
        {label}
      </label>
      {children}
      {hint ? <p className="text-xs text-muted-foreground">{hint}</p> : null}
      {error ? (
        <p className="text-sm text-destructive" role="alert">
          {error}
        </p>
      ) : null}
    </div>
  );
}

export { FormField };
