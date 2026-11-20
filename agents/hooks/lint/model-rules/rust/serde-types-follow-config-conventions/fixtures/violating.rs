use serde::{Deserialize, Serialize};
use std::path::PathBuf;

/// The project's own `harness.toml`; a misspelled key must be reported, not ignored.
#[derive(Debug, Deserialize)]
pub struct HarnessConfig {
    pub name: String,
    pub jobs: usize,
}

/// The project's own `skills.json`, written and read only by this crate.
#[derive(Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct SkillManifest {
    #[serde(rename = "skillName")]
    pub skill_name: String,
    pub source_dir: PathBuf,
    #[serde(rename = "lastSynced")]
    pub last_synced: String,
}

/// The project's own `lint.toml`. Every key is optional: an absent `exclude` means nothing is excluded and an absent
/// `max_findings` means 50.
#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct LintConfig {
    pub exclude: Vec<String>,
    pub max_findings: usize,
}

/// One line of `findings.json`. Consumers treat a present `fix` key as a fix to apply, so a finding without a fix
/// must leave the key out.
#[derive(Debug, Serialize)]
pub struct Finding {
    pub rule: String,
    pub line: u32,
    pub fix: Option<String>,
}

#[derive(Debug, Deserialize)]
/* Read from the project's agents.toml. */
pub struct AgentEntry {
    name: String,
    #[serde(rename = "skillDir")]
    skill_dir: PathBuf,
    source_path: PathBuf,
}
