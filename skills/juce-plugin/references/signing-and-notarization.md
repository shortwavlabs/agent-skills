# Signing And Notarization (macOS, Windows)

Signed, distributable plugin builds produced in GitHub Actions: macOS Developer ID signing, a notarized
`.pkg` installer, and Windows Authenticode signing with Microsoft Artifact Signing. Linux has no customary
signing. Building each platform is in [platform-builds.md](platform-builds.md); this file starts from built
Release bundles.

## Contents

- [Quick Reference](#quick-reference)
- [macOS: Credentials](#macos-credentials)
- [macOS: Release Workflow](#macos-release-workflow)
- [macOS: Installer Package](#macos-installer-package)
- [Windows: What To Sign And With What](#windows-what-to-sign-and-with-what)
- [Windows: Artifact Signing Set-Up](#windows-artifact-signing-set-up)
- [Windows: GitHub Access Without A Password](#windows-github-access-without-a-password)
- [Windows: Release Workflow](#windows-release-workflow)
- [GitHub Secrets On A Free Plan](#github-secrets-on-a-free-plan)
- [Linux](#linux)
- [Common Mistakes](#common-mistakes)
- [Sources](#sources)

## Quick Reference

| | macOS | Windows |
| --- | --- | --- |
| Identity | Apple Developer ID Application (bundles) and Developer ID Installer (`.pkg`) certificates | Microsoft Artifact Signing account, identity validation and a Public Trust certificate profile |
| Key custody | `.p12` exported from Keychain Access, imported into a temporary CI keychain | Never leaves Microsoft's HSM; CI signs remotely |
| Certificate lifetime | Years | About three days, renewed by the service; signatures stay valid through the timestamp |
| CI authentication | `.p12` + password secrets; notarization with an App Store Connect Team API key (`.p8`) | OpenID Connect from GitHub to an Entra app registration (federated credential); no stored password |
| Sign | `codesign --timestamp --options runtime` on each bundle; `productsign` on the `.pkg` | The plugin DLL inside the `.vst3` bundle, and any installer `.exe` |
| Post-sign | `notarytool submit --wait`, `stapler staple` | Nothing to notarize; SmartScreen reputation builds from downloads |
| Verify | `codesign --verify --strict`, `pkgutil --check-signature`, `stapler validate`, `spctl --assess --type install` | `Get-AuthenticodeSignature` status `Valid` with a timestamp certificate |
| One identity for many products | Yes | Yes: one account and one profile sign every product; the signing quota is shared |

## macOS: Credentials

**Developer ID certificates.** Only the team's Account Holder can create them: in Keychain Access, Certificate
Assistant > Request a Certificate From a Certificate Authority (saved to disk), then in Certificates, Identifiers &
Profiles create a **Developer ID Application** and a **Developer ID Installer** certificate from that request and
open the downloaded `.cer` on the same Mac, so it pairs with the private key. They last five years, and the same
identities sign every product of the team. Export each identity (certificate with its private key) from Keychain
Access as a `.p12` with an export password. The password is the one chosen at export, not the Apple ID password. Check
it before storing it:

```bash
/usr/bin/openssl pkcs12 -in DeveloperIDApplication.p12 -noout
```

No error means the password is right; "Mac verify error" means it is wrong. Use `/usr/bin/openssl` (LibreSSL):
Homebrew OpenSSL 3 rejects Keychain's legacy encryption unless given `-legacy`. A forgotten password is fixed by
exporting again from My Certificates, as long as the private key is in the login keychain
(`security find-identity -v` lists usable identities).

**Notarization key.** Use an App Store Connect **Team** API key: the `.p8` file, its Key ID and the Issuer ID.
Apple keeps no copy of the private key; a lost `.p8` means a new key:

1. App Store Connect > Users and Access > Integrations > App Store Connect API > Team Keys (Admin or Account
   Holder; the Account Holder may first need to Request Access).
2. Generate API Key, role **Developer** (enough for `notarytool`).
3. Download the `.p8` at once: the link disappears after one download (`AuthKey_<KEY_ID>.p8`).
4. Copy the Key ID from its row and the Issuer ID (a UUID) above the list.
5. Prove the three belong together: `xcrun notarytool history --key AuthKey_<KEY_ID>.p8 --key-id <KEY_ID> --issuer <ISSUER_ID>`.

One Team key serves every app on the team. Revoke a lost key only after every workflow that used it has moved
to the new one.

**Secrets** (one-line base64: `base64 -i file | tr -d '\n' | pbcopy`):

| Secret | Value |
| --- | --- |
| `APPLE_DEVELOPER_ID_APPLICATION_CERT_BASE64` / `_PASSWORD` | Application `.p12` and its export password |
| `APPLE_DEVELOPER_ID_INSTALLER_CERT_BASE64` / `_PASSWORD` | Installer `.p12` and its export password |
| `APPLE_NOTARY_KEY_BASE64`, `APPLE_NOTARY_KEY_ID`, `APPLE_NOTARY_ISSUER_ID` | Team API `.p8`, Key ID, Issuer ID |

## macOS: Release Workflow

Run it by `workflow_dispatch` with a numeric version input passed to CMake, so bundle, package and file names
agree. A workflow with only `workflow_dispatch` can be started only after its file exists on the default
branch. Steps, each failing fast:

1. **Check secrets** are non-empty (loop over names with `${!name}`), so a missing one fails before the build.
2. **Temporary keychain:** `security create-keychain` with a random password, `set-keychain-settings -lut 21600`,
   `unlock-keychain`, `security import <p12> -P <password> -A -t cert -f pkcs12 -k <keychain>` for both
   certificates, then `security set-key-partition-list -S apple-tool:,apple: -s -k <password> <keychain>` (without
   it `codesign` prompts and hangs), `security list-keychain -d user -s <keychain>`, and confirm both identities
   with `find-certificate -c "<exact Common Name>"`. Delete the keychain and decoded files in an `if: always()` step.
3. **Build** universal (`CMAKE_OSX_ARCHITECTURES="arm64;x86_64"`) with copy-after-build off.
4. **Check the artifacts** before signing: bundle ID, both slices (`lipo -archs`), the version
   (`plutil -extract CFBundleShortVersionString`), the AU type/subtype/manufacturer, no unexpected formats.
5. **Sign** each staged bundle: `codesign --force --timestamp --options runtime --keychain <kc> --sign "<Developer ID Application: …>"`.
   `--options runtime` is the hardened runtime notarization requires; plugins normally need no entitlements.
   Verify with `codesign --verify --strict --verbose=2` and compare `TeamIdentifier` from `codesign --display --verbose=4`.
6. **Package** (next section), `productsign` with the Installer identity, `pkgutil --check-signature`.
7. **Notarize:** `xcrun notarytool submit <pkg> --key <p8> --key-id <id> --issuer <issuer> --wait`, then
   `xcrun stapler staple` and `xcrun stapler validate`, then `spctl --assess --type install --verbose`.
   Authentication errors mean the `.p8`, Key ID and Issuer ID are not one active key; a rejection is a signing or
   content problem (`notarytool log <submission-id>`), not a reason to make a new key.
8. **Install and validate** on the runner: `sudo installer -pkg <pkg> -target /`; for the AU, clear
   `~/Library/Caches/AudioUnitCache` and `/Library/Caches/AudioUnitCache`, `killall -9 AudioComponentRegistrar`,
   then `auval -v <type> <subtype> <manufacturer>`; pluginval on the installed AU and VST3.
9. **Checksums** (`shasum -a 256`) and upload the `.pkg`, checksums, payload/choices listings and pluginval logs.

## macOS: Installer Package

- `pkgbuild --analyze --root <stage>` writes a component plist; set `BundleIsRelocatable`,
  `BundleIsVersionChecked` and `BundleHasStrictIdentifier` to false so an install always lands in
  `/Library/Audio/Plug-Ins/...` even if a copy exists elsewhere. Build one component package per format with
  `--install-location`, `--component-plist`, `--ownership recommended`.
- `productbuild --distribution Distribution.xml --resources <dir> --package-path <components>`; in
  `Distribution.xml`, `<options customize="allow" …>` and one `<choice>` per format with `start_selected="true"`:

  ```xml
  <installer-gui-script minSpecVersion="2">
      <title>Product</title>
      <options customize="allow" require-scripts="false" hostArchitectures="x86_64,arm64"/>
      <domains enable_anywhere="false" enable_currentUserHome="false" enable_localSystem="true"/>
      <background file="logo.png" alignment="bottomleft" scaling="none" mime-type="image/png"/>
      <background-darkAqua file="logo-white.png" alignment="bottomleft" scaling="none" mime-type="image/png"/>
      <choices-outline><line choice="au"/><line choice="vst3"/></choices-outline>
      <choice id="au" title="Audio Unit (AU)" start_selected="true"><pkg-ref id="com.vendor.product.au.pkg"/></choice>
      <choice id="vst3" title="VST3" start_selected="true"><pkg-ref id="com.vendor.product.vst3.pkg"/></choice>
      <pkg-ref id="com.vendor.product.au.pkg">Product-AU.pkg</pkg-ref>
      <pkg-ref id="com.vendor.product.vst3.pkg">Product-VST3.pkg</pkg-ref>
  </installer-gui-script>
  ```

  Gate it in CI: `installer -showChoicesXML` must list each choice visible, enabled and selected, and
  `pkgutil --payload-files` must contain each bundle.
- **Background logo.** Installer ignores `<background>` in Dark Mode; add `<background-darkAqua>` with a light
  variant. Use transparent PNGs, and save them at 144 dpi so a 128 px glyph draws at 64 pt (at 72 dpi it draws at
  twice the size). With `alignment="bottomleft" scaling="none"`, put transparent margin left of and below the
  glyph (about 24 pt and 20 pt) so it lines up with the step list instead of touching the window edge. Check
  both files are in the archive (`xar -tf <pkg>`). Test by building a throwaway product archive from the real
  `Distribution.xml` and Resources with empty `pkgbuild --nopayload` components under different identifiers.

## Windows: What To Sign And With What

- Hosts load unsigned VST3s. Signing is for SmartScreen (installer downloads) and Smart App Control on
  Windows 11, which checks every executable file. Sign the plugin DLL and the installer, always timestamped.
- SmartScreen reputation builds with download history (Microsoft's FAQ frames it per file); EV certificates no
  longer bypass it. Expect warnings on a new product's first releases whatever the certificate type.
- **Microsoft Artifact Signing** (formerly Trusted Signing): organizations in the US, Canada, EU, UK, Australia,
  New Zealand, Japan, South Korea, Singapore, Switzerland, Norway and Israel; individual developers in the US or
  Canada only. Needs a paid Azure subscription (pay-as-you-go). Basic tier 5,000 signatures a month, billed in
  full from account creation (not prorated). No EV, no custom CN/O: the certificate shows the validated legal
  name.
- **Otherwise** an OV certificate with the key in hardware or a cloud HSM (CA/B Forum CSC-13); certificates
  issued from 2026-03-01 last at most 460 days.

## Windows: Artifact Signing Set-Up

In the Azure portal, as the subscription owner:

1. Register the `Microsoft.CodeSigning` resource provider on the subscription if it is not listed.
2. Create an **Artifact Signing account** in a supported region (its Overview shows the **Account URI**, the
   signing endpoint, e.g. `https://eus.codesigning.azure.net/`) on the Basic tier.
3. Give yourself the **Artifact Signing Identity Verifier** role on the account (the New identity button is
   disabled without it).
4. **Identity validation > Individual > New identity > Public** (or Organization). For individuals the details
   come from the subscription's billing account, whose type must be *Individual*; use the name exactly as on the
   government ID. Microsoft emails a link: complete it in Microsoft Authenticator (Verified ID with a face check)
   and upload the ID, plus a recent utility bill or bank statement if the ID has no address. City, state and
   country appear on the certificate. Validation expires; reminders start 60 days before, and signing stops if
   it lapses. It is shared by every signing account in the subscription.
5. **Certificate profile:** type **Public Trust** (Public Trust Test is not trusted by Windows), select the
   validated identity, **Program type: None** (Windows endpoint security platform and Windows recovery remote
   management are for those Microsoft partner programs). Name it for reuse across products.

Certificates under the profile last about three days and are renewed automatically: Microsoft keeps them
short-lived for security, and the private key never leaves its HSM, so a misused certificate expires quickly
and there is nothing long-lived to steal or renew by hand. A signature made while a
certificate was valid stays valid because the signing timestamp proves when it was made.

## Windows: GitHub Access Without A Password

1. **App registration** (Microsoft Entra ID > App registrations > New registration): single tenant, no redirect
   URI. Note the Application (client) ID and Directory (tenant) ID. Do not create a client secret.
2. **Federated credential** (the app > Certificates & secrets > Federated credentials > Add credential,
   scenario *GitHub Actions deploying Azure resources*): entity type **Branch**, branch `main`, audience
   `api://AzureADTokenExchange`. The subject must equal GitHub's token `sub` exactly. Check which format the
   repository uses:

   ```bash
   gh api repos/<owner>/<repo>/actions/oidc/customization/sub
   gh api repos/<owner>/<repo> --jq '.owner.id, .id'   # owner ID, repository ID (user or organization owner)
   ```

   With `"use_immutable_subject": true` the subject is
   `repo:<owner>@<owner-id>/<repo>@<repo-id>:ref:refs/heads/main` (the portal form then asks for the numeric
   organization and repository IDs); otherwise `repo:<owner>/<repo>:ref:refs/heads/main`. A mismatch fails the
   login with "AADSTS70021: No matching federated identity record found".
3. **Role:** on the Artifact Signing account, Access control (IAM) > Add role assignment > **Artifact Signing
   Certificate Profile Signer** (older name: Trusted Signing Certificate Profile Signer) > members: the app. The
   member picker lists only people until you type the app's name in its search box. Assignments can take a few
   minutes to apply.
4. **Repository secrets** `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID`. They are identifiers,
   not passwords; the trust is the federated credential. The endpoint, account and profile names are not secret
   and can live in the workflow.
5. Another repository needs only its own federated credential on the same app (up to 20 per app) and the same
   three secrets.

If the portal shows you as **User Access Administrator at Root (Inherited)**, "Access management for Azure
resources" was switched on under Entra ID > Properties. Switch it off when done; it is not needed for signing.

## Windows: Release Workflow

```yaml
permissions:
  contents: read
  id-token: write          # OIDC token for azure/login
jobs:
  release:
    runs-on: windows-2025  # no `environment:` here; see below
    steps:
      # ... build, then copy the bundle to dist/stage
      - uses: azure/login@v3
        with:
          client-id: ${{ secrets.AZURE_CLIENT_ID }}
          tenant-id: ${{ secrets.AZURE_TENANT_ID }}
          subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
      - uses: azure/artifact-signing-action@v2
        with:
          endpoint: https://eus.codesigning.azure.net/
          signing-account-name: <account>
          certificate-profile-name: <profile>
          files: ${{ github.workspace }}\dist\stage\<Name>.vst3\Contents\x86_64-win\<Name>.vst3
          timestamp-rfc3161: http://timestamp.acs.microsoft.com
          timestamp-digest: SHA256
      - name: Verify the signature
        shell: pwsh
        run: |
          $sig = Get-AuthenticodeSignature -LiteralPath "dist\stage\<Name>.vst3\Contents\x86_64-win\<Name>.vst3"
          if ($sig.Status -ne 'Valid') { throw "Signature status: $($sig.Status)" }
          if ($null -eq $sig.TimeStamperCertificate) { throw "No timestamp" }
```

- **No `environment:` key on the job.** With one, GitHub's subject becomes `…:environment:<name>` and the
  branch credential no longer matches.
- **Keep `AZURE_CLIENT_ID`/`AZURE_TENANT_ID` out of job-level `env`.** The signing action uses
  `DefaultAzureCredential`, which tries `EnvironmentCredential` first; give those values only to a step that
  checks the secrets exist.
- The action runs on Windows x64 runners only; sign ARM64 artifacts in an x64 job.
- Then run pluginval on the signed copy, package (`.zip` with a README now, an installer later, signed the same
  way), write checksums and upload.
- Windows chooses the signing format from the file's PE header, so the `.vst3`-named DLL should sign as is; if
  signing reports "This file format cannot be signed because it is not recognized", sign a `.dll`-named copy and
  rename it back.

## GitHub Secrets On A Free Plan

Environment secrets, deployment-branch restrictions and required reviewers need GitHub Pro, Team or Enterprise
for private repositories. On the Free plan:

- Store signing secrets as **repository** secrets. `${{ secrets.NAME }}` reads one pool (organization,
  repository, environment; the most specific wins), so a job with an `environment:` line still finds them.
- An `environment:` line on a Free private repository only creates a deployment record; it enforces nothing.
- Any workflow pushed to any branch can read repository secrets: give write access only to people trusted with
  the signing identities. Windows OIDC adds a second guard, since only `main` matches the federated credential.
- On a paid plan, move the secrets to a protected environment (main only, reviewers) and delete the repository
  copies; for Windows OIDC, change the federated credential's entity type to Environment.

## Linux

No signing is customary for plugin binaries. Publish `SHA256SUMS` next to the archive; a detached GPG signature
is optional.

## Common Mistakes

- Validating an AU in the build directory: macOS only registers AUs under `Plug-Ins/Components`, so pluginval
  reports "No types found". Install it, reset the registrar, then validate.
- Treating the `.p12` password as the Apple ID password, or testing it with Homebrew OpenSSL 3 without `-legacy`.
- Hardened runtime set "in CMake": it is `codesign --options runtime`.
- Expecting `<background>` to show in Dark Mode, or a 72 dpi logo to draw at its pixel size on Retina.
- A federated credential in the old `repo:<owner>/<repo>:…` form when GitHub issues immutable-ID subjects.
- Assigning the signer role to your user instead of the app, or forgetting it: the signing step then fails 403.
- Expecting `workflow_dispatch` on a feature branch: the workflow file must be on the default branch first.

## Sources

- Apple: Developer ID, `notarytool`, `stapler`, Installer `Distribution.xml` reference (`background`,
  `background-darkAqua`).
- Microsoft Learn: [Artifact Signing quickstart](https://learn.microsoft.com/en-us/azure/artifact-signing/quickstart)
  and [FAQ](https://learn.microsoft.com/en-us/azure/artifact-signing/faq); [SmartScreen reputation](https://learn.microsoft.com/en-us/windows/apps/package-and-deploy/smartscreen-reputation).
- [azure/artifact-signing-action](https://github.com/Azure/artifact-signing-action) (v2 inputs: `endpoint`,
  `signing-account-name`, `certificate-profile-name`, `files`, `timestamp-rfc3161`, `timestamp-digest`);
  [azure/login](https://github.com/Azure/login).
- GitHub: OIDC subject customization REST API (`/repos/{owner}/{repo}/actions/oidc/customization/sub`);
  [Actions billing and plans](https://docs.github.com/en/billing/concepts/product-billing/github-actions).
- CA/B Forum ballot CSC-13; DigiCert on the 460-day code-signing validity limit.

Checked 2026-10. Portal labels, prices and action majors change: confirm against the current pages.
