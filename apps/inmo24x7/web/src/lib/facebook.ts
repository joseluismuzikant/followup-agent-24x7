/** Meta's JavaScript SDK for Embedded Signup. It only runs on HTTPS pages, so locally it
 * needs a tunnel to 5173; without VITE_META_APP_ID the panel shows the manual fallback. */

interface FacebookLoginResponse {
  authResponse?: { code?: string } | null;
  status?: string;
}

interface FacebookSdk {
  init(options: { appId: string; autoLogAppEvents: boolean; xfbml: boolean; version: string }): void;
  login(
    callback: (response: FacebookLoginResponse) => void,
    options: {
      config_id: string;
      response_type: "code";
      override_default_response_type: true;
      extras: { setup: Record<string, never> };
    },
  ): void;
}

declare global {
  interface Window {
    FB?: FacebookSdk;
    fbAsyncInit?: () => void;
  }
}

const SDK_URL = "https://connect.facebook.net/en_US/sdk.js";

export interface MetaConfig {
  appId: string;
  configId: string;
  graphVersion: string;
}

export function metaConfig(): MetaConfig | null {
  const appId = (import.meta.env.VITE_META_APP_ID ?? "").trim();
  const configId = (import.meta.env.VITE_META_EMBEDDED_SIGNUP_CONFIG_ID ?? "").trim();
  if (!appId || !configId) {
    return null;
  }
  const graphVersion = (import.meta.env.VITE_META_GRAPH_API_VERSION ?? "").trim() || "v26.0";
  return { appId, configId, graphVersion };
}

let loading: Promise<FacebookSdk> | null = null;

/** Loads and initializes the SDK once per page. */
export function loadFacebookSdk(config: MetaConfig): Promise<FacebookSdk> {
  if (window.FB) {
    return Promise.resolve(window.FB);
  }
  loading ??= new Promise<FacebookSdk>((resolve, reject) => {
    window.fbAsyncInit = () => {
      if (!window.FB) {
        reject(new Error("facebook_sdk_missing"));
        return;
      }
      window.FB.init({
        appId: config.appId,
        autoLogAppEvents: true,
        xfbml: true,
        version: config.graphVersion,
      });
      resolve(window.FB);
    };
    const script = document.createElement("script");
    script.src = SDK_URL;
    script.async = true;
    script.defer = true;
    script.crossOrigin = "anonymous";
    script.onerror = () => {
      loading = null;
      reject(new Error("facebook_sdk_failed"));
    };
    document.body.appendChild(script);
  });
  return loading;
}

/** The WA_EMBEDDED_SIGNUP message Meta's popup posts to the page. */
export interface SignupEvent {
  event: string;
  data: {
    phone_number_id?: string;
    waba_id?: string;
    business_id?: string;
    current_step?: string;
    error_code?: string;
    error_message?: string;
  };
}

export function parseSignupMessage(origin: string, raw: unknown): SignupEvent | null {
  if (!origin.endsWith("facebook.com")) {
    return null;
  }
  try {
    const value: unknown = typeof raw === "string" ? JSON.parse(raw) : raw;
    if (
      typeof value === "object" &&
      value !== null &&
      "type" in value &&
      value.type === "WA_EMBEDDED_SIGNUP" &&
      "event" in value &&
      typeof value.event === "string"
    ) {
      const data = "data" in value && typeof value.data === "object" && value.data ? value.data : {};
      return { event: value.event, data: data as SignupEvent["data"] };
    }
  } catch {
    // Other messages from facebook.com are not ours.
  }
  return null;
}
