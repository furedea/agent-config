import functools
import logging
import threading


class Retriever:
    def __init__(self, index, top_k):
        self.index = index
        self.top_k = top_k

    def search(self, query):
        return self.index.nearest(query, self.top_k)


class RateLimiter:
    def __init__(self, capacity, refill_per_second):
        self.capacity = capacity
        self.refill_per_second = refill_per_second
        self.tokens = capacity

    def take(self):
        if self.tokens < 1:
            return False
        self.tokens -= 1
        return True


class Point:
    __slots__ = ("x", "y")

    def __init__(self, x, y):
        self.x = x
        self.y = y


class OrderNotFoundError(Exception):
    def __init__(self, order_id):
        super().__init__(f"cannot load order {order_id}: not found")
        self.order_id = order_id


class Catalog:
    def __init__(self, products):
        self.products = products

    @functools.cached_property
    def by_sku(self):
        return {product.sku: product for product in self.products}


class Poller(threading.Thread):
    def __init__(self, source):
        super().__init__(daemon=True)
        self.source = source

    def run(self):
        self.source.poll_forever()


class ListHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.records = []

    def emit(self, record):
        self.records.append(record)


class Renderer:
    def __init__(self, template, escape):
        self.template = template
        self.escape = escape

    def render(self, context):
        return self.template.format(**{key: self.escape(value) for key, value in context.items()})
