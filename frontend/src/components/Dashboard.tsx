import React, { useEffect, useState } from "react";
import { RevenueSummary } from "./RevenueSummary";
import { SecureAPI } from "../lib/secureApi";

interface Property {
  id: string;
  name: string;
  timezone: string;
}

const Dashboard: React.FC = () => {
  const [properties, setProperties] = useState<Property[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await SecureAPI.getProperties();
        if (!cancelled) setProperties(res.data || []);
      } catch (err) {
        if (!cancelled) setError('Failed to load properties');
        console.error(err);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="min-h-full bg-paper">
      <div className="max-w-7xl mx-auto px-4 lg:px-8 py-8 lg:py-12">
        <header className="mb-10 flex items-baseline justify-between border-b border-rule pb-5">
          <div>
            <p className="font-sans text-[10px] font-medium uppercase tracking-[0.25em] text-meta mb-2">
              Revenue overview
            </p>
            <h1 className="font-serif text-3xl lg:text-4xl text-ink tracking-tight">
              Portfolio ledger
            </h1>
          </div>
          <p className="font-sans text-xs text-meta hidden sm:block max-w-xs text-right">
            Lifetime revenue and month-by-month activity for each property in your portfolio.
          </p>
        </header>

        {loading && (
          <p className="font-sans text-sm text-meta">Loading your properties&hellip;</p>
        )}
        {error && (
          <p className="font-sans text-sm text-red-700">{error}</p>
        )}
        {!loading && !error && properties.length === 0 && (
          <p className="font-sans text-sm text-meta">
            No properties are linked to this account yet.
          </p>
        )}

        {properties.length > 0 && (
          <section className="grid gap-6 grid-cols-1 lg:grid-cols-2 xl:grid-cols-3">
            {properties.map((p) => (
              <RevenueSummary
                key={p.id}
                propertyId={p.id}
                propertyName={p.name}
                timezone={p.timezone}
              />
            ))}
          </section>
        )}
      </div>
    </div>
  );
};

export default Dashboard;
