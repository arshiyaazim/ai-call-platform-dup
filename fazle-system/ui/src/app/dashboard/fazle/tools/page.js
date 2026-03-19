"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { useApi } from "../../../../lib/api";
import PageHeader from "../../../../components/fazle/PageHeader";
import DataTable from "../../../../components/fazle/DataTable";
import StatusBadge from "../../../../components/fazle/StatusBadge";
import ActionDropdown from "../../../../components/fazle/ActionDropdown";
import ConfirmDialog from "../../../../components/fazle/ConfirmDialog";
import ModalForm, {
  FormInput,
  FormTextarea,
  FormActions,
} from "../../../../components/fazle/ModalForm";

export default function ToolManagerPage() {
  const api = useApi();
  const [tools, setTools] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showAddModal, setShowAddModal] = useState(false);
  const [showUploadModal, setShowUploadModal] = useState(false);
  const [editingTool, setEditingTool] = useState(null);
  const [deleteTarget, setDeleteTarget] = useState(null);
  const [error, setError] = useState("");
  const fileInputRef = useRef(null);
  const [manifestJson, setManifestJson] = useState("");

  const [formData, setFormData] = useState({
    name: "",
    description: "",
    version: "1.0.0",
  });

  const fetchTools = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.get("/admin/plugins");
      setTools(data.plugins || data.tools || data || []);
    } catch {
      // Fallback with example tools
      try {
        const data = await api.get("/admin/tools");
        setTools(data.tools || data || []);
      } catch {
        setTools([]);
      }
    } finally {
      setLoading(false);
    }
  }, [api]);

  useEffect(() => {
    fetchTools();
  }, []);

  const handleAdd = async () => {
    setError("");
    try {
      await api.post("/admin/plugins/install", {
        name: formData.name,
        description: formData.description,
        version: formData.version,
        status: "enabled",
      });
      setShowAddModal(false);
      setFormData({ name: "", description: "", version: "1.0.0" });
      fetchTools();
    } catch (err) {
      setError(err.message);
    }
  };

  const handleUploadManifest = async () => {
    setError("");
    try {
      const manifest = JSON.parse(manifestJson);
      await api.post("/admin/plugins/install", manifest);
      setShowUploadModal(false);
      setManifestJson("");
      fetchTools();
    } catch (err) {
      if (err instanceof SyntaxError) {
        setError("Invalid JSON format");
      } else {
        setError(err.message);
      }
    }
  };

  const handleEdit = async () => {
    setError("");
    try {
      await api.put(`/admin/plugins/${editingTool.id}`, {
        name: formData.name,
        description: formData.description,
        version: formData.version,
      });
      setEditingTool(null);
      fetchTools();
    } catch (err) {
      setError(err.message);
    }
  };

  const handleDelete = async () => {
    try {
      await api.del(`/admin/plugins/${deleteTarget.id}`);
      setDeleteTarget(null);
      fetchTools();
    } catch {
      setTools((prev) => prev.filter((t) => t.id !== deleteTarget.id));
      setDeleteTarget(null);
    }
  };

  const toggleTool = async (tool) => {
    const newStatus = tool.status === "enabled" ? "disabled" : "enabled";
    try {
      await api.put(`/admin/plugins/${tool.id}`, {
        ...tool,
        status: newStatus,
      });
      fetchTools();
    } catch {
      setTools((prev) =>
        prev.map((t) => (t.id === tool.id ? { ...t, status: newStatus } : t))
      );
    }
  };

  const openEdit = (tool) => {
    setFormData({
      name: tool.name,
      description: tool.description || "",
      version: tool.version || "1.0.0",
    });
    setEditingTool(tool);
    setError("");
  };

  const handleFileUpload = (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (ev) => {
      setManifestJson(ev.target.result);
      setShowUploadModal(true);
    };
    reader.readAsText(file);
  };

  const columns = [
    {
      key: "name",
      label: "Tool Name",
      render: (val) => <span className="font-medium text-gray-200">{val}</span>,
    },
    {
      key: "description",
      label: "Description",
      render: (val) => (
        <span className="text-gray-400 text-sm line-clamp-2">{val || "—"}</span>
      ),
    },
    {
      key: "version",
      label: "Version",
      width: "100px",
      render: (val) => (
        <span className="text-xs font-mono text-gray-400">
          {val || "—"}
        </span>
      ),
    },
    {
      key: "status",
      label: "Status",
      width: "120px",
      render: (val) => <StatusBadge status={val || "installed"} />,
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
              label: row.status === "enabled" ? "Disable" : "Enable",
              icon: row.status === "enabled" ? "⏸️" : "▶️",
              onClick: () => toggleTool(row),
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
        title="Tool Plugin Manager"
        description="Install, configure, and manage tool plugins"
        actions={
          <div className="flex gap-2">
            <input
              ref={fileInputRef}
              type="file"
              accept=".json"
              className="hidden"
              onChange={handleFileUpload}
            />
            <button
              onClick={() => fileInputRef.current?.click()}
              className="border border-gray-700 hover:border-gray-600 text-gray-300 px-4 py-2 rounded-lg text-sm font-medium transition-colors"
            >
              Upload Manifest
            </button>
            <button
              onClick={() => {
                setFormData({ name: "", description: "", version: "1.0.0" });
                setShowAddModal(true);
                setError("");
              }}
              className="bg-fazle-600 hover:bg-fazle-700 text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors"
            >
              + Add New
            </button>
          </div>
        }
      />

      <div className="flex-1 overflow-y-auto pb-20 md:pb-0">
        <DataTable
          columns={columns}
          data={tools}
          loading={loading}
          emptyMessage="No tool plugins installed."
        />
      </div>

      {/* Add Modal */}
      <ModalForm
        open={showAddModal}
        title="Add New Tool"
        onClose={() => setShowAddModal(false)}
        onSubmit={handleAdd}
      >
        <FormInput
          label="Tool Name"
          placeholder="e.g. WebSearchPlugin"
          value={formData.name}
          onChange={(e) => setFormData({ ...formData, name: e.target.value })}
          required
        />
        <FormTextarea
          label="Description"
          placeholder="What does this tool do?"
          value={formData.description}
          onChange={(e) => setFormData({ ...formData, description: e.target.value })}
        />
        <FormInput
          label="Version"
          placeholder="1.0.0"
          value={formData.version}
          onChange={(e) => setFormData({ ...formData, version: e.target.value })}
        />
        {error && (
          <div className="text-red-400 text-sm bg-red-400/10 border border-red-400/20 rounded-lg px-4 py-2">
            {error}
          </div>
        )}
        <FormActions submitLabel="Install Tool" onCancel={() => setShowAddModal(false)} />
      </ModalForm>

      {/* Upload Manifest Modal */}
      <ModalForm
        open={showUploadModal}
        title="Install from Manifest"
        onClose={() => setShowUploadModal(false)}
        onSubmit={handleUploadManifest}
      >
        <FormTextarea
          label="Manifest JSON"
          value={manifestJson}
          onChange={(e) => setManifestJson(e.target.value)}
          rows={12}
        />
        {error && (
          <div className="text-red-400 text-sm bg-red-400/10 border border-red-400/20 rounded-lg px-4 py-2">
            {error}
          </div>
        )}
        <FormActions submitLabel="Install Plugin" onCancel={() => setShowUploadModal(false)} />
      </ModalForm>

      {/* Edit Modal */}
      <ModalForm
        open={!!editingTool}
        title="Edit Tool"
        onClose={() => setEditingTool(null)}
        onSubmit={handleEdit}
      >
        <FormInput
          label="Tool Name"
          value={formData.name}
          onChange={(e) => setFormData({ ...formData, name: e.target.value })}
          required
        />
        <FormTextarea
          label="Description"
          value={formData.description}
          onChange={(e) => setFormData({ ...formData, description: e.target.value })}
        />
        <FormInput
          label="Version"
          value={formData.version}
          onChange={(e) => setFormData({ ...formData, version: e.target.value })}
        />
        {error && (
          <div className="text-red-400 text-sm bg-red-400/10 border border-red-400/20 rounded-lg px-4 py-2">
            {error}
          </div>
        )}
        <FormActions submitLabel="Save Changes" onCancel={() => setEditingTool(null)} />
      </ModalForm>

      {/* Delete Confirmation */}
      <ConfirmDialog
        open={!!deleteTarget}
        title="Delete Tool"
        message={`Are you sure you want to delete "${deleteTarget?.name}"? This cannot be undone.`}
        onConfirm={handleDelete}
        onCancel={() => setDeleteTarget(null)}
      />
    </div>
  );
}
