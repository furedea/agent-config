import os


def wait_for(timeout_seconds):
    return timeout_seconds * 1000


def is_enabled(feature):
    return feature.enabled


def file_size_bytes(path):
    return os.path.getsize(path)


def sleep_for(timeout):
    return timeout * 1000


def check(flag, size):
    return flag and size > 0


def resize(width, height, delay):
    return (width * 2, height * 2, delay + 5)
