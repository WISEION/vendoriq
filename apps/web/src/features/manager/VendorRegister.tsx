/**
 * Screen 16 — vendor register (`/vendors`), spec §5, §8.
 *
 * Filter by type/category/class/status/region, search by name or VÖEN, export the current
 * filter to Excel. Every filter is a query parameter `listVendors`/`exportVendors` already
 * accept — nothing is filtered client-side, so the export always matches what's on screen
 * (contract note on `exportVendors`).
 */
import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link } from '@tanstack/react-router';
import { exportVendors, listVendors } from '../../api/vendors';
import { listCategories } from '../../api/admin';
import { useLocale } from '../../i18n/LocaleProvider';
import type { Locale } from '../../i18n/LocaleProvider';
import { ClassPill, Card, ErrorCard, LoadingCard, StatusPill, formatAmount, vendorPath } from './shared';
import './manager.css';

const CLASSES = ['A', 'B', 'C', 'D', 'F', 'KO'] as const;
const PAGE_SIZE = 25;

function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

export function VendorRegister() {
  const { t, locale } = useLocale();
  const [type, setType] = useState<'all' | 'sub' | 'sup'>('all');
  const [category, setCategory] = useState('');
  const [cls, setCls] = useState('');
  const [region, setRegion] = useState('');
  const [q, setQ] = useState('');
  const [page, setPage] = useState(1);
  const [exporting, setExporting] = useState(false);

  const categories = useQuery({ queryKey: ['categories'], queryFn: () => listCategories() });

  const query = {
    page,
    page_size: PAGE_SIZE,
    ...(type !== 'all' ? { type } : {}),
    ...(category ? { category: [category] } : {}),
    ...(cls ? { class: [cls as (typeof CLASSES)[number]] } : {}),
    ...(region ? { region } : {}),
    ...(q ? { q } : {}),
  } as const;

  const vendors = useQuery({
    queryKey: ['vendors', query],
    queryFn: () => listVendors(query),
  });

  async function handleExport() {
    setExporting(true);
    try {
      const blob = await exportVendors({
        ...(type !== 'all' ? { type } : {}),
        ...(category ? { category: [category] } : {}),
        ...(cls ? { class: [cls as (typeof CLASSES)[number]] } : {}),
        ...(region ? { region } : {}),
        ...(q ? { q } : {}),
        locale: locale as Locale,
      });
      downloadBlob(blob, 'vendors.xlsx');
    } finally {
      setExporting(false);
    }
  }

  const totalPages = vendors.data ? Math.max(1, Math.ceil(vendors.data.total / PAGE_SIZE)) : 1;

  return (
    <Card bodyClassName="mgr-card-bd-tight">
      <div className="mgr-card-hd" style={{ flexWrap: 'wrap', gap: 10 }}>
        <div className="mgr-filters">
          <div className="mgr-btn-group" role="group" aria-label={t('field_type')}>
            {(['all', 'sub', 'sup'] as const).map((value) => (
              <button
                key={value}
                type="button"
                className="mgr-btn mgr-btn-sm"
                aria-pressed={type === value}
                style={type === value ? { background: 'var(--accent-soft)', color: 'var(--accent)' } : undefined}
                onClick={() => {
                  setType(value);
                  setPage(1);
                }}
              >
                {t(`f_${value}`)}
              </button>
            ))}
          </div>
          <input
            type="text"
            aria-label={t('f_search')}
            placeholder={t('f_search')}
            value={q}
            onChange={(event) => {
              setQ(event.target.value);
              setPage(1);
            }}
            style={{ width: 220 }}
          />
          <select
            aria-label={t('f_cat')}
            value={category}
            onChange={(event) => {
              setCategory(event.target.value);
              setPage(1);
            }}
          >
            <option value="">
              {t('f_cat')}: {t('f_all')}
            </option>
            {(categories.data ?? []).map((c) => (
              <option key={c.code} value={c.code}>
                {locale === 'az' ? c.name_az : c.name_en}
              </option>
            ))}
          </select>
          <select
            aria-label={t('f_class')}
            value={cls}
            onChange={(event) => {
              setCls(event.target.value);
              setPage(1);
            }}
          >
            <option value="">
              {t('f_class')}: {t('f_all')}
            </option>
            {CLASSES.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
          <input
            type="text"
            aria-label={t('th_region')}
            placeholder={t('th_region')}
            value={region}
            onChange={(event) => {
              setRegion(event.target.value);
              setPage(1);
            }}
            style={{ width: 140 }}
          />
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <span className="muted small">
            {vendors.data?.total ?? 0} {t('vendors_n')}
          </span>
          <button
            type="button"
            className="mgr-btn"
            onClick={handleExport}
            disabled={exporting}
          >
            {exporting ? `${t('mgr_export')}…` : t('mgr_export')}
          </button>
        </div>
      </div>

      {vendors.isLoading ? (
        <LoadingCard />
      ) : vendors.isError ? (
        <ErrorCard message={String(vendors.error)} />
      ) : vendors.data && vendors.data.items.length > 0 ? (
        <div className="mgr-table-wrap">
          <table className="mgr-table">
            <thead>
              <tr>
                <th>{t('th_vendor')}</th>
                <th>{t('th_type')}</th>
                <th className="mgr-r">{t('th_score')}</th>
                <th>{t('th_class')}</th>
                <th>{t('th_status')}</th>
                <th>{t('th_source')}</th>
                <th>{t('th_updated')}</th>
              </tr>
            </thead>
            <tbody>
              {vendors.data.items.map((vendor) => (
                <tr key={vendor.id} className="mgr-row-link">
                  <td>
                    <Link to={vendorPath(vendor.id)}>
                      <b>{vendor.legal_name}</b>
                    </Link>
                    <div className="mgr-src">{vendor.voen ?? '—'}</div>
                  </td>
                  <td>{t(`type_${vendor.type}`)}</td>
                  <td className="mgr-r mono">
                    {vendor.latest_score != null ? formatAmount(vendor.latest_score) : '—'}
                  </td>
                  <td>
                    <ClassPill cls={vendor.latest_class} />
                  </td>
                  <td>
                    <StatusPill status={vendor.status} />
                  </td>
                  <td>
                    <span className="mgr-src">
                      {vendor.primary_source ? t(`src_${vendor.primary_source}`) : '—'}
                    </span>
                  </td>
                  <td className="mono small">{vendor.updated_at.slice(0, 10)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="mgr-empty">{t('none')}</div>
      )}

      {vendors.data && totalPages > 1 ? (
        <div className="mgr-pager">
          <button
            type="button"
            className="mgr-btn mgr-btn-sm"
            disabled={page <= 1}
            onClick={() => setPage((p) => Math.max(1, p - 1))}
          >
            ←
          </button>
          <span>
            {page} / {totalPages}
          </span>
          <button
            type="button"
            className="mgr-btn mgr-btn-sm"
            disabled={page >= totalPages}
            onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
          >
            →
          </button>
        </div>
      ) : null}
      <p className="small muted" style={{ padding: '0 18px 14px' }}>
        {t('cats_note')}
      </p>
    </Card>
  );
}
