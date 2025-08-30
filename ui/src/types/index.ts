export interface Thread {
    id: string;
    title: string;
    createdAt: Date;
    updatedAt: Date;
    messages: Message[];
}

export interface Message {
    id: string;
    threadId: string;
    content: string;
    type: 'user' | 'assistant';
    timestamp: Date;
    attachments?: Attachment[];
    sources?: SourceRef[];
}

export interface Attachment {
    id: string;
    name: string;
    type: 'text' | 'image' | 'audio';
    url?: string;
    data?: string; // base64 for small files
    size: number;
}

export interface SourceRef {
    id: string;
    title?: string;
    url?: string;
}

export interface AskRequest {
    query: string;
    final_n?: number;
    language?: string;
    mode?: string;
    max_sentences?: number;
}

export interface AskResponse {
    answer: string;
    used_ids: string[];
    sources?: SourceRef[];
    subject?: string;
    body?: string;
    format?: string;
}

export interface AgentRequest {
    text: string;
    thread_id?: string;
    confirm?: boolean;
    params?: Record<string, unknown>;
}

export interface AgentResponse {
    intent?: string;
    params_used?: Record<string, unknown>;
    result?: Record<string, unknown>;
}
