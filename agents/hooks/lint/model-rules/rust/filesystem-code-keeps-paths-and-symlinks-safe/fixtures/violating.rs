use std::fs::{self, File};
use std::io::{self, Write};
use std::path::{Path, PathBuf};

/// The lockfile pins every dependency; a project cannot build without a readable one.
pub fn write_lockfile(path: &Path, lock: &Lock) -> io::Result<()> {
    fs::write(path, lock.render())
}

pub fn collect_skills(dir: &Path, found: &mut Vec<PathBuf>) -> io::Result<()> {
    for entry in fs::read_dir(dir)? {
        let path = entry?.path();
        if path.is_dir() {
            collect_skills(&path, found)?;
        } else {
            found.push(path);
        }
    }
    Ok(())
}

pub fn save_settings(path: &Path, settings: &Settings) -> io::Result<()> {
    let mut file = File::create(path)?;
    file.write_all(settings.to_toml().as_bytes())?;
    Ok(())
}

pub fn back_up(dir: &str, name: &str) -> io::Result<u64> {
    fs::copy(format!("{dir}/{name}"), format!("{dir}/{name}.bak"))
}
