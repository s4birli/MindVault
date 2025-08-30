'use client';

import React, { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { Thread } from '@/types';
import { storage } from '@/lib/storage';
import Sidebar from './Sidebar';
import ChatArea from './ChatArea';
import Header from './Header';

interface ChatLayoutProps {
    initialThreadId?: string;
}

export default function ChatLayout({ initialThreadId }: ChatLayoutProps) {
    const [threads, setThreads] = useState<Thread[]>([]);
    const [currentThread, setCurrentThread] = useState<Thread | undefined>();
    const [isLoaded, setIsLoaded] = useState(false);
    const [isSidebarOpen, setIsSidebarOpen] = useState(true);
    const [searchQuery, setSearchQuery] = useState('');
    const router = useRouter();

    useEffect(() => {
        // Load threads from storage (database or localStorage)
        const loadThreads = async () => {
            try {
                const loadedThreads = await storage.getThreads();
                setThreads(loadedThreads);
                setIsLoaded(true);

                // If initialThreadId is provided, select that thread
                if (initialThreadId) {
                    const thread = loadedThreads.find(t => t.id === initialThreadId);
                    if (thread) {
                        setCurrentThread(thread);
                    }
                } else if (loadedThreads.length > 0) {
                    // Select the most recent thread if available
                    setCurrentThread(loadedThreads[0]);
                }
            } catch (error) {
                console.error('Error loading threads:', error);
                setIsLoaded(true);
            }
        };

        loadThreads();
    }, [initialThreadId]);

    const handleNewThread = async () => {
        try {
            // Always create a new thread when "New Chat" is clicked
            const newThread = await storage.createThread();

            // Navigate to the new thread URL
            router.push(`/thread/${newThread.id}`);

            // Set as current thread
            setCurrentThread(newThread);

            // Update threads list
            const updatedThreads = await storage.getThreads();
            setThreads(updatedThreads);
        } catch (error) {
            console.error('Error creating new thread:', error);
            // Fallback: just navigate to home page
            router.push('/');
            setCurrentThread(undefined);
        }
    };

    const handleThreadSelect = async (threadId: string) => {
        try {
            // Navigate to thread URL
            router.push(`/thread/${threadId}`);

            const thread = await storage.getThread(threadId);
            if (thread) {
                setCurrentThread(thread);
            }
        } catch (error) {
            console.error('Error loading thread:', error);
        }
    };

    const handleThreadDelete = async (threadId: string) => {
        try {
            await storage.deleteThread(threadId);
            const updatedThreads = await storage.getThreads();
            setThreads(updatedThreads);

            // If the deleted thread was current, select another one or clear
            if (currentThread?.id === threadId) {
                setCurrentThread(updatedThreads.length > 0 ? updatedThreads[0] : undefined);
            }
        } catch (error) {
            console.error('Error deleting thread:', error);
        }
    };

    const handleThreadRename = async (threadId: string, newTitle: string) => {
        try {
            await storage.updateThread(threadId, { title: newTitle });
            const updatedThreads = await storage.getThreads();
            setThreads(updatedThreads);

            // Update current thread if it's the one being renamed
            if (currentThread?.id === threadId) {
                const updatedThread = await storage.getThread(threadId);
                if (updatedThread) {
                    setCurrentThread(updatedThread);
                }
            }
        } catch (error) {
            console.error('Error renaming thread:', error);
        }
    };

    const handleThreadUpdate = async (updatedThread: Thread) => {
        try {
            const updatedThreads = await storage.getThreads();
            setThreads(updatedThreads);
            setCurrentThread(updatedThread);
        } catch (error) {
            console.error('Error updating thread list:', error);
        }
    };

    const handleSearch = (query: string) => {
        setSearchQuery(query);
        // TODO: Implement search functionality within current thread
        console.log('Searching for:', query);
    };

    const toggleSidebar = () => {
        setIsSidebarOpen(!isSidebarOpen);
    };

    if (!isLoaded) {
        return (
            <div className="flex items-center justify-center h-screen">
                <div className="text-center">
                    <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600 mx-auto"></div>
                    <p className="mt-2 text-gray-600">Loading...</p>
                </div>
            </div>
        );
    }

    return (
        <div className="flex h-screen bg-gray-50">
            {/* Sidebar */}
            <div className={`${isSidebarOpen ? 'translate-x-0' : '-translate-x-full'
                } fixed lg:relative lg:translate-x-0 z-30 transition-transform duration-300 ease-in-out`}>
                <Sidebar
                    threads={threads}
                    currentThreadId={currentThread?.id}
                    onThreadSelect={handleThreadSelect}
                    onNewThread={handleNewThread}
                    onThreadDelete={handleThreadDelete}
                    onThreadRename={handleThreadRename}
                />
            </div>

            {/* Sidebar Overlay (Mobile) */}
            {isSidebarOpen && (
                <div
                    className="fixed inset-0 bg-black bg-opacity-50 z-20 lg:hidden"
                    onClick={() => setIsSidebarOpen(false)}
                />
            )}

            {/* Main Chat Area */}
            <div className="flex-1 flex flex-col">
                {/* Header */}
                <Header
                    currentThreadTitle={currentThread?.title}
                    onSearch={handleSearch}
                    onToggleSidebar={toggleSidebar}
                    isSidebarOpen={isSidebarOpen}
                />

                {/* Chat Area */}
                <ChatArea
                    thread={currentThread}
                    onThreadUpdate={handleThreadUpdate}
                    searchQuery={searchQuery}
                />
            </div>

            {/* Future Right Sidebar for Todo List */}
            <div className="w-80 bg-gray-50 border-l border-gray-200 hidden xl:block">
                <div className="p-4 h-full flex items-center justify-center text-gray-400">
                    <div className="text-center">
                        <div className="text-4xl mb-2">📋</div>
                        <p>Todo List</p>
                        <p className="text-sm">(Coming Soon)</p>
                    </div>
                </div>
            </div>
        </div>
    );
}
