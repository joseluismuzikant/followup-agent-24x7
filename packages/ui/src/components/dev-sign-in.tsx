import { useId, useState } from "react";

import { Button } from "./button";
import { Input } from "./input";

interface DevSignInProps {
  onSignIn: (email: string) => void;
}

/** Local development sign-in (AUTH_MODE=dev). Never rendered in a production build. */
function DevSignIn({ onSignIn }: DevSignInProps) {
  const inputId = useId();
  const [email, setEmail] = useState("");
  const [error, setError] = useState<string | null>(null);

  return (
    <form
      aria-label="Modo desarrollo"
      className="flex flex-col gap-2 rounded-md border-2 border-dashed border-amber-500 bg-amber-50 p-3 text-amber-950"
      onSubmit={(event) => {
        event.preventDefault();
        const value = email.trim().toLowerCase();
        if (!/^[^@\s:]+@[^@\s:]+\.[^@\s:]+$/.test(value)) {
          setError("Ingresá un email válido.");
          return;
        }
        setError(null);
        onSignIn(value);
      }}
    >
      <p className="text-sm font-semibold">Modo desarrollo</p>
      <p className="text-xs">Entrás con cualquier email, sin contraseña. Solo para pruebas locales.</p>
      <label htmlFor={inputId} className="text-sm font-medium">
        Email de prueba
      </label>
      <Input
        id={inputId}
        type="email"
        value={email}
        placeholder="dueno@inmobiliariasur.test"
        onChange={(event) => setEmail(event.target.value)}
      />
      {error ? (
        <p className="text-sm text-destructive" role="alert">
          {error}
        </p>
      ) : null}
      <Button type="submit" variant="outline">
        Entrar
      </Button>
    </form>
  );
}

export { DevSignIn };
