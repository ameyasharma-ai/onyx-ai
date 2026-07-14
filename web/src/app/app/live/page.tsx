import React from "react";
import { LiveVoiceUI } from "@/components/voice/LiveVoiceUI";

export default async function LiveVoicePage({
  searchParams,
}: {
  searchParams: Promise<{ [key: string]: string | string[] | undefined }>;
}) {
  const resolvedParams = await searchParams;
  const chatSessionId = typeof resolvedParams?.chatSessionId === 'string' ? resolvedParams.chatSessionId : undefined;

  return (
    <main className="w-full h-full min-h-screen bg-black">
      <LiveVoiceUI chatSessionId={chatSessionId} />
    </main>
  );
}
