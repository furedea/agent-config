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
