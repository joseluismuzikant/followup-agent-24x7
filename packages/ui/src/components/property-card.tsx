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
  className?: string;
}

function PropertyCard({ property, resolveLink, className }: PropertyCardProps) {
  return (
    <article
      data-slot="property-card"
      className={cn("flex w-56 shrink-0 flex-col gap-1 rounded-lg border bg-card p-3", className)}
    >
      <h4 className="text-sm font-semibold leading-tight">{property.title}</h4>
      <p className="text-xs text-muted-foreground">{property.address}</p>
      <p className="text-sm font-medium">{property.price_label}</p>
      {property.over_budget ? (
        <p className="text-xs text-amber-700">Un poco más de tu presupuesto</p>
      ) : null}
      <a
        href={resolveLink ? resolveLink(property.link) : property.link}
        target="_blank"
        rel="noreferrer"
        className="mt-1 text-xs font-medium text-primary underline-offset-4 hover:underline"
      >
        Ver fotos
      </a>
    </article>
  );
}

export { PropertyCard, type PropertyCardData };
