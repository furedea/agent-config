use std::io;
use std::str::FromStr;

pub enum Format {
    Json,
    Yaml,
}

#[derive(Debug, thiserror::Error)]
#[error("unknown format: {0}")]
pub struct UnknownFormat(String);

impl FromStr for Format {
    type Err = UnknownFormat;

    fn from_str(raw: &str) -> Result<Self, Self::Err> {
        match raw {
            "json" => Ok(Self::Json),
            "yaml" => Ok(Self::Yaml),
            _ => Err(UnknownFormat(raw.to_string())),
        }
    }
}

pub fn parse_format(format: &str) -> Result<Format, UnknownFormat> {
    format.parse()
}

pub fn reason_phrase(code: u16) -> &'static str {
    match code {
        200 => "OK",
        404 => "Not Found",
        500 => "Internal Server Error",
        _ => "Unknown",
    }
}

pub fn exit_code(error: &io::Error) -> i32 {
    match error.kind() {
        io::ErrorKind::NotFound => 2,
        io::ErrorKind::PermissionDenied => 3,
        _ => 1,
    }
}

pub fn describe(kind: &str, count: usize) -> String {
    format!("{count} item(s) of kind {kind}")
}
