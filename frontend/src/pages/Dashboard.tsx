import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { fetchRepoRemote, fetchRepoStats, fetchSessionGraph } from "../api";
import { RepoStatsPanel } from "../components/RepoStatsPanel";
import type { SessionEvent } from "../types";
import { Explorer } from "./Explorer";
import AuthorChip from "../components/AuthChip";
import { ClaudeExplanationPanel } from '../components/ClaudeExplanationPanel';
import { ToolsInvokedPanel } from '../components/ToolsInvokedPanel';
import { useClaudeSession } from "../hooks/useClaudeSession";

interface DashboardProps {
  event: SessionEvent | null;
}

function SessionDashboard({
  event,
  onShowFullStats,
}: {
  event: SessionEvent;
  onShowFullStats: () => void;
}) {
  const { data, isLoading, error } = useQuery({
    queryKey: ["session-graph", event.node_ids],
    queryFn: () => fetchSessionGraph(event.node_ids),
  });
  const { data: remote } = useQuery({
    queryKey: ["repo-remote"],
    queryFn: fetchRepoRemote,
  });
  const githubBase = remote?.github_base ?? null;
  const { latestEvent, connected } = useClaudeSession();
  

  return (
        <div style={{ display: 'flex', flex:1, flexDirection: 'row', height: '100vh' }}>

    <div style={{ flex: 0.7, minHeight: 0, marginBottom: 24 }}>
    <div style={{ padding: 24 }} data-testid="session-dashboard">
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "baseline",
        }}
      >
        <h2>Query Results</h2>
        
      </div>
      <div style={{ fontSize: 13, color: "#6b7280", marginBottom: 16 }}>
        {event.question}
      </div>

      {isLoading && <div>Loading query results…</div>}
      {error && <div>Failed to load query results.</div>}
      {data && (
        <div style={{ display: "flex", gap: 16, flexWrap: "wrap" }}>
          <div>
            <h3>Cited Files &amp; Symbols</h3>
            <ul data-testid="session-cited-nodes">
              {data.nodes
                .filter((n) => n.type !== "commit" && n.type !== "author")
                .map((n) => (
                  <li key={n.id}>
                    {n.name}
                    {n.attrs.churn != null && (
                      <> — Modified {String(n.attrs.churn)} times</>
                    )}
                    {n.attrs.bus_factor != null && (
                      <>, by {String(n.attrs.bus_factor)} Authors</>
                    )}
                  </li>
                ))}
            </ul>
          </div>
          <div>
            <h3>Related Commits</h3>
            <Explorer event={event} />
          </div>
          <div>
            <h3>Related Authors</h3>
            <div style={{ marginRight: 24, marginLeft: 24 }}>
              {data.nodes
                .filter((n) => n.type === "author")
                .map((n) => {
                  return (
                    <AuthorChip key={n.id} author={n} githubBase={githubBase} />
                  );
                })}
            </div>
          </div>
        </div>
      )}
    </div>
    </div>
    <div style={{ flex: 0.3,}}>
      <div style={{ display: "flex", justifyContent: "flex-end", padding: 24, marginTop: 18 }}>
        <button
          style={{
            fontSize: 14,
            padding: "8px 16px",
            borderRadius: 999,
            border: "1px solid #fdba74",
            background: "#fff7ed",
            color: "#9a3412",
            cursor: "pointer",
            marginRight: 4,
            width: 200,
          }}
          onClick={onShowFullStats}
          data-testid="show-full-stats-button"
        >
          Show full repo stats
        </button>
      </div>
        <div style={{flex: 1, borderTop: '1px solid #e5e7eb',borderLeft: '1px solid #e5e7eb'}}>
          <ClaudeExplanationPanel event={latestEvent} connected={connected} />
          <ToolsInvokedPanel event={latestEvent} />
          </div>
        </div>
        </div>
  );
}

export function Dashboard({ event }: DashboardProps) {
  const [showFullStats, setShowFullStats] = useState(false);
  // A new question should always take over the scoped view again, even if
  // the user had previously asked to see the full repo stats.
  const [seenEventTimestamp, setSeenEventTimestamp] = useState(
    event?.timestamp,
  );
  if (event?.timestamp !== seenEventTimestamp) {
    setSeenEventTimestamp(event?.timestamp);
    setShowFullStats(false);
  }

  const { data, isLoading, error } = useQuery({
    queryKey: ["repo-stats"],
    queryFn: fetchRepoStats,
  });

  if (event && !showFullStats) {
    return (
      <SessionDashboard
        event={event}
        onShowFullStats={() => setShowFullStats(true)}
      />
    );
  }

  if (isLoading) return <div>Loading repository stats…</div>;
  if (error || !data) return <div>Failed to load repository stats.</div>;

  return (
    <div style={{ padding: 24 }}>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "baseline",
        }}
      >
        <h2>Repository Stats &amp; Engineering Health</h2>
        {event && (
          <button
            style={{
              fontSize: 14,
              padding: "8px 16px",
              borderRadius: 999,
              border: "1px solid #fdba74",
              background: "#fff7ed",
              color: "#9a3412",
              cursor: "pointer",
              marginRight: 4,
              width: 200,
            }}
            onClick={() => setShowFullStats(false)}
            data-testid="show-session-stats-button"
          >
            Show query results
          </button>
        )}
      </div>
      <RepoStatsPanel data={data} />
    </div>
  );
}
