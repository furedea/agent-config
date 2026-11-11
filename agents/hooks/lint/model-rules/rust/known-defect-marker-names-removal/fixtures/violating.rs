#[test]
#[ignore]
fn bare() {
    assert_eq!(1, 2);
}

#[test]
#[ignore = "broken"]
fn broken() {
    assert_eq!(1, 2);
}

#[test]
#[ignore = "fix later"]
fn fix_later() {
    assert_eq!(1, 2);
}

#[test]
// TODO: this fails.
#[ignore = "known defect"]
fn comment_without_condition() {
    assert_eq!(1, 2);
}

#[test]
#[cfg_attr(target_os = "windows", ignore = "broken")]
fn conditional() {
    assert_eq!(1, 2);
}
