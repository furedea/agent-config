pub fn page_items(items: &[Item], page: usize, size: usize) -> &[Item] {
    // The API numbers pages from 1, so page 1 starts at index 0.
    let start = (page.saturating_sub(1) * size).min(items.len());
    &items[start..(start + size).min(items.len())]
}

pub fn remove_dir(path: &std::path::Path) -> std::io::Result<()> {
    // macOS reports ENOTEMPTY while Spotlight still holds a file open; one retry is enough (#123).
    std::fs::remove_dir_all(path).or_else(|_| std::fs::remove_dir_all(path))
}

pub fn render_keys(map: &std::collections::HashMap<String, u32>) -> Vec<String> {
    let mut keys: Vec<String> = map.keys().cloned().collect();
    // Sorted so that the generated file does not change between runs.
    keys.sort();
    keys
}

pub fn fetch(client: &Client, url: &str) -> Result<Body, Error> {
    // Retry once: the first request after the laptop wakes up often times out.
    client.get(url).or_else(|_| client.get(url))
}

pub fn weekday(days_since_epoch: i64) -> u8 {
    /* 1970-01-01 was a Thursday, so day 0 maps to index 3 when Monday is 0. */
    ((days_since_epoch + 3).rem_euclid(7)) as u8
}

/// The number of tries a request gets: the first one and each retry.
pub fn tries(retries: u32) -> u32 {
    retries + 1
}
