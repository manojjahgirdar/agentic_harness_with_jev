"use client";

import { Conversation } from "@/components/Conversation";

export default function NewChatPage() {
  return (
    <main className="mx-auto min-h-dvh w-full max-w-6xl px-6 pt-8 pb-8 lg:px-10">
      <h1 className="mb-4 text-lg font-semibold">Tiffin Support Chat</h1>
      <Conversation />
    </main>
  );
}
