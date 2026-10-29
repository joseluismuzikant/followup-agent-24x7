import { FormField, Input } from "@followup/ui";
import { useId } from "react";

interface NotificationEmailsFieldProps {
  label: string;
  value: string;
  onChange: (value: string) => void;
  disabled?: boolean;
}

export function NotificationEmailsField({
  label,
  value,
  onChange,
  disabled,
}: NotificationEmailsFieldProps) {
  const id = useId();

  return (
    <FormField
      label={label}
      htmlFor={id}
      hint="Podés poner hasta 5 emails, separados por coma."
    >
      <Input
        id={id}
        type="text"
        inputMode="email"
        value={value}
        disabled={disabled}
        onChange={(event) => onChange(event.target.value)}
        placeholder="ventas@tuinmobiliaria.com"
      />
    </FormField>
  );
}
