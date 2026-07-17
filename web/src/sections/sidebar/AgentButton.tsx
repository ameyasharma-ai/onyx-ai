"use client";

import React, { memo } from "react";
import { MinimalAgent } from "@/lib/agents/types";
import { useCurrentAgent } from "@/lib/agents/hooks";
import { SidebarTab } from "@opal/components";
import AgentAvatar from "@/refresh-components/avatars/AgentAvatar";
import { ChatSession } from "@/app/app/interfaces";

import { createChatSession } from "@/app/app/services/lib";
import { useRouter } from "next/navigation";
import { useState } from "react";

export interface AgentButtonProps {
  agent: MinimalAgent;
  chatSessions?: ChatSession[];
  isPinned?: boolean;
  onTogglePin?: (pinned: boolean) => void;
}

const AgentButton = memo(({ agent, chatSessions, isPinned, onTogglePin }: AgentButtonProps) => {
  const currentAgent = useCurrentAgent();
  const isCurrentAgent = currentAgent?.id === agent.id;
  const router = useRouter();
  const [isCreating, setIsCreating] = useState(false);

  const latestSession = chatSessions?.find((s) => s.persona_id === agent.id);

  const handleClick = async (e: React.MouseEvent) => {
    e.preventDefault();
    if (isCreating) return;
    
    if (latestSession) {
      router.push(`/app?chatId=${latestSession.id}`);
    } else {
      setIsCreating(true);
      try {
        const chatId = await createChatSession(agent.id, null, null);
        router.push(`/app?chatId=${chatId}`);
      } catch (err) {
        console.error("Failed to create chat session:", err);
        router.push(`/app?agentId=${agent.id}`);
      }
      setIsCreating(false);
    }
  };

  return (
    <div className="flex flex-row items-center w-full group gap-2 pr-2">
      <div className="flex-1 min-w-0">
        <SidebarTab
          key={agent.id}
          icon={() => <AgentAvatar agent={agent} />}
          onClick={handleClick}
          type="button"
          selected={isCurrentAgent}
        >
          <div className="flex-1 min-w-0 pr-2">
            <div className="truncate">{agent.name}</div>
          </div>
        </SidebarTab>
      </div>
      
      <div className="flex-none text-text-03/40 text-sm">|</div>

      <button 
        className={`flex-none p-1 transition-opacity ${isPinned ? 'text-yellow-400 opacity-100' : 'text-text-03 opacity-0 group-hover:opacity-100 hover:text-yellow-400'}`}
        onClick={(e) => {
          e.preventDefault();
          e.stopPropagation();
          onTogglePin?.(!isPinned);
        }}
        title={isPinned ? "Unpin agent" : "Pin agent"}
      >
        <svg className="w-4 h-4" fill={isPinned ? "currentColor" : "none"} stroke="currentColor" viewBox="0 0 20 20">
          <path strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z"></path>
        </svg>
      </button>
    </div>
  );
});
AgentButton.displayName = "AgentButton";

export default AgentButton;
