"use client";

import { useState, useEffect } from "react";
import { useApi } from "../../../lib/api";
import PageHeader from "../../../components/fazle/PageHeader";
import StatusBadge from "../../../components/fazle/StatusBadge";

function StatCard({ icon, label, value, color = "fazle" }) {
  return (
    <div className="bg-[#1a1a2e] border border-gray-700/50 rounded-xl p-5">
      <div className="flex items-center gap-3 mb-3">
        <span className="text-2xl">{icon}</span>
        <span className="text-xs text-gray-500 uppercase tracking-wider">
          {label}
        </span>
      </div>
      <p className="text-3xl font-bold text-gray-200">{value ?? "—"}</p>
    </div>
  );
}

function RecentItem({ icon, title, subtitle, badge }) {
  return (
    <div className="flex items-center gap-3 px-4 py-3 hover:bg-gray-800/30 transition-colors rounded-lg">
      <span className="text-lg">{icon}</span>
      <div className="flex-1 min-w-0">
        <p className="text-sm text-gray-200 truncate">{title}</p>
        <p className="text-xs text-gray-500 truncate">{subtitle}</p>
      </div>
      {badge && <StatusBadge status={badge} />}
    </div>
  );
}

export default function FazleOverview() {
  const api = useApi();
  const [stats, setStats] = useState({});
  const [recentMemories, setRecentMemories] = useState([]);
  const [agents, setAgents] = useState([]);
  const [tasks, setTasks] = useState([]);
  const [health, setHealth] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchAll = async () => {
      setLoading(true);
      try {
        const results = await Promise.allSettled([
          api.get("/admin/dashboard/stats"),
          api.get("/admin/agents"),
          api.get("/admin/tasks"),
          api.get("/health"),
        ]);

        if (results[0].status === "fulfilled") setStats(results[0].value);
        if (results[1].status === "fulfilled") {
          const data = results[1].value;
          setAgents(data.agents || data || []);
        }
        if (results[2].status === "fulfilled") {
          const data = results[2].value;
          setTasks(data.tasks || data || []);
        }
        if (results[3].status === "fulfilled") setHealth(results[3].value);
      } catch {
        // Graceful fallback
      } finally {
        setLoading(false);
      }
    };

    fetchAll();
  }, []);

  const activeAgents = Array.isArray(agents)
    ? agents.filter((a) => a.status === "active" || a.enabled).length
    : 0;
  const scheduledTasks = Array.isArray(tasks)
    ? tasks.filter((t) => t.status === "pending" || t.status === "running").length
    : 0;

  return (
    <div className="flex flex-col h-full overflow-y-auto">
      <PageHeader
        title="Fazle AI Control Dashboard"
        description="System overview and management"
      />

      <div className="p-6 space-y-6 pb-20 md:pb-6">
        {/* Stats Grid */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <StatCard
            icon="🤖"
            label="Active Agents"
            value={loading ? "..." : activeAgents}
          />
          <StatCard
            icon="🧠"
            label="Memories"
            value={loading ? "..." : (stats.memory_count ?? "—")}
          />
          <StatCard
            icon="📋"
            label="Scheduled Tasks"
            value={loading ? "..." : scheduledTasks}
          />
          <StatCard
            icon="⚡"
            label="System Status"
            value={loading ? "..." : (health?.status === "ok" ? "Healthy" : "Check")}
          />
        </div>

        {/* Health Details */}
        {health && (
          <div className="bg-[#1a1a2e] border border-gray-700/50 rounded-xl p-5">
            <h3 className="text-sm font-semibold text-gray-200 mb-4">
              System Health
            </h3>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              {Object.entries(health.services || {}).map(([name, status]) => (
                <div
                  key={name}
                  className="flex items-center gap-2 bg-[#0a0a0f] rounded-lg p-3"
                >
                  <div
                    className={`w-2.5 h-2.5 rounded-full ${
                      status === "ok" || status === "healthy" || status === true
                        ? "bg-green-500"
                        : "bg-red-500"
                    }`}
                  />
                  <span className="text-xs text-gray-300 capitalize">
                    {name.replace(/_/g, " ")}
                  </span>
                </div>
              ))}
              {!health.services && (
                <div className="flex items-center gap-2 bg-[#0a0a0f] rounded-lg p-3 col-span-full">
                  <div className="w-2.5 h-2.5 rounded-full bg-green-500" />
                  <span className="text-xs text-gray-300">
                    API: {health.status || "connected"}
                  </span>
                </div>
              )}
            </div>
          </div>
        )}

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Active Agents */}
          <div className="bg-[#1a1a2e] border border-gray-700/50 rounded-xl">
            <div className="p-4 border-b border-gray-700/50">
              <h3 className="text-sm font-semibold text-gray-200">Agents</h3>
            </div>
            <div className="p-2">
              {loading ? (
                <div className="text-center py-6 text-gray-500 text-sm animate-pulse">
                  Loading...
                </div>
              ) : Array.isArray(agents) && agents.length > 0 ? (
                agents.slice(0, 5).map((agent, i) => (
                  <RecentItem
                    key={agent.id || i}
                    icon="🤖"
                    title={agent.name}
                    subtitle={agent.model || agent.description || "Agent"}
                    badge={agent.status || (agent.enabled ? "Active" : "Disabled")}
                  />
                ))
              ) : (
                <p className="text-center py-6 text-gray-500 text-sm">
                  No agents configured
                </p>
              )}
            </div>
          </div>

          {/* Recent Tasks */}
          <div className="bg-[#1a1a2e] border border-gray-700/50 rounded-xl">
            <div className="p-4 border-b border-gray-700/50">
              <h3 className="text-sm font-semibold text-gray-200">
                Recent Tasks
              </h3>
            </div>
            <div className="p-2">
              {loading ? (
                <div className="text-center py-6 text-gray-500 text-sm animate-pulse">
                  Loading...
                </div>
              ) : Array.isArray(tasks) && tasks.length > 0 ? (
                tasks.slice(0, 5).map((task, i) => (
                  <RecentItem
                    key={task.id || i}
                    icon="📋"
                    title={task.title || task.name}
                    subtitle={task.scheduled_at ? new Date(task.scheduled_at).toLocaleString() : task.schedule || ""}
                    badge={task.status}
                  />
                ))
              ) : (
                <p className="text-center py-6 text-gray-500 text-sm">
                  No tasks scheduled
                </p>
              )}
            </div>
          </div>
        </div>

        {/* Quick Actions */}
        <div className="bg-[#1a1a2e] border border-gray-700/50 rounded-xl p-5">
          <h3 className="text-sm font-semibold text-gray-200 mb-4">
            Quick Actions
          </h3>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {[
              { href: "/dashboard/fazle/memory", icon: "🧠", label: "Manage Memory" },
              { href: "/dashboard/fazle/agents", icon: "🤖", label: "Manage Agents" },
              { href: "/dashboard/fazle/tools", icon: "🔧", label: "Manage Tools" },
              { href: "/dashboard/fazle/tasks", icon: "📋", label: "Manage Tasks" },
            ].map((action) => (
              <a
                key={action.href}
                href={action.href}
                className="flex items-center gap-3 bg-[#0a0a0f] hover:bg-gray-800/50 border border-gray-700/50 rounded-lg p-4 transition-colors"
              >
                <span className="text-2xl">{action.icon}</span>
                <span className="text-sm text-gray-300">{action.label}</span>
              </a>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
