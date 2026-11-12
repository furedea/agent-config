package fixture

import "testing"

func TestBare(t *testing.T) {
	t.Skip("broken")
}

func TestFixLater(t *testing.T) {
	t.Skip("flaky, fix later")
}

func TestKnownBug(t *testing.T) {
	t.Skipf("known bug in %s", "the parser")
}

func TestCommentWithoutCondition(t *testing.T) {
	// TODO: this fails.
	t.Skip("known defect")
}

func TestSkipNow(t *testing.T) {
	// broken
	t.SkipNow()
}

func (s *Suite) TestSuiteSkip() {
	s.T().Skip("broken")
}

func TestTracked(t *testing.T) {
	t.Skip("known bug, tracked in #123")
}

func TestUnstable(t *testing.T) {
	// Fails since the last refactor.
	t.Skip("known defect in the importer")
}
