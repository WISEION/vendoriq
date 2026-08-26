/**
 * Vendor one-time codes, staff password + TOTP, session and identity — the three auth
 * screens are built on this file.
 *
 * Thin typed wrappers over `docs/openapi.yaml` — transport only, no business rule is
 * evaluated here (brief §2). Types are derived from the generated `./schema.d.ts`;
 * `contract.test.ts` checks every path below is still a key in that schema.
 */
import { call } from './http';
import type { Body } from './http';

/** Self-registration of a vendor */
export const registerVendor = (body: Body<'registerVendor'>) =>
  call<'registerVendor'>('post', '/auth/vendor/register', { body });

/** Request a one-time code */
export const requestOtp = (body: Body<'requestOtp'>) =>
  call<'requestOtp'>('post', '/auth/otp/request', { body });

/** Exchange a one-time code for a session */
export const verifyOtp = (body: Body<'verifyOtp'>) =>
  call<'verifyOtp'>('post', '/auth/otp/verify', { body });

/** Staff login with e-mail and password */
export const staffLogin = (body: Body<'staffLogin'>) =>
  call<'staffLogin'>('post', '/auth/staff/login', { body });

/** Verify the TOTP second factor */
export const verifyTotp = (body: Body<'verifyTotp'>) =>
  call<'verifyTotp'>('post', '/auth/staff/totp/verify', { body });

/** End the session */
export const logout = () => call<'logout'>('post', '/auth/logout');

/** The authenticated identity and its permissions */
export const getMe = () => call<'getMe'>('get', '/auth/me');
