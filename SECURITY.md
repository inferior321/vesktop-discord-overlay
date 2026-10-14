# Security

## Reporting a problem

If you find something that could put someone's Discord account or computer at risk, please **don't open a
public issue**. Report it privately instead: on this repository's **Security** tab, choose **Report a
vulnerability**. Include what you found, how to reproduce it, and which version (`python3 main.py --version`).

You'll get a reply as soon as possible; fixes for real problems come before anything else.

## What's in scope

- The overlay itself, `bridge.js` (the code it runs inside Vesktop), the installer and the launcher.
- Anything that could expose your login token, act on your account without you asking, or let another
  program or user on the computer do so more easily than they already could.

## Known and accepted

These are how the overlay works, and are described in the README's **Before you use it**:

- **The debug port.** Vesktop runs with Chromium's remote-debugging port (9222) open on 127.0.0.1 so the
  overlay can reach it. While it's open, any program run by any user account on the same computer could control
  your Discord session. Other computers can't reach it.
- **Discord's terms.** Vencord / Vesktop are client modifications, which Discord's Terms of Service don't
  allow; the overlay works through them.

## What the overlay does and doesn't do

- It never reads, stores or sends your login token; everything goes through Discord's own client code inside
  Vesktop.
- It only asks Discord for something when you do something (open a chat, send, react, edit, delete, mute, scroll
  back, scroll a forum's older posts, search GIFs, open a member list, join a call); it makes no requests on its
  own.
- The only other things it downloads are the images, GIFs and thumbnails it shows (from Discord's and
  YouTube's servers).
