"use client";

import { useEffect } from "react";
import { useRouter, useParams } from "next/navigation";
import { useAgent } from "@/lib/agents/hooks";
import AgentEditorPage from "@/views/AgentEditorPage";

export default function Page() {
  const router = useRouter();
  const params = useParams();
  const id = params?.id as string | undefined;
  
  // Don't parse until id is hydrated
  const agentId = id ? parseInt(id) : null;

  // Call hook unconditionally (passes null when ID is invalid or hydrating)
  const { agent, isLoading, refresh, error } = useAgent(
    agentId === null || isNaN(agentId) ? null : agentId
  );

  // Handle explicitly invalid ID (NaN after parsing a defined string)
  useEffect(() => {
    if (id !== undefined && agentId !== null && isNaN(agentId)) {
      router.push("/app");
    }
  }, [id, agentId, router]);

  // Redirect to home if agent not found (and no explicit error) after loading completes
  useEffect(() => {
    if (agentId !== null && !isNaN(agentId)) {
      if (!isLoading && !agent && !error) {
        router.push("/app");
      }
    }
  }, [agentId, isLoading, agent, error, router]);

  if (error) {
    return (
      <div className="p-8 text-red-500 flex flex-col gap-2">
        <h2 className="text-xl font-bold">Error loading agent</h2>
        <p>{error?.message || String(error)}</p>
      </div>
    );
  }

  // Show nothing while redirecting or loading
  if (isLoading || !agent) return null;

  return <AgentEditorPage agent={agent} refreshAgent={refresh} />;
}
