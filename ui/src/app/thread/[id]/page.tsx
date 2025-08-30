'use client';

import { useParams } from 'next/navigation';
import ChatLayout from '@/components/ChatLayout';

export default function ThreadPage() {
    const params = useParams();
    const threadId = params.id as string;

    return <ChatLayout initialThreadId={threadId} />;
}

