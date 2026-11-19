use std::num::ParseIntError;

pub struct Port(u16);

pub struct Name {
    value: String,
    tags: Vec<String>,
}

impl Name {
    pub fn as_str(&self) -> &str {
        &self.value
    }

    pub fn into_inner(self) -> String {
        self.value
    }

    pub fn to_lowercase(&self) -> String {
        self.value.to_lowercase()
    }

    pub fn is_empty(&self) -> bool {
        self.value.is_empty()
    }

    pub fn contains(&self, tag: &str) -> bool {
        self.tags.iter().any(|candidate| candidate == tag)
    }
}

impl Port {
    pub fn parse(raw: &str) -> Result<Self, ParseIntError> {
        raw.trim().parse().map(Self)
    }

    pub fn from_env() -> Option<Self> {
        std::env::var("PORT").ok()?.parse().ok().map(Self)
    }
}

pub trait Catalog {
    fn as_entries(&self) -> &[Entry];
}
