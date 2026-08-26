/**
 * The generic core every operation wrapper in `src/api/*.ts` is built on.
 *
 * Types come from `./schema.d.ts` (generated from `docs/openapi.yaml` by `npm run
 * generate:api` — see that file's header). This module never invents a shape: it derives
 * parameter, body and response types from the `operations` map the generator produced, and
 * delegates the actual network call to `apiFetch` in `client.ts`, which already owns the
 * error envelope and the CSRF header. No business rule is evaluated here — this is transport
 * only (brief §2).
 *
 * `call()` is intentionally loose about *which* path string it accepts: tying it to the
 * operation's own path key would need a second generic parameter threaded through every
 * wrapper for no real safety, because a wrong path is still a valid `string`. Instead
 * `src/api/contract.test.ts` reads every wrapper's source and asserts the literal path it
 * calls is a key of the generated schema — a contract change breaks that test, not
 * production.
 */
import { apiFetch, apiFetchBinary } from './client';
import type { operations } from './schema';

export type { operations };

type Operation = operations[keyof operations];

type ParamsOf<Op extends Operation> = Op extends { parameters: infer P } ? P : never;
type QueryOf<Op extends Operation> = ParamsOf<Op> extends { query?: infer Q } ? Q : undefined;
type PathParamsOf<Op extends Operation> = ParamsOf<Op> extends { path?: infer P } ? P : undefined;
type JsonBodyOf<Op extends Operation> = Op extends {
  requestBody?: { content: { 'application/json': infer B } };
}
  ? B
  : undefined;

type ResponsesOf<Op extends Operation> = Op extends { responses: infer R } ? R : never;
type SuccessStatus<Op extends Operation> = Extract<keyof ResponsesOf<Op>, 200 | 201 | 202 | 204>;
type SuccessOf<Op extends Operation> = {
  [S in SuccessStatus<Op>]: ResponsesOf<Op>[S] extends { content: { 'application/json': infer C } }
    ? C
    : void;
}[SuccessStatus<Op>];

/** `Query<'listVendors'>`, `PathParams<'getVendor'>`, `Body<'createVendor'>` — used by the wrappers. */
export type Query<Op extends keyof operations> = QueryOf<operations[Op]>;
export type PathParams<Op extends keyof operations> = PathParamsOf<operations[Op]>;
export type Body<Op extends keyof operations> = JsonBodyOf<operations[Op]>;
export type Success<Op extends keyof operations> = SuccessOf<operations[Op]>;

export type HttpMethod = 'get' | 'post' | 'put' | 'patch' | 'delete';

interface CallInit<Op extends keyof operations> {
  params?: PathParams<Op>;
  query?: Query<Op>;
  body?: Body<Op>;
}

function fillPath(template: string, params?: Record<string, unknown>): string {
  if (!params) return template;
  return template.replace(/\{([^}]+)\}/g, (_match, key: string) => {
    const value = params[key];
    return encodeURIComponent(String(value));
  });
}

function toQueryString(query?: Record<string, unknown>): string {
  if (!query) return '';
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value === undefined || value === null) continue;
    if (Array.isArray(value)) {
      for (const item of value) search.append(key, String(item));
    } else {
      search.append(key, String(value));
    }
  }
  const qs = search.toString();
  return qs ? `?${qs}` : '';
}

/**
 * Calls one JSON operation. `path` is the operation's path *template*
 * (`/vendors/{vendor_id}`, exactly as it appears in `docs/openapi.yaml`); `params` fills it in.
 */
export function call<Op extends keyof operations>(
  method: HttpMethod,
  path: string,
  init: CallInit<Op> = {},
): Promise<Success<Op>> {
  const url =
    fillPath(path, init.params as Record<string, unknown> | undefined) +
    toQueryString(init.query as Record<string, unknown> | undefined);
  return apiFetch<Success<Op>>(url, {
    method: method.toUpperCase(),
    body: init.body === undefined ? undefined : JSON.stringify(init.body),
  });
}

/**
 * Calls an operation whose response is a file (the `.xlsx` / `.pdf` exports), returning the
 * raw `Blob` instead of parsed JSON — `apiFetch` always parses JSON, so these bypass it and
 * talk to `fetch` directly while keeping the same base URL, credentials and CSRF handling.
 */
export function callBinary<Op extends keyof operations>(
  method: HttpMethod,
  path: string,
  init: { params?: PathParams<Op>; query?: Query<Op> } = {},
): Promise<Blob> {
  const url =
    fillPath(path, init.params as Record<string, unknown> | undefined) +
    toQueryString(init.query as Record<string, unknown> | undefined);
  return apiFetchBinary(url, method.toUpperCase());
}

/**
 * Calls an operation whose request body is `multipart/form-data` (a file upload alongside
 * form fields) rather than JSON.
 */
export function callMultipart<Op extends keyof operations>(
  method: HttpMethod,
  path: string,
  formData: FormData,
): Promise<Success<Op>> {
  return apiFetch<Success<Op>>(path, { method: method.toUpperCase(), body: formData });
}
