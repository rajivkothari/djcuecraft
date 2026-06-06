/* Frequency band analysis worker.
 * Input message: { samples: Float32Array, sampleRate: number }
 * Output message: { low: Float32Array, mid: Float32Array, high: Float32Array, numWindows: number }
 *
 * Uses simple single-pole IIR filters to separate three bands, then computes
 * RMS energy per hop window. Frequency separation is approximate but visually
 * effective for waveform display.
 */
self.onmessage = function (e) {
  const { samples, sampleRate } = e.data;
  const length = samples.length;
  const hopSize = 1024;
  const numWindows = Math.ceil(length / hopSize);

  // Single-pole IIR filter coefficients
  // Lowpass: y[n] = alpha*x[n] + (1-alpha)*y[n-1]
  const lpAlpha = (2 * Math.PI * 250) / sampleRate;
  // Highpass: y[n] = (1-alpha)*(y[n-1] + x[n] - x[n-1])
  const hpAlpha = (2 * Math.PI * 4000) / sampleRate;

  const low = new Float32Array(numWindows);
  const mid = new Float32Array(numWindows);
  const high = new Float32Array(numWindows);

  let lpPrev = 0;
  let hpPrev = 0;
  let hpPrevX = 0;

  let globalMax = 0;

  for (let w = 0; w < numWindows; w++) {
    const start = w * hopSize;
    const end = Math.min(start + hopSize, length);
    let sumL = 0, sumM = 0, sumH = 0;

    for (let i = start; i < end; i++) {
      const x = samples[i];

      // Lowpass
      const lp = lpAlpha * x + (1 - lpAlpha) * lpPrev;
      lpPrev = lp;

      // Highpass
      const hp = (1 - hpAlpha) * (hpPrev + x - hpPrevX);
      hpPrev = hp;
      hpPrevX = x;

      // Mid = original - low - high
      const mp = x - lp - hp;

      sumL += lp * lp;
      sumM += mp * mp;
      sumH += hp * hp;
    }

    const n = end - start;
    low[w] = Math.sqrt(sumL / n);
    mid[w] = Math.sqrt(sumM / n);
    high[w] = Math.sqrt(sumH / n);

    const total = low[w] + mid[w] + high[w];
    if (total > globalMax) globalMax = total;
  }

  // Normalize relative to global max
  if (globalMax > 0) {
    for (let w = 0; w < numWindows; w++) {
      low[w] /= globalMax;
      mid[w] /= globalMax;
      high[w] /= globalMax;
    }
  }

  self.postMessage(
    { low, mid, high, numWindows, hopSize, sampleRate },
    [low.buffer, mid.buffer, high.buffer],
  );
};
