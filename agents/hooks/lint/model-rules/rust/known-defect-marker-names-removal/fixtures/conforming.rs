// Remove when the parser handles empty input (#123).
#[test]
#[ignore]
fn comment_names_condition() {
    assert_eq!(1, 2);
}

#[test]
#[ignore = "known defect: remove once upstream 1.4 ships the fix"]
fn reason_names_condition() {
    assert_eq!(1, 2);
}

#[test]
#[ignore = "needs a running database"]
fn needs_database() {
    assert_eq!(1, 1);
}

#[test]
#[ignore = "slow"]
fn slow() {
    assert_eq!(1, 1);
}
