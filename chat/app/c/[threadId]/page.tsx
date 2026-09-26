"use client";

import { use } from "react";
import { Conversation } from "@/components/Conversation";

export default function ChatThreadPage({
  params,
}: {
  params: Promise<{ threadId: string }>;
}) {
  const { threadId } = use(params);

  return (
    <main className="mx-auto min-h-dvh w-full max-w-6xl px-6 pt-8 pb-8 lg:px-10">
      <h1 className="mb-4 text-lg font-semibold">Tiffin Support Chat</h1>
      <Conversation initialThreadId={decodeURIComponent(threadId)} />
    </main>
  );
}
