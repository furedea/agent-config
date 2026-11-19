use anyhow::Result;
use std::path::Path;

pub fn sync_orders(base_url: &str, token: &str) -> Result<usize> {
    let client = HttpClient::new(base_url)
        .with_token(token)
        .with_timeout_secs(30);
    let orders = client.fetch_orders()?;
    let overdue: Vec<_> = orders.iter().filter(|order| order.days_open > 30).collect();
    for order in &overdue {
        client.send_reminder(order.id)?;
    }
    Ok(overdue.len())
}

pub fn monthly_revenue(database_url: &str, month: u32) -> Result<u64> {
    let pool = Pool::new(database_url, 4)?;
    let repository = InvoiceRepository::new(pool);
    let invoices = repository.find_by_month(month)?;
    let paid = invoices.iter().filter(|invoice| invoice.paid);
    Ok(paid.map(|invoice| invoice.amount_cents).sum())
}

pub fn count_headings(dir: &Path) -> Result<usize> {
    let parser = MarkdownParser::with_options(ParseOptions {
        tables: true,
        footnotes: true,
    });
    let mut headings = 0;
    for entry in std::fs::read_dir(dir)? {
        let text = std::fs::read_to_string(entry?.path())?;
        headings += parser.parse(&text).headings().count();
    }
    Ok(headings)
}

pub fn charge_subscription(customer_id: u64, plan: &Plan) -> Result<Receipt> {
    let service = BillingService::builder()
        .region("eu-west-1")
        .api_key(&plan.key)
        .retries(3)
        .build()?;
    let amount = if plan.annual {
        plan.monthly_cents * 10
    } else {
        plan.monthly_cents
    };
    let receipt = service.charge(customer_id, amount)?;
    if receipt.declined {
        service.suspend(customer_id)?;
    }
    Ok(receipt)
}

pub fn archive_stale_sessions(redis_url: &str, max_idle_secs: u64) -> Result<u32> {
    let store = SessionStore::from(RedisConnection::new(redis_url)?);
    let mut archived = 0;
    for session in store.all()? {
        if session.idle_secs > max_idle_secs {
            store.archive(&session.id)?;
            archived += 1;
        }
    }
    Ok(archived)
}
