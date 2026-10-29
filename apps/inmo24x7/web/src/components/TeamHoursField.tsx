import type { ScheduleBlock } from "@followup/api-client-inmo24x7";
import { FormField, SegmentedControl } from "@followup/ui";

import { hoursPresets, presetForHours } from "../lib/setup";

interface TeamHoursFieldProps {
  value: ScheduleBlock[];
  onChange: (value: ScheduleBlock[]) => void;
  disabled?: boolean;
}

export function TeamHoursField({ value, onChange, disabled }: TeamHoursFieldProps) {
  const preset = presetForHours(value);

  return (
    <FormField
      label="Horario de tu equipo"
      hint={
        preset === null
          ? "Tu horario actual es personalizado. Elegí una opción para reemplazarlo."
          : undefined
      }
    >
      <SegmentedControl
        ariaLabel="Horario de tu equipo"
        options={hoursPresets.map(({ value: presetValue, label }) => ({
          value: presetValue,
          label,
        }))}
        value={preset}
        disabled={disabled}
        onChange={(next) => {
          const selected = hoursPresets.find((item) => item.value === next);
          if (selected) {
            onChange(selected.blocks.map((item) => ({ ...item })));
          }
        }}
      />
    </FormField>
  );
}
