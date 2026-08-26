import { useMemo, useState } from 'react';
import type { FormEvent } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { createCycle, deleteCycle, getCycle, inviteToCycle, listCycles, patchCycle } from '../../api/cycles';
import { listScoringModels } from '../../api/scoring-models';
import { listVendors } from '../../api/vendors';
import { ApiError } from '../../api/client';
import { useLocale } from '../../i18n/LocaleProvider';
import { localisedErrorKey } from '../auth/errorMessage';
import './projects.css';

type Cycle = Awaited<ReturnType<typeof listCycles>>['items'][number];

const CYCLE_KINDS = ['tender', 'periodic'] as const;
const CYCLE_STATUSES = ['draft', 'open', 'closed', 'archived'] as const;

interface CycleFormState {
  name: string;
  kind: (typeof CYCLE_KINDS)[number];
  scoring_model_version: string;
  status: (typeof CYCLE_STATUSES)[number];
  opens_at: string;
  closes_at: string;
}

function emptyForm(defaultModel: string): CycleFormState {
  return { name: '', kind: 'tender', scoring_model_version: defaultModel, status: 'draft', opens_at: '', closes_at: '' };
}

function toIso(value: string): string | null {
  return value ? new Date(value).toISOString() : null;
}

function fromIso(value: string | null | undefined): string {
  if (!value) return '';
  return value.slice(0, 16);
}

/** Screen 21 — `/cycles`: create, edit, delete cycles and bulk-invite vendors into one. */
export function CyclesScreen() {
  const { t, locale } = useLocale();
  const queryClient = useQueryClient();

  const cyclesQuery = useQuery({ queryKey: ['cycles'], queryFn: () => listCycles({ page_size: 100 }) });
  const modelsQuery = useQuery({ queryKey: ['scoring-models'], queryFn: () => listScoringModels() });
  const models = modelsQuery.data ?? [];

  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState<CycleFormState>(emptyForm(''));
  const [editingId, setEditingId] = useState<string | null>(null);
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);
  const [invitingId, setInvitingId] = useState<string | null>(null);

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ['cycles'] });

  const createMutation = useMutation({
    mutationFn: () =>
      createCycle({
        name: form.name,
        kind: form.kind,
        scoring_model_version: form.scoring_model_version,
        status: form.status,
        opens_at: toIso(form.opens_at),
        closes_at: toIso(form.closes_at),
      }),
    onSuccess: () => {
      invalidate();
      setShowCreate(false);
    },
  });

  const patchMutation = useMutation({
    mutationFn: (id: string) =>
      patchCycle(
        { cycle_id: id },
        {
          name: form.name,
          kind: form.kind,
          scoring_model_version: form.scoring_model_version,
          status: form.status,
          opens_at: toIso(form.opens_at),
          closes_at: toIso(form.closes_at),
        },
      ),
    onSuccess: () => {
      invalidate();
      setEditingId(null);
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => deleteCycle({ cycle_id: id }),
    onSuccess: () => {
      invalidate();
      setConfirmDeleteId(null);
    },
  });

  const startCreate = () => {
    setForm(emptyForm(models[0]?.version ?? ''));
    setEditingId(null);
    setShowCreate(true);
  };

  const startEdit = (cycle: Cycle) => {
    setForm({
      name: cycle.name,
      kind: cycle.kind,
      scoring_model_version: cycle.scoring_model_version,
      status: cycle.status,
      opens_at: fromIso(cycle.opens_at),
      closes_at: fromIso(cycle.closes_at),
    });
    setShowCreate(false);
    setEditingId(cycle.id);
  };

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault();
    if (editingId) patchMutation.mutate(editingId);
    else createMutation.mutate();
  };

  const activeError = editingId ? patchMutation.error : createMutation.error;

  return (
    <div>
      <div className="page-head">
        <h2>{t('cyc_title')}</h2>
        <p>{t('cyc_sub')}</p>
      </div>

      <div className="viq-toolbar">
        <div className="viq-toolbar-spacer" />
        <button type="button" className="btn-primary" onClick={startCreate}>
          {t('cyc_new')}
        </button>
      </div>

      {showCreate || editingId ? (
        <div className="viq-card">
          <div className="viq-card-head">
            <h3>{editingId ? t('cyc_edit_title') : t('cyc_new')}</h3>
          </div>
          <div className="viq-card-body">
            <form onSubmit={handleSubmit} noValidate>
              <div className="viq-form-grid">
                <div className="field">
                  <label htmlFor="cyc-name">{t('cyc_name')}</label>
                  <input
                    id="cyc-name"
                    required
                    value={form.name}
                    onChange={(event) => setForm({ ...form, name: event.target.value })}
                  />
                </div>
                <div className="field">
                  <label htmlFor="cyc-kind">{t('cyc_kind')}</label>
                  <select
                    id="cyc-kind"
                    value={form.kind}
                    onChange={(event) => setForm({ ...form, kind: event.target.value as CycleFormState['kind'] })}
                  >
                    {CYCLE_KINDS.map((kind) => (
                      <option key={kind} value={kind}>
                        {t(`cyc_kind_${kind}`)}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="field">
                  <label htmlFor="cyc-model">{t('cyc_model')}</label>
                  <select
                    id="cyc-model"
                    required
                    value={form.scoring_model_version}
                    onChange={(event) => setForm({ ...form, scoring_model_version: event.target.value })}
                  >
                    <option value="" disabled>
                      {t('show')}
                    </option>
                    {models.map((model) => (
                      <option key={model.version} value={model.version}>
                        {model.version} — {locale === 'en' ? model.name_en : model.name_az}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="field">
                  <label htmlFor="cyc-status">{t('cyc_status')}</label>
                  <select
                    id="cyc-status"
                    value={form.status}
                    onChange={(event) => setForm({ ...form, status: event.target.value as CycleFormState['status'] })}
                  >
                    {CYCLE_STATUSES.map((status) => (
                      <option key={status} value={status}>
                        {t(`cyc_status_${status}`)}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="field">
                  <label htmlFor="cyc-opens">{t('cyc_opens')}</label>
                  <input
                    id="cyc-opens"
                    type="datetime-local"
                    value={form.opens_at}
                    onChange={(event) => setForm({ ...form, opens_at: event.target.value })}
                  />
                </div>
                <div className="field">
                  <label htmlFor="cyc-closes">{t('cyc_closes')}</label>
                  <input
                    id="cyc-closes"
                    type="datetime-local"
                    value={form.closes_at}
                    onChange={(event) => setForm({ ...form, closes_at: event.target.value })}
                  />
                </div>
              </div>
              {activeError ? (
                <p className="form-error" role="alert">
                  {t(localisedErrorKey(activeError))}
                </p>
              ) : null}
              <div className="viq-actions">
                <button type="submit" className="btn-primary" disabled={createMutation.isPending || patchMutation.isPending}>
                  {t('cyc_save')}
                </button>
                <button
                  type="button"
                  className="btn-secondary"
                  onClick={() => {
                    setShowCreate(false);
                    setEditingId(null);
                  }}
                >
                  {t('cyc_cancel')}
                </button>
              </div>
            </form>
          </div>
        </div>
      ) : null}

      <div className="viq-card">
        <div className="viq-card-body viq-tight">
          <div className="viq-table-wrap">
            <table className="viq-table">
              <thead>
                <tr>
                  <th>{t('cyc_name')}</th>
                  <th>{t('cyc_kind')}</th>
                  <th>{t('cyc_model')}</th>
                  <th>{t('cyc_status')}</th>
                  <th className="viq-r">{t('cyc_applications')}</th>
                  <th>{t('cyc_closes')}</th>
                  <th aria-hidden="true" />
                </tr>
              </thead>
              <tbody>
                {(cyclesQuery.data?.items ?? []).map((cycle) => (
                  <CycleRow
                    key={cycle.id}
                    cycle={cycle}
                    onEdit={() => startEdit(cycle)}
                    onInvite={() => setInvitingId(cycle.id)}
                    onDeleteRequest={() => setConfirmDeleteId(cycle.id)}
                    confirmingDelete={confirmDeleteId === cycle.id}
                    onConfirmDelete={() => deleteMutation.mutate(cycle.id)}
                    onCancelDelete={() => setConfirmDeleteId(null)}
                    deletePending={deleteMutation.isPending}
                    deleteError={confirmDeleteId === cycle.id ? deleteMutation.error : null}
                  />
                ))}
              </tbody>
            </table>
          </div>
          {cyclesQuery.data && cyclesQuery.data.items.length === 0 ? (
            <p className="viq-empty">{t('cyc_empty')}</p>
          ) : null}
        </div>
      </div>

      {invitingId ? (
        <InvitePanel cycleId={invitingId} onClose={() => setInvitingId(null)} onInvited={invalidate} />
      ) : null}
    </div>
  );
}

function CycleRow({
  cycle,
  onEdit,
  onInvite,
  onDeleteRequest,
  confirmingDelete,
  onConfirmDelete,
  onCancelDelete,
  deletePending,
  deleteError,
}: {
  cycle: Cycle;
  onEdit: () => void;
  onInvite: () => void;
  onDeleteRequest: () => void;
  confirmingDelete: boolean;
  onConfirmDelete: () => void;
  onCancelDelete: () => void;
  deletePending: boolean;
  deleteError: unknown;
}) {
  const { t, locale } = useLocale();
  return (
    <tr>
      <td>
        <b>{cycle.name}</b>
      </td>
      <td>{t(`cyc_kind_${cycle.kind}`)}</td>
      <td className="viq-mono">{cycle.scoring_model_version}</td>
      <td>{t(`cyc_status_${cycle.status}`)}</td>
      <td className="viq-r viq-mono">{cycle.application_count ?? 0}</td>
      <td className="viq-mono">
        {cycle.closes_at ? new Date(cycle.closes_at).toLocaleDateString(locale === 'az' ? 'de-DE' : 'en-US') : '—'}
      </td>
      <td>
        <div className="viq-actions">
          <button type="button" className="btn-link" onClick={onEdit}>
            {t('cyc_edit_title')}
          </button>
          <button type="button" className="btn-link" onClick={onInvite}>
            {t('cyc_invite')}
          </button>
          {confirmingDelete ? (
            <>
              <button type="button" className="btn-link" onClick={onConfirmDelete} disabled={deletePending}>
                {t('cyc_delete_confirm')}
              </button>
              <button type="button" className="btn-link" onClick={onCancelDelete}>
                {t('cyc_cancel')}
              </button>
            </>
          ) : (
            <button type="button" className="btn-link" onClick={onDeleteRequest}>
              {t('cyc_delete')}
            </button>
          )}
        </div>
        {deleteError instanceof ApiError && deleteError.code === 'conflict' ? (
          <p className="form-error" role="alert">
            {t('cyc_delete_blocked')}
          </p>
        ) : null}
      </td>
    </tr>
  );
}

function InvitePanel({
  cycleId,
  onClose,
  onInvited,
}: {
  cycleId: string;
  onClose: () => void;
  onInvited: () => void;
}) {
  const { t } = useLocale();
  const cycleQuery = useQuery({ queryKey: ['cycle', cycleId], queryFn: () => getCycle({ cycle_id: cycleId }) });
  const vendorsQuery = useQuery({
    queryKey: ['vendors', 'for-invite'],
    // Only the statuses a fresh or repeat invitation makes sense for; the server is still
    // the authority — it skips an already-invited or suspended vendor regardless (spec §9).
    queryFn: () => listVendors({ page_size: 200, status: ['registered', 'rejected', 'prequalified'] }),
  });

  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [search, setSearch] = useState('');
  const [messageAz, setMessageAz] = useState('');
  const [messageEn, setMessageEn] = useState('');
  const [attempted, setAttempted] = useState(false);

  const inviteMutation = useMutation({
    mutationFn: () =>
      inviteToCycle(
        { cycle_id: cycleId },
        { vendor_ids: [...selected], message_az: messageAz || undefined, message_en: messageEn || undefined },
      ),
    onSuccess: () => onInvited(),
  });

  const vendors = vendorsQuery.data?.items ?? [];
  const filtered = useMemo(() => {
    const needle = search.trim().toLowerCase();
    if (!needle) return vendors;
    return vendors.filter((vendor) => vendor.legal_name.toLowerCase().includes(needle));
  }, [vendors, search]);

  const toggle = (id: string) => {
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const selectAll = () => setSelected(new Set(filtered.map((vendor) => vendor.id)));

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault();
    setAttempted(true);
    if (selected.size === 0) return;
    inviteMutation.mutate();
  };

  return (
    <div className="viq-card" role="region" aria-label={t('cyc_invite_title')}>
      <div className="viq-card-head">
        <div>
          <h3>
            {t('cyc_invite_title')} — {cycleQuery.data?.name}
          </h3>
          <p className="viq-package-meta">{t('cyc_invite_sub')}</p>
        </div>
        <button type="button" className="btn-secondary" onClick={onClose}>
          {t('cyc_cancel')}
        </button>
      </div>
      <div className="viq-card-body">
        {inviteMutation.data ? (
          <div>
            <h4>{t('cyc_invite_result_title')}</h4>
            <p>
              {inviteMutation.data.invited.length} {t('cyc_invited_count')}, {inviteMutation.data.skipped.length}{' '}
              {t('cyc_skipped_count')}
            </p>
            {inviteMutation.data.skipped.length > 0 ? (
              <ul>
                {inviteMutation.data.skipped.map((row) => (
                  <li key={row.vendor_id}>
                    {vendors.find((vendor) => vendor.id === row.vendor_id)?.legal_name ?? row.vendor_id}:{' '}
                    {t(`cyc_skip_reason_${row.reason}`)}
                  </li>
                ))}
              </ul>
            ) : null}
            <button type="button" className="btn-primary" onClick={onClose}>
              {t('cyc_cancel')}
            </button>
          </div>
        ) : (
          <form onSubmit={handleSubmit} noValidate>
            <input
              className="viq-search"
              type="search"
              aria-label={t('cyc_search_vendors')}
              placeholder={t('cyc_search_vendors')}
              value={search}
              onChange={(event) => setSearch(event.target.value)}
            />
            <div className="viq-actions">
              <button type="button" className="btn-link" onClick={selectAll}>
                {t('cyc_invite_select_all')}
              </button>
            </div>
            <fieldset style={{ border: 'none', padding: 0, margin: '8px 0' }}>
              <legend className="viq-package-meta">{t('cyc_invite_title')}</legend>
              <div className="viq-chip-list">
                {filtered.map((vendor) => (
                  <label key={vendor.id} className="viq-chip" data-checked={selected.has(vendor.id)}>
                    <input
                      type="checkbox"
                      checked={selected.has(vendor.id)}
                      onChange={() => toggle(vendor.id)}
                    />
                    {vendor.legal_name}
                  </label>
                ))}
              </div>
            </fieldset>
            <div className="viq-form-grid" style={{ marginTop: 12 }}>
              <div className="field">
                <label htmlFor="inv-msg-az">{t('cyc_invite_message_az')}</label>
                <textarea id="inv-msg-az" value={messageAz} onChange={(event) => setMessageAz(event.target.value)} />
              </div>
              <div className="field">
                <label htmlFor="inv-msg-en">{t('cyc_invite_message_en')}</label>
                <textarea id="inv-msg-en" value={messageEn} onChange={(event) => setMessageEn(event.target.value)} />
              </div>
            </div>
            {attempted && selected.size === 0 ? (
              <p className="form-error" role="alert">
                {t('cyc_invite_none_selected')}
              </p>
            ) : null}
            {inviteMutation.isError ? (
              <p className="form-error" role="alert">
                {t(localisedErrorKey(inviteMutation.error))}
              </p>
            ) : null}
            <div className="viq-actions">
              <button type="submit" className="btn-primary" disabled={inviteMutation.isPending}>
                {t('cyc_invite_send')}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
