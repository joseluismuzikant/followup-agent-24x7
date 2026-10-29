import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { fetchMe } from "../api/me";
import { fetchOnboarding } from "../api/onboarding";
import { deferOnboarding, resumeOnboarding } from "../lib/onboarding-deferred";
import { me, onboardingState } from "../test-fixtures";
import { ResumeOnboarding } from "./ResumeOnboarding";

vi.mock("../api/me", () => ({ fetchMe: vi.fn() }));
vi.mock("../api/onboarding", () => ({ fetchOnboarding: vi.fn() }));

function renderPanel() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/"]}>
        <Routes>
          <Route path="/onboarding" element={<div>Wizard</div>} />
          <Route
            path="/"
            element={
              <ResumeOnboarding>
                <div>Panel</div>
              </ResumeOnboarding>
            }
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("ResumeOnboarding", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    resumeOnboarding();
    vi.mocked(fetchMe).mockResolvedValue(me());
  });

  it("opens the wizard when onboarding is unfinished", async () => {
    vi.mocked(fetchOnboarding).mockResolvedValue(onboardingState("try"));
    renderPanel();
    expect(await screen.findByText("Wizard")).toBeTruthy();
  });

  it("lets the user into the panel after Terminar después", async () => {
    deferOnboarding();
    vi.mocked(fetchOnboarding).mockResolvedValue(onboardingState("try"));
    renderPanel();
    expect(await screen.findByText("Panel")).toBeTruthy();
  });

  it("does nothing once onboarding is finished", async () => {
    vi.mocked(fetchOnboarding).mockResolvedValue(onboardingState("done"));
    renderPanel();
    expect(await screen.findByText("Panel")).toBeTruthy();
  });

  it("never sends viewers to the wizard", async () => {
    vi.mocked(fetchMe).mockResolvedValue(me("viewer"));
    vi.mocked(fetchOnboarding).mockResolvedValue(onboardingState("agent"));
    renderPanel();
    expect(await screen.findByText("Panel")).toBeTruthy();
  });

  it("does not block the panel if onboarding cannot be loaded", async () => {
    vi.mocked(fetchOnboarding).mockRejectedValue(new Error("boom"));
    renderPanel();
    expect(await screen.findByText("Panel")).toBeTruthy();
  });
});
