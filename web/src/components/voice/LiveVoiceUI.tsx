"use client";

import React, { useEffect, useState, useRef } from "react";
import { LiveSessionClient } from "@/lib/voice/LiveSessionClient";
import { Mic, MicOff, Volume2, VolumeX, X, Settings, ChevronLeft } from "lucide-react";
import { useRouter } from "next/navigation";
import { createPortal } from "react-dom";
import { mutate } from "swr";
import AgentAvatar from "@/refresh-components/avatars/AgentAvatar";
import { useCurrentAgent } from "@/lib/agents/hooks";

export const LiveVoiceUI = ({ chatSessionId, onClose }: { chatSessionId?: string, onClose?: () => void }) => {
  const router = useRouter();
  const [client, setClient] = useState<LiveSessionClient | null>(null);
  const [state, setState] = useState<"disconnected" | "listening" | "thinking" | "speaking" | "idle">("disconnected");
  const [transcript, setTranscript] = useState<string>("");
  const orbRef = useRef<HTMLDivElement>(null);
  const [mounted, setMounted] = useState(false);
  const [createdChatId, setCreatedChatId] = useState<string | null>(null);

  const [isMicMuted, setIsMicMuted] = useState(false);
  const [isSpeakerMuted, setIsSpeakerMuted] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const [disableThinking, setDisableThinking] = useState(false);
  const currentAgent = useCurrentAgent();

  useEffect(() => {
    setMounted(true);

    const onStateChange = (s: "disconnected" | "listening" | "thinking" | "speaking" | "idle") => {
      setState(s);
      if (s === "listening") {
        setTranscript("");
      }
    };

    const onTranscript = (text: string, isFinal: boolean) => {
      setTranscript(text);
    };

    const onAmplitude = (rms: number) => {
      if (orbRef.current) {
        // Map RMS (0 to ~1000+) to a CSS scale value (1 to ~1.3)
        const scale = 1 + Math.min(rms / 800, 0.3);
        const glowSpread = Math.min(rms / 10, 100);
        
        orbRef.current.style.transform = `scale(${scale})`;
        
        // Dynamic glow based on volume
        if (rms > 10) {
          orbRef.current.style.boxShadow = `0 0 ${glowSpread}px ${glowSpread/2}px rgba(255, 255, 255, 0.3)`;
        } else {
          orbRef.current.style.boxShadow = '';
        }
      }
    };

    const onChatSessionId = (id: string) => {
      setCreatedChatId(id);
      // Update the URL behind the scenes so the UI is refreshed on close
      router.replace(`/app?chatId=${id}`);
      // Force Next.js to re-fetch Server Components (like the sidebar) so it appears immediately
      router.refresh();
    };

    const newClient = new LiveSessionClient(onStateChange, onTranscript, onAmplitude, onChatSessionId, chatSessionId, currentAgent?.id);
    setClient(newClient);

    return () => {
      newClient.disconnect();
    };
  }, [chatSessionId]);

  useEffect(() => {
    if (client) {
      client.sendSettings({ disableThinking });
    }
  }, [disableThinking, client]);

  const handleConnect = async () => {
    if (client) {
      setIsMicMuted(false);
      setIsSpeakerMuted(false);
      await client.connect();
    }
  };

  const handleDisconnect = () => {
    if (client) {
      client.disconnect();
    }
  };

  const toggleMic = () => {
    if (client) {
      client.setMicMuted(!isMicMuted);
      setIsMicMuted(!isMicMuted);
    }
  };

  const toggleSpeaker = () => {
    if (client) {
      client.setSpeakerMuted(!isSpeakerMuted);
      setIsSpeakerMuted(!isSpeakerMuted);
    }
  };

  if (!mounted) return null;

  return createPortal(
    <div className="fixed inset-0 z-[99999] flex flex-col items-center justify-between bg-black text-white overflow-hidden selection:bg-indigo-500/30 font-sans" style={{ position: 'fixed', top: 0, left: 0, right: 0, bottom: 0 }}>
      {/* Background gradients */}
      <div className="absolute inset-0 bg-gradient-to-b from-neutral-900/40 via-black to-black pointer-events-none" />
      <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[600px] bg-indigo-500/10 rounded-full blur-[120px] pointer-events-none" />

      {/* Header */}
      <div className="w-full flex justify-between items-center p-6 z-50">
        <button 
          onClick={() => {
            handleDisconnect();
            if (createdChatId) {
              if (onClose) onClose();
              setTimeout(() => {
                window.location.assign(`/app?chatId=${createdChatId}`);
              }, 750);
              return;
            } else if (chatSessionId) {
              if (onClose) onClose();
              setTimeout(() => {
                if (window.location.href.includes(chatSessionId)) {
                  window.location.reload();
                } else {
                  window.location.assign(`/app?chatId=${chatSessionId}`);
                }
              }, 750);
              return;
            }
            if (onClose) {
              onClose();
            } else {
              router.push('/app');
            }
          }}
          className="w-10 h-10 flex items-center justify-center rounded-full bg-white/5 hover:bg-white/10 active:scale-95 transition-all"
        >
          <ChevronLeft className="w-6 h-6 text-white/70" />
        </button>
        <div className="text-xs tracking-[0.2em] uppercase text-white/50 font-medium">
          {state === "disconnected" ? "Ready" : (state === "thinking" && disableThinking ? "Generating" : state)}
        </div>
        <div className="relative">
          <button 
            onClick={() => setShowSettings(!showSettings)}
            className="w-10 h-10 flex items-center justify-center rounded-full bg-white/5 hover:bg-white/10 active:scale-95 transition-all"
          >
            <Settings className="w-5 h-5 text-white/70" />
          </button>
          
          {/* Inline Settings Menu */}
          {showSettings && (
            <div className="absolute top-14 right-0 w-64 bg-neutral-900 border border-white/10 rounded-2xl shadow-2xl p-5 z-[999999] flex flex-col gap-4">
              <h3 className="text-sm font-medium tracking-wide text-white/90 border-b border-white/10 pb-2">Voice Settings</h3>
              
              <div 
                className="flex items-center justify-between gap-4 cursor-pointer group"
                onClick={() => setDisableThinking(!disableThinking)}
              >
                <span className="text-sm text-white/70 group-hover:text-white transition-colors">
                  Disable "Thinking"
                </span>
                <div className={`w-10 h-5 rounded-full transition-colors relative flex items-center p-0.5 ${disableThinking ? 'bg-indigo-500' : 'bg-neutral-700'}`}>
                  <div className={`w-4 h-4 bg-white rounded-full shadow-md transform transition-transform ${disableThinking ? 'translate-x-5' : 'translate-x-0'}`} />
                </div>
              </div>
              
              <p className="text-xs text-white/40 leading-relaxed">
                Disables Chain-of-Thought reasoning for faster responses.
              </p>
            </div>
          )}
        </div>
      </div>

      {/* Main Content - The Orb */}
      <div className="flex-1 flex flex-col items-center justify-center w-full z-10 relative mt-24">
        <div className="relative flex items-center justify-center w-80 h-80">
          {/* Pulsing rings for thinking/listening */}
          <div 
            className={`absolute inset-0 rounded-full border border-white/20 transition-all duration-1000 ${
              state === "thinking" ? "scale-125 opacity-0 animate-[ping_2s_cubic-bezier(0,0,0.2,1)_infinite]" : "scale-100 opacity-0"
            }`} 
          />
          <div 
            className={`absolute inset-0 rounded-full border border-white/10 transition-all duration-1000 delay-150 ${
              state === "thinking" ? "scale-150 opacity-0 animate-[ping_2s_cubic-bezier(0,0,0.2,1)_infinite]" : "scale-100 opacity-0"
            }`} 
          />

          {/* Central Orb */}
          <div 
            ref={orbRef}
            className={`relative w-48 h-48 rounded-full shadow-[0_0_100px_rgba(255,255,255,0.1)] transition-colors duration-700 ease-out border border-white/10 ${
              state === "listening" ? "bg-gradient-to-br from-indigo-500 to-cyan-400" :
              state === "thinking" ? "bg-gradient-to-br from-purple-500 to-pink-500 animate-pulse" :
              state === "speaking" ? "bg-gradient-to-br from-cyan-400 to-blue-500" :
              "bg-gradient-to-br from-neutral-800 to-neutral-900"
            }`}
            style={{ 
              backdropFilter: "blur(40px)",
              transition: "transform 0.05s ease-out, background-color 0.5s ease, box-shadow 0.05s ease-out" 
            }}
          >
            {/* Inner glow */}
            <div className="absolute inset-0 rounded-full bg-gradient-to-tr from-white/10 to-transparent mix-blend-overlay pointer-events-none z-10" />
            
            {/* Avatar inside orb */}
            {currentAgent && (
              <div className="absolute inset-0 flex items-center justify-center pointer-events-none overflow-hidden rounded-full drop-shadow-2xl opacity-90">
                 <AgentAvatar agent={currentAgent} size={192} />
              </div>
            )}
          </div>
        </div>

        {/* Transcript */}
        <div className="mt-16 min-h-[80px] w-full max-w-2xl px-8 text-center flex items-center justify-center">
          <p className="text-xl md:text-2xl font-light leading-relaxed text-white/90">
            {transcript || (state === "listening" ? "I'm listening..." : " ")}
          </p>
        </div>
      </div>

      {/* Bottom Controls */}
      <div className="w-full pb-12 pt-6 px-6 z-10 flex flex-col items-center justify-center gap-8">
        {state === "disconnected" ? (
          <button 
            onClick={handleConnect}
            className="w-20 h-20 bg-white hover:bg-neutral-200 text-black rounded-full flex items-center justify-center active:scale-90 transition-all shadow-[0_0_40px_rgba(255,255,255,0.2)] hover:shadow-[0_0_60px_rgba(255,255,255,0.3)]"
          >
            <Mic className="w-8 h-8" />
          </button>
        ) : (
          <div className="flex items-center gap-8">
            <button 
              onClick={toggleMic}
              className={`w-14 h-14 rounded-full flex items-center justify-center active:scale-90 transition-all ${
                isMicMuted 
                  ? "bg-red-500/20 text-red-400 border border-red-500/30 hover:bg-red-500/30" 
                  : "bg-white/10 text-white hover:bg-white/20 border border-white/5"
              }`}
            >
              {isMicMuted ? <MicOff className="w-6 h-6" /> : <Mic className="w-6 h-6" />}
            </button>

            <button 
              onClick={handleDisconnect}
              className="w-20 h-20 bg-red-500 hover:bg-red-600 text-white rounded-full flex items-center justify-center active:scale-90 transition-all shadow-[0_0_40px_rgba(239,68,68,0.3)] hover:shadow-[0_0_60px_rgba(239,68,68,0.5)]"
            >
              <X className="w-10 h-10" />
            </button>

            <button 
              onClick={toggleSpeaker}
              className={`w-14 h-14 rounded-full flex items-center justify-center active:scale-90 transition-all ${
                isSpeakerMuted 
                  ? "bg-red-500/20 text-red-400 border border-red-500/30 hover:bg-red-500/30" 
                  : "bg-white/10 text-white hover:bg-white/20 border border-white/5"
              }`}
            >
              {isSpeakerMuted ? <VolumeX className="w-6 h-6" /> : <Volume2 className="w-6 h-6" />}
            </button>
          </div>
        )}
      </div>
      
    </div>,
    document.body
  );
};
