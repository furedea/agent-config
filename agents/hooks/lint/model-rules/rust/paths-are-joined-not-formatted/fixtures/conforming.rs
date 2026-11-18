use std::path::{Path, PathBuf};

pub fn module_file(stem: &str) -> PathBuf {
    PathBuf::from(format!("{stem}.rs"))
}

pub fn temporary_file(dir: &Path, name: &str) -> PathBuf {
    dir.join(PathBuf::from(format!("{name}.tmp")))
}

pub fn release_dir(root: &Path, name: &str, version: &str) -> PathBuf {
    root.join(PathBuf::from(format!("{name}-{version}")))
}

pub fn backup_name(stem: &str) -> PathBuf {
    Path::new(&(stem.to_owned() + ".bak")).to_path_buf()
}

pub fn major_dir(major: u32) -> PathBuf {
    PathBuf::from(format!("v{major}"))
}
