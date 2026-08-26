/**
 * Screen 31 — `/admin/categories` (`docs/SCREENS.md`). Both taxonomies (work packages and
 * material groups), AZ+EN names, parent, create/edit/delete.
 *
 * `deleteCategory` is refused server-side when a category is in use — but not with an error:
 * `services/categories.py` deactivates it instead (`is_active: false`) so a vendor's history
 * keeps its label, and the endpoint still answers `204`. There is nothing for this screen to
 * "catch" — the row simply drops out of the default (active-only) list, which is why the
 * "show inactive" toggle exists: it is where a deactivated-not-deleted category is found
 * again. Nothing here pre-empts that decision by asking "is this category in use?" first.
 */
import { useMemo, useState } from 'react';
import type { FormEvent } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useLocale } from '../../i18n/LocaleProvider';
import { useSession } from '../../auth/SessionProvider';
import { Card, EmptyRow, ErrorText } from './shared';
import { categoriesQuery, useCreateCategory, useDeleteCategory, usePatchCategory } from './queries';
import type { CategoryRow } from './queries';
import './admin.css';

type Kind = 'work' | 'material';

interface CategoryForm {
  code: string;
  name_az: string;
  name_en: string;
  kind: Kind;
  parent_id: string;
  is_active: boolean;
}

function emptyForm(kind: Kind): CategoryForm {
  return { code: '', name_az: '', name_en: '', kind, parent_id: '', is_active: true };
}

export function CategoriesScreen() {
  const { t, locale } = useLocale();
  const { session } = useSession();
  const permissions =
    session.status === 'authenticated' ? session.principal.permissions : [];
  const canWrite = permissions.includes('createCategory');
  const canDelete = permissions.includes('deleteCategory');

  const [kind, setKind] = useState<Kind>('work');
  const [showInactive, setShowInactive] = useState(false);
  const [editingId, setEditingId] = useState<string | 'new' | null>(null);
  const [form, setForm] = useState<CategoryForm>(emptyForm('work'));
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);

  const categories = useQuery(categoriesQuery({ include_inactive: showInactive }));
  const createMutation = useCreateCategory();
  const patchMutation = usePatchCategory();
  const deleteMutation = useDeleteCategory();

  const rows = useMemo(
    () => (categories.data ?? []).filter((row) => row.kind === kind),
    [categories.data, kind],
  );
  const parentOptions = useMemo(
    () => rows.filter((row) => row.id !== editingId),
    [rows, editingId],
  );

  const startNew = () => {
    setForm(emptyForm(kind));
    setEditingId('new');
  };

  const startEdit = (category: CategoryRow) => {
    setForm({
      code: category.code,
      name_az: category.name_az,
      name_en: category.name_en,
      kind: category.kind,
      parent_id: category.parent_id ?? '',
      is_active: category.is_active ?? true,
    });
    setEditingId(category.id);
  };

  const toBody = () => ({
    code: form.code,
    name_az: form.name_az,
    name_en: form.name_en,
    kind: form.kind,
    parent_id: form.parent_id || null,
    is_active: form.is_active,
  });

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault();
    if (editingId === 'new') {
      createMutation.mutate(toBody(), { onSuccess: () => setEditingId(null) });
    } else if (editingId) {
      patchMutation.mutate(
        { id: editingId, body: toBody() },
        { onSuccess: () => setEditingId(null) },
      );
    }
  };

  const saveError = editingId === 'new' ? createMutation.error : patchMutation.error;
  const saving = createMutation.isPending || patchMutation.isPending;

  return (
    <div>
      <div className="page-head">
        <h2>{t('adm_categories_title')}</h2>
      </div>
      <p className="adm-note">{t('adm_categories_sub')}</p>

      <div className="adm-toolbar">
        <div className="adm-seg" role="group" aria-label={t('adm_categories_kind')}>
          {(['work', 'material'] as const).map((value) => (
            <button
              key={value}
              type="button"
              className="adm-seg-btn"
              aria-pressed={kind === value}
              onClick={() => {
                setKind(value);
                setEditingId(null);
              }}
            >
              {t(value === 'work' ? 'adm_kind_work' : 'adm_kind_material')}
            </button>
          ))}
        </div>
        <label className="adm-checkbox">
          <input
            type="checkbox"
            checked={showInactive}
            onChange={(event) => setShowInactive(event.target.checked)}
          />
          {t('adm_show_inactive')}
        </label>
        <div className="adm-toolbar-spacer" />
        {canWrite ? (
          <button type="button" className="btn-primary" onClick={startNew}>
            {t('adm_category_new')}
          </button>
        ) : null}
      </div>

      <Card title={t(kind === 'work' ? 'adm_kind_work' : 'adm_kind_material')}>
        <div className="adm-table-wrap">
          <table className="adm-table">
            <thead>
              <tr>
                <th scope="col">{t('adm_col_code')}</th>
                <th scope="col">{t('adm_col_name_az')}</th>
                <th scope="col">{t('adm_col_name_en')}</th>
                <th scope="col">{t('adm_col_parent')}</th>
                <th scope="col" className="adm-r">
                  {t('adm_col_vendors')}
                </th>
                <th scope="col" className="adm-r">
                  {t('adm_col_prequalified')}
                </th>
                <th scope="col">{t('adm_col_status')}</th>
                {canWrite || canDelete ? <th scope="col" aria-label={t('adm_col_actions')} /> : null}
              </tr>
            </thead>
            <tbody>
              {rows.map((category) => {
                const parent = rows.find((row) => row.id === category.parent_id);
                return (
                  <tr key={category.id}>
                    <td className="mono">{category.code}</td>
                    <td>{category.name_az}</td>
                    <td>{category.name_en}</td>
                    <td>{parent ? (locale === 'en' ? parent.name_en : parent.name_az) : '—'}</td>
                    <td className="adm-r">{category.vendor_count ?? 0}</td>
                    <td className="adm-r">{category.prequalified_count ?? 0}</td>
                    <td>
                      <span
                        className={`adm-pill ${category.is_active ? 'adm-pill-good' : 'adm-pill-mute'}`}
                      >
                        {t(category.is_active ? 'adm_active' : 'adm_inactive')}
                      </span>
                    </td>
                    {canWrite || canDelete ? (
                      <td>
                        <div className="adm-row-actions">
                          {canWrite ? (
                            <button
                              type="button"
                              className="btn-link"
                              onClick={() => startEdit(category)}
                            >
                              {t('adm_edit')}
                            </button>
                          ) : null}
                          {canDelete ? (
                            confirmDeleteId === category.id ? (
                              <>
                                <button
                                  type="button"
                                  className="btn-link"
                                  onClick={() => {
                                    deleteMutation.mutate(category.id);
                                    setConfirmDeleteId(null);
                                  }}
                                >
                                  {t('adm_delete_confirm')}
                                </button>
                                <button
                                  type="button"
                                  className="btn-link"
                                  onClick={() => setConfirmDeleteId(null)}
                                >
                                  {t('adm_cancel')}
                                </button>
                              </>
                            ) : (
                              <button
                                type="button"
                                className="btn-link"
                                onClick={() => setConfirmDeleteId(category.id)}
                              >
                                {t('adm_delete')}
                              </button>
                            )
                          ) : null}
                        </div>
                      </td>
                    ) : null}
                  </tr>
                );
              })}
              {categories.data && rows.length === 0 ? (
                <EmptyRow columns={8} text={t('adm_categories_empty')} />
              ) : null}
            </tbody>
          </table>
        </div>
        <ErrorText error={categories.error ?? deleteMutation.error} />
      </Card>

      {editingId ? (
        <Card title={editingId === 'new' ? t('adm_category_new') : t('adm_category_edit')}>
          <form onSubmit={handleSubmit} noValidate>
            <div className="adm-form-grid">
              <div className="field">
                <label htmlFor="cat-code">{t('adm_col_code')}</label>
                <input
                  id="cat-code"
                  required
                  value={form.code}
                  onChange={(event) => setForm({ ...form, code: event.target.value })}
                />
              </div>
              <div className="field">
                <label htmlFor="cat-name-az">{t('adm_col_name_az')}</label>
                <input
                  id="cat-name-az"
                  required
                  value={form.name_az}
                  onChange={(event) => setForm({ ...form, name_az: event.target.value })}
                />
              </div>
              <div className="field">
                <label htmlFor="cat-name-en">{t('adm_col_name_en')}</label>
                <input
                  id="cat-name-en"
                  required
                  value={form.name_en}
                  onChange={(event) => setForm({ ...form, name_en: event.target.value })}
                />
              </div>
              <div className="field">
                <label htmlFor="cat-kind">{t('adm_categories_kind')}</label>
                <select
                  id="cat-kind"
                  value={form.kind}
                  onChange={(event) => setForm({ ...form, kind: event.target.value as Kind })}
                >
                  <option value="work">{t('adm_kind_work')}</option>
                  <option value="material">{t('adm_kind_material')}</option>
                </select>
              </div>
              <div className="field">
                <label htmlFor="cat-parent">{t('adm_col_parent')}</label>
                <select
                  id="cat-parent"
                  value={form.parent_id}
                  onChange={(event) => setForm({ ...form, parent_id: event.target.value })}
                >
                  <option value="">{t('adm_no_parent')}</option>
                  {parentOptions
                    .filter((option) => option.kind === form.kind)
                    .map((option) => (
                      <option key={option.id} value={option.id}>
                        {locale === 'en' ? option.name_en : option.name_az}
                      </option>
                    ))}
                </select>
              </div>
              <label className="adm-checkbox" style={{ alignSelf: 'end' }}>
                <input
                  type="checkbox"
                  checked={form.is_active}
                  onChange={(event) => setForm({ ...form, is_active: event.target.checked })}
                />
                {t('adm_active')}
              </label>
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
