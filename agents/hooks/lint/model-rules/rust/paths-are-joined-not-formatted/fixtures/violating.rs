use std::path::{Path, PathBuf};

pub fn skill_path(root: &Path, name: &str) -> PathBuf {
    PathBuf::from(format!("{}/{}", root.display(), name))
}

pub fn config_file(home: &str, app: &str) -> PathBuf {
    PathBuf::from(format!("{home}/.config/{app}/config.toml"))
}

pub fn report_path(dir: &str, file: &str) -> PathBuf {
    Path::new(&(dir.to_string() + "/" + file)).to_path_buf()
}

pub fn windows_target(drive: &str, file: &str) -> PathBuf {
    PathBuf::from(format!("{drive}\\{file}"))
}

pub fn nested_log(base: String, year: u32, month: u32) -> PathBuf {
    PathBuf::from(base + &format!("/logs/{year}/{month:02}.log"))
}
