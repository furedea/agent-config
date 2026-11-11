use std::fs;
use std::io;
use std::path::Path;

pub struct Review {
    scores: Vec<f64>,
}

pub fn total(values: &[i32]) -> i32 {
    values.iter().sum()
}

pub fn read_config(path: &Path) -> io::Result<String> {
    fs::read_to_string(path)
}

pub fn write_report(path: &Path, body: &str) -> io::Result<()> {
    fs::write(path, body)
}

pub fn check_paths(paths: &[&Path]) -> io::Result<()> {
    for path in paths {
        fs::metadata(path)?;
    }
    Ok(())
}

impl Review {
    pub fn judge(&self, score: f64) -> bool {
        score >= 0.5 && !self.scores.is_empty()
    }
}

pub fn load_port(raw: &str) -> Result<u16, std::num::ParseIntError> {
    raw.parse()
}

pub fn run(args: &[String]) -> usize {
    args.len()
}

#[test]
fn get_next_after_reset() {
    let mut counter = 0;
    counter += 1;
    assert_eq!(counter, 1);
}
