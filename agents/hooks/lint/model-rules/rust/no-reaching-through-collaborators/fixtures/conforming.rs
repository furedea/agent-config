use std::path::Path;
use std::process::{Command, Output};

pub fn active_names(users: &[User]) -> Vec<String> {
    users
        .iter()
        .filter(|user| user.active)
        .map(|user| user.name.clone())
        .collect()
}

pub fn git_status(dir: &Path) -> std::io::Result<Output> {
    Command::new("git")
        .arg("status")
        .arg("--short")
        .current_dir(dir)
        .output()
}

pub fn arguments() -> Vec<String> {
    std::env::args().skip(1).collect()
}

pub fn file_label(path: &Path) -> String {
    path.file_name()
        .unwrap_or_default()
        .to_string_lossy()
        .into_owned()
}

/// `PageResponse` is the deserialized JSON body of the list endpoint, a plain record.
pub fn item_count(response: &PageResponse) -> usize {
    response.body.data.items.len()
}

pub struct Cache {
    entries: Entries,
}

impl Cache {
    pub fn size(&self) -> usize {
        self.entries.map.values().len()
    }
}
