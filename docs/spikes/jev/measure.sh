#!/usr/bin/env bash
# Measure jev-lint and jevlint on the spike rules and examples with one model (issue #75).
#
# Usage (from the repository root, with TYPESAFE_API_KEY in the environment):
#   op run --environment <1Password Environment ID> -- bash docs/spikes/jev/measure.sh
#
# The key is only checked for presence and never printed. Nothing is installed globally: jev-lint
# runs through `nix shell` + `npx` with a pinned version, jevlint is built into a temporary directory.
# Results: results/run.log and results/raw/ (committed; score them with analyze_results.py), plus
# results/{jev_lint,jevlint}.jsonl, a per-judgement view that is regenerated on each run.
set -euo pipefail

readonly JEVLINT_VERSION="v0.4.0"
readonly JEV_LINT_VERSION="0.7.0"
readonly MODEL="${JEV_MODEL:-jev-latest}"

spike_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly spike_dir

if [[ -z "${TYPESAFE_API_KEY:-}" ]]; then
  echo "error: TYPESAFE_API_KEY is not set in the environment (its value is never printed)" >&2
  exit 2
fi

work="$(mktemp -d "${TMPDIR:-/tmp}/jev-spike.XXXXXX")"
readonly work
mkdir -p "$work/bin" "$spike_dir/results"
echo "work directory: $work"

# Same model and provider for both tools.
export JEV_LINT_MODEL="$MODEL"
export TYPESAFE_DEFAULT_MODEL="$MODEL"
export JEVLINT_PROVIDER="typesafe"
export npm_config_cache="$work/npm-cache"

build_jevlint() {
  GOBIN="$work/bin" GOPATH="$work/gopath" CGO_ENABLED=1 CC="${CC:-/usr/bin/clang}" \
    nix shell nixpkgs#go -c go install "github.com/codegirl-007/jevlint/cmd/jevlint@${JEVLINT_VERSION}"
}

warm_up_jev_lint() {
  # Only the fetch matters; jev-lint has no --version flag and may exit non-zero on usage output.
  nix shell nixpkgs#nodejs_24 nixpkgs#ast-grep -c npx -y "jev-lint@${JEV_LINT_VERSION}" --help >/dev/null 2>&1 || true
}

echo "building jevlint ${JEVLINT_VERSION} (system clang; the Nix clang lacks -lresolv)"
build_jevlint
"$work/bin/jevlint" version
echo "fetching jev-lint ${JEV_LINT_VERSION}"
warm_up_jev_lint

echo "running measurements with model ${MODEL}"
python3 -I "$spike_dir/measure_runner.py" --work "$work" --model "$MODEL"
echo "done: $spike_dir/results/"
