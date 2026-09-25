# Life First App 💙

> **Status (per `HIBERNATION_STATUS.md`, marked 2026-08-19): intentionally
> dormant, NOT fossil/abandoned.** This is the original Phoenix/LifeFirst
> architecture; the Electron dashboard + PHP hotline track
> (`sector2/apps/lifefirst/`, live at `lifefirst.authenticcoder.com`) is the
> current active development focus instead. Do not archive/delete this
> directory without JW's explicit say-so.
>
> **Install section below was corrected 2026-09-24** — it previously
> described cloning a separate `LifeFirstApp.git` repo and running
> `java -jar LifeFirstApp.jar`, which doesn't match what's actually in this
> directory: a real Kotlin/Gradle Android app (`app/build.gradle.kts`,
> `AndroidManifest.xml`) plus a Python Firebase Cloud Function
> (`functions/main.py`), not a standalone Java JAR.

[![Sponsor jwl247](https://img.shields.io/badge/Sponsor%20jwl247-%E2%9D%A4-red?logo=github&style=for-the-badge)](https://github.com/sponsors/jwl247)
[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg?style=for-the-badge)](https://www.gnu.org/licenses/gpl-3.0)
[![Language: Java](https://img.shields.io/badge/Java-11+-orange?style=for-the-badge&logo=java)](https://java.com)

> A relentless personal accountability companion. Built for Laurie. Open to everyone.

Life First App is a fully open source, self-hostable accountability system with
10 AI-powered modules. No subscriptions. No vendor lock-in. No barriers.
Your data stays yours — always.

---

## What is Life First App?

Life First App started as something personal — built specifically for someone
with high-functioning autism who needed a reliable, patient, and relentless
daily companion. What began as an act of love became something anyone can use,
regardless of their circumstances or budget.

It runs on [Phoenix DevOps OS](https://github.com/jwl247/Phoenix-DevOps-oS) —
a self-hostable OS built from scratch specifically so this app would never
depend on a vendor again.

---

## Features

- **10 AI-powered accountability modules** — built for real daily life
- **Privacy-first** — self-hosted, your data never leaves your machine
- **Relentless** — shows up every single day, no matter what
- **Accessible** — designed for anyone, regardless of technical skill
- **No subscriptions** — free to run, free to own, free forever
- **Vendor lock-in proof** — runs entirely on your own hardware via Phoenix

---

## Modules

| Module | Purpose |
|--------|---------|
| Daily Check-in | Morning and evening accountability prompts |
| Goal Tracker | Set, monitor, and celebrate progress |
| Routine Builder | Build consistent daily habits |
| Mood Journal | Track emotional patterns over time |
| Task Manager | Break big tasks into manageable steps |
| Reminder System | Gentle, persistent reminders |
| Progress Reports | Weekly and monthly summaries |
| Focus Mode | Minimize distraction, maximize presence |
| Support Network | Connect trusted people to your journey |
| Emergency Anchor | Grounding tools for difficult moments |

---

## Getting Started

### Requirements
- Android Studio (or `gradlew` + an Android SDK on PATH)
- JDK 11+ (for Gradle itself)
- Firebase CLI, if you also want to run/deploy `functions/` (Python)

### Building the app (this directory, real project layout)

```bash
cd sector2/apps/lifefirst-android

# Build a debug APK
./gradlew assembleDebug        # gradlew.bat on Windows

# Or just open this folder directly in Android Studio and run from there
```

The Firebase Cloud Function (`functions/main.py`) is a separate deploy target —
see `.firebaserc` for the configured project, and use the standard
`firebase deploy --only functions` flow if/when this component is reactivated.

> This project is dormant (see status note above) — there is no current
> self-hosting guide because it isn't the active LifeFirst deployment target.
> If you're trying to actually run Laurie's Life First system today, see
> `sector2/apps/lifefirst/README.md` instead (PHP + Apache, live and deployed).

---

## Self-Hosting with Phoenix

Life First App is designed to run on
[Phoenix DevOps OS](https://github.com/jwl247/Phoenix-DevOps-oS).
Phoenix provides the Helix memory manager, security layer, and tunnel support
to keep your app fast, private, and accessible from anywhere — without
exposing your machine to the internet.

```
Your Device (Phoenix + Life First App)
        ↑
Cloudflare Tunnel  ←  no open ports, no exposed IP
        ↑
yourDomain.com  ←  accessible anywhere, fully private
```

---

## Contributing

Everyone is welcome here — experienced developers and complete beginners alike.
If something doesn't work, open an issue. If you have an idea, open a discussion.
If you want to build, open a pull request.

1. Fork the repo
2. Create a branch (`git checkout -b feature/your-idea`)
3. Commit your changes (`git commit -m 'Add your idea'`)
4. Push to the branch (`git push origin feature/your-idea`)
5. Open a Pull Request

---

## The Story

This app exists because of Laurie. She needed something relentless and patient
and always there. I built it for her. Then I realized a lot of people need
exactly that — and none of them should have to pay a subscription or hand
their data to a company to get it.

So here it is. Free. Open. Yours.

---

## Sister Projects

| Project | Description |
|---------|-------------|
| [Phoenix DevOps OS](https://github.com/jwl247/Phoenix-DevOps-oS) | The self-hostable OS that powers Life First App |
| [Double-Helix-StorageOS](https://github.com/jwl247/Double-Helix-StorageOS-experimental-) | Extreme speed storage layer |
| [REALsure-security](https://github.com/jwl247/REALsure-security-theoreticlly-unhackable-) | Security architecture powering the app |

---

## License

GNU General Public License v3.0 — free to use, free to build on.
If you build on Life First App, your work stays open source too.

---

## Support This Project

If Life First App helps you or someone you love, consider sponsoring.
Every bit keeps an old ironworker coding.

[![Sponsor jwl247](https://img.shields.io/badge/Sponsor%20jwl247-%E2%9D%A4-red?logo=github&style=for-the-badge)](https://github.com/sponsors/jwl247)

---

*Built with love. For Laurie. For everyone.*
