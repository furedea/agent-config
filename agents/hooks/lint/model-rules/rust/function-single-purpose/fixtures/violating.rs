use anyhow::{bail, Context, Result};
use std::collections::BTreeMap;
use std::path::Path;

pub fn report_word_counts(args: &[String]) -> Result<()> {
    let Some(path) = args.get(1) else {
        bail!("usage: words <file>");
    };
    let text = std::fs::read_to_string(path).with_context(|| format!("failed to read {path}"))?;
    let mut counts: BTreeMap<String, usize> = BTreeMap::new();
    for word in text.split_whitespace() {
        *counts.entry(word.to_lowercase()).or_default() += 1;
    }
    println!("{:<20} {:>6}", "word", "count");
    for (word, count) in &counts {
        println!("{word:<20} {count:>6}");
    }
    Ok(())
}

pub fn register_user(
    db: &mut Database,
    mailer: &Mailer,
    email: &str,
    password: &str,
) -> Result<UserId> {
    let at = email.bytes().position(|byte| byte == b'@');
    if at.is_none_or(|index| index == 0 || index + 1 == email.len()) {
        bail!("cannot register user: invalid email {email}");
    }
    let hash = hash_password(password);
    let id = db.insert_user(email, &hash)?;
    mailer.send(email, "Welcome", &format!("Your account {id} is ready."))?;
    Ok(id)
}

pub fn import_packets(path: &Path, store: &mut Store) -> Result<usize> {
    let bytes = std::fs::read(path)?;
    let mut offset = 0;
    let mut imported = 0;
    while offset + 4 <= bytes.len() {
        let length = u16::from_be_bytes([bytes[offset + 2], bytes[offset + 3]]) as usize;
        let payload = &bytes[offset + 4..offset + 4 + length];
        store.save(decode(payload)?)?;
        imported += 1;
        offset += 4 + length;
    }
    store.commit()?;
    Ok(imported)
}

pub fn load_and_render(path: &Path) -> Result<String> {
    let raw = std::fs::read_to_string(path)?;
    let post: Post = toml::from_str(&raw)?;
    let mut html = String::from("<article>");
    html.push_str(&format!("<h1>{}</h1>", post.title));
    for paragraph in post.body.split("\n\n") {
        html.push_str(&format!("<p>{paragraph}</p>"));
    }
    html.push_str("</article>");
    Ok(html)
}
