use anyhow::{anyhow, bail, Result};

pub fn validate(name: &str) -> Result<(), String> {
    if name.is_empty() {
        return Err("invalid".into());
    }
    Ok(())
}

pub fn open(path: &str) -> Result<String> {
    if path.is_empty() {
        bail!("failed");
    }
    Ok(path.to_string())
}

pub fn parse(raw: &str) -> Result<u16> {
    if raw.is_empty() {
        return Err(anyhow!("config"));
    }
    Ok(raw.len() as u16)
}

pub fn load(path: &str) -> Result<String> {
    if path.is_empty() {
        bail!("parse");
    }
    Ok(path.to_string())
}
