import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { LocaleProvider } from '../../i18n/LocaleProvider';
import { ClassBadge, StatePill } from './StatePill';

function renderWithLocale(node: React.ReactElement) {
  return render(<LocaleProvider>{node}</LocaleProvider>);
}

describe('StatePill', () => {
  it('always renders the state as text, not colour alone', () => {
    renderWithLocale(<StatePill state="go" />);
    expect(screen.getByText('GO')).toBeInTheDocument();
  });

  it('renders the conditional and no-go labels', () => {
    const { rerender } = renderWithLocale(<StatePill state="cond" />);
    expect(screen.getByText('ŞƏRTİ')).toBeInTheDocument();
    rerender(
      <LocaleProvider>
        <StatePill state="nogo" />
      </LocaleProvider>,
    );
    expect(screen.getByText('NO-GO')).toBeInTheDocument();
  });

  it('renders a neutral placeholder when the project has never been matched', () => {
    renderWithLocale(<StatePill state={null} />);
    expect(screen.getByText('—')).toBeInTheDocument();
  });
});

describe('ClassBadge', () => {
  it('renders the class letter', () => {
    renderWithLocale(<ClassBadge cls="A" />);
    expect(screen.getByText('A')).toBeInTheDocument();
  });

  it('renders an em dash when the class is unknown', () => {
    renderWithLocale(<ClassBadge cls={null} />);
    expect(screen.getByText('—')).toBeInTheDocument();
  });
});
