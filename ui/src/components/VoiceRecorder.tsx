'use client';

import React, { useState, useRef, useEffect } from 'react';
import { MicIcon, Square, PlayIcon, PauseIcon, TrashIcon, SendIcon } from 'lucide-react';

interface VoiceRecorderProps {
    onRecordingComplete: (audioBlob: Blob, transcript?: string) => void;
    onClose: () => void;
}

export default function VoiceRecorder({ onRecordingComplete, onClose }: VoiceRecorderProps) {
    const [isRecording, setIsRecording] = useState(false);
    const [recordingTime, setRecordingTime] = useState(0);
    const [audioBlob, setAudioBlob] = useState<Blob | null>(null);
    const [isPlaying, setIsPlaying] = useState(false);
    const [isTranscribing, setIsTranscribing] = useState(false);

    const mediaRecorderRef = useRef<MediaRecorder | null>(null);
    const audioRef = useRef<HTMLAudioElement | null>(null);
    const chunksRef = useRef<Blob[]>([]);
    const timerRef = useRef<NodeJS.Timeout | null>(null);

    useEffect(() => {
        return () => {
            if (timerRef.current) {
                clearInterval(timerRef.current);
            }
            if (mediaRecorderRef.current && mediaRecorderRef.current.state === 'recording') {
                mediaRecorderRef.current.stop();
            }
        };
    }, []);

    const startRecording = async () => {
        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            const mediaRecorder = new MediaRecorder(stream);
            mediaRecorderRef.current = mediaRecorder;
            chunksRef.current = [];

            mediaRecorder.ondataavailable = (event) => {
                if (event.data.size > 0) {
                    chunksRef.current.push(event.data);
                }
            };

            mediaRecorder.onstop = () => {
                const blob = new Blob(chunksRef.current, { type: 'audio/webm' });
                setAudioBlob(blob);
                stream.getTracks().forEach(track => track.stop());
            };

            mediaRecorder.start();
            setIsRecording(true);
            setRecordingTime(0);

            timerRef.current = setInterval(() => {
                setRecordingTime(prev => prev + 1);
            }, 1000);
        } catch (error) {
            console.error('Error starting recording:', error);
            alert('Could not access microphone. Please check permissions.');
        }
    };

    const stopRecording = () => {
        if (mediaRecorderRef.current && mediaRecorderRef.current.state === 'recording') {
            mediaRecorderRef.current.stop();
            setIsRecording(false);
            if (timerRef.current) {
                clearInterval(timerRef.current);
            }
        }
    };

    const playRecording = () => {
        if (audioBlob && !isPlaying) {
            const audio = new Audio(URL.createObjectURL(audioBlob));
            audioRef.current = audio;

            audio.onended = () => {
                setIsPlaying(false);
            };

            audio.play();
            setIsPlaying(true);
        } else if (audioRef.current && isPlaying) {
            audioRef.current.pause();
            audioRef.current.currentTime = 0;
            setIsPlaying(false);
        }
    };

    const deleteRecording = () => {
        setAudioBlob(null);
        setRecordingTime(0);
        setIsPlaying(false);
        if (audioRef.current) {
            audioRef.current.pause();
        }
    };

    const sendRecording = async () => {
        if (!audioBlob) return;

        setIsTranscribing(true);

        try {
            // For now, we'll send the audio without transcription
            // In a real implementation, you would call a transcription service here
            // const transcript = await transcribeAudio(audioBlob);

            onRecordingComplete(audioBlob);
            onClose();
        } catch (error) {
            console.error('Error processing recording:', error);
            // Send without transcript if transcription fails
            onRecordingComplete(audioBlob);
            onClose();
        } finally {
            setIsTranscribing(false);
        }
    };

    const formatTime = (seconds: number) => {
        const mins = Math.floor(seconds / 60);
        const secs = seconds % 60;
        return `${mins}:${secs.toString().padStart(2, '0')}`;
    };

    return (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
            <div className="bg-white rounded-lg p-6 w-96 max-w-[90vw]">
                <div className="text-center mb-6">
                    <h3 className="text-lg font-semibold mb-2">Voice Message</h3>
                    <div className="text-2xl font-mono text-gray-600">
                        {formatTime(recordingTime)}
                    </div>
                </div>

                <div className="flex justify-center mb-6">
                    {!isRecording && !audioBlob && (
                        <button
                            onClick={startRecording}
                            className="w-16 h-16 bg-red-500 text-white rounded-full flex items-center justify-center hover:bg-red-600 transition-colors"
                        >
                            <MicIcon size={24} />
                        </button>
                    )}

                    {isRecording && (
                        <button
                            onClick={stopRecording}
                            className="w-16 h-16 bg-red-500 text-white rounded-full flex items-center justify-center hover:bg-red-600 transition-colors animate-pulse"
                        >
                            <Square size={24} />
                        </button>
                    )}

                    {audioBlob && !isRecording && (
                        <div className="flex gap-3">
                            <button
                                onClick={playRecording}
                                className="w-12 h-12 bg-blue-500 text-white rounded-full flex items-center justify-center hover:bg-blue-600 transition-colors"
                            >
                                {isPlaying ? <PauseIcon size={20} /> : <PlayIcon size={20} />}
                            </button>
                            <button
                                onClick={deleteRecording}
                                className="w-12 h-12 bg-gray-500 text-white rounded-full flex items-center justify-center hover:bg-gray-600 transition-colors"
                            >
                                <TrashIcon size={20} />
                            </button>
                            <button
                                onClick={sendRecording}
                                disabled={isTranscribing}
                                className="w-12 h-12 bg-green-500 text-white rounded-full flex items-center justify-center hover:bg-green-600 transition-colors disabled:opacity-50"
                            >
                                {isTranscribing ? (
                                    <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-white"></div>
                                ) : (
                                    <SendIcon size={20} />
                                )}
                            </button>
                        </div>
                    )}
                </div>

                <div className="text-center text-sm text-gray-600 mb-4">
                    {!isRecording && !audioBlob && 'Click the microphone to start recording'}
                    {isRecording && 'Recording... Click stop when finished'}
                    {audioBlob && !isRecording && 'Play to review, then send or delete'}
                    {isTranscribing && 'Processing audio...'}
                </div>

                <div className="flex justify-center">
                    <button
                        onClick={onClose}
                        className="px-4 py-2 text-gray-600 hover:text-gray-800 transition-colors"
                    >
                        Cancel
                    </button>
                </div>
            </div>
        </div>
    );
}
