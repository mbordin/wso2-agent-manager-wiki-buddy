#!/usr/bin/env bash
# Crea il repo su GitHub (account autenticato in gh) e fa il push. Uso: ./publish.sh [nome-repo]
set -euo pipefail
cd "$(dirname "$0")"
REPO="${1:-wso2-agent-manager-wiki-buddy}"
gh auth status >/dev/null
[ -d .git ] || git init -b main
git add -A
git diff --cached --quiet || git commit -m "Wiki-Buddy: agente OpenAI + MCP DeepWiki per WSO2 Agent Manager"
if gh repo view "mbordin/$REPO" >/dev/null 2>&1; then
  git remote get-url origin >/dev/null 2>&1 || git remote add origin "https://github.com/mbordin/$REPO.git"
  git push -u origin main
else
  gh repo create "mbordin/$REPO" --public --source . --remote origin --push \
    --description "Esempio WSO2 Agent Manager: agente OpenAI con MCP di terze parti"
fi
echo "Pubblicato: https://github.com/mbordin/$REPO"
