class PCMWorkletProcessor extends AudioWorkletProcessor {
  process(inputs) {
    const in32 = inputs[0][0];
    if (in32) {
      // convert Float32 -> Int16 in the worklet
      const int16 = new Int16Array(in32.length);
      let sumSquares = 0;
      for (let i = 0; i < in32.length; i++) {
        let s = in32[i];
        sumSquares += s * s;
        s = s < -1 ? -1 : s > 1 ? 1 : s;
        int16[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
      }
      
      const rms = Math.sqrt(sumSquares / in32.length);
      
      // Send raw ArrayBuffer and RMS value
      this.port.postMessage({ buffer: int16.buffer, rms }, [int16.buffer]);
    }
    return true;
  }
}

registerProcessor('pcm-worklet-processor', PCMWorkletProcessor);
