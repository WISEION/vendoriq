import { useState } from 'react';
import { useLocale } from '../../i18n/LocaleProvider';
import { TABLE_COLUMNS } from './fieldCatalog';
import type { FieldRow } from './fieldCatalog';

type Row = Record<string, string>;

function toRows(value: unknown): Row[] {
  if (!Array.isArray(value)) return [];
  return value.map((row) => {
    if (row && typeof row === 'object') {
      const out: Row = {};
      for (const [key, cell] of Object.entries(row as Record<string, unknown>)) {
        out[key] = cell == null ? '' : String(cell);
      }
      return out;
    }
    return {};
  });
}

function emptyRow(code: string): Row {
  const row: Row = {};
  for (const column of TABLE_COLUMNS[code] ?? []) row[column.key] = '';
  return row;
}

function hasContent(row: Row): boolean {
  return Object.values(row).some((cell) => cell.trim() !== '');
}

/**
 * A repeatable-row table field (`C.t1` completed projects, `C.t2` ongoing projects, `G.t1`
 * references) — the Excel form's "cədvəl" columns, edited inline instead of the prototype's
 * placeholder button. `value` is saved as an array of plain objects keyed by column, the
 * same shape `packages/scoring.derive_raw` reads a project row from (`row["value"]` is the
 * contract amount for `C.t1`/`C.t2`).
 */
export function ProjectTable({
  row,
  value,
  minRows = 0,
  disabled,
  onSave,
}: {
  row: FieldRow;
  value: unknown;
  minRows?: number;
  disabled: boolean;
  onSave: (code: string, rows: Row[]) => void;
}) {
  const { t, locale } = useLocale();
  const columns = TABLE_COLUMNS[row.code] ?? [];
  const [rows, setRows] = useState<Row[]>(() => {
    const existing = toRows(value);
    return existing.length > 0 ? existing : [emptyRow(row.code)];
  });

  const commit = (next: Row[]) => {
    setRows(next);
    onSave(row.code, next.filter(hasContent));
  };

  const updateCell = (index: number, key: string, cell: string) => {
    setRows((current) => current.map((r, i) => (i === index ? { ...r, [key]: cell } : r)));
  };

  const filledCount = rows.filter(hasContent).length;
  const belowMinimum = minRows > 0 && filledCount < minRows;

  return (
    <div className="vp-table-field">
      <div className="vp-table-field-head">
        <span className="vp-row-label">
          {locale === 'az' ? row.az : row.en}
          {row.doc ? <span className="mono vp-row-doc"> · {row.doc}</span> : null}
        </span>
        <span className="vp-table-hint" data-ok={belowMinimum ? 'false' : 'true'}>
          {minRows > 0
            ? `${t('vt_rows')}: ${filledCount}/${minRows} ${t('vt_min')}`
            : `${t('vt_rows')}: ${filledCount}`}
        </span>
      </div>
      <div className="vp-tblwrap">
        <table>
          <caption className="vp-sr-only">{locale === 'az' ? row.az : row.en}</caption>
          <thead>
            <tr>
              {columns.map((column) => (
                <th key={column.key} scope="col">
                  {locale === 'az' ? column.az : column.en}
                </th>
              ))}
              <th scope="col">
                <span className="vp-sr-only">{t('vt_remove')}</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map((tableRow, index) => (
              // Row identity is genuinely positional here — a project row has no id of its
              // own until it is saved, and edits never reorder the list.
              <tr key={`${row.code}-${index}`}>
                {columns.map((column) => {
                  const cellId = `${row.code}-${index}-${column.key}`;
                  return (
                    <td key={column.key}>
                      <label htmlFor={cellId} className="vp-sr-only">
                        {locale === 'az' ? column.az : column.en}
                      </label>
                      <input
                        id={cellId}
                        type={column.type === 'number' ? 'number' : column.type === 'date' ? 'date' : 'text'}
                        value={tableRow[column.key] ?? ''}
                        disabled={disabled}
                        onChange={(event) => updateCell(index, column.key, event.target.value)}
                        onBlur={() => commit(rows)}
                      />
                    </td>
                  );
                })}
                <td>
                  <button
                    type="button"
                    className="btn-link"
                    disabled={disabled || rows.length <= 1}
                    onClick={() => commit(rows.filter((_, i) => i !== index))}
                  >
                    {t('vt_remove')}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <button
        type="button"
        className="btn-secondary"
        style={{ marginTop: 8 }}
        disabled={disabled}
        onClick={() => setRows((current) => [...current, emptyRow(row.code)])}
      >
        {t('vt_add_row')}
      </button>
    </div>
  );
}
