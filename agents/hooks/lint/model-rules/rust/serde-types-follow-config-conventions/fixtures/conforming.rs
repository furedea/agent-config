use serde::{Deserialize, Serialize};
use serde_json::{Map, Value};

/// Mirrors `.prettierrc`, which prettier owns; unknown keys are kept and written back.
#[derive(Debug, Serialize, Deserialize)]
pub struct PrettierConfig {
    #[serde(rename = "printWidth")]
    pub print_width: Option<u32>,
    #[serde(flatten)]
    pub rest: Map<String, Value>,
}

/// The project's own `harness.toml`.
#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields, rename_all = "kebab-case")]
pub struct HarnessConfig {
    pub name: String,
    #[serde(default)]
    pub extra_paths: Vec<String>,
    #[serde(default = "default_jobs")]
    pub max_jobs: usize,
}

/// One line of `findings.json`; a finding without a fix leaves the key out.
#[derive(Debug, Serialize)]
pub struct Finding {
    pub rule: String,
    pub line: u32,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub fix: Option<String>,
}

/// A pull request as the GitHub REST API returns it; the payload has many more fields that are not read.
#[derive(Debug, Deserialize)]
pub struct PullRequest {
    pub number: u64,
    pub title: String,
    pub draft: bool,
}

/// A JSON-RPC request this crate sends; every field is always present.
#[derive(Debug, Serialize)]
pub struct RpcRequest {
    pub jsonrpc: &'static str,
    pub id: u64,
    pub method: String,
}
