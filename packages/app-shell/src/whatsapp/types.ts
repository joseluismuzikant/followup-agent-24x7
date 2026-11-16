/** The WhatsApp connection as every product's API returns it (followup_platform's shared
 * router): the same shapes in each product's generated client. */

export interface WhatsAppError {
  code: string;
  title: string;
  message: string;
  action: string;
}

export interface WhatsAppAdminError extends WhatsAppError {
  meta_code: string;
  admin_detail: string;
}

export type WhatsAppStatusName = "connected" | "disconnected" | "error" | "not_connected";

export interface WhatsAppStatus {
  status: WhatsAppStatusName;
  display_phone_number?: string | null;
  verified_name?: string | null;
  last_inbound_at?: string | null;
  connected_at?: string | null;
  quality_rating?: string | null;
  business_verification?: "verified" | "pending" | "failed" | "unknown" | null;
  failing_since?: string | null;
  error?: WhatsAppError | null;
  signup_step?: string | null;
  signup_error?: WhatsAppError | null;
}

export interface WhatsAppConnection extends WhatsAppStatus {
  phone_number_id?: string | null;
  waba_id?: string | null;
  business_id?: string | null;
  sender?: "cloud" | "log" | null;
  template_name?: string | null;
  template_language?: string | null;
  visit_template_name?: string | null;
  visit_template_language?: string | null;
  last_error_code?: string | null;
  admin_error?: WhatsAppAdminError | null;
  updated_at?: string | null;
  has_access_token?: boolean;
}

export interface WhatsAppConnectionInput {
  phone_number_id: string;
  waba_id: string;
  display_phone_number?: string | null;
  access_token?: string | null;
  sender?: "cloud" | "log" | null;
  visit_template_name?: string | null;
  visit_template_language?: string | null;
}

export interface EmbeddedSignupInput {
  code: string;
  waba_id: string;
  phone_number_id: string;
  business_id?: string | null;
}

export interface SignupAbandonedInput {
  event: "CANCEL" | "ERROR" | "FINISH_ONLY_WABA" | "FINISH_GRANT_ONLY_API_ACCESS";
  current_step?: string | null;
  error_code?: string | null;
}

/** What a panel's Embedded Signup needs from its API. */
export interface WhatsAppPanelApi {
  completeEmbeddedSignup(input: EmbeddedSignupInput): Promise<WhatsAppStatus>;
  retryEmbeddedSignup(): Promise<WhatsAppStatus>;
  /** Meta's popup error in plain Spanish (null without a code, or if the report failed). */
  reportSignupAbandoned(input: SignupAbandonedInput): Promise<WhatsAppError | null>;
}

export type ConnectionAction = "test" | "subscribe" | "disconnect";

/** What a backoffice's manual connection needs from its API. */
export interface WhatsAppAdminApi {
  fetchConnection(tenantId: string): Promise<WhatsAppConnection>;
  saveConnection(tenantId: string, input: WhatsAppConnectionInput): Promise<WhatsAppConnection>;
  runConnectionAction(tenantId: string, action: ConnectionAction): Promise<WhatsAppConnection>;
  sendTestMessage(tenantId: string, to: string): Promise<string>;
}
