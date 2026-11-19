pub fn count_active(users: &[User]) -> usize {
    let mut count = 0;
    // loop over the users
    for user in users {
        if user.active {
            // increment the counter
            count += 1;
        }
    }
    count
}

pub fn total_cents(items: &[Item]) -> u64 {
    // sum the prices
    let total = items.iter().map(|item| item.price_cents).sum();
    // return the total
    total
}

pub fn first_name(full_name: &str) -> &str {
    /* split on whitespace and take the first part */
    full_name.split_whitespace().next().unwrap_or(full_name)
}

pub fn handle(request: &Request) -> Response {
    // ---- parse ----
    let body = parse_body(&request.body);
    // ---- validate ----
    let valid = validate(&body);
    // ---- respond ----
    if valid {
        Response::ok()
    } else {
        Response::bad_request()
    }
}

pub fn is_adult(age: u32) -> bool {
    // check if age is at least 18
    age >= 18
}
