import { cn } from "../lib/utils";

interface PropertyCardData {
  id: string;
  title: string;
  address: string;
  price_label: string;
  link: string;
  over_budget: boolean;
}

interface PropertyCardProps {
  property: PropertyCardData;
  /** Turns the card's link into a full URL, e.g. when the app runs on another origin. */
  resolveLink?: (link: string) => string;
  /** Makes the card a button that picks it (like a visit slot). "Ver fotos" never picks. */
  onChoose?: () => void;
  disabled?: boolean;
  className?: string;
}

function PropertyCard({ property, resolveLink, onChoose, disabled, className }: PropertyCardProps) {
  const details = (
    <>
      <span className="text-sm font-semibold leading-tight">{property.title}</span>
      <span className="text-xs text-muted-foreground">{property.address}</span>
      <span className="text-sm font-medium">{property.price_label}</span>
      {property.over_budget ? (
        <span className="text-xs text-amber-700">Un poco más de tu presupuesto</span>
      ) : null}
    </>
  );
  return (
    <article
      data-slot="property-card"
      className={cn(
        "flex w-56 shrink-0 flex-col rounded-lg border bg-card transition-colors",
        onChoose && !disabled && "hover:border-primary has-[button:focus-visible]:border-primary",
        className,
      )}
    >
      {onChoose ? (
        <button
          type="button"
          aria-label={`Elegir ${property.title}`}
          disabled={disabled}
          onClick={onChoose}
          className={cn(
            "flex flex-col gap-1 rounded-t-lg p-3 pb-1 text-left outline-none",
            "hover:bg-muted/60 focus-visible:ring-2 focus-visible:ring-ring",
            "disabled:cursor-not-allowed disabled:opacity-60",
          )}
        >
          {details}
        </button>
      ) : (
        <div className="flex flex-col gap-1 p-3 pb-1">{details}</div>
      )}
      <a
        href={resolveLink ? resolveLink(property.link) : property.link}
        target="_blank"
        rel="noreferrer"
        className="mx-3 mb-3 mt-1 self-start text-xs font-medium text-primary underline-offset-4 hover:underline"
      >
        Ver fotos
      </a>
    </article>
  );
}

export { PropertyCard, type PropertyCardData };
