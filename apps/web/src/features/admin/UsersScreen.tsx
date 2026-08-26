/**
 * Screen 32 — `/admin/users` (`docs/SCREENS.md`). The accounts, their roles, and role
 * changes.
 *
 * What a role may do is never repeated here as a second copy of `security/permissions.py`
 * (spec §3): the five short blurbs in the legend card are descriptive prose, straight out of
 * the spec's own role table, not a list of operation ids — the moment this screen needed to
 * know *which operations* a role may call, the answer comes from `GET /api/auth/me`
 * (`permissions`) for the signed-in admin, and from the server's own refusal (403/409) for
 * everyone else. `test_the_last_active_admin_cannot_be_demoted_or_deactivated` is the rule
 * this screen leans on for the one dangerous case (locking every admin out): it is not
 * pre-empted here, only surfaced when the server says no.
 */
import { useState } from 'react';
import type { FormEvent } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useLocale } from '../../i18n/LocaleProvider';
import { useSession } from '../../auth/SessionProvider';
import { Card, EmptyRow, ErrorText, useTimestamp } from './shared';
import {
  useCreateUser,
  useDeactivateUser,
  usePatchUser,
  useSetUserRole,
  usersQuery,
  vendorPickerQuery,
} from './queries';
import type { UserRow } from './queries';
import './admin.css';

const ROLES = ['vendor', 'officer', 'commission', 'manager', 'admin'] as const;
type Role = (typeof ROLES)[number];
const PAGE_SIZE = 25;

interface AccountForm {
  email: string;
  full_name: string;
  role: Role;
  vendor_id: string;
  locale: 'az' | 'en';
  password: string;
}

function emptyForm(): AccountForm {
  return { email: '', full_name: '', role: 'officer', vendor_id: '', locale: 'az', password: '' };
}

export function UsersScreen() {
  const { t } = useLocale();
  const stamp = useTimestamp();
  const { session } = useSession();
  const permissions = session.status === 'authenticated' ? session.principal.permissions : [];
  const currentUserId = session.status === 'authenticated' ? session.principal.id : null;
  const canCreate = permissions.includes('createUser');
  const canPatch = permissions.includes('patchUser');
  const canSetRole = permissions.includes('putUserRole');
  const canDeactivate = permissions.includes('deactivateUser');

  const [roleFilter, setRoleFilter] = useState<Role | 'all'>('all');
  const [q, setQ] = useState('');
  const [page, setPage] = useState(1);
  const [editingId, setEditingId] = useState<string | 'new' | null>(null);
  const [form, setForm] = useState<AccountForm>(emptyForm());
  const [confirmDeactivateId, setConfirmDeactivateId] = useState<string | null>(null);
  const [justCreated, setJustCreated] = useState<{ email: string; uri: string } | null>(null);

  const query = {
    page,
    page_size: PAGE_SIZE,
    ...(roleFilter !== 'all' ? { role: [roleFilter] } : {}),
    ...(q ? { q } : {}),
  };
  const users = useQuery(usersQuery(query));
  const vendors = useQuery(vendorPickerQuery);

  const createMutation = useCreateUser();
  const patchMutation = usePatchUser();
  const setRoleMutation = useSetUserRole();
  const deactivateMutation = useDeactivateUser();

  const startNew = () => {
    setForm(emptyForm());
    setJustCreated(null);
    setEditingId('new');
  };

  const startEdit = (user: UserRow) => {
    setForm({
      email: user.email,
      full_name: user.full_name ?? '',
      role: user.role,
      vendor_id: user.vendor_id ?? '',
      locale: user.locale === 'en' ? 'en' : 'az',
      password: '',
    });
    setEditingId(user.id);
  };

  const handleCreate = (event: FormEvent) => {
    event.preventDefault();
    createMutation.mutate(
      {
        email: form.email,
        full_name: form.full_name || undefined,
        role: form.role,
        vendor_id: form.role === 'vendor' ? form.vendor_id || undefined : undefined,
        locale: form.locale,
        password: form.role !== 'vendor' ? form.password || undefined : undefined,
      },
      {
        onSuccess: (created) => {
          setEditingId(null);
          if (created.totp_provisioning_uri) {
            setJustCreated({ email: created.email, uri: created.totp_provisioning_uri });
          }
        },
      },
    );
  };

  const handlePatch = (event: FormEvent, userId: string) => {
    event.preventDefault();
    patchMutation.mutate(
      {
        id: userId,
        body: {
          email: form.email,
          full_name: form.full_name || undefined,
          role: form.role,
          vendor_id: form.role === 'vendor' ? form.vendor_id || undefined : undefined,
          locale: form.locale,
          password: form.role !== 'vendor' ? form.password || undefined : undefined,
        },
      },
      { onSuccess: () => setEditingId(null) },
    );
  };

  const totalPages = users.data ? Math.max(1, Math.ceil(users.data.total / PAGE_SIZE)) : 1;
  const saveError = editingId === 'new' ? createMutation.error : patchMutation.error;
  const saving = createMutation.isPending || patchMutation.isPending;

  return (
    <div>
      <div className="page-head">
        <h2>{t('adm_users_title')}</h2>
      </div>
      <p className="adm-note">{t('adm_users_sub')}</p>

      <RoleLegend />

      <div className="adm-toolbar">
        <select
          aria-label={t('adm_filter_role')}
          value={roleFilter}
          onChange={(event) => {
            setRoleFilter(event.target.value as Role | 'all');
            setPage(1);
          }}
        >
          <option value="all">{t('adm_all_roles')}</option>
          {ROLES.map((role) => (
            <option key={role} value={role}>
              {t(`adm_role_${role}`)}
            </option>
          ))}
        </select>
        <input
          className="adm-search"
          placeholder={t('adm_search_users')}
          value={q}
          onChange={(event) => {
            setQ(event.target.value);
            setPage(1);
          }}
        />
        <div className="adm-toolbar-spacer" />
        {canCreate ? (
          <button type="button" className="btn-primary" onClick={startNew}>
            {t('adm_user_new')}
          </button>
        ) : null}
      </div>

      {justCreated ? (
        <div className="adm-alert" role="status">
          <strong>{t('adm_totp_uri_note')}</strong>
          <div>{justCreated.email}</div>
          <code className="adm-mono-block">{justCreated.uri}</code>
        </div>
      ) : null}

      <Card title={t('adm_users_title')}>
        <div className="adm-table-wrap">
          <table className="adm-table">
            <thead>
              <tr>
                <th scope="col">{t('adm_col_email')}</th>
                <th scope="col">{t('adm_col_full_name')}</th>
                <th scope="col">{t('adm_col_role')}</th>
                <th scope="col">{t('adm_col_vendor')}</th>
                <th scope="col">{t('adm_col_locale')}</th>
                <th scope="col">{t('adm_col_status')}</th>
                <th scope="col">{t('adm_col_totp')}</th>
                <th scope="col">{t('adm_col_last_login')}</th>
                {canPatch || canSetRole || canDeactivate ? (
                  <th scope="col" aria-label={t('adm_col_actions')} />
                ) : null}
              </tr>
            </thead>
            <tbody>
              {(users.data?.items ?? []).map((user) => (
                <tr key={user.id}>
                  <td>{user.email}</td>
                  <td>{user.full_name ?? '—'}</td>
                  <td>
                    {canSetRole ? (
                      <select
                        aria-label={t('adm_col_role')}
                        value={user.role}
                        disabled={setRoleMutation.isPending}
                        onChange={(event) =>
                          setRoleMutation.mutate({ id: user.id, role: event.target.value as Role })
                        }
                      >
                        {ROLES.map((role) => (
                          <option key={role} value={role}>
                            {t(`adm_role_${role}`)}
                          </option>
                        ))}
                      </select>
                    ) : (
                      <span className="adm-pill adm-pill-mute">{t(`adm_role_${user.role}`)}</span>
                    )}
                  </td>
                  <td>{user.vendor_name ?? '—'}</td>
                  <td>{(user.locale ?? 'az').toUpperCase()}</td>
                  <td>
                    <span
                      className={`adm-pill ${user.is_active ? 'adm-pill-good' : 'adm-pill-mute'}`}
                    >
                      {t(user.is_active ? 'adm_active' : 'adm_inactive')}
                    </span>
                  </td>
                  <td>{user.has_totp ? t('adm_yes') : t('adm_no')}</td>
                  <td>{stamp(user.last_login_at)}</td>
                  {canPatch || canSetRole || canDeactivate ? (
                    <td>
                      <div className="adm-row-actions">
                        {canPatch ? (
                          <button
                            type="button"
                            className="btn-link"
                            onClick={() => startEdit(user)}
                          >
                            {t('adm_edit')}
                          </button>
                        ) : null}
                        {canDeactivate && user.is_active ? (
                          confirmDeactivateId === user.id ? (
                            <>
                              <button
                                type="button"
                                className="btn-link"
                                onClick={() => {
                                  deactivateMutation.mutate(user.id);
                                  setConfirmDeactivateId(null);
                                }}
                              >
                                {t('adm_deactivate_confirm')}
                              </button>
                              <button
                                type="button"
                                className="btn-link"
                                onClick={() => setConfirmDeactivateId(null)}
                              >
                                {t('adm_cancel')}
                              </button>
                            </>
                          ) : (
                            <button
                              type="button"
                              className="btn-link"
                              onClick={() => setConfirmDeactivateId(user.id)}
                            >
                              {t('adm_deactivate')}
                            </button>
                          )
                        ) : null}
                        {user.id === currentUserId ? (
                          <span className="adm-you">{t('adm_you')}</span>
                        ) : null}
                      </div>
                    </td>
                  ) : null}
                </tr>
              ))}
              {users.data && users.data.items.length === 0 ? (
                <EmptyRow columns={9} text={t('adm_users_empty')} />
              ) : null}
            </tbody>
          </table>
        </div>
        <ErrorText error={users.error ?? setRoleMutation.error ?? deactivateMutation.error} />
        {users.data && users.data.total > PAGE_SIZE ? (
          <nav className="adm-pager" aria-label={t('adm_pagination')}>
            <button
              type="button"
              className="btn-secondary"
              disabled={page <= 1}
              onClick={() => setPage((current) => current - 1)}
            >
              {t('adm_prev')}
            </button>
            <span>
              {page} / {totalPages}
            </span>
            <button
              type="button"
              className="btn-secondary"
              disabled={page >= totalPages}
              onClick={() => setPage((current) => current + 1)}
            >
              {t('adm_next')}
            </button>
          </nav>
        ) : null}
      </Card>

      {editingId ? (
        <Card title={editingId === 'new' ? t('adm_user_new') : t('adm_user_edit')}>
          <form onSubmit={(event) => (editingId === 'new' ? handleCreate(event) : handlePatch(event, editingId))} noValidate>
            <div className="adm-form-grid">
              <div className="field">
                <label htmlFor="usr-email">{t('adm_col_email')}</label>
                <input
                  id="usr-email"
                  type="email"
                  required
                  value={form.email}
                  onChange={(event) => setForm({ ...form, email: event.target.value })}
                />
              </div>
              <div className="field">
                <label htmlFor="usr-name">{t('adm_col_full_name')}</label>
                <input
                  id="usr-name"
                  value={form.full_name}
                  onChange={(event) => setForm({ ...form, full_name: event.target.value })}
                />
              </div>
              <div className="field">
                <label htmlFor="usr-role">{t('adm_col_role')}</label>
                <select
                  id="usr-role"
                  value={form.role}
                  onChange={(event) => setForm({ ...form, role: event.target.value as Role })}
                >
                  {ROLES.map((role) => (
                    <option key={role} value={role}>
                      {t(`adm_role_${role}`)}
                    </option>
                  ))}
                </select>
              </div>
              {form.role === 'vendor' ? (
                <div className="field">
                  <label htmlFor="usr-vendor">{t('adm_col_vendor')}</label>
                  <select
                    id="usr-vendor"
                    required
                    value={form.vendor_id}
                    onChange={(event) => setForm({ ...form, vendor_id: event.target.value })}
                  >
                    <option value="">{t('adm_choose_vendor')}</option>
                    {(vendors.data?.items ?? []).map((vendor) => (
                      <option key={vendor.id} value={vendor.id}>
                        {vendor.legal_name}
                      </option>
                    ))}
                  </select>
                </div>
              ) : (
                <div className="field">
                  <label htmlFor="usr-password">{t('adm_col_password')}</label>
                  <input
                    id="usr-password"
                    type="password"
                    autoComplete="new-password"
                    value={form.password}
                    onChange={(event) => setForm({ ...form, password: event.target.value })}
                    placeholder={editingId === 'new' ? '' : t('adm_password_unchanged')}
                  />
                </div>
              )}
              <div className="field">
                <label htmlFor="usr-locale">{t('adm_col_locale')}</label>
                <select
                  id="usr-locale"
                  value={form.locale}
                  onChange={(event) =>
                    setForm({ ...form, locale: event.target.value as 'az' | 'en' })
                  }
                >
                  <option value="az">AZ</option>
                  <option value="en">EN</option>
                </select>
              </div>
            </div>
            <ErrorText error={saveError} />
            <div className="adm-actions" style={{ marginTop: 16 }}>
              <button type="submit" className="btn-primary" disabled={saving}>
                {t('adm_save')}
              </button>
              <button type="button" className="btn-secondary" onClick={() => setEditingId(null)}>
                {t('adm_cancel')}
              </button>
            </div>
          </form>
        </Card>
      ) : null}
    </div>
  );
}

/**
 * Spec §3's role table, in prose — not a permission matrix. It says what each role is *for*,
 * the same sentence the spec uses; it does not say which operation ids a role may call, so it
 * cannot drift out of sync with `security/permissions.py` the way a second matrix would.
 */
function RoleLegend() {
  const { t } = useLocale();
  return (
    <details className="adm-legend">
      <summary>{t('adm_roles_legend_title')}</summary>
      <dl>
        {ROLES.map((role) => (
          <div key={role} className="adm-legend-row">
            <dt>{t(`adm_role_${role}`)}</dt>
            <dd>{t(`adm_role_${role}_desc`)}</dd>
          </div>
        ))}
      </dl>
    </details>
  );
}
