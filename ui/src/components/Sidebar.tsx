'use client';

import React, { useState } from 'react';
import { Thread } from '@/types';
import { PlusIcon, MessageSquareIcon, EditIcon, CheckIcon, XIcon, TrashIcon, CalendarIcon, ListTodoIcon } from 'lucide-react';
import { formatDistanceToNow } from 'date-fns';

interface SidebarProps {
    threads: Thread[];
    currentThreadId?: string;
    onThreadSelect: (threadId: string) => void;
    onNewThread: () => void;
    onThreadDelete: (threadId: string) => void;
    onThreadRename: (threadId: string, newTitle: string) => void;
}

export default function Sidebar({
    threads,
    currentThreadId,
    onThreadSelect,
    onNewThread,
    onThreadDelete,
    onThreadRename,
}: SidebarProps) {
    const [editingThreadId, setEditingThreadId] = useState<string | null>(null);
    const [editTitle, setEditTitle] = useState('');

    const startEditing = (thread: Thread) => {
        setEditingThreadId(thread.id);
        setEditTitle(thread.title);
    };

    const saveEdit = () => {
        if (editingThreadId && editTitle.trim()) {
            onThreadRename(editingThreadId, editTitle.trim());
        }
        setEditingThreadId(null);
        setEditTitle('');
    };

    const cancelEdit = () => {
        setEditingThreadId(null);
        setEditTitle('');
    };

    return (
        <div className="w-80 bg-gray-50 border-r border-gray-200 flex flex-col h-screen">
            {/* Header */}
            <div className="p-4 border-b border-gray-200">
                <button
                    onClick={onNewThread}
                    className="w-full flex items-center gap-2 px-4 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
                >
                    <PlusIcon size={20} />
                    New Chat
                </button>
            </div>

            {/* Threads List */}
            <div className="flex-1 overflow-y-auto scrollbar-thin">
                <div className="p-2">
                    {threads.map((thread) => (
                        <div
                            key={thread.id}
                            className={`group relative mb-2 p-3 rounded-lg cursor-pointer transition-colors ${currentThreadId === thread.id
                                    ? 'bg-blue-100 border border-blue-200'
                                    : 'hover:bg-gray-100'
                                }`}
                            onClick={() => onThreadSelect(thread.id)}
                        >
                            <div className="flex items-start gap-2">
                                <MessageSquareIcon size={16} className="mt-1 text-gray-500 flex-shrink-0" />
                                <div className="flex-1 min-w-0">
                                    {editingThreadId === thread.id ? (
                                        <div className="flex items-center gap-1">
                                            <input
                                                type="text"
                                                value={editTitle}
                                                onChange={(e) => setEditTitle(e.target.value)}
                                                className="flex-1 text-sm bg-white border border-gray-300 rounded px-2 py-1"
                                                autoFocus
                                                onKeyDown={(e) => {
                                                    if (e.key === 'Enter') saveEdit();
                                                    if (e.key === 'Escape') cancelEdit();
                                                }}
                                                onClick={(e) => e.stopPropagation()}
                                            />
                                            <button
                                                onClick={(e) => {
                                                    e.stopPropagation();
                                                    saveEdit();
                                                }}
                                                className="p-1 text-green-600 hover:bg-green-100 rounded"
                                            >
                                                <CheckIcon size={14} />
                                            </button>
                                            <button
                                                onClick={(e) => {
                                                    e.stopPropagation();
                                                    cancelEdit();
                                                }}
                                                className="p-1 text-gray-500 hover:bg-gray-100 rounded"
                                            >
                                                <XIcon size={14} />
                                            </button>
                                        </div>
                                    ) : (
                                        <>
                                            <h3 className="text-sm font-medium text-gray-900 truncate">
                                                {thread.title}
                                            </h3>
                                            <p className="text-xs text-gray-500 mt-1">
                                                {formatDistanceToNow(thread.updatedAt)} ago
                                            </p>
                                            <div className="absolute right-2 top-2 opacity-0 group-hover:opacity-100 transition-opacity flex gap-1">
                                                <button
                                                    onClick={(e) => {
                                                        e.stopPropagation();
                                                        startEditing(thread);
                                                    }}
                                                    className="p-1 text-gray-500 hover:bg-gray-200 rounded"
                                                >
                                                    <EditIcon size={14} />
                                                </button>
                                                <button
                                                    onClick={(e) => {
                                                        e.stopPropagation();
                                                        onThreadDelete(thread.id);
                                                    }}
                                                    className="p-1 text-red-500 hover:bg-red-100 rounded"
                                                >
                                                    <TrashIcon size={14} />
                                                </button>
                                            </div>
                                        </>
                                    )}
                                </div>
                            </div>
                        </div>
                    ))}
                </div>
            </div>

            {/* Future Placeholders */}
            <div className="border-t border-gray-200">
                <div className="p-4 space-y-3">
                    <div className="flex items-center gap-2 text-gray-400 text-sm">
                        <CalendarIcon size={16} />
                        <span>Calendar (Coming Soon)</span>
                    </div>
                    <div className="flex items-center gap-2 text-gray-400 text-sm">
                        <ListTodoIcon size={16} />
                        <span>Todo List (Coming Soon)</span>
                    </div>
                </div>
            </div>
        </div>
    );
}
