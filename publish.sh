#!/bin/sh

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
BOLD='\033[1m'
NC='\033[0m' # No Color

# Function to print step headers
print_step() {
    echo ""
    echo "${BLUE}${BOLD}═══════════════════════════════════════════════════════════════${NC}"
    echo "${BLUE}${BOLD}  $1${NC}"
    echo "${BLUE}${BOLD}═══════════════════════════════════════════════════════════════${NC}"
    echo ""
}

# Function to print success message
print_success() {
    echo "${GREEN}${BOLD}✓ $1${NC}"
}

# Function to print error message and exit
print_error() {
    echo "${RED}${BOLD}✗ $1${NC}"
    exit 1
}

# Function to run command with error handling
run_command() {
    local cmd="$1"
    local description="$2"

    echo "${YELLOW}→ Running: ${cmd}${NC}"

    if $cmd; then
        print_success "$description completed successfully"
    else
        print_error "$description failed"
    fi
}

# Non-fatal variant: warns on failure but does not exit. Used for the
# wiki sync/build/publish trio so a wiki hiccup never invalidates a
# PyPI release that is already live.
run_command_soft() {
    local cmd="$1"
    local description="$2"

    echo "${YELLOW}→ Running: ${cmd}${NC}"

    if $cmd; then
        print_success "$description completed successfully"
    else
        echo "${YELLOW}${BOLD}⚠ $description failed (continuing)${NC}"
    fi
}

echo "${BOLD}${BLUE}"
echo "███████╗███████╗███╗   ███╗ █████╗  ██████╗██╗     ██╗"
echo "██╔════╝██╔════╝████╗ ████║██╔══██╗██╔════╝██║     ██║"
echo "███████╗█████╗  ██╔████╔██║███████║██║     ██║     ██║"
echo "╚════██║██╔══╝  ██║╚██╔╝██║██╔══██║██║     ██║     ██║"
echo "███████║███████╗██║ ╚═╝ ██║██║  ██║╚██████╗███████╗██║"
echo "╚══════╝╚══════╝╚═╝     ╚═╝╚═╝  ╚═╝ ╚═════╝╚══════╝╚═╝"
echo "${NC}"
echo "${BOLD}Starting Package Publishing Process...${NC}"

print_step "1/12 Cleaning Previous Build"
run_command "pdm run clean" "Clean"

print_step "2/12 Installing Dependencies"
run_command "pdm run install" "Dependencies installation"

print_step "3/12 Installing Development Dependencies"
run_command "pdm run install-dev" "Development dependencies installation"

print_step "4/12 Code Linting"
run_command "pdm run lint" "Linting"

print_step "5/12 Type Checking"
run_command "pdm run typecheck" "Type checking"

print_step "6/12 Running Tests"
run_command "pdm run test-quick" "Tests"

print_step "7/12 Bumping Version"
run_command "pdm run version-patch" "Version bump"

print_step "8/12 Building Package"
run_command "pdm build" "Package build"

print_step "9/12 Publishing Package"
run_command "pdm publish" "Package publishing"

# ── Kenboard wiki sync / build / publish ─────────────────────────────────
# Run AFTER PyPI publish so a wiki hiccup never invalidates a live release.
# Non-fatal (run_command_soft): a missing `ken` or kenboard checkout warns
# but does not abort the script.

print_step "10/12 Wiki sync (kenboard tasks → kenboard/wiki/)"
run_command_soft "ken wiki sync" "Wiki sync"

print_step "11/12 Wiki build (kenboard/wiki/ → kenboard/wiki-html/)"
run_command_soft "ken wiki build" "Wiki build"

print_step "12/12 Wiki publish (commit wiki-html to angel SVN)"
# kenboard/wiki-html lives in the angel SVN tree, not in this checkout.
# We commit from /Users/q/Projects/2113.ch (the angel working copy) when
# available; otherwise warn and skip.
ANGEL_WC="/Users/q/Projects/2113.ch"
if [ -d "$ANGEL_WC/.svn" ] && [ -d "$ANGEL_WC/kenboard/wiki-html" ]; then
    run_command_soft \
        "svn commit $ANGEL_WC/kenboard/wiki-html -m 'wiki: sync after semacli release'" \
        "Wiki SVN commit"
else
    echo "${YELLOW}${BOLD}⚠ angel SVN checkout not found at $ANGEL_WC — wiki not committed${NC}"
fi

echo ""
echo "${GREEN}${BOLD}🎉 PUBLISHING COMPLETED SUCCESSFULLY! 🎉${NC}"
echo "${GREEN}${BOLD}═══════════════════════════════════════════════════════════════${NC}"
echo "${GREEN}Your semacli package has been successfully published!${NC}"
echo "${GREEN}Kenboard wiki sync/build/publish ran in non-fatal mode after.${NC}"
echo ""
