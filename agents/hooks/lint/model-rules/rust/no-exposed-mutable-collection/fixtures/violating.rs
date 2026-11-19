use std::collections::{BTreeMap, HashSet};

/// Tracks stay sorted by position and never repeat; `add` keeps both rules.
pub struct Playlist {
    tracks: Vec<Track>,
}

impl Playlist {
    pub fn add(&mut self, track: Track) {
        if !self.tracks.contains(&track) {
            self.tracks.push(track);
            self.tracks.sort_by_key(|track| track.position);
        }
    }

    pub fn tracks_mut(&mut self) -> &mut Vec<Track> {
        &mut self.tracks
    }
}

/// A team never has more than `limit` members.
pub struct Team {
    members: HashSet<UserId>,
    limit: usize,
}

impl Team {
    pub fn members(&mut self) -> &mut HashSet<UserId> {
        &mut self.members
    }
}

/// `index` maps each entry's key to its position in `entries` and must stay in step with it.
pub struct Catalog {
    entries: Vec<Entry>,
    index: BTreeMap<String, usize>,
}

impl Catalog {
    pub fn index_mut(&mut self) -> &mut BTreeMap<String, usize> {
        &mut self.index
    }
}

/// Only the first `len` bytes of `storage` hold data.
pub struct Frame {
    storage: [u8; 1500],
    len: usize,
}

impl Frame {
    pub fn storage(&mut self) -> &mut [u8] {
        &mut self.storage
    }
}
