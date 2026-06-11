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

print_step "1/13 Cleaning Previous Build"
run_command "pdm run clean" "Clean"

print_step "2/13 Installing Dependencies"
run_command "pdm run install" "Dependencies installation"

print_step "3/13 Installing Development Dependencies"
run_command "pdm run install-dev" "Development dependencies installation"

print_step "4/13 Code Linting"
run_command "pdm run lint" "Linting"

print_step "5/13 Type Checking"
run_command "pdm run typecheck" "Type checking"

print_step "6/14 Running Tests (unit + integration, with coverage)"
# Full suite with coverage: the quality-metrics gate (step 8) reads the
# .coverage file this run leaves behind.
run_command "pdm run test" "Tests (full suite, coverage)"

print_step "7/14 Running Integration Tests (VCR strict replay)"
# --vcr-record=none is hard-coded in the test-integration script: a stale
# cassette aborts the release rather than silently re-recording against
# whatever Semaphore happens to be reachable from the build machine.
run_command "pdm run test-integration" "Integration tests (replay)"

# Blocking quality-metrics gate (ken #828): absolute ceilings + best-ever
# ratchet against doc/quality-history.csv — see doc/code-quality.md.
print_step "8/14 Quality Metrics Gate"
run_command "pdm run metrics-gate" "Quality metrics gate"

# Push the (already committed) work so the GitHub CI runs the SonarCloud
# analysis of HEAD, then block on the quality gate (ken #835, same pattern
# as kenboard). 900s: the CI takes ~4-5 min to produce the analysis.
print_step "9/16 Pushing Code for SonarCloud Analysis"
run_command "git push" "Push for analysis"

print_step "10/16 SonarCloud Quality Gate"
run_command "pdm run sonar-gate" "SonarCloud quality gate"

print_step "11/16 Bumping Version"
run_command "pdm run version-patch" "Version bump"

print_step "12/16 Building Package"
run_command "pdm build" "Package build"

print_step "13/16 Publishing Package"
run_command "pdm publish" "Package publishing"

# ── Kenboard wiki sync / build / publish ─────────────────────────────────
# Run AFTER PyPI publish so a wiki hiccup never invalidates a live release.
# Non-fatal (run_command_soft): a missing `ken` or kenboard checkout warns
# but does not abort the script.

print_step "14/16 Wiki sync (kenboard tasks → wiki/)"
run_command_soft "ken wiki sync" "Wiki sync"

print_step "15/16 Wiki build (wiki/ → wiki-html/)"
run_command_soft "ken wiki build" "Wiki build"

# ── Git commit + push ────────────────────────────────────────────────────
# Captures the version bump (step 8), the regenerated wiki/ + wiki-html/
# (steps 11-12), and any other tracked changes still in the working tree.
# Non-fatal: PyPI is already updated, so a git hiccup must not abort the
# script — the operator pushes manually.
print_step "16/16 Git commit + push (release artifacts)"
VERSION=$(grep '^__version__' semacli/__init__.py | cut -d'"' -f2)
COMMIT_MSG="release: v${VERSION} — auto by publish.sh"
echo "${YELLOW}→ Running: git add -A && git commit -m \"${COMMIT_MSG}\" && git push${NC}"
if git add -A && git diff --cached --quiet; then
    echo "${YELLOW}${BOLD}⚠ Nothing to commit (working tree already clean)${NC}"
elif git commit -m "$COMMIT_MSG"; then
    print_success "Git commit completed (${COMMIT_MSG})"
    if git push; then
        print_success "Git push completed"
    else
        echo "${YELLOW}${BOLD}⚠ Git push failed — PyPI is live, push v${VERSION} manually${NC}"
    fi
else
    echo "${YELLOW}${BOLD}⚠ Git commit failed — fix and push v${VERSION} manually${NC}"
fi

echo ""
echo "${GREEN}${BOLD}🎉 PUBLISHING COMPLETED SUCCESSFULLY! 🎉${NC}"
echo "${GREEN}${BOLD}═══════════════════════════════════════════════════════════════${NC}"
echo "${GREEN}semacli v${VERSION} has been published to PyPI.${NC}"
echo "${GREEN}Wiki sync + build + git push ran in non-fatal mode after.${NC}"
echo ""
