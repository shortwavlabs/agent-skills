# CI/CD: GitHub Actions for VCV Rack Plugins

## Complete Workflow

Save as `.github/workflows/build.yml`:

```yaml
name: Build VCV Rack Plugin
on: [push, pull_request]

env:
  rack-sdk-version: latest
  rack-plugin-toolchain-dir: /home/build/rack-plugin-toolchain

defaults:
  run:
    shell: bash

jobs:
  modify-plugin-version:
    name: Modify plugin version
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/cache@v4
        id: plugin-version-cache
        with:
          path: plugin.json
          key: ${{ github.sha }}-${{ github.run_id }}
      - run: |
          gitrev=`git rev-parse --short HEAD`
          pluginversion=`jq -r '.version' plugin.json`
          echo "Set plugin version from $pluginversion to $pluginversion-$gitrev"
          cat <<< `jq --arg VERSION "$pluginversion-$gitrev" '.version=$VERSION' plugin.json` > plugin.json
        if: "! startsWith(github.ref, 'refs/tags/v')"

  build:
    name: ${{ matrix.platform }}
    needs: modify-plugin-version
    runs-on: ubuntu-latest
    container:
      image: ghcr.io/qno/rack-plugin-toolchain-win-linux
      options: --user root
    strategy:
      matrix:
        platform: [win-x64, lin-x64]
    steps:
      - uses: actions/checkout@v4
        with:
          submodules: recursive
      - uses: actions/cache@v4
        id: plugin-version-cache
        with:
          path: plugin.json
          key: ${{ github.sha }}-${{ github.run_id }}
      - name: Build plugin
        run: |
          export PLUGIN_DIR=$GITHUB_WORKSPACE
          pushd ${{ env.rack-plugin-toolchain-dir }}
          make plugin-build-${{ matrix.platform }}
      - name: Upload artifact
        uses: actions/upload-artifact@v4
        with:
          path: ${{ env.rack-plugin-toolchain-dir }}/plugin-build
          name: ${{ matrix.platform }}

  build-mac:
    name: mac
    needs: modify-plugin-version
    runs-on: macos-latest
    strategy:
      fail-fast: false
      matrix:
        platform: [x64, arm64]
    steps:
      - uses: actions/checkout@v4
        with:
          submodules: recursive
      - uses: actions/cache@v4
        id: plugin-version-cache
        with:
          path: plugin.json
          key: ${{ github.sha }}-${{ github.run_id }}
      - name: Get Rack-SDK
        run: |
          pushd $HOME
          wget -O Rack-SDK.zip https://vcvrack.com/downloads/Rack-SDK-${{ env.rack-sdk-version }}-mac-x64+arm64.zip
          unzip Rack-SDK.zip
      - name: Build plugin
        run: |
          CROSS_COMPILE_TARGET_x64=x86_64-apple-darwin
          CROSS_COMPILE_TARGET_arm64=arm64-apple-darwin
          export RACK_DIR=$HOME/Rack-SDK
          export CROSS_COMPILE=$CROSS_COMPILE_TARGET_${{ matrix.platform }}
          make dep
          make dist
      - name: Upload artifact
        uses: actions/upload-artifact@v4
        with:
          path: dist/*.vcvplugin
          name: mac-${{ matrix.platform }}

  publish:
    name: Publish plugin
    if: startsWith(github.ref, 'refs/tags/v')
    runs-on: ubuntu-latest
    needs: [build, build-mac]
    steps:
      - uses: actions/checkout@v4
      - uses: FranzDiebold/github-env-vars-action@v2
      - name: Check version match
        run: |
          pluginversion=`jq -r '.version' plugin.json`
          if [ "v$pluginversion" != "${{ env.CI_REF_NAME }}" ]; then
            echo "Version mismatch: v$pluginversion vs ${{ env.CI_REF_NAME }}"
            exit 1
          fi
      - name: Create Release
        uses: softprops/action-gh-release@v2
        with:
          tag_name: ${{ github.ref }}
          name: Release ${{ env.CI_REF_NAME }}
          body: |
            ${{ env.CI_REPOSITORY_NAME }} VCV Rack Plugin ${{ env.CI_REF_NAME }}
          draft: false
          prerelease: false
      - uses: actions/download-artifact@v4
        with:
          path: _artifacts
      - name: Upload release assets
        uses: svenstaro/upload-release-action@v2
        with:
          repo_token: ${{ secrets.GITHUB_TOKEN }}
          file: _artifacts/**/*.vcvplugin
          tag: ${{ github.ref }}
          file_glob: true
```

## Release Workflow

1. Update `version` in `plugin.json`
2. Commit all changes
3. Tag: `git tag v2.0.0`
4. Push: `git push && git push --tags`
5. CI builds all 4 platforms and creates a GitHub Release

## Using rack-plugin-toolchain Locally

### Docker (recommended)
```bash
# Build the Docker image (one-time, ~30 min)
cd rack-plugin-toolchain
make docker-build

# Build your plugin for all platforms
docker run --rm \
  -v /path/to/your-plugin:/plugin \
  rack-plugin-toolchain:19 \
  make plugin-build PLUGIN_DIR=/plugin

# Build for specific platform
docker run --rm \
  -v /path/to/your-plugin:/plugin \
  rack-plugin-toolchain:19 \
  make plugin-build-mac-arm64 PLUGIN_DIR=/plugin
```

### Native Linux
```bash
cd rack-plugin-toolchain
make toolchain-all    # Build all cross-compilers (~4 hours)
make rack-sdk-all     # Download all SDKs
make plugin-build PLUGIN_DIR=/path/to/your-plugin
```

## Make Targets Reference

| Target | Description |
|--------|-------------|
| `make` | Build plugin for current platform |
| `make dep` | Build third-party dependencies |
| `make dist` | Create .vcvplugin distributable |
| `make install` | Install to Rack user folder |
| `make clean` | Clean build artifacts |
| `make cleandep` | Clean dependency builds |

## Platform-Specific Output

| Platform | Output | Location |
|----------|--------|----------|
| macOS | `plugin.dylib` → `.vcvplugin` | `dist/` |
| Linux | `plugin.so` → `.vcvplugin` | `dist/` |
| Windows | `plugin.dll` → `.vcvplugin` | `dist/` |

## Rack User Plugin Directories

For `make install`:

| Platform | Path |
|----------|------|
| macOS | `~/Library/Application Support/Rack2/plugins-v2/` |
| Linux | `~/.local/share/Rack2/plugins-v2/` |
| Windows | `%LOCALAPPDATA%/Rack2/plugins-v2/` |
