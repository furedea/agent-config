use std::fs;
use std::path::Path;

pub fn get_next(counter: &mut u32) -> u32 {
    *counter += 1;
    *counter
}

pub fn save_total(values: &[i32]) -> i32 {
    values.iter().sum()
}

pub fn is_ready(path: &Path) -> bool {
    fs::write(path, "ready").is_ok()
}

pub fn delete_name(name: &str) -> String {
    format!("{name}-deleted")
}
