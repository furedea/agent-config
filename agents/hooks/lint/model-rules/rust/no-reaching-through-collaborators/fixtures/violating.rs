pub struct Checkout {
    session: Session,
}

impl Checkout {
    pub fn reserve(&self) -> Result<Connection, Error> {
        self.session.connection().pool().acquire()
    }
}

pub fn database_password(app: &App) -> String {
    app.config().database().credentials().password().to_string()
}

pub fn tax_country(invoice: &Invoice) -> CountryCode {
    invoice.customer().account().billing_address().country()
}

pub fn notify(ctx: &Context, message: &Message) -> Result<(), Error> {
    ctx.services().mailer().transport().send(message)
}

pub fn queue_depth(worker: &Worker) -> usize {
    worker.scheduler().queue().pending().len()
}
