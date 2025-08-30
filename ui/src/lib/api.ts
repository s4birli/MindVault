import axios from 'axios';
import { AskRequest, AskResponse, AgentRequest, AgentResponse } from '@/types';

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

const api = axios.create({
    baseURL: API_BASE_URL,
    headers: {
        'Content-Type': 'application/json',
    },
});

export const askAPI = {
    ask: async (request: AskRequest): Promise<AskResponse> => {
        const response = await api.post('/ask', request);
        return response.data;
    },
};

export const agentAPI = {
    act: async (request: AgentRequest): Promise<AgentResponse> => {
        const response = await api.post('/agent/act', request);
        return response.data;
    },
};

export const healthAPI = {
    check: async () => {
        const response = await api.get('/health');
        return response.data;
    },
};

export const threadsAPI = {
    getAll: async () => {
        const response = await api.get('/threads');
        return response.data;
    },

    create: async (title?: string) => {
        const response = await api.post('/threads', { title });
        return response.data;
    },

    get: async (threadId: string) => {
        const response = await api.get(`/threads/${threadId}`);
        return response.data;
    },

    update: async (threadId: string, updates: { title?: string }) => {
        const response = await api.put(`/threads/${threadId}`, updates);
        return response.data;
    },

    delete: async (threadId: string) => {
        const response = await api.delete(`/threads/${threadId}`);
        return response.data;
    },

    addMessage: async (threadId: string, message: {
        content: string;
        type: string;
        attachments?: Array<Record<string, unknown>>;
        sources?: Array<Record<string, unknown>>;
    }) => {
        const response = await api.post(`/threads/${threadId}/messages`, message);
        return response.data;
    },
};

export default api;
