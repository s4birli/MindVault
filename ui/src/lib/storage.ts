import { Thread, Message } from '@/types';
import { v4 as uuidv4 } from 'uuid';
import { threadsAPI } from './api';

const THREADS_KEY = 'mindvault_threads';
const USE_DATABASE = true; // Set to false to use localStorage

export const storage = {
    getThreads: async (): Promise<Thread[]> => {
        if (typeof window === 'undefined') return [];

        if (USE_DATABASE) {
            try {
                const threads = await threadsAPI.getAll();
                return threads.map((thread: Record<string, unknown>) => ({
                    ...thread,
                    createdAt: new Date((thread.createdAt || thread.created_at) as string),
                    updatedAt: new Date((thread.updatedAt || thread.updated_at) as string),
                    messages: (thread.messages as Record<string, unknown>[] || []).map((msg: Record<string, unknown>) => ({
                        ...msg,
                        threadId: msg.threadId || msg.thread_id,
                        timestamp: new Date(msg.timestamp as string),
                    })),
                }));
            } catch (error) {
                console.error('Error loading threads from database:', error);
                // Fallback to localStorage
                return storage.getThreadsFromLocalStorage();
            }
        }

        return storage.getThreadsFromLocalStorage();
    },

    getThreadsFromLocalStorage: (): Thread[] => {
        try {
            const stored = localStorage.getItem(THREADS_KEY);
            if (!stored) return [];
            const threads = JSON.parse(stored);
            // Convert date strings back to Date objects
            return threads.map((thread: Thread & { createdAt: string; updatedAt: string; messages: Array<Message & { timestamp: string }> }) => ({
                ...thread,
                createdAt: new Date(thread.createdAt),
                updatedAt: new Date(thread.updatedAt),
                messages: thread.messages.map((msg) => ({
                    ...msg,
                    timestamp: new Date(msg.timestamp),
                })),
            }));
        } catch (error) {
            console.error('Error loading threads from localStorage:', error);
            return [];
        }
    },

    saveThreads: (threads: Thread[]): void => {
        if (typeof window === 'undefined') return;
        try {
            localStorage.setItem(THREADS_KEY, JSON.stringify(threads));
        } catch (error) {
            console.error('Error saving threads:', error);
        }
    },

    createThread: async (title?: string): Promise<Thread> => {
        if (USE_DATABASE) {
            try {
                const thread = await threadsAPI.create(title);
                return {
                    ...thread,
                    createdAt: new Date((thread.createdAt || thread.created_at) as string),
                    updatedAt: new Date((thread.updatedAt || thread.updated_at) as string),
                    messages: [],
                };
            } catch (error) {
                console.error('Error creating thread in database:', error);
                // Fallback to localStorage
            }
        }

        // localStorage fallback
        const thread: Thread = {
            id: uuidv4(),
            title: title || 'New Chat',
            createdAt: new Date(),
            updatedAt: new Date(),
            messages: [],
        };

        const threads = await storage.getThreads();
        threads.unshift(thread);
        storage.saveThreads(threads);

        return thread;
    },

    updateThread: async (threadId: string, updates: Partial<Thread>): Promise<Thread | null> => {
        if (USE_DATABASE) {
            try {
                const thread = await threadsAPI.update(threadId, { title: updates.title });
                return {
                    ...thread,
                    createdAt: new Date((thread.createdAt || thread.created_at) as string),
                    updatedAt: new Date((thread.updatedAt || thread.updated_at) as string),
                    messages: (thread.messages as Record<string, unknown>[] || []).map((msg: Record<string, unknown>) => ({
                        ...msg,
                        threadId: msg.threadId || msg.thread_id,
                        timestamp: new Date(msg.timestamp as string),
                    })),
                };
            } catch (error) {
                console.error('Error updating thread in database:', error);
                // Fallback to localStorage
            }
        }

        // localStorage fallback
        const threads = await storage.getThreads();
        const threadIndex = threads.findIndex(t => t.id === threadId);

        if (threadIndex === -1) return null;

        threads[threadIndex] = {
            ...threads[threadIndex],
            ...updates,
            updatedAt: new Date(),
        };

        storage.saveThreads(threads);
        return threads[threadIndex];
    },

    addMessage: async (threadId: string, message: Omit<Message, 'id' | 'timestamp'>): Promise<Message> => {
        if (USE_DATABASE) {
            try {
                const dbMessage = await threadsAPI.addMessage(threadId, {
                    content: message.content,
                    type: message.type,
                    attachments: message.attachments as Array<Record<string, unknown>> | undefined,
                    sources: message.sources as Array<Record<string, unknown>> | undefined,
                });
                return {
                    ...dbMessage,
                    threadId: (dbMessage.threadId || dbMessage.thread_id) as string,
                    timestamp: new Date(dbMessage.timestamp as string),
                };
            } catch (error) {
                console.error('Error adding message to database:', error);
                // Fallback to localStorage
            }
        }

        // localStorage fallback
        const newMessage: Message = {
            ...message,
            id: uuidv4(),
            timestamp: new Date(),
        };

        const threads = await storage.getThreads();
        const threadIndex = threads.findIndex(t => t.id === threadId);

        if (threadIndex !== -1) {
            threads[threadIndex].messages.push(newMessage);
            threads[threadIndex].updatedAt = new Date();

            // Auto-generate title from first user message if title is still default
            if (threads[threadIndex].title === 'New Chat' && message.type === 'user') {
                const title = message.content.length > 50
                    ? message.content.substring(0, 47) + '...'
                    : message.content;
                threads[threadIndex].title = title;
            }

            storage.saveThreads(threads);
        }

        return newMessage;
    },

    deleteThread: async (threadId: string): Promise<void> => {
        if (USE_DATABASE) {
            try {
                await threadsAPI.delete(threadId);
                return;
            } catch (error) {
                console.error('Error deleting thread from database:', error);
                // Fallback to localStorage
            }
        }

        // localStorage fallback
        const threads = await storage.getThreads();
        const filteredThreads = threads.filter(t => t.id !== threadId);
        storage.saveThreads(filteredThreads);
    },

    getThread: async (threadId: string): Promise<Thread | null> => {
        if (USE_DATABASE) {
            try {
                const thread = await threadsAPI.get(threadId);
                return {
                    ...thread,
                    createdAt: new Date((thread.createdAt || thread.created_at) as string),
                    updatedAt: new Date((thread.updatedAt || thread.updated_at) as string),
                    messages: (thread.messages as Record<string, unknown>[] || []).map((msg: Record<string, unknown>) => ({
                        ...msg,
                        threadId: msg.threadId || msg.thread_id,
                        timestamp: new Date(msg.timestamp as string),
                    })),
                };
            } catch (error) {
                console.error('Error getting thread from database:', error);
                // Fallback to localStorage
            }
        }

        // localStorage fallback
        const threads = await storage.getThreads();
        return threads.find(t => t.id === threadId) || null;
    },
};
