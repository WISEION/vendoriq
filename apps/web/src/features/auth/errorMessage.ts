import { ApiError } from '../../api/client';

/**
 * `ErrorEnvelope.error.message` is documented as "English text for logs and developers,
 * never shown verbatim to a vendor" (`docs/openapi.yaml`) — so every screen renders from
 * `error.code` through the localised `err_*` keys instead, never `error.message`.
 */
export function localisedErrorKey(error: unknown): string {
  if (error instanceof ApiError) {
    return `err_${error.code}`;
  }
  return 'err_internal_error';
}
