'use client';

import React, { useEffect, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Thread, Attachment } from '@/types';
import Message from './Message';
import MessageInput from './MessageInput';
import { askAPI, agentAPI } from '@/lib/api';
import { storage } from '@/lib/storage';
import { LoaderIcon } from 'lucide-react';

interface ChatAreaProps {
    thread?: Thread;
    onThreadUpdate: (thread: Thread) => void;
    searchQuery?: string;
}

export default function ChatArea({ thread, onThreadUpdate, searchQuery }: ChatAreaProps) {
    const [isLoading, setIsLoading] = useState(false);
    const messagesEndRef = useRef<HTMLDivElement>(null);
    const router = useRouter();

    const scrollToBottom = () => {
        messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    };

    useEffect(() => {
        scrollToBottom();
    }, [thread?.messages]);

    const handleSendMessage = async (content: string, attachments?: Attachment[]) => {
        setIsLoading(true);

        // Create new thread if none exists (fallback case)
        let currentThread = thread;
        if (!currentThread) {
            currentThread = await storage.createThread();
            onThreadUpdate(currentThread);
            // Navigate to the new thread URL
            router.push(`/thread/${currentThread.id}`);
        }

        // Add user message
        await storage.addMessage(currentThread.id, {
            threadId: currentThread.id,
            content,
            type: 'user',
            attachments,
        });

        // Update thread with user message
        const updatedThread = await storage.getThread(currentThread.id);
        if (updatedThread) {
            onThreadUpdate(updatedThread);
        }

        try {
            // Determine if this looks like an agent request or a regular ask request
            const isAgentRequest = content.toLowerCase().includes('find') ||
                content.toLowerCase().includes('search') ||
                content.toLowerCase().includes('summarize') ||
                content.toLowerCase().includes('local');

            let assistantContent = '';
            let sources: Array<{ id: string; title?: string; url?: string }> = [];

            if (isAgentRequest) {
                // Try agent first
                const agentResponse = await agentAPI.act({
                    text: content,
                    thread_id: currentThread.id,
                });

                if (agentResponse.result && !agentResponse.result.error) {
                    // Format search.find results nicely
                    if (agentResponse.intent === 'search.find' && agentResponse.result.items) {
                        const items = agentResponse.result.items as Array<{
                            id: string;
                            title: string;
                            preview: string;
                            score: number;
                            provider: string;
                            url: string;
                            ts: string;
                            snippet: string;
                        }>;

                        assistantContent = `🔍 **Search Results**

I found **${agentResponse.result.total || 0}** relevant documents. Here are the top results:

${items.map((item, index) => `**${index + 1}. ${item.title}**
📧 ${item.provider} • 📅 ${new Date(item.ts).toLocaleDateString()}
📝 ${item.snippet.substring(0, 200)}${item.snippet.length > 200 ? '...' : ''}
🔗 [Open](${item.url})
`).join('\n')}

${agentResponse.result.has_more ? `\n📄 *Showing ${items.length} of ${agentResponse.result.total} total results*` : ''}`;

                        // Convert items to sources format for UI
                        sources = items.map(item => ({
                            id: item.id,
                            title: item.title,
                            url: item.url
                        }));
                    } else if (agentResponse.intent === 'search.local' && agentResponse.result.items) {
                        // Format search.local results
                        const items = agentResponse.result.items as Array<Record<string, unknown>>;
                        assistantContent = `📁 **Local Files Found**

I found **${agentResponse.result.total || 0}** local files. Here are the results:

${items.map((item, index) => `**${index + 1}. ${item.title || item.name || 'Unnamed'}**
📄 ${item.type || 'file'} • 📅 ${item.ts ? new Date(item.ts as string).toLocaleDateString() : 'Unknown date'}
📝 ${((item.snippet as string) || (item.preview as string) || '').substring(0, 200)}
${item.path ? `📂 ${item.path}` : ''}
`).join('\n')}`;
                    } else if (agentResponse.intent === 'search.summarize' && agentResponse.result.summary) {
                        // Format summarize results
                        assistantContent = `📋 **Summary**

${agentResponse.result.summary}

${agentResponse.result.documents_processed ? `📊 *Based on ${agentResponse.result.documents_processed} documents*` : ''}`;
                    } else {
                        // Generic formatting for other responses
                        assistantContent = (agentResponse.result.message as string) ||
                            `🤖 **${agentResponse.intent || 'Agent'} Response**\n\n${JSON.stringify(agentResponse.result, null, 2)}`;
                        if (agentResponse.result.sources) {
                            sources = agentResponse.result.sources as Array<{ id: string; title?: string; url?: string }>;
                        }
                    }
                } else {
                    // Fallback to ask API
                    const askResponse = await askAPI.ask({
                        query: content,
                        final_n: 5,
                        language: 'auto',
                        max_sentences: 3,
                    });
                    assistantContent = askResponse.answer;
                    sources = askResponse.sources || [];
                }
            } else {
                // Regular ask request
                const askResponse = await askAPI.ask({
                    query: content,
                    final_n: 5,
                    language: 'auto',
                    max_sentences: 3,
                });
                assistantContent = askResponse.answer;
                sources = askResponse.sources || [];
            }

            // Add assistant message
            await storage.addMessage(currentThread.id, {
                threadId: currentThread.id,
                content: assistantContent,
                type: 'assistant',
                sources,
            });

            // Update thread with assistant message
            const finalThread = await storage.getThread(currentThread.id);
            if (finalThread) {
                onThreadUpdate(finalThread);
            }

        } catch (error) {
            console.error('Error sending message:', error);

            // Add mock response when backend is not available
            let mockResponse = '';
            if (content.toLowerCase().includes('find') || content.toLowerCase().includes('search')) {
                mockResponse = `🔍 **Search Results** (Mock Response - Backend not running)

I would search for: &quot;${content}&quot;

**Mock Results:**
• Document 1: AI Research Paper (2024)
• Document 2: Machine Learning Guide
• Document 3: Project Documentation

*Note: Start the backend with \`docker compose up api db\` to get real results from your documents.*`;
            } else {
                mockResponse = `🤖 **MindVault Response** (Mock - Backend not running)

I received your message: &quot;${content}&quot;

This is a mock response since the backend is not running. To get real AI responses:

1. Start Docker Desktop
2. Run: \`docker compose -f docker-compose.dev.yml up api db\`
3. Wait for services to be ready
4. Try your message again

*Your message has been saved locally and will work with the backend once it's running.*`;
            }

            // Add mock response message
            await storage.addMessage(currentThread.id, {
                threadId: currentThread.id,
                content: mockResponse,
                type: 'assistant',
            });

            const errorThread = await storage.getThread(currentThread.id);
            if (errorThread) {
                onThreadUpdate(errorThread);
            }
        } finally {
            setIsLoading(false);
        }
    };

    if (!thread) {
        return (
            <div className="flex-1 flex items-center justify-center bg-gray-50">
                <div className="text-center max-w-md mx-auto p-6">
                    <div className="w-16 h-16 bg-gradient-to-br from-blue-500 to-purple-600 rounded-full flex items-center justify-center mx-auto mb-4">
                        <span className="text-white font-bold text-xl">MV</span>
                    </div>
                    <h2 className="text-2xl font-semibold text-gray-900 mb-2">Welcome to MindVault</h2>
                    <p className="text-gray-600 mb-6">Your AI assistant is ready to help. Start a conversation by typing a message or recording a voice note.</p>
                    <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 text-sm text-blue-800 mb-4">
                        💡 <strong>Tip:</strong> Try asking questions like &quot;search for documents about...&quot; or &quot;find information on...&quot; to use the search agents.
                    </div>

                    {/* Quick Test Buttons */}
                    <div className="space-y-2">
                        <p className="text-sm font-medium text-gray-700">Quick Test Commands:</p>
                        <div className="flex flex-wrap gap-2">
                            <button
                                onClick={() => handleSendMessage("find documents about AI", [])}
                                className="px-3 py-1 bg-blue-100 text-blue-700 rounded-full text-xs hover:bg-blue-200 transition-colors"
                            >
                                Test search.find
                            </button>
                            <button
                                onClick={() => handleSendMessage("search local files for project", [])}
                                className="px-3 py-1 bg-green-100 text-green-700 rounded-full text-xs hover:bg-green-200 transition-colors"
                            >
                                Test search.local
                            </button>
                            <button
                                onClick={() => handleSendMessage("summarize recent documents", [])}
                                className="px-3 py-1 bg-purple-100 text-purple-700 rounded-full text-xs hover:bg-purple-200 transition-colors"
                            >
                                Test search.summarize
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        );
    }

    return (
        <div className="flex-1 flex flex-col bg-white">
            {/* Messages */}
            <div className="flex-1 overflow-y-auto scrollbar-thin">
                {thread.messages.length === 0 ? (
                    <div className="flex items-center justify-center h-full">
                        <div className="text-center">
                            <h3 className="text-lg font-medium text-gray-900 mb-2">Start a conversation</h3>
                            <p className="text-gray-600">Ask me anything or upload files to get started.</p>
                        </div>
                    </div>
                ) : (
                    <div>
                        {thread.messages
                            .filter(message => {
                                if (!searchQuery) return true;
                                return message.content.toLowerCase().includes(searchQuery.toLowerCase());
                            })
                            .map((message) => (
                                <Message key={message.id} message={message} searchQuery={searchQuery} />
                            ))}

                        {isLoading && (
                            <div className="flex gap-4 p-6 bg-white">
                                <div className="w-8 h-8 rounded-full bg-gray-200 text-gray-600 flex items-center justify-center">
                                    <LoaderIcon size={16} className="animate-spin" />
                                </div>
                                <div className="flex-1">
                                    <div className="flex items-center gap-2 mb-1">
                                        <span className="text-sm font-medium text-gray-900">MindVault</span>
                                        <span className="text-xs text-gray-500">thinking...</span>
                                    </div>
                                    <div className="flex items-center gap-2">
                                        <div className="animate-pulse flex space-x-1">
                                            <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce"></div>
                                            <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '0.1s' }}></div>
                                            <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '0.2s' }}></div>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        )}
                        <div ref={messagesEndRef} />
                    </div>
                )}
            </div>

            {/* Input */}
            <MessageInput onSendMessage={handleSendMessage} disabled={isLoading} />
        </div>
    );
}
