from __future__ import annotations

from json import loads
from subprocess import run
from shop.settings import Config
import requests as r
from yaml import load
import numpy as np
import pandas as pd
from shop.orders import models as order_models
from shop.users import models as user_models
from swebench.inference.make_datasets.utils import parse
from typing import Self


def read_orders(path):
    frame = pd.read_csv(path)
    return np.asarray(frame["total"])


def load_settings(text):
    data = loads(text)
    return Config(**data)


def lint(paths):
    return run(["ruff", "check", *paths], check=False).returncode


def fetch(url):
    return r.get(url, timeout=5).json()


def read_manifest(handle):
    return load(handle)


def owner_of(order: order_models.Order) -> user_models.User:
    return order.owner


def patch_of(output):
    return parse(output)
