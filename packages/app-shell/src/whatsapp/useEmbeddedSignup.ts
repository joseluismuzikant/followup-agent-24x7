import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useRef, useState } from "react";

import { SignupRequestError } from "./errors";
import { loadFacebookSdk, parseSignupMessage } from "./facebook";
import type { MetaConfig, SignupEvent } from "./facebook";
import type { WhatsAppError, WhatsAppPanelApi, WhatsAppStatus } from "./types";

/** The product's error copy for API failures ("No pudimos..." plus the reference code). */
export type DescribeError = (error: unknown, fallback: string) => string;

export type SignupState =
  | { phase: "idle" }
  | { phase: "connecting" }
  | { phase: "finishing" }
  | { phase: "connected"; status: WhatsAppStatus }
  | { phase: "problem"; title: string; message: string; action?: string; canRetry: boolean };

/** How long to wait for the second half (FB.login's code or the FINISH message). */
const PAIR_TIMEOUT_MS = 8000;

const closedEarly: SignupState = {
  phase: "problem",
  title: "No terminaste la conexión",
  message: "Cerraste la ventana de Meta antes de terminar. Cuando quieras, volvé a intentar.",
  canRetry: false,
};

const noNumber: SignupState = {
  phase: "problem",
  title: "Falta elegir el número",
  message:
    "Conectaste la cuenta de Meta pero no elegiste un número. Volvé a conectar y elegí el número de WhatsApp.",
  canRetry: false,
};

function fromError(error: unknown, describe: DescribeError): SignupState {
  if (error instanceof SignupRequestError && error.translated) {
    return {
      phase: "problem",
      title: error.translated.title,
      message: error.translated.message,
      action: error.translated.action,
      canRetry: error.code === "whatsapp_signup_failed",
    };
  }
  return {
    phase: "problem",
    title: "No pudimos conectar WhatsApp",
    message: describe(error, "Probá de nuevo en unos minutos."),
    canRetry: false,
  };
}

function fromMeta(error: WhatsAppError | null, fallback: SignupState): SignupState {
  if (!error) {
    return fallback;
  }
  return {
    phase: "problem",
    title: error.title,
    message: error.message,
    action: error.action,
    canRetry: false,
  };
}

/** Meta's popup gives two halves: FB.login's 30-second code and a WA_EMBEDDED_SIGNUP message
 * with the WABA and number ids. Whichever arrives second sends both to the API at once.
 * Each product passes its API, its Meta app and its error copy. */
export function useEmbeddedSignup(
  api: WhatsAppPanelApi,
  config: MetaConfig | null,
  describe: DescribeError,
) {
  const queryClient = useQueryClient();
  const { completeEmbeddedSignup, reportSignupAbandoned, retryEmbeddedSignup } = api;
  const [state, setState] = useState<SignupState>({ phase: "idle" });
  const code = useRef<string | null>(null);
  const finish = useRef<SignupEvent["data"] | null>(null);
  const settled = useRef(true);
  const timer = useRef<number | null>(null);

  const settle = useCallback((next: SignupState) => {
    settled.current = true;
    if (timer.current !== null) {
      window.clearTimeout(timer.current);
      timer.current = null;
    }
    setState(next);
  }, []);

  const submit = useCallback(async () => {
    const data = finish.current;
    if (settled.current || !code.current || !data?.waba_id || !data.phone_number_id) {
      return;
    }
    settled.current = true;
    setState({ phase: "finishing" });
    try {
      const status = await completeEmbeddedSignup({
        code: code.current,
        waba_id: data.waba_id,
        phone_number_id: data.phone_number_id,
        business_id: data.business_id ?? null,
      });
      queryClient.setQueryData(["whatsapp"], status);
      await queryClient.invalidateQueries({ queryKey: ["onboarding"] });
      settle({ phase: "connected", status });
    } catch (error) {
      await queryClient.invalidateQueries({ queryKey: ["whatsapp"] });
      settle(fromError(error, describe));
    }
  }, [completeEmbeddedSignup, describe, queryClient, settle]);

  const waitForTheOtherHalf = useCallback(() => {
    if (timer.current !== null) {
      return;
    }
    timer.current = window.setTimeout(() => {
      timer.current = null;
      if (!settled.current) {
        settle(closedEarly);
      }
    }, PAIR_TIMEOUT_MS);
  }, [settle]);

  useEffect(() => {
    function onMessage(message: MessageEvent) {
      const parsed = parseSignupMessage(message.origin, message.data);
      if (!parsed || settled.current) {
        return;
      }
      const { event, data } = parsed;
      if (event === "FINISH" || event === "FINISH_WHATSAPP_BUSINESS_APP_ONBOARDING") {
        finish.current = data;
        if (code.current) {
          void submit();
        } else {
          waitForTheOtherHalf();
        }
        return;
      }
      if (event === "FINISH_ONLY_WABA" || event === "FINISH_GRANT_ONLY_API_ACCESS") {
        void reportSignupAbandoned({ event });
        settle(noNumber);
        return;
      }
      if (event === "CANCEL" || event === "ERROR") {
        settled.current = true;
        void reportSignupAbandoned({
          event,
          current_step: data.current_step ?? null,
          error_code: data.error_code ?? null,
        }).then((error) => settle(fromMeta(error, closedEarly)));
      }
    }
    window.addEventListener("message", onMessage);
    return () => window.removeEventListener("message", onMessage);
  }, [reportSignupAbandoned, settle, submit, waitForTheOtherHalf]);

  useEffect(
    () => () => {
      if (timer.current !== null) {
        window.clearTimeout(timer.current);
      }
    },
    [],
  );

  const connect = useCallback(async () => {
    if (!config) {
      return;
    }
    code.current = null;
    finish.current = null;
    settled.current = false;
    setState({ phase: "connecting" });
    try {
      const sdk = await loadFacebookSdk(config);
      sdk.login(
        (response) => {
          const received = response.authResponse?.code;
          if (settled.current) {
            return;
          }
          if (!received) {
            // Closed without finishing. A late CANCEL message may still say where.
            waitForTheOtherHalf();
            return;
          }
          code.current = received;
          if (finish.current) {
            void submit();
          } else {
            waitForTheOtherHalf();
          }
        },
        {
          config_id: config.configId,
          response_type: "code",
          override_default_response_type: true,
          extras: { setup: {} },
        },
      );
    } catch {
      settle({
        phase: "problem",
        title: "No pudimos abrir Meta",
        message: "Revisá que el navegador no esté bloqueando ventanas emergentes y probá de nuevo.",
        canRetry: false,
      });
    }
  }, [config, settle, submit, waitForTheOtherHalf]);

  const retry = useCallback(async () => {
    setState({ phase: "finishing" });
    try {
      const status = await retryEmbeddedSignup();
      queryClient.setQueryData(["whatsapp"], status);
      await queryClient.invalidateQueries({ queryKey: ["onboarding"] });
      setState({ phase: "connected", status });
    } catch (error) {
      setState(fromError(error, describe));
    }
  }, [describe, queryClient, retryEmbeddedSignup]);

  return { available: config !== null, state, connect, retry };
}
