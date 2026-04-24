from storage_tagger.config_loader import load_default_configs
from storage_tagger.domain_gate import DomainGate


def test_positive_storage_query():
    gate = DomainGate(load_default_configs()["rules"], thresholds=load_default_configs()["thresholds"])
    label, conf, _ = gate.classify("shoe rack for entryway")
    assert label == "storage_related"
    assert conf >= 0.9


def test_negative_old_spice():
    gate = DomainGate(load_default_configs()["rules"], thresholds=load_default_configs()["thresholds"])
    label, conf, _ = gate.classify("old spice deodorant for men")
    assert label == "not_storage"


def test_ambiguous_lego():
    gate = DomainGate(load_default_configs()["rules"], thresholds=load_default_configs()["thresholds"])
    label, conf, _ = gate.classify("lego")
    assert label == "ambiguous"


def test_domain_gate_uses_configured_confidence():
    gate = DomainGate(
        load_default_configs()["rules"],
        thresholds={"domain": {"positive_confidence": 0.88, "ambiguous_confidence": 0.44}},
    )

    label, conf, _ = gate.classify("shoe rack for entryway")
    assert label == "storage_related"
    assert conf == 0.88

    label, conf, _ = gate.classify("lego")
    assert label == "ambiguous"
    assert conf == 0.44
