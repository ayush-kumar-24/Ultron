// Domain services. Pages import these — never the api client directly.
// Each maps 1:1 to a backend resource so the mock can be replaced endpoint-by-endpoint.
import { api } from '../api/client.js';

export const userService = {
  me: () => api.get('/me'),
  update: (patch) => api.patch('/me', patch),
};

export const overviewService = {
  summary: () => api.get('/overview'),
};

export const chatService = {
  list: () => api.get('/conversations'),
  get: (id) => api.get(`/conversations/${id}`),
  create: (body) => api.post('/conversations', body),
  update: (id, patch) => api.patch(`/conversations/${id}`, patch),
  remove: (id) => api.delete(`/conversations/${id}`),
  messages: (id) => api.get(`/conversations/${id}/messages`),
  /** Streams a turn. onEvent receives {type:'user'|'state'|'tool'|'token', ...}. Resolves with {message, conversation}. */
  send: (conversationId, text, context, onEvent) => api.stream('/chat/stream', { conversationId, text, context }, onEvent),
  saveToMemory: (messageId, text) => api.post(`/messages/${messageId}/memory`, { text }),
  createTask: (messageId, title, projectId) => api.post(`/messages/${messageId}/task`, { title, projectId }),
};

export const memoryService = {
  list: (params) => api.get('/memories', params),
  stats: () => api.get('/memory/stats'),
  create: (body) => api.post('/memories', body),
  update: (id, patch) => api.patch(`/memories/${id}`, patch),
  remove: (id) => api.delete(`/memories/${id}`),
};

export const knowledgeService = {
  list: (params) => api.get('/knowledge', params),
  get: (id) => api.get(`/knowledge/${id}`),
  add: (body) => api.post('/knowledge', body),
  remove: (id) => api.delete(`/knowledge/${id}`),
  summarize: (id) => api.post(`/knowledge/${id}/summarize`),
  saveToMemory: (id) => api.post(`/knowledge/${id}/memory`),
};

export const taskService = {
  list: (params) => api.get('/tasks', params),
  parse: (text) => api.post('/tasks/parse', { text }),
  create: (body) => api.post('/tasks', body),
  update: (id, patch) => api.patch(`/tasks/${id}`, patch),
  remove: (id) => api.delete(`/tasks/${id}`),
  planDay: () => api.get('/plan/day'),
};

export const calendarService = {
  events: (params) => api.get('/events', params),
  add: (body) => api.post('/events', body),
  remove: (id) => api.delete(`/events/${id}`),
  context: () => api.get('/calendar/context'),
};

export const automationService = {
  list: () => api.get('/automations'),
  runs: (id) => api.get(`/automations/${id}/runs`),
  create: (body) => api.post('/automations', body),
  update: (id, patch) => api.patch(`/automations/${id}`, patch),
  remove: (id) => api.delete(`/automations/${id}`),
  run: (id) => api.post(`/automations/${id}/run`),
};

export const agentService = {
  list: () => api.get('/agents'),
  get: (id) => api.get(`/agents/${id}`),
  executions: (id) => api.get(id ? `/agents/${id}/executions` : '/executions'),
  /** Streams an orchestration. onEvent receives {type:'step', index, agent, label, status}. */
  orchestrate: (request, onEvent) => api.stream('/agents/orchestrate', { request }, onEvent),
};

export const researchService = {
  list: () => api.get('/research'),
  get: (id) => api.get(`/research/${id}`),
  remove: (id) => api.delete(`/research/${id}`),
  /** Streams a session. onEvent receives {type:'session'|'step'|'report', ...}. */
  start: (query, projectId, onEvent) => api.stream('/research/stream', { query, projectId }, onEvent),
  createTasks: (id) => api.post(`/research/${id}/tasks`),
  saveToKnowledge: (id) => api.post(`/research/${id}/knowledge`),
};

export const projectService = {
  list: () => api.get('/projects'),
  get: (id) => api.get(`/projects/${id}`),
  create: (body) => api.post('/projects', body),
};

export const goalService = {
  list: () => api.get('/goals'),
  update: (id, patch) => api.patch(`/goals/${id}`, patch),
  create: (body) => api.post('/goals', body),
};

export const insightService = { get: () => api.get('/insights') };
export const activityService = { list: (params) => api.get('/activity', params) };
export const sessionService = { list: () => api.get('/sessions') };

export const notificationService = {
  list: () => api.get('/notifications'),
  markRead: (id) => api.patch(`/notifications/${id}`, { read: true }),
  readAll: () => api.post('/notifications/read-all'),
};

export const integrationService = {
  list: () => api.get('/integrations'),
  connect: (id) => api.post(`/integrations/${id}/connect`),
  disconnect: (id) => api.post(`/integrations/${id}/disconnect`),
};

export const settingsService = {
  get: () => api.get('/settings'),
  update: (section, patch) => api.patch(`/settings/${section}`, patch),
};

export const searchService = { query: (q) => api.get('/search', { q }) };

export const voiceService = {
  /** Streams a transcript. onEvent receives {type:'state'|'partial', ...}. Resolves with {transcript}. */
  transcribe: (prompt, onEvent) => api.stream('/voice/transcribe', { prompt }, onEvent),
};

export const systemService = {
  health: () => api.get('/system/health'),
  resetDemo: () => api.post('/system/reset'),
  wipe: () => api.post('/system/wipe'),
};

/** Real-time events from the backend (agent, automation, notification, knowledge, research, heartbeat). */
export const events = api.events;
export { api };
