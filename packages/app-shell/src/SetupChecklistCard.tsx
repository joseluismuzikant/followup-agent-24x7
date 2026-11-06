import { Button, ChecklistCard } from "@followup/ui";
import { Link, useNavigate } from "react-router";

import { resumeOnboarding } from "./onboarding-deferred";

export interface ChecklistLike {
  items: { key: string; done: boolean }[];
  ready_count: number;
  total: number;
}

export interface SetupChecklistCardProps {
  checklist: ChecklistLike;
  /** The product's label (and link) for each item key. */
  labels: Record<string, { label: string; href?: string }>;
  /** Show "Continuar configuración" while the wizard is unfinished. */
  wizardUnfinished: boolean;
  title?: string;
}

/** Inicio's "Te falta poco" card, for any product. */
export function SetupChecklistCard({
  checklist,
  labels,
  wizardUnfinished,
  title = "Te falta poco para dejarlo completo",
}: SetupChecklistCardProps) {
  const navigate = useNavigate();

  return (
    <ChecklistCard
      className="max-w-xl"
      title={title}
      progressLabel={`${checklist.ready_count} de ${checklist.total} listos`}
      items={checklist.items.map((item) => ({
        key: item.key,
        done: item.done,
        label: labels[item.key]?.label ?? item.key,
        href: labels[item.key]?.href,
      }))}
      renderLink={(item, children) => (
        <Link to={item.href ?? "/"} className="text-primary underline-offset-4 hover:underline">
          {children}
        </Link>
      )}
      footer={
        wizardUnfinished ? (
          <Button
            variant="outline"
            className="self-start"
            onClick={() => {
              resumeOnboarding();
              navigate("/onboarding");
            }}
          >
            Continuar configuración
          </Button>
        ) : null
      }
    />
  );
}
