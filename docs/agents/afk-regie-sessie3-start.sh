#!/usr/bin/env bash
# Start regiesessie 3 headless (Fable, auto-permissies), los van de sessie die dit aanroept.
# De opdracht staat in afk-regie-sessie3-start.md (alles ná de scheidingslijn).
# Log: ~/gwsw-orox-helpers-sessie3/sessie3.log (stream-json, één JSON-regel per gebeurtenis);
# volgen met `tail -f`, hervatten met `claude --resume "$(cat ~/gwsw-orox-helpers-sessie3/session-id)"`.
set -euo pipefail
REPO=/home/martin/gwsw-orox-helpers
MAP="$HOME/gwsw-orox-helpers-sessie3"
mkdir -p "$MAP"
SID=$(uuidgen)
echo "$SID" > "$MAP/session-id"
PROMPT=$(sed -n '/^---$/,$p' "$REPO/docs/agents/afk-regie-sessie3-start.md" | tail -n +2)
cd "$REPO"
# Pas starten als sessie 2 klaar is: #68 gesloten én de werkboom op dev schoon.
until [ "$(gh issue view 68 -R mcolee/gwsw-orox-helpers --json state --jq .state)" = "CLOSED" ] \
      && [ -z "$(git status --porcelain)" ]; do
  sleep 120
done
sleep 60
# De CLAUDE*-omgevingsvariabelen van een aanroepende Claude-sessie gaan niet mee: eigen sessie.
setsid nohup env -u CLAUDECODE -u CLAUDE_CODE_SESSION_ID -u CLAUDE_CODE_CHILD_SESSION \
  -u CLAUDE_PID -u CLAUDE_CODE_MESSAGING_SOCKET -u CLAUDE_CODE_MESSAGING_TOKEN \
  -u CLAUDE_CODE_BRIDGE_SESSION_ID -u CLAUDE_CODE_ENTRYPOINT \
  claude -p "$PROMPT" \
    --model claude-fable-5-1 \
    --permission-mode auto \
    --session-id "$SID" \
    --output-format stream-json --verbose \
    > "$MAP/sessie3.log" 2> "$MAP/sessie3.err" < /dev/null &
echo "gestart: pid $! sessie $SID"
