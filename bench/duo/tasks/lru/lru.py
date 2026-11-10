class LRUCache:
    """A least-recently-used cache.

    - LRUCache(capacity): capacity is an int >= 0; raise ValueError if it is negative.
    - get(key, default=None): return the value and mark the key as most recently used; return default if missing.
    - put(key, value): insert or update; updating an existing key also marks it most recently used.
      When the cache is over capacity, evict the least recently used key. With capacity 0 nothing is stored.
    - len(cache) is the number of stored keys; `key in cache` checks presence WITHOUT changing recency.
    - keys() returns keys from least to most recently used.
    """

    def __init__(self, capacity):
        self.capacity = capacity
        self.data = {}

    def get(self, key, default=None):
        return self.data.get(key, default)

    def put(self, key, value):
        self.data[key] = value
        if len(self.data) > self.capacity:
            del self.data[next(iter(self.data))]

    def __len__(self):
        return len(self.data)

    def keys(self):
        return list(self.data)
