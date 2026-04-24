from storage_taxonomy.canonical_extractor import CanonicalExtractor
from storage_taxonomy.taxonomy_registry import SCENARIO_FIELD


def test_derived_scenario_must_be_canonical():
    result = CanonicalExtractor().extract("lego storage")

    assert result.fields[SCENARIO_FIELD] == ""


def test_known_derived_scenario_is_allowed():
    result = CanonicalExtractor().extract("garage tool storage")

    assert result.fields[SCENARIO_FIELD] == "garage tool storage"
