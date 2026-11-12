package fixture

import (
	"os"
	"runtime"
	"testing"
)

func TestCommentNamesCondition(t *testing.T) {
	// Remove when the parser handles empty input (#123).
	t.Skip("known defect in the parser")
}

func TestMessageNamesCondition(t *testing.T) {
	t.Skip("known defect: remove once upstream v1.4 ships the fix")
}

func TestNeedsDocker(t *testing.T) {
	if os.Getenv("DOCKER_HOST") == "" {
		t.Skip("requires a running docker daemon")
	}
}

func TestShortMode(t *testing.T) {
	if testing.Short() {
		t.Skip("short mode")
	}
}

func TestAfterRewrite(t *testing.T) {
	t.Skip("known defect, skipped until the cache rewrite lands")
}

func TestPlatformGap(t *testing.T) {
	// Windows has no symlink support here; enable the test when the sandbox runs on Linux only.
	t.Skip("symlinks are unsupported on this platform")
}

func TestNeedsNewerToolchain(t *testing.T) {
	if runtime.Version() < "go1.23" {
		t.Skipf("needs the range-over-func iterators of go1.23, running %s", runtime.Version())
	}
}

func TestUntilRelease(t *testing.T) {
	// The upstream bug is tracked in #88; this stays skipped until the v2 client release that carries its fix.
	t.Skip("upstream client drops the last frame")
}
