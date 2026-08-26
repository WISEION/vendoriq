/**
 * The register — profiles, categories, contacts, observations, documents.
 *
 * Thin typed wrappers over `docs/openapi.yaml` — transport only, no business rule is
 * evaluated here (brief §2). Types are derived from the generated `./schema.d.ts`;
 * `contract.test.ts` checks every path below is still a key in that schema.
 */
import { call, callBinary } from './http';
import type { Body, PathParams, Query } from './http';

/** The vendor register */
export const listVendors = (query?: Query<'listVendors'>) =>
  call<'listVendors'>('get', '/vendors', { query });

/** Create a vendor (officer) */
export const createVendor = (body: Body<'createVendor'>) =>
  call<'createVendor'>('post', '/vendors', { body });

/** Export the filtered register to Excel */
export const exportVendors = (query?: Query<'exportVendors'>) =>
  callBinary<'exportVendors'>('get', '/vendors/export.xlsx', { query });

/** Vendor detail */
export const getVendor = (params: PathParams<'getVendor'>) =>
  call<'getVendor'>('get', '/vendors/{vendor_id}', { params });

/** Update vendor attributes */
export const patchVendor = (params: PathParams<'patchVendor'>, body: Body<'patchVendor'>) =>
  call<'patchVendor'>('patch', '/vendors/{vendor_id}', { params, body });

/** Categories claimed by the vendor */
export const listVendorCategories = (params: PathParams<'listVendorCategories'>) =>
  call<'listVendorCategories'>('get', '/vendors/{vendor_id}/categories', { params });

/** Replace the vendor's category selection */
export const setVendorCategories = (
  params: PathParams<'setVendorCategories'>,
  body: Body<'setVendorCategories'>,
) => call<'setVendorCategories'>('put', '/vendors/{vendor_id}/categories', { params, body });

/** Officer confirms category assignments */
export const confirmVendorCategories = (
  params: PathParams<'confirmVendorCategories'>,
  body: Body<'confirmVendorCategories'>,
) =>
  call<'confirmVendorCategories'>('post', '/vendors/{vendor_id}/categories/confirm', {
    params,
    body,
  });

/** Contact people */
export const listContacts = (params: PathParams<'listContacts'>) =>
  call<'listContacts'>('get', '/vendors/{vendor_id}/contacts', { params });

/** Add a contact */
export const createContact = (params: PathParams<'createContact'>, body: Body<'createContact'>) =>
  call<'createContact'>('post', '/vendors/{vendor_id}/contacts', { params, body });

/** Update a contact */
export const patchContact = (params: PathParams<'patchContact'>, body: Body<'patchContact'>) =>
  call<'patchContact'>('patch', '/vendors/{vendor_id}/contacts/{contact_id}', { params, body });

/** Remove a contact */
export const deleteContact = (params: PathParams<'deleteContact'>) =>
  call<'deleteContact'>('delete', '/vendors/{vendor_id}/contacts/{contact_id}', { params });

/** Provenance history for the vendor's fields */
export const listObservations = (
  params: PathParams<'listObservations'>,
  query?: Query<'listObservations'>,
) => call<'listObservations'>('get', '/vendors/{vendor_id}/observations', { params, query });

/** Manual entry or correction */
export const createObservation = (
  params: PathParams<'createObservation'>,
  body: Body<'createObservation'>,
) => call<'createObservation'>('post', '/vendors/{vendor_id}/observations', { params, body });

/** The 38-item document checklist for this vendor */
export const listDocuments = (
  params: PathParams<'listDocuments'>,
  query?: Query<'listDocuments'>,
) => call<'listDocuments'>('get', '/vendors/{vendor_id}/documents', { params, query });

/** Start a document upload */
export const initDocumentUpload = (
  params: PathParams<'initDocumentUpload'>,
  body: Body<'initDocumentUpload'>,
) =>
  call<'initDocumentUpload'>('post', '/vendors/{vendor_id}/documents/upload-init', {
    params,
    body,
  });

/** Confirm an upload and record the document */
export const completeDocumentUpload = (
  params: PathParams<'completeDocumentUpload'>,
  body: Body<'completeDocumentUpload'>,
) =>
  call<'completeDocumentUpload'>('post', '/vendors/{vendor_id}/documents/upload-complete', {
    params,
    body,
  });

/** Update status, dates or verification */
export const patchDocument = (params: PathParams<'patchDocument'>, body: Body<'patchDocument'>) =>
  call<'patchDocument'>('patch', '/vendors/{vendor_id}/documents/{document_id}', { params, body });

/** A signed, expiring download link */
export const getDocumentDownload = (params: PathParams<'getDocumentDownload'>) =>
  call<'getDocumentDownload'>('get', '/vendors/{vendor_id}/documents/{document_id}', { params });

/** Invite the vendor to a cycle */
export const inviteVendor = (params: PathParams<'inviteVendor'>, body: Body<'inviteVendor'>) =>
  call<'inviteVendor'>('post', '/vendors/{vendor_id}/invite', { params, body });

/** Suspend or lift a suspension (manager) */
export const suspendVendor = (params: PathParams<'suspendVendor'>, body: Body<'suspendVendor'>) =>
  call<'suspendVendor'>('post', '/vendors/{vendor_id}/suspend', { params, body });
