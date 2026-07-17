"use client";

import React, { useState } from "react";
import { MinimalAgent } from "@/lib/agents/types";
import { errorHandlingFetcher } from "@/lib/fetcher";
import useSWR, { mutate } from "swr";
import { useRouter } from "next/navigation";
import { useAppRouter } from "@/hooks/appNavigation";
import AgentAvatar from "@/refresh-components/avatars/AgentAvatar";
import Image from "next/image";
import Link from "next/link";
import { createChatSession } from "@/app/app/services/lib";
import { cn } from "@opal/utils";

interface PaginatedAgentResponse {
  items: MinimalAgent[];
  total_items: number;
}

export default function PersonaLibraryPage() {
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("all");
  const [sortBy, setSortBy] = useState("rating");
  const [page, setPage] = useState(0);
  const [tab, setTab] = useState<"all" | "my_personas" | "favorites">("all");
  const router = useRouter();
  const appRouter = useAppRouter();

  const { data: categoriesData } = useSWR<string[]>("/api/persona/categories", errorHandlingFetcher);
  
  const endpoint = `/api/persona/explore?query=${encodeURIComponent(query)}&category=${encodeURIComponent(category)}&sort_by=${sortBy}&page_num=${page}&page_size=20&tab=${tab}`;
  const { data: agentsData, isLoading, mutate } = useSWR<PaginatedAgentResponse>(endpoint, errorHandlingFetcher);

  const handleRate = async (e: React.MouseEvent, agentId: number) => {
    e.stopPropagation();
    try {
      await fetch(`/api/persona/${agentId}/rate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ rating: 5 })
      });
      mutate();
    } catch (err) {
      console.error("Failed to rate persona", err);
    }
  };

  const handleFavorite = async (e: React.MouseEvent, personaId: number) => {
    e.stopPropagation();
    await fetch(`/api/persona/${personaId}/favorite`, { method: "POST" });
    mutate();
  };

  const categories = categoriesData ? ["all", ...categoriesData] : ["all"];

  return (
    <div className="p-8 max-w-7xl mx-auto flex flex-col h-full w-full">
      <div className="flex justify-between items-center mb-4">
        <h1 className="text-4xl font-bold text-text-800">
          PersonaLibrary
        </h1>
        <button 
          onClick={() => window.location.href = '/chat'}
          className="p-2 text-text-500 hover:bg-background-200 rounded-full transition-colors"
          title="Close Library"
        >
          <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12"></path></svg>
        </button>
      </div>
      <p className="text-text-500 mb-8 text-lg">
        Discover and explore curated AI personas.
      </p>

      {/* Tabs */}
      <div className="flex gap-6 border-b border-border mb-6">
        <button
          className={cn("pb-3 px-1 font-semibold text-sm transition-colors border-b-2", tab === "all" ? "border-purple-600 text-purple-600" : "border-transparent text-text-500 hover:text-text-700")}
          onClick={() => { setTab("all"); setPage(0); }}
        >
          All
        </button>
        <button
          className={cn("pb-3 px-1 font-semibold text-sm transition-colors border-b-2", tab === "my_personas" ? "border-purple-600 text-purple-600" : "border-transparent text-text-500 hover:text-text-700")}
          onClick={() => { setTab("my_personas"); setPage(0); }}
        >
          My Personas
        </button>
        <button
          className={cn("pb-3 px-1 font-semibold text-sm transition-colors border-b-2", tab === "favorites" ? "border-purple-600 text-purple-600" : "border-transparent text-text-500 hover:text-text-700")}
          onClick={() => { setTab("favorites"); setPage(0); }}
        >
          Favorites
        </button>
      </div>

      {/* Header Controls */}
      <div className="flex flex-col lg:flex-row justify-between items-start lg:items-center gap-4 mb-8 w-full">
        <div className="flex flex-col md:flex-row flex-1 gap-4 w-full lg:w-auto">
          <input 
            type="text" 
            placeholder="Search personas..."
            className="flex-1 px-4 py-2 bg-white text-gray-900 border border-gray-300 rounded-lg focus:ring-2 focus:ring-purple-500 focus:outline-none placeholder-gray-400"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          <select 
            className="flex-1 px-4 py-2 bg-white text-gray-900 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-purple-500"
            value={category}
            onChange={(e) => setCategory(e.target.value)}
          >
            {categories.map((c) => (
              <option key={c} value={c}>{c === "all" ? "All Categories" : c}</option>
            ))}
          </select>
          <select
            className="flex-1 px-4 py-2 bg-white text-gray-900 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-purple-500"
            value={sortBy}
            onChange={(e) => setSortBy(e.target.value)}
          >
            <option value="rating">Top Rated</option>
            <option value="popular">Most Popular</option>
            <option value="recent">Recently Added</option>
          </select>
        </div>
        <Link 
          href="/app/agents/create" 
          className="w-full lg:w-auto px-6 py-2 bg-gradient-to-r from-blue-600 to-purple-600 text-white font-semibold rounded-lg shadow hover:opacity-90 transition-opacity text-center flex-shrink-0"
        >
          + Create Persona
        </Link>
      </div>

      {/* Grid */}
      {isLoading ? (
        <div className="flex justify-center items-center h-64 w-full">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-purple-600"></div>
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-6">
          {agentsData?.items.map(agent => (
            <div 
              key={agent.id} 
              onClick={async () => {
                try {
                  // Check if there's an existing session with this persona
                  const res = await fetch("/api/chat/get-user-chat-sessions");
                  if (res.ok) {
                    const data = await res.json();
                    const existingSession = data.sessions?.find((s: any) => s.persona_id === agent.id);
                    if (existingSession) {
                      appRouter({ chatSessionId: existingSession.id });
                      return;
                    }
                  }
                  
                  // If no existing session found, create a new one
                  const chatId = await createChatSession(agent.id, null, null);
                  appRouter({ chatSessionId: chatId });
                } catch (e) {
                  console.error("Failed to route to or create chat session:", e);
                  appRouter({ agentId: agent.id });
                }
              }}
              className="group flex flex-col bg-background-100 border border-border shadow-sm rounded-xl overflow-hidden hover:shadow-md transition-all duration-300 cursor-pointer p-5"
            >
              <div className="flex items-start gap-4 mb-3">
                {/* Icon */}
                <div className="h-14 w-14 rounded-full overflow-hidden flex-shrink-0 bg-background-200">
                  <AgentAvatar agent={agent} size={56} />
                </div>
                
                <div className="flex-1 min-w-0">
                  <h3 className="font-bold text-text-800 text-lg line-clamp-1">{agent.name}</h3>
                  {agent.category && (
                    <span className="text-xs text-text-500 font-medium">
                      {agent.category}
                    </span>
                  )}
                </div>

                {/* Edit Button */}
                {(agent.user_permission === "OWNER" || agent.user_permission === "EDITOR") && (
                  <button 
                    onClick={(e) => {
                      e.stopPropagation();
                      router.push(`/app/agents/edit/${agent.id}`);
                    }}
                    className="p-1.5 bg-background-200 border border-border rounded hover:bg-background-300 text-text-600 transition-colors flex-shrink-0"
                    title="Edit Persona"
                  >
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z"></path></svg>
                  </button>
                )}
              </div>
              
              <p className="text-sm text-text-500 line-clamp-3 mb-3 flex-1">
                {agent.description}
              </p>

              {agent.owner && (
                <div className="flex items-center gap-2 mb-4">
                  {agent.owner.profile_photo_id ? (
                    <img src={`/api/persona/image/${agent.owner.profile_photo_id}`} className="w-5 h-5 rounded-full object-cover" />
                  ) : (
                    <div className="w-5 h-5 rounded-full bg-background-200 flex items-center justify-center text-text-500 font-bold text-[10px] select-none">
                      {agent.owner.personal_name?.[0]?.toUpperCase() ?? agent.owner.email?.[0]?.toUpperCase() ?? "U"}
                    </div>
                  )}
                  <span className="text-xs text-text-500 font-medium">
                    By {agent.owner.personal_name || agent.owner.email}
                  </span>
                </div>
              )}
              
              <div className="flex items-center justify-between text-xs mt-auto pt-4 border-t border-border">
                <button 
                  onClick={(e) => handleRate(e, agent.id)}
                  className="flex items-center bg-background-200 hover:bg-background-300 border border-border rounded text-text-700 transition-colors group/star font-medium overflow-hidden"
                  title="Give 5 Stars"
                >
                  <div className="flex items-center gap-1.5 px-2 py-1">
                    <svg className="w-3.5 h-3.5 text-text-500 group-hover/star:text-yellow-500 transition-colors" fill="currentColor" viewBox="0 0 16 16"><path d="M8 .25a.75.75 0 0 1 .673.418l1.882 3.815 4.21.612a.75.75 0 0 1 .416 1.279l-3.046 2.97.719 4.192a.751.751 0 0 1-1.088.791L8 12.347l-3.766 1.98a.75.75 0 0 1-1.088-.79l.72-4.194L.818 6.374a.75.75 0 0 1 .416-1.28l4.21-.611L7.327.668A.75.75 0 0 1 8 .25Z"></path></svg>
                    <span>Star</span>
                  </div>
                  <div className="border-l border-border px-2 py-1 bg-background-100 group-hover/star:bg-background-200 transition-colors font-semibold">
                    {agent.rating_average ? agent.rating_average.toFixed(1) : "0"}
                  </div>
                </button>
                <div className="flex items-center gap-1.5 text-text-500">
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z"></path></svg>
                  <span className="font-medium text-sm">{agent.chat_count || 0}</span>
                </div>
              </div>
            </div>
          ))}
          {(!agentsData?.items || agentsData.items.length === 0) && (
            <div className="col-span-full py-12 text-center text-gray-500">
              No personas found matching your search.
            </div>
          )}
        </div>
      )}

      {/* Pagination (Simple) */}
      {agentsData && agentsData.total_items > 20 && (
        <div className="flex justify-center mt-8 gap-4">
          <button 
            disabled={page === 0}
            onClick={() => setPage(p => p - 1)}
            className="px-4 py-2 border border-gray-300 rounded hover:bg-gray-50 disabled:opacity-50"
          >
            Previous
          </button>
          <button 
            disabled={(page + 1) * 20 >= agentsData.total_items}
            onClick={() => setPage(p => p + 1)}
            className="px-4 py-2 border border-gray-300 rounded hover:bg-gray-50 disabled:opacity-50"
          >
            Next
          </button>
        </div>
      )}
    </div>
  );
}
