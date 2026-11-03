import type { InboxTab } from "@followup/api-client-inmo24x7";
import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "react-router";

import { fetchMe } from "../api/me";
import { InboxList } from "../components/inbox/InboxList";
import { LeadPanel } from "../components/inbox/LeadPanel";
import { canActOnLeads } from "../lib/leads";

const TABS: readonly InboxTab[] = ["attention", "visits", "all"];

function tabFrom(value: string | null): InboxTab {
  return TABS.includes(value as InboxTab) ? (value as InboxTab) : "attention";
}

/** Consultas (S6): tabs, search and export on the left; the selected lead on the right. The
 * URL keeps the tab, the search and the lead (the new-lead email links to ?lead=<id>). */
export function ConsultasPage() {
  const [params, setParams] = useSearchParams();
  const tab = tabFrom(params.get("tab"));
  const search = params.get("q") ?? "";
  const selected = params.get("lead");
  const meQuery = useQuery({ queryKey: ["me"], queryFn: fetchMe });
  const canAct = meQuery.data ? canActOnLeads(meQuery.data.profile.role) : false;

  function update(changes: Record<string, string | null>) {
    setParams(
      (current) => {
        const next = new URLSearchParams(current);
        for (const [key, value] of Object.entries(changes)) {
          if (value) {
            next.set(key, value);
          } else {
            next.delete(key);
          }
        }
        return next;
      },
      { replace: true },
    );
  }

  return (
    <div className="grid gap-4 lg:grid-cols-[minmax(0,22rem)_minmax(0,1fr)]">
      <InboxList
        tab={tab}
        search={search}
        selected={selected}
        onTabChange={(next) => update({ tab: next })}
        onSearchChange={(next) => update({ q: next || null })}
        onSelect={(id) => update({ lead: id })}
      />
      {selected ? (
        <LeadPanel key={selected} leadId={selected} canAct={canAct} />
      ) : (
        <p className="hidden self-center text-center text-sm text-muted-foreground lg:block">
          Elegí una consulta para ver la conversación.
        </p>
      )}
    </div>
  );
}
