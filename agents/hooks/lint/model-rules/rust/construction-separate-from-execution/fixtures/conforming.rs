use anyhow::Result;
use std::io::BufRead;

pub fn build_client(config: &Config) -> Result<HttpClient> {
    let client = HttpClient::builder()
        .base_url(&config.api_url)
        .timeout_secs(config.timeout_secs)
        .user_agent("orders-sync")
        .build()?;
    Ok(client)
}

pub fn main_entry(config: Config) -> Result<()> {
    let client = HttpClient::new(&config.api_url);
    let repository = OrderRepository::new(Pool::new(&config.database_url, 4)?);
    let app = App::new(client, repository);
    app.run()
}

pub fn count_lines(text: &str) -> usize {
    let reader = LineReader::new(text.as_bytes());
    reader.lines().count()
}

pub struct Engine {
    store: Store,
    cache: CacheManager,
}

impl Engine {
    pub fn new(store: Store) -> Self {
        Self {
            store,
            cache: CacheManager::default(),
        }
    }
}

pub fn default_store() -> MemoryStore {
    MemoryStore::default()
}
