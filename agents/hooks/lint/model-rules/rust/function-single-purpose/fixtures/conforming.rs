use anyhow::Result;
use std::path::Path;

pub fn publish(path: &Path, site: &mut Site) -> Result<()> {
    let post = load_post(path)?;
    let html = render_post(&post);
    site.write_page(&post.slug, &html)?;
    site.update_index(&post)
}

pub fn http_status_text(code: u16) -> &'static str {
    match code {
        200 => "OK",
        201 => "Created",
        204 => "No Content",
        301 => "Moved Permanently",
        304 => "Not Modified",
        400 => "Bad Request",
        401 => "Unauthorized",
        403 => "Forbidden",
        404 => "Not Found",
        409 => "Conflict",
        500 => "Internal Server Error",
        503 => "Service Unavailable",
        _ => "Unknown",
    }
}

pub fn read_post(path: &Path) -> Result<Post> {
    load_post(path)
}

pub fn summary(post: &Post) -> Summary {
    let words = post.body.split_whitespace().count();
    let minutes = words.div_ceil(200);
    let first_line = post.body.lines().next().unwrap_or_default().to_string();
    Summary {
        title: post.title.clone(),
        words,
        minutes,
        first_line,
    }
}

pub fn median(values: &mut [f64]) -> Option<f64> {
    if values.is_empty() {
        return None;
    }
    values.sort_by(f64::total_cmp);
    let middle = values.len() / 2;
    if values.len() % 2 == 0 {
        Some((values[middle - 1] + values[middle]) / 2.0)
    } else {
        Some(values[middle])
    }
}
