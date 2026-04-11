#!/bin/bash
# agent-skills session start hook
# Injects the using-agent-skills meta-skill into every new session

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SKILLS_DIR="$(dirname "$SCRIPT_DIR")/skills"
META_SKILL="$SKILLS_DIR/using-agent-skills/SKILL.md"

json_escape() {
  perl -0777 -pe 's/\\/\\\\/g; s/"/\\"/g; s/\r?\n/\\n/g'
}

if [ -f "$META_SKILL" ]; then
  CONTENT=$(cat "$META_SKILL")
  ADDITIONAL_CONTEXT="agent-skills loaded. Use the skill discovery flowchart to find the right skill for your task.

$CONTENT"
  ESCAPED=$(printf '%s' "$ADDITIONAL_CONTEXT" | json_escape)
  printf '%s\n' "{\"hookSpecificOutput\":{\"hookEventName\":\"SessionStart\",\"additionalContext\":\"$ESCAPED\"}}"
else
  ADDITIONAL_CONTEXT="agent-skills: using-agent-skills meta-skill not found. Skills may still be available individually."
  ESCAPED=$(printf '%s' "$ADDITIONAL_CONTEXT" | json_escape)
  printf '%s\n' "{\"hookSpecificOutput\":{\"hookEventName\":\"SessionStart\",\"additionalContext\":\"$ESCAPED\"}}"
fi
