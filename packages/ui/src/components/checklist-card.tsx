import type { ReactNode } from "react";

import { cn } from "../lib/utils";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "./card";

interface ChecklistItem {
  key: string;
  label: string;
  done: boolean;
  /** Where a pending item leads. Done items are never links. */
  href?: string;
}

interface ChecklistCardProps {
  title: string;
  description?: string;
  /** Short progress text such as "3 de 5 listos". */
  progressLabel: string;
  items: readonly ChecklistItem[];
  /** Lets the app render its router link for pending items. */
  renderLink?: (item: ChecklistItem, children: ReactNode) => ReactNode;
  footer?: ReactNode;
  className?: string;
}

function ChecklistCard({
  title,
  description,
  progressLabel,
  items,
  renderLink,
  footer,
  className,
}: ChecklistCardProps) {
  return (
    <Card data-slot="checklist-card" className={className}>
      <CardHeader>
        <div className="flex items-center justify-between gap-4">
          <CardTitle>{title}</CardTitle>
          <span className="text-sm font-medium text-muted-foreground">{progressLabel}</span>
        </div>
        {description ? <CardDescription>{description}</CardDescription> : null}
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <ul className="flex flex-col gap-2">
          {items.map((item) => (
            <li key={item.key} className="flex items-center gap-2 text-sm">
              <span
                aria-hidden="true"
                className={cn(
                  "flex size-5 items-center justify-center rounded-full border text-xs",
                  item.done && "border-primary bg-primary text-primary-foreground",
                )}
              >
                {item.done ? "✓" : ""}
              </span>
              {item.done || !item.href ? (
                <span className={cn(item.done && "text-muted-foreground")}>
                  {item.label}
                  {item.done ? <span className="sr-only"> (listo)</span> : null}
                </span>
              ) : renderLink ? (
                renderLink(item, item.label)
              ) : (
                <a href={item.href} className="text-primary underline-offset-4 hover:underline">
                  {item.label}
                </a>
              )}
            </li>
          ))}
        </ul>
        {footer}
      </CardContent>
    </Card>
  );
}

export { ChecklistCard, type ChecklistItem };
