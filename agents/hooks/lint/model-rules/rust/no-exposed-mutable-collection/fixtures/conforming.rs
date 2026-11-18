use std::path::PathBuf;

/// The parsed command line; any list of files is valid.
pub struct Args {
    pub verbose: bool,
    pub files: Vec<PathBuf>,
}

impl Args {
    pub fn files_mut(&mut self) -> &mut Vec<PathBuf> {
        &mut self.files
    }
}

/// Raw audio samples with no rule on their values.
pub struct Samples(Vec<f32>);

impl Samples {
    pub fn as_mut_slice(&mut self) -> &mut [f32] {
        &mut self.0
    }
}

pub fn last_group<T>(groups: &mut Vec<Vec<T>>) -> &mut Vec<T> {
    if groups.is_empty() {
        groups.push(Vec::new());
    }
    groups.last_mut().expect("a group was just pushed")
}

pub fn fresh_buffer(pool: &mut Vec<Vec<u8>>) -> &mut Vec<u8> {
    pool.push(Vec::with_capacity(4096));
    pool.last_mut().expect("a buffer was just pushed")
}
