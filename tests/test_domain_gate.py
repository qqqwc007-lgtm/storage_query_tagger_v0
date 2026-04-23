from storage_tagger.config_loader import load_default_configs
from storage_tagger.domain_gate import DomainGate


def test_positive_storage_query():
    gate = DomainGate(load_default_configs()["rules"])
    label, conf, _ = gate.classify("shoe rack for entryway")
    assert label == "storage_related"
    assert conf >= 0.9


def test_negative_old_spice():
    gate = DomainGate(load_default_configs()["rules"])
    label, conf, _ = gate.classify("old spice deodorant for men")
    assert label == "not_storage"


def test_ambiguous_lego():
    gate = DomainGate(load_default_configs()["rules"])
    label, conf, _ = gate.classify("lego")
    assert label == "ambiguous"
