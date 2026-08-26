#!/usr/bin/env python3
"""PreToolUse-hook: waarschuwt (blokkeert NIET) bij twee Bash-gewoonten die de
globale CLAUDE.md verbiedt maar die subagents blijven maken:

  1. een `cd <pad> && …`-prefix -- de werkmap is al de repo-root;
  2. `echo "=== kop ==="`-segmenten -- de tool labelt de uitvoer al per commando.

Werkt op de hoofdsessie én op subagent-tool-calls (PreToolUse vuurt op beide).
Niet-blokkerend: geeft alleen `additionalContext` terug, exit altijd 0.
Faalt open: bij onleesbare invoer of twijfel geen output en exit 0, zodat een
kapotte hook nooit een tool-call tegenhoudt. Leest stdin met python3 (de losse
`jq`-CLI staat niet op deze machine)."""

import json
import re
import sys

try:
    data = json.load(sys.stdin)
    cmd = data.get("tool_input", {}).get("command", "")
except Exception:
    sys.exit(0)

if not isinstance(cmd, str) or not cmd:
    sys.exit(0)

msgs = []

# 1. `cd <pad>` gevolgd door een geketend commando (&& of ;). Een kale `cd`
#    zonder keten valt hier bewust buiten.
if re.search(r"(^|[\s;&(])cd\s+\S+\s*(&&|;)", cmd):
    msgs.append(
        "`cd <pad> && …`: de werkmap is al de repo-root en blijft dat tussen "
        "Bash-calls -- laat de cd-prefix weg. Werk je in een worktree of de "
        "andere repo, gebruik dan `git -C <pad> …` in plaats van `cd`."
    )

# 2. Decoratieve kopregels `echo "=== … ==="` (of ==== enz.).
if re.search(r"""echo\s+['"]?==""", cmd):
    msgs.append(
        '`echo "=== kop ==="`: de tool labelt de uitvoer al per commando -- '
        "laat de kopregels weg (een korte `echo --` mag als het echt moet)."
    )

if msgs:
    out = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "additionalContext": "Efficiëntie-nudge (niet-blokkerend, uit CLAUDE.md): "
            + " ".join(msgs),
        }
    }
    print(json.dumps(out, ensure_ascii=False))

sys.exit(0)
