// public/widget.js, run in jsdom: the button, its wa.me link and the text Sofía reads
// (the same pattern as properties/domain/reference.py in the API).
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import SOURCE from "../public/widget.js?raw";

const CONFIG = {
  agency_name: "Inmobiliaria Sur",
  phone: "5491155550000",
  color: "#1e3a8a",
  text_color: "#ffffff",
  position: "left",
  label: "Consultar por WhatsApp",
};

async function load(config: unknown = CONFIG, ok = true) {
  const fetchMock = vi.fn().mockResolvedValue({ ok, json: () => Promise.resolve(config) });
  vi.stubGlobal("fetch", fetchMock);
  const script = document.createElement("script");
  script.setAttribute("src", "https://app.inmo24x7.com/widget.js");
  script.setAttribute("data-agencia", "AbC123xyz");
  document.body.appendChild(script);
  Object.defineProperty(document, "currentScript", { value: script, configurable: true });
  new Function(SOURCE)();
  await new Promise((done) => setTimeout(done, 0));
  await new Promise((done) => setTimeout(done, 0));
  return { fetchMock, button: document.querySelector<HTMLAnchorElement>('a[href^="https://wa.me/"]') };
}

function text(button: HTMLAnchorElement | null): string {
  return decodeURIComponent(new URL(button!.href).searchParams.get("text") ?? "");
}

describe("widget.js", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
    document.title = "Depto 2 amb en Palermo | Inmobiliaria Sur";
    delete (window as unknown as Record<string, unknown>).__inmo24x7Widget;
    window.history.replaceState({}, "", "/");
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("reads only its public settings from its own host, without cookies", async () => {
    const { fetchMock, button } = await load();

    expect(fetchMock).toHaveBeenCalledWith("https://app.inmo24x7.com/widget/v1/AbC123xyz", {
      method: "GET",
      credentials: "omit",
      mode: "cors",
    });
    expect(button?.textContent).toBe("Consultar por WhatsApp");
    expect(button?.getAttribute("aria-label")).toBe(
      "Consultar por WhatsApp con Inmobiliaria Sur (se abre WhatsApp)",
    );
    expect(button?.style.left).toBe("20px");
    expect(button?.target).toBe("_blank");
    expect(document.cookie).toBe("");
  });

  it("names the property marked with data-propiedad", async () => {
    const marked = document.createElement("div");
    marked.setAttribute("data-propiedad", "TKO1234");
    marked.setAttribute("data-titulo", "2 ambientes luminoso");
    document.body.appendChild(marked);

    const { button } = await load();

    expect(button?.href.startsWith("https://wa.me/5491155550000?text=")).toBe(true);
    expect(text(button)).toBe("Hola, me interesa la propiedad «2 ambientes luminoso» (ref. TKO1234)");
  });

  it("uses a property page's own address and title", async () => {
    window.history.replaceState({}, "", "/propiedad/12345-depto-palermo");

    const { button } = await load();

    expect(text(button)).toBe(
      `Hola, me interesa la propiedad «Depto 2 amb en Palermo | Inmobiliaria Sur» (ref. ${window.location.origin}/propiedad/12345-depto-palermo)`,
    );
  });

  it("writes a generic text elsewhere, and shows nothing without WhatsApp", async () => {
    const { button } = await load();
    expect(text(button)).toBe("Hola, les escribo desde su web para hacer una consulta.");

    document.body.innerHTML = "";
    delete (window as unknown as Record<string, unknown>).__inmo24x7Widget;
    const hidden = await load({ ...CONFIG, phone: null });
    expect(hidden.button).toBeNull();
  });
});
