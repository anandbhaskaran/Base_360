import React, { useEffect, useState } from 'react';
import { SecureAPI } from '../lib/secureApi';

interface Summary {
    property_id: string;
    total_revenue: number;
    currency: string;
    reservations_count: number;
    period: string;
}

interface Bucket {
    year: number;
    month: number;
    total: string;
    count: number;
}

interface RevenueSummaryProps {
    propertyId: string;
    propertyName?: string;
    timezone?: string;
}

const MONTH_FULL = [
    'January', 'February', 'March', 'April', 'May', 'June',
    'July', 'August', 'September', 'October', 'November', 'December',
];

const formatMoney = (value: number | string, currency: string) =>
    `${currency} ${Number(value).toLocaleString(undefined, {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
    })}`;

export const RevenueSummary: React.FC<RevenueSummaryProps> = ({
    propertyId,
    propertyName,
    timezone,
}) => {
    const [summary, setSummary] = useState<Summary | null>(null);
    const [buckets, setBuckets] = useState<Bucket[] | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');

    useEffect(() => {
        let cancelled = false;
        const fetch = async () => {
            setLoading(true);
            setError('');
            try {
                const [s, b] = await Promise.all([
                    SecureAPI.getDashboardSummary(propertyId),
                    SecureAPI.getDashboardBreakdown(propertyId),
                ]);
                if (cancelled) return;
                setSummary(s);
                setBuckets(b?.buckets ?? []);
            } catch (err) {
                if (!cancelled) setError('Failed to load revenue');
                console.error(err);
            } finally {
                if (!cancelled) setLoading(false);
            }
        };
        fetch();
        return () => {
            cancelled = true;
        };
    }, [propertyId]);

    if (loading) {
        return (
            <article className="bg-white border border-rule p-6 flex flex-col gap-4">
                <div className="animate-pulse space-y-3">
                    <div className="h-3 bg-rule w-1/2"></div>
                    <div className="h-8 bg-rule w-3/4"></div>
                    <div className="h-32 bg-rule"></div>
                </div>
            </article>
        );
    }

    if (error || !summary) {
        return (
            <article className="bg-white border border-rule p-6">
                <p className="font-serif text-lg text-ink">{propertyName || propertyId}</p>
                <p className="mt-2 text-sm text-red-700">{error || 'No data'}</p>
            </article>
        );
    }

    const rows = [...(buckets ?? [])].sort(
        (a, b) => b.year - a.year || b.month - a.month
    );
    const maxRow = rows.reduce((m, r) => Math.max(m, Number(r.total)), 0);

    return (
        <article className="bg-white border border-rule p-6 flex flex-col gap-5">
            <header className="flex items-start justify-between gap-3">
                <h3 className="font-serif text-xl text-ink leading-tight tracking-tight">
                    {propertyName || summary.property_id}
                </h3>
                {timezone && (
                    <span className="font-mono text-[10px] uppercase tracking-wider text-meta bg-tag px-2 py-1 whitespace-nowrap">
                        {timezone}
                    </span>
                )}
            </header>

            <div>
                <p className="font-sans text-[10px] font-medium uppercase tracking-[0.2em] text-meta mb-1">
                    Lifetime revenue
                </p>
                <p className="font-mono text-2xl font-medium text-ink tabular-nums">
                    {formatMoney(summary.total_revenue, summary.currency)}
                </p>
                <p className="font-sans text-xs text-meta mt-1">
                    from {summary.reservations_count}{' '}
                    {summary.reservations_count === 1 ? 'stay' : 'stays'}
                </p>
            </div>

            <div>
                <div className="flex items-baseline justify-between border-b border-rule pb-2">
                    <p className="font-sans text-[10px] font-medium uppercase tracking-[0.2em] text-meta">
                        Monthly ledger
                    </p>
                    <p className="font-sans text-[10px] uppercase tracking-widest text-meta">
                        {rows.length} {rows.length === 1 ? 'month' : 'months'}
                    </p>
                </div>

                {rows.length === 0 ? (
                    <p className="font-sans text-xs text-meta pt-3">No activity yet.</p>
                ) : (
                    <ol className="divide-y divide-rule">
                        {rows.map((row) => {
                            const value = Number(row.total);
                            const pct = maxRow > 0 ? (value / maxRow) * 100 : 0;
                            return (
                                <li
                                    key={`${row.year}-${row.month}`}
                                    className="grid grid-cols-[1fr_auto_auto] items-baseline gap-3 py-2.5 relative"
                                >
                                    <span
                                        aria-hidden
                                        className="absolute left-0 right-0 bottom-0 h-[2px] bg-ink/10"
                                        style={{ width: `${pct}%` }}
                                    />
                                    <span className="font-sans text-sm text-ink">
                                        {MONTH_FULL[row.month - 1]} {row.year}
                                    </span>
                                    <span className="font-mono text-sm text-ink tabular-nums">
                                        {formatMoney(value, summary.currency)}
                                    </span>
                                    <span className="font-mono text-xs text-meta tabular-nums w-16 text-right">
                                        {row.count} {row.count === 1 ? 'stay' : 'stays'}
                                    </span>
                                </li>
                            );
                        })}
                    </ol>
                )}
            </div>
        </article>
    );
};
