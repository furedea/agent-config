"""Source samples whose selected subjects tests/test_model_rule_files.py counts per language."""

PYTHON_SOURCE = """\
import pytest


def get_user(users):
    users.clear()
    return users


def load(path):
    if not path:
        raise ValueError("bad")
    return path


def pure(a, b):
    return a + b


# Removed when the parser handles empty input (#123).
@pytest.mark.xfail(strict=True, reason="empty input")
def test_known_defect():
    assert False
"""

TYPESCRIPT_SOURCE = """\
function getUser(users: string[]): string[] {
  users.length = 0;
  return users;
}

function load(path: string): string {
  if (!path) {
    throw new Error("bad");
  }
  return path;
}

function pure(a: number, b: number): number {
  return a + b;
}

// Removed when the parser handles empty input (#123).
test.fails("known defect", () => {});

type Request = { readonly url: string; readonly retries?: number };
const parsed = JSON.parse("{}") as Request;
const levels = ["low", "high"] as const;
const typed = <Request>JSON.parse("{}");

function stamp(): number {
  // The clock is read here on purpose.
  return Date.now();
}

describe("stamp", () => {
  it("returns a number", () => {});
});
describe.each([1, 2])("stamp table", () => {
  it("returns a number", () => {});
});
describe.concurrent("stamp again", () => {
  it("returns a number", () => {});
});

vi.mock("./sibling");
vi.doMock("./other");
it.concurrent("first case", () => {});
it.concurrent("second case", () => {});

const expiresAt = () => Date.now() + 1000;
const nonce = () => randomBytes(8);

class Loader {
  load = (path: string): string => {
    if (!path) throw new Error("missing");
    return path;
  };
}

register("/item", () => {
  throw new Error("missing");
});

function makeHandler(): () => void {
  return () => {
    throw new Error("missing");
  };
}

function makeSource(): () => Generator<number> {
  return function* () {
    throw new Error("missing");
  };
}

const loadLater = function (path: string): string {
  if (!path) throw new Error("missing");
  return path;
};

export default () => {
  throw new Error("no default handler");
};

const handlers = {
  open: () => Date(),
  reject: (id: string) => Promise.reject(new Error(`load item ${id}: missing`)),
};

const startedAt = () => new Date;

const pick = handlers
  ? () => {
      // The first handler wins.
      return 1;
    }
  : undefined;

suite("parse", () => {
  it("reads one", () => {});
});

class LoadState {
  isLoading = false;
  data?: string;
}
"""


GO_SOURCE = """\
package sample

import (
	"errors"
	"testing"
)

func GetUser(users []string) []string {
	users = users[:0]
	return users
}

func Load(path string) (string, error) {
	if path == "" {
		return "", errors.New("bad")
	}
	return path, nil
}

func Pure(a, b int) int {
	return a + b
}

func TestLoad(t *testing.T) {
	// Removed when the parser handles empty input (#123).
	t.Skip("known defect")
}

func TestBare(t *testing.T) {
	// broken
	t.SkipNow()
}

func (s *Suite) TestSuiteSkip() {
	s.T().Skip("broken")
}

func (c *Client) TestEnabled() bool {
	c.enabled = true
	return c.enabled
}

func main() {}

func Start(ch chan int) {
	go func() { close(ch) }()
	panic("unreachable")
}

func Report(logger Logger, err error) error {
	logger.Errorf("load: %v", err)
	return err
}
"""

RUST_SOURCE = """\
use anyhow::{bail, Context, Result};

pub fn get_user(users: &mut Vec<String>) -> usize {
    users.clear();
    users.len()
}

pub fn load(path: &str) -> Result<String> {
    if path.is_empty() {
        bail!("bad");
    }
    Ok(path.to_string())
}

pub fn pure(a: i32, b: i32) -> i32 {
    a + b
}

pub fn read(path: &str) -> Result<String> {
    std::fs::read_to_string(path).context("failed")
}

pub fn qualify(path: &str) -> anyhow::Result<String> {
    if path.is_empty() {
        anyhow::bail!("bad");
    }
    Ok(path.to_string())
}

#[cfg(not(test))]
pub fn get_connection(pool: &mut Vec<u8>) -> usize {
    pool.clear();
    pool.len()
}

// Removed when the parser handles empty input (#123).
#[test]
/* regression */
#[ignore]
fn known_defect() {
    assert_eq!(1, 2);
}

#[test]
#[cfg_attr(target_os = "windows", ignore = "broken")]
fn conditional_defect() {
    assert_eq!(1, 2);
}

#[test]
#[cfg_attr(
    target_os = "windows",
    ignore = "broken"
)]
fn wrapped_defect() {
    assert_eq!(1, 2);
}

#[cfg_attr(target_os = "linux", test)]
fn get_conditional_test(pool: &mut Vec<u8>) {
    pool.clear();
}

#[test]
#[cfg_attr(feature = "ignore", should_panic)]
fn feature_named_ignore() {
    assert_eq!(1, 1);
}

#[cfg_attr(ignore, test)]
fn condition_named_ignore() {
    assert_eq!(1, 1);
}

#[cfg_attr(feature = "tokio", tokio::test(flavor = "multi_thread"))]
fn argumented_conditional_test() {
    assert_eq!(1, 1);
}

#[cfg_attr(
    feature = "tokio",
    tokio::test(flavor = "multi_thread")
)]
fn wrapped_argumented_test() {
    assert_eq!(1, 1);
}

#[cfg_attr(any(unix, ignore = "ci"), should_panic)]
fn nested_condition_names_ignore() {
    assert_eq!(1, 1);
}

#[test]
#[cfg_attr(unix, ignore)]
fn bare_conditional_ignore() {
    assert_eq!(1, 2);
}

pub fn lookup(map: &Map, key: &str) -> Result<u8, &'static str> {
    map.get(key).ok_or("missing")
}

pub fn lookup_named(map: &Map, key: &str) -> Result<u8, String> {
    map.get(key).ok_or_else(|| format!("read {key}: missing"))
}

pub fn convert(raw: &str) -> Result<u8, String> {
    raw.parse().map_err(|e| format!("parse {raw}: {e}"))
}

pub fn keep_error(map: &Map, key: &str, err: Error) -> Result<u8, Error> {
    map.get(key).ok_or(err)
}

pub fn convert_plain(raw: &str) -> Result<u8, Error> {
    raw.parse().map_err(From::from)
}
"""
