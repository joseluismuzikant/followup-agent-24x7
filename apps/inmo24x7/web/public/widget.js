/* global window, document, fetch, URL */
/*!
 * inmo24x7 - "Consultar por WhatsApp" for an agency's website.
 *
 *   <script src="https://app.inmo24x7.com/widget.js" data-agencia="PUBLIC_ID" async></script>
 *
 * No dependencies, no cookies, no storage, no tracking: it reads the agency's public button
 * settings (name, WhatsApp number, colors) from /widget/v1/<id> on the same host as this file,
 * and shows one floating link that opens wa.me with a prefilled text.
 *
 * On a property page the text names the property, so Sofia starts from it:
 *   "Hola, me interesa la propiedad <<titulo>> (ref. <codigo>)" (with angle quotes)
 * The code comes from `data-propiedad` on any element (Tokko's code, our id or the link),
 * else from the page's address when it looks like a property page (it has a number in its
 * path, like /propiedad/12345-depto). The title comes from `data-titulo` on that element,
 * else the page's og:title, else its <title>.
 */
(function () {
  "use strict";

  var script =
    document.currentScript || document.querySelector('script[src*="widget.js"][data-agencia]');
  if (!script || window.__inmo24x7Widget) {
    return;
  }
  window.__inmo24x7Widget = true;
  var agency = script.getAttribute("data-agencia");
  if (!agency) {
    return;
  }
  var GENERIC = "Hola, les escribo desde su web para hacer una consulta.";
  var HEX = /^#[0-9a-fA-F]{6}$/;

  function clean(text, limit) {
    return String(text || "")
      .replace(/\s+/g, " ")
      .trim()
      .slice(0, limit);
  }

  function reference() {
    var marked = document.querySelector("[data-propiedad]");
    if (marked) {
      var code = clean(marked.getAttribute("data-propiedad"), 300);
      if (code) {
        return { code: code, title: clean(marked.getAttribute("data-titulo"), 120) };
      }
    }
    var path = window.location.pathname || "/";
    if (/\d/.test(path) && path !== "/") {
      return { code: window.location.origin + path, title: "" };
    }
    return null;
  }

  function pageTitle() {
    var og = document.querySelector('meta[property="og:title"]');
    return clean((og && og.getAttribute("content")) || document.title, 120);
  }

  function message() {
    var found = reference();
    if (!found) {
      return GENERIC;
    }
    var title = found.title || pageTitle() || "esta propiedad";
    // The same text as the panel's preview and properties/domain/reference.py.
    // Escaped quotes: this file stays ASCII, so a website without a UTF-8 charset still
    // sends the right text.
    return (
      "Hola, me interesa la propiedad \u00ab" +
      title.replace(/[\u00ab\u00bb]/g, "") +
      "\u00bb (ref. " +
      found.code +
      ")"
    );
  }

  function link(phone) {
    return "https://wa.me/" + phone + "?text=" + encodeURIComponent(message());
  }

  function render(config) {
    if (!config || !config.phone) {
      return; // WhatsApp not connected yet: no button
    }
    var color = HEX.test(script.getAttribute("data-color") || "")
      ? script.getAttribute("data-color")
      : HEX.test(config.color || "")
        ? config.color
        : "#047857";
    var text = HEX.test(config.text_color || "") ? config.text_color : "#ffffff";
    var label = clean(script.getAttribute("data-texto") || config.label, 40) || "Consultar por WhatsApp";
    var side = config.position === "left" ? "left" : "right";

    var button = document.createElement("a");
    button.href = link(config.phone);
    button.target = "_blank";
    button.rel = "noopener noreferrer";
    button.setAttribute(
      "aria-label",
      label + (config.agency_name ? " con " + clean(config.agency_name, 80) : "") + " (se abre WhatsApp)",
    );
    button.style.cssText = [
      "position:fixed",
      "bottom:20px",
      side + ":20px",
      "z-index:2147483000",
      "display:inline-flex",
      "align-items:center",
      "gap:8px",
      "max-width:calc(100vw - 40px)",
      "min-height:48px",
      "box-sizing:border-box",
      "padding:12px 18px",
      "border-radius:999px",
      "background:" + color,
      "color:" + text,
      "font:600 15px/1.2 system-ui,-apple-system,'Segoe UI',Roboto,sans-serif",
      "text-decoration:none",
      "box-shadow:0 6px 20px rgba(0,0,0,.25)",
      "white-space:nowrap",
      "overflow:hidden",
      "text-overflow:ellipsis",
    ].join(";");
    button.innerHTML =
      '<svg aria-hidden="true" focusable="false" viewBox="0 0 24 24" width="22" height="22" ' +
      'style="flex:none" fill="currentColor"><path d="M12 2a10 10 0 0 0-8.6 15.1L2 22l5-1.3A10 ' +
      "10 0 1 0 12 2Zm5.3 14.1c-.2.6-1.3 1.2-1.8 1.2-.5.1-1 .2-3.4-.7-2.9-1.2-4.7-4.1-4.9-4.3" +
      "-.1-.2-1.2-1.6-1.2-3s.8-2.2 1-2.5c.3-.3.6-.4.8-.4h.6c.2 0 .4 0 .6.5l.9 2.1c.1.2.1.4 0 .6" +
      "l-.4.6-.4.4c-.1.2-.3.3-.1.6.2.3.8 1.3 1.7 2.1 1.2 1 2.1 1.4 2.4 1.5.3.2.5.1.6 0l.9-1" +
      "c.2-.3.4-.2.6-.1l2 1c.3.1.5.2.5.3.1.2.1.7-.1 1.4Z\"/></svg>";
    var span = document.createElement("span");
    span.textContent = label;
    span.style.cssText = "overflow:hidden;text-overflow:ellipsis";
    button.appendChild(span);
    // Single-page sites change the URL without reloading: the text is built on each click.
    button.addEventListener("click", function () {
      button.href = link(config.phone);
    });
    button.addEventListener("focus", function () {
      button.style.outline = "3px solid " + text;
      button.style.outlineOffset = "3px";
    });
    button.addEventListener("blur", function () {
      button.style.outline = "none";
    });
    document.body.appendChild(button);
  }

  var base = new URL(script.src, window.location.href);
  var url = new URL("/widget/v1/" + encodeURIComponent(agency), base.origin);
  function start() {
    fetch(url.toString(), { method: "GET", credentials: "omit", mode: "cors" })
      .then(function (response) {
        return response.ok ? response.json() : null;
      })
      .then(render)
      .catch(function () {
        /* the website keeps working without the button */
      });
  }
  if (document.body) {
    start();
  } else {
    document.addEventListener("DOMContentLoaded", start);
  }
})();
