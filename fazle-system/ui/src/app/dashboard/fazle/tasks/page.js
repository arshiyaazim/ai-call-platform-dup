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
  FormField,
} from "../../../../components/fazle/ModalForm";

const CRON_PRESETS = [
  { value: "", label: "Custom" },
  { value: "* * * * *", label: "Every minute" },
  { value: "*/5 * * * *", label: "Every 5 minutes" },
  { value: "*/15 * * * *", label: "Every 15 minutes" },
  { value: "0 * * * *", label: "Every hour" },
  { value: "0 0 * * *", label: "Daily at midnight" },
  { value: "0 9 * * *", label: "Daily at 9 AM" },
  { value: "0 0 * * 1", label: "Weekly (Monday)" },
  { value: "0 0 1 * *", label: "Monthly" },
];

function CronEditor({ value, onChange }) {
  const [preset, setPreset] = useState("");

  const handlePreset = (e) => {
    const val = e.target.value;
    setPreset(val);
    if (val) onChange(val);
  };

  return (
    <div className="space-y-2">
      <div className="flex gap-2">
        <select
          value={preset}
          onChange={handlePreset}
          className="flex-1 bg-[#0a0a0f] border border-gray-700 rounded-lg px-3 py-2.5 text-sm text-gray-200 focus:outline-none focus:border-fazle-500"
        >
          {CRON_PRESETS.map((p) => (
            <option key={p.label} value={p.value}>{p.label}</option>
          ))}
        </select>
      </div>
      <input
        type="text"
        value={value}
        onChange={(e) => {
          setPreset("");
          onChange(e.target.value);
        }}
        placeholder="* * * * * (min hour dom mon dow)"
        className="w-full bg-[#0a0a0f] border border-gray-700 rounded-lg px-3 py-2.5 text-sm text-gray-200 placeholder-gray-500 focus:outline-none focus:border-fazle-500 font-mono"
      />
      <p className="text-xs text-gray-500">
        Format: minute hour day-of-month month day-of-week
      </p>
    </div>
  );
}

const TASK_TYPES = [
  { value: "reminder", label: "Reminder" },
  { value: "call", label: "Call" },
  { value: "summary", label: "Summary" },
  { value: "report", label: "Report" },
  { value: "backup", label: "Backup" },
  { value: "custom", label: "Custom" },
];

export default function TaskSchedulerPage() {
  const api = useApi();
  const [tasks, setTasks] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showAddModal, setShowAddModal] = useState(false);
  const [editingTask, setEditingTask] = useState(null);
  const [deleteTarget, setDeleteTarget] = useState(null);
  const [error, setError] = useState("");

  const [formData, setFormData] = useState({
    name: "",
    task_type: "reminder",
    schedule: "",
    description: "",
    scheduled_at: "",
  });

  const fetchTasks = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.get("/admin/tasks");
      setTasks(data.tasks || data || []);
    } catch {
      try {
        const data = await api.get("/tasks");
        setTasks(data.tasks || data || []);
      } catch {
        setTasks([]);
      }
    } finally {
      setLoading(false);
    }
  }, [api]);

  useEffect(() => {
    fetchTasks();
  }, []);

  const handleAdd = async () => {
    setError("");
    try {
      await api.post("/admin/tasks", {
        title: formData.name,
        task_type: formData.task_type,
        schedule: formData.schedule || undefined,
        description: formData.description,
        scheduled_at: formData.scheduled_at || undefined,
        status: "pending",
      });
      setShowAddModal(false);
      resetForm();
      fetchTasks();
    } catch (err) {
      setError(err.message);
    }
  };

  const handleEdit = async () => {
    setError("");
    try {
      await api.put(`/admin/tasks/${editingTask.id}`, {
        title: formData.name,
        task_type: formData.task_type,
        schedule: formData.schedule || undefined,
        description: formData.description,
        scheduled_at: formData.scheduled_at || undefined,
      });
      setEditingTask(null);
      fetchTasks();
    } catch (err) {
      setError(err.message);
    }
  };

  const handleDelete = async () => {
    try {
      await api.del(`/admin/tasks/${deleteTarget.id}`);
      setDeleteTarget(null);
      fetchTasks();
    } catch {
      setTasks((prev) => prev.filter((t) => t.id !== deleteTarget.id));
      setDeleteTarget(null);
    }
  };

  const togglePause = async (task) => {
    const newStatus = task.status === "paused" ? "pending" : "paused";
    try {
      await api.put(`/admin/tasks/${task.id}`, { ...task, status: newStatus });
      fetchTasks();
    } catch {
      setTasks((prev) =>
        prev.map((t) => (t.id === task.id ? { ...t, status: newStatus } : t))
      );
    }
  };

  const resetForm = () => {
    setFormData({ name: "", task_type: "reminder", schedule: "", description: "", scheduled_at: "" });
  };

  const openEdit = (task) => {
    setFormData({
      name: task.title || task.name || "",
      task_type: task.task_type || "reminder",
      schedule: task.schedule || "",
      description: task.description || "",
      scheduled_at: task.scheduled_at ? task.scheduled_at.slice(0, 16) : "",
    });
    setEditingTask(task);
    setError("");
  };

  const columns = [
    {
      key: "title",
      label: "Task Name",
      render: (val, row) => (
        <span className="font-medium text-gray-200">{val || row.name || "—"}</span>
      ),
    },
    {
      key: "schedule",
      label: "Schedule",
      width: "160px",
      render: (val, row) => (
        <span className="text-xs text-gray-400 font-mono">
          {val || (row.scheduled_at ? new Date(row.scheduled_at).toLocaleString() : "—")}
        </span>
      ),
    },
    {
      key: "status",
      label: "Status",
      width: "110px",
      render: (val) => <StatusBadge status={val || "pending"} />,
    },
    {
      key: "last_run",
      label: "Last Run",
      width: "130px",
      render: (val) =>
        val ? (
          <span className="text-xs text-gray-500">
            {new Date(val).toLocaleDateString()}
          </span>
        ) : (
          <span className="text-xs text-gray-600">Never</span>
        ),
    },
    {
      key: "next_run",
      label: "Next Run",
      width: "130px",
      render: (val, row) => {
        const next = val || row.scheduled_at;
        return next ? (
          <span className="text-xs text-gray-500">
            {new Date(next).toLocaleDateString()}
          </span>
        ) : (
          <span className="text-xs text-gray-600">—</span>
        );
      },
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
              label: row.status === "paused" ? "Resume" : "Pause",
              icon: row.status === "paused" ? "▶️" : "⏸️",
              onClick: () => togglePause(row),
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
        title="Task Scheduler"
        description="Schedule and manage automated tasks"
        actions={
          <button
            onClick={() => {
              resetForm();
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
          data={tasks}
          loading={loading}
          emptyMessage="No scheduled tasks. Create one to get started."
        />
      </div>

      {/* Add Modal */}
      <ModalForm
        open={showAddModal}
        title="Add New Task"
        onClose={() => setShowAddModal(false)}
        onSubmit={handleAdd}
      >
        <FormInput
          label="Task Name"
          placeholder="e.g. Daily Summary Report"
          value={formData.name}
          onChange={(e) => setFormData({ ...formData, name: e.target.value })}
          required
        />
        <FormSelect
          label="Task Type"
          options={TASK_TYPES}
          value={formData.task_type}
          onChange={(e) => setFormData({ ...formData, task_type: e.target.value })}
        />
        <FormField label="Cron Schedule">
          <CronEditor
            value={formData.schedule}
            onChange={(val) => setFormData({ ...formData, schedule: val })}
          />
        </FormField>
        <FormInput
          label="Or One-Time Schedule"
          type="datetime-local"
          value={formData.scheduled_at}
          onChange={(e) => setFormData({ ...formData, scheduled_at: e.target.value })}
        />
        <FormTextarea
          label="Description"
          placeholder="Task description..."
          value={formData.description}
          onChange={(e) => setFormData({ ...formData, description: e.target.value })}
        />
        {error && (
          <div className="text-red-400 text-sm bg-red-400/10 border border-red-400/20 rounded-lg px-4 py-2">
            {error}
          </div>
        )}
        <FormActions submitLabel="Create Task" onCancel={() => setShowAddModal(false)} />
      </ModalForm>

      {/* Edit Modal */}
      <ModalForm
        open={!!editingTask}
        title="Edit Task"
        onClose={() => setEditingTask(null)}
        onSubmit={handleEdit}
      >
        <FormInput
          label="Task Name"
          value={formData.name}
          onChange={(e) => setFormData({ ...formData, name: e.target.value })}
          required
        />
        <FormSelect
          label="Task Type"
          options={TASK_TYPES}
          value={formData.task_type}
          onChange={(e) => setFormData({ ...formData, task_type: e.target.value })}
        />
        <FormField label="Cron Schedule">
          <CronEditor
            value={formData.schedule}
            onChange={(val) => setFormData({ ...formData, schedule: val })}
          />
        </FormField>
        <FormInput
          label="Or One-Time Schedule"
          type="datetime-local"
          value={formData.scheduled_at}
          onChange={(e) => setFormData({ ...formData, scheduled_at: e.target.value })}
        />
        <FormTextarea
          label="Description"
          value={formData.description}
          onChange={(e) => setFormData({ ...formData, description: e.target.value })}
        />
        {error && (
          <div className="text-red-400 text-sm bg-red-400/10 border border-red-400/20 rounded-lg px-4 py-2">
            {error}
          </div>
        )}
        <FormActions submitLabel="Save Changes" onCancel={() => setEditingTask(null)} />
      </ModalForm>

      {/* Delete Confirmation */}
      <ConfirmDialog
        open={!!deleteTarget}
        title="Delete Task"
        message={`Are you sure you want to delete "${deleteTarget?.title || deleteTarget?.name}"? This cannot be undone.`}
        onConfirm={handleDelete}
        onCancel={() => setDeleteTarget(null)}
      />
    </div>
  );
}
