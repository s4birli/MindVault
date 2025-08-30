'use client';

import React, { useState, useRef, KeyboardEvent } from 'react';
import { SendIcon, PaperclipIcon, MicIcon, ImageIcon } from 'lucide-react';
import { Attachment } from '@/types';
import VoiceRecorder from './VoiceRecorder';

interface MessageInputProps {
    onSendMessage: (content: string, attachments?: Attachment[]) => void;
    disabled?: boolean;
}

export default function MessageInput({ onSendMessage, disabled }: MessageInputProps) {
    const [message, setMessage] = useState('');
    const [attachments, setAttachments] = useState<Attachment[]>([]);
    const [showVoiceRecorder, setShowVoiceRecorder] = useState(false);
    const textareaRef = useRef<HTMLTextAreaElement>(null);
    const fileInputRef = useRef<HTMLInputElement>(null);

    const handleSend = () => {
        if (message.trim() || attachments.length > 0) {
            onSendMessage(message.trim(), attachments);
            setMessage('');
            setAttachments([]);
            if (textareaRef.current) {
                textareaRef.current.style.height = 'auto';
            }
        }
    };

    const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            handleSend();
        }
    };

    const handleTextareaChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
        setMessage(e.target.value);

        // Auto-resize textarea
        if (textareaRef.current) {
            textareaRef.current.style.height = 'auto';
            textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 200)}px`;
        }
    };

    const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
        const files = e.target.files;
        if (!files) return;

        Array.from(files).forEach((file) => {
            // Check file size (limit to 10MB)
            if (file.size > 10 * 1024 * 1024) {
                alert(`File ${file.name} is too large. Maximum size is 10MB.`);
                return;
            }

            const reader = new FileReader();
            reader.onload = (event) => {
                let fileType: 'image' | 'audio' | 'text' = 'text';

                if (file.type.startsWith('image/')) {
                    fileType = 'image';
                } else if (file.type.startsWith('audio/')) {
                    fileType = 'audio';
                } else if (file.type.includes('pdf') || file.type.includes('document') || file.type.includes('text')) {
                    fileType = 'text';
                }

                const attachment: Attachment = {
                    id: Math.random().toString(36).substring(7),
                    name: file.name,
                    type: fileType,
                    data: event.target?.result as string,
                    size: file.size,
                };
                setAttachments(prev => [...prev, attachment]);
            };
            reader.readAsDataURL(file);
        });

        // Reset file input
        e.target.value = '';
    };

    const removeAttachment = (id: string) => {
        setAttachments(prev => prev.filter(att => att.id !== id));
    };

    const handleVoiceRecording = (audioBlob: Blob, transcript?: string) => {
        if (transcript) {
            // If we have a transcript, send it as text
            onSendMessage(transcript);
        } else {
            // Otherwise, send as audio attachment
            const reader = new FileReader();
            reader.onload = (event) => {
                const attachment: Attachment = {
                    id: Math.random().toString(36).substring(7),
                    name: `voice-message-${Date.now()}.webm`,
                    type: 'audio',
                    data: event.target?.result as string,
                    size: audioBlob.size,
                };
                onSendMessage('🎤 Voice Message', [attachment]);
            };
            reader.readAsDataURL(audioBlob);
        }
        setShowVoiceRecorder(false);
    };

    return (
        <div className="border-t border-gray-200 bg-white">
            {/* Attachments Preview */}
            {attachments.length > 0 && (
                <div className="p-4 border-b border-gray-100">
                    <div className="flex flex-wrap gap-2">
                        {attachments.map((attachment) => (
                            <div
                                key={attachment.id}
                                className="flex items-center gap-2 bg-gray-100 rounded-lg p-2 text-sm"
                            >
                                {attachment.type === 'image' && <ImageIcon size={16} />}
                                {attachment.type === 'audio' && <MicIcon size={16} />}
                                {attachment.type === 'text' && <PaperclipIcon size={16} />}
                                <span className="truncate max-w-32">{attachment.name}</span>
                                <button
                                    onClick={() => removeAttachment(attachment.id)}
                                    className="text-gray-500 hover:text-red-500"
                                >
                                    ×
                                </button>
                            </div>
                        ))}
                    </div>
                </div>
            )}

            <div className="p-4">
                <div className="flex items-end gap-3">
                    {/* Attachment Button */}
                    <div className="relative">
                        <button
                            onClick={() => fileInputRef.current?.click()}
                            disabled={disabled}
                            className="p-2 text-gray-500 hover:text-gray-700 hover:bg-gray-100 rounded-lg transition-colors disabled:opacity-50"
                        >
                            <PaperclipIcon size={20} />
                        </button>
                        <input
                            ref={fileInputRef}
                            type="file"
                            multiple
                            accept="image/*,audio/*,video/*,.txt,.pdf,.doc,.docx,.csv,.json,.md,.rtf"
                            onChange={handleFileSelect}
                            className="hidden"
                        />
                    </div>

                    {/* Voice Recording Button */}
                    <button
                        onClick={() => setShowVoiceRecorder(true)}
                        disabled={disabled}
                        className="p-2 text-gray-500 hover:text-gray-700 hover:bg-gray-100 rounded-lg transition-colors disabled:opacity-50"
                    >
                        <MicIcon size={20} />
                    </button>

                    {/* Text Input */}
                    <div className="flex-1 relative">
                        <textarea
                            ref={textareaRef}
                            value={message}
                            onChange={handleTextareaChange}
                            onKeyDown={handleKeyDown}
                            placeholder="Type your message..."
                            disabled={disabled}
                            className="w-full p-3 border border-gray-300 rounded-lg resize-none focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent disabled:opacity-50 disabled:cursor-not-allowed"
                            rows={1}
                            style={{ minHeight: '48px', maxHeight: '200px' }}
                        />
                    </div>

                    {/* Send Button */}
                    <button
                        onClick={handleSend}
                        disabled={disabled || (!message.trim() && attachments.length === 0)}
                        className="p-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                        <SendIcon size={20} />
                    </button>
                </div>

                <div className="mt-2 text-xs text-gray-500">
                    Press Enter to send, Shift+Enter for new line
                </div>
            </div>

            {/* Voice Recorder Modal */}
            {showVoiceRecorder && (
                <VoiceRecorder
                    onRecordingComplete={handleVoiceRecording}
                    onClose={() => setShowVoiceRecorder(false)}
                />
            )}
        </div>
    );
}
