use std::path::PathBuf;

#[derive(Debug, Default)]
pub struct Options {
    pub verbose: bool,
    pub jobs: usize,
}

#[derive(Debug)]
pub struct Report {
    pub passed: usize,
    pub failed: usize,
    pub skipped: usize,
}

#[derive(Debug, Clone, Copy)]
pub struct Point {
    pub x: f64,
    pub y: f64,
}

#[derive(Debug)]
pub(crate) struct Row {
    pub(crate) cells: Vec<String>,
}

#[derive(Debug, serde::Deserialize)]
pub struct Config {
    pub name: String,
    pub paths: Vec<PathBuf>,
}
