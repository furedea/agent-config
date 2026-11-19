from dataclasses import dataclass


class Cart:
    __slots__ = ("_items", "_owner")

    def __init__(self, owner):
        self._owner = owner
        self._items = []

    def add(self, item):
        if item.quantity <= 0:
            raise ValueError(f"cannot add {item.sku} to the cart: quantity must be positive")
        self._items.append(item)

    def items(self):
        return self._items

    def owner(self):
        return self._owner


class Tags:
    __slots__ = ("_tags",)

    def __init__(self):
        self._tags = set()

    def tag(self, name):
        self._tags.add(name.lower())

    @property
    def all(self):
        return self._tags


class Request:
    __slots__ = ("_headers",)

    def __init__(self):
        self._headers = {}

    def set_header(self, name, value):
        self._headers[name.lower()] = value

    def headers(self):
        return self._headers


class Playlist:
    __slots__ = ("_songs",)

    def __init__(self, songs):
        self._songs = tuple(songs)

    def songs(self):
        return self._songs


class Inbox:
    __slots__ = ("_messages",)

    def __init__(self):
        self._messages = []

    def receive(self, message):
        self._messages.append(message)

    def messages(self):
        return self._messages.copy()

    def latest(self):
        return self._messages[-1]


@dataclass(slots=True)
class CsvRow:
    _cells: list[str]

    def cells(self):
        return self._cells
