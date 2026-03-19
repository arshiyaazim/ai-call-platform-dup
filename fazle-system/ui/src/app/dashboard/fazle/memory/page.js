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

const MEMORY_TYPES = [
  { value: "preference", label: "Preference" },
  { value: "contact", label: "Contact" },
  { value: "knowledge", label: "Knowledge" },
  { value: "personal", label: "Personal" },
  { value: "conversation", label: "Conversation" },
];

export default function MemoryManagerPage() {
  const api = useApi();
  const [memories, setMemories] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showAddModal, setShowAddModal] = useState(false);
  const [editingMemory, setEditingMemory] = useState(null);
  const [deleteTarget, setDeleteTarget] = useState(null);
  const [error, setError] = useState("");

  // Form state
  const [formData, setFormData] = useState({
    type: "knowledge",
    content: "",
    metadata: "",
  });

  const fetchMemories = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.post("/memory/search", {
        query: "all memories",
        limit: 100,
      });
      setMemories(data.results || []);
    } catch {
      // Fallback: try GET
      try {
        const data = await api.get("/admin/memories");
        setMemories(data.memories || data || []);
      } catch {
        setMemories([]);
      }
    } finally {
      setLoading(false);
    }
  }, [api]);

  useEffect(() => {
    fetchMemories();
  }, []);

  const handleAdd = async () => {
    setError("");
    try {
      await api.post("/memory", {
        text: formData.content,
        memory_type: formData.type,
        metadata: formData.metadata ? JSON.parse(formData.metadata) : undefined,
      });
      setShowAddModal(false);
      setFormData({ type: "knowledge", content: "", metadata: "" });
      fetchMemories();
    } catch (err) {
      setError(err.message);
    }
  };

  const handleEdit = async () => {
    setError("");
    try {
      await api.put(`/memory/${editingMemory.id}`, {
        text: formData.content,
        memory_type: formData.type,
        metadata: formData.metadata ? JSON.parse(formData.metadata) : undefined,
      });
      setEditingMemory(null);
      setFormData({ type: "knowledge", content: "", metadata: "" });
      fetchMemories();
    } catch (err) {
      setError(err.message);
    }
  };

  const handleDelete = async () => {
    try {
      await api.del(`/memory/${deleteTarget.id}`);
      setDeleteTarget(null);
      fetchMemories();
    } catch {
      // silent fail
    }
  };

  const handleLock = async (memory) => {
    try {
      await api.patch(`/memory/${memory.id}/lock`);
      fetchMemories();
    } catch {
      // Fallback: try PUT
      try {
        await api.put(`/memory/${memory.id}`, {
          ...memory,
          locked: !memory.locked,
        });
        fetchMemories();
      } catch {
        // silent
      }
    }
  };

  const openEdit = (memory) => {
    setFormData({
      type: memory.type || memory.memory_type || "knowledge",
      content: memory.text || memory.content || "",
      metadata: memory.metadata ? JSON.stringify(memory.metadata, null, 2) : "",
    });
    setEditingMemory(memory);
    setError("");
  };

  const openAdd = () => {
    setFormData({ type: "knowledge", content: "", metadata: "" });
    setShowAddModal(true);
    setError("");
  };

  const columns = [
    {
      key: "id",
      label: "ID",
      width: "80px",
      render: (val) => (
        <span className="text-xs text-gray-500 font-mono">
          {String(val).slice(0, 8)}...
        </span>
      ),
    },
    {
      key: "type",
      label: "Type",
      width: "120px",
      render: (val, row) => (
        <StatusBadge status={val || row.memory_type || "—"} />
      ),
    },
    {
      key: "text",
      label: "Content",
      render: (val, row) => (
        <span className="line-clamp-2 text-gray-300">
          {val || row.content || "—"}
        </span>
      ),
    },
    {
      key: "created_at",
      label: "Created",
      width: "130px",
      render: (val) =>
        val ? (
          <span className="text-xs text-gray-500">
            {new Date(val).toLocaleDateString()}
          </span>
        ) : (
          "—"
        ),
    },
    {
      key: "locked",
      label: "Status",
      width: "100px",
      render: (val) => (
        <StatusBadge status={val ? "Locked" : "Unlocked"} />
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
              label: row.locked ? "Unlock" : "Lock",
              icon: row.locked ? "🔓" : "🔒",
              onClick: () => handleLock(row),
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
        title="Memory Manager"
        description="View, add, edit, and lock AI memories"
        actions={
          <button
            onClick={openAdd}
            className="bg-fazle-600 hover:bg-fazle-700 text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors"
          >
            + Add New
          </button>
        }
      />

      <div className="flex-1 overflow-y-auto pb-20 md:pb-0">
        <DataTable
          columns={columns}
          data={memories}
          loading={loading}
          emptyMessage="No memories found. Add your first memory."
        />
      </div>

      {/* Add Modal */}
      <ModalForm
        open={showAddModal}
        title="Add New Memory"
        onClose={() => setShowAddModal(false)}
        onSubmit={handleAdd}
      >
        <FormSelect
          label="Memory Type"
          options={MEMORY_TYPES}
          value={formData.type}
          onChange={(e) => setFormData({ ...formData, type: e.target.value })}
        />
        <FormTextarea
          label="Content"
          placeholder="Enter memory content..."
          value={formData.content}
          onChange={(e) => setFormData({ ...formData, content: e.target.value })}
          required
        />
        <FormTextarea
          label="Metadata (JSON, optional)"
          placeholder='{"source": "manual", "tags": ["important"]}'
          value={formData.metadata}
          onChange={(e) =>
            setFormData({ ...formData, metadata: e.target.value })
          }
        />
        {error && (
          <div className="text-red-400 text-sm bg-red-400/10 border border-red-400/20 rounded-lg px-4 py-2">
            {error}
          </div>
        )}
        <FormActions
          submitLabel="Add Memory"
          onCancel={() => setShowAddModal(false)}
        />
      </ModalForm>

      {/* Edit Modal */}
      <ModalForm
        open={!!editingMemory}
        title="Edit Memory"
        onClose={() => setEditingMemory(null)}
        onSubmit={handleEdit}
      >
        <FormSelect
          label="Memory Type"
          options={MEMORY_TYPES}
          value={formData.type}
          onChange={(e) => setFormData({ ...formData, type: e.target.value })}
        />
        <FormTextarea
          label="Content"
          placeholder="Enter memory content..."
          value={formData.content}
          onChange={(e) => setFormData({ ...formData, content: e.target.value })}
          required
        />
        <FormTextarea
          label="Metadata (JSON, optional)"
          placeholder='{"source": "manual"}'
          value={formData.metadata}
          onChange={(e) =>
            setFormData({ ...formData, metadata: e.target.value })
          }
        />
        {error && (
          <div className="text-red-400 text-sm bg-red-400/10 border border-red-400/20 rounded-lg px-4 py-2">
            {error}
          </div>
        )}
        <FormActions
          submitLabel="Save Changes"
          onCancel={() => setEditingMemory(null)}
        />
      </ModalForm>

      {/* Delete Confirmation */}
      <ConfirmDialog
        open={!!deleteTarget}
        title="Delete Memory"
        message="Are you sure you want to delete this memory? This action cannot be undone."
        onConfirm={handleDelete}
        onCancel={() => setDeleteTarget(null)}
      />
    </div>
  );
}
