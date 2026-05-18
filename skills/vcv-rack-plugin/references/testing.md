# Testing VCV Rack Plugins

Testing Rack plugins requires isolating DSP code from the Rack SDK runtime. The standard approach is to compile DSP classes as standalone binaries with minimal stubs for Rack APIs.

## Test Architecture

Separate your DSP code from Rack glue so it can be tested without loading the Rack SDK:

```
src/
  dsp/                  # Pure DSP classes — no Rack includes
    filter.h
    oscillator.h
    limiter.h
  module.cpp            # Rack Module/ModuleWidget — hard to unit test
  plugin.cpp
tests/
  filter_test.cpp       # Tests dsp/ code in isolation
  oscillator_test.cpp
run_tests.sh            # Compile + run all tests
```

The key insight: your `dsp/` directory should have zero Rack SDK dependencies. If a DSP class needs `rack::math::clamp()`, either inline your own version or extract the Rack dependency behind an interface.

## Test Framework

Most Rack plugins use a lightweight custom framework rather than pulling in Catch2 or Google Test. The minimal pattern:

```cpp
// In test file or shared test header
namespace Test {

struct Context {
    int passed = 0;
    int failed = 0;

    void assertTrue (bool cond, const char* expr, const char* file, int line)
    {
        if (cond) { passed++; }
        else { fprintf (stderr, "FAIL %s:%d: %s\n", file, line, expr); failed++; }
    }

    void assertNear (float actual, float expected, float tol,
                     const char* expr, const char* file, int line)
    {
        bool ok = std::fabs (actual - expected) <= tol;
        if (ok) { passed++; }
        else {
            fprintf (stderr, "FAIL %s:%d: %s (got %f, expected %f +/- %f)\n",
                     file, line, expr, actual, expected, tol);
            failed++;
        }
    }

    void summary() const
    {
        printf ("\n%d passed, %d failed\n", passed, failed);
    }
};

}

#define T_ASSERT(ctx, cond) \
    (ctx).assertTrue ((cond), #cond, __FILE__, __LINE__)

#define T_ASSERT_NEAR(ctx, actual, expected, tol) \
    (ctx).assertNear ((actual), (expected), (tol), #actual " ~= " #expected, __FILE__, __LINE__)
```

Usage:

```cpp
int main()
{
    Test::Context ctx;

    // Run test functions
    test_filter_passthrough (ctx);
    test_filter_cutoff (ctx);
    test_filter_reset (ctx);

    ctx.summary();
    return ctx.failed > 0 ? 1 : 0;
}
```

## DSP Test Patterns

### Passthrough (Identity) Test

Verify that default/bypass settings produce unchanged output:

```cpp
void test_filter_passthrough (Test::Context& ctx)
{
    MyFilter filter;
    filter.reset();

    for (int i = 0; i < 256; ++i)
    {
        float input = 0.5f * sinf (i * 0.1f);
        float output = filter.processSample (input);
        T_ASSERT_NEAR (ctx, output, input, 1e-6f);
    }
}
```

### Extreme Values / Robustness

Feed NaN, inf, very large, very small, and DC values. Verify no crash, no NaN propagation:

```cpp
void test_stability (Test::Context& ctx)
{
    MyFilter filter;
    filter.reset();

    float inputs[] = { 0.0f, 1.0f, -1.0f, 10.0f, -10.0f, 1e6f, -1e6f };

    for (auto input : inputs)
    {
        for (int i = 0; i < 1000; ++i)
        {
            float output = filter.processSample (input);
            T_ASSERT (ctx, std::isfinite (output));
            T_ASSERT (ctx, std::fabs (output) < 100.0f);
        }
    }
}
```

### Parameter Sweep

Test across a range of parameter values:

```cpp
void test_cutoff_sweep (Test::Context& ctx)
{
    MyFilter filter;
    filter.reset();

    for (float cutoff = 0.0f; cutoff <= 1.0f; cutoff += 0.1f)
    {
        filter.setCutoff (cutoff);
        for (int i = 0; i < 100; ++i)
        {
            float out = filter.processSample (0.5f);
            T_ASSERT (ctx, std::isfinite (out));
        }
    }
}
```

### State Reset

Verify that `reset()` clears all internal state:

```cpp
void test_filter_reset (Test::Context& ctx)
{
    MyFilter filter;

    // Process some signal
    for (int i = 0; i < 1000; ++i)
        filter.processSample (1.0f);

    filter.reset();

    // After reset, feeding silence should produce silence
    for (int i = 0; i < 100; ++i)
    {
        float out = filter.processSample (0.0f);
        T_ASSERT_NEAR (ctx, out, 0.0f, 1e-6f);
    }
}
```

### Long-Running Stability

Process thousands of samples to catch accumulated drift or denormal issues:

```cpp
void test_long_run (Test::Context& ctx)
{
    MyFilter filter;
    filter.reset();

    for (int i = 0; i < 50000; ++i)
    {
        float input = 0.3f * sinf (i * 0.01f);
        float output = filter.processSample (input);
        T_ASSERT (ctx, std::isfinite (output));
        T_ASSERT (ctx, std::fabs (output) < 5.0f);
    }
}
```

### Multiple Sample Rates

```cpp
void test_sample_rates (Test::Context& ctx)
{
    int rates[] = { 44100, 48000, 96000 };

    for (auto sr : rates)
    {
        MyFilter filter;
        filter.setSampleRate (sr);
        filter.reset();

        for (int i = 0; i < 256; ++i)
        {
            float out = filter.processSample (0.5f);
            T_ASSERT (ctx, std::isfinite (out));
        }
    }
}
```

### Bit-Crusher / Quantizer Testing

Test specific bit depths:

```cpp
void test_bit_depth (Test::Context& ctx)
{
    BitCrusher crusher;

    // 16-bit should be near-transparent
    crusher.setBits (16);
    float out = crusher.process (0.123456f);
    T_ASSERT_NEAR (ctx, out, 0.123456f, 1e-3f);

    // 1-bit should be extreme
    crusher.setBits (1);
    out = crusher.process (0.5f);
    T_ASSERT (ctx, out == 1.0f || out == -1.0f || out == 0.0f);
}
```

### Filter Response Verification

Low cutoff should attenuate more than high cutoff:

```cpp
void test_lowpass_response (Test::Context& ctx)
{
    MyFilter filter;

    // High cutoff — signal passes
    filter.setCutoff (0.9f);
    float highOut = 0.0f;
    for (int i = 0; i < 1000; ++i)
        highOut += std::fabs (filter.processSample (0.5f * sinf (i * 0.1f)));
    filter.reset();

    // Low cutoff — signal attenuated
    filter.setCutoff (0.1f);
    float lowOut = 0.0f;
    for (int i = 0; i < 1000; ++i)
        lowOut += std::fabs (filter.processSample (0.5f * sinf (i * 0.1f)));

    T_ASSERT (ctx, lowOut < highOut);  // low cutoff = less energy
}
```

## Mocking Rack APIs

Three strategies, from simplest to most isolated:

### Strategy 1: No Rack Dependency (Preferred)

Design DSP code with zero Rack includes. The DSP headers only use standard C++ math and types. This is the cleanest approach — no mocking needed.

```cpp
// dsp/filter.h — no Rack includes
#pragma once
#include <cmath>
#include <cstdint>

namespace MyPlugin {
class Filter {
public:
    void setSampleRate (float sr) { sampleRate = sr; }
    float processSample (float input);
    void reset();
private:
    float sampleRate = 44100.0f;
    // ...
};
}
```

### Strategy 2: Preprocessor Guard

In production code, conditionally exclude Rack-dependent paths:

```cpp
// In dsp module header:
#ifndef MY_PLUGIN_RUN_TESTS
    #include <rack.hpp>
#else
    // Minimal stubs
    namespace rack {
        namespace math {
            inline float clamp (float x, float lo, float hi) {
                return std::max (lo, std::min (hi, x));
            }
            inline float rescale (float x, float x0, float x1, float y0, float y1) {
                return y0 + (x - x0) / (x1 - x0) * (y1 - y0);
            }
        }
    }
#endif
```

Compile tests with `-DMY_PLUGIN_RUN_TESTS`.

### Strategy 3: Inline Mock in Test File

For code that must include Rack types, mock the entire namespace:

```cpp
// At the top of the test file:
#define RACK_HPP_INCLUDED  // Prevent rack.hpp from being included

namespace rack {
    namespace random {
        inline float uniform() { return (float) rand() / RAND_MAX; }
        inline float normal() { return uniform() * 2.0f - 1.0f; }
    }
    namespace logger {
        enum Level { DEBUG_LEVEL, INFO_LEVEL, WARN_LEVEL, FATAL_LEVEL };
        inline void log (...) {}
    }
    namespace math {
        inline float clamp (float x, float lo, float hi) {
            return std::max (lo, std::min (hi, x));
        }
    }
}
#define DEBUG(format, ...) do {} while (0)
```

Then include your production headers — they'll see the mock namespace instead of the real Rack SDK.

## Test Runner Script

A robust test runner with auto-discovery, colored output, and exit codes:

```bash
#!/bin/bash
set -euo pipefail

# Configuration
RACK_SDK="${RACK_DIR:-dep/Rack-SDK}"
TEST_DIR="src/tests"
BUILD_DIR="build/tests"
CXX="${CXX:-g++}"

# Colors
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'

mkdir -p "$BUILD_DIR"

# Find all test files
TEST_FILES=$(find "$TEST_DIR" -name "*_test.cpp" -o -name "test_*.cpp")

if [ -z "$TEST_FILES" ]; then
    echo -e "${RED}No test files found in ${TEST_DIR}${NC}"
    exit 3
fi

TOTAL_PASSED=0
TOTAL_FAILED=0
FAILED_TESTS=""

for test_file in $TEST_FILES; do
    test_name=$(basename "$test_file" .cpp)
    test_bin="${BUILD_DIR}/${test_name}"

    echo -e "${YELLOW}Compiling ${test_name}...${NC}"

    if $CXX -std=c++17 -O2 -Wall \
        -I./src -I"${RACK_SDK}/include" \
        -DMY_PLUGIN_RUN_TESTS \
        -o "$test_bin" "$test_file" -lm; then

        echo -e "${YELLOW}Running ${test_name}...${NC}"
        if "$test_bin"; then
            echo -e "${GREEN}  PASSED${NC}"
            TOTAL_PASSED=$((TOTAL_PASSED + 1))
        else
            echo -e "${RED}  FAILED${NC}"
            TOTAL_FAILED=$((TOTAL_FAILED + 1))
            FAILED_TESTS="${FAILED_TESTS}  - ${test_name}\n"
        fi
    else
        echo -e "${RED}  COMPILE FAILED${NC}"
        TOTAL_FAILED=$((TOTAL_FAILED + 1))
        FAILED_TESTS="${FAILED_TESTS}  - ${test_name} (compile)\n"
    fi
done

echo ""
echo -e "Results: ${GREEN}${TOTAL_PASSED} passed${NC}, ${RED}${TOTAL_FAILED} failed${NC}"

if [ -n "$FAILED_TESTS" ]; then
    echo -e "${RED}Failed tests:\n${FAILED_TESTS}${NC}"
    exit 1
fi
exit 0
```

## Coverage

Using gcov with GCC or llvm-cov with Clang:

```bash
#!/bin/bash
CXX="${CXX:-g++}"
COV_FLAGS="--coverage -fprofile-arcs -ftest-coverage -O0 -g"

$CXX $COV_FLAGS -std=c++17 -I./src -DMY_PLUGIN_RUN_TESTS \
    -o build/test_myplugin src/tests/test_myplugin.cpp -lm

./build/test_myplugin

# Generate coverage reports
if command -v llvm-cov &>/dev/null; then
    llvm-cov gcov build/*.gcno
else
    gcov build/*.gcno
fi

# Parse and summarize per-file coverage
mkdir -p coverage
mv *.gcov coverage/
echo "Coverage reports in coverage/"
```

## Performance Benchmarking

Measure per-block processing time and compare against the real-time budget:

```cpp
#include <chrono>

void benchmark_processing (Test::Context& ctx)
{
    MyModule module;
    const int block_size = 128;
    const int sample_rate = 44100;
    const float real_time_budget_us = (float) block_size / sample_rate * 1e6;

    module.setSampleRate (sample_rate);

    // Warmup
    for (int i = 0; i < 250; ++i)
    {
        float in[block_size] = {0.5f};
        module.process (in, block_size);
    }

    // Measure
    auto start = std::chrono::high_resolution_clock::now();
    for (int i = 0; i < 1200; ++i)
    {
        float in[block_size] = {0.5f};
        module.process (in, block_size);
    }
    auto end = std::chrono::high_resolution_clock::now();

    float total_us = std::chrono::duration<float, std::micro> (end - start).count();
    float mean_us = total_us / 1200.0f;
    float usage_pct = (mean_us / real_time_budget_us) * 100.0f;

    printf ("Mean: %.1f us/block (%.1f%% of real-time budget)\n", mean_us, usage_pct);

    T_ASSERT (ctx, usage_pct < 50.0f);  // Must be well under real-time budget
}
```

## What to Test

| Category | What to Verify |
|----------|---------------|
| **Passthrough** | Default settings produce unchanged output |
| **Reset** | After reset, silence in = silence out |
| **Stability** | NaN/inf never appear, even with extreme inputs |
| **Parameter bounds** | All parameter values [0, 1] produce finite output |
| **Sample rates** | 44100, 48000, 96000 all work |
| **Block sizes** | 1, 32, 128, 256, 1024 all work |
| **Edge cases** | Zero input, DC input, full-scale input, rapid parameter changes |
| **Long runs** | 10,000+ samples stay stable (catches accumulator drift, denormals) |
| **State** | Reset clears state, multiple resets are safe |
| **Stereo** | Left/right channels processed independently |
| **Frequency response** | Lowpass attenuates highs, highpass attenuates lows |

## Running Tests in CI

```yaml
# In .github/workflows/build.yml
- name: Run tests
  run: |
    chmod +x run_tests.sh
    ./run_tests.sh
```

The test script should exit 0 on success, non-zero on failure. CI will pick up the exit code automatically.
