# Compact Handoff

> A [Claude Code](https://code.claude.com/docs/en/skills) skill.

Compact the current conversation into a large standalone handoff file on disk, then open a BRAND NEW Claude Code session named after the current chat with an incremented counter, seeded with only a pointer to that file, leaving the current chat fully intact. Use this whenever the user wants a clean context window without losing what was learned, or says any of — "compact to a new chat", "compact but start fresh", "carry this over to a new session", "hand this off", "new chat with this context", "my context is getting heavy", "this chat is too long", "start over but remember this", "dump the context and open a fresh one", or asks for a handoff, a context dump, or a session summary they can reuse later. Also use it when a long investigation is finished and the follow-up work deserves its own window. Prefer this over plain /compact whenever the user wants the old chat to stay readable afterward, and reach for it even if they never say the word "compact".

## Install

Via [skills.sh](https://skills.sh):

```bash
npx skills add marks97/compact-handoff
```

Or manually — copy the `compact-handoff/` folder into your `.claude/skills/` directory.

## Usage

Once installed, Claude invokes this skill automatically when your request matches
what it does (see the triggers in [`compact-handoff/SKILL.md`](compact-handoff/SKILL.md)). You can
also ask for it by name.

## License

MIT © Marc Amoros

