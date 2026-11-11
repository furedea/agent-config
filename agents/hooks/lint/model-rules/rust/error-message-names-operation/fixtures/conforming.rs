use anyhow::{bail, Result};

pub fn load_config(path: &str) -> Result<String> {
    if path.is_empty() {
        bail!("read config {path}: path is empty");
    }
    Ok(path.to_string())
}

pub fn parse_port(raw: &str) -> Result<u16, String> {
    if raw.is_empty() {
        return Err(format!("parse port {raw:?}: value is empty"));
    }
    Ok(raw.len() as u16)
}

fn describe(operation: &str, subject: &str) -> String {
    format!("{operation} {subject}: not permitted")
}

pub fn remove(path: &str) -> Result<(), String> {
    if path == "/" {
        return Err(describe("remove", path));
    }
    Ok(())
}

pub fn forward(raw: &str) -> Result<u16, std::num::ParseIntError> {
    let port = raw.parse::<u16>()?;
    if port == 0 {
        bail!("parse port {raw}: zero is reserved");
    }
    Ok(port)
}
