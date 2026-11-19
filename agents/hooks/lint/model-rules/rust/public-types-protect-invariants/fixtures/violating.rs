use std::collections::HashMap;

#[derive(Debug, Clone, Copy)]
pub struct Percentage(pub u8);

impl Percentage {
    pub fn new(value: u8) -> Result<Self, RangeError> {
        if value > 100 {
            return Err(RangeError(value));
        }
        Ok(Self(value))
    }
}

#[derive(Debug)]
pub struct SortedIds {
    pub ids: Vec<u32>,
}

impl SortedIds {
    pub fn new(mut ids: Vec<u32>) -> Self {
        ids.sort_unstable();
        ids.dedup();
        Self { ids }
    }

    pub fn contains(&self, id: u32) -> bool {
        self.ids.binary_search(&id).is_ok()
    }
}

#[derive(Debug)]
pub struct DateRange {
    pub start: Date,
    pub end: Date,
}

impl DateRange {
    pub fn new(start: Date, end: Date) -> Result<Self, RangeOrderError> {
        if end < start {
            return Err(RangeOrderError { start, end });
        }
        Ok(Self { start, end })
    }
}

#[derive(Debug)]
pub struct Inventory {
    pub items: HashMap<Sku, u32>,
    total: u32,
}

impl Inventory {
    pub fn add(&mut self, sku: Sku, count: u32) {
        *self.items.entry(sku).or_default() += count;
        self.total += count;
    }
}

#[derive(Debug)]
pub struct Email {
    pub value: String,
}

impl Email {
    pub fn parse(value: &str) -> Result<Self, EmailError> {
        if !value.contains('@') {
            return Err(EmailError::MissingAt);
        }
        Ok(Self {
            value: value.to_string(),
        })
    }
}
