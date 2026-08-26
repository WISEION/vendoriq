import { useEffect, useState } from 'react';
import type { FormEvent } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from '@tanstack/react-router';
import { listCategories } from '../../api/admin';
import { ApiError } from '../../api/client';
import {
  createPackage,
  createProject,
  deletePackage,
  deleteProject,
  getProject,
  patchPackage,
  patchProject,
} from '../../api/projects';
import { useLocale } from '../../i18n/LocaleProvider';
import { localisedErrorKey } from '../auth/errorMessage';
import { formatMoney } from './format';
import { PROJECTS_PATH, projectEditPath } from './paths';
import { ClassBadge } from './StatePill';
import './projects.css';

type WorkPackage = NonNullable<Awaited<ReturnType<typeof getProject>>['packages']>[number];
type ScoreClass = WorkPackage['min_class'];

const STAGES = ['pipeline', 'go_nogo', 'tender', 'execution'] as const;
//: KO is a failure state, never a package's minimum bar — offered nowhere in this picker —
//: but the field itself stays typed as the full `ScoreClass` so assigning a loaded
//: package's `min_class` back into the form never needs a narrowing cast.
const CLASSES = ['A', 'B', 'C', 'D', 'F'] as const satisfies readonly ScoreClass[];
const CERTS = ['iso9001', 'iso45001'] as const;

interface ProjectFormState {
  code: string;
  name: string;
  client: string;
  stage: (typeof STAGES)[number];
  estimated_value: string;
  deadline: string;
  external_ref: string;
  is_demo: boolean;
}

function emptyProjectForm(): ProjectFormState {
  return {
    code: '',
    name: '',
    client: '',
    stage: 'pipeline',
    estimated_value: '',
    deadline: '',
    external_ref: '',
    is_demo: false,
  };
}

interface PackageFormState {
  category_code: string;
  estimated_value: string;
  min_class: ScoreClass;
  required_certs: string[];
  notes: string;
}

function emptyPackageForm(defaultCategory: string): PackageFormState {
  return { category_code: defaultCategory, estimated_value: '', min_class: 'C', required_certs: [], notes: '' };
}

/** Screen 23 — `/projects/new` (no `projectId`) and `/projects/$projectId/edit`. */
export function ProjectEditScreen({ projectId }: { projectId?: string }) {
  const { t } = useLocale();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const isNew = !projectId;

  const projectQuery = useQuery({
    queryKey: ['project', projectId],
    queryFn: () => getProject({ project_id: projectId as string }),
    enabled: !isNew,
  });
  const categoriesQuery = useQuery({ queryKey: ['categories'], queryFn: () => listCategories() });

  const [form, setForm] = useState<ProjectFormState>(emptyProjectForm());
  const [confirmDelete, setConfirmDelete] = useState(false);

  useEffect(() => {
    if (!projectQuery.data) return;
    const project = projectQuery.data;
    setForm({
      code: project.code,
      name: project.name,
      client: project.client ?? '',
      stage: project.stage,
      estimated_value: project.estimated_value !== null && project.estimated_value !== undefined ? String(project.estimated_value) : '',
      deadline: project.deadline ?? '',
      external_ref: project.external_ref ?? '',
      is_demo: project.is_demo,
    });
  }, [projectQuery.data]);

  const toBody = () => ({
    code: form.code,
    name: form.name,
    client: form.client || undefined,
    stage: form.stage,
    estimated_value: form.estimated_value ? Number(form.estimated_value) : undefined,
    deadline: form.deadline || null,
    external_ref: form.external_ref || undefined,
    is_demo: form.is_demo,
  });

  const createMutation = useMutation({
    mutationFn: () => createProject(toBody()),
    onSuccess: (project) => {
      queryClient.invalidateQueries({ queryKey: ['projects'] });
      void navigate({ to: projectEditPath(project.id) });
    },
  });

  const patchMutation = useMutation({
    mutationFn: () => patchProject({ project_id: projectId as string }, toBody()),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['projects'] });
      queryClient.invalidateQueries({ queryKey: ['project', projectId] });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: () => deleteProject({ project_id: projectId as string }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['projects'] });
      void navigate({ to: PROJECTS_PATH });
    },
  });

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault();
    if (isNew) createMutation.mutate();
    else patchMutation.mutate();
  };

  const saveError = isNew ? createMutation.error : patchMutation.error;
  const saving = createMutation.isPending || patchMutation.isPending;

  return (
    <div>
      <div className="page-head">
        <h2>{isNew ? t('pe_new_title') : t('pe_edit_title')}</h2>
      </div>

      <div className="viq-card">
        <div className="viq-card-body">
          <form onSubmit={handleSubmit} noValidate>
            <div className="viq-form-grid">
              <div className="field">
                <label htmlFor="pe-code">{t('pe_code')}</label>
                <input id="pe-code" required value={form.code} onChange={(event) => setForm({ ...form, code: event.target.value })} />
              </div>
              <div className="field">
                <label htmlFor="pe-name">{t('pe_name')}</label>
                <input id="pe-name" required value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} />
              </div>
              <div className="field">
                <label htmlFor="pe-client">{t('pe_client')}</label>
                <input id="pe-client" value={form.client} onChange={(event) => setForm({ ...form, client: event.target.value })} />
              </div>
              <div className="field">
                <label htmlFor="pe-stage">{t('pe_stage')}</label>
                <select
                  id="pe-stage"
                  value={form.stage}
                  onChange={(event) => setForm({ ...form, stage: event.target.value as ProjectFormState['stage'] })}
                >
                  {STAGES.map((value) => (
                    <option key={value} value={value}>
                      {t(`stage_${value}`)}
                    </option>
                  ))}
                </select>
              </div>
              <div className="field">
                <label htmlFor="pe-value">{t('pe_value')}</label>
                <input
                  id="pe-value"
                  type="number"
                  min={0}
                  value={form.estimated_value}
                  onChange={(event) => setForm({ ...form, estimated_value: event.target.value })}
                />
              </div>
              <div className="field">
                <label htmlFor="pe-deadline">{t('pe_deadline')}</label>
                <input id="pe-deadline" type="date" value={form.deadline} onChange={(event) => setForm({ ...form, deadline: event.target.value })} />
              </div>
              <div className="field">
                <label htmlFor="pe-ref">{t('pe_external_ref')}</label>
                <input id="pe-ref" value={form.external_ref} onChange={(event) => setForm({ ...form, external_ref: event.target.value })} />
              </div>
              <div className="viq-checkbox-row" style={{ alignSelf: 'end' }}>
                <input
                  id="pe-demo"
                  type="checkbox"
                  checked={form.is_demo}
                  onChange={(event) => setForm({ ...form, is_demo: event.target.checked })}
                />
                <label htmlFor="pe-demo">{t('pe_is_demo')}</label>
              </div>
            </div>
            {saveError ? (
              <p className="form-error" role="alert">
                {t(localisedErrorKey(saveError))}
              </p>
            ) : null}
            <div className="viq-actions">
              <button type="submit" className="btn-primary" disabled={saving}>
                {t('pe_save')}
              </button>
              {!isNew ? (
                confirmDelete ? (
                  <>
                    <button type="button" className="btn-secondary" onClick={() => deleteMutation.mutate()} disabled={deleteMutation.isPending}>
                      {t('pe_delete_confirm')}
                    </button>
                    <button type="button" className="btn-link" onClick={() => setConfirmDelete(false)}>
                      {t('cyc_cancel')}
                    </button>
                  </>
                ) : (
                  <button type="button" className="btn-link" onClick={() => setConfirmDelete(true)}>
                    {t('pe_delete')}
                  </button>
                )
              ) : null}
            </div>
          </form>
        </div>
      </div>

      {isNew ? (
        <p className="viq-empty">{t('pe_save_first')}</p>
      ) : (
        <PackagesEditor
          projectId={projectId as string}
          packages={projectQuery.data?.packages ?? []}
          categories={categoriesQuery.data ?? []}
        />
      )}
    </div>
  );
}

function PackagesEditor({
  projectId,
  packages,
  categories,
}: {
  projectId: string;
  packages: WorkPackage[];
  categories: Awaited<ReturnType<typeof listCategories>>;
}) {
  const { t, locale } = useLocale();
  const queryClient = useQueryClient();
  const invalidate = () => queryClient.invalidateQueries({ queryKey: ['project', projectId] });

  const [editingId, setEditingId] = useState<string | 'new' | null>(null);
  const [form, setForm] = useState<PackageFormState>(emptyPackageForm(categories[0]?.code ?? ''));
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);

  const createMutation = useMutation({
    mutationFn: () =>
      createPackage(
        { project_id: projectId },
        {
          category_code: form.category_code,
          estimated_value: Number(form.estimated_value || 0),
          min_class: form.min_class,
          required_certs: form.required_certs,
          notes: form.notes || undefined,
        },
      ),
    onSuccess: () => {
      invalidate();
      setEditingId(null);
    },
  });

  const patchMutation = useMutation({
    mutationFn: (packageId: string) =>
      patchPackage(
        { project_id: projectId, package_id: packageId },
        {
          category_code: form.category_code,
          estimated_value: Number(form.estimated_value || 0),
          min_class: form.min_class,
          required_certs: form.required_certs,
          notes: form.notes || undefined,
        },
      ),
    onSuccess: () => {
      invalidate();
      setEditingId(null);
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (packageId: string) => deletePackage({ project_id: projectId, package_id: packageId }),
    onSuccess: () => {
      invalidate();
      setConfirmDeleteId(null);
    },
  });

  const startNew = () => {
    setForm(emptyPackageForm(categories[0]?.code ?? ''));
    setEditingId('new');
  };

  const startEdit = (pkg: WorkPackage) => {
    setForm({
      category_code: pkg.category.code,
      estimated_value: String(pkg.estimated_value),
      min_class: pkg.min_class,
      required_certs: pkg.required_certs ?? [],
      notes: pkg.notes ?? '',
    });
    setEditingId(pkg.id);
  };

  const toggleCert = (cert: string) => {
    setForm((current) => ({
      ...current,
      required_certs: current.required_certs.includes(cert)
        ? current.required_certs.filter((c) => c !== cert)
        : [...current.required_certs, cert],
    }));
  };

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault();
    if (editingId === 'new') createMutation.mutate();
    else if (editingId) patchMutation.mutate(editingId);
  };

  const saveError = editingId === 'new' ? createMutation.error : patchMutation.error;

  return (
    <div className="viq-card">
      <div className="viq-card-head">
        <div>
          <h3>{t('pe_packages_title')}</h3>
        </div>
        <button type="button" className="btn-primary" onClick={startNew}>
          {t('pe_package_new')}
        </button>
      </div>
      <div className="viq-card-body viq-tight">
        <div className="viq-table-wrap">
          <table className="viq-table">
            <thead>
              <tr>
                <th>{t('pe_package_category')}</th>
                <th className="viq-r">{t('pe_package_value')}</th>
                <th>{t('pe_package_min_class')}</th>
                <th>{t('pe_package_certs')}</th>
                <th aria-hidden="true" />
              </tr>
            </thead>
            <tbody>
              {packages.map((pkg) => (
                <tr key={pkg.id}>
                  <td>{locale === 'en' ? pkg.category.name_en : pkg.category.name_az}</td>
                  <td className="viq-r viq-mono">{formatMoney(pkg.estimated_value, locale)}</td>
                  <td>
                    <ClassBadge cls={pkg.min_class} />
                  </td>
                  <td>
                    {(pkg.required_certs ?? []).length > 0 ? (pkg.required_certs ?? []).map((c) => t(c)).join(', ') : '—'}
                  </td>
                  <td>
                    <div className="viq-actions">
                      <button type="button" className="btn-link" onClick={() => startEdit(pkg)}>
                        {t('pe_package_edit')}
                      </button>
                      {confirmDeleteId === pkg.id ? (
                        <>
                          <button type="button" className="btn-link" onClick={() => deleteMutation.mutate(pkg.id)}>
                            {t('pe_package_delete_confirm')}
                          </button>
                          <button type="button" className="btn-link" onClick={() => setConfirmDeleteId(null)}>
                            {t('cyc_cancel')}
                          </button>
                        </>
                      ) : (
                        <button type="button" className="btn-link" onClick={() => setConfirmDeleteId(pkg.id)}>
                          {t('pe_package_delete')}
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {packages.length === 0 ? <p className="viq-empty">{t('pe_packages_empty')}</p> : null}
      </div>

      {editingId ? (
        <div className="viq-card-body">
          <form onSubmit={handleSubmit} noValidate>
            <div className="viq-form-grid">
              <div className="field">
                <label htmlFor="pkg-category">{t('pe_package_category')}</label>
                <select
                  id="pkg-category"
                  required
                  value={form.category_code}
                  onChange={(event) => setForm({ ...form, category_code: event.target.value })}
                >
                  {categories.map((category) => (
                    <option key={category.id} value={category.code}>
                      {locale === 'en' ? category.name_en : category.name_az}
                    </option>
                  ))}
                </select>
              </div>
              <div className="field">
                <label htmlFor="pkg-value">{t('pe_package_value')}</label>
                <input
                  id="pkg-value"
                  type="number"
                  min={0}
                  required
                  value={form.estimated_value}
                  onChange={(event) => setForm({ ...form, estimated_value: event.target.value })}
                />
              </div>
              <div className="field">
                <label htmlFor="pkg-class">{t('pe_package_min_class')}</label>
                <select
                  id="pkg-class"
                  value={form.min_class}
                  onChange={(event) => setForm({ ...form, min_class: event.target.value as PackageFormState['min_class'] })}
                >
                  {CLASSES.map((cls) => (
                    <option key={cls} value={cls}>
                      {cls}
                    </option>
                  ))}
                </select>
              </div>
              <div className="viq-field-span">
                <span id="pkg-certs-label">{t('pe_package_certs')}</span>
                <div className="viq-chip-list" role="group" aria-labelledby="pkg-certs-label" style={{ marginTop: 6 }}>
                  {CERTS.map((cert) => (
                    <label key={cert} className="viq-chip" data-checked={form.required_certs.includes(cert)}>
                      <input type="checkbox" checked={form.required_certs.includes(cert)} onChange={() => toggleCert(cert)} />
                      {t(cert)}
                    </label>
                  ))}
                </div>
              </div>
              <div className="viq-field-span field">
                <label htmlFor="pkg-notes">{t('pe_package_notes')}</label>
                <textarea id="pkg-notes" value={form.notes} onChange={(event) => setForm({ ...form, notes: event.target.value })} />
              </div>
            </div>
            {saveError ? (
              <p className="form-error" role="alert">
                {t(localisedErrorKey(saveError))}
              </p>
            ) : null}
            <div className="viq-actions">
              <button type="submit" className="btn-primary" disabled={createMutation.isPending || patchMutation.isPending}>
                {t('pe_package_save')}
              </button>
              <button type="button" className="btn-secondary" onClick={() => setEditingId(null)}>
                {t('pe_package_cancel')}
              </button>
            </div>
          </form>
        </div>
      ) : null}

      {deleteMutation.error instanceof ApiError ? (
        <p className="form-error" role="alert" style={{ padding: '0 20px 16px' }}>
          {t(localisedErrorKey(deleteMutation.error))}
        </p>
      ) : null}
    </div>
  );
}
