"use client";

import React, { useState } from "react";
import { MinimalAgent } from "@/lib/agents/types";
import { errorHandlingFetcher } from "@/lib/fetcher";
import useSWR from "swr";
import { useAppRouter } from "@/hooks/appNavigation";

interface PaginatedAgentResponse {
  items: MinimalAgent[];
  total_items: number;
}

export default function PersonaLibraryPage() {
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("all");
  const [sortBy, setSortBy] = useState("rating");
  const [page, setPage] = useState(0);
  const appRouter = useAppRouter();

  const { data: categoriesData } = useSWR<string[]>("/api/persona/categories", errorHandlingFetcher);
  
  const endpoint = `/api/persona/explore?query=${encodeURIComponent(query)}&category=${encodeURIComponent(category)}&sort_by=${sortBy}&page_num=${page}&page_size=20`;
  const { data: agentsData, isLoading } = useSWR<PaginatedAgentResponse>(endpoint, errorHandlingFetcher);

  const categories = categoriesData ? ["all", ...categoriesData] : ["all"];

  return (
    <div className="p-8 max-w-7xl mx-auto flex flex-col h-full w-full">
      <div className="flex justify-between items-center mb-4">
        <h1 className="text-4xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-blue-500 to-purple-600">
          PersonaLabs
        </h1>
        <button 
          onClick={() => window.location.href = '/chat'}
          className="p-2 text-gray-500 hover:bg-gray-100 rounded-full transition-colors"
          title="Close Library"
        >
          <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12"></path></svg>
        </button>
      </div>
      <p className="text-gray-500 text-lg mb-8">
        Discover and explore curated AI personas.
      </p>

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
        <a 
          href="/app/agents/create" 
          className="w-full lg:w-auto px-6 py-2 bg-gradient-to-r from-blue-600 to-purple-600 text-white font-semibold rounded-lg shadow hover:opacity-90 transition-opacity text-center flex-shrink-0"
        >
          + Create Persona
        </a>
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
              onClick={() => appRouter({ agentId: agent.id })}
              className="group flex flex-col bg-white border border-gray-100 shadow-sm rounded-xl overflow-hidden hover:shadow-xl transition-all duration-300 cursor-pointer transform hover:-translate-y-1"
            >
              {/* Banner */}
              <div className="h-24 bg-gradient-to-r from-purple-100 to-blue-100 w-full flex-shrink-0" />
              
              <div className="px-5 pb-5 pt-0 relative flex-1 flex flex-col">
                {/* Icon */}
                <div className="h-16 w-16 rounded-full bg-white border-4 border-white shadow-md flex items-center justify-center -mt-8 mb-3 overflow-hidden relative">
                  <div className="h-full w-full bg-blue-500 flex items-center justify-center text-white text-2xl font-bold">
                    {agent.name.charAt(0)}
                  </div>
                </div>

                {/* Edit Button */}
                {(agent.user_permission === "OWNER" || agent.user_permission === "EDITOR") && (
                  <div className="absolute top-2 right-4">
                    <button 
                      onClick={(e) => {
                        e.stopPropagation();
                        window.location.href = `/app/agents/edit/${agent.id}`;
                      }}
                      className="p-1.5 bg-white border border-gray-200 rounded shadow-sm hover:bg-gray-50 text-gray-600 transition-colors"
                      title="Edit Persona"
                    >
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z"></path></svg>
                    </button>
                  </div>
                )}
                
                <h3 className="font-bold text-gray-900 text-lg line-clamp-1">{agent.name}</h3>
                {agent.category && (
                  <span className="text-xs text-purple-600 bg-purple-50 px-2 py-1 rounded-full self-start mb-2 mt-1 font-medium">
                    {agent.category}
                  </span>
                )}
                
                <p className="text-sm text-gray-500 line-clamp-2 mt-1 mb-4 flex-1">
                  {agent.description}
                </p>
                
                <div className="flex items-center justify-between text-xs text-gray-400 mt-auto pt-4 border-t border-gray-50">
                  <div className="flex items-center gap-1">
                    <svg className="w-4 h-4 text-yellow-400" fill="currentColor" viewBox="0 0 20 20"><path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z"></path></svg>
                    <span className="font-medium text-gray-600">{agent.rating_average ? agent.rating_average.toFixed(1) : "New"}</span>
                  </div>
                  <div className="flex items-center gap-1">
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z"></path></svg>
                    <span>{agent.chat_count || 0}</span>
                  </div>
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
