import { createApiClient as createSharedClient } from "@followup/app-shell/api";
import type { ApiClientOptions } from "@followup/app-shell/api";

import type { components, paths } from "./schema";

export type { components, paths };

type Schemas = components["schemas"];

export type MeResponse = Schemas["MeResponse"];
export type SignUpResponse = Schemas["SignUpResponse"];
export type OnboardingState = Schemas["OnboardingRead"];
export type SetupChecklist = Schemas["ChecklistRead"];
export type TenantSettings = Schemas["TenantSettingsRead"];
export type TenantSettingsInput = Schemas["TenantSettingsWrite"];
export type ScheduleBlock = Schemas["ScheduleBlockModel"];
export type Client = Schemas["ClientRead"];
export type ClientDetail = Schemas["ClientDetailRead"];
export type ClientList = Schemas["ClientListRead"];
export type ClientInput = Schemas["ClientWrite"];
export type ClientUpdateInput = Schemas["ClientUpdate"];
export type ClientInvoice = Schemas["ClientInvoiceRead"];
export type Invoice = Schemas["InvoiceListItemRead"];
export type InvoiceDetail = Schemas["InvoiceDetailRead"];
export type InvoiceList = Schemas["InvoiceListRead"];
export type InvoiceInput = Schemas["InvoiceWrite"];
export type InvoiceStatus = Schemas["DisplayStatusRead"];
export type TabCounts = Schemas["TabCountsRead"];
export type InvoiceTab = keyof TabCounts;
export type MarkPaidInput = Schemas["MarkPaidWrite"];
export type PaidVia = MarkPaidInput["paid_via"];
export type Summary = Schemas["SummaryRead"];
export type ImportReport = Schemas["ImportReportRead"];
export type BusinessList = Schemas["BusinessListRead"];
export type BusinessRow = Schemas["BusinessRowRead"];
export type BusinessDetail = Schemas["BusinessDetailRead"];
export type BusinessCreated = Schemas["BusinessCreatedRead"];
export type BusinessCreateInput = Schemas["BusinessCreate"];
export type BusinessActivity = Schemas["ActivityRead"];

// The shared client (bearer token, 5xx hook, request id) lives in @followup/app-shell/api.
export {
  ApiRequestError,
  REQUEST_ID_HEADER,
  apiError,
  errorCode,
  serverErrorInfo,
  type ApiClientOptions,
  type ServerErrorInfo,
} from "@followup/app-shell/api";

export function createApiClient(baseUrl: string, options: ApiClientOptions = {}) {
  return createSharedClient<paths>(baseUrl, options);
}

export type ApiClient = ReturnType<typeof createApiClient>;
