import { cn } from "../lib/utils";

/** The product's initial on the product's gradient square (inmo24x7: green to navy). */
function BrandMark({ name, className }: { name: string; className?: string }) {
  return (
    <div
      aria-hidden="true"
      className={cn(
        "brand-gradient grid size-10 shrink-0 place-items-center rounded-xl text-lg font-bold text-white shadow-[0_8px_25px_var(--highlight-glow)]",
        className,
      )}
    >
      {name.slice(0, 1).toUpperCase()}
    </div>
  );
}

export { BrandMark };
