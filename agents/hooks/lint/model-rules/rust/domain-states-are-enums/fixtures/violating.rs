use std::time::Duration;

pub enum OrderState {
    Pending,
    Paid,
    Shipped,
    Cancelled,
}

pub fn render(report: &Report, format: &str) -> String {
    match format {
        "json" => report.to_json(),
        "yaml" => report.to_yaml(),
        _ => report.to_text(),
    }
}

pub fn retry_delay(policy: String, attempt: u32) -> Duration {
    if policy == "exponential" {
        Duration::from_millis(100 * 2u64.pow(attempt))
    } else if policy == "linear" {
        Duration::from_millis(100 * u64::from(attempt))
    } else {
        Duration::from_millis(100)
    }
}

pub fn status_label(state: &OrderState) -> &'static str {
    match state {
        OrderState::Paid => "paid",
        OrderState::Shipped => "shipped",
        _ => "pending",
    }
}

pub fn should_page(level: &str) -> bool {
    level == "error" || level == "fatal"
}

pub fn endpoint(provider: &str) -> &'static str {
    if provider == "claude" {
        "https://claude.example/v1"
    } else {
        "https://codex.example/v1"
    }
}
