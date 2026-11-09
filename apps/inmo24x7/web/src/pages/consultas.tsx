import type { InboxTab } from "@followup/api-client-inmo24x7";
import { Button, LG_UP, useMediaQuery } from "@followup/ui";
import { useQuery } from "@tanstack/react-query";
import { useEffect } from "react";
import { useLocation, useNavigate, useSearchParams } from "react-router";

import { fetchMe } from "../api/me";
import { InboxList } from "../components/inbox/InboxList";
import { LeadPanel } from "../components/inbox/LeadPanel";
import { canActOnLeads } from "../lib/leads";

const TABS: readonly InboxTab[] = ["attention", "visits", "all"];

function tabFrom(value: string | null): InboxTab {
  return TABS.includes(value as InboxTab) ? (value as InboxTab) : "attention";
}

/** Consultas (S6): tabs, search and export on the left; the selected lead on the right. The
 * URL keeps the tab, the search and the lead (the new-lead email links to ?lead=<id>).
 * Below `lg` one pane at a time: the list, or the lead with a way back to it. */
export function ConsultasPage() {
  const wide = useMediaQuery(LG_UP);
  const location = useLocation();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const tab = tabFrom(params.get("tab"));
  const search = params.get("q") ?? "";
  const selected = params.get("lead");
  const meQuery = useQuery({ queryKey: ["me"], queryFn: fetchMe });
  const canAct = meQuery.data ? canActOnLeads(meQuery.data.profile.role) : false;

  // A lead opened on a phone starts at its top, not where the list was scrolled to.
  useEffect(() => {
    if (!wide && selected) {
      window.scrollTo?.({ top: 0 });
    }
  }, [wide, selected]);

  function update(changes: Record<string, string | null>, push = false) {
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
      // On a phone opening a lead is a new history entry, so the system back gesture returns
      // to the list.
      push ? { state: { fromList: true } } : { replace: true },
    );
  }

  function backToList() {
    if ((location.state as { fromList?: boolean } | null)?.fromList) {
      void navigate(-1);
    } else {
      update({ lead: null });
    }
  }

  const list = (
    <InboxList
      tab={tab}
      search={search}
      selected={selected}
      onTabChange={(next) => update({ tab: next })}
      onSearchChange={(next) => update({ q: next || null })}
      onSelect={(id) => update({ lead: id }, !wide)}
    />
  );

  if (!wide) {
    return selected ? (
      <div className="flex flex-col gap-3">
        <Button variant="ghost" className="-ml-2 self-start" onClick={backToList}>
          <span aria-hidden="true">←</span> Volver a Consultas
        </Button>
        <LeadPanel key={selected} leadId={selected} canAct={canAct} />
      </div>
    ) : (
      list
    );
  }

  return (
    <div className="grid gap-4 lg:grid-cols-[minmax(0,22rem)_minmax(0,1fr)]">
      {list}
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
