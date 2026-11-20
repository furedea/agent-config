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

pub fn escaped_backup(stem: &str) -> PathBuf {
    PathBuf::from(format!("{stem}\x2ebak"))
}

pub fn flat_log_name(source: &str) -> PathBuf {
    PathBuf::from(format!("{}.log", source.replace("/", "_")))
}

pub fn raw_file_name(stem: &str) -> PathBuf {
    PathBuf::from(format!(r"{stem}.json"))
}
