export interface DashboardStats {
  active_agents: number;
  total_memories: number;
  scheduled_tasks: number;
  average_latency: number;
  active_conversations: number;
}

export interface Memory {
  id: string;
  content: string;
  type: string;
  created: string;
  status: string;
  locked: boolean;
}

export interface Agent {
  id: string;
  name: string;
  model: string;
  priority: number;
  status: 'active' | 'inactive' | 'error';
  enabled: boolean;
}

export interface Plugin {
  id: string;
  name: string;
  description: string;
  version: string;
  status: 'active' | 'inactive' | 'error';
  enabled: boolean;
}

export interface Task {
  id: string;
  name: string;
  schedule: string;
  status: 'running' | 'paused' | 'completed' | 'failed';
  last_run: string | null;
  next_run: string | null;
}

export interface Persona {
  name: string;
  tone: string;
  language: string;
  speaking_style: string;
  knowledge_notes: string;
}

export interface LogEntry {
  id: string;
  timestamp: string;
  user_query: string;
  agent_route: string;
  tools_used: string[];
  latency: number;
}

export interface ApiError {
  detail: string;
  status: number;
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  per_page: number;
}
