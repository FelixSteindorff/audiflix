# Security Policy

## Supported versions

Audiflix is a small project maintained by one person. Security fixes are made
for the latest release only.

| Version | Supported |
|---|---|
| 0.1.x | ✅ |
| < 0.1 | ❌ |

## Reporting a vulnerability

Please **do not open a public issue** for a security problem.

1. Use GitHub's private reporting:
   [Report a vulnerability](https://github.com/FelixSteindorff/audiflix/security/advisories/new).
2. If that is not possible, write to the address on the maintainer's GitHub
   profile and put "Audiflix security" in the subject line.

Please include:

- what you did and what happened,
- the Audiflix version (Help → About) and your operating system,
- the Audiobookshelf server version, if it is relevant,
- log excerpts if they help - Audiflix redacts tokens automatically, but please
  check before sending.

You can expect an acknowledgement within **7 days** and an assessment within
**30 days**. Fixed issues are credited in `CHANGELOG.md` unless you prefer
otherwise.

## What Audiflix does to protect your credentials

- **Tokens are never written to disk in plain text.** Access and refresh tokens
  go into the system credential store through `keyring` (Windows Credential
  Manager, macOS Keychain, Secret Service). When no backend is available the
  token is kept in memory for the current session only and the user is told. A
  `token.json` from a pre-release version is deleted on start-up.
- **Tokens leave the machine only towards your own server.** Audiobookshelf can
  return absolute media URLs; Audiflix compares scheme, host and port with the
  configured server and refuses to attach the token to anything else. Downloads
  use the `Authorization` header rather than a URL parameter.
- **Nothing secret is logged.** Every log record passes a filter that replaces
  `token=` query values and `Authorization` / `x-refresh-token` header values
  with `<redacted>`.
- **Unencrypted HTTP is flagged.** Signing in over `http://` to a non-local host
  requires an explicit confirmation.
- **Passwords are never stored.** They are sent once to `/login` and then
  discarded; only the resulting tokens are kept.
- TLS certificates are verified by `requests` with the system trust store.
  There is no option to disable verification.

## Threat model and limits

Audiflix is a desktop client. It trusts:

- **the local user account** - anything running as you can read the credential
  store and the process memory,
- **the configured Audiobookshelf server** - it is your server, and its
  responses drive what the client displays and plays.

Audiflix does **not** protect against a compromised operating system, a
malicious VLC installation, or an attacker who controls the server you point it
at. It does not accept incoming network connections and does not open a port.

## Third-party components

Audiflix bundles no server code. It depends on wxPython, python-vlc, requests,
keyring and accessible_output2, and requires a separately installed VLC media
player. Vulnerabilities in those projects should be reported to them; if a
version pin in `requirements-build.txt` is affected, please tell us so the pin
can be raised.
