import { Card, CardContent } from "@/components/ui/card";
import type { ComparisonResult } from "@/lib/api-client";

/** A matrix over already-stored component scores - no recomputation (ARCHITECTURE.md section 6). */
export function ComparisonMatrix({ result }: { result: ComparisonResult }) {
  if (result.rows.length === 0) return null;

  const componentKeys = Array.from(
    new Set(result.rows.flatMap((row) => Object.keys(row.components))),
  );

  return (
    <Card>
      <CardContent className="overflow-x-auto p-4">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border-strong text-left text-ink-subtle">
              <th className="py-2 pr-4 font-medium">Candidate</th>
              <th className="py-2 pr-4 font-medium">Overall</th>
              {componentKeys.map((key) => (
                <th key={key} className="py-2 pr-4 font-medium capitalize">
                  {key.replace(/_/g, " ")}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {result.rows.map((row) => (
              <tr key={row.candidate_id} className="border-b border-border last:border-0">
                <td className="py-2 pr-4 text-ink">{row.candidate_id.slice(0, 8)}</td>
                <td className="py-2 pr-4 font-semibold tabular-nums text-ink">
                  {Math.round(row.overall)}
                </td>
                {componentKeys.map((key) => (
                  <td key={key} className="py-2 pr-4 tabular-nums text-ink-muted">
                    {row.components[key] !== undefined ? Math.round(row.components[key]) : "—"}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </CardContent>
    </Card>
  );
}
