pub struct Label {
    name: String,
    bytes: Vec<u8>,
    kind: Kind,
}

impl Label {
    pub fn as_upper(&self) -> String {
        self.name.to_uppercase()
    }

    pub fn into_name(&self) -> &str {
        &self.name
    }

    pub fn to_bytes(&self) -> &[u8] {
        &self.bytes
    }

    pub fn empty(&self) -> bool {
        self.name.is_empty()
    }

    pub fn directory(&self) -> bool {
        self.kind == Kind::Directory
    }
}

pub fn parse_port(raw: &str) -> u16 {
    raw.trim().parse().unwrap_or(0)
}

pub trait Archive {
    fn into_entries(&self) -> &[Entry];
}
