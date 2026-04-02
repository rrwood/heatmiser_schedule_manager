#!/bin/sh
# Git Manager for heatmiser_schedule_manager
# Usage: ./git-manager.sh <command> [options]
#
# Commands:
#   setup                          - Configure git user and GitHub token
#   status                         - Show current git status
#   pull                           - Pull latest changes from GitHub
#   push [message]                 - Stage all, commit with message, and push
#   log [n]                        - Show last n commits (default 10)
#   tag <version> [message]        - Create an annotated tag (e.g. v1.0.0)
#   release <version> [title] [notes] - Create a GitHub release from a tag
#   list-releases                  - List all GitHub releases

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
GITHUB_REPO=""          # Set this after creating the GitHub repo, e.g. "youruser/heatmiser_schedule_manager"
CONFIG_FILE="/config/.git-manager-config"

cd "$REPO_DIR" || exit 1

# Load saved config (token, username, email)
if [ -f "$CONFIG_FILE" ]; then
    . "$CONFIG_FILE"
fi

# Use token for HTTPS auth if available
if [ -n "$GITHUB_TOKEN" ]; then
    git config credential.helper "!f() { echo username=token; echo password=$GITHUB_TOKEN; }; f"
fi

usage() {
    echo "Usage: $0 <command> [options]"
    echo ""
    echo "Commands:"
    echo "  setup                          Configure git user and GitHub token"
    echo "  status                         Show git status"
    echo "  pull                           Pull latest changes"
    echo "  push [commit message]          Stage all changes, commit, and push"
    echo "  log [n]                        Show last n commits (default 10)"
    echo "  tag <version> [message]        Create and push an annotated tag"
    echo "  release <version> [title] [notes]  Create a GitHub release from a tag"
    echo "  list-releases                  List GitHub releases"
    echo ""
    echo "Examples:"
    echo "  $0 setup"
    echo "  $0 push 'Initial release'"
    echo "  $0 tag v1.0.0 'Initial release'"
    echo "  $0 release v1.0.0 'Version 1.0.0' 'First public release'"
}

cmd_setup() {
    echo "=== Git Manager Setup ==="
    echo ""
    printf "GitHub username: "
    read -r GIT_USER_NAME
    printf "GitHub email: "
    read -r GIT_USER_EMAIL
    printf "GitHub repo (e.g. youruser/heatmiser_schedule_manager): "
    read -r GITHUB_REPO_INPUT
    echo ""
    echo "Create a GitHub Personal Access Token at:"
    echo "  https://github.com/settings/tokens/new"
    echo "Required scopes: repo (full control)"
    echo ""
    printf "GitHub Personal Access Token: "
    read -r GITHUB_TOKEN

    git config user.name "$GIT_USER_NAME"
    git config user.email "$GIT_USER_EMAIL"

    cat > "$CONFIG_FILE" << EOF
GITHUB_TOKEN=$GITHUB_TOKEN
GIT_USER_NAME=$GIT_USER_NAME
GIT_USER_EMAIL=$GIT_USER_EMAIL
GITHUB_REPO=$GITHUB_REPO_INPUT
EOF
    chmod 600 "$CONFIG_FILE"

    GITHUB_REPO="$GITHUB_REPO_INPUT"
    git remote set-url origin "https://token:${GITHUB_TOKEN}@github.com/${GITHUB_REPO}.git" 2>/dev/null \
        || git remote add origin "https://token:${GITHUB_TOKEN}@github.com/${GITHUB_REPO}.git"

    echo ""
    echo "Setup complete! Test with: $0 status"
}

_require_repo() {
    if [ -z "$GITHUB_REPO" ]; then
        echo "Error: GITHUB_REPO not set. Run: $0 setup"
        exit 1
    fi
}

_require_token() {
    if [ -z "$GITHUB_TOKEN" ]; then
        echo "Error: GITHUB_TOKEN not set. Run: $0 setup"
        exit 1
    fi
}

cmd_status() {
    echo "=== Repository Status ==="
    git status
}

cmd_pull() {
    echo "=== Pulling latest changes ==="
    git pull origin "$(git rev-parse --abbrev-ref HEAD)"
}

cmd_push() {
    MESSAGE="${1:-Update $(date '+%Y-%m-%d %H:%M')}"
    echo "=== Committing and Pushing ==="
    echo "Message: $MESSAGE"
    echo ""
    git add -A
    git status --short
    echo ""
    git diff --cached --stat
    echo ""
    git commit -m "$MESSAGE" || { echo "Nothing to commit."; exit 0; }
    git push origin "$(git rev-parse --abbrev-ref HEAD)"
    echo ""
    echo "Pushed successfully."
}

cmd_log() {
    N="${1:-10}"
    git log --oneline -"$N"
}

cmd_tag() {
    VERSION="$1"
    MESSAGE="${2:-Release $VERSION}"

    if [ -z "$VERSION" ]; then
        echo "Error: version required (e.g. v1.0.0)"
        exit 1
    fi

    echo "=== Creating tag $VERSION ==="
    git tag -a "$VERSION" -m "$MESSAGE"
    git push origin "$VERSION"
    echo "Tag $VERSION created and pushed."
}

cmd_release() {
    _require_repo
    _require_token

    VERSION="$1"
    TITLE="${2:-$VERSION}"
    NOTES="${3:-Release $VERSION}"

    if [ -z "$VERSION" ]; then
        echo "Error: version required (e.g. v1.0.0)"
        exit 1
    fi

    # Create tag first if it doesn't exist
    if ! git rev-parse "$VERSION" >/dev/null 2>&1; then
        echo "Tag $VERSION not found, creating it first..."
        cmd_tag "$VERSION" "$TITLE"
    fi

    echo "=== Creating GitHub Release $VERSION ==="

    RESPONSE=$(curl -s -X POST \
        -H "Authorization: token $GITHUB_TOKEN" \
        -H "Content-Type: application/json" \
        -d "{
            \"tag_name\": \"$VERSION\",
            \"name\": \"$TITLE\",
            \"body\": \"$NOTES\",
            \"draft\": false,
            \"prerelease\": false
        }" \
        "https://api.github.com/repos/${GITHUB_REPO}/releases")

    RELEASE_URL=$(echo "$RESPONSE" | grep -o '"html_url": "[^"]*"' | head -1 | cut -d'"' -f4)

    if [ -n "$RELEASE_URL" ]; then
        echo "Release created: $RELEASE_URL"
    else
        echo "Error creating release:"
        echo "$RESPONSE"
        exit 1
    fi
}

cmd_list_releases() {
    _require_repo
    _require_token

    echo "=== GitHub Releases ==="
    curl -s \
        -H "Authorization: token $GITHUB_TOKEN" \
        "https://api.github.com/repos/${GITHUB_REPO}/releases" \
        | grep -E '"tag_name"|"name"|"html_url"' \
        | paste - - - \
        | sed 's/.*"tag_name": "\([^"]*\)".*"name": "\([^"]*\)".*"html_url": "\([^"]*\)".*/\1  \2\n  \3/'
}

COMMAND="$1"
shift || true

case "$COMMAND" in
    setup)         cmd_setup ;;
    status)        cmd_status ;;
    pull)          cmd_pull ;;
    push)          cmd_push "$@" ;;
    log)           cmd_log "$@" ;;
    tag)           cmd_tag "$@" ;;
    release)       cmd_release "$@" ;;
    list-releases) cmd_list_releases ;;
    ""|help|--help|-h) usage ;;
    *)
        echo "Unknown command: $COMMAND"
        usage
        exit 1
        ;;
esac
