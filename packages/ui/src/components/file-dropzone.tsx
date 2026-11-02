import { useId, useState } from "react";

import { cn } from "../lib/utils";

interface FileDropzoneProps {
  accept: string;
  onFile: (file: File) => void;
  disabled?: boolean;
  label: string;
  hint?: string;
  className?: string;
}

/** Drag a file in or click to choose one. Only the first file is used. */
function FileDropzone({ accept, onFile, disabled = false, label, hint, className }: FileDropzoneProps) {
  const inputId = useId();
  const [dragging, setDragging] = useState(false);

  return (
    <label
      htmlFor={inputId}
      data-dragging={dragging || undefined}
      onDragOver={(event) => {
        event.preventDefault();
        if (!disabled) {
          setDragging(true);
        }
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={(event) => {
        event.preventDefault();
        setDragging(false);
        const file = event.dataTransfer.files[0];
        if (file && !disabled) {
          onFile(file);
        }
      }}
      className={cn(
        "flex cursor-pointer flex-col items-center gap-1 rounded-lg border-2 border-dashed px-4 py-8 text-center text-sm transition-colors",
        dragging ? "border-primary bg-primary/5" : "border-border hover:bg-muted/50",
        disabled && "cursor-not-allowed opacity-60",
        className,
      )}
    >
      <span className="font-medium">{label}</span>
      {hint ? <span className="text-xs text-muted-foreground">{hint}</span> : null}
      <input
        id={inputId}
        type="file"
        accept={accept}
        disabled={disabled}
        className="sr-only"
        onChange={(event) => {
          const file = event.target.files?.[0];
          if (file) {
            onFile(file);
          }
          event.target.value = "";
        }}
      />
    </label>
  );
}

export { FileDropzone };
