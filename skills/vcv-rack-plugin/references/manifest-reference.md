# plugin.json Manifest Reference

## Top-Level Fields

### Required
| Field | Type | Description |
|-------|------|-------------|
| `slug` | string | Unique identifier. Letters, numbers, `-`, `_`. Case-sensitive. **Must NEVER change after release.** |
| `name` | string | Human-readable name. Can change freely. |
| `version` | string | `MAJOR.MINOR.REVISION` (e.g., `"2.0.0"`). Major must match Rack major version. No "v" prefix. |
| `license` | string | SPDX identifier (`"GPL-3.0-or-later"`, `"MIT"`, `"CC0-1.0"`), `"proprietary"` for freeware, or commercial license URL. |
| `author` | string | Your name, company, or alias. |

### Optional
| Field | Type | Description |
|-------|------|-------------|
| `brand` | string | Prefix for all module names in browser (e.g., "VCV" → "VCV VCO"). Defaults to plugin name. |
| `description` | string | One-line plugin summary. |
| `authorEmail` | string | Support email. |
| `authorUrl` | string | Author homepage. |
| `pluginUrl` | string | Plugin homepage. |
| `manualUrl` | string | Manual URL (HTML, PDF, GitHub readme/wiki). |
| `sourceUrl` | string | Source code homepage (main page, not .git URL). |
| `donateUrl` | string | Donation link (PayPal, Cash App, Ko-fi, etc.). |
| `changelogUrl` | string | Changelog URL. |
| `minRackVersion` | string | Minimum Rack version for Library download (requires Rack 2.4.0+). |

## Module Entries (`modules[]` array)

### Required
| Field | Type | Description |
|-------|------|-------------|
| `slug` | string | Unique module ID. Same naming rules as plugin slug. Must not change after release. |
| `name` | string | Human-readable module name. |

### Optional
| Field | Type | Description |
|-------|------|-------------|
| `description` | string | One-line summary. Shown in Module Browser tooltip. |
| `tags` | string[] | Tags from approved list (case-insensitive). See below. |
| `keywords` | string | Search aliases/abbreviations. Not displayed to user. |
| `manualUrl` | string | Module-specific manual URL. Falls back to plugin manual. |
| `modularGridUrl` | string | ModularGrid URL for Hardware clone modules. |
| `hidden` | bool | Hide from browser/Library. Use for deprecated modules. |

## Approved Module Tags

Use these exact strings (case-insensitive):

**Sound Sources:**
- `Oscillator` (not "VCO")
- `Low-frequency oscillator` (not "LFO")
- `Noise`
- `Drum`
- `Sampler`
- `Physical modeling`
- `Speech`
- `Synth voice`

**Sound Processing:**
- `Filter`
- `Voltage-controlled amplifier` (not "VCA")
- `Waveshaper`
- `Distortion`
- `Ring modulator`
- `Delay`
- `Reverb`
- `Chorus`
- `Flanger`
- `Phaser`
- `Compressor`
- `Limiter`
- `Dynamics`
- `Equalizer`
- `Panning`

**Modulation:**
- `Envelope generator`
- `Function generator`
- `Low-pass gate`
- `Slew limiter`
- `Sample and hold`
- `Sequencer`
- `Arpeggiator`
- `Clock generator`
- `Clock modulator`
- `Random`
- `Quantizer`
- `Logic`

**Utility:**
- `Mixer`
- `Multiple`
- `Attenuator`
- `Switch`
- `Controller`
- `Utility`
- `Dual`
- `Quad`
- `Polyphonic`
- `MIDI`
- `Tuner`
- `Recording`

**Other:**
- `Effect`
- `Granular`
- `Envelope follower`
- `Vocoder`
- `Expander`
- `External`
- `Hardware clone`
- `Blank`
- `Visual`
- `Digital`

## Example

```json
{
  "slug": "swv-guitar-tools",
  "name": "SWV Guitar Tools",
  "version": "2.0.0",
  "license": "GPL-3.0-or-later",
  "brand": "Shortwav Labs",
  "author": "Shortwav Labs",
  "authorEmail": "contact@shortwavlabs.com",
  "donateUrl": "https://ko-fi.com/shortwavlabs",
  "minRackVersion": "2.6.0",
  "modules": [
    {
      "slug": "NAM",
      "name": "NAM Player",
      "description": "Neural Amp Modeler player for guitar signals",
      "tags": ["Distortion", "Effect", "Hardware clone"]
    },
    {
      "slug": "CabSim",
      "name": "Cab Sim",
      "description": "Cabinet simulator with impulse response loading",
      "tags": ["Effect", "Filter"]
    }
  ]
}
```

## Version Numbering

- Format: `MAJOR.MINOR.REVISION` (e.g., `2.3.1`)
- Major version must match Rack major (currently `2`)
- Git tag format: `v2.3.1` (with "v" prefix for tags only, not in plugin.json)
- Tag must exactly match plugin.json version for automated releases
