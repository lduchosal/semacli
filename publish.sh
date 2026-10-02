#!/bin/sh

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
BOLD='\033[1m'
NC='\033[0m' # No Color

# Parse command line arguments (ported from kenboard publish.sh, ken #997)
QUALITY_ONLY=false
BUMP_TYPE="patch"
for arg in "$@"; do
    case $arg in
        --quality)
            QUALITY_ONLY=true
            shift
            ;;
        --major)
            BUMP_TYPE="major"
            shift
            ;;
        --minor)
            BUMP_TYPE="minor"
            shift
            ;;
        --patch)
            BUMP_TYPE="patch"
            shift
            ;;
        -h|--help)
            echo "Usage: $0 [--quality] [--major|--minor|--patch] [--help]"
            echo ""
            echo "Options:"
            echo "  --quality       Run only quality checks without publishing"
            echo "  --major         Bump major version (x.0.0)"
            echo "  --minor         Bump minor version (0.x.0)"
            echo "  --patch         Bump patch version (0.0.x) [default]"
            echo "  --help          Show this help message"
            exit 0
            ;;
        *)
            echo "Unknown argument: $arg"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

# Set total steps based on mode (one per print_step call):
#   18 = 15 Python gates + 3 VS Code extension gates (ken #1131)
#   +10 publish-only: push, sonar gate, bump, build, .vsix, PyPI, wiki sync,
#       wiki build, git commit + push, tag + GitHub release
if [ "$QUALITY_ONLY" = true ]; then
    STEPS=18
else
    STEPS=28
fi
STEP=0

# Function to print step headers (auto-incrementing counter, kenboard style)
print_step() {
    STEP=$((STEP + 1))
    echo ""
    echo "${BLUE}${BOLD}═══════════════════════════════════════════════════════════════${NC}"
    echo "${BLUE}${BOLD}  $STEP/$STEPS $1${NC}"
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

    if eval "$cmd"; then
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

    if eval "$cmd"; then
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
if [ "$QUALITY_ONLY" = true ]; then
    echo "${BOLD}Starting Quality Checks...${NC}"
else
    echo "${BOLD}Starting Package Publishing Process...${NC}"
fi

print_step "Cleaning Previous Build"
run_command "pdm run clean" "Clean"

print_step "Installing Dependencies"
run_command "pdm run install" "Dependencies installation"

print_step "Installing Development Dependencies"
run_command "pdm run install-dev" "Development dependencies installation"

# Dependency freshness (ken #997): pdm.lock is gitignored, so the GitHub CI
# resolves dependencies fresh on every run while the local venv stays at
# whatever was last locked. Updating HERE — before the gates — means every
# release is validated against the same versions the CI will get (the ruff
# 0.15→0.16 drift shipped v0.5.25 green locally and red in CI).
print_step "Checking for Outdated Dependencies"
run_command "pdm outdated" "Outdated dependencies report"

print_step "Updating Dependencies"
run_command "pdm update" "Dependencies update"

print_step "Format Check (black)"
run_command "pdm run format-check" "Format check"

print_step "Linting (ruff)"
run_command "pdm run lint" "Linting"

print_step "Import Architecture (lint-imports)"
run_command "pdm run arch" "Import architecture check"

print_step "Type Checking (mypy)"
run_command "pdm run typecheck" "Type checking"

print_step "Docstring Coverage (interrogate)"
run_command "pdm run interrogate" "Docstring coverage"

print_step "Code Quality Check (refurb)"
run_command "pdm run refurb" "Code quality check"

print_step "Dead Code Check (vulture)"
run_command "pdm run vulture" "Dead code check"

print_step "Running Tests (unit + integration, with coverage)"
# Full suite with coverage: the quality-metrics gate below reads the
# .coverage file this run leaves behind.
run_command "pdm run test" "Tests (full suite, coverage)"

print_step "Running Integration Tests (VCR strict replay)"
# --vcr-record=none is hard-coded in the test-integration script: a stale
# cassette aborts the release rather than silently re-recording against
# whatever Semaphore happens to be reachable from the build machine.
run_command "pdm run test-integration" "Integration tests (replay)"

# VS Code extension (ken #1131): own npm toolchain under vscode/. npm ci
# from the committed lockfile, then a blocking audit — a known vulnerability
# in the toolchain stops the release (bump the dependency, don't ignore it).
print_step "Installing VS Code Extension Dependencies (npm ci)"
run_command "pdm run vscode-install" "VS Code extension dependencies"

print_step "VS Code Extension Security Audit (npm audit)"
run_command "pdm run vscode-audit" "VS Code extension security audit"

print_step "VS Code Extension: lint + type check + tests (coverage gate)"
run_command "pdm run vscode-lint" "VS Code extension lint + format (biome)"
run_command "pdm run vscode-typecheck" "VS Code extension type check (tsc)"
run_command "pdm run vscode-test" "VS Code extension tests + coverage"

# Blocking quality-metrics gate (ken #828): absolute ceilings + best-ever
# ratchet against doc/quality-history.csv — see doc/code-quality.md.
print_step "Quality Metrics Gate"
run_command "pdm run metrics-gate" "Quality metrics gate"

# Exit here if --quality flag is set
if [ "$QUALITY_ONLY" = true ]; then
    echo ""
    echo "${GREEN}${BOLD}🎉 QUALITY CHECKS COMPLETED SUCCESSFULLY! 🎉${NC}"
    echo "${GREEN}${BOLD}═══════════════════════════════════════════════════════════════${NC}"
    echo "${GREEN}All quality checks have passed.${NC}"
    echo ""
    exit 0
fi

# Push the (already committed) work so the GitHub CI runs the SonarCloud
# analysis of HEAD, then block on the quality gate (ken #835, same pattern
# as kenboard). 900s: the CI takes ~4-5 min to produce the analysis.
print_step "Pushing Code for SonarCloud Analysis"
run_command "git push" "Push for analysis"

print_step "SonarCloud Quality Gate"
run_command "pdm run sonar-gate" "SonarCloud quality gate"

print_step "Bumping Version (${BUMP_TYPE})"
run_command "pdm run version-${BUMP_TYPE}" "Version bump"
VERSION=$(grep '^__version__' semacli/__init__.py | cut -d'"' -f2)
# The .vsix carries the semacli release it was built with (ken #1131).
# `"version"` is the only such key in vscode/package.json (guarded by
# tests/unit/test_vscode_extension.py); portable sed (BSD + GNU).
sed -i.bak 's/"version": "[^"]*"/"version": "'"${VERSION}"'"/' vscode/package.json && rm vscode/package.json.bak
grep -q "\"version\": \"${VERSION}\"" vscode/package.json || print_error "vscode/package.json not synced to ${VERSION}"
print_success "Version ${VERSION} synced to vscode/package.json"

print_step "Building Package"
run_command "pdm build" "Package build"

# Packaged BEFORE the PyPI upload: a vsce failure aborts while nothing is
# live yet. vsce names the file after vscode/package.json's version.
print_step "Packaging VS Code Extension (.vsix)"
VSIX="vscode/semacli-vscode-${VERSION}.vsix"
rm -f vscode/*.vsix
run_command "pdm run vscode-package" "VS Code extension package"
[ -f "${VSIX}" ] || print_error "vsce did not produce ${VSIX}"

print_step "Publishing Package"
run_command "pdm publish" "Package publishing"

# ── Kenboard wiki sync / build / publish ─────────────────────────────────
# Run AFTER PyPI publish so a wiki hiccup never invalidates a live release.
# Non-fatal (run_command_soft): a missing `ken` or kenboard checkout warns
# but does not abort the script.

print_step "Wiki sync (kenboard tasks → wiki/)"
run_command_soft "ken wiki sync" "Wiki sync"

print_step "Wiki build (wiki/ → wiki-html/)"
run_command_soft "ken wiki build" "Wiki build"

# ── Git commit + push ────────────────────────────────────────────────────
# Captures the version bump, the regenerated wiki/ + wiki-html/, and any
# other tracked changes still in the working tree. Non-fatal: PyPI is
# already updated, so a git hiccup must not abort the script — the
# operator pushes manually.
print_step "Git commit + push (release artifacts)"
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

# ── Tag + GitHub release with the VS Code extension (ken #1131) ──────────
# PyPI is live by now: stop on error, but print the exact recovery command.
# The tag must point at the release commit — the git step above is soft, so
# check HEAD before tagging. Idempotent: an existing release (re-run) gets
# the asset re-uploaded with --clobber.
print_step "Tag semacli-${VERSION} + GitHub Release (.vsix)"
TAG="semacli-${VERSION}"
RECOVER="git tag ${TAG} && git push origin ${TAG} && gh release create ${TAG} --verify-tag --title 'semacli ${VERSION}' --generate-notes ${VSIX}"
[ "$(git log -1 --format=%s)" = "${COMMIT_MSG}" ] \
    || print_error "HEAD is not the release commit — recover by hand: ${RECOVER}"
command -v gh > /dev/null 2>&1 || print_error "gh CLI not found — recover: ${RECOVER}"
git rev-parse -q --verify "refs/tags/${TAG}" > /dev/null || run_command "git tag ${TAG}" "Git tag ${TAG}"
run_command "git push origin ${TAG}" "Push tag ${TAG}"
if gh release view "${TAG}" > /dev/null 2>&1; then
    run_command "gh release upload ${TAG} ${VSIX} --clobber" "Attach $(basename "${VSIX}") to ${TAG}"
else
    run_command "gh release create ${TAG} --verify-tag --title 'semacli ${VERSION}' --generate-notes ${VSIX}" \
        "GitHub release ${TAG} with $(basename "${VSIX}")"
fi

echo ""
echo "${GREEN}${BOLD}🎉 PUBLISHING COMPLETED SUCCESSFULLY! 🎉${NC}"
echo "${GREEN}${BOLD}═══════════════════════════════════════════════════════════════${NC}"
echo "${GREEN}semacli v${VERSION} has been published to PyPI.${NC}"
echo "${GREEN}GitHub release semacli-${VERSION} carries semacli-vscode-${VERSION}.vsix.${NC}"
echo "${GREEN}Wiki sync + build + git push ran in non-fatal mode after.${NC}"
echo ""
