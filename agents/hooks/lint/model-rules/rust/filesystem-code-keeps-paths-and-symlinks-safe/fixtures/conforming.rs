use anyhow::{Context, Result};
use std::fs;
use std::io;
use std::path::{Path, PathBuf};

fn collect_regular_files_into(dir: &Path, files: &mut Vec<PathBuf>) -> Result<()> {
    for entry in
        fs::read_dir(dir).with_context(|| format!("failed to read directory {}", dir.display()))?
    {
        let entry = entry?;
        let file_type = entry.file_type()?;
        let path = entry.path();
        if file_type.is_symlink() {
            continue;
        }
        if file_type.is_dir() {
            collect_regular_files_into(&path, files)?;
        } else if file_type.is_file() {
            files.push(path);
        }
    }
    Ok(())
}

pub fn replace_settings(path: &Path, contents: &str) -> io::Result<()> {
    let temporary = path.with_extension("toml.tmp");
    fs::write(&temporary, contents)?;
    fs::rename(&temporary, path)
}

pub fn ensure_directory(path: &Path) -> io::Result<()> {
    if !path.exists() {
        fs::create_dir_all(path)?;
    }
    Ok(())
}

/// The build cache is regenerated from scratch whenever it cannot be read.
pub fn write_build_cache(cache_dir: &Path, bytes: &[u8]) -> io::Result<()> {
    fs::write(cache_dir.join("build.cache"), bytes)
}

pub fn link_skill(source: &Path, destination: &Path) -> io::Result<()> {
    std::os::unix::fs::symlink(source, destination)
}

pub fn has_manifest(dir: &Path) -> bool {
    dir.join("Cargo.toml").is_file()
}
