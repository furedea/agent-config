use anyhow::{anyhow, bail, Context, Result};

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

pub fn read(path: &str) -> Result<String> {
    std::fs::read_to_string(path).context("failed")
}

pub fn find(map: &std::collections::HashMap<String, u16>, key: &str) -> Result<u16, &'static str> {
    map.get(key).copied().ok_or("missing")
}

pub fn lookup(map: &std::collections::HashMap<String, u16>, key: &str) -> Result<u16, String> {
    map.get(key)
        .copied()
        .ok_or_else(|| format!("no entry for {key}"))
}

pub fn convert(raw: &str) -> Result<u16, String> {
    raw.parse::<u16>().map_err(|_| "bad number".to_string())
}
