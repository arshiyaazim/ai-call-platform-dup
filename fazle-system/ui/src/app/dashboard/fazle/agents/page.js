"use client";

import { useState, useEffect, useCallback } from "react";
import { useApi } from "../../../../lib/api";
import PageHeader from "../../../../components/fazle/PageHeader";
import DataTable from "../../../../components/fazle/DataTable";
import StatusBadge from "../../../../components/fazle/StatusBadge";
import ActionDropdown from "../../../../components/fazle/ActionDropdown";
import ConfirmDialog from "../../../../components/fazle/ConfirmDialog";
import ModalForm, {
  FormInput,
  FormSelect,
  FormTextarea,
  FormActions,
} from "../../../../components/fazle/ModalForm";

const DEFAULT_AGENTS = [
  { id: "conversation", name: "ConversationAgent", model: "gpt-4o-mini", priority: 1, status: "active", description: "Handles natural conversation flow" },
  { id: "memory", name: "MemoryAgent", model: "gpt-4o-mini", priority: 2, status: "active", description: "Manages memory retrieval and storage" },
  { id: "research", name: "ResearchAgent", model: "gpt-4o", priority: 3, status: "active", description: "Web research and information gathering" },
  { id: "task", name: "TaskAgent", model: "gpt-4o-mini", priority: 4, status: "active", description: "Task scheduling and management" },
  { id: "tool", name: "ToolAgent", model: "gpt-4o-mini", priority: 5, status: "active", description: "Tool plugin orchestration" },
];

const MODEL_OPTIONS = [
  { value: "gpt-4o", label: "GPT-4o" },
  { value: "gpt-4o-mini", label: "GPT-4o Mini" },
  { value: "gpt-4-turbo", label: "GPT-4 Turbo" },
  { value: "claude-3-opus", label: "Claude 3 Opus" },
  { value: "claude-3-sonnet", label: "Claude 3 Sonnet" },
  { value: "ollama/llama3", label: "Ollama Llama 3" },
];

export default function AgentManagerPage() {
  const api = useApi();
  const [agents, setAgents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showAddModal, setShowAddModal] = useState(false);
  const [editingAgent, setEditingAgent] = useState(null);
  const [deleteTarget, setDeleteTarget] = useState(null);
  const [error, setError] = useState("");

  const [formData, setFormData] = useState({
    name: "",
    model: "gpt-4o-mini",
    priority: 1,
    description: "",
  });

  const fetchAgents = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.get("/admin/agents");
      setAgents(data.agents || data || []);
    } catch {
      // Use default agents as fallback
      setAgents(DEFAULT_AGENTS);
    } finally {
      setLoading(false);
    }
  }, [api]);

  useEffect(() => {
    fetchAgents();
  }, []);

  const handleAdd = async () => {
    setError("");
    try {
      await api.post("/admin/agents", {
        ...formData,
        status: "active",
      });
      setShowAddModal(false);
      setFormData({ name: "", model: "gpt-4o-mini", priority: 1, description: "" });
      fetchAgents();
    } catch (err) {
      setError(err.message);
    }
  };

  const handleEdit = async () => {
    setError("");
    try {
      await api.put(`/admin/agents/${editingAgent.id}`, {
        ...formData,
        status: editingAgent.status,
      });
      setEditingAgent(null);
      fetchAgents();
    } catch (err) {
      setError(err.message);
    }
  };

  const handleDelete = async () => {
    try {
      await api.del(`/admin/agents/${deleteTarget.id}`);
      setDeleteTarget(null);
      fetchAgents();
    } catch {
      // Remove locally as fallback
      setAgents((prev) => prev.filter((a) => a.id !== deleteTarget.id));
      setDeleteTarget(null);
    }
  };

  const toggleAgent = async (agent) => {
    const newStatus = agent.status === "active" ? "disabled" : "active";
    try {
      await api.put(`/admin/agents/${agent.id}`, {
        ...agent,
        status: newStatus,
      });
      fetchAgents();
    } catch {
      // Update locally
      setAgents((prev) =>
        prev.map((a) => (a.id === agent.id ? { ...a, status: newStatus } : a))
      );
    }
  };

  const openEdit = (agent) => {
    setFormData({
      name: agent.name,
      model: agent.model || "gpt-4o-mini",
      priority: agent.priority || 1,
      description: agent.description || "",
    });
    setEditingAgent(agent);
    setError("");
  };

  const columns = [
    {
      key: "name",
      label: "Agent Name",
      render: (val) => <span className="font-medium text-gray-200">{val}</span>,
    },
    {
      key: "status",
      label: "Status",
      width: "120px",
      render: (val) => <StatusBadge status={val || "active"} />,
    },
    {
      key: "model",
      label: "Model",
      width: "160px",
      render: (val) => (
        <span className="text-xs text-gray-400 font-mono bg-gray-800/50 px-2 py-1 rounded">
          {val || "—"}
        </span>
      ),
    },
    {
      key: "priority",
      label: "Priority",
      width: "90px",
      render: (val) => (
        <span className="text-gray-400">{val ?? "—"}</span>
      ),
    },
    {
      key: "_actions",
      label: "",
      width: "50px",
      render: (_, row) => (
        <ActionDropdown
          actions={[
            { label: "Edit", icon: "✏️", onClick: () => openEdit(row) },
            {
              label: row.status === "active" ? "Disable" : "Enable",
              icon: row.status === "active" ? "⏸️" : "▶️",
              onClick: () => toggleAgent(row),
            },
            {
              label: "Delete",
              icon: "🗑️",
              onClick: () => setDeleteTarget(row),
              danger: true,
            },
          ]}
        />
      ),
    },
  ];

  return (
    <div className="flex flex-col h-full overflow-hidden">
      <PageHeader
        title="Agent Manager"
        description="Configure and manage AI agents"
        actions={
          <button
            onClick={() => {
              setFormData({ name: "", model: "gpt-4o-mini", priority: 1, description: "" });
              setShowAddModal(true);
              setError("");
            }}
            className="bg-fazle-600 hover:bg-fazle-700 text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors"
          >
            + Add New
          </button>
        }
      />

      <div className="flex-1 overflow-y-auto pb-20 md:pb-0">
        <DataTable
          columns={columns}
          data={agents}
          loading={loading}
          emptyMessage="No agents configured."
        />
      </div>

      {/* Add Modal */}
      <ModalForm
        open={showAddModal}
        title="Add New Agent"
        onClose={() => setShowAddModal(false)}
        onSubmit={handleAdd}
      >
        <FormInput
          label="Agent Name"
          placeholder="e.g. ResearchAgent"
          value={formData.name}
          onChange={(e) => setFormData({ ...formData, name: e.target.value })}
          required
        />
        <FormSelect
          label="Model"
          options={MODEL_OPTIONS}
          value={formData.model}
          onChange={(e) => setFormData({ ...formData, model: e.target.value })}
        />
        <FormInput
          label="Priority"
          type="number"
          min={1}
          max={10}
          value={formData.priority}
          onChange={(e) =>
            setFormData({ ...formData, priority: parseInt(e.target.value) || 1 })
          }
        />
        <FormTextarea
          label="Description"
          placeholder="What does this agent do?"
          value={formData.description}
          onChange={(e) =>
            setFormData({ ...formData, description: e.target.value })
          }
        />
        {error && (
          <div className="text-red-400 text-sm bg-red-400/10 border border-red-400/20 rounded-lg px-4 py-2">
            {error}
          </div>
        )}
        <FormActions submitLabel="Add Agent" onCancel={() => setShowAddModal(false)} />
      </ModalForm>

      {/* Edit Modal */}
      <ModalForm
        open={!!editingAgent}
        title="Edit Agent"
        onClose={() => setEditingAgent(null)}
        onSubmit={handleEdit}
      >
        <FormInput
          label="Agent Name"
          value={formData.name}
          onChange={(e) => setFormData({ ...formData, name: e.target.value })}
          required
        />
        <FormSelect
          label="Model"
          options={MODEL_OPTIONS}
          value={formData.model}
          onChange={(e) => setFormData({ ...formData, model: e.target.value })}
        />
        <FormInput
          label="Priority"
          type="number"
          min={1}
          max={10}
          value={formData.priority}
          onChange={(e) =>
            setFormData({ ...formData, priority: parseInt(e.target.value) || 1 })
          }
        />
        <FormTextarea
          label="Description"
          value={formData.description}
          onChange={(e) =>
            setFormData({ ...formData, description: e.target.value })
          }
        />
        {error && (
          <div className="text-red-400 text-sm bg-red-400/10 border border-red-400/20 rounded-lg px-4 py-2">
            {error}
          </div>
        )}
        <FormActions submitLabel="Save Changes" onCancel={() => setEditingAgent(null)} />
      </ModalForm>

      {/* Delete Confirmation */}
      <ConfirmDialog
        open={!!deleteTarget}
        title="Delete Agent"
        message={`Are you sure you want to delete "${deleteTarget?.name}"? This cannot be undone.`}
        onConfirm={handleDelete}
        onCancel={() => setDeleteTarget(null)}
      />
    </div>
  );
}
