import { useId, useState } from 'react';
import type { FormEvent } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { listCategories } from '../../api/admin';
import { createContact, patchVendor, setVendorCategories } from '../../api/vendors';
import type { Body } from '../../api/http';
import { useLocale } from '../../i18n/LocaleProvider';
import { localisedErrorKey } from '../auth/errorMessage';
import './vendor.css';
import { useVendorId, useVendorProfile, vendorKey } from './hooks';
import type { VendorDetail } from './hooks';

type VendorPatchBody = Body<'patchVendor'>;
type ContactRow = NonNullable<VendorDetail['contacts']>[number];

type IdentityField = 'legal_name' | 'voen' | 'legal_form' | 'registration_year' | 'address' | 'region' | 'website';

const IDENTITY_FIELDS: { key: IdentityField; labelKey: string; type: 'text' | 'number' }[] = [
  { key: 'legal_name', labelKey: 'field_legal_name', type: 'text' },
  { key: 'voen', labelKey: 'field_voen', type: 'text' },
  { key: 'legal_form', labelKey: 'field_legal_form', type: 'text' },
  { key: 'registration_year', labelKey: 'field_registration_year', type: 'number' },
  { key: 'address', labelKey: 'field_address', type: 'text' },
  { key: 'region', labelKey: 'field_region', type: 'text' },
  { key: 'website', labelKey: 'field_website', type: 'text' },
];

export function VendorProfile() {
  const { t } = useLocale();
  const vendorId = useVendorId();
  const profile = useVendorProfile(vendorId);

  if (profile.isLoading) return <div className="card vp-empty">{t('vp_loading')}</div>;
  if (profile.isError || !profile.data) {
    return (
      <div className="card form-error" role="alert">
        {t(localisedErrorKey(profile.error))}
      </div>
    );
  }

  const vendor = profile.data;
  const locked = vendor.status === 'prequalified';

  return (
    <div className="vp-stack">
      <IdentityCard vendorId={vendorId!} vendor={vendor} locked={locked} />
      <ContactsCard vendorId={vendorId!} contacts={vendor.contacts ?? []} />
      <CategoriesCard vendorId={vendorId!} current={vendor.categories ?? []} />
      <div className="card">
        <div className="vp-card-head">
          <h3>{t('vp_bank')}</h3>
        </div>
        <dl className="vp-field-static">
          <dt>{t('field_iban')}</dt>
          <dd className="mono">{String(vendor.current_fields?.['A.20'] ?? '—')}</dd>
        </dl>
        <p className="muted" style={{ fontSize: 12, marginTop: 8 }}>
          {t('vp_bank_note')}
        </p>
      </div>
    </div>
  );
}

function IdentityCard({
  vendorId,
  vendor,
  locked,
}: {
  vendorId: string;
  vendor: NonNullable<ReturnType<typeof useVendorProfile>['data']>;
  locked: boolean;
}) {
  const { t } = useLocale();
  const queryClient = useQueryClient();
  const [saved, setSaved] = useState<IdentityField | null>(null);
  const patch = useMutation({
    mutationFn: (changes: VendorPatchBody) => patchVendor({ vendor_id: vendorId }, changes),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: vendorKey(vendorId) }),
  });

  return (
    <div className="card">
      <div className="vp-card-head">
        <h3>{t('vp_title')}</h3>
      </div>
      <p className="muted" style={{ marginTop: -8, marginBottom: 16 }}>
        {t('vp_sub')}
      </p>
      {locked ? <p className="vp-table-hint" data-ok="false">{t('vp_locked')}</p> : null}
      <div className="vp-grid-2">
        {IDENTITY_FIELDS.map((field) => (
          <IdentityInput
            key={field.key}
            field={field}
            value={vendor[field.key]}
            disabled={locked || patch.isPending}
            onSave={(value) => {
              patch.mutate({ [field.key]: value } as VendorPatchBody);
              setSaved(field.key);
            }}
          />
        ))}
      </div>
      {saved && patch.isSuccess ? (
        <p className="vp-row-saved" role="status">
          {t('vp_saved')}
        </p>
      ) : null}
      {patch.isError ? (
        <p className="form-error" role="alert">
          {t(localisedErrorKey(patch.error))}
        </p>
      ) : null}
    </div>
  );
}

function IdentityInput({
  field,
  value,
  disabled,
  onSave,
}: {
  field: { key: IdentityField; labelKey: string; type: 'text' | 'number' };
  value: string | number | null | undefined;
  disabled: boolean;
  onSave: (value: string | number) => void;
}) {
  const { t } = useLocale();
  const id = useId();
  const [draft, setDraft] = useState(value == null ? '' : String(value));

  return (
    <div className="field">
      <label htmlFor={id}>{t(field.labelKey)}</label>
      <input
        id={id}
        type={field.type}
        value={draft}
        disabled={disabled}
        onChange={(event) => setDraft(event.target.value)}
        onBlur={() => {
          if (draft.trim() === '' || draft === String(value ?? '')) return;
          onSave(field.type === 'number' ? Number(draft) : draft);
        }}
      />
    </div>
  );
}

function ContactsCard({
  vendorId,
  contacts,
}: {
  vendorId: string;
  contacts: ContactRow[];
}) {
  const { t } = useLocale();
  const queryClient = useQueryClient();
  const [name, setName] = useState('');
  const [position, setPosition] = useState('');
  const [phone, setPhone] = useState('');
  const [email, setEmail] = useState('');

  const create = useMutation({
    mutationFn: () =>
      createContact({ vendor_id: vendorId }, { name, position, phone, email, is_primary: contacts.length === 0 }),
    onSuccess: () => {
      setName('');
      setPosition('');
      setPhone('');
      setEmail('');
      void queryClient.invalidateQueries({ queryKey: vendorKey(vendorId) });
    },
  });

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault();
    if (!name.trim()) return;
    create.mutate();
  };

  return (
    <div className="card">
      <div className="vp-card-head">
        <h3>{t('vp_contacts')}</h3>
      </div>
      {contacts.length === 0 ? (
        <p className="vp-empty">{t('vp_no_contacts')}</p>
      ) : (
        <ul className="vp-next-list">
          {contacts.map((contact) => (
            <li key={contact.id} className="vp-next-item">
              <span>
                <strong>{contact.name}</strong>
                {contact.position ? ` · ${contact.position}` : ''}
                {contact.phone ? ` · ${contact.phone}` : ''}
                {contact.email ? ` · ${contact.email}` : ''}
              </span>
              {contact.is_primary ? (
                <span className="vp-pill" data-tone="accent">
                  {t('vp_primary')}
                </span>
              ) : null}
            </li>
          ))}
        </ul>
      )}
      <form className="vp-grid-2" style={{ marginTop: 16 }} onSubmit={handleSubmit}>
        <div className="field">
          <label htmlFor="contact-name">{t('field_contact_name')}</label>
          <input id="contact-name" value={name} onChange={(event) => setName(event.target.value)} required />
        </div>
        <div className="field">
          <label htmlFor="contact-position">{t('field_position')}</label>
          <input id="contact-position" value={position} onChange={(event) => setPosition(event.target.value)} />
        </div>
        <div className="field">
          <label htmlFor="contact-phone">{t('field_phone')}</label>
          <input id="contact-phone" value={phone} onChange={(event) => setPhone(event.target.value)} />
        </div>
        <div className="field">
          <label htmlFor="contact-email">{t('field_email')}</label>
          <input
            id="contact-email"
            type="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
          />
        </div>
        <div style={{ gridColumn: '1 / -1' }}>
          <button type="submit" className="btn-secondary" disabled={create.isPending || !name.trim()}>
            {t('vp_add_contact')}
          </button>
        </div>
        {create.isError ? (
          <p className="form-error" role="alert" style={{ gridColumn: '1 / -1' }}>
            {t(localisedErrorKey(create.error))}
          </p>
        ) : null}
      </form>
    </div>
  );
}

function CategoriesCard({
  vendorId,
  current,
}: {
  vendorId: string;
  current: { category: { code: string; name_az: string; name_en: string; kind: 'work' | 'material' }; confirmed: boolean }[];
}) {
  const { t, locale } = useLocale();
  const queryClient = useQueryClient();
  const catalogue = useQuery({
    queryKey: ['categories', 'all'],
    queryFn: () => listCategories(),
  });
  const [selected, setSelected] = useState<Set<string>>(() => new Set(current.map((row) => row.category.code)));
  const confirmedByCode = new Map(current.map((row) => [row.category.code, row.confirmed]));

  const save = useMutation({
    mutationFn: () => setVendorCategories({ vendor_id: vendorId }, { category_codes: [...selected] }),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: vendorKey(vendorId) }),
  });

  const toggle = (code: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(code)) next.delete(code);
      else next.add(code);
      return next;
    });
  };

  const work = (catalogue.data ?? []).filter((category) => category.kind === 'work');
  const material = (catalogue.data ?? []).filter((category) => category.kind === 'material');

  return (
    <div className="card">
      <div className="vp-card-head">
        <h3>{t('th_cats')}</h3>
      </div>
      <p className="muted" style={{ marginTop: -8, marginBottom: 12 }}>
        {t('cats_note')}
      </p>
      <CategoryGroup
        heading={t('vp_kind_work')}
        categories={work}
        selected={selected}
        confirmedByCode={confirmedByCode}
        locale={locale}
        onToggle={toggle}
      />
      <CategoryGroup
        heading={t('vp_kind_material')}
        categories={material}
        selected={selected}
        confirmedByCode={confirmedByCode}
        locale={locale}
        onToggle={toggle}
      />
      <button
        type="button"
        className="btn-secondary"
        style={{ marginTop: 12 }}
        disabled={save.isPending}
        onClick={() => save.mutate()}
      >
        {t('vp_save')}
      </button>
      {save.isSuccess ? (
        <p className="vp-row-saved" role="status">
          {t('vp_saved')}
        </p>
      ) : null}
    </div>
  );
}

function CategoryGroup({
  heading,
  categories,
  selected,
  confirmedByCode,
  locale,
  onToggle,
}: {
  heading: string;
  categories: { code: string; name_az: string; name_en: string }[];
  selected: Set<string>;
  confirmedByCode: Map<string, boolean>;
  locale: string;
  onToggle: (code: string) => void;
}) {
  const { t } = useLocale();
  if (categories.length === 0) return null;
  return (
    <div style={{ marginBottom: 14 }}>
      <div className="vp-row-header" style={{ padding: '4px 0' }}>
        {heading}
      </div>
      <div className="vp-chip-list">
        {categories.map((category) => (
          <label key={category.code} className="vp-chip" data-checked={selected.has(category.code) ? 'true' : 'false'}>
            <input
              type="checkbox"
              checked={selected.has(category.code)}
              onChange={() => onToggle(category.code)}
            />
            {locale === 'az' ? category.name_az : category.name_en}
            {confirmedByCode.get(category.code) ? ` · ${t('vp_confirmed')}` : ''}
          </label>
        ))}
      </div>
    </div>
  );
}
