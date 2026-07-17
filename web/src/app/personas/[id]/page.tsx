"use client";

import React, { useState, useEffect } from "react";
import { useParams, useRouter } from "next/navigation";
import { errorHandlingFetcher } from "@/lib/fetcher";
import useSWR from "swr";
import { Agent } from "@/lib/agents/types";
import { createChatSession } from "@/app/app/services/lib";

export default function PersonaProfilePage() {
  const params = useParams();
  const router = useRouter();
  const id = params?.id as string;

  const { data: agent, isLoading, mutate } = useSWR<Agent>(
    id ? `/api/persona/${id}` : null,
    errorHandlingFetcher
  );

  const handleRate = async (rating: number) => {
    await fetch(`/api/persona/${id}/rate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ rating }),
    });
    mutate();
  };

  const handleFavorite = async () => {
    await fetch(`/api/persona/${id}/favorite`, {
      method: "POST",
    });
    mutate();
  };

  if (isLoading) {
    return (
      <div className="flex h-full w-full justify-center items-center">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-purple-600"></div>
      </div>
    );
  }

  if (!agent) {
    return (
      <div className="flex h-full w-full justify-center items-center text-gray-500">
        Persona not found.
      </div>
    );
  }

  const startChat = async () => {
    try {
      const res = await fetch("/api/chat/get-user-chat-sessions");
      if (res.ok) {
        const data = await res.json();
        const existingSession = data.sessions?.find((s: any) => s.persona_id === agent.id);
        if (existingSession) {
          router.push(`/app?chatId=${existingSession.id}`);
          return;
        }
      }
      const chatId = await createChatSession(agent.id, null, null);
      router.push(`/app?chatId=${chatId}`);
    } catch (e) {
      console.error("Failed to create chat session:", e);
      router.push(`/app?agentId=${id}`);
    }
  };

  const startLiveMode = async () => {
    try {
      const res = await fetch("/api/chat/get-user-chat-sessions");
      let chatIdToUse = null;
      if (res.ok) {
        const data = await res.json();
        const existingSession = data.sessions?.find((s: any) => s.persona_id === agent.id);
        if (existingSession) {
          chatIdToUse = existingSession.id;
        }
      }
      if (!chatIdToUse) {
        chatIdToUse = await createChatSession(agent.id, null, null);
      }
      router.push(`/app?chatId=${chatIdToUse}&live=true`);
    } catch (e) {
      console.error("Failed to create chat session for live mode:", e);
      router.push(`/app?agentId=${id}&live=true`);
    }
  };

  return (
    <div className="flex flex-col h-full w-full bg-gray-50 overflow-y-auto">
      {/* Banner */}
      <div className="h-64 md:h-80 w-full bg-gradient-to-r from-purple-300 via-blue-300 to-indigo-300 relative">
        <button 
          onClick={() => router.push('/personas')}
          className="absolute top-6 left-6 bg-black/20 hover:bg-black/40 text-white rounded-full p-2 backdrop-blur-sm transition-colors"
        >
          <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 19l-7-7m0 0l7-7m-7 7h18" /></svg>
        </button>
      </div>

      <div className="max-w-5xl mx-auto w-full px-6 md:px-12 -mt-24 md:-mt-32 relative pb-20">
        <div className="bg-white rounded-3xl shadow-xl p-8 md:p-12">
          {/* Header Section */}
          <div className="flex flex-col md:flex-row md:items-end gap-8 mb-8 border-b border-gray-100 pb-8">
            <div className="h-32 w-32 md:h-48 md:w-48 rounded-full bg-white border-8 border-white shadow-lg overflow-hidden flex items-center justify-center flex-shrink-0">
               <div className="h-full w-full bg-gradient-to-br from-indigo-500 to-purple-500 flex items-center justify-center text-white text-6xl font-bold">
                 {agent.name.charAt(0)}
               </div>
            </div>
            
            <div className="flex-1">
              <div className="flex items-center gap-4 mb-2">
                <h1 className="text-4xl font-extrabold text-gray-900">{agent.name}</h1>
                <button onClick={handleFavorite} className={`p-2 rounded-full transition-colors ${agent.favorite_count && agent.favorite_count > 0 ? 'text-red-500 bg-red-50' : 'text-gray-400 hover:text-red-500 bg-gray-50 hover:bg-red-50'}`}>
                  <svg className="w-6 h-6" fill={agent.favorite_count && agent.favorite_count > 0 ? 'currentColor' : 'none'} stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4.318 6.318a4.5 4.5 0 000 6.364L12 20.364l7.682-7.682a4.5 4.5 0 00-6.364-6.364L12 7.636l-1.318-1.318a4.5 4.5 0 00-6.364 0z" /></svg>
                </button>
              </div>
              
              <div className="flex items-center gap-6 text-sm text-gray-500 mb-6 font-medium">
                {agent.category && (
                  <span className="px-3 py-1 bg-indigo-50 text-indigo-600 rounded-full">{agent.category}</span>
                )}
                <div className="flex items-center gap-1">
                  <svg className="w-4 h-4 text-yellow-400" fill="currentColor" viewBox="0 0 20 20"><path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z"></path></svg>
                  <span>{agent.rating_average?.toFixed(1) || '0.0'} ({agent.rating_count || 0} reviews)</span>
                </div>
                <div className="flex items-center gap-1">
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z"></path></svg>
                  <span>{agent.chat_count || 0} chats</span>
                </div>
              </div>

              <div className="flex flex-wrap gap-4">
                <button onClick={startChat} className="px-6 py-3 bg-gray-900 text-white font-semibold rounded-xl hover:bg-gray-800 transition-colors shadow-sm flex items-center gap-2">
                  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" /></svg>
                  Chat Now
                </button>
                <button onClick={startLiveMode} className="px-6 py-3 bg-gradient-to-r from-purple-600 to-indigo-600 text-white font-semibold rounded-xl hover:from-purple-700 hover:to-indigo-700 transition-colors shadow-md flex items-center gap-2">
                  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" /></svg>
                  Live Mode
                </button>
              </div>
            </div>
          </div>

          {/* Details Section */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-12">
            <div className="lg:col-span-2 space-y-8">
              <section>
                <h2 className="text-2xl font-bold text-gray-900 mb-4">About</h2>
                <p className="text-gray-700 leading-relaxed text-lg whitespace-pre-wrap">
                  {agent.long_description || agent.description}
                </p>
              </section>

              {agent.starter_messages && agent.starter_messages.length > 0 && (
                <section>
                  <h2 className="text-xl font-bold text-gray-900 mb-4">Conversation Starters</h2>
                  <div className="grid gap-3">
                    {agent.starter_messages.map((sm, idx) => (
                      <div key={idx} className="p-4 bg-gray-50 border border-gray-100 rounded-xl hover:bg-indigo-50 hover:border-indigo-100 transition-colors cursor-pointer text-gray-700">
                        "{sm.message}"
                      </div>
                    ))}
                  </div>
                </section>
              )}
            </div>

            <div className="space-y-8">
              <section className="bg-gray-50 rounded-2xl p-6 border border-gray-100">
                <h3 className="text-lg font-bold text-gray-900 mb-4">Traits</h3>
                <div className="space-y-4">
                  <div>
                    <div className="text-sm text-gray-500 mb-1">Creativity / Temperature</div>
                    <div className="w-full bg-gray-200 rounded-full h-2">
                      <div className="bg-indigo-500 h-2 rounded-full" style={{ width: `${(agent.temperature || 0) * 100}%` }}></div>
                    </div>
                  </div>
                  <div>
                    <div className="text-sm text-gray-500 mb-1">Voice Profile</div>
                    <div className="font-medium text-gray-900">{agent.voice_id ? "Custom Voice" : "Standard Voice"}</div>
                  </div>
                </div>
              </section>

              {agent.tags && agent.tags.length > 0 && (
                <section>
                  <h3 className="text-lg font-bold text-gray-900 mb-4">Tags</h3>
                  <div className="flex flex-wrap gap-2">
                    {agent.tags.map(tag => (
                      <span key={tag} className="px-3 py-1 bg-white border border-gray-200 text-gray-600 rounded-full text-sm font-medium shadow-sm">
                        {tag}
                      </span>
                    ))}
                  </div>
                </section>
              )}

              <section>
                <h3 className="text-lg font-bold text-gray-900 mb-4">Rate this Persona</h3>
                <div className="flex items-center gap-2">
                  {[1, 2, 3, 4, 5].map((star) => (
                    <button 
                      key={star}
                      onClick={() => handleRate(star)}
                      className="text-gray-300 hover:text-yellow-400 hover:scale-110 transition-all focus:outline-none"
                    >
                      <svg className="w-8 h-8" fill="currentColor" viewBox="0 0 20 20"><path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z"></path></svg>
                    </button>
                  ))}
                </div>
              </section>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
