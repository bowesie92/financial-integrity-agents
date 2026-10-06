"""Build a full dataset for one seed. Later stages add more steps here."""
from .dataset import Dataset
from .gl_clean import build_clean_gl
from .master import build_master


def build(seed):
    ds = Dataset(seed)
    build_master(ds)
    build_clean_gl(ds)
    return ds
