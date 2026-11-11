package fixture

import (
	"os"
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
