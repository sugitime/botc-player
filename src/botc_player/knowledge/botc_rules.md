# Blood on the Clocktower — Agent Rules Primer

Blood on the Clocktower (BotC) is a social deduction game. One Storyteller runs the game.
Players are either **Good** or **Evil**. Good wins by executing all Demons. Evil wins by
reducing the living players to two (or by other script-specific conditions).

## Core structure

- **Script**: A curated set of roles (e.g. Trouble Brewing, Bad Moon Rising, Sects & Violets).
- **Setup**: Roles are assigned secretly. There is usually one Demon, 0–3 Minions, Outsiders, and Townsfolk.
- **Day**: Discussion, nominations, votes, execution.
- **Night**: Storyteller wakes roles in order; private information is delivered (often as pings / whispers in online play).

## Alignments & bluffs

- **Townsfolk (Good)**: Honest abilities that help Good. Generally should tell the truth unless bluffing for a tactical reason (rare for most Townsfolk).
- **Outsiders (Good)**: Abilities that can hurt Good if mishandled (e.g. Drunk, Recluse, Saint, Butler). Often truth-adjacent but confusing.
- **Minions (Evil)**: Support the Demon. Must lie about identity. Coordinate privately when possible.
- **Demon (Evil)**: Kills at night (usually). Must bluff as a Good role and survive the day.

## When to lie vs tell the truth

| Situation | Truth? | Notes |
|-----------|--------|-------|
| You are confirmed Good Townsfolk with solid info | Prefer truth | Share carefully; protect soft info from misread |
| You are Evil bluffing a role | Lie about identity | Keep a consistent bluff; match night timing |
| You are Poisoned / Drunk (if you know) | Your info may be false | Say what you "saw" but leave room for error |
| Night info that outs a teammate | Protect teammates | Soft-claim, mislead, or redirect |
| Final day / tight numbers | Maximize team EV | Sometimes hard-claim; sometimes throw suspicion |

**Hard rule for this agent:** Always optimize for **your team's win**. Good players generally
maximize information quality for Good. Evil players protect the Demon and create false narratives.

## Public speaking etiquette (critical for online BotC)

1. **Do not talk over people.** Wait for silence or a clear gap.
2. **Raise hand** (use the in-app hand / speak request) during structured public discussion.
3. **Speak when called on** by the Storyteller or when the queue reaches you.
4. Keep turns **short** (1–3 points). Yield if interrupted or time is short.
5. In **private chats / whispers**, you may speak more freely and strategically.
6. Be **polite**. Never insult players. Disagreement is fine; rudeness is not.
7. During **nominations/votes**, be clear and brief. State nominee + reason + vote intent.

## Night pings & private interactions (botc.app style)

- Storyteller may ping you for ability targets or confirmations.
- Respond promptly at night when woken.
- Use private voice/text channels only with intended partners.
- Do not leak private Evil coordination into public chat.

## Voting

- Vote only when the app expects a vote (nomination phase).
- Count living players and required majority if known.
- Evil: vote to protect Demon / eliminate strong Good reads when safe.
- Good: vote based on evidence, social reads, and ability results.

## Common Trouble Brewing roles (baseline script)

**Townsfolk:** Washerwoman, Librarian, Investigator, Chef, Empath, Fortune Teller, Undertaker, Monk, Ravenkeeper, Virgin, Slayer, Soldier, Mayor  
**Outsiders:** Butler, Drunk, Recluse, Saint  
**Minions:** Poisoner, Spy, Scarlet Woman, Baron  
**Demon:** Imp

Other scripts expand the role pool; reason from ability text when available.

## Online interface notes (botc.app)

- Video/avatar and mic are browser WebRTC devices (virtual cam + virtual mic).
- Hand raise, mute, vote, and grimoire UI elements must be driven carefully.
- Night UI may show prompts; answer via clicks and/or short voice replies.
- Prefer structured tool actions (raise_hand, vote, select_player) over free-form mouse thrashing.
