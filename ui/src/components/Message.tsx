'use client';

import React from 'react';
import Image from 'next/image';
import { Message as MessageType, SourceRef } from '@/types';
import { UserIcon, BotIcon, ExternalLinkIcon, ImageIcon, MicIcon, PaperclipIcon } from 'lucide-react';
import { formatDistanceToNow } from 'date-fns';
import ReactMarkdown from 'react-markdown';

interface MessageProps {
    message: MessageType;
    searchQuery?: string;
}

export default function Message({ message, searchQuery }: MessageProps) {
    const isUser = message.type === 'user';

    const renderAttachment = (attachment: { id: string; name: string; type: string; data?: string }) => {
        switch (attachment.type) {
            case 'image':
                return (
                    <div key={attachment.id} className="mt-2">
                        <div className="flex items-center gap-2 text-sm text-gray-600 mb-1">
                            <ImageIcon size={16} />
                            {attachment.name}
                        </div>
                        {attachment.data && (
                            <div className="relative max-w-xs">
                                <Image
                                    src={attachment.data}
                                    alt={attachment.name}
                                    width={300}
                                    height={200}
                                    className="rounded-lg border object-cover"
                                    style={{ maxWidth: '100%', height: 'auto' }}
                                />
                            </div>
                        )}
                    </div>
                );
            case 'audio':
                return (
                    <div key={attachment.id} className="mt-2">
                        <div className="flex items-center gap-2 text-sm text-gray-600 mb-1">
                            <MicIcon size={16} />
                            {attachment.name}
                        </div>
                        {attachment.data && (
                            <audio controls className="max-w-xs">
                                <source src={attachment.data} />
                                Your browser does not support the audio element.
                            </audio>
                        )}
                    </div>
                );
            default:
                return (
                    <div key={attachment.id} className="mt-2 flex items-center gap-2 text-sm text-gray-600">
                        <PaperclipIcon size={16} />
                        {attachment.name}
                    </div>
                );
        }
    };

    const renderSources = (sources: SourceRef[]) => {
        if (!sources || sources.length === 0) return null;

        return (
            <div className="mt-3 pt-3 border-t border-gray-100">
                <div className="text-xs font-medium text-gray-500 mb-2">Sources:</div>
                <div className="space-y-1">
                    {sources.map((source, index) => (
                        <div key={source.id || index} className="flex items-center gap-2 text-xs text-gray-600">
                            <div className="w-4 h-4 bg-gray-200 rounded-full flex items-center justify-center text-xs font-mono">
                                {index + 1}
                            </div>
                            {source.url ? (
                                <a
                                    href={source.url}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    className="flex items-center gap-1 hover:text-blue-600"
                                >
                                    <span className="truncate">{source.title || source.url}</span>
                                    <ExternalLinkIcon size={10} />
                                </a>
                            ) : (
                                <span className="truncate">{source.title || source.id}</span>
                            )}
                        </div>
                    ))}
                </div>
            </div>
        );
    };

    const highlightText = (text: string, query?: string) => {
        if (!query) return text;

        const parts = text.split(new RegExp(`(${query})`, 'gi'));
        return parts.map((part, index) =>
            part.toLowerCase() === query.toLowerCase() ?
                <mark key={index} className="bg-yellow-200 px-1 rounded">{part}</mark> : part
        );
    };

    return (
        <div className={`flex gap-4 p-6 ${isUser ? 'bg-gray-50' : 'bg-white'}`}>
            {/* Avatar */}
            <div className={`w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0 ${isUser ? 'bg-blue-600 text-white' : 'bg-gray-200 text-gray-600'
                }`}>
                {isUser ? <UserIcon size={16} /> : <BotIcon size={16} />}
            </div>

            {/* Content */}
            <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-1">
                    <span className="text-sm font-medium text-gray-900">
                        {isUser ? 'You' : 'MindVault'}
                    </span>
                    <span className="text-xs text-gray-500">
                        {formatDistanceToNow(message.timestamp)} ago
                    </span>
                </div>

                {/* Message Content */}
                <div className="text-gray-800">
                    {isUser ? (
                        <div className="whitespace-pre-wrap">{highlightText(message.content, searchQuery)}</div>
                    ) : (
                        <div className="prose prose-sm max-w-none">
                            <ReactMarkdown>{message.content}</ReactMarkdown>
                        </div>
                    )}
                </div>

                {/* Attachments */}
                {message.attachments && message.attachments.length > 0 && (
                    <div className="mt-2">
                        {message.attachments.map(renderAttachment)}
                    </div>
                )}

                {/* Sources */}
                {message.sources && renderSources(message.sources)}
            </div>
        </div>
    );
}
