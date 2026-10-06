"""Build a full dataset for one seed. Later stages add more steps here."""
from .ap import add_ap
from .dataset import Dataset
from .gl_clean import build_clean_gl, finalize_gl
from .gl_patterns import add_decoys, add_planted
from .master import build_master
from .tax import add_use_tax


def build_clean(seed):
    """Master data and the clean ledger only (stage 1)."""
    ds = Dataset(seed)
    build_master(ds)
    build_clean_gl(ds)
    finalize_gl(ds)
    return ds


def build(seed):
    ds = Dataset(seed)
    build_master(ds)
    build_clean_gl(ds)
    add_planted(ds)
    add_decoys(ds)
    finalize_gl(ds)
    add_ap(ds)
    add_use_tax(ds)
    return ds
