# Guitar DSP Example Prompts

## Contents

- Implementation prompts
- Neural modeling prompts
- Debugging prompts
- Validation prompts
- Review prompts

## Implementation Prompts

- "Use $guitar-dsp to add a realtime-safe RTNeural model loader to this JUCE amp plugin."
- "Use $guitar-dsp to design a C++ DSP block for a four-knob overdrive with bypass, smoothing, and tests."
- "Use $guitar-dsp to design a passive tone stack model with insertion loss, smoothing, and response tests."
- "Use $guitar-dsp to approximate a tube preamp stage with triode-like saturation and coupling-cap recovery."
- "Use $guitar-dsp to add speaker cabinet dynamics on top of an existing IR loader."
- "Use $guitar-dsp to add cabinet IR loading with safe swaps, sample-rate conversion, blend endpoints, and latency reporting."
- "Use $guitar-dsp to refactor this pedal DSP so APVTS access stays outside the audio block."
- "Use $guitar-dsp to design a measurement harness for drive transfer curves, alias spectra, and level compensation."

## Neural Modeling Prompts

- "Use $guitar-dsp to review this neural amp training run and tell me whether it is ready to export."
- "Use $guitar-dsp to compare these RTNeural package metrics: ESR, RMSE, correlation, ASR, RTF, latency, and receptive field."
- "Use $guitar-dsp to explain why this model has good validation loss but sounds wrong on palm mutes."
- "Use $guitar-dsp to create an export package contract for user-loadable neural amp models."

## Debugging Prompts

- "Use $guitar-dsp to diagnose why this guitar plugin clicks when I automate the tone controls."
- "Use $guitar-dsp to find the likely source of aliasing in this high-gain pedal chain."
- "Use $guitar-dsp to debug why my dry/wet compressor blend sounds hollow."
- "Use $guitar-dsp to explain why this plugin reports latency even though the RTNeural model is causal."
- "Use $guitar-dsp to inspect this preset reload bug where the cabinet IR path disappears after reopening the DAW."

## Validation Prompts

- "Use $guitar-dsp to write a release validation checklist for a JUCE guitar amp modeler."
- "Use $guitar-dsp to design unit tests for bypass identity, reset determinism, automation safety, stereo routing, and finite output."
- "Use $guitar-dsp to define an offline render matrix for gate, compressor, drive, cabinet, delay, and reverb behavior."
- "Use $guitar-dsp to decide which pluginval, auval, DAW smoke, and benchmark gates should block release."

## Review Prompts

- "Use $guitar-dsp to review this C++ DSP block for realtime safety and guitar-tone regressions."
- "Use $guitar-dsp to review this RTNeural runtime integration for sample-rate, metadata, state, and latency bugs."
- "Use $guitar-dsp to review these effect blocks and suggest measurement fixtures before we tune by ear."
- "Use $guitar-dsp to audit this plugin's audio callback for allocation, locks, logging, file I/O, and heavy object destruction."
