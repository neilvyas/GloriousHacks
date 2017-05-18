from functools import reduce


def get_deep(d, path):
    return reduce(lambda d, k: d.get(k, {}), path.split('.'), d)
