type LiveSessionState = "disconnected" | "listening" | "thinking" | "speaking" | "idle";

type StateCallback = (state: LiveSessionState) => void;
type TranscriptCallback = (text: string, isFinal: boolean) => void;
type AmplitudeCallback = (rms: number) => void;

export class LiveSessionClient {
  private ws: WebSocket | null = null;
  private audioContext: AudioContext | null = null;
  private mediaStream: MediaStream | null = null;
  private workletNode: AudioWorkletNode | null = null;
  private source: MediaStreamAudioSourceNode | null = null;
  
  private backendState: LiveSessionState = "disconnected";
  private currentState: LiveSessionState = "disconnected";
  private onStateChange: StateCallback | null = null;
  private onTranscript: TranscriptCallback | null = null;
  private onAmplitude: AmplitudeCallback | null = null;
  private onChatSessionId: ((id: string) => void) | null = null;
  private chatSessionId?: string;
  private personaId?: number;

  // For playback
  private playQueue: ArrayBuffer[] = [];
  private isPlaying = false;
  private playbackContext: AudioContext | null = null;
  private currentSource: AudioBufferSourceNode | null = null;

  constructor(
    onStateChange: StateCallback,
    onTranscript: TranscriptCallback,
    onAmplitude: AmplitudeCallback,
    onChatSessionId: (id: string) => void,
    chatSessionId?: string,
    personaId?: number
  ) {
    this.onStateChange = onStateChange;
    this.onTranscript = onTranscript;
    this.onAmplitude = onAmplitude;
    this.onChatSessionId = onChatSessionId;
    this.chatSessionId = chatSessionId;
    this.personaId = personaId;
  }

  async connect() {
    try {
      // 1. Fetch WebSocket auth token
      const tokenRes = await fetch("/api/voice/ws-token", {
        method: "POST",
      });
      if (!tokenRes.ok) {
        throw new Error("Failed to fetch WebSocket auth token");
      }
      const tokenData = await tokenRes.json();
      const token = tokenData.token;

      // 2. Determine WS URL
      const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
      const host = window.location.host;
      let wsUrl = `${protocol}//${host}/api/voice/live-session?token=${token}`;
      if (this.chatSessionId) {
        wsUrl += `&chat_session_id=${this.chatSessionId}`;
      }
      if (this.personaId) {
        wsUrl += `&persona_id=${this.personaId}`;
      }
      
      this.ws = new WebSocket(wsUrl);
      this.ws.binaryType = "arraybuffer";

    this.ws.onopen = async () => {
      this.setState("listening");
      await this.startRecording();
    };

    this.ws.onmessage = async (event) => {
      if (typeof event.data === "string") {
        const msg = JSON.parse(event.data);
        if (msg.type === "state") {
          this.setBackendState(msg.state);
        } else if (msg.type === "transcript_partial") {
          if (this.onTranscript) this.onTranscript(msg.text, false);
        } else if (msg.type === "transcript_final") {
          if (this.onTranscript) this.onTranscript(msg.text, true);
        } else if (msg.type === "interrupt") {
          this.stopPlayback();
        } else if (msg.type === "chat_session_id") {
          if (this.onChatSessionId) this.onChatSessionId(msg.chat_session_id);
        }
      } else {
        // Binary audio chunk (synthesized speech)
        // If we've interrupted locally, backendState will be "listening".
        // Drop any inflight trailing audio chunks to prevent ghost playback!
        if (this.backendState !== "speaking") {
          return;
        }
        
        this.playQueue.push(event.data);
        this.updateDerivedState();
        this.processPlayQueue();
      }
    };

    this.ws.onclose = () => {
      this.disconnect();
    };
    } catch (e) {
      console.error("LiveSessionClient connect error:", e);
      this.setBackendState("disconnected");
    }
  }

  private async startRecording() {
    this.mediaStream = await navigator.mediaDevices.getUserMedia({
      audio: {
        channelCount: 1,
        sampleRate: 24000,
        echoCancellation: true,
        noiseSuppression: true,
      },
    });

    this.audioContext = new (window.AudioContext || (window as any).webkitAudioContext)({
      sampleRate: 24000,
    });

    this.source = this.audioContext.createMediaStreamSource(this.mediaStream);
    
    try {
      await this.audioContext.audioWorklet.addModule('/pcm-worklet-processor.js');
      this.workletNode = new AudioWorkletNode(this.audioContext, 'pcm-worklet-processor');

      this.workletNode.port.onmessage = (e) => {
        const { buffer, rms } = e.data;
        if (this.onAmplitude) this.onAmplitude(rms);
        
        // Instant client-side interrupt if user speaks loudly while assistant is speaking
        if (this.currentState === "speaking" && rms > 1500) {
          this.stopPlayback();
          this.setState("listening");
          if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            this.ws.send(JSON.stringify({ action: "stop" }));
          }
        }

        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
          this.ws.send(buffer);
        }
      };

      this.source.connect(this.workletNode);
    } catch (error) {
      console.error("Error setting up AudioWorklet:", error);
    }
  }

  private async processPlayQueue() {
    if (this.isPlaying || this.playQueue.length === 0) {
      this.updateDerivedState();
      return;
    }
    this.isPlaying = true;
    this.updateDerivedState();

    if (!this.playbackContext) {
      this.playbackContext = new (window.AudioContext || (window as any).webkitAudioContext)();
    }

    const chunk = this.playQueue.shift();
    if (chunk) {
      try {
        const audioBuffer = await this.playbackContext.decodeAudioData(chunk);
        this.currentSource = this.playbackContext.createBufferSource();
        this.currentSource.buffer = audioBuffer;
        this.currentSource.connect(this.playbackContext.destination);
        
        this.currentSource.onended = () => {
          this.isPlaying = false;
          this.updateDerivedState();
          this.processPlayQueue();
        };
        
        this.currentSource.start();
      } catch (e) {
        console.error("Error decoding audio chunk", e);
        this.isPlaying = false;
        this.updateDerivedState();
        this.processPlayQueue();
      }
    }
  }

  private stopPlayback() {
    this.playQueue = [];
    if (this.currentSource) {
      try {
        this.currentSource.stop();
      } catch (e) {}
      this.currentSource = null;
    }
    this.isPlaying = false;
    this.updateDerivedState();
  }

  private updateDerivedState() {
    let derivedState = this.backendState;
    
    // If backend thinks we are idle, but we have audio queued or playing, we are still speaking!
    if (this.backendState === "idle" && (this.isPlaying || this.playQueue.length > 0)) {
      derivedState = "speaking";
    }
    
    // If backend thinks we are speaking, but we are not playing anything yet, we are thinking!
    if (this.backendState === "speaking" && !this.isPlaying && this.playQueue.length === 0) {
      derivedState = "thinking";
    }

    if (this.currentState !== derivedState) {
      this.currentState = derivedState;
      if (this.onStateChange) this.onStateChange(derivedState);
    }
  }

  private setBackendState(state: LiveSessionState) {
    this.backendState = state;
    this.updateDerivedState();
  }

  private setState(state: LiveSessionState) {
    this.backendState = state;
    this.updateDerivedState();
  }

  setMicMuted(muted: boolean) {
    if (this.mediaStream) {
      this.mediaStream.getAudioTracks().forEach(track => {
        track.enabled = !muted;
      });
    }
  }

  setSpeakerMuted(muted: boolean) {
    // A simple way to mute the speaker is to suspend the playback context.
    // However, suspending means audio won't drain from the queue properly if it's already decoded.
    // Given the constraints, we will just rely on the UI state for now, 
    // or add a GainNode later. For now, suspending is ok for a hard mute.
    if (this.playbackContext) {
      if (muted) {
        this.playbackContext.suspend();
      } else {
        this.playbackContext.resume();
      }
    }
  }

  sendSettings(settings: { disableThinking?: boolean }) {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({
        type: "settings",
        action: "settings",
        disable_thinking: settings.disableThinking
      }));
    }
  }

  disconnect() {
    this.setBackendState("disconnected");
    this.stopPlayback();
    
    if (this.workletNode) {
      this.workletNode.disconnect();
      this.workletNode = null;
    }
    if (this.source) {
      this.source.disconnect();
      this.source = null;
    }
    if (this.audioContext) {
      this.audioContext.close();
      this.audioContext = null;
    }
    if (this.mediaStream) {
      this.mediaStream.getTracks().forEach((track) => track.stop());
      this.mediaStream = null;
    }
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
  }
}
